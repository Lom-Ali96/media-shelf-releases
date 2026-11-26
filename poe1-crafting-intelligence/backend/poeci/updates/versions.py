"""Patch awareness: compares imported game data, the newest available game data
and the patch the crafting rules were last reviewed for.

The rule is simple and strict: if the game data is from a newer major.minor patch
than the mechanics registry was reviewed against, every recommendation is flagged
`rules_unverified_for_patch` until someone reviews the registry and bumps
`verified_for_patch`. Nothing silently applies old rules to a new patch."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..knowledge import importer
from ..knowledge.coverage import load_registry

ENGINE_VERSION = "0.1.0"


def major_minor(version: str) -> str:
    parts = version.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else version


def _newer(a: str, b: str) -> bool:
    return importer._version_key(a) > importer._version_key(b)


def record_check(conn: sqlite3.Connection, kind: str, value: str, source: str) -> None:
    conn.execute(
        "INSERT INTO version_checks(checked_at, kind, value, source) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), kind, value, source),
    )
    conn.commit()


def last_check(conn: sqlite3.Connection, kind: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT checked_at, value, source FROM version_checks WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)
    ).fetchone()


def check_remote(conn: sqlite3.Connection) -> str | None:
    """Ask the RePoE export which game version it was generated from (one tiny
    text file). Returns None if offline; the failure is not fatal."""
    try:
        v = importer.fetch_remote_version()
    except Exception:  # noqa: BLE001 - network errors are reported via status()
        return None
    record_check(conn, "remote_game_data", v, "RePoE version.txt")
    return v


def status(conn: sqlite3.Connection, imported_version: str | None) -> dict:
    reg = load_registry()
    verified = reg["verified_for_patch"]
    remote = last_check(conn, "remote_game_data")
    market = conn.execute("SELECT MAX(fetched_at) FROM market_snapshots").fetchone()[0]
    warnings: list[str] = []
    rules_ok = True
    if imported_version is None:
        warnings.append("No game data imported yet. Run the importer (see INSTALLATION.md).")
        rules_ok = False
    else:
        if major_minor(imported_version) != verified:
            rules_ok = False
            warnings.append(
                f"Game data is patch {major_minor(imported_version)} but crafting rules were reviewed for {verified}. "
                "All recommendations are flagged until the mechanics registry is re-reviewed."
            )
        if remote and _newer(remote["value"], imported_version):
            warnings.append(f"Newer game data available: {remote['value']} (imported: {imported_version}).")
    if remote is None:
        warnings.append("Remote game-data version never checked (offline or not run yet).")
    if market is None:
        warnings.append("No market data fetched yet; costs cannot be priced.")
    return {
        "engine_version": ENGINE_VERSION,
        "imported_game_data": imported_version,
        "latest_known_remote_game_data": dict(remote) if remote else None,
        "mechanics_verified_for_patch": verified,
        "rules_verified_for_current_data": rules_ok,
        "latest_market_update": market,
        "community_research_update": None,
        "warnings": warnings,
    }
