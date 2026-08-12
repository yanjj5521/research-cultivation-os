from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from core.bootstrap import seed_clean_database
from core.schema import (
    BASE_SCHEMA_SQL,
    CLEAN_SCHEMA_VERSION,
    DATABASE_FILENAME,
    FTS_SCHEMA_SQL,
)
from runtime_paths import INSTANCE_DIR


DB_PATH = INSTANCE_DIR / DATABASE_FILENAME


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def transaction() -> Iterable[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with transaction() as connection:
        table_count = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchone()[0]
        )
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if table_count:
            if version != CLEAN_SCHEMA_VERSION:
                raise RuntimeError(
                    "This edition only accepts its own clean database. "
                    "Old databases are intentionally not migrated."
                )
            return

        connection.executescript(BASE_SCHEMA_SQL)
        try:
            connection.executescript(FTS_SCHEMA_SQL)
        except sqlite3.OperationalError:
            pass
        seed_clean_database(connection, now_iso)
        connection.execute(f"PRAGMA user_version = {CLEAN_SCHEMA_VERSION}")


def get_setting(key: str, default: str = "") -> str:
    with connect() as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO settings(key,value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )


def log_activity(
    action: str,
    xp: int,
    detail: str = "",
    entry_id: int | None = None,
) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO activities(action,entry_id,xp,detail,created_at)
            VALUES (?,?,?,?,?)
            """,
            (action, entry_id, xp, detail, now_iso()),
        )


def total_xp(connection: sqlite3.Connection | None = None) -> int:
    owns_connection = connection is None
    connection = connection or connect()
    try:
        row = connection.execute(
            "SELECT COALESCE(SUM(xp),0) AS xp FROM activities"
        ).fetchone()
        return int(row["xp"])
    finally:
        if owns_connection:
            connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None
