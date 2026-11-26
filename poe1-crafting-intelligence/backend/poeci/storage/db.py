"""Tiny SQLite layer with ordered SQL migrations (stdlib only)."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .. import config

MIGRATIONS = Path(__file__).with_name("migrations")


class _Result:
    """Rows fetched while the lock was held, so callers can read them afterwards."""

    def __init__(self, rows: list, lastrowid: int | None):
        self._rows, self.lastrowid = rows, lastrowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class LockedConnection:
    """One SQLite connection shared by the web server's worker threads.

    sqlite3 objects must not be used by two threads at once (the stress test got
    'bad parameter or other API misuse' and HTTP 500s), so every call runs under
    one lock and results are fully fetched before the lock is released."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, sql: str, params=()) -> _Result:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return _Result(cur.fetchall(), cur.lastrowid)

    def executemany(self, sql: str, seq) -> None:
        with self._lock:
            self._conn.executemany(sql, seq)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()


def connect(path: Path | str | None = None) -> LockedConnection:
    path = Path(path or config.DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    conn = LockedConnection(raw)
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: "LockedConnection") -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        conn.executescript(f.read_text())
        conn.execute("INSERT INTO schema_migrations(name) VALUES (?)", (f.name,))
        applied.append(f.name)
    conn.commit()
    return applied


def get_setting(conn: "LockedConnection", key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: "LockedConnection", key: str, value: str) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()
