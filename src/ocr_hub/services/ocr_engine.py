"""Two-Stage Receipt OCR & Product Classification Engine.

Stage 1 (Vision Model - OCR_PROVIDER / OCR_MODEL):
    Reads the receipt image and extracts raw JSON with empty ``clean_name`` and ``subcategory``.

Stage 2 (Text Classifier Model - CLASSIFIER_PROVIDER / CLASSIFIER_MODEL):
    Receives the JSON from Stage 1 and populates ``clean_name`` and ``subcategory`` for each item.
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
from ocr_hub.repositories import taxonomy_repo

logger = logging.getLogger(__name__)


# ==============================================================================
# STAGE 1 PROMPT: Pure OCR Extraction (clean_name and subcategory left empty)
# ==============================================================================
STAGE_1_OCR_PROMPT = """Read all data from this receipt and return ONLY pure JSON code (without any introductory text, explanations, or Markdown formatting tags such as ```json).

Data analysis rules:
1. "store_name": Store/chain name (e.g. "Jumbo", "Lidl", "Biedronka").
2. "transaction_date": Purchase date extracted from the receipt strictly in YYYY-MM-DD format.
3. "total_amount": Final total amount to pay (float).
4. "currency": Three-letter currency code extracted from the receipt (e.g. "EUR", "PLN"). If missing, infer from the country/store.
5. "items" list (receipt line items):
   - "name": Exact original item name from the receipt.
   - "clean_name": empty
   - "subcategory": empty
   - "quantity": Product quantity or weight (float, default 1.0).
   - "unit_price": Price per unit/piece (float).
   - "total_price": Total price for the item after quantity or negative discount amount (float).

Required JSON structure:
{
  "store_name": "string",
  "transaction_date": "YYYY-MM-DD",
  "total_amount": 0.00,
  "currency": "EUR",
  "items": [
    {
      "name": "string",
      "clean_name": "",
      "subcategory": null,
      "quantity": 1.0,
      "unit_price": 0.00,
      "total_price": 0.00
    }
  ]
}"""


def build_stage_2_classifier_prompt(
    subcategories: list[str] | None = None,
    language: str = "en",
) -> str:
    """Build the prompt for Stage 2 (Text LLM filling in clean_name and subcategory)."""
    allowed_subcats = subcategories or taxonomy_repo.get_active_subcategory_codes()
    subcats_formatted = ", ".join(f'"{s}"' for s in allowed_subcats)
    lang_map = {
        "en": "English",
        "pl": "Polish",
    }
    lang_desc = lang_map.get(language.strip().lower(), "English")

    return (
        "You are a receipt product normalizer and classifier.\n"
        "You will receive a JSON object extracted from a receipt where each item in `items` has an empty `clean_name` and `subcategory`.\n"
        "Return ONLY pure JSON code (without any introductory text, explanations, or Markdown formatting tags such as ```json) "
        "with the exact same structure and numeric values, filling in `clean_name` and `subcategory` for every item:\n"
        f"1. `clean_name`: Concise, human-readable generic product name in {lang_desc} (lowercase, e.g. "
        "if English: 'yellow cheese', 'eggs', 'rolled oats', 'chicken breast'; "
        "if Polish: 'ser żółty', 'jajka', 'płatki owsiane', 'pierś z kurczaka'). "
        "For bottle deposits ('STATIEGELD' / 'KAUCJA') use 'deposit' (or 'kaucja' if Polish). "
        "For discount/rebate lines (negative prices, 'ACTIE', 'BONUS', 'RABAT', 'KIES&MIX') use 'Discount' (or 'Rabat' if Polish).\n"
        f"2. `subcategory`: Choose strictly ONE from [{subcats_formatted}], or `null` if the line is a discount.\n"
        "Do not modify `store_name`, `transaction_date`, `total_amount`, `currency`, `name`, `quantity`, `unit_price`, or `total_price`."
    )


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
    """Validate a parsed OCR dictionary into a ``ReceiptOCRResult`` model."""
    result = ReceiptOCRResult.model_validate(data)
    result.store_name = normalize_store_name(result.store_name)
    return result


def _strip_json_fences(raw_text: str) -> str:
    """Remove optional ```json ... ``` markdown code fences from LLM output."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _resolve_openai_compatible_credentials(provider: str) -> tuple[str, str]:
    """Return ``(api_key, base_url)`` for OpenAI, DeepSeek, or OpenRouter."""
    p = provider.strip().lower()
    if p == "deepseek":
        key = config.DEEPSEEK_API_KEY or config.OPENAI_API_KEY
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured in .env.")
        return key, config.DEEPSEEK_BASE_URL
    if p == "openrouter":
        key = config.OPENROUTER_API_KEY or config.OPENAI_API_KEY
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured in .env.")
        return key, config.OPENROUTER_BASE_URL

    key = config.OPENAI_API_KEY
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured in .env.")
    return key, config.OPENAI_BASE_URL


def _call_vision_model(
    content: bytes,
    content_type: str,
    prompt: str,
    provider: str,
    model: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Execute Stage 1 Vision call (OpenAI/OpenRouter or Gemini)."""
    req_timeout = timeout if timeout is not None else config.OCR_TIMEOUT_SECONDS
    b64_image = base64.b64encode(content).decode("ascii")
    p = provider.strip().lower()

    if p == "gemini":
        key = config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured in .env.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": content_type, "data": b64_image}},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        logger.info("[Stage 1 OCR - Gemini] POST %s model=%s", url, model)
        response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
        response.raise_for_status()
        raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(_strip_json_fences(raw_text))

    if p in ("openai", "openrouter", "custom"):
        key, base_url = _resolve_openai_compatible_credentials(p)
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{b64_image}"},
                        },
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        logger.info("[Stage 1 OCR - %s] POST %s model=%s", p, url, model)
        response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_json_fences(raw_text))

    raise ValueError(
        f"Unsupported Stage 1 OCR provider '{provider}'. Choose 'openai', 'gemini', or 'openrouter'."
    )


def _call_text_classifier_model(
    raw_ocr_data: dict[str, Any],
    system_prompt: str,
    provider: str,
    model: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Execute Stage 2 Text Classifier call (OpenAI, Gemini, DeepSeek, or OpenRouter)."""
    req_timeout = timeout if timeout is not None else config.OCR_TIMEOUT_SECONDS
    input_json_str = json.dumps(raw_ocr_data, ensure_ascii=False)
    p = provider.strip().lower()

    if p == "gemini":
        key = config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured in .env.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": input_json_str}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        logger.info("[Stage 2 Classifier - Gemini] POST %s model=%s", url, model)
        response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
        response.raise_for_status()
        raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(_strip_json_fences(raw_text))

    if p in ("openai", "deepseek", "openrouter", "custom"):
        key, base_url = _resolve_openai_compatible_credentials(p)
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_json_str},
            ],
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        logger.info("[Stage 2 Classifier - %s] POST %s model=%s", p, url, model)
        response = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_json_fences(raw_text))

    raise ValueError(
        f"Unsupported Stage 2 Classifier provider '{provider}'. Choose 'openai', 'gemini', 'deepseek', or 'openrouter'."
    )


def extract_raw_receipt_ocr(
    content: bytes,
    content_type: str = "image/jpeg",
    provider: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Stage 1: Extract receipt header and raw items with empty ``clean_name`` and ``subcategory``."""
    chosen_provider = (provider or config.OCR_PROVIDER).strip().lower()
    chosen_model = (model or config.OCR_MODEL).strip()
    if chosen_provider == "gemini" and not model and chosen_model.startswith("gpt-"):
        chosen_model = "gemini-2.5-flash"

    raw_data = _call_vision_model(
        content=content,
        content_type=content_type,
        prompt=STAGE_1_OCR_PROMPT,
        provider=chosen_provider,
        model=chosen_model,
        timeout=timeout,
    )

    # Guarantee Stage 1 contract: clean_name is "" and subcategory is None before Stage 2
    for item in raw_data.get("items", []):
        if isinstance(item, dict):
            item["clean_name"] = ""
            item["subcategory"] = None

    return raw_data


def classify_receipt_items(
    raw_ocr_data: dict[str, Any],
    subcategories: list[str] | None = None,
    language: str = "en",
    provider: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Stage 2: Populate ``clean_name`` and ``subcategory`` on the Stage 1 JSON using the classifier model."""
    if not raw_ocr_data.get("items"):
        return raw_ocr_data

    chosen_provider = (provider or config.CLASSIFIER_PROVIDER).strip().lower()
    chosen_model = (model or config.CLASSIFIER_MODEL).strip()
    if chosen_provider == "gemini" and not model and chosen_model.startswith("gpt-"):
        chosen_model = "gemini-2.5-flash"
    elif chosen_provider == "deepseek" and not model and chosen_model.startswith("gpt-"):
        chosen_model = "deepseek-chat"

    system_prompt = build_stage_2_classifier_prompt(
        subcategories=subcategories,
        language=language,
    )

    return _call_text_classifier_model(
        raw_ocr_data=raw_ocr_data,
        system_prompt=system_prompt,
        provider=chosen_provider,
        model=chosen_model,
        timeout=timeout,
    )


def analyze_receipt_image(
    content: bytes,
    content_type: str = "image/jpeg",
    provider: str | None = None,
    model: str | None = None,
    classifier_provider: str | None = None,
    classifier_model: str | None = None,
    subcategories: list[str] | None = None,
    default_currency: str = "EUR",
    language: str = "en",
    timeout: int | None = None,
) -> ReceiptOCRResult:
    """Run the two-stage pipeline (Stage 1 Vision OCR -> Stage 2 Text Classifier) and validate result."""
    # Stage 1: Vision OCR
    stage1_json = extract_raw_receipt_ocr(
        content=content,
        content_type=content_type,
        provider=provider,
        model=model,
        timeout=timeout,
    )
    if not stage1_json.get("currency"):
        stage1_json["currency"] = default_currency

    # Stage 2: Text Classification (fills clean_name & subcategory)
    stage2_json = classify_receipt_items(
        raw_ocr_data=stage1_json,
        subcategories=subcategories,
        language=language,
        provider=classifier_provider or provider,
        model=classifier_model,
        timeout=timeout,
    )
    if not stage2_json.get("currency"):
        stage2_json["currency"] = default_currency

    return validate_ocr_result(stage2_json)
