"""CSV and copyable text export helpers for confirmed receipts."""

import csv
import io
import re
from typing import Any

from ocr_hub.repositories.catalog_repo import fold_polish_ascii

CSV_COLUMNS = [
    "date",
    "store",
    "raw_name",
    "clean_name",
    "category",
    "subcategory",
    "quantity",
    "unit",
    "unit_price",
    "total_price",
    "currency",
]


def _iter_csv_rows(receipts: list[dict[str, Any]]) -> list[list[Any]]:
    """Convert one or more receipt dicts (from OCR result or receipts_repo) into flat CSV rows."""
    rows: list[list[Any]] = []
    for rec in receipts:
        txn_date = str(rec.get("transaction_date") or "")
        store_name = str(rec.get("store_name") or "Unknown Store")
        currency = str(rec.get("currency") or "PLN")
        items = rec.get("items") or []
        for item in items:
            raw_name = item.get("raw_name") or item.get("name") or ""
            clean_name = item.get("clean_name") or raw_name
            category = item.get("category_code") if "category_code" in item else item.get("category")
            subcategory = (
                item.get("subcategory_code")
                if "subcategory_code" in item
                else item.get("subcategory")
            )
            qty = float(item.get("quantity") if item.get("quantity") is not None else 1.0)
            unit = str(item.get("unit") or "pcs")
            unit_price = float(item.get("unit_price") or 0.0)
            total_price = float(item.get("total_price") or 0.0)
            rows.append(
                [
                    txn_date,
                    store_name,
                    raw_name,
                    clean_name,
                    category or "",
                    subcategory or "",
                    f"{qty:g}",
                    unit,
                    f"{unit_price:.2f}",
                    f"{total_price:.2f}",
                    currency,
                ]
            )
    return rows


def format_receipts_csv_text(receipts: list[dict[str, Any]]) -> str:
    """Serialize one or more receipts into a UTF-8 CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    writer.writerows(_iter_csv_rows(receipts))
    return buf.getvalue().strip()


def format_receipts_csv_bytes(receipts: list[dict[str, Any]]) -> bytes:
    """Serialize one or more receipts into UTF-8 CSV bytes for file download/Telegram upload."""
    return (format_receipts_csv_text(receipts) + "\n").encode("utf-8")


def format_receipt_copyable_text(receipt: dict[str, Any]) -> str:
    """Format a single confirmed receipt into a clean copy-pasteable CSV block."""
    return format_receipts_csv_text([receipt])


def build_receipt_csv_filename(receipt: dict[str, Any]) -> str:
    """Build a deterministic filename such as ``2026-10-28_biedronka_54-30.csv``."""
    txn_date = str(receipt.get("transaction_date") or "undated").strip() or "undated"
    raw_store = fold_polish_ascii(str(receipt.get("store_name") or "receipt")).lower()
    store_slug = re.sub(r"[^a-z0-9]+", "-", raw_store).strip("-") or "receipt"
    total_amount = float(receipt.get("total_amount") or 0.0)
    amount_slug = f"{total_amount:.2f}".replace(".", "-")
    return f"{txn_date}_{store_slug}_{amount_slug}.csv"
