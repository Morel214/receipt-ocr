"""FastAPI application for Receipt OCR Hub.

Combines:
1. Public/Friend OCR & Classification API (/api/v1/ocr/parse)
2. Self-service user configuration & webhook testing (/api/v1/me/*)
3. Queue management endpoints (/api/v1/jobs/*)
4. Multi-Bot Admin provisioning API (/api/v1/admin/tenants)
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status

from ocr_hub import config
from ocr_hub.api.auth import get_current_tenant, verify_admin_key
from ocr_hub.bot.bot_manager import bot_manager
from ocr_hub.db.models import TenantCreateRequest, TenantUpdateConfigRequest
from ocr_hub.db.schema import init_db
from ocr_hub.repositories import jobs_repo, tenants_repo
from ocr_hub.services import ocr_engine, queue_service, webhook_dispatcher

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


def _serialize_tenant(tenant: dict[str, Any], include_secrets: bool = True) -> dict[str, Any]:
    """Format a tenant record for API responses."""
    data = {
        "id": tenant["id"],
        "name": tenant["name"],
        "webhook_url": tenant.get("webhook_url"),
        "has_webhook_secret": bool(tenant.get("webhook_secret")),
        "default_currency": tenant.get("default_currency", "PLN"),
        "language": tenant.get("language", "pl"),
        "subcategories": tenant.get("subcategories") or config.DEFAULT_SUBCATEGORIES,
        "ocr_provider": tenant.get("ocr_provider") or config.OCR_PROVIDER,
        "ocr_model": tenant.get("ocr_model") or config.OCR_MODEL,
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
    title="Receipt OCR Hub API",
    description=(
        "Multi-tenant Receipt OCR & Product Classification Gateway with dynamic "
        "Telegram Multi-Bot Manager and Webhook delivery."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Service health and active bot count check."""
    return {
        "status": "ok",
        "service": "receipt-ocr-hub",
        "active_telegram_bots": len(bot_manager.running_tenant_ids()),
        "default_provider": config.OCR_PROVIDER,
        "default_model": config.OCR_MODEL,
    }


@app.post("/api/v1/ocr/parse", tags=["OCR"])
async def parse_receipt_endpoint(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    currency: str | None = Form(default=None),
    language: str | None = Form(default=None),
    subcategories: str | None = Form(default=None),
    forward_to_webhook: bool = Form(default=False),
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Upload a receipt image, run Cloud OCR + item classification, and return structured JSON.

    Can be shared with friends using their personal ``API_KEY``. Optionally forwards
    the parsed receipt to the user's configured ``webhook_url``.
    """
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
        else tenant.get("subcategories")
    )

    try:
        ocr_result = await asyncio.to_thread(
            ocr_engine.analyze_receipt_image,
            content=content,
            content_type=content_type,
            provider=provider or tenant.get("ocr_provider"),
            model=model or tenant.get("ocr_model"),
            subcategories=custom_subcats,
            default_currency=currency or tenant.get("default_currency", "PLN"),
            language=language or tenant.get("language", "pl"),
        )
    except Exception as exc:
        logger.exception("[parse_receipt_endpoint] OCR failed for tenant %s", tenant["name"])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OCR processing failed: {exc}",
        ) from exc

    response_data = ocr_result.model_dump(mode="json")

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


@app.get("/api/v1/me", tags=["User Self-Service"])
async def get_my_profile(
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return the authenticated user's profile, webhook settings, and bot status."""
    return _serialize_tenant(tenant, include_secrets=True)


@app.put("/api/v1/me/config", tags=["User Self-Service"])
async def update_my_config(
    payload: TenantUpdateConfigRequest,
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Update the authenticated user's destination webhook, categories, model, or bot token."""
    update_fields = payload.model_dump(exclude_unset=True)
    updated = tenants_repo.update_tenant(tenant["id"], **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if "telegram_bot_token" in update_fields or "is_active" in update_fields:
        await bot_manager.start_bot_for_tenant(updated)

    return _serialize_tenant(updated, include_secrets=True)


@app.post("/api/v1/me/test-webhook", tags=["User Self-Service"])
async def test_my_webhook(
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Send a test payload to the authenticated user's configured webhook URL."""
    return await asyncio.to_thread(webhook_dispatcher.send_test_webhook, tenant)


@app.get("/api/v1/jobs", tags=["Receipt Jobs"])
async def list_my_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List receipt jobs belonging to the authenticated user."""
    return jobs_repo.list_jobs(tenant_id=tenant["id"], status=job_status)


@app.post("/api/v1/jobs/{job_id}/confirm", tags=["Receipt Jobs"])
async def confirm_my_job(
    job_id: int,
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Confirm a pending receipt job and push its JSON to the configured webhook."""
    try:
        return await asyncio.to_thread(queue_service.confirm_job, tenant["id"], job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/jobs/{job_id}/reject", tags=["Receipt Jobs"])
async def reject_my_job(
    job_id: int,
    tenant: dict[str, Any] = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Reject and delete a receipt job."""
    ok = await asyncio.to_thread(queue_service.reject_job, tenant["id"], job_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    return {"job_id": job_id, "status": "rejected"}


# ==============================================================================
# Admin Endpoints (Protected by ADMIN_API_KEY)
# ==============================================================================


@app.post(
    "/api/v1/admin/tenants",
    dependencies=[Depends(verify_admin_key)],
    status_code=status.HTTP_201_CREATED,
    tags=["Admin (Multi-Bot Management)"],
)
async def admin_create_tenant(payload: TenantCreateRequest) -> dict[str, Any]:
    """Register a new user/friend, generate their API key, and start their Telegram bot."""
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
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant name or Telegram bot token already registered: {exc}",
        ) from exc

    if tenant.get("telegram_bot_token"):
        await bot_manager.start_bot_for_tenant(tenant)

    return _serialize_tenant(tenant, include_secrets=True)


@app.get(
    "/api/v1/admin/tenants",
    dependencies=[Depends(verify_admin_key)],
    tags=["Admin (Multi-Bot Management)"],
)
async def admin_list_tenants() -> list[dict[str, Any]]:
    """List all registered tenants and their Telegram bot status."""
    tenants = tenants_repo.list_tenants()
    return [_serialize_tenant(t, include_secrets=True) for t in tenants]


@app.patch(
    "/api/v1/admin/tenants/{tenant_id}",
    dependencies=[Depends(verify_admin_key)],
    tags=["Admin (Multi-Bot Management)"],
)
async def admin_update_tenant(
    tenant_id: int,
    payload: TenantUpdateConfigRequest,
) -> dict[str, Any]:
    """Update a tenant's configuration or Telegram bot token and hot-reload their bot."""
    update_fields = payload.model_dump(exclude_unset=True)
    updated = tenants_repo.update_tenant(tenant_id, **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await bot_manager.start_bot_for_tenant(updated)
    return _serialize_tenant(updated, include_secrets=True)


@app.delete(
    "/api/v1/admin/tenants/{tenant_id}",
    dependencies=[Depends(verify_admin_key)],
    tags=["Admin (Multi-Bot Management)"],
)
async def admin_delete_tenant(tenant_id: int) -> dict[str, Any]:
    """Stop a tenant's Telegram bot and remove the tenant from the database."""
    await bot_manager.stop_bot_for_tenant(tenant_id)
    deleted = tenants_repo.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenant_id": tenant_id, "deleted": True}
