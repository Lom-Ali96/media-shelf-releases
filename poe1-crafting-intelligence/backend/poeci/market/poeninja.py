"""poe.ninja economy adapter (PoE1).

Policy (from poe.ninja's API docs, as found by web search on 2026-11-26):
  * only the economy overview endpoints are meant for third-party use;
    builds/character/PoB endpoints are internal and are NOT used here;
  * there is no SLA or versioning, responses can change without notice;
  * excessive use gets clients blocked.
So this adapter: caches every response in SQLite, refuses to refetch the same
(league, category) more often than config.MARKET_CACHE_SECONDS, sends an
honest User-Agent, and validates the response shape defensively.

STATUS: verified live on 2026-11-26 (league "Covens"). poe.ninja had moved
from /api/data/{currency,item}overview to the two /poe1/api/economy/... endpoints
below; the old ones return 404. See API_INTEGRATIONS.md.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import httpx

from .. import config

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage import db

# Stackable goods traded on the currency exchange vs. items priced from stash listings.
EXCHANGE_CATEGORIES = {"Currency", "Fragment", "Essence", "Fossil", "Resonator", "Oil", "DeliriumOrb"}
STASH_ITEM_CATEGORIES = {
    "Beast", "BaseType", "ClusterJewel", "UniqueJewel", "UniqueAccessory", "UniqueArmour", "UniqueWeapon",
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
    if category in EXCHANGE_CATEGORIES:
        # Exchange payload: prices in `lines` keyed by id, names in `items`.
        core = payload.get("core") or {}
        if core.get("primary") != "chaos":
            raise MarketError(f"unexpected poe.ninja response: primary currency {core.get('primary')!r}, expected 'chaos'")
        names = {it.get("id"): it.get("name") for it in payload.get("items") or []}
        divine_rate = (core.get("rates") or {}).get("divine")
        for ln in lines:
            name, chaos = names.get(ln.get("id")), ln.get("primaryValue")
            if not name or chaos is None:
                continue
            # The exchange reports trade volume, not a listing count.
            rows.append({"name": name, "variant": None, "chaos_value": float(chaos),
                         "divine_value": float(chaos) * divine_rate if divine_rate else None, "listing_count": None})
        return rows
    for ln in lines:
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
    def __init__(self, conn: "db.LockedConnection", client: httpx.Client | None = None):
        self.conn = conn
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT})

    def _url(self, league: str, category: str) -> tuple[str, dict]:
        kind = "exchange/current/overview" if category in EXCHANGE_CATEGORIES else "stash/current/item/overview"
        return f"{config.POE_NINJA_BASE}/poe1/api/economy/{kind}", {"league": league, "type": category}

    def latest_snapshot(self, league: str, category: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM market_snapshots WHERE source='poe.ninja' AND league=? AND category=? ORDER BY id DESC LIMIT 1",
            (league, category),
        ).fetchone()

    def fetch(self, league: str, category: str, game_version: str | None = None, force: bool = False) -> int:
        """Fetch (or reuse cached) prices; returns the snapshot id."""
        if category not in EXCHANGE_CATEGORIES | STASH_ITEM_CATEGORIES:
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
            if not rows:  # poe.ninja answers 200 with empty lists for an unknown league
                raise MarketError(f"poe.ninja returned no {category} prices for league {league!r}; "
                                  "check the league name (poe.ninja uses short names, e.g. 'Covens')")
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


def price_of(conn: "db.LockedConnection", league: str, name: str) -> dict | None:
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


def set_override(conn: "db.LockedConnection", league: str, name: str, chaos_value: float, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO price_overrides(league, name, chaos_value, note, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(league, name) DO UPDATE SET chaos_value=excluded.chaos_value, note=excluded.note, updated_at=excluded.updated_at",
        (league, name, chaos_value, note, _now().isoformat()),
    )
    conn.commit()
