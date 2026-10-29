"""Repository for opt-in personal receipt persistence (populated only when 'hub_db' is enabled)."""

from pathlib import Path
from typing import Any

from ocr_hub.db.connection import get_connection
from ocr_hub.db.models import ReceiptOCRResult


def _fetch_items_by_receipt_ids(
    cursor: Any,
    receipt_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Fetch line items for one or more receipt IDs in a single query."""
    if not receipt_ids:
        return {}
    placeholders = ",".join("?" for _ in receipt_ids)
    cursor.execute(
        f"""
        SELECT
            id,
            receipt_id,
            line_no,
            raw_name,
            clean_name,
            category_code,
            subcategory_code,
            product_id,
            alias_id,
            unit,
            quantity,
            unit_price,
            total_price,
            brand,
            off_search_query,
            pack_amount,
            pack_unit,
            match_source
        FROM receipt_items
        WHERE receipt_id IN ({placeholders})
        ORDER BY receipt_id ASC, line_no ASC, id ASC;
        """,
        receipt_ids,
    )
    cols = [col[0] for col in cursor.description]
    grouped: dict[int, list[dict[str, Any]]] = {rid: [] for rid in receipt_ids}
    for row in cursor.fetchall():
        item = dict(zip(cols, row))
        grouped.setdefault(int(item["receipt_id"]), []).append(item)
    return grouped


def get_receipt(
    receipt_id: int,
    tenant_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single persisted receipt (with its line items) scoped to ``tenant_id``."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                tenant_id,
                job_id,
                store_id,
                store_name,
                transaction_date,
                total_amount,
                currency,
                confidence,
                cache_hits,
                llm_classified_count,
                created_at
            FROM receipts
            WHERE id = ? AND tenant_id = ?
            LIMIT 1;
            """,
            (int(receipt_id), int(tenant_id)),
        )
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if row is None:
            return None

        receipt = dict(zip(cols, row))
        items_map = _fetch_items_by_receipt_ids(cursor, [int(receipt["id"])])
        items = items_map.get(int(receipt["id"]), [])
        receipt["items_count"] = len(items)
        receipt["items"] = items
        return receipt


def save_confirmed_receipt(
    tenant_id: int,
    result: ReceiptOCRResult,
    job_id: int | None = None,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist a confirmed receipt and its line items into ``receipts`` and ``receipt_items``.

    Idempotent on ``job_id`` when ``job_id`` is provided.
    """
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        if job_id is not None:
            cursor.execute(
                "SELECT id FROM receipts WHERE job_id = ? AND tenant_id = ? LIMIT 1;",
                (int(job_id), int(tenant_id)),
            )
            existing = cursor.fetchone()
            if existing is not None:
                existing_id = int(existing[0])
            else:
                existing_id = None
        else:
            existing_id = None

        if existing_id is None:
            txn_date = str(result.transaction_date) if result.transaction_date else None
            cursor.execute(
                """
                INSERT INTO receipts (
                    tenant_id,
                    job_id,
                    store_id,
                    store_name,
                    transaction_date,
                    total_amount,
                    currency,
                    confidence,
                    cache_hits,
                    llm_classified_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    int(tenant_id),
                    int(job_id) if job_id is not None else None,
                    result.store_id,
                    result.store_name or "Unknown Store",
                    txn_date,
                    float(result.total_amount),
                    result.currency or "PLN",
                    result.confidence,
                    int(result.cache_hits or 0),
                    int(result.llm_classified_count or 0),
                ),
            )
            receipt_id = int(cursor.lastrowid)

            for line_no, item in enumerate(result.items, start=1):
                cursor.execute(
                    """
                    INSERT INTO receipt_items (
                        receipt_id,
                        line_no,
                        raw_name,
                        clean_name,
                        category_code,
                        subcategory_code,
                        product_id,
                        alias_id,
                        unit,
                        quantity,
                        unit_price,
                        total_price,
                        brand,
                        off_search_query,
                        pack_amount,
                        pack_unit,
                        match_source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        receipt_id,
                        line_no,
                        item.name,
                        item.clean_name or item.name,
                        item.category,
                        item.subcategory,
                        item.product_id,
                        item.alias_id,
                        item.unit or "pcs",
                        float(item.quantity),
                        float(item.unit_price),
                        float(item.total_price),
                        item.brand,
                        item.off_search_query,
                        item.pack_amount,
                        item.pack_unit,
                        item.match_source or "llm",
                    ),
                )
        else:
            receipt_id = existing_id

    saved = get_receipt(receipt_id, tenant_id=tenant_id, database_path=database_path)
    assert saved is not None
    return saved


def list_receipts(
    tenant_id: int,
    month: str | None = None,
    limit: int = 50,
    offset: int = 0,
    include_items: bool = False,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List saved receipts for ``tenant_id``, optionally filtered by ``YYYY-MM`` month prefix."""
    clauses = ["r.tenant_id = ?"]
    params: list[Any] = [int(tenant_id)]

    if month and month.strip():
        clauses.append("r.transaction_date LIKE ?")
        params.append(f"{month.strip()}%")

    where_sql = " AND ".join(clauses)
    params.extend([int(limit), int(offset)])

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                r.id,
                r.tenant_id,
                r.job_id,
                r.store_id,
                r.store_name,
                r.transaction_date,
                r.total_amount,
                r.currency,
                r.confidence,
                r.cache_hits,
                r.llm_classified_count,
                r.created_at,
                (SELECT COUNT(*) FROM receipt_items ri WHERE ri.receipt_id = r.id) AS items_count
            FROM receipts r
            WHERE {where_sql}
            ORDER BY COALESCE(r.transaction_date, '') DESC, r.id DESC
            LIMIT ? OFFSET ?;
            """,
            params,
        )
        cols = [col[0] for col in cursor.description]
        receipts = [dict(zip(cols, row)) for row in cursor.fetchall()]

        if include_items and receipts:
            rids = [int(r["id"]) for r in receipts]
            items_map = _fetch_items_by_receipt_ids(cursor, rids)
            for rec in receipts:
                rec["items"] = items_map.get(int(rec["id"]), [])

    return receipts
