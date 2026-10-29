"""FastAPI application for Receipt OCR Hub.

Provides:
1. Built-in Web UI Dashboard (GET /) for adding Telegram bots, setting destination webhooks, and choosing OCR/Classifier models.
2. Simple OCR API endpoint (POST /api/ocr and POST /api/v1/ocr/parse) running the 2-stage pipeline (Vision OCR -> Text Classifier).
3. Bot & Webhook management endpoints (/api/bots/*).
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse

from ocr_hub import config
from ocr_hub.api.auth import (
    check_optional_admin_key,
    get_current_tenant,
    require_strict_admin_key,
    verify_admin_key,
)
from ocr_hub.api.web_ui import render_dashboard_html
from ocr_hub.bot.bot_manager import bot_manager
from ocr_hub.db.migrations import list_applied_migrations
from ocr_hub.db.models import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    SubcategoryCreateRequest,
    SubcategoryUpdateRequest,
    TenantCreateRequest,
    TenantUpdateConfigRequest,
)
from ocr_hub.db.schema import init_db
from ocr_hub.repositories import catalog_repo, jobs_repo, taxonomy_repo, tenants_repo
from ocr_hub.services import ocr_engine, queue_service, webhook_dispatcher

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


def _serialize_tenant(tenant: dict[str, Any], include_secrets: bool = True) -> dict[str, Any]:
    """Format a tenant record for API & Web UI responses."""
    data = {
        "id": tenant["id"],
        "name": tenant["name"],
        "webhook_url": tenant.get("webhook_url"),
        "has_webhook_secret": bool(tenant.get("webhook_secret")),
        "default_currency": tenant.get("default_currency", "PLN"),
        "language": tenant.get("language", "pl"),
        "subcategories": taxonomy_repo.get_active_subcategory_codes(),
        "ocr_provider": tenant.get("ocr_provider") or config.OCR_PROVIDER,
        "ocr_model": tenant.get("ocr_model") or config.OCR_MODEL,
        "classifier_provider": tenant.get("classifier_provider") or config.CLASSIFIER_PROVIDER,
        "classifier_model": tenant.get("classifier_model") or config.CLASSIFIER_MODEL,
        "raw_ocr_provider": tenant.get("ocr_provider"),
        "raw_ocr_model": tenant.get("ocr_model"),
        "raw_classifier_provider": tenant.get("classifier_provider"),
        "raw_classifier_model": tenant.get("classifier_model"),
        "allowed_chat_ids": tenant.get("allowed_chat_ids_list", []),
        "has_telegram_bot": bool(tenant.get("telegram_bot_token")),
        "bot_running": bot_manager.is_running(int(tenant["id"])),
        "is_active": bool(tenant.get("is_active", True)),
        "created_at": tenant.get("created_at"),
    }
    if include_secrets:
        data["api_key"] = tenant["api_key"]
    return data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize SQLite schema, bootstrap default tenant, and start all Telegram bots."""
    init_db()
    config.ensure_directories()
    tenants_repo.bootstrap_default_tenant()
    await bot_manager.start_all_from_db()
    try:
        yield
    finally:
        await bot_manager.stop_all()


app = FastAPI(
    title="Receipt OCR Hub",
    description=(
        "Two-Stage Receipt OCR & Product Classification Gateway with Web Dashboard "
        "and Telegram Multi-Bot Manager."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def web_dashboard() -> HTMLResponse:
    """Serve the built-in English Web UI Dashboard."""
    return HTMLResponse(content=render_dashboard_html())


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Service health and active bot count check."""
    return {
        "status": "ok",
        "service": "receipt-ocr-hub",
        "active_telegram_bots": len(bot_manager.running_tenant_ids()),
        "schema_version": (list_applied_migrations() or [{"version": 0}])[-1]["version"],
        "default_ocr_provider": config.OCR_PROVIDER,
        "default_ocr_model": config.OCR_MODEL,
        "default_classifier_provider": config.CLASSIFIER_PROVIDER,
        "default_classifier_model": config.CLASSIFIER_MODEL,
    }


async def _handle_ocr_parse(
    file: UploadFile,
    provider: str | None,
    model: str | None,
    classifier_provider: str | None,
    classifier_model: str | None,
    currency: str | None,
    language: str | None,
    subcategories: str | None,
    forward_to_webhook: bool,
    tenant: dict[str, Any],
) -> dict[str, Any]:
    """Shared implementation for /api/ocr and /api/v1/ocr/parse."""
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, or WEBP images are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    custom_subcats = (
        [s.strip() for s in subcategories.split(",") if s.strip()]
        if subcategories
        else taxonomy_repo.get_active_subcategory_codes()
    )

    try:
        ocr_result = await asyncio.to_thread(
            ocr_engine.analyze_receipt_image,
            content=content,
            content_type=content_type,
            provider=provider or tenant.get("ocr_provider"),
            model=model or tenant.get("ocr_model"),
            classifier_provider=classifier_provider or tenant.get("classifier_provider"),
            classifier_model=classifier_model or tenant.get("classifier_model"),
            subcategories=custom_subcats,
            default_currency=currency or tenant.get("default_currency", "EUR"),
            language=language or tenant.get("language", "en"),
        )
    except Exception as exc:
        logger.exception("[_handle_ocr_parse] OCR failed for tenant %s", tenant["name"])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OCR processing failed: {exc}",
        ) from exc

    response_data = {
        "store_name": ocr_result.store_name,
        "transaction_date": str(ocr_result.transaction_date) if ocr_result.transaction_date else None,
        "total_amount": float(ocr_result.total_amount),
        "currency": ocr_result.currency,
        "items": [
            {
                "name": item.name,
                "clean_name": item.clean_name,
                "subcategory": item.subcategory,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
            for item in ocr_result.items
        ],
    }

    if forward_to_webhook and tenant.get("webhook_url"):
        try:
            delivery = await asyncio.to_thread(
                webhook_dispatcher.dispatch_receipt_webhook,
                tenant=tenant,
                result=ocr_result,
                job_id=None,
            )
            response_data["webhook_delivery"] = delivery
        except RuntimeError as exc:
            response_data["webhook_delivery"] = {"delivered": False, "error": str(exc)}

    return response_data


@app.post("/api/ocr", tags=["OCR"])
async def parse_receipt_simple(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    classifier_provider: str | None = Form(default=None),
    classifier_model: str | None = Form(default=None),
    currency: str | None = Form(default=None),
    language: str | None = Form(default=None),
    subcategories: str | None = Form(default=None),
    forward_to_webhook: bool = Form(default=False),
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Primary simplified OCR endpoint: upload receipt image -> Stage 1 OCR -> Stage 2 Classifier -> JSON."""
    return await _handle_ocr_parse(
        file=file,
        provider=provider,
        model=model,
        classifier_provider=classifier_provider,
        classifier_model=classifier_model,
        currency=currency,
        language=language,
        subcategories=subcategories,
        forward_to_webhook=forward_to_webhook,
        tenant=tenant,
    )


@app.post("/api/v1/ocr/parse", tags=["OCR"], include_in_schema=False)
async def parse_receipt_v1_alias(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    classifier_provider: str | None = Form(default=None),
    classifier_model: str | None = Form(default=None),
    currency: str | None = Form(default=None),
    language: str | None = Form(default=None),
    subcategories: str | None = Form(default=None),
    forward_to_webhook: bool = Form(default=False),
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Backward-compatible alias for /api/ocr."""
    return await _handle_ocr_parse(
        file=file,
        provider=provider,
        model=model,
        classifier_provider=classifier_provider,
        classifier_model=classifier_model,
        currency=currency,
        language=language,
        subcategories=subcategories,
        forward_to_webhook=forward_to_webhook,
        tenant=tenant,
    )


# ==============================================================================
# Bot & User Management Endpoints (Used by Web UI Dashboard & Admin API)
# ==============================================================================


@app.get(
    "/api/bots",
    dependencies=[Depends(verify_admin_key)],
    tags=["Bots & Webhooks"],
)
@app.get(
    "/api/v1/admin/tenants",
    dependencies=[Depends(verify_admin_key)],
    include_in_schema=False,
)
async def list_bots() -> list[dict[str, Any]]:
    """List all registered bots/users and their live status."""
    tenants = tenants_repo.list_tenants()
    return [_serialize_tenant(t, include_secrets=True) for t in tenants]


@app.post(
    "/api/bots",
    dependencies=[Depends(verify_admin_key)],
    status_code=status.HTTP_201_CREATED,
    tags=["Bots & Webhooks"],
)
@app.post(
    "/api/v1/admin/tenants",
    dependencies=[Depends(verify_admin_key)],
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_bot(payload: TenantCreateRequest) -> dict[str, Any]:
    """Register a new user/bot, generate their API key, and start their Telegram bot."""
    try:
        tenant = tenants_repo.create_tenant(
            name=payload.name,
            telegram_bot_token=payload.telegram_bot_token,
            allowed_chat_ids=payload.allowed_chat_ids,
            webhook_url=payload.webhook_url,
            webhook_secret=payload.webhook_secret,
            default_currency=payload.default_currency,
            language=payload.language,
            subcategories=payload.subcategories,
            ocr_provider=payload.ocr_provider,
            ocr_model=payload.ocr_model,
            classifier_provider=payload.classifier_provider,
            classifier_model=payload.classifier_model,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bot/user name or Telegram bot token already exists: {exc}",
        ) from exc

    if tenant.get("telegram_bot_token"):
        await bot_manager.start_bot_for_tenant(tenant)

    return _serialize_tenant(tenant, include_secrets=True)


@app.put(
    "/api/bots/{bot_id}",
    dependencies=[Depends(verify_admin_key)],
    tags=["Bots & Webhooks"],
)
@app.patch(
    "/api/v1/admin/tenants/{bot_id}",
    dependencies=[Depends(verify_admin_key)],
    include_in_schema=False,
)
async def update_bot(
    bot_id: int,
    payload: TenantUpdateConfigRequest,
) -> dict[str, Any]:
    """Update a bot's destination webhook, models, or Telegram token and hot-reload the bot."""
    update_fields = payload.model_dump(exclude_unset=True)
    updated = tenants_repo.update_tenant(bot_id, **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Bot/user not found")

    await bot_manager.start_bot_for_tenant(updated)
    return _serialize_tenant(updated, include_secrets=True)


@app.delete(
    "/api/bots/{bot_id}",
    dependencies=[Depends(verify_admin_key)],
    tags=["Bots & Webhooks"],
)
@app.delete(
    "/api/v1/admin/tenants/{bot_id}",
    dependencies=[Depends(verify_admin_key)],
    include_in_schema=False,
)
async def delete_bot(bot_id: int) -> dict[str, Any]:
    """Stop a Telegram bot and remove its configuration from the database."""
    await bot_manager.stop_bot_for_tenant(bot_id)
    deleted = tenants_repo.delete_tenant(bot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bot/user not found")
    return {"bot_id": bot_id, "deleted": True}


@app.post(
    "/api/bots/{bot_id}/test-webhook",
    dependencies=[Depends(verify_admin_key)],
    tags=["Bots & Webhooks"],
)
async def test_bot_webhook(bot_id: int) -> dict[str, Any]:
    """Send a test payload to the specified bot's destination webhook URL."""
    tenant = tenants_repo.get_tenant_by_id(bot_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Bot/user not found")
    return await asyncio.to_thread(webhook_dispatcher.send_test_webhook, tenant)


# ==============================================================================
# Self-Service & Queue Endpoints (Authenticated by Tenant API Key)
# ==============================================================================


@app.get("/api/v1/me", tags=["User Self-Service"], include_in_schema=False)
async def get_my_profile(
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return the authenticated user's profile and settings."""
    return _serialize_tenant(tenant, include_secrets=True)


@app.put("/api/v1/me/config", tags=["User Self-Service"], include_in_schema=False)
async def update_my_config(
    payload: TenantUpdateConfigRequest,
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Update the authenticated user's configuration via their API key."""
    update_fields = payload.model_dump(exclude_unset=True)
    updated = tenants_repo.update_tenant(tenant["id"], **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if "telegram_bot_token" in update_fields or "is_active" in update_fields:
        await bot_manager.start_bot_for_tenant(updated)

    return _serialize_tenant(updated, include_secrets=True)


@app.get("/api/jobs", tags=["Receipt Jobs"])
@app.get("/api/v1/jobs", include_in_schema=False)
async def list_my_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List receipt jobs belonging to the authenticated user."""
    return jobs_repo.list_jobs(tenant_id=tenant["id"], status=job_status)


# ==============================================================================
# Admin Status & Global Taxonomy Endpoints (Categories & Subcategories in PL/EN)
# ==============================================================================


@app.get("/api/admin/status", tags=["Health"])
async def admin_auth_status(
    is_admin: bool = Depends(check_optional_admin_key),
) -> dict[str, Any]:
    """Return whether ADMIN_API_KEY is configured and whether the caller holds a valid Admin Key."""
    return {
        "admin_key_configured": bool(config.ADMIN_API_KEY),
        "is_admin": is_admin,
    }


@app.get("/api/taxonomy", tags=["Taxonomy"])
async def get_taxonomy(
    include_inactive: bool = Query(default=False),
    is_admin: bool = Depends(check_optional_admin_key),
) -> dict[str, Any]:
    """Return the shared global category and subcategory tree (PL & EN).

    Non-admin callers only receive active, confirmed taxonomy entries.
    """
    show_all = bool(include_inactive and is_admin)
    return {
        "categories": taxonomy_repo.get_taxonomy_tree(only_active=not show_all),
        "active_subcategory_codes": taxonomy_repo.get_active_subcategory_codes(),
        "is_admin": is_admin,
    }


@app.get(
    "/api/taxonomy/pending",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def list_pending_taxonomy_suggestions() -> dict[str, Any]:
    """Return manual_user category and subcategory suggestions awaiting Admin approval."""
    return taxonomy_repo.list_pending_taxonomy()


@app.post(
    "/api/taxonomy/categories",
    status_code=status.HTTP_201_CREATED,
    tags=["Taxonomy"],
)
async def create_taxonomy_category(
    payload: CategoryCreateRequest,
    is_admin: bool = Depends(check_optional_admin_key),
) -> dict[str, Any]:
    """Create a category (confirmed immediately for Admin; queued as pending manual_user otherwise)."""
    try:
        return taxonomy_repo.create_category(
            code=payload.code,
            name_pl=payload.name_pl,
            name_en=payload.name_en,
            sort_order=payload.sort_order,
            is_active=payload.is_active if is_admin else False,
            status="confirmed" if is_admin else "pending",
            source="admin" if is_admin else "manual_user",
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post(
    "/api/taxonomy/categories/{category_id}/approve",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def approve_taxonomy_category(category_id: int) -> dict[str, Any]:
    """Approve a pending manual_user category so it enters the active taxonomy."""
    approved = taxonomy_repo.approve_category(category_id)
    if approved is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return approved


@app.put(
    "/api/taxonomy/categories/{category_id}",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def update_taxonomy_category(
    category_id: int,
    payload: CategoryUpdateRequest,
) -> dict[str, Any]:
    """Update a category's code, PL/EN names, sort order, or active flag (Admin Key required)."""
    try:
        updated = taxonomy_repo.update_category(
            category_id, **payload.model_dump(exclude_unset=True)
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return updated


@app.delete(
    "/api/taxonomy/categories/{category_id}",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def delete_taxonomy_category(category_id: int) -> dict[str, Any]:
    """Delete a category (and its cascaded subcategories) from the global taxonomy (Admin Key required)."""
    deleted = taxonomy_repo.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"category_id": category_id, "deleted": True}


@app.post(
    "/api/taxonomy/subcategories",
    status_code=status.HTTP_201_CREATED,
    tags=["Taxonomy"],
)
async def create_taxonomy_subcategory(
    payload: SubcategoryCreateRequest,
    is_admin: bool = Depends(check_optional_admin_key),
) -> dict[str, Any]:
    """Create a subcategory (confirmed immediately for Admin; queued as pending manual_user otherwise)."""
    parent = taxonomy_repo.get_category_by_id(payload.category_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent category not found")
    try:
        return taxonomy_repo.create_subcategory(
            category_id=payload.category_id,
            code=payload.code,
            name_pl=payload.name_pl,
            name_en=payload.name_en,
            sort_order=payload.sort_order,
            is_active=payload.is_active if is_admin else False,
            status="confirmed" if is_admin else "pending",
            source="admin" if is_admin else "manual_user",
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.post(
    "/api/taxonomy/subcategories/{subcategory_id}/approve",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def approve_taxonomy_subcategory(subcategory_id: int) -> dict[str, Any]:
    """Approve a pending manual_user subcategory so it enters the active taxonomy."""
    approved = taxonomy_repo.approve_subcategory(subcategory_id)
    if approved is None:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return approved


@app.put(
    "/api/taxonomy/subcategories/{subcategory_id}",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def update_taxonomy_subcategory(
    subcategory_id: int,
    payload: SubcategoryUpdateRequest,
) -> dict[str, Any]:
    """Update a subcategory's parent category, code, PL/EN names, sort order, or active flag (Admin Key required)."""
    try:
        updated = taxonomy_repo.update_subcategory(
            subcategory_id, **payload.model_dump(exclude_unset=True)
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return updated


@app.delete(
    "/api/taxonomy/subcategories/{subcategory_id}",
    dependencies=[Depends(require_strict_admin_key)],
    tags=["Taxonomy"],
)
async def delete_taxonomy_subcategory(subcategory_id: int) -> dict[str, Any]:
    """Delete a subcategory from the global taxonomy (Admin Key required)."""
    deleted = taxonomy_repo.delete_subcategory(subcategory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return {"subcategory_id": subcategory_id, "deleted": True}


@app.get("/api/catalog/stats", tags=["Catalog"])
async def get_catalog_overview() -> dict[str, Any]:
    """Return summary counts for the shared product catalog, aliases, stores, and pending suggestions."""
    return catalog_repo.get_catalog_stats()
