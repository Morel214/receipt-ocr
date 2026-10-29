"""Database schema definition and initialization for Receipt OCR Hub."""

from pathlib import Path

from ocr_hub.db.connection import get_connection
from ocr_hub.db.migrations import run_migrations


def init_db(database_path: str | Path | None = None) -> None:
    """Initialize tenants and receipt_jobs tables and indexes."""
    with get_connection(database_path) as conn:
        cursor = conn.cursor()

        # Tenants table: each user/bot configuration
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                api_key TEXT NOT NULL UNIQUE,
                telegram_bot_token TEXT UNIQUE,
                allowed_chat_ids TEXT DEFAULT '',
                webhook_url TEXT,
                webhook_secret TEXT,
                default_currency TEXT NOT NULL DEFAULT 'EUR',
                language TEXT NOT NULL DEFAULT 'en',
                subcategories_json TEXT,
                ocr_provider TEXT,
                ocr_model TEXT,
                classifier_provider TEXT,
                classifier_model TEXT,
                delivery_modes_json TEXT NOT NULL DEFAULT '["webhook"]',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Idempotent migration for existing databases
        cursor.execute("PRAGMA table_info(tenants)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "classifier_provider" not in existing_cols:
            cursor.execute("ALTER TABLE tenants ADD COLUMN classifier_provider TEXT;")
        if "classifier_model" not in existing_cols:
            cursor.execute("ALTER TABLE tenants ADD COLUMN classifier_model TEXT;")

        # Receipt jobs queue scoped to each tenant
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS receipt_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                batch_id TEXT,
                telegram_chat_id TEXT NOT NULL,
                telegram_message_id INTEGER,
                original_filename TEXT,
                image_path TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                ocr_json TEXT,
                store_name TEXT,
                transaction_date TEXT,
                total_amount REAL,
                currency TEXT,
                items_json TEXT,
                confidence REAL,
                is_duplicate INTEGER NOT NULL DEFAULT 0,
                webhook_delivered INTEGER NOT NULL DEFAULT 0,
                webhook_response_code INTEGER,
                last_error TEXT,
                prompt_sent_at DATETIME,
                last_prompt_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
            );
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenants_api_key ON tenants(api_key);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_tenant_status ON receipt_jobs(tenant_id, status);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_tenant_batch ON receipt_jobs(tenant_id, batch_id);"
        )

        # Apply versioned schema migrations (global taxonomy, catalog, etc.)
        run_migrations(conn)
