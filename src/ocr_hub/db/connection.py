"""SQLite connection management with foreign key enforcement."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from ocr_hub import config


@contextmanager
def get_connection(
    database_path: str | Path | None = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Yield a transactional SQLite connection with foreign keys enabled."""
    db_file = Path(database_path) if database_path is not None else config.DB_PATH
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
