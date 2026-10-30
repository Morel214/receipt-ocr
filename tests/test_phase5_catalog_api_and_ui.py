"""Tests for Phase 5: /api/catalog/* REST endpoints, Web UI Catalog tab, permissions, Manual User Queue, and 1-click Merge."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from ocr_hub import config
from ocr_hub.db.models import ReceiptItem, ReceiptOCRResult
from ocr_hub.repositories import catalog_repo, receipts_repo
from ocr_hub.services import ocr_engine


def test_web_ui_renders_catalog_tab_and_seeded_stores_endpoint(client: TestClient) -> None:
    ui_resp = client.get("/")
    assert ui_resp.status_code == 200
    html = ui_resp.text

    # Top-level tabs & Catalog sub-views + modals
    assert "📦 Product Catalog" in html
    assert "🏷️ Global Taxonomy" in html
    assert "Products Browser" in html
    assert "Auto-LLM Review (Optional)" in html
    assert "Manual User Queue" in html
    assert "Receipt Aliases &amp; OFF Queries" in html
    assert 'id="editProductModal"' in html
    assert 'id="mergeProductModal"' in html
    assert 'id="aliasModal"' in html

    stores_resp = client.get("/api/catalog/stores")
    assert stores_resp.status_code == 200
    stores_data = stores_resp.json()
    assert stores_data["count"] >= 10
    display_names = {s["display_name"] for s in stores_data["stores"]}
    assert {"Biedronka", "Lidl", "Żabka", "Auchan", "Kaufland"}.issubset(display_names)


def test_guest_manual_user_queue_vs_strict_admin_permissions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = {"X-Admin-Key": "test-admin-secret"}

    # 1. Guest (no X-Admin-Key) submits a category, subcategory, and product
    guest_cat = client.post(
        "/api/taxonomy/categories",
        json={"code": "SUPPLEMENTS", "name_pl": "Suplementy", "name_en": "Supplements"},
    )
    assert guest_cat.status_code == 201
    assert guest_cat.json()["status"] == "pending"
    assert guest_cat.json()["source"] == "manual_user"

    # Find FOOD category id for subcategory submission
    tax_resp = client.get("/api/taxonomy")
    food_cat = next(c for c in tax_resp.json()["categories"] if c["code"] == "FOOD")

    guest_sub = client.post(
        "/api/taxonomy/subcategories",
        json={
            "category_id": food_cat["id"],
            "code": "fermented_dairy",
            "name_pl": "Nabiał fermentowany",
            "name_en": "Fermented dairy",
        },
    )
    assert guest_sub.status_code == 201
    assert guest_sub.json()["status"] == "pending"

    guest_prod_1 = client.post(
        "/api/catalog/products",
        json={
            "name_pl": "kefir naturalny",
            "name_en": "natural kefir",
            "subcategory_code": "dairy",
            "default_unit": "pcs",
        },
    )
    assert guest_prod_1.status_code == 201
    p1 = guest_prod_1.json()
    assert p1["status"] == "pending"
    assert p1["source"] == "manual_user"

    guest_prod_2 = client.post(
        "/api/catalog/products",
        json={
            "name_pl": "spam produkt testowy",
            "name_en": "spam test product",
            "subcategory_code": "other",
            "default_unit": "pcs",
        },
    )
    assert guest_prod_2.status_code == 201
    p2 = guest_prod_2.json()
    assert p2["status"] == "pending"

    # 2. Pending manual_user products are excluded from active catalog & FTS5 until approved
    public_list = client.get("/api/catalog/products?q=kefir")
    assert public_list.status_code == 200
    assert public_list.json()["count"] == 0
    assert catalog_repo.search_products_fts("kefir") == []

    stats = client.get("/api/catalog/stats").json()
    assert stats["products_active"] == 0
    assert stats["products_pending"] == 2
    assert stats["pending_taxonomy_count"] == 2
    assert stats["manual_user_pending_total"] == 4

    # 3. Guest cannot read manual-queue or mutate/approve/merge/delete products or aliases
    assert client.get("/api/catalog/manual-queue").status_code == 403
    assert (
        client.put(f"/api/catalog/products/{p1['id']}", json={"name_pl": "hack"}).status_code
        == 403
    )
    assert client.post(f"/api/catalog/products/{p1['id']}/approve").status_code == 403
    assert (
        client.post(
            f"/api/catalog/products/{p1['id']}/merge",
            json={"target_product_id": p2["id"]},
        ).status_code
        == 403
    )
    assert client.delete(f"/api/catalog/products/{p1['id']}").status_code == 403
    assert (
        client.post(
            "/api/catalog/aliases",
            json={"raw_name": "KEFIR 400G", "product_id": p1["id"]},
        ).status_code
        == 403
    )

    # Even if ADMIN_API_KEY env var were accidentally unset, strict catalog mutations stay locked (403)
    monkeypatch.setattr(config, "ADMIN_API_KEY", "")
    assert client.post(f"/api/catalog/products/{p1['id']}/approve").status_code == 403
    monkeypatch.setattr(config, "ADMIN_API_KEY", "test-admin-secret")

    # 4. Admin inspects /api/catalog/manual-queue, approves p1, and rejects p2
    mq_resp = client.get("/api/catalog/manual-queue", headers=admin_headers)
    assert mq_resp.status_code == 200
    mq = mq_resp.json()
    assert mq["total_pending"] == 4
    assert len(mq["categories"]) == 1
    assert len(mq["subcategories"]) == 1
    assert {p["id"] for p in mq["products"]} == {p1["id"], p2["id"]}

    approve_resp = client.post(
        f"/api/catalog/products/{p1['id']}/approve", headers=admin_headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "confirmed"

    reject_resp = client.delete(f"/api/catalog/products/{p2['id']}", headers=admin_headers)
    assert reject_resp.status_code == 200
    assert reject_resp.json()["deleted"] is True

    # Now kefir naturalny is active in public search and typo-tolerant FTS5!
    public_after = client.get("/api/catalog/products?q=kefir").json()
    assert public_after["count"] == 1
    assert public_after["products"][0]["name_pl"] == "kefir naturalny"
    assert public_after["products"][0]["status"] == "confirmed"

    fts_hits = catalog_repo.search_products_fts("kefr naturalny")
    assert any(h["id"] == p1["id"] for h in fts_hits)


def test_catalog_search_edit_alias_repoint_and_merge_update_live_ocr_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = {"X-Admin-Key": "test-admin-secret"}

    # Create a tenant for saving a historical Hub DB receipt
    bot_resp = client.post(
        "/api/bots",
        headers=admin_headers,
        json={
            "name": "DomingoCatalogUser",
            "language": "pl",
            "default_currency": "PLN",
            "delivery_modes": ["hub_db"],
        },
    )
    assert bot_resp.status_code == 201
    tenant = bot_resp.json()

    biedronka = catalog_repo.resolve_store("Biedronka", auto_create=False)
    lidl = catalog_repo.resolve_store("Lidl", auto_create=False)
    assert biedronka is not None and lidl is not None

    # Seed two duplicate 'auto' products learned from LLM + one distinct free-range egg product
    prod_a = catalog_repo.create_or_get_product(
        name_pl="jajka",
        name_en="eggs",
        subcategory_code="eggs",
        default_unit="pcs",
        status="auto",
        source="llm",
    )
    prod_b = catalog_repo.create_or_get_product(
        name_pl="jaja kurze",
        name_en="hen eggs",
        subcategory_code="dairy",
        default_unit="pcs",
        status="auto",
        source="llm",
    )
    prod_c_resp = client.post(
        "/api/catalog/products",
        headers=admin_headers,
        json={
            "name_pl": "jajka z wolnego wybiegu",
            "name_en": "free-range eggs",
            "subcategory_code": "eggs",
            "default_unit": "pcs",
        },
    )
    assert prod_c_resp.status_code == 201
    prod_c = prod_c_resp.json()
    assert prod_c["status"] == "confirmed"

    alias_biedr = catalog_repo.upsert_alias(
        raw_name="JAJA MOJA KURKA M 10",
        product_id=prod_a["id"],
        store_id=biedronka["id"],
        brand="Moja Kurka",
        off_search_query="Moja Kurka jaja M 10",
        source="llm",
        status="auto",
    )
    alias_lidl_1 = catalog_repo.upsert_alias(
        raw_name="JAJA WIEJSKIE L 10",
        product_id=prod_b["id"],
        store_id=lidl["id"],
        brand="Złota Nioska",
        off_search_query="Zlota Nioska jaja L 10",
        source="llm",
        status="auto",
    )
    alias_lidl_2 = catalog_repo.upsert_alias(
        raw_name="JAJA WOLNY WYBIEG 10SZT",
        product_id=prod_b["id"],
        store_id=lidl["id"],
        brand="Lidl",
        off_search_query="jaja wolny wybieg 10",
        source="llm",
        status="auto",
    )

    # Save a historical Hub DB receipt pointing to duplicate prod_b & alias_lidl_1 + alias_lidl_2
    saved_receipt = receipts_repo.save_confirmed_receipt(
        tenant_id=tenant["id"],
        result=ReceiptOCRResult(
            store_id=lidl["id"],
            store_name="Lidl",
            transaction_date="2026-10-29",
            total_amount=21.98,
            currency="PLN",
            items=[
                ReceiptItem(
                    name="JAJA WIEJSKIE L 10",
                    clean_name="jaja kurze",
                    name_pl="jaja kurze",
                    name_en="hen eggs",
                    product_id=prod_b["id"],
                    alias_id=alias_lidl_1["alias_id"],
                    category="FOOD",
                    subcategory="dairy",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=9.99,
                    total_price=9.99,
                    match_source="llm",
                ),
                ReceiptItem(
                    name="JAJA WOLNY WYBIEG 10SZT",
                    clean_name="jaja kurze",
                    name_pl="jaja kurze",
                    name_en="hen eggs",
                    product_id=prod_b["id"],
                    alias_id=alias_lidl_2["alias_id"],
                    category="FOOD",
                    subcategory="dairy",
                    unit="pcs",
                    quantity=1.0,
                    unit_price=11.99,
                    total_price=11.99,
                    match_source="llm",
                ),
            ],
        ),
        job_id=None,
    )

    # 1. Auto-LLM Review filter returns the two 'auto' products
    auto_list = client.get("/api/catalog/products?status=auto").json()
    assert {p["id"] for p in auto_list["products"]} == {prod_a["id"], prod_b["id"]}

    # 2. Searching products by linked store alias / brand ('moja kurka') ranks prod_a #1!
    brand_search = client.get("/api/catalog/products?q=moja kurka").json()
    assert brand_search["count"] >= 1
    assert brand_search["products"][0]["id"] == prod_a["id"]
    assert brand_search["products"][0]["alias_count"] == 1

    # 3. 1-Click Merge: merge duplicate prod_b INTO canonical prod_a
    merge_resp = client.post(
        f"/api/catalog/products/{prod_b['id']}/merge",
        headers=admin_headers,
        json={"target_product_id": prod_a["id"]},
    )
    assert merge_resp.status_code == 200
    merged_payload = merge_resp.json()
    assert merged_payload["removed_product_id"] == prod_b["id"]
    assert merged_payload["target_product_id"] == prod_a["id"]
    assert merged_payload["product"]["alias_count"] == 3

    # Verify prod_b no longer exists
    assert (
        client.put(
            f"/api/catalog/products/{prod_b['id']}",
            headers=admin_headers,
            json={"name_pl": "gone"},
        ).status_code
        == 404
    )

    # 4. Re-point alias_lidl_2 ('JAJA WOLNY WYBIEG 10SZT') to prod_c and enrich its OFF query
    alias_upd_resp = client.put(
        f"/api/catalog/aliases/{alias_lidl_2['alias_id']}",
        headers=admin_headers,
        json={
            "product_id": prod_c["id"],
            "brand": "Złota Nioska Bio",
            "off_search_query": "Zlota Nioska jaja wolny wybieg M 10 szt",
        },
    )
    assert alias_upd_resp.status_code == 200
    assert alias_upd_resp.json()["product_id"] == prod_c["id"]
    assert alias_upd_resp.json()["alias_status"] == "confirmed"

    # Historical Hub DB receipt items were automatically re-pointed: item 1 -> prod_a, item 2 -> prod_c!
    refreshed_receipt = receipts_repo.get_receipt(
        saved_receipt["id"], tenant_id=tenant["id"]
    )
    assert refreshed_receipt is not None
    item_pids = [it["product_id"] for it in refreshed_receipt["items"]]
    assert item_pids == [prod_a["id"], prod_c["id"]]

    # 5. Admin edits prod_a PL/EN names & confirms it via PUT /api/catalog/products/{id}
    edit_prod_resp = client.put(
        f"/api/catalog/products/{prod_a['id']}",
        headers=admin_headers,
        json={
            "name_pl": "jajka kurze",
            "name_en": "chicken eggs",
            "subcategory_code": "eggs",
        },
    )
    assert edit_prod_resp.status_code == 200
    assert edit_prod_resp.json()["status"] == "confirmed"
    assert edit_prod_resp.json()["name_pl"] == "jajka kurze"
    assert edit_prod_resp.json()["name_en"] == "chicken eggs"

    # Also confirm alias_biedr via POST /api/catalog/aliases/{id}/approve
    approve_alias_resp = client.post(
        f"/api/catalog/aliases/{alias_biedr['alias_id']}/approve",
        headers=admin_headers,
    )
    assert approve_alias_resp.status_code == 200
    assert approve_alias_resp.json()["alias_status"] == "confirmed"

    # 6. Next Lidl receipt scan hits 100% cache (0 Stage 2 LLM calls!) with updated names & OFF queries
    monkeypatch.setattr(
        ocr_engine,
        "_call_vision_model",
        lambda **kwargs: {
            "store_name": "Lidl sp. z o.o.",
            "transaction_date": "2026-10-30",
            "total_amount": 21.98,
            "currency": "PLN",
            "items": [
                {
                    "name": "JAJA WIEJSKIE L 10",
                    "unit": "pcs",
                    "quantity": 1.0,
                    "unit_price": 9.99,
                    "total_price": 9.99,
                },
                {
                    "name": "JAJA WOLNY WYBIEG 10SZT",
                    "unit": "pcs",
                    "quantity": 1.0,
                    "unit_price": 11.99,
                    "total_price": 11.99,
                },
            ],
        },
    )

    def _forbid_stage_2(**kwargs):
        raise AssertionError("Stage 2 LLM classifier should not run when all items hit cache!")

    monkeypatch.setattr(ocr_engine, "_call_text_classifier_model", _forbid_stage_2)

    pl_scan = ocr_engine.analyze_receipt_image(
        content=b"fake-lidl-receipt",
        language="pl",
        persist_catalog=True,
    )
    assert [it.match_source for it in pl_scan.items] == ["cache", "cache"]
    assert pl_scan.items[0].product_id == prod_a["id"]
    assert pl_scan.items[0].clean_name == "jajka kurze"
    assert pl_scan.items[0].name_en == "chicken eggs"
    assert pl_scan.items[0].subcategory == "eggs"
    assert pl_scan.items[0].category == "FOOD"

    assert pl_scan.items[1].product_id == prod_c["id"]
    assert pl_scan.items[1].clean_name == "jajka z wolnego wybiegu"
    assert pl_scan.items[1].off_search_query == "Zlota Nioska jaja wolny wybieg M 10 szt"

    # English user scanning the same items receives English clean_name from the same cache
    en_scan = ocr_engine.analyze_receipt_image(
        content=b"fake-lidl-receipt",
        language="en",
        persist_catalog=True,
    )
    assert [it.clean_name for it in en_scan.items] == ["chicken eggs", "free-range eggs"]

    # 7. Verify /api/catalog/stats reflects repeat cache hits & hit rate > 0%
    final_stats = client.get("/api/catalog/stats").json()
    assert final_stats["products_active"] == 2
    assert final_stats["products_confirmed"] == 2
    assert final_stats["products_auto"] == 0
    assert final_stats["aliases_total"] == 3
    assert final_stats["repeat_cache_hits"] == 4
    assert final_stats["cache_hit_rate_pct"] > 50.0
