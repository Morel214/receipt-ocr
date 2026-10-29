"""Unit tests for the Two-Stage Receipt OCR & Product Classification Engine."""

import json
from unittest.mock import MagicMock

import pytest

from ocr_hub import config
from ocr_hub.services import ocr_engine

STAGE_1_RAW_RESPONSE = {
    "store_name": "ALBERT HEIJN",
    "transaction_date": "2026-10-22",
    "total_amount": 6.45,
    "currency": "EUR",
    "items": [
        {
            "name": "AH HAVERMOUT",
            "clean_name": "",
            "subcategory": None,
            "quantity": 1.0,
            "unit_price": 0.75,
            "total_price": 0.75,
        },
        {
            "name": "PLAK JONG GVP",
            "clean_name": "",
            "subcategory": None,
            "quantity": 2.0,
            "unit_price": 3.00,
            "total_price": 6.00,
        },
        {
            "name": "BONUS AH JONG",
            "clean_name": "",
            "subcategory": None,
            "quantity": 1.0,
            "unit_price": -0.30,
            "total_price": -0.30,
        },
    ],
}

STAGE_2_CLASSIFIED_RESPONSE = {
    "store_name": "ALBERT HEIJN",
    "transaction_date": "2026-10-22",
    "total_amount": 6.45,
    "currency": "EUR",
    "items": [
        {
            "name": "AH HAVERMOUT",
            "clean_name": "rolled oats",
            "subcategory": "grains",
            "quantity": 1.0,
            "unit_price": 0.75,
            "total_price": 0.75,
        },
        {
            "name": "PLAK JONG GVP",
            "clean_name": "yellow cheese",
            "subcategory": "dairy",
            "quantity": 2.0,
            "unit_price": 3.00,
            "total_price": 6.00,
        },
        {
            "name": "BONUS AH JONG",
            "clean_name": "Discount",
            "subcategory": None,
            "quantity": 1.0,
            "unit_price": -0.30,
            "total_price": -0.30,
        },
    ],
}


def test_stage_1_and_stage_2_prompts() -> None:
    assert '"clean_name": ""' in ocr_engine.STAGE_1_OCR_PROMPT
    assert '"subcategory": null' in ocr_engine.STAGE_1_OCR_PROMPT

    stage2_prompt = ocr_engine.build_stage_2_classifier_prompt(
        subcategories=["dairy", "grains"],
        language="en",
    )
    assert '"dairy"' in stage2_prompt
    assert '"grains"' in stage2_prompt


def test_two_stage_pipeline_with_distinct_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "deepseek-key")

    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "generativelanguage.googleapis.com" in url:
            # Stage 1 (Gemini Vision OCR)
            resp.json.return_value = {
                "candidates": [
                    {"content": {"parts": [{"text": json_module.dumps(STAGE_1_RAW_RESPONSE)}]}}
                ]
            }
        else:
            # Stage 2 (DeepSeek Text Classifier)
            resp.json.return_value = {
                "choices": [
                    {"message": {"content": json_module.dumps(STAGE_2_CLASSIFIED_RESPONSE)}}
                ]
            }
        return resp

    import json as json_module

    monkeypatch.setattr("ocr_hub.services.ocr_engine.requests.post", fake_post)

    result = ocr_engine.analyze_receipt_image(
        content=b"fake-image-bytes",
        content_type="image/jpeg",
        provider="gemini",
        model="gemini-2.5-flash",
        classifier_provider="deepseek",
        classifier_model="deepseek-chat",
        language="en",
        persist_catalog=False,
    )

    assert len(calls) == 2
    assert "gemini-2.5-flash" in calls[0]["url"]
    assert calls[1]["json"]["model"] == "deepseek-chat"

    assert result.store_name == "Albert Heijn"
    assert result.total_amount == 6.45
    assert result.currency == "EUR"
    assert len(result.items) == 3
    assert result.items[0].clean_name == "rolled oats"
    assert result.items[0].subcategory == "grains"
    assert result.items[1].clean_name == "yellow cheese"
    assert result.items[1].subcategory == "dairy"
    assert result.items[2].clean_name == "Discount"
    assert result.items[2].subcategory is None
    assert result.items[2].total_price == -0.30
