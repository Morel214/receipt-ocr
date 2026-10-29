"""Multi-tenant receipt job queue orchestration service."""

import json
import logging
from pathlib import Path
import re
from typing import Any

from ocr_hub import config
from ocr_hub.repositories import catalog_repo, jobs_repo, receipts_repo, taxonomy_repo, tenants_repo
from ocr_hub.services.ocr_engine import (
    analyze_receipt_image,
    commit_result_to_catalog,
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

_KNOWN_EDIT_KEYS = (
    "off_search_query",
    "transaction_date",
    "total_amount",
    "total_price",
    "subcategory",
    "store_name",
    "unit_price",
    "raw_name",
    "currency",
    "quantity",
    "name_pl",
    "name_en",
    "subcat",
    "store",
    "total",
    "price",
    "brand",
    "date",
    "name",
    "unit",
    "qty",
    "off",
    "raw",
)
_EDIT_KEY_RE = re.compile(
    r"(?:^|\s+)(" + "|".join(_KNOWN_EDIT_KEYS) + r")\s*=\s*",
    flags=re.IGNORECASE,
)
_ITEM_PREFIX_RE = re.compile(r"^\s*#?(\d+)\s+(.+?)\s*$", flags=re.DOTALL)


def parse_edit_assignments(spec: str) -> dict[str, str]:
    """Parse ``key=value`` pairs from a mobile-friendly Telegram ``/edit`` command string.

    Supports both unquoted multi-word values (``name=ser żółty price=12,99``) and quoted values.
    """
    matches = list(_EDIT_KEY_RE.finditer(spec))
    if not matches or matches[0].start() > 0 and spec[: matches[0].start()].strip():
        return {}

    parsed: dict[str, str] = {}
    for idx, match in enumerate(matches):
        key = match.group(1).lower()
        val_start = match.end()
        val_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(spec)
        raw_val = spec[val_start:val_end].strip()
        if len(raw_val) >= 2 and raw_val[0] == raw_val[-1] and raw_val[0] in ('"', "'"):
            raw_val = raw_val[1:-1].strip()
        parsed[key] = raw_val
    return parsed


def _parse_decimal(raw_value: str, field_name: str) -> float:
    """Parse a dot- or Polish comma-formatted decimal number."""
    cleaned = raw_value.strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid number for '{field_name}': '{raw_value}'.") from exc


def edit_job_before_confirm(
    tenant_id: int,
    job_id: int,
    edit_spec: str,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply header or line-item corrections to an open receipt job prior to ``/confirm``.

    Supported forms:
        - ``<item_no> delete`` — remove an erroneous OCR line item (1-based index).
        - ``<item_no> name=ser żółty subcat=dairy qty=1 unit=pcs price=12.99`` — edit item fields.
        - ``store=Biedronka date=2026-10-28 total=54.30 currency=PLN`` — edit receipt header
          (``total=sum`` recalculates receipt total from line items).
    """
    job = jobs_repo.get_job(job_id, tenant_id=tenant_id, database_path=database_path)
    if job is None:
        raise ValueError(f"Receipt job #{job_id} not found.")
    if job.get("status") not in CONFIRMABLE_STATUSES:
        raise ValueError(
            f"Receipt #{job_id} cannot be edited in status '{job.get('status')}'."
        )
    if not job.get("ocr_json"):
        raise ValueError(f"Receipt #{job_id} has no OCR payload to edit.")

    spec = (edit_spec or "").strip()
    if not spec:
        raise ValueError(
            f"Empty edit command. Example: /edit {job_id} 1 name=jajka price=9.99 or /edit {job_id} total=54.30"
        )

    tenant = tenants_repo.get_tenant_by_id(tenant_id, database_path=database_path)
    lang = "pl" if (tenant and str(tenant.get("language", "pl")).lower() == "pl") else "en"

    result = validate_ocr_result(json.loads(job["ocr_json"]))
    subcat_map = {
        s["code"].lower(): s
        for cat in taxonomy_repo.get_taxonomy_tree(only_active=True, database_path=database_path)
        for s in cat.get("subcategories", [])
    }
    cat_id_to_code = {
        int(cat["id"]): str(cat["code"])
        for cat in taxonomy_repo.get_taxonomy_tree(only_active=True, database_path=database_path)
    }

    item_match = _ITEM_PREFIX_RE.match(spec)
    if item_match:
        item_no = int(item_match.group(1))
        rest = item_match.group(2).strip()
        if item_no < 1 or item_no > len(result.items):
            raise ValueError(
                f"Item #{item_no} out of range (receipt #{job_id} has {len(result.items)} item(s))."
            )

        if rest.lower() in ("delete", "del", "rm", "remove"):
            if len(result.items) <= 1:
                raise ValueError(
                    "Cannot delete the last remaining item on a receipt. Use /reject instead."
                )
            result.items.pop(item_no - 1)
        else:
            assignments = parse_edit_assignments(rest)
            if not assignments:
                raise ValueError(
                    f"Could not parse item edits. Example: /edit {job_id} {item_no} name=jajka price=9.99 subcat=eggs"
                )
            target = result.items[item_no - 1]
            classification_edited = False
            qty_or_price_edited = False
            explicit_total = False

            if "raw" in assignments or "raw_name" in assignments:
                raw_text = (assignments.get("raw_name") or assignments.get("raw") or "").strip()
                if not raw_text:
                    raise ValueError("Item raw name cannot be empty.")
                target.name = raw_text

            if "unit" in assignments:
                u = assignments["unit"].strip().lower().rstrip(".")
                if u not in ("pcs", "kg", "l", "szt", "litr"):
                    raise ValueError("Allowed units: pcs, kg, l.")
                target.unit = "kg" if u == "kg" else ("l" if u in ("l", "litr") else "pcs")

            if "qty" in assignments or "quantity" in assignments:
                raw_qty = assignments.get("quantity") or assignments.get("qty") or ""
                qty_val = _parse_decimal(raw_qty, "qty")
                if qty_val <= 0:
                    raise ValueError("Quantity must be greater than 0.")
                target.quantity = qty_val
                qty_or_price_edited = True

            if "price" in assignments or "unit_price" in assignments:
                raw_price = assignments.get("unit_price") or assignments.get("price") or ""
                target.unit_price = _parse_decimal(raw_price, "price")
                qty_or_price_edited = True

            if "total" in assignments or "total_price" in assignments:
                raw_tot = assignments.get("total_price") or assignments.get("total") or ""
                target.total_price = _parse_decimal(raw_tot, "total")
                explicit_total = True

            if qty_or_price_edited and not explicit_total:
                target.total_price = round(float(target.quantity) * float(target.unit_price), 2)
            elif explicit_total and not qty_or_price_edited and float(target.quantity) > 0:
                target.unit_price = round(float(target.total_price) / float(target.quantity), 2)

            explicit_subcat = assignments.get("subcategory") or assignments.get("subcat")
            if explicit_subcat is not None:
                sub_key = explicit_subcat.strip().lower()
                if sub_key in ("none", "null", "-"):
                    target.subcategory = None
                    target.category = None
                else:
                    sub_obj = subcat_map.get(sub_key)
                    if sub_obj is None:
                        allowed_codes = ", ".join(sorted(subcat_map.keys()))
                        raise ValueError(
                            f"Unknown subcategory '{explicit_subcat}'. Active subcategories: {allowed_codes}"
                        )
                    target.subcategory = str(sub_obj["code"])
                    target.category = cat_id_to_code.get(int(sub_obj["category_id"]))
                classification_edited = True

            if "brand" in assignments:
                target.brand = assignments["brand"].strip() or None
                classification_edited = True

            if "off" in assignments or "off_search_query" in assignments:
                off_val = (
                    assignments.get("off_search_query")
                    if "off_search_query" in assignments
                    else assignments.get("off", "")
                )
                target.off_search_query = off_val.strip() or None
                classification_edited = True

            has_name_edit = any(k in assignments for k in ("name", "name_pl", "name_en"))
            if has_name_edit:
                classification_edited = True
                new_clean = assignments.get("name", "").strip().lower()
                new_pl = assignments.get("name_pl", "").strip().lower()
                new_en = assignments.get("name_en", "").strip().lower()

                lookup_pl = new_pl or (new_clean if lang == "pl" else "")
                lookup_en = new_en or (new_clean if lang == "en" else "")
                existing_prod = catalog_repo.find_product_by_clean_name(
                    name_pl=lookup_pl or None,
                    name_en=lookup_en or None,
                    database_path=database_path,
                )

                if existing_prod is not None and not (new_pl and new_en):
                    target.product_id = int(existing_prod["id"])
                    target.name_pl = existing_prod["name_pl"]
                    target.name_en = existing_prod["name_en"]
                    target.clean_name = (
                        existing_prod["name_pl"] if lang == "pl" else existing_prod["name_en"]
                    )
                    if explicit_subcat is None and existing_prod.get("subcategory_code"):
                        target.subcategory = existing_prod["subcategory_code"]
                        target.category = existing_prod.get("category_code")
                else:
                    base_name = new_clean or new_pl or new_en
                    if not base_name:
                        raise ValueError("Clean product name cannot be empty.")
                    target.product_id = None
                    target.name_pl = new_pl or base_name
                    target.name_en = new_en or base_name
                    target.clean_name = target.name_pl if lang == "pl" else target.name_en

            if classification_edited:
                target.match_source = "user"
                target.alias_id = None
    else:
        assignments = parse_edit_assignments(spec)
        if not assignments:
            raise ValueError(
                f"Could not parse edit command. Examples:\n"
                f"• /edit {job_id} 1 name=jajka price=9.99 subcat=eggs\n"
                f"• /edit {job_id} 2 delete\n"
                f"• /edit {job_id} store=Biedronka date=2026-10-28 total=54.30"
            )

        if "store" in assignments or "store_name" in assignments:
            raw_store = (assignments.get("store_name") or assignments.get("store") or "").strip()
            if not raw_store:
                raise ValueError("Store name cannot be empty.")
            resolved = catalog_repo.resolve_store(
                raw_store, auto_create=False, database_path=database_path
            )
            if resolved is not None:
                result.store_id = int(resolved["id"])
                result.store_name = resolved["display_name"]
            else:
                result.store_id = None
                result.store_name = normalize_store_name(raw_store)

        if "date" in assignments or "transaction_date" in assignments:
            raw_date = (
                assignments.get("transaction_date") or assignments.get("date") or ""
            ).strip()
            if raw_date.lower() in ("none", "null", "-"):
                result.transaction_date = None
            else:
                # Re-validate ISO YYYY-MM-DD through ReceiptOCRResult validator
                temp_payload = result.model_dump(mode="json")
                temp_payload["transaction_date"] = raw_date
                try:
                    result = validate_ocr_result(temp_payload)
                except Exception as exc:
                    raise ValueError(
                        f"Invalid date '{raw_date}'. Use YYYY-MM-DD (e.g. 2026-10-28)."
                    ) from exc

        if "total" in assignments or "total_amount" in assignments:
            raw_total = (assignments.get("total_amount") or assignments.get("total") or "").strip()
            if raw_total.lower() in ("sum", "auto"):
                computed = round(sum(float(it.total_price) for it in result.items), 2)
                result.total_amount = max(0.0, computed)
            else:
                tot_val = _parse_decimal(raw_total, "total")
                if tot_val < 0:
                    raise ValueError("Receipt total_amount cannot be negative.")
                result.total_amount = tot_val

        if "currency" in assignments:
            curr = assignments["currency"].strip().upper()
            if not curr or len(curr) > 10:
                raise ValueError("Invalid currency code.")
            result.currency = curr

    validated_dict = validate_ocr_result(result.model_dump(mode="json")).model_dump(mode="json")
    jobs_repo.update_job_ocr(job_id, validated_dict, database_path=database_path)

    store_name = validated_dict.get("store_name") or ""
    txn_date = str(validated_dict.get("transaction_date") or "")
    total_amount = float(validated_dict.get("total_amount") or 0.0)
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

    updated = jobs_repo.get_job(job_id, tenant_id=tenant_id, database_path=database_path)
    assert updated is not None
    return updated


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
            subcategories=taxonomy_repo.get_active_subcategory_codes(database_path=database_path),
            default_currency=tenant.get("default_currency", "PLN"),
            language=tenant.get("language", "pl"),
            persist_catalog=False,
            database_path=database_path,
        )
    except Exception as exc:
        logger.error("[ocr_one_job] Job %s OCR failed: %s", job_id, exc)
        jobs_repo.set_job_status(
            job_id, jobs_repo.FAILED, str(exc), database_path=database_path
        )
        raise

    result_dict = result.model_dump(mode="json")
    if not result_dict.get("store_name"):
        result_dict["store_name"] = "Unknown Store"
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
    store_name = result.store_name or normalize_store_name(result.store_name)
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

    # Commit anonymized product & alias mappings into the shared catalog once upon confirmation
    if job.get("status") != jobs_repo.DELIVERY_FAILED:
        result = commit_result_to_catalog(result, source="llm", database_path=database_path)
        store_name = result.store_name or store_name
        jobs_repo.update_job_ocr(
            job_id, result.model_dump(mode="json"), database_path=database_path
        )

    raw_modes = tenant.get("delivery_modes")
    modes = list(raw_modes) if isinstance(raw_modes, list) else ["webhook"]

    if "webhook" in modes:
        try:
            delivery = dispatch_receipt_webhook(tenant=tenant, result=result, job_id=job_id)
        except RuntimeError as exc:
            jobs_repo.set_job_status(
                job_id, jobs_repo.DELIVERY_FAILED, str(exc), database_path=database_path
            )
            raise
    else:
        delivery = {"delivered": False, "status_code": None, "response": None}

    hub_receipt_id: int | None = None
    if "hub_db" in modes:
        saved_receipt = receipts_repo.save_confirmed_receipt(
            tenant_id=tenant_id,
            result=result,
            job_id=job_id,
            database_path=database_path,
        )
        hub_receipt_id = int(saved_receipt["id"])

    jobs_repo.mark_job_confirmed(
        job_id=job_id,
        webhook_delivered=delivery["delivered"],
        webhook_response_code=delivery["status_code"],
        database_path=database_path,
    )

    # Privacy guarantee: when hub_db is NOT enabled, remove local receipt photo and detailed line-item JSON
    if "hub_db" not in modes:
        _delete_image(job)
        jobs_repo.clear_job_payload(job_id, database_path=database_path)

    try:
        process_next_queued_job(tenant_id=tenant_id, database_path=database_path)
    except Exception:
        logger.exception("[confirm_job] Failed to advance queue after confirming job %s", job_id)

    return {
        "job_id": job_id,
        "hub_receipt_id": hub_receipt_id,
        "saved_to_hub_db": hub_receipt_id is not None,
        "delivery_modes": modes,
        "store_name": store_name,
        "transaction_date": txn_date,
        "total_amount": total_amount,
        "currency": result.currency,
        "items_count": len(result.items),
        "webhook_delivered": delivery["delivered"],
        "webhook_status_code": delivery["status_code"],
        "webhook_response": delivery["response"],
        "result": result.model_dump(mode="json"),
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
