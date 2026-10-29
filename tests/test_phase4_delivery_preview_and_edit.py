"""Tests for Phase 4: 4 delivery_modes, opt-in Hub DB privacy, rich Telegram preview, /edit, inline buttons, and /export."""

import asyncio
import csv
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
import pytest

from ocr_hub.bot import handlers
from ocr_hub.db.models import ReceiptItem, ReceiptOCRResult
from ocr_hub.repositories import catalog_repo, jobs_repo, receipts_repo, tenants_repo
from ocr_hub.services import queue_service


def test_privacy_rule_opt_in_hub_db_and_rest_receipts_endpoints(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = {"X-Admin-Key": "test-admin-secret"}

    # 1. Friend opts ONLY into telegram_csv (NO hub_db!)
    friend_resp = client.post(
        "/api/bots",
        headers=admin_headers,
        json={
            "name": "FriendCsvOnly",
            "language": "pl",
            "default_currency": "PLN",
            "delivery_modes": ["telegram_csv"],
        },
    )
    assert friend_resp.status_code == 201
    friend = friend_resp.json()
    assert friend["delivery_modes"] == ["telegram_csv"]

    # 2. Domingo enables hub_db + telegram_text
    domingo_resp = client.post(
        "/api/bots",
        headers=admin_headers,
        json={
            "name": "DomingoHub",
            "language": "pl",
            "default_currency": "PLN",
            "delivery_modes": ["hub_db", "telegram_text"],
        },
    )
    assert domingo_resp.status_code == 201
    domingo = domingo_resp.json()
    assert domingo["delivery_modes"] == ["hub_db", "telegram_text"]

    # Friend scans & confirms a Biedronka receipt
    friend_img = tmp_path / "friend_r1.jpg"
    friend_img.write_bytes(b"friend-jpeg")
    friend_job_id = jobs_repo.create_job(
        tenant_id=friend["id"],
        batch_id="bf1",
        chat_id="101",
        message_id=1,
        filename="friend_r1.jpg",
        image_path=str(friend_img),
    )
    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: ReceiptOCRResult(
            store_name="Biedronka",
            transaction_date="2026-10-28",
            total_amount=8.99,
            currency="PLN",
            items=[
                ReceiptItem(
                    name="JAJA MOJA KURKA M 10",
                    clean_name="jajka",
                    name_pl="jajka",
                    name_en="eggs",
                    category="FOOD",
                    subcategory="eggs",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=8.99,
                    total_price=8.99,
                    brand="Moja Kurka",
                    off_search_query="Moja Kurka jaja M 10 szt",
                    match_source="llm",
                )
            ],
        ),
    )
    queue_service.process_batch(tenant_id=friend["id"], batch_id="bf1")
    friend_outcome = queue_service.confirm_job(tenant_id=friend["id"], job_id=friend_job_id)

    assert friend_outcome["saved_to_hub_db"] is False
    assert friend_outcome["hub_receipt_id"] is None

    # Shared catalog WAS enriched with the anonymized product & alias!
    biedronka = catalog_repo.resolve_store("Biedronka", auto_create=False)
    assert biedronka is not None
    cached_alias = catalog_repo.lookup_alias("JAJA MOJA KURKA M 10", store_id=biedronka["id"])
    assert cached_alias is not None
    assert cached_alias["name_pl"] == "jajka"

    # Privacy check: ZERO rows in receipts for Friend, local image deleted, and job items_json scrubbed!
    assert receipts_repo.list_receipts(tenant_id=friend["id"]) == []
    assert not friend_img.exists()
    scrubbed_job = jobs_repo.get_job(friend_job_id, tenant_id=friend["id"])
    assert scrubbed_job is not None
    assert scrubbed_job["ocr_json"] is None
    assert scrubbed_job["items_json"] is None

    friend_api_list = client.get(
        "/api/receipts", headers={"X-API-Key": friend["api_key"]}
    ).json()
    assert friend_api_list == {"receipts": [], "count": 0, "hub_db_enabled": False}

    # Domingo scans & confirms a Lidl receipt (with hub_db enabled)
    dom_img = tmp_path / "dom_r1.jpg"
    dom_img.write_bytes(b"dom-jpeg")
    dom_job_id = jobs_repo.create_job(
        tenant_id=domingo["id"],
        batch_id="bd1",
        chat_id="202",
        message_id=2,
        filename="dom_r1.jpg",
        image_path=str(dom_img),
    )
    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: ReceiptOCRResult(
            store_name="Lidl",
            transaction_date="2026-10-28",
            total_amount=12.99,
            currency="PLN",
            cache_hits=0,
            llm_classified_count=1,
            items=[
                ReceiptItem(
                    name="SER GOUDA 400G",
                    clean_name="ser żółty",
                    name_pl="ser żółty",
                    name_en="yellow cheese",
                    category="FOOD",
                    subcategory="dairy",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=12.99,
                    total_price=12.99,
                    match_source="llm",
                )
            ],
        ),
    )
    queue_service.process_batch(tenant_id=domingo["id"], batch_id="bd1")
    dom_outcome = queue_service.confirm_job(tenant_id=domingo["id"], job_id=dom_job_id)

    assert dom_outcome["saved_to_hub_db"] is True
    rec_id = dom_outcome["hub_receipt_id"]
    assert isinstance(rec_id, int)

    # Domingo retrieves receipt via GET /api/receipts, GET /api/receipts/{id}, and GET /api/receipts/export.csv
    list_resp = client.get(
        "/api/receipts?month=2026-10&include_items=true",
        headers={"X-API-Key": domingo["api_key"]},
    )
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["hub_db_enabled"] is True
    assert list_body["count"] == 1
    assert list_body["receipts"][0]["store_name"] == "Lidl"
    assert list_body["receipts"][0]["items"][0]["clean_name"] == "ser żółty"

    detail_resp = client.get(
        f"/api/receipts/{rec_id}",
        headers={"X-API-Key": domingo["api_key"]},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["total_amount"] == 12.99

    # Multi-tenant isolation: Friend cannot access Domingo's stored receipt
    forbidden_detail = client.get(
        f"/api/receipts/{rec_id}",
        headers={"X-API-Key": friend["api_key"]},
    )
    assert forbidden_detail.status_code == 404

    csv_resp = client.get(
        "/api/receipts/export.csv?month=2026-10",
        headers={"X-API-Key": domingo["api_key"]},
    )
    assert csv_resp.status_code == 200
    assert "SER GOUDA 400G" in csv_resp.text


def test_preview_sum_check_and_edit_command_marks_user_confirmed(
    temp_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = tenants_repo.create_tenant(
        name="EditTester",
        language="pl",
        default_currency="PLN",
        delivery_modes=["hub_db"],
        database_path=temp_db,
    )
    img = tmp_path / "edit.jpg"
    img.write_bytes(b"jpg")
    job_id = jobs_repo.create_job(
        tenant_id=tenant["id"],
        batch_id="be1",
        chat_id="303",
        message_id=1,
        filename="edit.jpg",
        image_path=str(img),
        database_path=temp_db,
    )

    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: ReceiptOCRResult(
            store_name="Biedronka",
            transaction_date="2026-10-29",
            total_amount=25.00,
            currency="PLN",
            items=[
                ReceiptItem(
                    name="SER GOUDA PL 400G",
                    clean_name="masło",
                    name_pl="masło",
                    name_en="butter",
                    category="FOOD",
                    subcategory="other",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=10.00,
                    total_price=10.00,
                    match_source="llm",
                ),
                ReceiptItem(
                    name="MLEKO 3.2% 1L",
                    clean_name="mleko 3.2%",
                    name_pl="mleko 3.2%",
                    name_en="milk 3.2%",
                    category="FOOD",
                    subcategory="dairy",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=4.50,
                    total_price=4.50,
                    match_source="llm",
                ),
                ReceiptItem(
                    name="SUMA PTU A 23%",
                    clean_name="inne",
                    name_pl="inne",
                    name_en="other",
                    category="OTHER",
                    subcategory="other",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=99.00,
                    total_price=99.00,
                    match_source="llm",
                ),
            ],
        ),
    )
    processed = queue_service.process_batch(
        tenant_id=tenant["id"], batch_id="be1", database_path=temp_db
    )
    initial_preview = handlers.render_job_preview(processed[0])
    assert "⚠️ Sum mismatch" in initial_preview
    assert "113.50 PLN" in initial_preview

    # 1. Delete garbage line #3 via /edit <id> 3 delete
    update_del = MagicMock()
    update_del.effective_chat.id = 303
    update_del.message.text = f"/edit {job_id} 3 delete"
    update_del.message.reply_text = AsyncMock()
    context = MagicMock()
    context.application.bot_data = {"tenant_id": tenant["id"]}
    context.args = [str(job_id), "3", "delete"]

    asyncio.run(handlers.cmd_edit(update_del, context))
    del_reply = update_del.message.reply_text.call_args[0][0]
    assert "SUMA PTU" not in del_reply

    # 2. Fix item #1 multi-word name, Polish comma price, and subcategory via /edit
    update_fix = MagicMock()
    update_fix.effective_chat.id = 303
    update_fix.message.text = f"/edit {job_id} 1 name=ser żółty gouda price=20,50 subcat=dairy"
    update_fix.message.reply_text = AsyncMock()
    context.args = [
        str(job_id),
        "1",
        "name=ser",
        "żółty",
        "gouda",
        "price=20,50",
        "subcat=dairy",
    ]

    asyncio.run(handlers.cmd_edit(update_fix, context))
    fix_reply = update_fix.message.reply_text.call_args[0][0]
    assert "✅ Sum check OK (25.00 PLN · 2 items)" in fix_reply
    assert "ser żółty gouda [dairy]" in fix_reply
    assert "✏️" in fix_reply

    # 3. Confirm job -> user-edited item must enter product_aliases as status='confirmed', source='user'
    outcome = queue_service.confirm_job(
        tenant_id=tenant["id"], job_id=job_id, database_path=temp_db
    )
    assert outcome["saved_to_hub_db"] is True
    biedronka = catalog_repo.resolve_store("Biedronka", auto_create=False, database_path=temp_db)
    assert biedronka is not None
    alias = catalog_repo.lookup_alias(
        "SER GOUDA PL 400G", store_id=biedronka["id"], database_path=temp_db
    )
    assert alias is not None
    assert alias["name_pl"] == "ser żółty gouda"
    assert alias["subcategory_code"] == "dairy"
    assert alias["alias_status"] == "confirmed"
    assert alias["alias_source"] == "user"


def test_telegram_inline_buttons_text_csv_and_export_command(
    temp_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = tenants_repo.create_tenant(
        name="TelegramFullModes",
        language="pl",
        default_currency="PLN",
        delivery_modes=["hub_db", "telegram_text", "telegram_csv"],
        database_path=temp_db,
    )

    img1 = tmp_path / "tg1.jpg"
    img1.write_bytes(b"jpg1")
    job1_id = jobs_repo.create_job(
        tenant_id=tenant["id"],
        batch_id="btg1",
        chat_id="777",
        message_id=10,
        filename="tg1.jpg",
        image_path=str(img1),
        database_path=temp_db,
    )

    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: ReceiptOCRResult(
            store_name="Biedronka",
            transaction_date="2026-10-28",
            total_amount=13.78,
            currency="PLN",
            items=[
                ReceiptItem(
                    name="JAJA M 10",
                    clean_name="jajka",
                    name_pl="jajka",
                    name_en="eggs",
                    category="FOOD",
                    subcategory="eggs",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=8.99,
                    total_price=8.99,
                    match_source="cache",
                ),
                ReceiptItem(
                    name="BANANY LUZ",
                    clean_name="banany",
                    name_pl="banany",
                    name_en="bananas",
                    category="FOOD",
                    subcategory="fruits",
                    unit="kg",
                    quantity=0.685,
                    unit_price=6.99,
                    total_price=4.79,
                    match_source="llm",
                ),
            ],
        ),
    )

    context = MagicMock()
    context.application.bot_data = {"tenant_id": tenant["id"]}
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()

    # 1. Batch notify sends rich preview with inline Confirm & Reject buttons
    asyncio.run(handlers.process_batch_and_notify(tenant["id"], "btg1", 777, context))
    assert context.bot.send_message.call_count == 1
    preview_kwargs = context.bot.send_message.call_args.kwargs
    assert "✅ Sum check OK (13.78 PLN · 2 items)" in preview_kwargs["text"]
    assert "⚡" in preview_kwargs["text"]
    assert "🆕" in preview_kwargs["text"]
    buttons = preview_kwargs["reply_markup"].inline_keyboard[0]
    assert buttons[0].callback_data == f"confirm:{job1_id}"
    assert buttons[1].callback_data == f"reject:{job1_id}"

    # 2. Tap inline [✅ Confirm] button -> delivers summary + <pre> text + .csv document!
    context.bot.send_message.reset_mock()
    context.bot.send_document.reset_mock()

    cb_update = MagicMock()
    cb_update.effective_chat.id = 777
    cb_update.callback_query.data = f"confirm:{job1_id}"
    cb_update.callback_query.answer = AsyncMock()
    cb_update.callback_query.edit_message_reply_markup = AsyncMock()

    asyncio.run(handlers.handle_callback_query(cb_update, context))
    cb_update.callback_query.answer.assert_called_once()
    cb_update.callback_query.edit_message_reply_markup.assert_called_once_with(reply_markup=None)

    # 2 messages sent: confirmation summary + <pre> copyable CSV text
    assert context.bot.send_message.call_count == 2
    pre_msg = context.bot.send_message.call_args_list[1].kwargs["text"]
    assert pre_msg.startswith("<pre>date,store,raw_name,clean_name,")
    assert "2026-10-28,Biedronka,BANANY LUZ,banany,FOOD,fruits,0.685,kg,6.99,4.79,PLN" in pre_msg

    # 1 CSV document sent via send_document
    assert context.bot.send_document.call_count == 1
    doc_kwargs = context.bot.send_document.call_args.kwargs
    assert doc_kwargs["filename"] == "2026-10-28_biedronka_13-78.csv"
    csv_content = doc_kwargs["document"].getvalue().decode("utf-8")
    parsed_rows = list(csv.DictReader(io.StringIO(csv_content)))
    assert len(parsed_rows) == 2
    assert parsed_rows[0]["clean_name"] == "jajka"
    assert parsed_rows[1]["unit"] == "kg"

    # 3. Run /export 2026-10 -> sends monthly CSV file from Hub DB
    context.bot.send_document.reset_mock()
    exp_update = MagicMock()
    exp_update.effective_chat.id = 777
    exp_update.message.reply_text = AsyncMock()
    context.args = ["2026-10"]

    asyncio.run(handlers.cmd_export(exp_update, context))
    assert context.bot.send_document.call_count == 1
    exp_kwargs = context.bot.send_document.call_args.kwargs
    assert exp_kwargs["filename"] == "receipts_2026-10.csv"
    assert "JAJA M 10" in exp_kwargs["document"].getvalue().decode("utf-8")

    # 4. Tap inline [🗑️ Reject] button on a second job -> deletes job cleanly
    img2 = tmp_path / "tg2.jpg"
    img2.write_bytes(b"jpg2")
    job2_id = jobs_repo.create_job(
        tenant_id=tenant["id"],
        batch_id="btg2",
        chat_id="777",
        message_id=11,
        filename="tg2.jpg",
        image_path=str(img2),
        database_path=temp_db,
    )
    queue_service.process_batch(tenant_id=tenant["id"], batch_id="btg2", database_path=temp_db)

    rej_update = MagicMock()
    rej_update.effective_chat.id = 777
    rej_update.callback_query.data = f"reject:{job2_id}"
    rej_update.callback_query.answer = AsyncMock()
    rej_update.callback_query.edit_message_reply_markup = AsyncMock()

    asyncio.run(handlers.handle_callback_query(rej_update, context))
    assert jobs_repo.get_job(job2_id, tenant_id=tenant["id"], database_path=temp_db) is None
