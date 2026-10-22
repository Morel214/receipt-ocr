"""Tests for multi-tenant isolation, job queue lifecycle, and webhook delivery."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from ocr_hub.db.models import ReceiptItem, ReceiptOCRResult
from ocr_hub.repositories import jobs_repo, tenants_repo
from ocr_hub.services import queue_service


def _fake_ocr_result(store: str = "Biedronka", total: float = 42.50) -> ReceiptOCRResult:
    return ReceiptOCRResult(
        store_name=store,
        transaction_date="2026-10-22",
        total_amount=total,
        currency="PLN",
        confidence=0.95,
        items=[
            ReceiptItem(
                name="SER GOUDA",
                clean_name="ser gouda",
                category="FOOD",
                subcategory="nabiał",
                quantity=1.0,
                unit_price=total,
                total_price=total,
                confidence=0.95,
            )
        ],
    )


def test_multi_tenant_queue_and_webhook_delivery(
    temp_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_a = tenants_repo.create_tenant(
        name="UserA",
        webhook_url="https://user-a.example.com/webhook",
        webhook_secret="secret-a",
    )
    tenant_b = tenants_repo.create_tenant(
        name="UserB",
        webhook_url="https://user-b.example.com/webhook",
        webhook_secret="secret-b",
    )

    img_a = tmp_path / "img_a.jpg"
    img_a.write_bytes(b"jpeg-bytes-a")
    job_a_id = jobs_repo.create_job(
        tenant_id=tenant_a["id"],
        batch_id="batch1",
        chat_id="1001",
        message_id=1,
        filename="img_a.jpg",
        image_path=str(img_a),
    )

    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: _fake_ocr_result("Lidl", 55.00),
    )

    processed = queue_service.process_batch(tenant_id=tenant_a["id"], batch_id="batch1")
    assert len(processed) == 1
    assert processed[0]["store_name"] == "Lidl"
    assert processed[0]["status"] == jobs_repo.AWAITING_CONFIRMATION

    # Tenant B must NOT see or be able to confirm Tenant A's job
    assert jobs_repo.list_open_jobs(tenant_id=tenant_b["id"]) == []
    with pytest.raises(ValueError, match="nie istnieje"):
        queue_service.confirm_job(tenant_id=tenant_b["id"], job_id=job_a_id)

    # Confirm as Tenant A -> should POST to Tenant A's webhook with Bearer secret-a
    captured_requests: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        captured_requests.append({"url": url, "json": json, "headers": headers})
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"status": "saved", "receipt_id": 99}
        return resp

    monkeypatch.setattr("ocr_hub.services.webhook_dispatcher.requests.post", fake_post)

    outcome = queue_service.confirm_job(tenant_id=tenant_a["id"], job_id=job_a_id)
    assert outcome["webhook_delivered"] is True
    assert outcome["webhook_status_code"] == 200
    assert len(captured_requests) == 1
    assert captured_requests[0]["url"] == "https://user-a.example.com/webhook"
    assert captured_requests[0]["headers"]["Authorization"] == "Bearer secret-a"
    assert captured_requests[0]["json"]["store_name"] == "Lidl"
    assert captured_requests[0]["json"]["items"][0]["clean_name"] == "ser gouda"


def test_webhook_failure_marks_job_delivery_failed_and_allows_retry(
    temp_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = tenants_repo.create_tenant(
        name="RetryUser",
        webhook_url="https://down.example.com/webhook",
    )
    img = tmp_path / "img.jpg"
    img.write_bytes(b"jpeg-bytes")
    job_id = jobs_repo.create_job(
        tenant_id=tenant["id"],
        batch_id="b1",
        chat_id="2002",
        message_id=10,
        filename="img.jpg",
        image_path=str(img),
    )

    monkeypatch.setattr(
        "ocr_hub.services.queue_service.analyze_receipt_image",
        lambda **kwargs: _fake_ocr_result("Biedronka", 19.99),
    )
    queue_service.process_batch(tenant_id=tenant["id"], batch_id="b1")

    def failing_post(*args, **kwargs):
        raise requests.ConnectionError("Connection refused")

    monkeypatch.setattr("ocr_hub.services.webhook_dispatcher.requests.post", failing_post)

    with pytest.raises(RuntimeError, match="Webhook delivery"):
        queue_service.confirm_job(tenant_id=tenant["id"], job_id=job_id)

    job_after_fail = jobs_repo.get_job(job_id, tenant_id=tenant["id"])
    assert job_after_fail is not None
    assert job_after_fail["status"] == jobs_repo.DELIVERY_FAILED

    # Now webhook recovers -> confirming the same job succeeds without re-running OCR
    def working_post(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"ok": True}
        return resp

    monkeypatch.setattr("ocr_hub.services.webhook_dispatcher.requests.post", working_post)
    outcome = queue_service.confirm_job(tenant_id=tenant["id"], job_id=job_id)
    assert outcome["webhook_delivered"] is True
    assert outcome["webhook_status_code"] == 201
