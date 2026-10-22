"""Pytest fixtures for Receipt OCR Hub tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocr_hub import config
from ocr_hub.api.app import app
from ocr_hub.db.schema import init_db


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated temporary SQLite database and uploads directory."""
    db_file = tmp_path / "test_ocr_hub.db"
    uploads_dir = tmp_path / "uploads"
    receipts_dir = uploads_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(config, "RECEIPTS_UPLOAD_DIR", receipts_dir)
    monkeypatch.setattr(config, "ADMIN_API_KEY", "test-admin-secret")
    monkeypatch.setattr(config, "DEFAULT_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "DEFAULT_WEBHOOK_URL", "")

    init_db(db_file)
    return db_file


@pytest.fixture()
def client(temp_db: Path) -> TestClient:
    """FastAPI TestClient bound to the isolated temporary database."""
    with TestClient(app) as test_client:
        yield test_client
