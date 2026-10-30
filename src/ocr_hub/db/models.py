"""Pydantic domain models for Receipt OCR Hub, tenants, and webhooks."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReceiptItem(BaseModel):
    """A single line item on a receipt."""

    name: str = Field(min_length=1, max_length=200)
    clean_name: str = Field(default="", max_length=200)
    category: str | None = Field(default=None, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="pcs", max_length=20)
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(ge=-1000000)
    total_price: float = Field(ge=-1000000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    product_id: int | None = None
    alias_id: int | None = None
    name_pl: str | None = None
    name_en: str | None = None
    brand: str | None = None
    off_search_query: str | None = None
    pack_amount: float | None = None
    pack_unit: str | None = None
    match_source: str = Field(default="llm", max_length=30)

    @field_validator("clean_name", mode="before")
    @classmethod
    def normalize_clean_name(cls, value: Any) -> str:
        """Coerce null/missing clean_name to ''."""
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in ("", "null", "[null]", "none") else text

    @field_validator("subcategory", "category", mode="before")
    @classmethod
    def normalize_optional_taxonomy(cls, value: Any) -> str | None:
        """Coerce null/missing category or subcategory to None."""
        if value is None:
            return None
        text = str(value).strip()
        return None if text.lower() in ("", "null", "[null]", "none") else text

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: Any) -> str:
        """Normalize receipt quantity unit strictly to 'pcs', 'kg', or 'l'."""
        if value is None:
            return "pcs"
        u = str(value).strip().lower().rstrip(".")
        if u in ("kg", "kilogram", "kilograms", "waga"):
            return "kg"
        if u in ("l", "litr", "liter", "liters", "litre"):
            return "l"
        return "pcs"


class ReceiptOCRResult(BaseModel):
    """Structured OCR and product classification result."""

    receipt_id: int | None = None
    store_id: int | None = None
    store_name: str = Field(default="Unknown Store", min_length=1, max_length=200)
    transaction_date: date | None = None
    total_amount: float = Field(default=0.0, ge=0)
    currency: str = Field(default="PLN", max_length=10)
    confidence: float | None = None
    cache_hits: int = 0
    llm_classified_count: int = 0
    items: list[ReceiptItem] = Field(default_factory=list)


SUPPORTED_LANGUAGES = ("en", "pl")
VALID_DELIVERY_MODES = ("hub_db", "webhook", "telegram_text", "telegram_csv")


def normalize_delivery_modes(modes: list[str]) -> list[str]:
    """Validate and deduplicate delivery mode identifiers while preserving order."""
    normalized: list[str] = []
    for raw_mode in modes:
        mode = str(raw_mode).strip().lower()
        if not mode:
            continue
        if mode not in VALID_DELIVERY_MODES:
            raise ValueError(
                f"Unsupported delivery mode '{raw_mode}'. Allowed: {VALID_DELIVERY_MODES}"
            )
        if mode not in normalized:
            normalized.append(mode)
    return normalized


class TenantCreateRequest(BaseModel):
    """Payload for registering a new user/bot and their destination webhook."""

    name: str = Field(min_length=1, max_length=100)
    telegram_bot_token: str | None = None
    allowed_chat_ids: list[int] = Field(default_factory=list)
    webhook_url: str | None = None
    webhook_secret: str | None = None
    default_currency: str = Field(default="PLN", max_length=10)
    language: str = Field(default="pl", max_length=10)
    delivery_modes: list[str] = Field(default_factory=lambda: ["webhook"])
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

    @field_validator("delivery_modes")
    @classmethod
    def validate_delivery_modes(cls, value: list[str]) -> list[str]:
        """Validate requested post-confirmation delivery modes."""
        return normalize_delivery_modes(value)


class TenantUpdateConfigRequest(BaseModel):
    """Update payload for a bot/user configuration."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_url: str | None = None
    webhook_secret: str | None = None
    default_currency: str | None = Field(default=None, max_length=10)
    language: str | None = Field(default=None, max_length=10)
    delivery_modes: list[str] | None = None
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

    @field_validator("delivery_modes")
    @classmethod
    def validate_optional_delivery_modes(cls, value: list[str] | None) -> list[str] | None:
        """Validate optional post-confirmation delivery modes update."""
        if value is None:
            return None
        return normalize_delivery_modes(value)


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


VALID_CATALOG_STATUSES = ("auto", "confirmed", "pending")


class CatalogProductCreateRequest(BaseModel):
    """Payload for creating a product in the shared catalog (or pending manual_user queue)."""

    name_pl: str = Field(min_length=1, max_length=150)
    name_en: str = Field(min_length=1, max_length=150)
    subcategory_code: str | None = Field(default=None, max_length=60)
    default_unit: str = Field(default="pcs", max_length=20)

    @field_validator("default_unit", mode="before")
    @classmethod
    def validate_unit(cls, value: Any) -> str:
        return ReceiptItem.normalize_unit(value)


class CatalogProductUpdateRequest(BaseModel):
    """Payload for Admin edits to a shared catalog product."""

    name_pl: str | None = Field(default=None, min_length=1, max_length=150)
    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    subcategory_code: str | None = Field(default=None, max_length=60)
    default_unit: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)
    kcal_100g: float | None = None
    protein_100g: float | None = None
    carbs_100g: float | None = None
    fat_100g: float | None = None
    fiber_100g: float | None = None
    default_piece_weight_g: float | None = None
    nutrition_source: str | None = Field(default=None, max_length=30)

    @field_validator("default_unit", mode="before")
    @classmethod
    def validate_optional_unit(cls, value: Any) -> str | None:
        if value is None:
            return None
        return ReceiptItem.normalize_unit(value)

    @field_validator("status")
    @classmethod
    def validate_optional_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().lower()
        if clean not in VALID_CATALOG_STATUSES:
            raise ValueError(
                f"Unsupported product status '{value}'. Allowed: {VALID_CATALOG_STATUSES}"
            )
        return clean


class CatalogProductMergeRequest(BaseModel):
    """Payload for merging a duplicate source product into a canonical target product."""

    target_product_id: int = Field(gt=0)


class CatalogAliasCreateRequest(BaseModel):
    """Payload for manually adding or overriding a receipt item alias in the catalog cache."""

    raw_name: str = Field(min_length=1, max_length=200)
    product_id: int = Field(gt=0)
    store_id: int | None = None
    brand: str | None = Field(default=None, max_length=120)
    off_search_query: str | None = Field(default=None, max_length=200)
    pack_amount: float | None = None
    pack_unit: str | None = Field(default=None, max_length=20)


class CatalogAliasUpdateRequest(BaseModel):
    """Payload for editing an existing receipt item alias mapping or OFF metadata."""

    product_id: int | None = Field(default=None, gt=0)
    store_id: int | None = None
    brand: str | None = Field(default=None, max_length=120)
    off_search_query: str | None = Field(default=None, max_length=200)
    pack_amount: float | None = None
    pack_unit: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)

    @field_validator("status")
    @classmethod
    def validate_alias_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().lower()
        if clean not in ("auto", "confirmed"):
            raise ValueError("Alias status must be 'auto' or 'confirmed'.")
        return clean


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
