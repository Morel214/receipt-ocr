"""Two-Stage Receipt OCR & Cache-First Product Classification Engine.

Stage 1 (Vision Model - OCR_PROVIDER / OCR_MODEL):
    Reads the receipt image (optimized for Polish fiscal receipts 'PARAGON FISKALNY' as well as
    international receipts) and extracts raw JSON with ``unit`` ('pcs', 'kg', 'l') and empty
    ``clean_name`` / ``subcategory``.

Cache Lookup (Shared Product & Alias Catalog):
    Normalizes store and raw item names against ``product_aliases``. Known items bypass Stage 2 completely.

Stage 2 (Text Classifier Model - CLASSIFIER_PROVIDER / CLASSIFIER_MODEL):
    Invoked ONLY for cache-miss items, receiving up to 5 FTS5 trigram candidates per item, and produces
    generic PL & EN clean names, subcategory code, and brand / Open Food Facts search metadata.
"""

import base64
from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any
import unicodedata

import requests

from ocr_hub import config
from ocr_hub.db.models import ReceiptOCRResult
from ocr_hub.repositories import catalog_repo, taxonomy_repo

logger = logging.getLogger(__name__)


# ==============================================================================
# STAGE 1 PROMPT: Vision OCR (Tailored for Polish Fiscal Receipts & International)
# ==============================================================================
STAGE_1_OCR_PROMPT = """Read all purchased items and metadata from this receipt image and return ONLY pure JSON code (no introductory text, no explanations, no ```json fences).

CRITICAL RULES FOR POLISH FISCAL RECEIPTS ("PARAGON FISKALNY") & GENERAL RECEIPTS:
1. "store_name": Extract the retail chain / brand name, NOT the parent legal company name at the top:
   - "JERONIMO MARTINS POLSKA S.A." / "JMP S.A." -> "Biedronka" (unless "DROGERIE HEBE" -> "Hebe")
   - "LIDL SP. Z O.O. SP. K." -> "Lidl"
   - "ŻABKA POLSKA" or a franchisee header containing "ŻABKA" / "ZABKA Zxxxx" -> "Żabka"
   - "KAUFLAND POLSKA MARKETY" -> "Kaufland", "DINO POLSKA S.A." -> "Dino", "ROSSMANN SDP" -> "Rossmann"
   - For independent local shops, extract the shop name without "SP. Z O.O." / "S.A.".
2. "transaction_date": Purchase date strictly normalized to YYYY-MM-DD (convert Polish formats like DD.MM.YYYY, DD-MM-YYYY, or YY-MM-DD to YYYY-MM-DD).
3. "total_amount": Final amount paid ("SUMA PLN" / "RAZEM" / "DO ZAPŁATY" / "TOTAL") as a float with a dot decimal separator.
4. "currency": Three-letter ISO currency code ("PLN" for Polish receipts with PLN/zł/NIP/PTU; otherwise e.g. "EUR", "USD").
5. RECEIPT BOUNDARIES — WHAT TO INCLUDE AND IGNORE:
   - Extract ONLY purchased items and item-level discounts located above the tax/total summary ("SPRZEDAŻ OPODATKOWANA", "PTU A/B/C", "SUMA PTU", "SUMA PLN").
   - NEVER include tax breakdown lines ("SPRZEDAŻ OPODATKOWANA", "PTU"), payment lines ("KARTA", "GOTÓWKA", "BLIK", "RESZTA"), NIP/BDO/receipt numbers, or bottom marketing savings summaries ("UDZIELONO RABATU", "ŁĄCZNY RABAT", "OSZCZĘDZASZ", "SUMA RABATÓW" printed near/below SUMA PLN).
   - Include bottle/packaging deposits ("KAUCJA", "OPŁATA KAUCYJNA", "BUTELKA ZWROTNA", "STATIEGELD") as line items.
6. POLISH LINE ITEM FORMATTING, MULTI-LINE ITEMS, UNITS & DISCOUNTS:
   - Polish fiscal printers often split one item across 2 lines: line 1 has the raw product name, line 2 has "quantity * unit_price = total_price [PTU_LETTER]" (e.g. "0,685 kg * 6,99  4,79 C" or "2 szt. x 3,50  7,00 A"). Merge them into ONE item.
   - Convert Polish comma decimals ("12,99", "0,685") to standard JSON floats (12.99, 0.685).
   - Strip the trailing fiscal VAT/PTU tax letter ("A", "B", "C", "D", "E", "G") attached to prices or line endings. Keep genuine product letters (e.g. "JAJA M 10", "WITAMINA C").
   - "unit": Must be strictly one of "pcs", "kg", or "l":
     * "kg" ONLY when sold by weight in kilograms (e.g. "0,685 kg x 6,99", "LUZ", "WAGA").
     * "l" ONLY when sold loose by volume in liters (e.g. "15,40 l x 6,39").
     * "pcs" for all packaged items sold per piece/pack ("szt", "op", e.g. 1 bottle of "MLEKO 1L" bought as "1 x 4,49" has quantity=1.0 and unit="pcs").
   - Per-item discounts ("Rabat", "Opust", "Lidl Plus rabat", "Promocja"):
     * Make sure the sum of "total_price" across all items equals "total_amount" ("SUMA PLN"). Never subtract the same discount twice.
     * If an item shows original price (e.g. 12.99) followed by a "Rabat -3.00" line (final 9.99), emit the item with total_price=12.99 AND a separate discount item (name="RABAT <item>", quantity=1.0, unit="pcs", unit_price=-3.00, total_price=-3.00).
   - Leave "clean_name" as "" and "subcategory" as null (Stage 2 handles classification).

Required JSON structure:
{
  "store_name": "Biedronka",
  "transaction_date": "YYYY-MM-DD",
  "total_amount": 0.00,
  "currency": "PLN",
  "items": [
    {
      "name": "EXACT RAW ITEM NAME",
      "clean_name": "",
      "subcategory": null,
      "unit": "pcs",
      "quantity": 1.0,
      "unit_price": 0.00,
      "total_price": 0.00
    }
  ]
}"""


def build_stage_2_classifier_prompt(
    subcategories: list[str] | None = None,
    language: str = "pl",
) -> str:
    """Build the system prompt for Stage 2 (classifying unknown receipt items with FTS5 candidates)."""
    allowed_subcats = subcategories or taxonomy_repo.get_active_subcategory_codes()
    subcats_formatted = ", ".join(f'"{s}"' for s in allowed_subcats)
    lang_map = {
        "en": "English",
        "pl": "Polish",
    }
    lang_desc = lang_map.get(language.strip().lower(), "Polish")

    return (
        "You are a grocery and retail product normalizer and catalog classifier (specialized in Polish and European receipts).\n"
        f"Preferred user display language: {lang_desc} (`{language.strip().lower()}`).\n"
        "You will receive a JSON object `{\"store_name\": ..., \"items\": [...]}` containing ONLY receipt items not yet in our alias cache.\n"
        "Each input item has `idx`, `name` (raw receipt abbreviation), `unit`, and `candidates` (existing catalog products with `product_id`, `name_pl`, `name_en`, `subcategory`).\n\n"
        "Return ONLY pure JSON (no markdown fences, no commentary) with structure `{\"items\": [...]}` containing one object per input item with:\n"
        "1. `idx`: Exact integer `idx` from the input item.\n"
        "2. `matched_product_id`: If one of `candidates` is the EXACT same generic product concept (e.g. receipt 'MLEKO LACIATE 3,2% 1L' matches candidate 'mleko 3.2%' / 'milk 3.2%', or 'JAJA MOJA KURKA M 10' matches candidate 'jajka' / 'eggs'), set `matched_product_id` to that candidate's integer `product_id`. Otherwise set `null`.\n"
        "3. `name_pl`: Concise, everyday generic product name in Polish (lowercase, NO brand name, NO package weight/count — e.g. 'jajka', 'ser żółty', 'płatki owsiane', 'pierś z kurczaka', 'mleko 3.2%', 'twaróg półtłusty', 'kaucja'). Keep fat % only when nutritionally distinct (like milk/cream).\n"
        "4. `name_en`: Concise, everyday generic product name in English (lowercase, NO brand name, NO package weight/count — e.g. 'eggs', 'yellow cheese', 'rolled oats', 'chicken breast', 'milk 3.2%', 'semi-fat quark', 'deposit').\n"
        f"5. `clean_name`: Set equal to `name_pl` if user language is Polish, or `name_en` if English.\n"
        f"6. `subcategory`: Choose strictly ONE from [{subcats_formatted}] (or `null` only if the line is a discount).\n"
        "7. `brand`: Decoded brand name from the raw receipt text if recognizable (e.g. 'Moja Kurka', 'Łaciate', 'Piątnica', 'Pilos', 'Krakus', 'Tymbark'), otherwise `null` (e.g. for loose fruits/vegetables/bread).\n"
        "8. `off_search_query`: Expanded, human-readable Polish/original product query combining brand + specific product + variant/pack size for searching Open Food Facts later (e.g. 'Moja Kurka jaja M 10 szt', 'Łaciate mleko 3.2% 1L', 'Piątnica serek wiejski 200g'), or `null` for unbranded loose produce / deposits.\n"
        "9. `pack_amount`: Numeric net size of 1 package if visible in raw name (converted to base unit: e.g. '500G' -> 0.5, '1L' -> 1.0, '250ML' -> 0.25, '10SZT' -> 10.0), otherwise `null`.\n"
        "10. `pack_unit`: `'kg'`, `'l'`, or `'pcs'` matching `pack_amount`, otherwise `null`."
    )


def normalize_store_name(name: str | None) -> str:
    """Normalize a store name to Title Case while preserving Polish characters and apostrophes."""
    if not name:
        return "Unknown Store"
    return " ".join(word.capitalize() for word in name.strip().split())


def sanitize_slug(text: str) -> str:
    """Sanitize a string into a filesystem-safe slug."""
    folded = catalog_repo.fold_polish_ascii(text)
    normalized = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
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
    if not result.store_name or result.store_name.strip().lower() == "unknown store":
        result.store_name = "Unknown Store"
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
    """Stage 1: Extract receipt header and raw items (with ``unit`` and empty ``clean_name`` / ``subcategory``)."""
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

    for item in raw_data.get("items", []):
        if isinstance(item, dict):
            item["clean_name"] = ""
            item["subcategory"] = None
            item.setdefault("unit", "pcs")

    return raw_data


def classify_receipt_items(
    raw_ocr_data: dict[str, Any],
    subcategories: list[str] | None = None,
    language: str = "pl",
    provider: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Stage 2: Classify unknown receipt items using the text classifier model."""
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


def _build_subcategory_to_category_map(
    database_path: str | Path | None = None,
) -> dict[str, str]:
    """Build a lookup map ``{subcategory_code: category_code}`` from active taxonomy."""
    try:
        subs = taxonomy_repo.list_subcategories(only_active=False, database_path=database_path)
        return {s["code"].lower(): s["category_code"] for s in subs}
    except Exception:
        return {}


def commit_result_to_catalog(
    result: ReceiptOCRResult,
    source: str = "llm",
    database_path: str | Path | None = None,
) -> ReceiptOCRResult:
    """Persist new products & store item aliases (or increment hit counts) for a confirmed receipt."""
    try:
        store = catalog_repo.resolve_store(
            result.store_name, auto_create=True, database_path=database_path
        )
    except Exception:
        logger.exception("[commit_result_to_catalog] Could not resolve store '%s'", result.store_name)
        return result

    store_id = int(store["id"]) if store else None
    if store:
        result.store_id = store_id
        result.store_name = store["display_name"]

    subcat_to_cat = _build_subcategory_to_category_map(database_path=database_path)

    for item in result.items:
        if float(item.total_price) < 0 or float(item.unit_price) < 0:
            continue

        # Already matched from cache and untouched -> increment hit counter
        if item.match_source == "cache" and item.product_id:
            catalog_repo.lookup_alias(
                item.name,
                store_id=store_id,
                increment_hit=True,
                database_path=database_path,
            )
            continue

        item_source = "user" if item.match_source == "user" else source
        item_status = "confirmed" if item_source in ("user", "admin") else "auto"

        product = None
        if item.product_id and item_source != "user":
            product = catalog_repo.get_product_by_id(item.product_id, database_path=database_path)

        if product is None:
            fallback_clean = (item.clean_name or item.name).strip().lower()
            name_pl = (item.name_pl or fallback_clean).strip().lower()
            name_en = (item.name_en or fallback_clean).strip().lower()
            if not name_pl or not name_en:
                continue
            product = catalog_repo.create_or_get_product(
                name_pl=name_pl,
                name_en=name_en,
                subcategory_code=item.subcategory,
                default_unit=item.unit,
                status=item_status,
                source=item_source,
                database_path=database_path,
            )

        alias = catalog_repo.upsert_alias(
            raw_name=item.name,
            product_id=int(product["id"]),
            store_id=store_id,
            brand=item.brand,
            off_search_query=item.off_search_query,
            pack_amount=item.pack_amount,
            pack_unit=item.pack_unit,
            source=item_source,
            status=item_status,
            database_path=database_path,
        )
        item.product_id = int(product["id"])
        item.name_pl = product["name_pl"]
        item.name_en = product["name_en"]
        if product.get("subcategory_code"):
            item.subcategory = product["subcategory_code"]
        if item.subcategory:
            item.category = subcat_to_cat.get(item.subcategory.lower()) or product.get(
                "category_code"
            )
        if alias.get("off_search_query") and not item.off_search_query:
            item.off_search_query = alias["off_search_query"]

    return result


def analyze_receipt_image(
    content: bytes,
    content_type: str = "image/jpeg",
    provider: str | None = None,
    model: str | None = None,
    classifier_provider: str | None = None,
    classifier_model: str | None = None,
    subcategories: list[str] | None = None,
    default_currency: str = "PLN",
    language: str = "pl",
    persist_catalog: bool = True,
    database_path: str | Path | None = None,
    timeout: int | None = None,
) -> ReceiptOCRResult:
    """Run Stage 1 Vision OCR -> Catalog Alias Cache -> Stage 2 Classifier (only for misses)."""
    lang = "pl" if language.strip().lower() == "pl" else "en"

    # 1. Stage 1: Vision OCR
    stage1_json = extract_raw_receipt_ocr(
        content=content,
        content_type=content_type,
        provider=provider,
        model=model,
        timeout=timeout,
    )
    if not stage1_json.get("currency"):
        stage1_json["currency"] = default_currency

    raw_store_name = stage1_json.get("store_name") or "Unknown Store"
    store_record = None
    try:
        store_record = catalog_repo.resolve_store(
            raw_store_name, auto_create=False, database_path=database_path
        )
    except Exception:
        store_record = None

    store_id = int(store_record["id"]) if store_record else None
    resolved_store_name = (
        store_record["display_name"] if store_record else normalize_store_name(raw_store_name)
    )
    subcat_to_cat = _build_subcategory_to_category_map(database_path=database_path)

    raw_items: list[dict[str, Any]] = [
        dict(it) for it in stage1_json.get("items", []) if isinstance(it, dict)
    ]
    enriched_items: list[dict[str, Any]] = []
    unknown_for_stage2: list[dict[str, Any]] = []
    cache_hits = 0

    # 2. Check Discounts Rule & Catalog Alias Cache before calling Stage 2
    for idx, item in enumerate(raw_items):
        total_price = float(item.get("total_price") or 0.0)
        unit_price = float(item.get("unit_price") or 0.0)
        raw_name = str(item.get("name") or "").strip()

        if total_price < 0 or unit_price < 0:
            item["clean_name"] = "Rabat" if lang == "pl" else "Discount"
            item["name_pl"] = "Rabat"
            item["name_en"] = "Discount"
            item["subcategory"] = None
            item["category"] = None
            item["match_source"] = "rule"
            enriched_items.append(item)
            continue

        cached = None
        try:
            cached = catalog_repo.lookup_alias(
                raw_name,
                store_id=store_id,
                increment_hit=False,
                database_path=database_path,
            )
        except Exception:
            cached = None

        if cached is not None:
            cache_hits += 1
            item["product_id"] = int(cached["product_id"])
            item["name_pl"] = cached["name_pl"]
            item["name_en"] = cached["name_en"]
            item["clean_name"] = cached["name_pl"] if lang == "pl" else cached["name_en"]
            item["subcategory"] = cached["subcategory_code"]
            item["category"] = cached["category_code"]
            item["brand"] = cached.get("brand")
            item["off_search_query"] = cached.get("off_search_query")
            item["pack_amount"] = cached.get("pack_amount")
            item["pack_unit"] = cached.get("pack_unit")
            item["match_source"] = "cache"
            enriched_items.append(item)
            continue

        candidates_raw: list[dict[str, Any]] = []
        try:
            fts_matches = catalog_repo.search_products_fts(
                raw_name, limit=5, database_path=database_path
            )
            candidates_raw = [
                {
                    "product_id": int(p["id"]),
                    "name_pl": p["name_pl"],
                    "name_en": p["name_en"],
                    "subcategory": p.get("subcategory_code"),
                }
                for p in fts_matches
            ]
        except Exception:
            candidates_raw = []

        unknown_for_stage2.append(
            {
                "idx": idx,
                "name": raw_name,
                "unit": item.get("unit", "pcs"),
                "quantity": item.get("quantity", 1.0),
                "unit_price": unit_price,
                "total_price": total_price,
                "candidates": candidates_raw,
            }
        )
        enriched_items.append(item)

    # 3. Stage 2: Call Text Classifier ONLY if there are unknown items
    llm_classified_count = 0
    if unknown_for_stage2:
        logger.info(
            "[analyze_receipt_image] Cache hits=%d, sending %d unknown item(s) to Stage 2 Classifier",
            cache_hits,
            len(unknown_for_stage2),
        )
        stage2_input = {
            "store_name": resolved_store_name,
            "items": unknown_for_stage2,
        }
        stage2_output = classify_receipt_items(
            raw_ocr_data=stage2_input,
            subcategories=subcategories,
            language=lang,
            provider=classifier_provider or provider,
            model=classifier_model,
            timeout=timeout,
        )
        classified_list = stage2_output.get("items", []) if isinstance(stage2_output, dict) else []

        by_idx: dict[int, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for pos, cls_item in enumerate(classified_list):
            if not isinstance(cls_item, dict):
                continue
            if "idx" in cls_item and isinstance(cls_item["idx"], int):
                by_idx[cls_item["idx"]] = cls_item
            elif pos < len(unknown_for_stage2):
                # Fallback for positional/legacy responses lacking 'idx'
                if cls_item.get("name"):
                    by_name[str(cls_item["name"]).strip().upper()] = cls_item
                else:
                    by_idx[unknown_for_stage2[pos]["idx"]] = cls_item

        for unk in unknown_for_stage2:
            target_idx = unk["idx"]
            target_item = enriched_items[target_idx]
            cls_data = by_idx.get(target_idx) or by_name.get(unk["name"].upper()) or {}

            matched_pid = cls_data.get("matched_product_id")
            matched_product = None
            if isinstance(matched_pid, int):
                try:
                    matched_product = catalog_repo.get_product_by_id(
                        matched_pid, database_path=database_path
                    )
                except Exception:
                    matched_product = None

            if matched_product is not None:
                name_pl = matched_product["name_pl"]
                name_en = matched_product["name_en"]
                subcat = matched_product.get("subcategory_code") or cls_data.get("subcategory")
                target_item["product_id"] = int(matched_product["id"])
            else:
                fallback_clean = str(cls_data.get("clean_name") or unk["name"]).strip().lower()
                name_pl = str(cls_data.get("name_pl") or fallback_clean).strip().lower()
                name_en = str(cls_data.get("name_en") or fallback_clean).strip().lower()
                subcat = cls_data.get("subcategory")

            target_item["name_pl"] = name_pl
            target_item["name_en"] = name_en
            target_item["clean_name"] = name_pl if lang == "pl" else name_en
            target_item["subcategory"] = subcat
            target_item["category"] = (
                subcat_to_cat.get(str(subcat).lower()) if subcat else None
            )
            target_item["brand"] = cls_data.get("brand")
            target_item["off_search_query"] = cls_data.get("off_search_query")
            target_item["pack_amount"] = (
                float(cls_data["pack_amount"])
                if isinstance(cls_data.get("pack_amount"), (int, float))
                else None
            )
            target_item["pack_unit"] = cls_data.get("pack_unit")
            target_item["match_source"] = "llm"
            llm_classified_count += 1
    else:
        logger.info(
            "[analyze_receipt_image] 100%% cache/rule hit (%d cached) — Stage 2 Classifier skipped!",
            cache_hits,
        )

    final_payload = {
        "store_id": store_id,
        "store_name": resolved_store_name,
        "transaction_date": stage1_json.get("transaction_date"),
        "total_amount": stage1_json.get("total_amount", 0.0),
        "currency": stage1_json.get("currency") or default_currency,
        "confidence": stage1_json.get("confidence"),
        "cache_hits": cache_hits,
        "llm_classified_count": llm_classified_count,
        "items": enriched_items,
    }
    validated = validate_ocr_result(final_payload)

    if persist_catalog:
        validated = commit_result_to_catalog(validated, source="llm", database_path=database_path)

    return validated
