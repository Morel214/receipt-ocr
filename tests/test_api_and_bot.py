"""Integration tests for FastAPI endpoints and Telegram bot commands."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ocr_hub.bot import handlers
from ocr_hub.db.models import ReceiptItem, ReceiptOCRResult


def test_admin_create_tenant_and_parse_receipt_via_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Admin creates a new friend tenant
    resp = client.post(
        "/api/v1/admin/tenants",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={
            "name": "Kamil",
            "webhook_url": "https://kamil-homelab.local/api/receipts",
            "webhook_secret": "kamil-token",
            "default_currency": "EUR",
        },
    )
    assert resp.status_code == 201
    tenant_data = resp.json()
    api_key = tenant_data["api_key"]
    assert api_key.startswith("ocr_live_")
    assert tenant_data["name"] == "Kamil"

    # 2. Friend checks their profile with their personal API key
    me_resp = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["webhook_url"] == "https://kamil-homelab.local/api/receipts"

    # 3. Friend updates their subcategories and model via self-service API
    cfg_resp = client.put(
        "/api/v1/me/config",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "subcategories": ["dairy", "meat", "snacks"],
            "ocr_provider": "gemini",
            "ocr_model": "gemini-2.5-flash",
        },
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["subcategories"] == ["dairy", "meat", "snacks"]
    assert cfg_resp.json()["ocr_model"] == "gemini-2.5-flash"

    # 4. Friend sends a receipt image to /api/v1/ocr/parse
    monkeypatch.setattr(
        "ocr_hub.services.ocr_engine.analyze_receipt_image",
        lambda **kwargs: ReceiptOCRResult(
            store_name="Jumbo",
            transaction_date="2026-10-22",
            total_amount=14.20,
            currency="EUR",
            confidence=0.97,
            items=[
                ReceiptItem(
                    name="JUMBO KIPFILET",
                    clean_name="filet z kurczaka",
                    category="FOOD",
                    subcategory="meat",
                    quantity=1.0,
                    unit_price=14.20,
                    total_price=14.20,
                    confidence=0.97,
                )
            ],
        ),
    )

    parse_resp = client.post(
        "/api/v1/ocr/parse",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("paragon.jpg", b"fake-jpeg-data", "image/jpeg")},
    )
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["store_name"] == "Jumbo"
    assert parsed["total_amount"] == 14.20
    assert parsed["items"][0]["clean_name"] == "filet z kurczaka"
    assert parsed["items"][0]["subcategory"] == "meat"


def test_telegram_set_webhook_and_set_model_commands(temp_db) -> None:
    import asyncio
    from ocr_hub.repositories import tenants_repo

    tenant = tenants_repo.create_tenant(name="TelegramUser")

    update = MagicMock()
    update.effective_chat.id = 555111
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.application.bot_data = {"tenant_id": tenant["id"]}

    # /set_webhook
    context.args = ["https://moja-baza.pl/api/webhook", "moj-sekret-123"]
    asyncio.run(handlers.cmd_set_webhook(update, context))

    updated = tenants_repo.get_tenant_by_id(tenant["id"])
    assert updated is not None
    assert updated["webhook_url"] == "https://moja-baza.pl/api/webhook"
    assert updated["webhook_secret"] == "moj-sekret-123"

    # /set_model
    context.args = ["gemini", "gemini-2.5-flash"]
    asyncio.run(handlers.cmd_set_model(update, context))

    updated = tenants_repo.get_tenant_by_id(tenant["id"])
    assert updated is not None
    assert updated["ocr_provider"] == "gemini"
    assert updated["ocr_model"] == "gemini-2.5-flash"
