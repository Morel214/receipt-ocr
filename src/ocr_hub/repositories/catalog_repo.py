"""Repository for the shared Product Catalog, Store normalization, OCR Alias Cache, and FTS5 search."""

from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any
import unicodedata

from ocr_hub.db.connection import get_connection
from ocr_hub.repositories import taxonomy_repo

_POLISH_CHAR_MAP = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
        "ß": "ss",
        "æ": "ae",
        "Æ": "AE",
        "ø": "o",
        "Ø": "O",
    }
)

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:SP\.?\s*Z\s*O\.?\s*O\.?|SP\.?\s*K\.?|S\.?\s*A\.?|SPOLKA\s+AKCYJNA|SKLEP\s*(?:NR\.?)?\s*\d+)\b",
    flags=re.IGNORECASE,
)

_PACK_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?(?:g|kg|ml|l|cl|szt|op|pcs|x\d+)$", flags=re.IGNORECASE)


def fold_polish_ascii(text: str) -> str:
    """Fold Polish and European diacritics (including ł/Ł) cleanly into ASCII."""
    translated = text.translate(_POLISH_CHAR_MAP)
    decomposed = unicodedata.normalize("NFKD", translated)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def normalize_store_alias_key(raw_store_name: str) -> str:
    """Normalize a raw receipt store header into an uppercase ASCII lookup key."""
    folded = fold_polish_ascii(raw_store_name).upper()
    folded = _COMPANY_SUFFIX_RE.sub(" ", folded)
    folded = re.sub(r"[^A-Z0-9]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def slugify_store_key(name: str) -> str:
    """Build a lowercase snake/slug key for a newly discovered store."""
    folded = fold_polish_ascii(name).lower()
    folded = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    return folded or "unknown_store"


def normalize_raw_item_name(raw_name: str) -> str:
    """Normalize a dirty receipt item name into a deterministic cache lookup key.

    Examples:
        ``"MLEKO ŁACIATE 3,2% 1 L *C"`` -> ``"MLEKO LACIATE 3.2% 1L"``
        ``"JAJA MOJA KURKA M 10 SZT."`` -> ``"JAJA MOJA KURKA M 10SZT"``
    """
    text = fold_polish_ascii(raw_name).upper().strip()
    # Convert Polish decimal commas between digits into dots (3,2% -> 3.2%)
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    # Strip trailing fiscal PTU markers if attached at the end (e.g. "*A", "PTU C")
    text = re.sub(r"\s+(?:PTU\s*[A-G]|\*[A-G])$", "", text)
    # Collapse space between numeric amount and common Polish/metric units (1 L -> 1L, 10 SZT -> 10SZT)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s+(G|KG|ML|L|SZT|OP|PCS)\b", r"\1\2", text)
    # Replace punctuation other than '.', '%', '/', '-' inside words with spaces
    text = re.sub(r"[^A-Z0-9.%/-]+", " ", text)
    # Clean stray leading/trailing dots or hyphens around tokens
    tokens = [tok.strip(".-/") for tok in text.split() if tok.strip(".-/")]
    return " ".join(tokens)


def normalize_clean_product_name(name: str) -> str:
    """Normalize a clean product name (PL or EN) for deduplication and FTS5 indexing."""
    text = fold_polish_ascii(name).lower().strip()
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    text = re.sub(r"[^a-z0-9.%/-]+", " ", text)
    tokens = [tok.strip(".-/") for tok in text.split() if tok.strip(".-/")]
    return " ".join(tokens)


# ==============================================================================
# Stores & Store Aliases
# ==============================================================================


def list_stores(database_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all registered stores ordered by display_name."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stores ORDER BY display_name ASC, id ASC;")
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def resolve_store(
    raw_store_name: str | None,
    auto_create: bool = True,
    country: str = "PL",
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Resolve a raw OCR store header (e.g. 'JERONIMO MARTINS POLSKA S.A.') to a canonical store record."""
    if not raw_store_name or not raw_store_name.strip():
        return None

    norm = normalize_store_alias_key(raw_store_name)
    if not norm:
        return None

    with get_connection(database_path) as conn:
        cursor = conn.cursor()

        # 1. Exact alias match
        cursor.execute(
            """
            SELECT s.*
            FROM store_aliases sa
            JOIN stores s ON s.id = sa.store_id
            WHERE sa.alias_norm = ?
            LIMIT 1;
            """,
            (norm,),
        )
        row = cursor.fetchone()
        if row:
            cols = [c[0] for c in cursor.description]
            return dict(zip(cols, row))

        # 2. Substring/word-boundary match against known store aliases (longest alias wins)
        cursor.execute(
            """
            SELECT sa.alias_norm, s.*
            FROM store_aliases sa
            JOIN stores s ON s.id = sa.store_id
            ORDER BY LENGTH(sa.alias_norm) DESC;
            """
        )
        all_cols = [c[0] for c in cursor.description]
        store_cols = all_cols[1:]
        padded_norm = f" {norm} "
        for candidate in cursor.fetchall():
            alias_norm = candidate[0]
            if f" {alias_norm} " in padded_norm:
                return dict(zip(store_cols, candidate[1:]))

        if not auto_create:
            return None

        # 3. Auto-register newly encountered local store
        display = " ".join(w.capitalize() for w in raw_store_name.strip().split())
        base_key = slugify_store_key(norm)
        store_key = base_key
        suffix = 2
        while True:
            cursor.execute("SELECT id FROM stores WHERE store_key = ?;", (store_key,))
            if cursor.fetchone() is None:
                break
            store_key = f"{base_key}_{suffix}"
            suffix += 1

        cursor.execute(
            "INSERT INTO stores (store_key, display_name, country) VALUES (?, ?, ?);",
            (store_key, display, country.upper()),
        )
        new_store_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT OR IGNORE INTO store_aliases (alias_norm, store_id) VALUES (?, ?);",
            (norm, new_store_id),
        )
        cursor.execute("SELECT * FROM stores WHERE id = ?;", (new_store_id,))
        cols = [c[0] for c in cursor.description]
        created_row = cursor.fetchone()
        assert created_row is not None
        return dict(zip(cols, created_row))


# ==============================================================================
# Generic Products & FTS5 Trigram Search
# ==============================================================================

_PRODUCT_SELECT_SQL = """
    SELECT
        p.id,
        p.name_pl,
        p.name_en,
        p.name_pl_norm,
        p.name_en_norm,
        p.subcategory_id,
        s.code AS subcategory_code,
        s.name_pl AS subcategory_name_pl,
        s.name_en AS subcategory_name_en,
        c.code AS category_code,
        c.name_pl AS category_name_pl,
        c.name_en AS category_name_en,
        p.default_unit,
        p.status,
        p.source,
        p.kcal_100g,
        p.protein_100g,
        p.carbs_100g,
        p.fat_100g,
        p.fiber_100g,
        p.default_piece_weight_g,
        p.nutrition_source,
        (SELECT COUNT(*) FROM product_aliases pa WHERE pa.product_id = p.id) AS alias_count,
        (SELECT COALESCE(SUM(pa.hit_count), 0) FROM product_aliases pa WHERE pa.product_id = p.id) AS total_hits,
        p.created_at,
        p.updated_at
    FROM products p
    LEFT JOIN subcategories s ON s.id = p.subcategory_id
    LEFT JOIN categories c ON c.id = s.category_id
"""


def get_product_by_id(
    product_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a single enriched product by ID, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"{_PRODUCT_SELECT_SQL} WHERE p.id = ?;", (product_id,))
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None


def find_product_by_clean_name(
    name_pl: str | None = None,
    name_en: str | None = None,
    include_pending: bool = False,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Find an existing product matching normalized Polish or English clean name."""
    pl_norm = normalize_clean_product_name(name_pl) if name_pl else ""
    en_norm = normalize_clean_product_name(name_en) if name_en else ""
    if not pl_norm and not en_norm:
        return None

    clauses: list[str] = []
    params: list[Any] = []
    if pl_norm:
        clauses.append("p.name_pl_norm = ?")
        params.append(pl_norm)
    if en_norm:
        clauses.append("p.name_en_norm = ?")
        params.append(en_norm)

    status_filter = "" if include_pending else " AND p.status IN ('auto', 'confirmed')"
    query = (
        f"{_PRODUCT_SELECT_SQL} WHERE ({' OR '.join(clauses)}){status_filter}"
        " ORDER BY CASE WHEN p.status = 'confirmed' THEN 0 ELSE 1 END, p.id ASC LIMIT 1;"
    )
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None


def create_or_get_product(
    name_pl: str,
    name_en: str,
    subcategory_code: str | None = None,
    subcategory_id: int | None = None,
    default_unit: str = "pcs",
    status: str = "auto",
    source: str = "llm",
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return an existing product matching PL/EN clean name, or create a new catalog product."""
    clean_pl = name_pl.strip().lower()
    clean_en = name_en.strip().lower()
    if not clean_pl or not clean_en:
        raise ValueError("Both name_pl and name_en are required to create a product.")

    if status != "pending":
        existing = find_product_by_clean_name(
            name_pl=clean_pl,
            name_en=clean_en,
            include_pending=False,
            database_path=database_path,
        )
        if existing is not None:
            return existing

    resolved_subcat_id = subcategory_id
    if resolved_subcat_id is None and subcategory_code:
        sub = taxonomy_repo.get_subcategory_by_code(
            subcategory_code, only_active=True, database_path=database_path
        )
        if sub is not None:
            resolved_subcat_id = int(sub["id"])

    unit_clean = default_unit.strip().lower() if default_unit else "pcs"
    if unit_clean not in ("pcs", "kg", "l"):
        unit_clean = "pcs"

    pl_norm = normalize_clean_product_name(clean_pl)
    en_norm = normalize_clean_product_name(clean_en)

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO products (
                name_pl, name_en, name_pl_norm, name_en_norm,
                subcategory_id, default_unit, status, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                clean_pl,
                clean_en,
                pl_norm,
                en_norm,
                resolved_subcat_id,
                unit_clean,
                status,
                source,
            ),
        )
        product_id = int(cursor.lastrowid)

    created = get_product_by_id(product_id, database_path=database_path)
    assert created is not None
    return created


def update_product(
    product_id: int,
    database_path: str | Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update product fields (recomputing normalized FTS columns when PL/EN names change)."""
    existing = get_product_by_id(product_id, database_path=database_path)
    if existing is None:
        return None

    if "subcategory_code" in fields:
        sub_code = fields.pop("subcategory_code")
        if sub_code:
            sub = taxonomy_repo.get_subcategory_by_code(sub_code, database_path=database_path)
            if sub:
                fields["subcategory_id"] = sub["id"]
        else:
            fields["subcategory_id"] = None

    if "name_pl" in fields and fields["name_pl"] is not None:
        fields["name_pl"] = str(fields["name_pl"]).strip().lower()
        fields["name_pl_norm"] = normalize_clean_product_name(fields["name_pl"])

    if "name_en" in fields and fields["name_en"] is not None:
        fields["name_en"] = str(fields["name_en"]).strip().lower()
        fields["name_en_norm"] = normalize_clean_product_name(fields["name_en"])

    allowed = {
        "name_pl",
        "name_en",
        "name_pl_norm",
        "name_en_norm",
        "subcategory_id",
        "default_unit",
        "status",
        "source",
        "kcal_100g",
        "protein_100g",
        "carbs_100g",
        "fat_100g",
        "fiber_100g",
        "default_piece_weight_g",
        "nutrition_source",
    }

    updates: list[str] = []
    params: list[Any] = []
    for col, val in fields.items():
        if col in allowed:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return existing

    updates.append("updated_at = ?")
    params.append(datetime.now().replace(microsecond=0).isoformat())
    params.append(product_id)

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?;", params)

    return get_product_by_id(product_id, database_path=database_path)


def list_products(
    status: str | None = None,
    subcategory_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List catalog products with optional status or subcategory filters."""
    query = f"{_PRODUCT_SELECT_SQL} WHERE 1 = 1"
    params: list[Any] = []
    if status:
        query += " AND p.status = ?"
        params.append(status)
    if subcategory_code:
        query += " AND LOWER(s.code) = LOWER(?)"
        params.append(subcategory_code.strip())
    query += " ORDER BY p.id DESC LIMIT ? OFFSET ?;"
    params.extend([int(limit), int(offset)])

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def query_products(
    q: str | None = None,
    status: str | None = None,
    source: str | None = None,
    subcategory_code: str | None = None,
    include_pending: bool = False,
    limit: int = 100,
    offset: int = 0,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Browse and search catalog products with FTS5 typo tolerance plus alias/brand substring matching."""
    status_clean = status.strip().lower() if status and status.strip() else None
    if status_clean == "pending" and not include_pending:
        return []

    sub_clean = subcategory_code.strip().lower() if subcategory_code and subcategory_code.strip() else None
    source_clean = source.strip().lower() if source and source.strip() else None
    search_text = q.strip() if q and q.strip() else ""

    def _matches_filters(prod: dict[str, Any]) -> bool:
        p_status = str(prod.get("status") or "")
        if not include_pending and p_status == "pending":
            return False
        if status_clean and p_status != status_clean:
            return False
        if source_clean and str(prod.get("source") or "").lower() != source_clean:
            return False
        if sub_clean and str(prod.get("subcategory_code") or "").lower() != sub_clean:
            return False
        return True

    if not search_text:
        query = f"{_PRODUCT_SELECT_SQL} WHERE 1 = 1"
        params: list[Any] = []
        if status_clean:
            query += " AND p.status = ?"
            params.append(status_clean)
        elif not include_pending:
            query += " AND p.status IN ('auto', 'confirmed')"
        if source_clean:
            query += " AND LOWER(p.source) = ?"
            params.append(source_clean)
        if sub_clean:
            query += " AND LOWER(s.code) = ?"
            params.append(sub_clean)
        query += " ORDER BY total_hits DESC, p.id DESC LIMIT ? OFFSET ?;"
        params.extend([int(limit), int(offset)])
        with get_connection(database_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Search mode: prioritize exact/substring product & alias/brand/OFF matches first, then typo-tolerant FTS5
    combined: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    norm_prod_q = normalize_clean_product_name(search_text)
    norm_raw_q = normalize_raw_item_name(search_text)
    like_prod = f"%{norm_prod_q}%" if norm_prod_q else f"%{search_text.lower()}%"
    like_raw = f"%{norm_raw_q}%" if norm_raw_q else f"%{search_text.upper()}%"
    like_folded_lower = f"%{fold_polish_ascii(search_text).lower().strip()}%"

    sql = f"""
        {_PRODUCT_SELECT_SQL}
        WHERE (
            p.name_pl_norm LIKE ?
            OR p.name_en_norm LIKE ?
            OR LOWER(p.name_pl) LIKE ?
            OR LOWER(p.name_en) LIKE ?
            OR EXISTS (
                SELECT 1 FROM product_aliases pa
                WHERE pa.product_id = p.id
                  AND (
                      pa.raw_name_norm LIKE ?
                      OR LOWER(COALESCE(pa.brand, '')) LIKE ?
                      OR LOWER(COALESCE(pa.off_search_query, '')) LIKE ?
                  )
            )
        )
        ORDER BY
            CASE
                WHEN p.name_pl_norm LIKE ? OR p.name_en_norm LIKE ? THEN 0
                ELSE 1
            END,
            total_hits DESC,
            p.id DESC
        LIMIT ?;
    """
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            sql,
            (
                like_prod,
                like_prod,
                f"%{search_text.lower()}%",
                f"%{search_text.lower()}%",
                like_raw,
                like_folded_lower,
                like_folded_lower,
                like_prod,
                like_prod,
                max(int(limit) + int(offset) + 30, 80),
            ),
        )
        cols = [c[0] for c in cursor.description]
        for row in cursor.fetchall():
            item = dict(zip(cols, row))
            pid = int(item["id"])
            if pid not in seen_ids and _matches_filters(item):
                seen_ids.add(pid)
                combined.append(item)

    fts_hits = search_products_fts(
        search_text,
        limit=max(int(limit) + int(offset), 40),
        include_pending=include_pending,
        database_path=database_path,
    )
    for item in fts_hits:
        pid = int(item["id"])
        if pid not in seen_ids and _matches_filters(item):
            seen_ids.add(pid)
            combined.append(item)

    return combined[int(offset) : int(offset) + int(limit)]


def approve_product(
    product_id: int,
    approve_aliases: bool = True,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Approve an ``auto`` or ``pending`` product into ``confirmed`` active catalog status."""
    existing = get_product_by_id(product_id, database_path=database_path)
    if existing is None:
        return None

    # If a pending manual_user product duplicates an already-active product, merge into canonical
    if existing.get("status") == "pending":
        duplicate_active = find_product_by_clean_name(
            name_pl=existing["name_pl"],
            name_en=existing["name_en"],
            include_pending=False,
            database_path=database_path,
        )
        if duplicate_active is not None and int(duplicate_active["id"]) != int(product_id):
            merged = merge_products(
                source_product_id=int(product_id),
                target_product_id=int(duplicate_active["id"]),
                database_path=database_path,
            )
            return update_product(int(merged["id"]), status="confirmed", database_path=database_path)

    updated = update_product(product_id, status="confirmed", database_path=database_path)
    if approve_aliases and updated is not None:
        with get_connection(database_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE product_aliases SET status = 'confirmed' WHERE product_id = ? AND status = 'auto';",
                (int(product_id),),
            )
        updated = get_product_by_id(product_id, database_path=database_path)
    return updated


def delete_product(
    product_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a product (and its cascaded aliases) from the catalog."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?;", (int(product_id),))
        return cursor.rowcount > 0


def _extract_trigrams(norm_query: str) -> list[str]:
    """Extract unique 3-character trigrams from normalized non-package words."""
    tokens = [
        tok for tok in norm_query.split() if not _PACK_TOKEN_RE.match(tok) and len(tok) >= 3
    ]
    seen: set[str] = set()
    trigrams: list[str] = []
    for tok in tokens:
        clean_tok = tok.replace('"', "")
        for i in range(len(clean_tok) - 2):
            tri = clean_tok[i : i + 3]
            if tri not in seen:
                seen.add(tri)
                trigrams.append(tri)
    return trigrams


def search_products_fts(
    query: str,
    limit: int = 5,
    include_pending: bool = False,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Search similar catalog products using FTS5 trigram BM25 with typo-tolerant subsequence fallback."""
    norm_q = normalize_clean_product_name(query)
    if not norm_q:
        return []

    filtered_tokens = [tok for tok in norm_q.split() if not _PACK_TOKEN_RE.match(tok)]
    effective_q = " ".join(filtered_tokens) or norm_q
    trigrams = _extract_trigrams(effective_q)
    status_clause = "" if include_pending else " AND p.status IN ('auto', 'confirmed')"

    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    with get_connection(database_path) as conn:
        cursor = conn.cursor()

        # 1. Fast FTS5 trigram OR match ordered by BM25 relevance
        if trigrams:
            fts_expr = " OR ".join(f'"{tri}"' for tri in trigrams[:24])
            sql = f"""
                {_PRODUCT_SELECT_SQL}
                JOIN products_fts fts ON fts.rowid = p.id
                WHERE products_fts MATCH ?{status_clause}
                ORDER BY bm25(products_fts) ASC
                LIMIT ?;
            """
            cursor.execute(sql, (fts_expr, int(limit)))
            cols = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(cols, row))
                seen_ids.add(int(item["id"]))
                results.append(item)

        # 2. Subsequence & substring fallback for short words or deletions (e.g. 'mlko' -> 'mleko')
        if len(results) < limit:
            first_word = re.sub(r"[^a-z0-9]", "", effective_q.split()[0])
            if first_word:
                subseq_pattern = "%" + "%".join(first_word[:8]) + "%"
                sql_like = f"""
                    {_PRODUCT_SELECT_SQL}
                    WHERE (p.name_pl_norm LIKE ? OR p.name_en_norm LIKE ?){status_clause}
                    LIMIT 30;
                """
                cursor.execute(sql_like, (subseq_pattern, subseq_pattern))
                cols = [c[0] for c in cursor.description]
                fallback_candidates: list[tuple[float, dict[str, Any]]] = []
                for row in cursor.fetchall():
                    item = dict(zip(cols, row))
                    if int(item["id"]) in seen_ids:
                        continue
                    score_pl = SequenceMatcher(None, effective_q, item["name_pl_norm"]).ratio()
                    score_en = SequenceMatcher(None, effective_q, item["name_en_norm"]).ratio()
                    best = max(score_pl, score_en)
                    if best >= 0.45:
                        fallback_candidates.append((best, item))

                fallback_candidates.sort(key=lambda pair: pair[0], reverse=True)
                for _, item in fallback_candidates:
                    if len(results) >= limit:
                        break
                    seen_ids.add(int(item["id"]))
                    results.append(item)

    return results


# ==============================================================================
# Product Aliases (OCR Cache + Brand / Open Food Facts Search Query)
# ==============================================================================

_ALIAS_SELECT_SQL = """
    SELECT
        a.id AS alias_id,
        a.store_id,
        st.store_key,
        st.display_name AS store_display_name,
        a.raw_name_original,
        a.raw_name_norm,
        a.product_id,
        p.name_pl,
        p.name_en,
        p.subcategory_id,
        sub.code AS subcategory_code,
        sub.name_pl AS subcategory_name_pl,
        sub.name_en AS subcategory_name_en,
        cat.code AS category_code,
        p.default_unit,
        a.brand,
        a.off_search_query,
        a.pack_amount,
        a.pack_unit,
        a.source AS alias_source,
        a.status AS alias_status,
        p.status AS product_status,
        a.hit_count,
        a.last_seen_at,
        a.created_at
    FROM product_aliases a
    JOIN products p ON p.id = a.product_id
    LEFT JOIN stores st ON st.id = a.store_id
    LEFT JOIN subcategories sub ON sub.id = p.subcategory_id
    LEFT JOIN categories cat ON cat.id = sub.category_id
"""


def get_alias_by_id(
    alias_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return an enriched product alias by ID, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"{_ALIAS_SELECT_SQL} WHERE a.id = ?;", (alias_id,))
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None


def lookup_alias(
    raw_name: str,
    store_id: int | None = None,
    allow_cross_store: bool = True,
    increment_hit: bool = False,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Look up a normalized receipt item in the active alias cache.

    Priority:
        1. Exact ``(store_id, raw_name_norm)`` match for the current store.
        2. Global ``(store_id IS NULL, raw_name_norm)`` match.
        3. Highest-hit match across other stores when ``allow_cross_store=True``.
    """
    raw_norm = normalize_raw_item_name(raw_name)
    if not raw_norm:
        return None

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        if store_id is not None and not allow_cross_store:
            sql = f"""
                {_ALIAS_SELECT_SQL}
                WHERE a.raw_name_norm = ?
                  AND (a.store_id = ? OR a.store_id IS NULL)
                  AND a.status IN ('auto', 'confirmed')
                  AND p.status IN ('auto', 'confirmed')
                ORDER BY CASE WHEN a.store_id = ? THEN 0 ELSE 1 END, a.hit_count DESC
                LIMIT 1;
            """
            cursor.execute(sql, (raw_norm, store_id, store_id))
        else:
            sql = f"""
                {_ALIAS_SELECT_SQL}
                WHERE a.raw_name_norm = ?
                  AND a.status IN ('auto', 'confirmed')
                  AND p.status IN ('auto', 'confirmed')
                ORDER BY
                    CASE
                        WHEN ? IS NOT NULL AND a.store_id = ? THEN 0
                        WHEN a.store_id IS NULL THEN 1
                        ELSE 2
                    END,
                    CASE WHEN a.status = 'confirmed' THEN 0 ELSE 1 END,
                    a.hit_count DESC
                LIMIT 1;
            """
            cursor.execute(sql, (raw_norm, store_id, store_id))

        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        if row is None:
            return None

        matched = dict(zip(cols, row))
        if increment_hit:
            now = datetime.now().replace(microsecond=0).isoformat()
            cursor.execute(
                "UPDATE product_aliases SET hit_count = hit_count + 1, last_seen_at = ? WHERE id = ?;",
                (now, matched["alias_id"]),
            )
            matched["hit_count"] = int(matched["hit_count"]) + 1
            matched["last_seen_at"] = now

        return matched


def upsert_alias(
    raw_name: str,
    product_id: int,
    store_id: int | None = None,
    brand: str | None = None,
    off_search_query: str | None = None,
    pack_amount: float | None = None,
    pack_unit: str | None = None,
    source: str = "llm",
    status: str = "auto",
    increment_hit_on_conflict: bool = True,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create or update a ``(store_id, raw_name_norm) -> product_id`` alias mapping.

    Human-confirmed aliases (``status='confirmed'``) are never overwritten by automatic LLM calls.
    """
    raw_norm = normalize_raw_item_name(raw_name)
    if not raw_norm:
        raise ValueError("Normalized raw_name cannot be empty.")

    now = datetime.now().replace(microsecond=0).isoformat()
    clean_brand = brand.strip() if brand and brand.strip() else None
    clean_off = off_search_query.strip() if off_search_query and off_search_query.strip() else None
    clean_pack_unit = pack_unit.strip().lower() if pack_unit and pack_unit.strip() else None

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, status, hit_count
            FROM product_aliases
            WHERE COALESCE(store_id, 0) = COALESCE(?, 0)
              AND raw_name_norm = ?
            LIMIT 1;
            """,
            (store_id, raw_norm),
        )
        existing = cursor.fetchone()

        if existing is None:
            cursor.execute(
                """
                INSERT INTO product_aliases (
                    store_id, raw_name_original, raw_name_norm, product_id,
                    brand, off_search_query, pack_amount, pack_unit,
                    source, status, hit_count, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
                """,
                (
                    store_id,
                    raw_name.strip(),
                    raw_norm,
                    int(product_id),
                    clean_brand,
                    clean_off,
                    pack_amount,
                    clean_pack_unit,
                    source,
                    status,
                    now,
                ),
            )
            alias_id = int(cursor.lastrowid)
        else:
            alias_id = int(existing[0])
            existing_status = str(existing[1])
            new_hits = int(existing[2]) + (1 if increment_hit_on_conflict else 0)
            human_override = source in ("user", "admin")

            if existing_status == "confirmed" and not human_override:
                # Preserve human-confirmed mapping; only bump hit counter and fill missing OFF metadata
                cursor.execute(
                    """
                    UPDATE product_aliases
                    SET hit_count = ?,
                        last_seen_at = ?,
                        brand = COALESCE(brand, ?),
                        off_search_query = COALESCE(off_search_query, ?)
                    WHERE id = ?;
                    """,
                    (new_hits, now, clean_brand, clean_off, alias_id),
                )
            else:
                new_status = "confirmed" if human_override else status
                cursor.execute(
                    """
                    UPDATE product_aliases
                    SET product_id = ?,
                        brand = COALESCE(?, brand),
                        off_search_query = COALESCE(?, off_search_query),
                        pack_amount = COALESCE(?, pack_amount),
                        pack_unit = COALESCE(?, pack_unit),
                        source = ?,
                        status = ?,
                        hit_count = ?,
                        last_seen_at = ?
                    WHERE id = ?;
                    """,
                    (
                        int(product_id),
                        clean_brand,
                        clean_off,
                        pack_amount,
                        clean_pack_unit,
                        source,
                        new_status,
                        new_hits,
                        now,
                        alias_id,
                    ),
                )

    saved = get_alias_by_id(alias_id, database_path=database_path)
    assert saved is not None
    return saved


def list_aliases(
    product_id: int | None = None,
    store_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return product aliases with optional filters."""
    query = f"{_ALIAS_SELECT_SQL} WHERE 1 = 1"
    params: list[Any] = []
    if product_id is not None:
        query += " AND a.product_id = ?"
        params.append(int(product_id))
    if store_id is not None:
        query += " AND a.store_id = ?"
        params.append(int(store_id))
    if status is not None:
        query += " AND a.status = ?"
        params.append(status)
    query += " ORDER BY a.hit_count DESC, a.id DESC LIMIT ? OFFSET ?;"
    params.extend([int(limit), int(offset)])

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def query_aliases(
    q: str | None = None,
    product_id: int | None = None,
    store_id: int | None = None,
    status: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Search and filter receipt aliases across raw names, clean products, brands, and OFF queries."""
    query = f"{_ALIAS_SELECT_SQL} WHERE 1 = 1"
    params: list[Any] = []
    if product_id is not None:
        query += " AND a.product_id = ?"
        params.append(int(product_id))
    if store_id is not None:
        query += " AND a.store_id = ?"
        params.append(int(store_id))
    if status and status.strip():
        query += " AND a.status = ?"
        params.append(status.strip().lower())
    if source and source.strip():
        query += " AND LOWER(a.source) = ?"
        params.append(source.strip().lower())

    if q and q.strip():
        raw_text = q.strip()
        norm_raw = normalize_raw_item_name(raw_text)
        norm_clean = normalize_clean_product_name(raw_text)
        like_raw = f"%{norm_raw}%" if norm_raw else f"%{raw_text.upper()}%"
        like_clean = f"%{norm_clean}%" if norm_clean else f"%{raw_text.lower()}%"
        like_lower = f"%{raw_text.lower()}%"
        query += """
            AND (
                a.raw_name_norm LIKE ?
                OR LOWER(a.raw_name_original) LIKE ?
                OR p.name_pl_norm LIKE ?
                OR p.name_en_norm LIKE ?
                OR LOWER(COALESCE(a.brand, '')) LIKE ?
                OR LOWER(COALESCE(a.off_search_query, '')) LIKE ?
                OR LOWER(COALESCE(st.display_name, '')) LIKE ?
            )
        """
        params.extend(
            [like_raw, like_lower, like_clean, like_clean, like_lower, like_lower, like_lower]
        )

    query += " ORDER BY a.hit_count DESC, a.id DESC LIMIT ? OFFSET ?;"
    params.extend([int(limit), int(offset)])

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def update_alias(
    alias_id: int,
    database_path: str | Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update an existing alias mapping (e.g. re-point product_id, edit brand/OFF query, confirm status)."""
    existing = get_alias_by_id(alias_id, database_path=database_path)
    if existing is None:
        return None

    if "product_id" in fields and fields["product_id"] is not None:
        target_prod = get_product_by_id(int(fields["product_id"]), database_path=database_path)
        if target_prod is None:
            raise ValueError(f"Target product #{fields['product_id']} not found.")
        fields["product_id"] = int(fields["product_id"])

    for nullable_str in ("brand", "off_search_query", "pack_unit"):
        if nullable_str in fields and fields[nullable_str] is not None:
            cleaned = str(fields[nullable_str]).strip()
            if nullable_str == "pack_unit":
                cleaned = cleaned.lower()
            fields[nullable_str] = cleaned if cleaned else None

    if "status" not in fields or fields["status"] is None:
        fields["status"] = "confirmed"
    if "source" not in fields or fields["source"] is None:
        fields["source"] = "admin"

    allowed = {
        "product_id",
        "store_id",
        "brand",
        "off_search_query",
        "pack_amount",
        "pack_unit",
        "status",
        "source",
    }
    updates: list[str] = []
    params: list[Any] = []
    for col, val in fields.items():
        if col in allowed:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return existing

    params.append(int(alias_id))
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE product_aliases SET {', '.join(updates)} WHERE id = ?;",
            params,
        )
        # If product_id changed and receipt_items tracks alias_id, sync historical receipt_items.product_id
        if "product_id" in fields and fields["product_id"] is not None:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='receipt_items';"
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE receipt_items SET product_id = ? WHERE alias_id = ?;",
                    (int(fields["product_id"]), int(alias_id)),
                )

    return get_alias_by_id(alias_id, database_path=database_path)


def approve_alias(
    alias_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Mark an ``auto`` alias (and its parent ``auto`` product if needed) as ``confirmed``."""
    updated = update_alias(alias_id, status="confirmed", database_path=database_path)
    if updated is not None and updated.get("product_status") == "auto":
        update_product(int(updated["product_id"]), status="confirmed", database_path=database_path)
        updated = get_alias_by_id(alias_id, database_path=database_path)
    return updated


def delete_alias(
    alias_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a product alias from the OCR cache."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_aliases WHERE id = ?;", (int(alias_id),))
        return cursor.rowcount > 0


def merge_products(
    source_product_id: int,
    target_product_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge duplicate ``source_product_id`` into ``target_product_id``, re-pointing all aliases."""
    if source_product_id == target_product_id:
        raise ValueError("Cannot merge a product into itself.")

    target = get_product_by_id(target_product_id, database_path=database_path)
    if target is None:
        raise ValueError(f"Target product #{target_product_id} not found.")
    source = get_product_by_id(source_product_id, database_path=database_path)
    if source is None:
        raise ValueError(f"Source product #{source_product_id} not found.")

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='receipt_items';"
        )
        has_receipt_items = cursor.fetchone() is not None

        cursor.execute(
            "SELECT id, store_id, raw_name_norm, hit_count FROM product_aliases WHERE product_id = ?;",
            (source_product_id,),
        )
        for alias_id, store_id, raw_norm, hits in cursor.fetchall():
            cursor.execute(
                """
                SELECT id, hit_count FROM product_aliases
                WHERE product_id = ?
                  AND COALESCE(store_id, 0) = COALESCE(?, 0)
                  AND raw_name_norm = ?
                LIMIT 1;
                """,
                (target_product_id, store_id, raw_norm),
            )
            conflict = cursor.fetchone()
            if conflict:
                cursor.execute(
                    "UPDATE product_aliases SET hit_count = hit_count + ? WHERE id = ?;",
                    (int(hits), int(conflict[0])),
                )
                if has_receipt_items:
                    cursor.execute(
                        "UPDATE receipt_items SET alias_id = ? WHERE alias_id = ?;",
                        (int(conflict[0]), int(alias_id)),
                    )
                cursor.execute("DELETE FROM product_aliases WHERE id = ?;", (int(alias_id),))
            else:
                cursor.execute(
                    "UPDATE product_aliases SET product_id = ? WHERE id = ?;",
                    (target_product_id, int(alias_id)),
                )

        if has_receipt_items:
            cursor.execute(
                "UPDATE receipt_items SET product_id = ? WHERE product_id = ?;",
                (target_product_id, source_product_id),
            )

        if source.get("status") == "confirmed" and target.get("status") == "auto":
            cursor.execute(
                "UPDATE products SET status = 'confirmed' WHERE id = ?;",
                (target_product_id,),
            )

        cursor.execute("DELETE FROM products WHERE id = ?;", (source_product_id,))

    merged = get_product_by_id(target_product_id, database_path=database_path)
    assert merged is not None
    return merged


def get_catalog_stats(database_path: str | Path | None = None) -> dict[str, Any]:
    """Return summary counts for products, aliases, cache hit efficiency, stores, and pending items."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products;")
        products_total = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'confirmed';")
        products_confirmed = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'auto';")
        products_auto = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending';")
        products_pending = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM product_aliases;")
        alias_row = cursor.fetchone()
        aliases_total = int(alias_row[0])
        total_alias_hits = int(alias_row[1])

        cursor.execute("SELECT COUNT(*) FROM product_aliases WHERE status = 'confirmed';")
        aliases_confirmed = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM product_aliases WHERE status = 'auto';")
        aliases_auto = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM stores;")
        stores_total = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM categories WHERE status = 'pending';")
        pending_cats = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM subcategories WHERE status = 'pending';")
        pending_subs = int(cursor.fetchone()[0])

    repeat_cache_hits = max(0, total_alias_hits - aliases_total)
    cache_hit_rate_pct = (
        round((repeat_cache_hits / total_alias_hits) * 100.0, 1) if total_alias_hits > 0 else 0.0
    )
    pending_taxonomy_count = pending_cats + pending_subs

    return {
        "products_total": products_total,
        "products_active": products_confirmed + products_auto,
        "products_confirmed": products_confirmed,
        "products_auto": products_auto,
        "products_pending": products_pending,
        "aliases_total": aliases_total,
        "aliases_confirmed": aliases_confirmed,
        "aliases_auto": aliases_auto,
        "total_alias_hits": total_alias_hits,
        "repeat_cache_hits": repeat_cache_hits,
        "cache_hit_rate_pct": cache_hit_rate_pct,
        "stores_total": stores_total,
        "pending_taxonomy_count": pending_taxonomy_count,
        "manual_user_pending_total": pending_taxonomy_count + products_pending,
    }
