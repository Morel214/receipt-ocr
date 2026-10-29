"""Tests for Phase 3: Polish Stage 1 Vision prompt, cache-first Stage 2 bypass, FTS5 candidates, and queue commit."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ocr_hub import config
from ocr_hub.repositories import catalog_repo, jobs_repo, tenants_repo
from ocr_hub.services import ocr_engine, queue_service


def test_polish_stage1_prompt_includes_fiscal_rules_and_unit() -> None:
    prompt = ocr_engine.STAGE_1_OCR_PROMPT
    assert "PARAGON FISKALNY" in prompt
    assert "JERONIMO MARTINS POLSKA" in prompt
    assert "UDZIELONO RABATU" in prompt
    assert '"unit": "pcs"' in prompt


def test_cache_first_pipeline_skips_stage2_on_second_scan_and_switches_language(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "d-key")

    stage1_polish_receipt = {
        "store_name": "JERONIMO MARTINS POLSKA S.A.",
        "transaction_date": "2026-10-28",
        "total_amount": 12.78,
        "currency": "PLN",
        "items": [
            {
                "name": "JAJA MOJA KURKA M 10",
                "clean_name": "",
                "subcategory": None,
                "unit": "pcs",
                "quantity": 1.0,
                "unit_price": 8.99,
                "total_price": 8.99,
            },
            {
                "name": "BANANY LUZ",
                "clean_name": "",
                "subcategory": None,
                "unit": "kg",
                "quantity": 0.685,
                "unit_price": 6.99,
                "total_price": 4.79,
            },
            {
                "name": "RABAT JAJA",
                "clean_name": "",
                "subcategory": None,
                "unit": "pcs",
                "quantity": 1.0,
                "unit_price": -1.00,
                "total_price": -1.00,
            },
        ],
    }

    stage2_calls: list[dict] = []
    stage1_calls = 0

    def fake_post(url, headers=None, json=None, timeout=None):
        nonlocal stage1_calls
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "generativelanguage.googleapis.com" in url:
            stage1_calls += 1
            resp.json.return_value = {
                "candidates": [
                    {"content": {"parts": [{"text": json_lib.dumps(stage1_polish_receipt)}]}}
                ]
            }
        else:
            user_input = json_lib.loads(json["messages"][1]["content"])
            stage2_calls.append(user_input)
            resp.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json_lib.dumps(
                                {
                                    "items": [
                                        {
                                            "idx": 0,
                                            "matched_product_id": None,
                                            "name_pl": "jajka",
                                            "name_en": "eggs",
                                            "clean_name": "jajka",
                                            "subcategory": "eggs",
                                            "brand": "Moja Kurka",
                                            "off_search_query": "Moja Kurka jaja M 10 szt",
                                            "pack_amount": 10.0,
                                            "pack_unit": "pcs",
                                        },
                                        {
                                            "idx": 1,
                                            "matched_product_id": None,
                                            "name_pl": "banany",
                                            "name_en": "bananas",
                                            "clean_name": "banany",
                                            "subcategory": "fruits",
                                            "brand": None,
                                            "off_search_query": None,
                                            "pack_amount": None,
                                            "pack_unit": None,
                                        },
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        return resp

    json_lib = json
    monkeypatch.setattr("ocr_hub.services.ocr_engine.requests.post", fake_post)

    # First scan (Polish user) -> 1 Stage 1 call + 1 Stage 2 call (only 2 positive items sent; discount handled by rule)
    first = ocr_engine.analyze_receipt_image(
        content=b"img1",
        provider="gemini",
        model="gemini-2.5-flash",
        classifier_provider="deepseek",
        classifier_model="deepseek-chat",
        language="pl",
        persist_catalog=True,
        database_path=temp_db,
    )
    assert stage1_calls == 1
    assert len(stage2_calls) == 1
    assert len(stage2_calls[0]["items"]) == 2  # Discount item (-1.00) bypassed Stage 2
    assert first.store_name == "Biedronka"
    assert first.cache_hits == 0
    assert first.llm_classified_count == 2
    assert first.items[0].clean_name == "jajka"
    assert first.items[0].category == "FOOD"
    assert first.items[0].subcategory == "eggs"
    assert first.items[0].off_search_query == "Moja Kurka jaja M 10 szt"
    assert first.items[1].unit == "kg"
    assert first.items[1].clean_name == "banany"
    assert first.items[2].clean_name == "Rabat"
    assert first.items[2].match_source == "rule"

    # Second scan (English user!) -> 100% cache hit -> ZERO Stage 2 calls, English names returned automatically!
    second = ocr_engine.analyze_receipt_image(
        content=b"img2",
        provider="gemini",
        model="gemini-2.5-flash",
        classifier_provider="deepseek",
        classifier_model="deepseek-chat",
        language="en",
        persist_catalog=True,
        database_path=temp_db,
    )
    assert stage1_calls == 2
    assert len(stage2_calls) == 1  # Still 1! Stage 2 was NOT invoked at all!
    assert second.cache_hits == 2
    assert second.llm_classified_count == 0
    assert second.items[0].clean_name == "eggs"
    assert second.items[0].match_source == "cache"
    assert second.items[1].clean_name == "bananas"
    assert second.items[2].clean_name == "Discount"


def test_partial_cache_passes_fts5_candidates_and_queue_commits_only_on_confirm(
    temp_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "d-key")

    # Seed 1 existing product ('jajka' / 'eggs') + 1 Biedronka alias
    biedronka = catalog_repo.resolve_store("Biedronka", database_path=temp_db)
    assert biedronka is not None
    eggs = catalog_repo.create_or_get_product(
        name_pl="jajka",
        name_en="eggs",
        subcategory_code="eggs",
        database_path=temp_db,
    )
    catalog_repo.upsert_alias(
        raw_name="JAJA MOJA KURKA M 10",
        product_id=eggs["id"],
        store_id=biedronka["id"],
        database_path=temp_db,
    )

    stage1_data = {
        "store_name": "Biedronka",
        "transaction_date": "2026-10-29",
        "total_amount": 18.98,
        "currency": "PLN",
        "items": [
            {
                "name": "JAJA MOJA KURKA M 10",
                "unit": "pcs",
                "quantity": 1.0,
                "unit_price": 8.99,
                "total_price": 8.99,
            },
            {
                "name": "JAJKA WIEJSKIE L 10SZT",
                "unit": "pcs",
                "quantity": 1.0,
                "unit_price": 9.99,
                "total_price": 9.99,
            },
        ],
    }

    captured_stage2_inputs: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "generativelanguage.googleapis.com" in url:
            resp.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": json_lib.dumps(stage1_data)}]}}]
            }
        else:
            s2_in = json_lib.loads(json["messages"][1]["content"])
            captured_stage2_inputs.append(s2_in)
            resp.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json_lib.dumps(
                                {
                                    "items": [
                                        {
                                            "idx": 1,
                                            "matched_product_id": eggs["id"],
                                            "name_pl": "jajka",
                                            "name_en": "eggs",
                                            "clean_name": "jajka",
                                            "subcategory": "eggs",
                                            "brand": None,
                                            "off_search_query": "Jajka wiejskie L 10 szt",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        return resp

    json_lib = json
    monkeypatch.setattr("ocr_hub.services.ocr_engine.requests.post", fake_post)

    tenant = tenants_repo.create_tenant(
        name="QueueTester",
        language="pl",
        ocr_provider="gemini",
        ocr_model="gemini-2.5-flash",
        classifier_provider="deepseek",
        classifier_model="deepseek-chat",
        database_path=temp_db,
    )
    img = tmp_path / "r1.jpg"
    img.write_bytes(b"jpg")
    job_id = jobs_repo.create_job(
        tenant_id=tenant["id"],
        batch_id="b1",
        chat_id="99",
        message_id=1,
        filename="r1.jpg",
        image_path=str(img),
        database_path=temp_db,
    )

    # Preview step (process_batch) -> runs with persist_catalog=False!
    queue_service.process_batch(tenant_id=tenant["id"], batch_id="b1", database_path=temp_db)
    assert len(captured_stage2_inputs) == 1
    # Only item idx=1 ('JAJKA WIEJSKIE L 10SZT') was sent to Stage 2, WITH 'jajka' in its FTS5 candidates!
    assert len(captured_stage2_inputs[0]["items"]) == 1
    sent_item = captured_stage2_inputs[0]["items"][0]
    assert sent_item["name"] == "JAJKA WIEJSKIE L 10SZT"
    assert any(c["product_id"] == eggs["id"] for c in sent_item["candidates"])

    # Before /confirm, the new alias 'JAJKA WIEJSKIE L 10SZT' is NOT yet saved in product_aliases!
    assert (
        catalog_repo.lookup_alias(
            "JAJKA WIEJSKIE L 10SZT", store_id=biedronka["id"], database_path=temp_db
        )
        is None
    )

    # Upon /confirm, the alias is committed to the shared catalog without creating a duplicate product!
    queue_service.confirm_job(tenant_id=tenant["id"], job_id=job_id, database_path=temp_db)
    saved_alias = catalog_repo.lookup_alias(
        "JAJKA WIEJSKIE L 10SZT", store_id=biedronka["id"], database_path=temp_db
    )
    assert saved_alias is not None
    assert saved_alias["product_id"] == eggs["id"]
    assert catalog_repo.get_catalog_stats(temp_db)["products_total"] == 1
