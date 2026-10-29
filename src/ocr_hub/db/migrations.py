"""Versioned SQLite schema migrations and default taxonomy seeding for Receipt OCR Hub."""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ocr_hub.db.connection import get_connection

# Default Global Taxonomy (Polish & English) — editable at runtime via Web UI / REST API
DEFAULT_TAXONOMY_SEED: list[dict[str, Any]] = [
    {
        "code": "FOOD",
        "name_pl": "Jedzenie i napoje",
        "name_en": "Food & Beverages",
        "sort_order": 10,
        "subcategories": [
            ("dairy", "nabiał", "dairy", 10),
            ("eggs", "jajka", "eggs", 20),
            ("meat_poultry", "mięso i drób", "meat & poultry", 30),
            ("fish_seafood", "ryby i owoce morza", "fish & seafood", 40),
            ("charcuterie", "wędliny i kiełbasy", "cold cuts & sausages", 50),
            ("vegetables", "warzywa", "vegetables", 60),
            ("fruits", "owoce", "fruits", 70),
            ("bakery", "pieczywo", "bakery", 80),
            ("grains_pasta", "zboża, ryż i makarony", "grains, rice & pasta", 90),
            ("canned_jarred", "konserwy i przetwory", "canned & jarred food", 100),
            ("frozen", "mrożonki", "frozen food", 110),
            ("ready_meals", "dania gotowe", "ready meals", 120),
            ("snacks_sweets", "przekąski i słodycze", "snacks & sweets", 130),
            ("beverages", "napoje, kawa i herbata", "beverages, coffee & tea", 140),
            ("alcohol", "alkohol", "alcohol", 150),
            ("spices_oils", "przyprawy, oleje i sosy", "spices, oils & sauces", 160),
        ],
    },
    {
        "code": "HOUSEHOLD",
        "name_pl": "Chemia i dom",
        "name_en": "Household",
        "sort_order": 20,
        "subcategories": [
            ("cleaning", "środki czystości", "cleaning supplies", 10),
            ("home_supplies", "artykuły domowe", "household supplies", 20),
        ],
    },
    {
        "code": "PERSONAL_CARE",
        "name_pl": "Higiena i kosmetyki",
        "name_en": "Personal Care",
        "sort_order": 30,
        "subcategories": [
            ("personal_care", "kosmetyki i higiena", "cosmetics & hygiene", 10),
            ("pharmacy_supplements", "apteka i suplementy", "pharmacy & supplements", 20),
        ],
    },
    {
        "code": "DEPOSIT",
        "name_pl": "Kaucja",
        "name_en": "Deposit",
        "sort_order": 40,
        "subcategories": [
            ("deposit", "kaucja", "bottle deposit", 10),
        ],
    },
    {
        "code": "OTHER",
        "name_pl": "Inne",
        "name_en": "Other",
        "sort_order": 50,
        "subcategories": [
            ("other", "inne", "other", 10),
        ],
    },
]


def _migration_001_global_taxonomy(cursor: sqlite3.Cursor) -> None:
    """Create global categories & subcategories tables and seed default PL/EN taxonomy."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name_pl TEXT NOT NULL,
            name_en TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS subcategories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            code TEXT NOT NULL UNIQUE,
            name_pl TEXT NOT NULL,
            name_en TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_subcategories_category ON subcategories(category_id);"
    )

    for cat in DEFAULT_TAXONOMY_SEED:
        cursor.execute(
            """
            INSERT OR IGNORE INTO categories (code, name_pl, name_en, sort_order, is_active)
            VALUES (?, ?, ?, ?, 1);
            """,
            (cat["code"], cat["name_pl"], cat["name_en"], cat["sort_order"]),
        )
        cursor.execute("SELECT id FROM categories WHERE code = ?;", (cat["code"],))
        row = cursor.fetchone()
        if not row:
            continue
        category_id = int(row[0])

        for sub_code, sub_pl, sub_en, sub_order in cat["subcategories"]:
            cursor.execute(
                """
                INSERT OR IGNORE INTO subcategories (
                    category_id, code, name_pl, name_en, sort_order, is_active
                )
                VALUES (?, ?, ?, ?, ?, 1);
                """,
                (category_id, sub_code, sub_pl, sub_en, sub_order),
            )


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Cursor], None]]] = [
    (1, "001_global_taxonomy_categories_and_subcategories", _migration_001_global_taxonomy),
]


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply any pending numbered migrations on an open SQLite connection."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute("SELECT version FROM schema_migrations;")
    applied = {int(row[0]) for row in cursor.fetchall()}

    newly_applied: list[int] = []
    for version, name, migration_fn in sorted(MIGRATIONS, key=lambda m: m[0]):
        if version in applied:
            continue
        migration_fn(cursor)
        cursor.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
            (version, name),
        )
        newly_applied.append(version)

    return newly_applied


def list_applied_migrations(
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return applied schema migrations ordered by version."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version ASC;"
        )
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
