"""Pydantic domain models for Receipt OCR Hub, tenants, and webhooks."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReceiptItem(BaseModel):
    """A single line item on a receipt."""

    name: str = Field(min_length=1, max_length=200)
    clean_name: str = Field(default="", max_length=200)
    subcategory: str | None = Field(default=None, max_length=100)
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(ge=-1000000)
    total_price: float = Field(ge=-1000000)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("clean_name", mode="before")
    @classmethod
    def normalize_clean_name(cls, value: Any) -> str:
        """Coerce null/missing clean_name to ''."""
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in ("", "null", "[null]", "none") else text

    @field_validator("subcategory", mode="before")
    @classmethod
    def normalize_subcategory(cls, value: Any) -> str | None:
        """Coerce null/missing subcategory to None."""
        if value is None:
            return None
        text = str(value).strip()
        return None if text.lower() in ("", "null", "[null]", "none") else text


class ReceiptOCRResult(BaseModel):
    """Structured OCR and product classification result."""

    receipt_id: int | None = None
    store_name: str = Field(default="Unknown Store", min_length=1, max_length=200)
    transaction_date: date | None = None
    total_amount: float = Field(default=0.0, ge=0)
    currency: str = Field(default="EUR", max_length=10)
    confidence: float | None = Field(default=None, ge=0, le=1)
    items: list[ReceiptItem] = Field(default_factory=list)


SUPPORTED_LANGUAGES = ("en", "pl")


class TenantCreateRequest(BaseModel):
    """Payload for registering a new user/bot and their destination webhook."""

    name: str = Field(min_length=1, max_length=100)
    telegram_bot_token: str | None = None
    allowed_chat_ids: list[int] = Field(default_factory=list)
    webhook_url: str | None = None
    webhook_secret: str | None = None
    default_currency: str = Field(default="PLN", max_length=10)
    language: str = Field(default="pl", max_length=10)
    subcategories: list[str] | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    classifier_provider: str | None = None
    classifier_model: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Restrict language selection to English ('en') or Polish ('pl')."""
        lang = value.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{value}'. Allowed: {SUPPORTED_LANGUAGES}")
        return lang


class TenantUpdateConfigRequest(BaseModel):
    """Update payload for a bot/user configuration."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_url: str | None = None
    webhook_secret: str | None = None
    default_currency: str | None = Field(default=None, max_length=10)
    language: str | None = Field(default=None, max_length=10)
    subcategories: list[str] | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    classifier_provider: str | None = None
    classifier_model: str | None = None
    allowed_chat_ids: list[int] | None = None
    telegram_bot_token: str | None = None
    is_active: bool | None = None

    @field_validator("language")
    @classmethod
    def validate_optional_language(cls, value: str | None) -> str | None:
        """Restrict language selection to English ('en') or Polish ('pl') when provided."""
        if value is None:
            return None
        lang = value.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{value}'. Allowed: {SUPPORTED_LANGUAGES}")
        return lang


class CategoryCreateRequest(BaseModel):
    """Payload for creating a global taxonomy category."""

    code: str = Field(min_length=1, max_length=50)
    name_pl: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    sort_order: int = 100
    is_active: bool = True


class CategoryUpdateRequest(BaseModel):
    """Payload for updating a global taxonomy category."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name_pl: str | None = Field(default=None, min_length=1, max_length=100)
    name_en: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


class SubcategoryCreateRequest(BaseModel):
    """Payload for creating a global taxonomy subcategory."""

    category_id: int
    code: str = Field(min_length=1, max_length=60)
    name_pl: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    sort_order: int = 100
    is_active: bool = True


class SubcategoryUpdateRequest(BaseModel):
    """Payload for updating a global taxonomy subcategory."""

    category_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=60)
    name_pl: str | None = Field(default=None, min_length=1, max_length=100)
    name_en: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


class WebhookDeliveryPayload(BaseModel):
    """Payload sent to a user's configured webhook URL upon receipt confirmation."""

    event: str = "receipt.confirmed"
    job_id: int | None = None
    tenant_name: str
    confirmed_at: str
    store_name: str
    transaction_date: str | None = None
    total_amount: float
    currency: str
    confidence: float | None = None
    items: list[dict[str, Any]]
    receipt: dict[str, Any]
