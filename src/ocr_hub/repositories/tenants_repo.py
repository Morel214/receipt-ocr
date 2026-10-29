"""Repository for managing multi-bot tenants, API keys, and destination webhooks."""

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from ocr_hub import config
from ocr_hub.db.connection import get_connection
from ocr_hub.db.models import normalize_delivery_modes


def generate_api_key() -> str:
    """Generate a random bearer API key for a tenant."""
    return f"ocr_live_{secrets.token_hex(16)}"


def _row_to_tenant(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a raw SQLite row into an enriched tenant dictionary."""
    data = dict(zip(columns, row))
    raw_chat_ids = data.get("allowed_chat_ids") or ""
    data["allowed_chat_ids_list"] = [
        int(x.strip()) for x in str(raw_chat_ids).split(",") if x.strip().lstrip("-").isdigit()
    ]
    raw_subcats = data.get("subcategories_json")
    if raw_subcats:
        try:
            data["subcategories"] = json.loads(raw_subcats)
        except Exception:
            data["subcategories"] = list(config.DEFAULT_SUBCATEGORIES)
    else:
        data["subcategories"] = list(config.DEFAULT_SUBCATEGORIES)
    raw_modes = data.get("delivery_modes_json")
    if raw_modes is not None:
        try:
            parsed_modes = json.loads(raw_modes)
            data["delivery_modes"] = (
                normalize_delivery_modes(parsed_modes)
                if isinstance(parsed_modes, list)
                else ["webhook"]
            )
        except Exception:
            data["delivery_modes"] = ["webhook"]
    else:
        data["delivery_modes"] = ["webhook"]
    data["is_active"] = bool(data.get("is_active", 1))
    return data


def create_tenant(
    name: str,
    telegram_bot_token: str | None = None,
    allowed_chat_ids: list[int] | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    default_currency: str = "EUR",
    language: str = "en",
    delivery_modes: list[str] | None = None,
    subcategories: list[str] | None = None,
    ocr_provider: str | None = None,
    ocr_model: str | None = None,
    classifier_provider: str | None = None,
    classifier_model: str | None = None,
    api_key: str | None = None,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Register a new tenant and return its persisted record."""
    key = api_key or generate_api_key()
    chat_ids_str = ",".join(str(cid) for cid in (allowed_chat_ids or []))
    subcats_json = (
        json.dumps(subcategories, ensure_ascii=False) if subcategories is not None else None
    )
    modes_list = (
        normalize_delivery_modes(delivery_modes) if delivery_modes is not None else ["webhook"]
    )
    modes_json = json.dumps(modes_list, ensure_ascii=False)
    clean_token = (
        telegram_bot_token.strip()
        if telegram_bot_token and telegram_bot_token.strip()
        else None
    )

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tenants (
                name, api_key, telegram_bot_token, allowed_chat_ids,
                webhook_url, webhook_secret, default_currency, language,
                delivery_modes_json, subcategories_json, ocr_provider, ocr_model,
                classifier_provider, classifier_model, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                name.strip(),
                key,
                clean_token,
                chat_ids_str,
                webhook_url.strip() if webhook_url else None,
                webhook_secret.strip() if webhook_secret else None,
                default_currency.strip().upper(),
                language.strip().lower(),
                modes_json,
                subcats_json,
                ocr_provider.strip().lower() if ocr_provider else None,
                ocr_model.strip() if ocr_model else None,
                classifier_provider.strip().lower() if classifier_provider else None,
                classifier_model.strip() if classifier_model else None,
            ),
        )
        tenant_id = int(cursor.lastrowid)

    tenant = get_tenant_by_id(tenant_id, database_path=database_path)
    assert tenant is not None
    return tenant


def get_tenant_by_id(
    tenant_id: int,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a tenant by ID, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?;", (tenant_id,))
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return _row_to_tenant(columns, row) if row else None


def get_tenant_by_api_key(
    api_key: str,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return an active tenant matching ``api_key``, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tenants WHERE api_key = ? AND is_active = 1;",
            (api_key.strip(),),
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return _row_to_tenant(columns, row) if row else None


def get_tenant_by_name(
    name: str,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return a tenant by unique name, or None."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tenants WHERE LOWER(TRIM(name)) = LOWER(TRIM(?));",
            (name,),
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return _row_to_tenant(columns, row) if row else None


def list_tenants(
    only_active: bool = False,
    database_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return all tenants, optionally filtered to active ones."""
    query = "SELECT * FROM tenants"
    if only_active:
        query += " WHERE is_active = 1"
    query += " ORDER BY id ASC;"
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        return [_row_to_tenant(columns, row) for row in cursor.fetchall()]


def update_tenant(
    tenant_id: int,
    database_path: str | Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update selected configuration fields on a tenant and return the updated record."""
    allowed_columns = {
        "name",
        "telegram_bot_token",
        "allowed_chat_ids",
        "webhook_url",
        "webhook_secret",
        "default_currency",
        "language",
        "delivery_modes_json",
        "subcategories_json",
        "ocr_provider",
        "ocr_model",
        "classifier_provider",
        "classifier_model",
        "is_active",
    }
    updates: list[str] = []
    params: list[Any] = []

    if "delivery_modes" in fields:
        modes = fields.pop("delivery_modes")
        if modes is not None:
            fields["delivery_modes_json"] = json.dumps(
                normalize_delivery_modes(modes), ensure_ascii=False
            )

    if "subcategories" in fields:
        subcats = fields.pop("subcategories")
        fields["subcategories_json"] = (
            json.dumps(subcats, ensure_ascii=False) if subcats is not None else None
        )

    if "allowed_chat_ids" in fields and isinstance(fields["allowed_chat_ids"], list):
        fields["allowed_chat_ids"] = ",".join(str(x) for x in fields["allowed_chat_ids"])

    if "telegram_bot_token" in fields and fields["telegram_bot_token"] is not None:
        tok = str(fields["telegram_bot_token"]).strip()
        fields["telegram_bot_token"] = tok if tok else None

    if "is_active" in fields and isinstance(fields["is_active"], bool):
        fields["is_active"] = 1 if fields["is_active"] else 0

    for col, val in fields.items():
        if col in allowed_columns:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return get_tenant_by_id(tenant_id, database_path=database_path)

    updates.append("updated_at = ?")
    params.append(datetime.now().replace(microsecond=0).isoformat())
    params.append(tenant_id)

    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE tenants SET {', '.join(updates)} WHERE id = ?;",
            params,
        )

    return get_tenant_by_id(tenant_id, database_path=database_path)


def delete_tenant(
    tenant_id: int,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a tenant and its cascaded jobs."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tenants WHERE id = ?;", (tenant_id,))
        return cursor.rowcount > 0


def bootstrap_default_tenant(
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Ensure the default bootstrap tenant from environment variables exists if configured."""
    if not (config.DEFAULT_TELEGRAM_BOT_TOKEN or config.DEFAULT_WEBHOOK_URL):
        return None

    name = config.DEFAULT_TENANT_NAME or "admin"
    existing = get_tenant_by_name(name, database_path=database_path)
    chat_ids = [
        int(x.strip())
        for x in config.DEFAULT_ALLOWED_CHAT_IDS.split(",")
        if x.strip().lstrip("-").isdigit()
    ]
    if existing is None:
        return create_tenant(
            name=name,
            telegram_bot_token=config.DEFAULT_TELEGRAM_BOT_TOKEN or None,
            allowed_chat_ids=chat_ids,
            webhook_url=config.DEFAULT_WEBHOOK_URL or None,
            webhook_secret=config.DEFAULT_WEBHOOK_SECRET or None,
            database_path=database_path,
        )
    return existing
