import os
import sqlite3
from pathlib import Path


def get_db_path() -> str:
    """Resolve the active database path, allowing tests and local runs to override it."""
    return os.getenv("RECEIPTS_DB_PATH", str(Path(__file__).resolve().parent / "data" / "receipts.db"))


def ensure_database_and_table() -> str:
    """Create the data directory and database table if they do not already exist."""
    db_path = get_db_path()
    db_dir = Path(db_path).resolve().parent
    db_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id TEXT NOT NULL UNIQUE,
            sequence_no INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            current_hash TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


def get_connection() -> sqlite3.Connection:
    """Return a live database connection for application use."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn
