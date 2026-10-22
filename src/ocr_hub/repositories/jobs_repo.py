"""Data access repository for the multi-tenant Telegram & API receipt job queue."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ocr_hub.db.connection import get_connection

# Job status constants
QUEUED = "queued"
AWAITING_CONFIRMATION = "awaiting_confirmation"
NEEDS_REVIEW = "needs_review"
AWAITING_EDIT = "awaiting_edit"
DELIVERY_FAILED = "delivery_failed"
CONFIRMED = "confirmed"
REJECTED = "rejected"
FAILED = "failed"

# Statuses that are considered "open" (awaiting a user decision or webhook retry)
OPEN_STATUSES = (AWAITING_CONFIRMATION, NEEDS_REVIEW, AWAITING_EDIT, DELIVERY_FAILED)


def create_job(
    tenant_id: int,
    batch_id: str | None,
    chat_id: str,
    message_id: int | None,
    filename: str,
    image_path: str,
    database_path: str | Path | None = None,
) -> int:
    """Create a receipt job scoped to ``tenant_id`` and return its ID."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO receipt_jobs (
                tenant_id, batch_id, telegram_chat_id, telegram_message_id,
                original_filename, image_path, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (tenant_id, batch_id, str(chat_id), message_id, filename, image_path, QUEUED),
        )
        return int(cursor.lastrowid)


def get_job(
    job_id: int,
    tenant_id: int | None = None,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single job (optionally enforcing ``tenant_id`` ownership), or None."""
    query = "SELECT * FROM receipt_jobs WHERE id = ?"
    params: list[Any] = [job_id]
    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)
    query += ";"

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None


def list_jobs(
    tenant_id: int,
    status: str | None = None,
    batch_id: str | None = None,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return jobs for ``tenant_id`` optionally filtered by status and/or batch."""
    query = "SELECT * FROM receipt_jobs WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    if batch_id is not None:
        query += " AND batch_id = ?"
        params.append(batch_id)
    query += " ORDER BY id ASC;"

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_next_queued_job(
    tenant_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the oldest job in ``queued`` state for a tenant."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM receipt_jobs WHERE tenant_id = ? AND status = ? ORDER BY id ASC LIMIT 1;",
            (tenant_id, QUEUED),
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None


def count_by_status(
    tenant_id: int,
    status: str,
    database_path: str | Path | None = None,
) -> int:
    """Return the number of jobs in a given status for ``tenant_id``."""
    with get_connection(database_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM receipt_jobs WHERE tenant_id = ? AND status = ?;",
            (tenant_id, status),
        )
        return int(cur.fetchone()[0])


def update_job_ocr(
    job_id: int,
    result: dict[str, Any],
    database_path: str | Path | None = None,
) -> None:
    """Persist OCR output and move the job to ``awaiting_confirmation``."""
    items = result.get("items", [])
    now = datetime.now().replace(microsecond=0).isoformat()
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE receipt_jobs
            SET ocr_json = ?, items_json = ?,
                store_name = ?, transaction_date = ?, total_amount = ?,
                currency = ?, confidence = ?, status = ?, updated_at = ?
            WHERE id = ?;
            """,
            (
                json.dumps(result, ensure_ascii=False, default=str),
                json.dumps(items, ensure_ascii=False, default=str),
                result.get("store_name"),
                str(result.get("transaction_date")) if result.get("transaction_date") else None,
                float(result["total_amount"]),
                result.get("currency"),
                result.get("confidence"),
                AWAITING_CONFIRMATION,
                now,
                job_id,
            ),
        )


def set_job_status(
    job_id: int,
    status: str,
    error: str | None = None,
    database_path: str | Path | None = None,
) -> None:
    """Update job status and optionally record an error message."""
    now = datetime.now().replace(microsecond=0).isoformat()
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE receipt_jobs SET status = ?, last_error = ?, updated_at = ? WHERE id = ?;",
            (status, error, now, job_id),
        )


def set_job_needs_review(
    job_id: int,
    database_path: str | Path | None = None,
) -> None:
    """Flag a job as needing manual review (e.g. low OCR confidence)."""
    set_job_status(job_id, NEEDS_REVIEW, database_path=database_path)


def set_job_duplicate(
    job_id: int,
    is_duplicate: bool,
    database_path: str | Path | None = None,
) -> None:
    """Record whether the receipt looks like a duplicate for this tenant."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE receipt_jobs SET is_duplicate = ? WHERE id = ?;",
            (1 if is_duplicate else 0, job_id),
        )


def find_duplicate_confirmed_job(
    tenant_id: int,
    store_name: str,
    transaction_date: str,
    total_amount: float,
    exclude_job_id: int | None = None,
    database_path: str | Path | None = None,
) -> int | None:
    """Return the job ID of an already confirmed receipt with identical store/date/amount for this tenant."""
    query = """
        SELECT id
        FROM receipt_jobs
        WHERE tenant_id = ?
          AND status = ?
          AND LOWER(TRIM(store_name)) = LOWER(TRIM(?))
          AND transaction_date = ?
          AND total_amount = ?
    """
    params: list[Any] = [tenant_id, CONFIRMED, store_name, str(transaction_date), float(total_amount)]
    if exclude_job_id is not None:
        query += " AND id != ?"
        params.append(exclude_job_id)
    query += " LIMIT 1;"

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return int(row[0]) if row else None


def mark_job_confirmed(
    job_id: int,
    webhook_delivered: bool = True,
    webhook_response_code: int | None = None,
    database_path: str | Path | None = None,
) -> None:
    """Mark a job as confirmed and record webhook delivery status."""
    now = datetime.now().replace(microsecond=0).isoformat()
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE receipt_jobs
            SET status = ?,
                webhook_delivered = ?,
                webhook_response_code = ?,
                last_error = NULL,
                updated_at = ?
            WHERE id = ?;
            """,
            (CONFIRMED, 1 if webhook_delivered else 0, webhook_response_code, now, job_id),
        )


def update_job_image_path(
    job_id: int,
    image_path: str,
    database_path: str | Path | None = None,
) -> None:
    """Update the stored image path for a job."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE receipt_jobs SET image_path = ? WHERE id = ?;",
            (image_path, job_id),
        )


def list_open_jobs(
    tenant_id: int,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return all open jobs awaiting confirmation for ``tenant_id``."""
    placeholders = ",".join("?" for _ in OPEN_STATUSES)
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM receipt_jobs WHERE tenant_id = ? AND status IN ({placeholders}) ORDER BY id ASC;",
            (tenant_id, *OPEN_STATUSES),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_stale_jobs(
    tenant_id: int,
    timeout_hours: float,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return open jobs for ``tenant_id`` whose last prompt is older than ``timeout_hours``."""
    cutoff = (datetime.now() - timedelta(hours=timeout_hours)).replace(microsecond=0).isoformat()
    placeholders = ",".join("?" for _ in OPEN_STATUSES)
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT * FROM receipt_jobs
            WHERE tenant_id = ?
              AND status IN ({placeholders})
              AND (last_prompt_at IS NULL OR last_prompt_at < ?)
            ORDER BY id ASC;
            """,
            (tenant_id, *OPEN_STATUSES, cutoff),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def delete_job(
    job_id: int,
    tenant_id: int | None = None,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a job (optionally checking ``tenant_id``). Returns True if removed."""
    query = "DELETE FROM receipt_jobs WHERE id = ?"
    params: list[Any] = [job_id]
    if tenant_id is not None:
        query += " AND tenant_id = ?"
        params.append(tenant_id)
    query += ";"
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.rowcount > 0
