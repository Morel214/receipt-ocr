"""Centralized configuration and environment settings for Receipt OCR Hub."""

import os
from pathlib import Path

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))

ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE)

DEFAULT_DB_PATH = DATA_DIR / "ocr_hub.db"
DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))

UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(DATA_DIR / "uploads")))
RECEIPTS_UPLOAD_DIR = UPLOADS_DIR / "receipts"

# Admin authentication
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "change-me-admin-master-secret")

# Cloud OCR & Classification LLM configuration
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "openai").strip().lower()
OCR_MODEL = os.getenv("OCR_MODEL", "gpt-4o-mini").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "120"))

# Default Biometer subcategories (used unless a tenant overrides them)
DEFAULT_SUBCATEGORIES: list[str] = [
    "nabiał",
    "mięso i wędliny",
    "warzywa",
    "owoce",
    "pieczywo",
    "produkty zbożowe",
    "makaron",
    "przetwory i słoiki",
    "gotowy posiłek",
    "przekąski",
    "napoje",
    "artykuły domowe/inne",
    "inne",
]

# Queue & Telegram polling settings
RECEIPT_OCR_CONFIDENCE_THRESHOLD = float(os.getenv("RECEIPT_OCR_CONFIDENCE_THRESHOLD", "0.7"))
RECEIPT_JOB_TIMEOUT_HOURS = float(os.getenv("RECEIPT_JOB_TIMEOUT_HOURS", "24"))
TELEGRAM_POLL_INTERVAL_SECONDS = int(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "5"))
TELEGRAM_BATCH_COOLDOWN_SECONDS = int(os.getenv("TELEGRAM_BATCH_COOLDOWN_SECONDS", "90"))
TELEGRAM_BATCH_DEBOUNCE_SECONDS = int(os.getenv("TELEGRAM_BATCH_DEBOUNCE_SECONDS", "5"))

# Optional bootstrap tenant from .env
DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "admin").strip()
DEFAULT_TELEGRAM_BOT_TOKEN = os.getenv("DEFAULT_TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_ALLOWED_CHAT_IDS = os.getenv("DEFAULT_ALLOWED_CHAT_IDS", "").strip()
DEFAULT_WEBHOOK_URL = os.getenv("DEFAULT_WEBHOOK_URL", "").strip()
DEFAULT_WEBHOOK_SECRET = os.getenv("DEFAULT_WEBHOOK_SECRET", "").strip()

# Server settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))


def ensure_directories() -> None:
    """Create essential data and upload directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.parent:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)


ensure_directories()
