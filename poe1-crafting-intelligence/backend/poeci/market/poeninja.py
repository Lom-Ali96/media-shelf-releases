"""poe.ninja economy adapter (PoE1).

Policy (from poe.ninja's API docs, as found by web search on 2026-11-26):
  * only the economy overview endpoints are meant for third-party use;
    builds/character/PoB endpoints are internal and are NOT used here;
  * there is no SLA or versioning, responses can change without notice;
  * excessive use gets clients blocked.
So this adapter: caches every response in SQLite, refuses to refetch the same
(league, category) more often than config.MARKET_CACHE_SECONDS, sends an
honest User-Agent, and validates the response shape defensively.

STATUS: response parsing is tested against recorded sample payloads only. It
has not been run against the live API from the development container (network
policy blocked poe.ninja there). Verify on first use - see API_INTEGRATIONS.md.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import httpx

from .. import config

CURRENCY_CATEGORIES = {"Currency", "Fragment"}
ITEM_CATEGORIES = {
    "Essence", "Fossil", "Resonator", "Beast", "Oil", "DeliriumOrb",
    "BaseType", "ClusterJewel", "UniqueJewel", "UniqueAccessory", "UniqueArmour", "UniqueWeapon",
}
_lock = threading.Lock()


class MarketError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_overview(category: str, payload: dict) -> list[dict]:
    """Normalise a poe.ninja overview payload into price rows."""
    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise MarketError("unexpected poe.ninja response: no 'lines' list")
    rows = []
    for ln in lines:
        if category in CURRENCY_CATEGORIES:
            name = ln.get("currencyTypeName")
            chaos = ln.get("chaosEquivalent")
            listing = (ln.get("receive") or {}).get("listing_count")
            divine = None
            variant = None
        else:
            name = ln.get("name")
            chaos = ln.get("chaosValue")
            divine = ln.get("divineValue")
            listing = ln.get("listingCount")
            variant = ln.get("variant") or (str(ln["levelRequired"]) if ln.get("levelRequired") else None)
        if not name or chaos is None:
            continue
        rows.append({"name": name, "variant": variant, "chaos_value": float(chaos), "divine_value": divine, "listing_count": listing})
    return rows


class PoeNinja:
    def __init__(self, conn: sqlite3.Connection, client: httpx.Client | None = None):
        self.conn = conn
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT})

    def _url(self, league: str, category: str) -> tuple[str, dict]:
        kind = "currencyoverview" if category in CURRENCY_CATEGORIES else "itemoverview"
        return f"{config.POE_NINJA_BASE}/api/data/{kind}", {"league": league, "type": category}

    def latest_snapshot(self, league: str, category: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM market_snapshots WHERE source='poe.ninja' AND league=? AND category=? ORDER BY id DESC LIMIT 1",
            (league, category),
        ).fetchone()

    def fetch(self, league: str, category: str, game_version: str | None = None, force: bool = False) -> int:
        """Fetch (or reuse cached) prices; returns the snapshot id."""
        if category not in CURRENCY_CATEGORIES | ITEM_CATEGORIES:
            raise MarketError(f"unsupported category {category!r}")
        with _lock:
            last = self.latest_snapshot(league, category)
            if last is not None and not force:
                age = _now() - datetime.fromisoformat(last["fetched_at"])
                if age < timedelta(seconds=config.MARKET_CACHE_SECONDS):
                    return last["id"]
            url, params = self._url(league, category)
            r = self.client.get(url, params=params)
            if r.status_code == 429:
                raise MarketError("poe.ninja rate limit hit (HTTP 429); using cached data until it clears")
            r.raise_for_status()
            payload = r.json()
            rows = parse_overview(category, payload)
            return self.store(league, category, payload, rows, game_version, source="poe.ninja")

    def store(self, league, category, payload, rows, game_version, source) -> int:
        cur = self.conn.execute(
            "INSERT INTO market_snapshots(fetched_at, source, league, category, game_version, payload) VALUES (?,?,?,?,?,?)",
            (_now().isoformat(), source, league, category, game_version, json.dumps(payload)),
        )
        sid = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO prices(snapshot_id, name, variant, chaos_value, divine_value, listing_count) VALUES (?,?,?,?,?,?)",
            [(sid, r["name"], r["variant"], r["chaos_value"], r["divine_value"], r["listing_count"]) for r in rows],
        )
        self.conn.commit()
        return sid


def price_of(conn: sqlite3.Connection, league: str, name: str) -> dict | None:
    """Best known chaos price for `name`: manual override first, then newest snapshot."""
    o = conn.execute("SELECT chaos_value, updated_at, note FROM price_overrides WHERE league=? AND name=?", (league, name)).fetchone()
    if o:
        return {"name": name, "chaos_value": o["chaos_value"], "source": "manual override", "as_of": o["updated_at"], "note": o["note"]}
    if name == "Chaos Orb":
        return {"name": name, "chaos_value": 1.0, "source": "definition", "as_of": None}
    row = conn.execute(
        """SELECT p.chaos_value, p.listing_count, s.fetched_at, s.source FROM prices p
           JOIN market_snapshots s ON s.id = p.snapshot_id
           WHERE s.league = ? AND p.name = ? ORDER BY s.id DESC LIMIT 1""",
        (league, name),
    ).fetchone()
    if not row:
        return None
    return {"name": name, "chaos_value": row["chaos_value"], "listing_count": row["listing_count"],
            "source": row["source"], "as_of": row["fetched_at"], "is_listing_price": True}


def set_override(conn: sqlite3.Connection, league: str, name: str, chaos_value: float, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO price_overrides(league, name, chaos_value, note, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(league, name) DO UPDATE SET chaos_value=excluded.chaos_value, note=excluded.note, updated_at=excluded.updated_at",
        (league, name, chaos_value, note, _now().isoformat()),
    )
    conn.commit()
