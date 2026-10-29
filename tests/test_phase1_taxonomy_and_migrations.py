"""Tests for Phase 1: SQLite WAL, versioned migrations, global PL/EN taxonomy CRUD, and Web UI cleanup."""

from pathlib import Path

from fastapi.testclient import TestClient

from ocr_hub.db.connection import get_connection
from ocr_hub.db.migrations import list_applied_migrations
from ocr_hub.db.schema import init_db
from ocr_hub.repositories import taxonomy_repo, tenants_repo
from ocr_hub.services import ocr_engine


def test_wal_and_idempotent_migrations_preserve_existing_tenants(temp_db: Path) -> None:
    with get_connection(temp_db) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

    migrations = list_applied_migrations(temp_db)
    assert len(migrations) >= 1
    assert migrations[0]["version"] == 1

    tenant = tenants_repo.create_tenant(
        name="ExistingServerBot",
        default_currency="PLN",
        language="pl",
        database_path=temp_db,
    )

    # Re-running init_db must be completely idempotent and preserve existing bots & taxonomy
    init_db(temp_db)
    reloaded = tenants_repo.get_tenant_by_id(tenant["id"], database_path=temp_db)
    assert reloaded is not None
    assert reloaded["name"] == "ExistingServerBot"
    assert len(list_applied_migrations(temp_db)) == len(migrations)


def test_global_taxonomy_api_crud_and_stage2_prompt_integration(client: TestClient) -> None:
    # 1. Inspect seeded taxonomy
    res = client.get("/api/taxonomy")
    assert res.status_code == 200
    body = res.json()
    cat_codes = [c["code"] for c in body["categories"]]
    assert cat_codes == ["FOOD", "HOUSEHOLD", "PERSONAL_CARE", "DEPOSIT", "OTHER"]
    assert "dairy" in body["active_subcategory_codes"]
    assert "eggs" in body["active_subcategory_codes"]

    # 2. Add a new category + subcategory via Admin API
    admin_headers = {"X-Admin-Key": "test-admin-secret"}
    cat_resp = client.post(
        "/api/taxonomy/categories",
        headers=admin_headers,
        json={"code": "pets", "name_pl": "Zwierzęta", "name_en": "Pets"},
    )
    assert cat_resp.status_code == 201
    pets_cat = cat_resp.json()
    assert pets_cat["code"] == "PETS"

    sub_resp = client.post(
        "/api/taxonomy/subcategories",
        headers=admin_headers,
        json={
            "category_id": pets_cat["id"],
            "code": "Pet Food",
            "name_pl": "karma dla zwierząt",
            "name_en": "pet food",
        },
    )
    assert sub_resp.status_code == 201
    pet_sub = sub_resp.json()
    assert pet_sub["code"] == "pet_food"

    # Stage 2 prompt now automatically includes the new active subcategory from DB
    prompt_pl = ocr_engine.build_stage_2_classifier_prompt(language="pl")
    assert '"pet_food"' in prompt_pl
    assert "Polish" in prompt_pl

    # 3. Disable subcategory -> removed from active codes, still visible with include_inactive=true
    upd_resp = client.put(
        f"/api/taxonomy/subcategories/{pet_sub['id']}",
        headers=admin_headers,
        json={"is_active": False, "name_pl": "karma i akcesoria"},
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["is_active"] is False
    assert upd_resp.json()["name_pl"] == "karma i akcesoria"
    assert "pet_food" not in taxonomy_repo.get_active_subcategory_codes()

    all_tax = client.get("/api/taxonomy?include_inactive=true").json()
    pets_tree = next(c for c in all_tax["categories"] if c["code"] == "PETS")
    assert pets_tree["subcategories"][0]["code"] == "pet_food"
    assert pets_tree["subcategories"][0]["is_active"] is False

    # 4. Delete category cascades its subcategories
    del_resp = client.delete(
        f"/api/taxonomy/categories/{pets_cat['id']}",
        headers=admin_headers,
    )
    assert del_resp.status_code == 200
    assert taxonomy_repo.get_subcategory_by_code("pet_food") is None


def test_language_restricted_to_pl_and_en_and_webui_cleaned(client: TestClient) -> None:
    admin_headers = {"X-Admin-Key": "test-admin-secret"}

    # Invalid language rejected
    bad_resp = client.post(
        "/api/bots",
        headers=admin_headers,
        json={"name": "FrenchBot", "language": "fr"},
    )
    assert bad_resp.status_code == 422

    # Polish & English accepted
    ok_resp = client.post(
        "/api/bots",
        headers=admin_headers,
        json={"name": "PolishBot", "language": "pl", "default_currency": "PLN"},
    )
    assert ok_resp.status_code == 201
    assert ok_resp.json()["language"] == "pl"
    assert ok_resp.json()["default_currency"] == "PLN"

    # Web UI check
    html = client.get("/").text
    assert "Global Categories &amp; Subcategories" in html
    assert 'id="subcategories"' not in html
    assert '<option value="pl">Polish (pl)</option>' in html
    assert '<option value="en">English (en)</option>' in html
    assert '<option value="nl">' not in html
