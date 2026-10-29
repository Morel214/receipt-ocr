"""Integration tests for Web Dashboard, simplified API endpoints, and Telegram photo bot."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ocr_hub.bot import handlers
from ocr_hub.db.models import ReceiptItem, ReceiptOCRResult


def test_web_dashboard_and_simplified_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Web Dashboard renders at GET /
    home_resp = client.get("/")
    assert home_resp.status_code == 200
    assert "Receipt OCR Hub" in home_resp.text

    # 2. Create a bot/user via POST /api/bots
    resp = client.post(
        "/api/bots",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={
            "name": "Alex",
            "webhook_url": "https://alex-homelab.local/api/receipts",
            "webhook_secret": "alex-token",
            "default_currency": "EUR",
            "ocr_provider": "gemini",
            "ocr_model": "gemini-2.5-flash",
            "classifier_provider": "deepseek",
            "classifier_model": "deepseek-chat",
        },
    )
    assert resp.status_code == 201
    bot_data = resp.json()
    api_key = bot_data["api_key"]
    assert api_key.startswith("ocr_live_")
    assert bot_data["ocr_model"] == "gemini-2.5-flash"
    assert bot_data["classifier_model"] == "deepseek-chat"

    # 3. Parse a receipt using the simplified POST /api/ocr endpoint
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
                    clean_name="chicken breast",
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
        "/api/ocr",
        headers={"X-API-Key": api_key},
        files={"file": ("receipt.jpg", b"fake-jpeg-data", "image/jpeg")},
    )
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed == {
        "store_name": "Jumbo",
        "transaction_date": "2026-10-22",
        "total_amount": 14.20,
        "currency": "EUR",
        "cache_hits": 0,
        "llm_classified_count": 0,
        "items": [
            {
                "name": "JUMBO KIPFILET",
                "clean_name": "chicken breast",
                "category": None,
                "subcategory": "meat",
                "unit": "pcs",
                "quantity": 1.0,
                "unit_price": 14.20,
                "total_price": 14.20,
                "product_id": None,
                "brand": None,
                "off_search_query": None,
                "match_source": "llm",
            }
        ],
    }


def test_telegram_bot_has_only_photo_and_queue_commands(temp_db) -> None:
    from ocr_hub.repositories import tenants_repo

    tenant = tenants_repo.create_tenant(name="PhotoBotUser")

    update = MagicMock()
    update.effective_chat.id = 555111
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.application.bot_data = {"tenant_id": tenant["id"]}

    asyncio.run(handlers.cmd_help(update, context))
    help_reply = update.message.reply_text.call_args[0][0]
    assert "/confirm" in help_reply
    assert "/reject" in help_reply
    assert "/set_webhook" not in help_reply
    assert "/set_model" not in help_reply
