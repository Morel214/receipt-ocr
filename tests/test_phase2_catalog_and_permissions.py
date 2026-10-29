"""Tests for Phase 2: Shared Product & Store Catalog, FTS5 search, and Taxonomy manual_user permissions."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from ocr_hub import config
from ocr_hub.repositories import catalog_repo, taxonomy_repo
from ocr_hub.services import ocr_engine


def test_taxonomy_guest_vs_admin_permissions_and_manual_user_approval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_headers = {"X-Admin-Key": "test-admin-secret"}

    # 1. Guest without Admin Key CANNOT edit, disable, or delete existing subcategories
    dairy = taxonomy_repo.get_subcategory_by_code("dairy")
    assert dairy is not None

    assert client.put(
        f"/api/taxonomy/subcategories/{dairy['id']}",
        json={"is_active": False},
    ).status_code == 403
    assert client.delete(f"/api/taxonomy/subcategories/{dairy['id']}").status_code == 403

    # Even if ADMIN_API_KEY is empty in .env, guest edits/deletes remain locked
    monkeypatch.setattr(config, "ADMIN_API_KEY", "")
    assert client.put(
        f"/api/taxonomy/subcategories/{dairy['id']}",
        json={"is_active": False},
    ).status_code == 403
    monkeypatch.setattr(config, "ADMIN_API_KEY", "test-admin-secret")

    # 2. Guest adding category + subcategory -> saved as pending manual_user (NOT active!)
    guest_cat_resp = client.post(
        "/api/taxonomy/categories",
        json={"code": "garden", "name_pl": "Ogród", "name_en": "Garden"},
    )
    assert guest_cat_resp.status_code == 201
    guest_cat = guest_cat_resp.json()
    assert guest_cat["status"] == "pending"
    assert guest_cat["source"] == "manual_user"
    assert guest_cat["is_active"] is False

    guest_sub_resp = client.post(
        "/api/taxonomy/subcategories",
        json={
            "category_id": guest_cat["id"],
            "code": "plants",
            "name_pl": "rośliny",
            "name_en": "plants",
        },
    )
    assert guest_sub_resp.status_code == 201
    guest_sub = guest_sub_resp.json()
    assert guest_sub["status"] == "pending"
    assert guest_sub["source"] == "manual_user"
    assert guest_sub["is_active"] is False

    # Unapproved manual_user items must NOT enter active taxonomy or Stage 2 prompt
    public_tax = client.get("/api/taxonomy?include_inactive=true").json()
    assert "GARDEN" not in [c["code"] for c in public_tax["categories"]]
    assert "plants" not in public_tax["active_subcategory_codes"]
    assert '"plants"' not in ocr_engine.build_stage_2_classifier_prompt(language="pl")

    # 3. Admin sees pending queue and approves both -> now active!
    pending = client.get("/api/taxonomy/pending", headers=admin_headers).json()
    assert any(c["code"] == "GARDEN" for c in pending["categories"])
    assert any(s["code"] == "plants" for s in pending["subcategories"])

    assert (
        client.post(
            f"/api/taxonomy/categories/{guest_cat['id']}/approve",
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/taxonomy/subcategories/{guest_sub['id']}/approve",
            headers=admin_headers,
        ).status_code
        == 200
    )

    after_approve = client.get("/api/taxonomy").json()
    assert "GARDEN" in [c["code"] for c in after_approve["categories"]]
    assert "plants" in after_approve["active_subcategory_codes"]
    assert '"plants"' in ocr_engine.build_stage_2_classifier_prompt(language="pl")


def test_polish_normalization_and_store_resolution(temp_db: Path) -> None:
    assert (
        catalog_repo.fold_polish_ascii("Łaciate twaróg półtłusty żółty")
        == "Laciate twarog poltlusty zolty"
    )
    assert (
        catalog_repo.normalize_raw_item_name("MLEKO ŁACIATE 3,2% 1 L *C")
        == "MLEKO LACIATE 3.2% 1L"
    )
    assert (
        catalog_repo.normalize_raw_item_name("JAJA MOJA KURKA M 10 SZT.")
        == "JAJA MOJA KURKA M 10SZT"
    )
    assert catalog_repo.normalize_raw_item_name("WITAMINA C 1000MG") == "WITAMINA C 1000MG"

    biedronka = catalog_repo.resolve_store(
        "JERONIMO MARTINS POLSKA S.A. SKLEP NR 4122", database_path=temp_db
    )
    assert biedronka is not None
    assert biedronka["store_key"] == "biedronka"
    assert biedronka["display_name"] == "Biedronka"

    lidl = catalog_repo.resolve_store("LIDL SP. Z O.O. SP. K.", database_path=temp_db)
    assert lidl is not None and lidl["store_key"] == "lidl"

    zabka = catalog_repo.resolve_store("ŻABKA POLSKA SP. Z O.O. Z5120", database_path=temp_db)
    assert zabka is not None and zabka["store_key"] == "zabka"
    assert zabka["display_name"] == "Żabka"

    bakery = catalog_repo.resolve_store("Piekarnia Rzemieślnicza Ziarno", database_path=temp_db)
    assert bakery is not None
    assert bakery["store_key"] == "piekarnia_rzemieslnicza_ziarno"


def test_catalog_products_aliases_fts5_typos_and_merge(temp_db: Path) -> None:
    biedronka = catalog_repo.resolve_store("Biedronka", database_path=temp_db)
    lidl = catalog_repo.resolve_store("Lidl", database_path=temp_db)
    assert biedronka and lidl

    eggs = catalog_repo.create_or_get_product(
        name_pl="jajka",
        name_en="eggs",
        subcategory_code="eggs",
        default_unit="pcs",
        database_path=temp_db,
    )
    milk = catalog_repo.create_or_get_product(
        name_pl="mleko 3.2%",
        name_en="milk 3.2%",
        subcategory_code="dairy",
        default_unit="l",
        database_path=temp_db,
    )
    quark = catalog_repo.create_or_get_product(
        name_pl="twaróg półtłusty",
        name_en="semi-fat quark",
        subcategory_code="dairy",
        default_unit="kg",
        database_path=temp_db,
    )
    cheese = catalog_repo.create_or_get_product(
        name_pl="ser żółty",
        name_en="yellow cheese",
        subcategory_code="dairy",
        default_unit="kg",
        database_path=temp_db,
    )

    # Deduplication by normalized clean name
    dup_check = catalog_repo.create_or_get_product(
        name_pl="Mleko 3,2%",
        name_en="Milk 3.2%",
        subcategory_code="dairy",
        database_path=temp_db,
    )
    assert dup_check["id"] == milk["id"]

    # Dual-level alias: generic product ('jajka') + specific Open Food Facts query ('Moja Kurka jaja M 10 szt')
    catalog_repo.upsert_alias(
        raw_name="JAJA MOJA KURKA M 10 SZT.",
        product_id=eggs["id"],
        store_id=biedronka["id"],
        brand="Moja Kurka",
        off_search_query="Moja Kurka jaja M 10 szt",
        pack_amount=10.0,
        pack_unit="pcs",
        source="llm",
        status="auto",
        database_path=temp_db,
    )

    hit = catalog_repo.lookup_alias(
        "jaja moja kurka m 10szt",
        store_id=biedronka["id"],
        increment_hit=True,
        database_path=temp_db,
    )
    assert hit is not None
    assert hit["product_id"] == eggs["id"]
    assert hit["name_pl"] == "jajka"
    assert hit["name_en"] == "eggs"
    assert hit["subcategory_code"] == "eggs"
    assert hit["category_code"] == "FOOD"
    assert hit["brand"] == "Moja Kurka"
    assert hit["off_search_query"] == "Moja Kurka jaja M 10 szt"
    assert hit["hit_count"] == 2

    # Human-confirmed override cannot be overwritten by automatic LLM call
    catalog_repo.upsert_alias(
        raw_name="SER GOUDA PL 400G",
        product_id=cheese["id"],
        store_id=lidl["id"],
        source="user",
        status="confirmed",
        database_path=temp_db,
    )
    after_llm = catalog_repo.upsert_alias(
        raw_name="SER GOUDA PL 400G",
        product_id=quark["id"],
        store_id=lidl["id"],
        source="llm",
        status="auto",
        database_path=temp_db,
    )
    assert after_llm["product_id"] == cheese["id"]
    assert after_llm["alias_status"] == "confirmed"

    # Typo-tolerant FTS5 + subsequence search
    res_quark = catalog_repo.search_products_fts("twarug poltlusty 250g", database_path=temp_db)
    assert res_quark and res_quark[0]["id"] == quark["id"]

    res_milk = catalog_repo.search_products_fts("mlko", database_path=temp_db)
    assert any(p["id"] == milk["id"] for p in res_milk)

    # Merge duplicate product into canonical product
    eggs_dup = catalog_repo.create_or_get_product(
        name_pl="jaja kurze",
        name_en="hen eggs",
        subcategory_code="eggs",
        database_path=temp_db,
    )
    catalog_repo.upsert_alias(
        raw_name="JAJA ZLOTA NIOSKA L 10",
        product_id=eggs_dup["id"],
        store_id=lidl["id"],
        database_path=temp_db,
    )
    catalog_repo.merge_products(
        source_product_id=eggs_dup["id"],
        target_product_id=eggs["id"],
        database_path=temp_db,
    )
    assert catalog_repo.get_product_by_id(eggs_dup["id"], database_path=temp_db) is None
    repointed = catalog_repo.lookup_alias(
        "JAJA ZLOTA NIOSKA L 10", store_id=lidl["id"], database_path=temp_db
    )
    assert repointed is not None and repointed["product_id"] == eggs["id"]
