"""Unit tests for Cloud Vision OCR & Product Classification Engine."""

from unittest.mock import MagicMock

import pytest

from ocr_hub import config
from ocr_hub.services import ocr_engine


SAMPLE_LLM_RESPONSE = {
    "store_name": "ALBERT HEIJN",
    "transaction_date": "2026-10-22",
    "total_amount": 6.45,
    "currency": "EUR",
    "confidence": 0.96,
    "items": [
        {
            "name": "AH HAVERMOUT",
            "clean_name": "płatki owsiane",
            "category": "FOOD",
            "subcategory": "produkty zbożowe",
            "quantity": 1.0,
            "unit_price": 0.75,
            "total_price": 0.75,
            "confidence": 0.98,
        },
        {
            "name": "PLAK JONG GVP",
            "clean_name": "ser żółty",
            "category": "FOOD",
            "subcategory": "nabiał",
            "quantity": 2.0,
            "unit_price": 3.00,
            "total_price": 6.00,
            "confidence": 0.95,
        },
        {
            "name": "BONUS AH JONG",
            "clean_name": "Rabat",
            "category": "FOOD",
            "subcategory": None,
            "quantity": 1.0,
            "unit_price": -0.30,
            "total_price": -0.30,
            "confidence": 0.99,
        },
    ],
}


def test_build_ocr_system_prompt_includes_subcategories() -> None:
    prompt = ocr_engine.build_ocr_system_prompt(
        subcategories=["nabiał", "warzywa"],
        default_currency="EUR",
        language="pl",
    )
    assert '"nabiał"' in prompt
    assert '"warzywa"' in prompt
    assert "EUR" in prompt


def test_analyze_receipt_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-123")
    import json

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": f"```json\n{json.dumps(SAMPLE_LLM_RESPONSE)}\n```"
                }
            }
        ]
    }
    fake_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("ocr_hub.services.ocr_engine.requests.post", lambda *a, **kw: fake_resp)

    result = ocr_engine.analyze_receipt_image(
        content=b"fake-image-bytes",
        content_type="image/jpeg",
        provider="openai",
        model="gpt-4o-mini",
    )
    assert result.store_name == "Albert Heijn"
    assert result.total_amount == 6.45
    assert result.currency == "EUR"
    assert len(result.items) == 3
    assert result.items[0].clean_name == "płatki owsiane"
    assert result.items[0].subcategory == "produkty zbożowe"
    assert result.items[2].clean_name == "Rabat"
    assert result.items[2].subcategory is None
    assert result.items[2].total_price == -0.30


def test_analyze_receipt_gemini_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-test-key")
    import json

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(SAMPLE_LLM_RESPONSE)}]
                }
            }
        ]
    }
    fake_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("ocr_hub.services.ocr_engine.requests.post", lambda *a, **kw: fake_resp)

    result = ocr_engine.analyze_receipt_image(
        content=b"fake-image-bytes",
        content_type="image/png",
        provider="gemini",
        model="gemini-2.5-flash",
    )
    assert result.store_name == "Albert Heijn"
    assert len(result.items) == 3
