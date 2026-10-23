"""Webhook delivery service for pushing final OCR JSON results to a user's destination URL."""

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from ocr_hub.db.models import ReceiptOCRResult, WebhookDeliveryPayload

logger = logging.getLogger(__name__)


def build_webhook_payload(
    tenant: dict[str, Any],
    result: ReceiptOCRResult,
    job_id: int | None = None,
) -> dict[str, Any]:
    """Build a standardized JSON payload for webhook delivery."""
    receipt_dict = result.model_dump(mode="json")
    txn_date = str(result.transaction_date) if result.transaction_date else None
    payload = WebhookDeliveryPayload(
        event="receipt.confirmed",
        job_id=job_id,
        tenant_name=tenant["name"],
        confirmed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        store_name=result.store_name,
        transaction_date=txn_date,
        total_amount=float(result.total_amount),
        currency=result.currency or tenant.get("default_currency", "EUR"),
        confidence=result.confidence,
        items=receipt_dict.get("items", []),
        receipt=receipt_dict,
    )
    return payload.model_dump(mode="json")


def dispatch_receipt_webhook(
    tenant: dict[str, Any],
    result: ReceiptOCRResult,
    job_id: int | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """POST the parsed receipt JSON to the tenant's configured ``webhook_url``."""
    webhook_url = (tenant.get("webhook_url") or "").strip()
    if not webhook_url:
        logger.info(
            "[dispatch_receipt_webhook] Tenant '%s' has no webhook_url configured; skipping push.",
            tenant["name"],
        )
        return {"delivered": False, "status_code": None, "response": None}

    payload = build_webhook_payload(tenant=tenant, result=result, job_id=job_id)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-OCR-Hub-Event": "receipt.confirmed",
        "X-OCR-Hub-Tenant": str(tenant["name"]),
    }
    secret = (tenant.get("webhook_secret") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    logger.info(
        "[dispatch_receipt_webhook] POST %s for tenant=%s job=%s",
        webhook_url,
        tenant["name"],
        job_id,
    )
    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        try:
            body = response.json()
        except Exception:
            body = response.text[:500]
        return {
            "delivered": True,
            "status_code": response.status_code,
            "response": body,
        }
    except requests.RequestException as exc:
        logger.error(
            "[dispatch_receipt_webhook] Delivery to %s failed for tenant %s: %s",
            webhook_url,
            tenant["name"],
            exc,
        )
        raise RuntimeError(f"Webhook delivery to {webhook_url} failed: {exc}") from exc


def send_test_webhook(
    tenant: dict[str, Any],
    timeout: int = 15,
) -> dict[str, Any]:
    """Send a diagnostic test ping to the tenant's configured webhook URL."""
    webhook_url = (tenant.get("webhook_url") or "").strip()
    if not webhook_url:
        return {
            "ok": False,
            "status_code": None,
            "detail": "No webhook_url configured for this bot.",
        }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-OCR-Hub-Event": "webhook.test",
        "X-OCR-Hub-Tenant": str(tenant["name"]),
    }
    secret = (tenant.get("webhook_secret") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    sample_payload = {
        "event": "webhook.test",
        "tenant_name": tenant["name"],
        "tested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "message": "Test connection from Receipt OCR Hub",
    }

    try:
        response = requests.post(webhook_url, json=sample_payload, headers=headers, timeout=timeout)
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "detail": response.text[:300],
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "detail": str(exc),
        }
