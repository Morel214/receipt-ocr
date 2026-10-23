"""Multi-tenant receipt job queue orchestration service."""

import json
import logging
from pathlib import Path
from typing import Any

from ocr_hub import config
from ocr_hub.repositories import jobs_repo, tenants_repo
from ocr_hub.services.ocr_engine import (
    analyze_receipt_image,
    generate_receipt_filename,
    normalize_store_name,
    validate_ocr_result,
)
from ocr_hub.services.webhook_dispatcher import dispatch_receipt_webhook

logger = logging.getLogger(__name__)

CONFIRMABLE_STATUSES = (
    jobs_repo.AWAITING_CONFIRMATION,
    jobs_repo.NEEDS_REVIEW,
    jobs_repo.AWAITING_EDIT,
    jobs_repo.DELIVERY_FAILED,
)


def _content_type_for(path: str) -> str:
    """Infer an image MIME type from a file path."""
    return "image/png" if Path(path).suffix.lower() == ".png" else "image/jpeg"


def _read_image(job: dict[str, Any]) -> bytes:
    """Read the saved receipt image bytes for OCR processing."""
    path = Path(job["image_path"])
    if not path.exists():
        raise FileNotFoundError(f"Receipt image not found: {path}")
    return path.read_bytes()


def _delete_image(job: dict[str, Any]) -> None:
    """Best-effort removal of a saved receipt image."""
    path = Path(job["image_path"]) if job.get("image_path") else None
    if path and path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _rename_job_image(
    job: dict[str, Any],
    result_dict: dict[str, Any],
    database_path: str | Path | None = None,
) -> None:
    """Rename a saved receipt image to ``{date}-{store}-{amount}.{ext}`` inside its directory."""
    old_path = Path(job["image_path"])
    if not old_path.exists():
        return

    store_name = result_dict.get("store_name") or "Unknown Store"
    txn_date = str(result_dict.get("transaction_date") or "")
    total_amount = float(result_dict.get("total_amount") or 0.0)
    ext = old_path.suffix.lstrip(".") or "jpg"

    try:
        filename = generate_receipt_filename(
            store_name, txn_date, total_amount, ext, upload_dir=old_path.parent
        )
        new_path = old_path.parent / filename
        old_path.rename(new_path)
        jobs_repo.update_job_image_path(job["id"], str(new_path), database_path=database_path)
    except Exception:
        logger.exception("[_rename_job_image] Could not rename image for job %s", job["id"])


def ocr_one_job(
    job: dict[str, Any],
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the 2-stage OCR + Classification pipeline on a single job and update its queue status."""
    job_id = job["id"]
    tenant_id = job["tenant_id"]
    tenant = tenants_repo.get_tenant_by_id(tenant_id, database_path=database_path)
    if tenant is None:
        raise ValueError(f"Tenant {tenant_id} not found for job {job_id}")

    content = _read_image(job)
    content_type = _content_type_for(job["image_path"])

    logger.info(
        "[ocr_one_job] Running 2-stage OCR pipeline for tenant=%s job=%s",
        tenant["name"],
        job_id,
    )
    try:
        result = analyze_receipt_image(
            content=content,
            content_type=content_type,
            provider=tenant.get("ocr_provider"),
            model=tenant.get("ocr_model"),
            classifier_provider=tenant.get("classifier_provider"),
            classifier_model=tenant.get("classifier_model"),
            subcategories=tenant.get("subcategories"),
            default_currency=tenant.get("default_currency", "EUR"),
            language=tenant.get("language", "en"),
        )
    except Exception as exc:
        logger.error("[ocr_one_job] Job %s OCR failed: %s", job_id, exc)
        jobs_repo.set_job_status(
            job_id, jobs_repo.FAILED, str(exc), database_path=database_path
        )
        raise

    result_dict = result.model_dump(mode="json")
    result_dict["store_name"] = normalize_store_name(result_dict.get("store_name"))
    jobs_repo.update_job_ocr(job_id, result_dict, database_path=database_path)

    item_confidences = [
        item.get("confidence")
        for item in result_dict.get("items", [])
        if item.get("confidence") is not None
    ]
    confidence = result_dict.get("confidence")
    if item_confidences:
        confidence = min(min(item_confidences), confidence if confidence is not None else 1.0)
    if confidence is not None and confidence < config.RECEIPT_OCR_CONFIDENCE_THRESHOLD:
        jobs_repo.set_job_needs_review(job_id, database_path=database_path)

    store_name = result_dict.get("store_name") or ""
    txn_date = str(result_dict.get("transaction_date") or "")
    total_amount = float(result_dict.get("total_amount") or 0.0)
    if store_name and txn_date and total_amount:
        dup_id = jobs_repo.find_duplicate_confirmed_job(
            tenant_id=tenant_id,
            store_name=store_name,
            transaction_date=txn_date,
            total_amount=total_amount,
            exclude_job_id=job_id,
            database_path=database_path,
        )
        jobs_repo.set_job_duplicate(job_id, dup_id is not None, database_path=database_path)

    _rename_job_image(job, result_dict, database_path=database_path)
    updated = jobs_repo.get_job(job_id, tenant_id=tenant_id, database_path=database_path)
    assert updated is not None
    return updated


def process_next_queued_job(
    tenant_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """OCR the oldest queued job for ``tenant_id``, if any."""
    job = jobs_repo.get_next_queued_job(tenant_id=tenant_id, database_path=database_path)
    if job is None:
        return None
    return ocr_one_job(job, database_path=database_path)


def process_batch(
    tenant_id: int,
    batch_id: str,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """OCR every queued job in a batch sequentially for ``tenant_id``."""
    jobs = jobs_repo.list_jobs(
        tenant_id=tenant_id,
        status=jobs_repo.QUEUED,
        batch_id=batch_id,
        database_path=database_path,
    )
    processed: list[dict[str, Any]] = []
    for job in jobs:
        try:
            processed.append(ocr_one_job(job, database_path=database_path))
        except Exception:
            logger.exception(
                "[process_batch] Job %s in batch %s (tenant %s) failed",
                job["id"],
                batch_id,
                tenant_id,
            )
    return processed


def confirm_job(
    tenant_id: int,
    job_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Confirm a job and push its parsed OCR payload to the tenant's configured webhook.

    Raises:
        ValueError: If job does not exist, belongs to another tenant, has no OCR result, or is a duplicate.
        RuntimeError: If webhook delivery fails (job marked ``delivery_failed`` so user can retry).
    """
    job = jobs_repo.get_job(job_id, tenant_id=tenant_id, database_path=database_path)
    if job is None:
        raise ValueError(f"Receipt job #{job_id} not found.")
    if not job.get("ocr_json"):
        raise ValueError(f"Receipt job #{job_id} has no OCR result yet.")

    tenant = tenants_repo.get_tenant_by_id(tenant_id, database_path=database_path)
    if tenant is None:
        raise ValueError(f"Tenant not found (tenant_id={tenant_id}).")

    result = validate_ocr_result(json.loads(job["ocr_json"]))
    store_name = normalize_store_name(result.store_name)
    txn_date = str(result.transaction_date) if result.transaction_date else ""
    total_amount = float(result.total_amount)

    existing_id = jobs_repo.find_duplicate_confirmed_job(
        tenant_id=tenant_id,
        store_name=store_name,
        transaction_date=txn_date,
        total_amount=total_amount,
        exclude_job_id=job_id,
        database_path=database_path,
    )
    if existing_id is not None:
        raise ValueError(
            f"Receipt #{job_id} is a duplicate of already confirmed receipt #{existing_id} "
            f"({store_name} / {txn_date} / {total_amount:.2f}). Use /reject {job_id}."
        )

    try:
        delivery = dispatch_receipt_webhook(tenant=tenant, result=result, job_id=job_id)
    except RuntimeError as exc:
        jobs_repo.set_job_status(
            job_id, jobs_repo.DELIVERY_FAILED, str(exc), database_path=database_path
        )
        raise

    jobs_repo.mark_job_confirmed(
        job_id=job_id,
        webhook_delivered=delivery["delivered"],
        webhook_response_code=delivery["status_code"],
        database_path=database_path,
    )

    try:
        process_next_queued_job(tenant_id=tenant_id, database_path=database_path)
    except Exception:
        logger.exception("[confirm_job] Failed to advance queue after confirming job %s", job_id)

    return {
        "job_id": job_id,
        "store_name": store_name,
        "transaction_date": txn_date,
        "total_amount": total_amount,
        "currency": result.currency,
        "items_count": len(result.items),
        "webhook_delivered": delivery["delivered"],
        "webhook_status_code": delivery["status_code"],
        "webhook_response": delivery["response"],
    }


def reject_job(
    tenant_id: int,
    job_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Reject a job: delete its image and database row, then advance the tenant's queue."""
    job = jobs_repo.get_job(job_id, tenant_id=tenant_id, database_path=database_path)
    if job is None:
        return False
    _delete_image(job)
    jobs_repo.delete_job(job_id, tenant_id=tenant_id, database_path=database_path)
    try:
        process_next_queued_job(tenant_id=tenant_id, database_path=database_path)
    except Exception:
        logger.exception("[reject_job] Failed to advance queue after rejecting job %s", job_id)
    return True


def confirm_all(
    tenant_id: int,
    batch_id: str | None = None,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Confirm all open jobs for ``tenant_id`` (optionally filtered to ``batch_id``)."""
    jobs = (
        jobs_repo.list_jobs(tenant_id=tenant_id, batch_id=batch_id, database_path=database_path)
        if batch_id
        else jobs_repo.list_open_jobs(tenant_id=tenant_id, database_path=database_path)
    )
    confirmed: list[dict[str, Any]] = []
    for job in jobs:
        if job["status"] in CONFIRMABLE_STATUSES:
            try:
                confirmed.append(
                    confirm_job(tenant_id=tenant_id, job_id=job["id"], database_path=database_path)
                )
            except (ValueError, RuntimeError) as exc:
                logger.warning("[confirm_all] Skipping job %s: %s", job["id"], exc)
    return confirmed


def reject_all(
    tenant_id: int,
    batch_id: str | None = None,
    database_path: str | Path | None = None,
) -> list[int]:
    """Reject all open jobs for ``tenant_id`` (optionally filtered to ``batch_id``)."""
    jobs = (
        jobs_repo.list_jobs(tenant_id=tenant_id, batch_id=batch_id, database_path=database_path)
        if batch_id
        else jobs_repo.list_open_jobs(tenant_id=tenant_id, database_path=database_path)
    )
    rejected: list[int] = []
    for job in jobs:
        if job["status"] in CONFIRMABLE_STATUSES:
            _delete_image(job)
            jobs_repo.delete_job(job["id"], tenant_id=tenant_id, database_path=database_path)
            rejected.append(job["id"])
    try:
        process_next_queued_job(tenant_id=tenant_id, database_path=database_path)
    except Exception:
        logger.exception("[reject_all] Failed to advance queue for tenant %s", tenant_id)
    return rejected
