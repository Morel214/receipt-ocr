"""Versioned SQLite schema migrations and default taxonomy/stores seeding for Receipt OCR Hub."""

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

# Predefined Polish retail chains and their fiscal receipt company/header variants
DEFAULT_POLISH_STORES_SEED: list[tuple[str, str, str, list[str]]] = [
    ("biedronka", "Biedronka", "PL", ["BIEDRONKA", "JERONIMO MARTINS", "JMP S.A.", "JMP SA"]),
    ("lidl", "Lidl", "PL", ["LIDL", "LIDL SP Z O O", "LIDL POLSKA"]),
    ("zabka", "Żabka", "PL", ["ZABKA", "ZABKA POLSKA", "ZABKA NANO"]),
    ("kaufland", "Kaufland", "PL", ["KAUFLAND", "KAUFLAND POLSKA", "KAUFLAND POLSKA MARKETY"]),
    ("dino", "Dino", "PL", ["DINO", "DINO POLSKA"]),
    ("auchan", "Auchan", "PL", ["AUCHAN", "AUCHAN POLSKA"]),
    ("carrefour", "Carrefour", "PL", ["CARREFOUR", "CARREFOUR POLSKA", "CARREFOUR EXPRESS", "CARREFOUR MARKET"]),
    ("netto", "Netto", "PL", ["NETTO", "NETTO INDYGO"]),
    ("aldi", "Aldi", "PL", ["ALDI", "ALDI SP Z O O"]),
    ("stokrotka", "Stokrotka", "PL", ["STOKROTKA"]),
    ("lewiatan", "Lewiatan", "PL", ["LEWIATAN", "POLSKA SIEC HANDLOWA LEWIATAN"]),
    ("intermarche", "Intermarché", "PL", ["INTERMARCHE"]),
    ("leclerc", "E.Leclerc", "PL", ["LECLERC", "E LECLERC"]),
    ("rossmann", "Rossmann", "PL", ["ROSSMANN", "ROSSMANN SDP", "ROSSMANN SUPERMARKETY DROGERYJNE"]),
    ("hebe", "Hebe", "PL", ["HEBE", "JERONIMO MARTINS DROGERIE"]),
    ("pepco", "Pepco", "PL", ["PEPCO", "PEPCO POLAND"]),
    ("action", "Action", "PL", ["ACTION", "ACTION POLAND"]),
    ("dealz", "Dealz", "PL", ["DEALZ", "DEALZ POLAND"]),
    ("makro", "Makro", "PL", ["MAKRO", "MAKRO CASH AND CARRY"]),
    ("selgros", "Selgros", "PL", ["SELGROS", "SELGROS CASH AND CARRY", "TRANSGOURMET"]),
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


def _migration_002_shared_catalog_and_taxonomy_approval(cursor: sqlite3.Cursor) -> None:
    """Add taxonomy approval columns plus stores, products, FTS5 trigram index, and product_aliases."""
    # 1. Add status & source columns to categories and subcategories for manual_user approval queue
    cursor.execute("PRAGMA table_info(categories);")
    cat_cols = {row[1] for row in cursor.fetchall()}
    if "status" not in cat_cols:
        cursor.execute(
            "ALTER TABLE categories ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed';"
        )
    if "source" not in cat_cols:
        cursor.execute(
            "ALTER TABLE categories ADD COLUMN source TEXT NOT NULL DEFAULT 'seed';"
        )

    cursor.execute("PRAGMA table_info(subcategories);")
    sub_cols = {row[1] for row in cursor.fetchall()}
    if "status" not in sub_cols:
        cursor.execute(
            "ALTER TABLE subcategories ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed';"
        )
    if "source" not in sub_cols:
        cursor.execute(
            "ALTER TABLE subcategories ADD COLUMN source TEXT NOT NULL DEFAULT 'seed';"
        )

    # 2. Stores & Store Aliases (normalizing fiscal receipt company headers to store chains)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'PL',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS store_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_norm TEXT NOT NULL UNIQUE,
            store_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores (id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_aliases_store ON store_aliases(store_id);"
    )

    for store_key, display_name, country, aliases in DEFAULT_POLISH_STORES_SEED:
        cursor.execute(
            """
            INSERT OR IGNORE INTO stores (store_key, display_name, country)
            VALUES (?, ?, ?);
            """,
            (store_key, display_name, country),
        )
        cursor.execute("SELECT id FROM stores WHERE store_key = ?;", (store_key,))
        row = cursor.fetchone()
        if not row:
            continue
        store_id = int(row[0])
        for alias in aliases:
            cursor.execute(
                """
                INSERT OR IGNORE INTO store_aliases (alias_norm, store_id)
                VALUES (?, ?);
                """,
                (alias, store_id),
            )

    # 3. Shared Generic Products table (Level 1 generic names + future-ready nutrition columns)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_pl TEXT NOT NULL,
            name_en TEXT NOT NULL,
            name_pl_norm TEXT NOT NULL,
            name_en_norm TEXT NOT NULL,
            subcategory_id INTEGER,
            default_unit TEXT NOT NULL DEFAULT 'pcs',
            status TEXT NOT NULL DEFAULT 'auto',
            source TEXT NOT NULL DEFAULT 'llm',
            kcal_100g REAL,
            protein_100g REAL,
            carbs_100g REAL,
            fat_100g REAL,
            fiber_100g REAL,
            default_piece_weight_g REAL,
            nutrition_source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subcategory_id) REFERENCES subcategories (id) ON DELETE SET NULL
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_subcat ON products(subcategory_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_pl_norm ON products(name_pl_norm);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_en_norm ON products(name_en_norm);")

    # 4. FTS5 Trigram full-text index synced automatically via SQLite triggers
    cursor.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
            name_pl,
            name_en,
            name_pl_norm,
            name_en_norm,
            content='products',
            content_rowid='id',
            tokenize='trigram'
        );
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, name_pl, name_en, name_pl_norm, name_en_norm)
            VALUES (new.id, new.name_pl, new.name_en, new.name_pl_norm, new.name_en_norm);
        END;
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name_pl, name_en, name_pl_norm, name_en_norm)
            VALUES ('delete', old.id, old.name_pl, old.name_en, old.name_pl_norm, old.name_en_norm);
        END;
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name_pl, name_en, name_pl_norm, name_en_norm)
            VALUES ('delete', old.id, old.name_pl, old.name_en, old.name_pl_norm, old.name_en_norm);
            INSERT INTO products_fts(rowid, name_pl, name_en, name_pl_norm, name_en_norm)
            VALUES (new.id, new.name_pl, new.name_en, new.name_pl_norm, new.name_en_norm);
        END;
        """
    )

    # 5. Product Aliases (OCR cache + Level 2 brand / Open Food Facts search query)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER,
            raw_name_original TEXT NOT NULL,
            raw_name_norm TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            brand TEXT,
            off_search_query TEXT,
            pack_amount REAL,
            pack_unit TEXT,
            source TEXT NOT NULL DEFAULT 'llm',
            status TEXT NOT NULL DEFAULT 'auto',
            hit_count INTEGER NOT NULL DEFAULT 1,
            last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores (id) ON DELETE SET NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_product_aliases_store_raw
            ON product_aliases (COALESCE(store_id, 0), raw_name_norm);
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_aliases_raw_norm ON product_aliases(raw_name_norm);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_aliases_product ON product_aliases(product_id);"
    )


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Cursor], None]]] = [
    (1, "001_global_taxonomy_categories_and_subcategories", _migration_001_global_taxonomy),
    (
        2,
        "002_shared_catalog_and_taxonomy_approval",
        _migration_002_shared_catalog_and_taxonomy_approval,
    ),
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
