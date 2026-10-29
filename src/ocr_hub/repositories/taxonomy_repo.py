"""Repository for managing the shared global Categories & Subcategories taxonomy (PL/EN)."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from ocr_hub import config
from ocr_hub.db.connection import get_connection


def _normalize_category_code(code: str) -> str:
    """Normalize a category code to UPPER_SNAKE_CASE."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", code.strip()).strip("_").upper()
    if not cleaned:
        raise ValueError("Category code cannot be empty.")
    return cleaned


def _normalize_subcategory_code(code: str) -> str:
    """Normalize a subcategory code to lower_snake_case."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", code.strip()).strip("_").lower()
    if not cleaned:
        raise ValueError("Subcategory code cannot be empty.")
    return cleaned


def _row_to_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a SQLite row to a dictionary with boolean ``is_active``."""
    item = dict(zip(columns, row))
    if "is_active" in item:
        item["is_active"] = bool(item["is_active"])
    return item


def list_categories(
    only_active: bool = False,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return categories ordered by ``sort_order`` and ``id`` (excluding unapproved when ``only_active=True``)."""
    query = "SELECT * FROM categories"
    if only_active:
        query += " WHERE is_active = 1 AND status = 'confirmed'"
    query += " ORDER BY sort_order ASC, id ASC;"
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        cols = [c[0] for c in cursor.description]
        return [_row_to_dict(cols, row) for row in cursor.fetchall()]


def get_category_by_id(
    category_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single category by ID, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories WHERE id = ?;", (category_id,))
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return _row_to_dict(cols, row) if row else None


def create_category(
    code: str,
    name_pl: str,
    name_en: str,
    sort_order: int = 100,
    is_active: bool = True,
    status: str = "confirmed",
    source: str = "admin",
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new top-level category (or pending manual_user suggestion when unauthenticated)."""
    norm_code = _normalize_category_code(code)
    effective_active = 1 if (is_active and status == "confirmed") else 0
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO categories (code, name_pl, name_en, sort_order, is_active, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                norm_code,
                name_pl.strip(),
                name_en.strip(),
                int(sort_order),
                effective_active,
                status,
                source,
            ),
        )
        cat_id = int(cursor.lastrowid)
    created = get_category_by_id(cat_id, database_path=database_path)
    assert created is not None
    return created


def approve_category(
    category_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Approve a pending manual_user category into the active global taxonomy."""
    return update_category(
        category_id,
        is_active=True,
        status="confirmed",
        database_path=database_path,
    )


def update_category(
    category_id: int,
    database_path: str | Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update a category's code, PL/EN names, sort_order, status, or active state."""
    allowed = {"code", "name_pl", "name_en", "sort_order", "is_active", "status", "source"}
    updates: list[str] = []
    params: list[Any] = []

    if "code" in fields and fields["code"] is not None:
        fields["code"] = _normalize_category_code(str(fields["code"]))
    if "name_pl" in fields and fields["name_pl"] is not None:
        fields["name_pl"] = str(fields["name_pl"]).strip()
    if "name_en" in fields and fields["name_en"] is not None:
        fields["name_en"] = str(fields["name_en"]).strip()
    if "is_active" in fields and isinstance(fields["is_active"], bool):
        fields["is_active"] = 1 if fields["is_active"] else 0

    for col, val in fields.items():
        if col in allowed and val is not None:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return get_category_by_id(category_id, database_path=database_path)

    params.append(category_id)
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE categories SET {', '.join(updates)} WHERE id = ?;",
            params,
        )

    return get_category_by_id(category_id, database_path=database_path)


def delete_category(
    category_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a category (and its cascaded subcategories)."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?;", (category_id,))
        return cursor.rowcount > 0


def list_subcategories(
    only_active: bool = False,
    category_id: int | None = None,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return subcategories enriched with parent category metadata."""
    query = """
        SELECT
            s.id,
            s.category_id,
            c.code AS category_code,
            c.name_pl AS category_name_pl,
            c.name_en AS category_name_en,
            s.code,
            s.name_pl,
            s.name_en,
            s.sort_order,
            s.is_active,
            s.status,
            s.source,
            s.created_at
        FROM subcategories s
        JOIN categories c ON c.id = s.category_id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if only_active:
        query += (
            " AND s.is_active = 1 AND s.status = 'confirmed'"
            " AND c.is_active = 1 AND c.status = 'confirmed'"
        )
    if category_id is not None:
        query += " AND s.category_id = ?"
        params.append(category_id)
    query += " ORDER BY c.sort_order ASC, s.sort_order ASC, s.id ASC;"

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        return [_row_to_dict(cols, row) for row in cursor.fetchall()]


def get_subcategory_by_id(
    subcategory_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single subcategory by ID, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                s.id, s.category_id, c.code AS category_code,
                c.name_pl AS category_name_pl, c.name_en AS category_name_en,
                s.code, s.name_pl, s.name_en, s.sort_order,
                s.is_active, s.status, s.source, s.created_at
            FROM subcategories s
            JOIN categories c ON c.id = s.category_id
            WHERE s.id = ?;
            """,
            (subcategory_id,),
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return _row_to_dict(cols, row) if row else None


def get_subcategory_by_code(
    code: str,
    only_active: bool = False,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single subcategory by its unique code, or None."""
    query = """
        SELECT
            s.id, s.category_id, c.code AS category_code,
            c.name_pl AS category_name_pl, c.name_en AS category_name_en,
            s.code, s.name_pl, s.name_en, s.sort_order,
            s.is_active, s.status, s.source, s.created_at
        FROM subcategories s
        JOIN categories c ON c.id = s.category_id
        WHERE LOWER(s.code) = LOWER(?)
    """
    if only_active:
        query += (
            " AND s.is_active = 1 AND s.status = 'confirmed'"
            " AND c.is_active = 1 AND c.status = 'confirmed'"
        )
    query += ";"
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (code.strip(),))
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return _row_to_dict(cols, row) if row else None


def create_subcategory(
    category_id: int,
    code: str,
    name_pl: str,
    name_en: str,
    sort_order: int = 100,
    is_active: bool = True,
    status: str = "confirmed",
    source: str = "admin",
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new subcategory under ``category_id`` (or pending manual_user suggestion)."""
    norm_code = _normalize_subcategory_code(code)
    effective_active = 1 if (is_active and status == "confirmed") else 0
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO subcategories (
                category_id, code, name_pl, name_en, sort_order, is_active, status, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(category_id),
                norm_code,
                name_pl.strip(),
                name_en.strip(),
                int(sort_order),
                effective_active,
                status,
                source,
            ),
        )
        sub_id = int(cursor.lastrowid)
    created = get_subcategory_by_id(sub_id, database_path=database_path)
    assert created is not None
    return created


def approve_subcategory(
    subcategory_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Approve a pending manual_user subcategory into the active global taxonomy."""
    return update_subcategory(
        subcategory_id,
        is_active=True,
        status="confirmed",
        database_path=database_path,
    )


def update_subcategory(
    subcategory_id: int,
    database_path: str | Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update a subcategory's parent category, code, PL/EN names, sort_order, status, or active state."""
    allowed = {
        "category_id",
        "code",
        "name_pl",
        "name_en",
        "sort_order",
        "is_active",
        "status",
        "source",
    }
    updates: list[str] = []
    params: list[Any] = []

    if "code" in fields and fields["code"] is not None:
        fields["code"] = _normalize_subcategory_code(str(fields["code"]))
    if "name_pl" in fields and fields["name_pl"] is not None:
        fields["name_pl"] = str(fields["name_pl"]).strip()
    if "name_en" in fields and fields["name_en"] is not None:
        fields["name_en"] = str(fields["name_en"]).strip()
    if "is_active" in fields and isinstance(fields["is_active"], bool):
        fields["is_active"] = 1 if fields["is_active"] else 0

    for col, val in fields.items():
        if col in allowed and val is not None:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return get_subcategory_by_id(subcategory_id, database_path=database_path)

    params.append(subcategory_id)
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE subcategories SET {', '.join(updates)} WHERE id = ?;",
            params,
        )

    return get_subcategory_by_id(subcategory_id, database_path=database_path)


def delete_subcategory(
    subcategory_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a subcategory by ID."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subcategories WHERE id = ?;", (subcategory_id,))
        return cursor.rowcount > 0


def list_pending_taxonomy(
    database_path: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return unapproved ('pending') categories and subcategories submitted by non-admin users."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM categories WHERE status = 'pending' ORDER BY id ASC;"
        )
        cat_cols = [c[0] for c in cursor.description]
        pending_cats = [_row_to_dict(cat_cols, row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT
                s.id, s.category_id, c.code AS category_code,
                c.name_pl AS category_name_pl, c.name_en AS category_name_en,
                s.code, s.name_pl, s.name_en, s.sort_order,
                s.is_active, s.status, s.source, s.created_at
            FROM subcategories s
            JOIN categories c ON c.id = s.category_id
            WHERE s.status = 'pending'
            ORDER BY s.id ASC;
            """
        )
        sub_cols = [c[0] for c in cursor.description]
        pending_subs = [_row_to_dict(sub_cols, row) for row in cursor.fetchall()]

    return {"categories": pending_cats, "subcategories": pending_subs}


def get_taxonomy_tree(
    only_active: bool = False,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return categories with their nested subcategories list."""
    categories = list_categories(only_active=only_active, database_path=database_path)
    subcategories = list_subcategories(only_active=only_active, database_path=database_path)

    by_cat: dict[int, list[dict[str, Any]]] = {c["id"]: [] for c in categories}
    for sub in subcategories:
        cid = sub["category_id"]
        if cid in by_cat:
            by_cat[cid].append(sub)

    for cat in categories:
        cat["subcategories"] = by_cat.get(cat["id"], [])
    return categories


def get_active_subcategory_codes(
    database_path: str | Path | None = None,
) -> list[str]:
    """Return active, confirmed subcategory codes from the DB, falling back to config defaults."""
    try:
        subcats = list_subcategories(only_active=True, database_path=database_path)
        codes = [s["code"] for s in subcats]
        return codes if codes else list(config.DEFAULT_SUBCATEGORIES)
    except sqlite3.OperationalError:
        return list(config.DEFAULT_SUBCATEGORIES)
