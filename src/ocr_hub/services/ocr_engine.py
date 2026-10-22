"""Cloud Vision OCR & Product Classification Engine (OpenAI / OpenRouter / Gemini).

Replaces the legacy n8n workflow with direct, structured cloud VLM calls that
simultaneously extract receipt headers, line items, clean product names, and
categories/subcategories.
"""

import base64
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from ocr_hub import config
from ocr_hub.db.models import ReceiptOCRResult

logger = logging.getLogger(__name__)


def normalize_store_name(name: str | None) -> str:
    """Normalize a store name to Title Case while preserving apostrophes."""
    if not name:
        return "Unknown Store"
    return " ".join(word.capitalize() for word in name.strip().split())


def sanitize_slug(text: str) -> str:
    """Sanitize a string into a filesystem-safe slug."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    return re.sub(r"[-\s]+", "-", slug) or "unknown"


def generate_receipt_filename(
    store_name: str,
    transaction_date: str,
    total_amount: float,
    ext: str = "jpg",
    upload_dir: Path | None = None,
) -> str:
    """Generate a unique receipt filename formatted as ``{date}-{store}-{amount}.{ext}``."""
    target_dir = upload_dir or config.RECEIPTS_UPLOAD_DIR
    clean_date = (
        transaction_date.strip() if transaction_date else datetime.now().strftime("%Y-%m-%d")
    )
    clean_store = sanitize_slug(store_name)
    amount_slug = f"{float(total_amount):.2f}".replace(".", "-")
    base_name = f"{clean_date}-{clean_store}-{amount_slug}"
    candidate = f"{base_name}.{ext}"
    if not (target_dir / candidate).exists():
        return candidate

    counter = 1
    while True:
        candidate = f"{base_name}-{counter}.{ext}"
        if not (target_dir / candidate).exists():
            return candidate
        counter += 1


def validate_ocr_result(data: dict[str, Any]) -> ReceiptOCRResult:
    """Validate raw OCR dictionary into a ``ReceiptOCRResult`` model."""
    result = ReceiptOCRResult.model_validate(data)
    result.store_name = normalize_store_name(result.store_name)
    return result


def build_ocr_system_prompt(
    subcategories: list[str] | None = None,
    default_currency: str = "PLN",
    language: str = "pl",
) -> str:
    """Build the system instruction for receipt extraction and item categorization."""
    allowed_subcats = subcategories or config.DEFAULT_SUBCATEGORIES
    subcats_formatted = ", ".join(f'"{s}"' for s in allowed_subcats)
    lang_label = "Polish (lowercase)" if language.lower() == "pl" else f"'{language}' (lowercase)"

    return (
        "You are an expert Receipt OCR and Grocery Product Classifier.\n"
        "Analyze the provided receipt image (which may be in Polish, Dutch, English, German, or another language) "
        "and return ONLY a valid JSON object matching the exact schema below.\n\n"
        "### Extraction & Classification Rules:\n"
        "1. `store_name`: Name of the merchant/supermarket in Title Case (e.g. 'Biedronka', 'Lidl', 'Jumbo', 'Albert Heijn').\n"
        "2. `transaction_date`: Receipt date in `YYYY-MM-DD` format (or null if unreadable).\n"
        "3. `total_amount`: Final total amount paid (float, >= 0).\n"
        f"4. `currency`: 3-letter ISO currency code detected from the receipt (e.g. 'PLN', 'EUR', 'USD'). Default to '{default_currency}' if not shown.\n"
        "5. `confidence`: Overall OCR reading confidence between 0.0 and 1.0.\n"
        "6. `items`: Array of line items purchased. For EVERY item on the receipt:\n"
        "   - `name`: Exact raw item text as printed on the receipt (e.g. 'PLAK JONG GVP', 'SCHARREL M/L 12ST').\n"
        f"   - `clean_name`: Simplified, human-readable generic product name in {lang_label} "
        "(e.g. 'ser żółty', 'jajka', 'płatki owsiane', 'filet z kurczaka'). "
        "For bottle deposits ('STATIEGELD' / 'KAUCJA') use 'kaucja'. "
        "For discount/rebate lines ('RABAT', 'OPUST', 'ACTIE', 'KIES&MIX', 'BONUS') use 'Rabat'.\n"
        "   - `category`: High-level category ('FOOD', 'HOUSEHOLD', 'HEALTH', 'OTHER').\n"
        f"   - `subcategory`: Choose strictly ONE from: [{subcats_formatted}], or `null` if the line is a discount ('Rabat').\n"
        "   - `quantity`: Numeric quantity (float > 0, default 1.0).\n"
        "   - `unit_price`: Price per single unit (float; use a NEGATIVE number for discounts/promotions).\n"
        "   - `total_price`: Total price for this line item (float; use a NEGATIVE number for discounts/promotions).\n"
        "   - `confidence`: Line-level reading confidence between 0.0 and 1.0.\n\n"
        "### Required JSON Output Structure:\n"
        "{\n"
        '  "store_name": "string",\n'
        '  "transaction_date": "YYYY-MM-DD",\n'
        '  "total_amount": 0.0,\n'
        f'  "currency": "{default_currency}",\n'
        '  "confidence": 0.95,\n'
        '  "items": [\n'
        "    {\n"
        '      "name": "RAW RECEIPT NAME",\n'
        '      "clean_name": "normalized name",\n'
        '      "category": "FOOD",\n'
        '      "subcategory": "one of allowed subcategories or null",\n'
        '      "quantity": 1.0,\n'
        '      "unit_price": 0.0,\n'
        '      "total_price": 0.0,\n'
        '      "confidence": 0.95\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _strip_json_fences(raw_text: str) -> str:
    """Remove optional ```json ... ``` markdown code fences from LLM output."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _call_openai_compatible(
    content: bytes,
    content_type: str,
    system_prompt: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Call OpenAI or any OpenAI-compatible Vision API (OpenRouter, Groq, LiteLLM)."""
    key = api_key or config.OPENAI_API_KEY
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in .env before running OpenAI OCR."
        )
    url = f"{(base_url or config.OPENAI_BASE_URL).rstrip('/')}/chat/completions"
    req_timeout = timeout if timeout is not None else config.OCR_TIMEOUT_SECONDS
    b64_image = base64.b64encode(content).decode("ascii")

    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract and classify all items from this receipt image into the required JSON format.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{b64_image}"},
                    },
                ],
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    logger.info("[_call_openai_compatible] POST %s model=%s (%d bytes)", url, model, len(content))
    response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
    response.raise_for_status()
    resp_json = response.json()
    raw_content = resp_json["choices"][0]["message"]["content"]
    return json.loads(_strip_json_fences(raw_content))


def _call_gemini(
    content: bytes,
    content_type: str,
    system_prompt: str,
    model: str,
    api_key: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Call Google Gemini Vision REST API with structured JSON output."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in .env before running Gemini OCR."
        )
    req_timeout = timeout if timeout is not None else config.OCR_TIMEOUT_SECONDS
    b64_image = base64.b64encode(content).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "Extract and classify all items from this receipt image into the required JSON format."
                    },
                    {
                        "inlineData": {
                            "mimeType": content_type,
                            "data": b64_image,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json",
    }

    logger.info("[_call_gemini] POST %s model=%s (%d bytes)", url, model, len(content))
    response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
    response.raise_for_status()
    resp_json = response.json()
    raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(_strip_json_fences(raw_text))


def analyze_receipt_image(
    content: bytes,
    content_type: str = "image/jpeg",
    provider: str | None = None,
    model: str | None = None,
    subcategories: list[str] | None = None,
    default_currency: str = "PLN",
    language: str = "pl",
    timeout: int | None = None,
) -> ReceiptOCRResult:
    """Run Cloud Vision OCR + item classification on a receipt image and validate the result.

    Args:
        content: Raw image bytes (JPEG/PNG).
        content_type: Image MIME type.
        provider: Cloud provider ('openai' or 'gemini'). Defaults to ``config.OCR_PROVIDER``.
        model: Model identifier override (e.g. 'gpt-4o-mini', 'gemini-2.5-flash').
        subcategories: Optional custom list of allowed item subcategories.
        default_currency: Default currency code if not printed on the receipt.
        language: Language code for ``clean_name`` normalization (default 'pl').
        timeout: Request timeout in seconds.

    Returns:
        Validated ``ReceiptOCRResult`` instance.
    """
    chosen_provider = (provider or config.OCR_PROVIDER).strip().lower()
    chosen_model = (model or config.OCR_MODEL).strip()
    if chosen_provider == "gemini" and not model and chosen_model.startswith("gpt-"):
        chosen_model = "gemini-2.5-flash"

    system_prompt = build_ocr_system_prompt(
        subcategories=subcategories,
        default_currency=default_currency,
        language=language,
    )

    if chosen_provider in ("openai", "openrouter", "custom"):
        raw_data = _call_openai_compatible(
            content=content,
            content_type=content_type,
            system_prompt=system_prompt,
            model=chosen_model,
            timeout=timeout,
        )
    elif chosen_provider == "gemini":
        raw_data = _call_gemini(
            content=content,
            content_type=content_type,
            system_prompt=system_prompt,
            model=chosen_model,
            timeout=timeout,
        )
    else:
        raise ValueError(
            f"Unsupported OCR provider '{chosen_provider}'. Choose 'openai' or 'gemini'."
        )

    return validate_ocr_result(raw_data)
