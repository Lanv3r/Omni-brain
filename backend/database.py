from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BACKEND_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "omni_brain.sqlite3"
DATA_TABLES = ("tickets", "tasks", "alerts", "devices")


@contextmanager
def database_connection(
    database_path: str | Path | None = None,
) -> Iterator[sqlite3.Connection]:
    path = Path(
        database_path
        or os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    ).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path | None = None) -> None:
    with database_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_path.stem
            if version in applied:
                continue
            migration_sql = migration_path.read_text(encoding="utf-8")
            escaped_version = version.replace("'", "''")
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{migration_sql}\n"
                "INSERT INTO schema_migrations (version) "
                f"VALUES ('{escaped_version}');\nCOMMIT;"
            )


def list_records(
    table: str, database_path: str | Path | None = None
) -> list[dict[str, object]]:
    if table not in DATA_TABLES:
        raise ValueError(f"Unknown data table: {table}")
    with database_connection(database_path) as connection:
        rows = connection.execute(
            f"SELECT * FROM {table} ORDER BY display_order, id"
        ).fetchall()
    return [dict(row) for row in rows]


def dashboard_summary(database_path: str | Path | None = None) -> dict[str, int]:
    with database_connection(database_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in DATA_TABLES
        }
