"""Pydantic domain models for Receipt OCR Hub, tenants, and webhooks."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReceiptItem(BaseModel):
    """A single line item on a receipt (compatible with Biometer ReceiptItem)."""

    name: str = Field(min_length=1, max_length=200)
    clean_name: str = Field(default="", max_length=200)
    category: str = Field(default="FOOD", max_length=100)
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
    currency: str = Field(default="PLN", max_length=10)
    confidence: float | None = Field(default=None, ge=0, le=1)
    items: list[ReceiptItem] = Field(default_factory=list)


class TenantCreateRequest(BaseModel):
    """Payload for registering a new user/friend and their Telegram bot."""

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


class TenantUpdateConfigRequest(BaseModel):
    """Self-service or admin update payload for a tenant's destination/OCR settings."""

    webhook_url: str | None = None
    webhook_secret: str | None = None
    default_currency: str | None = Field(default=None, max_length=10)
    language: str | None = Field(default=None, max_length=10)
    subcategories: list[str] | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    allowed_chat_ids: list[int] | None = None
    telegram_bot_token: str | None = None
    is_active: bool | None = None


class WebhookDeliveryPayload(BaseModel):
    """Payload sent to a user's configured webhook URL upon receipt confirmation.

    Includes both top-level ReceiptOCRResult fields (for direct drop-in
    compatibility with Biometer) and nested ``receipt`` metadata.
    """

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
