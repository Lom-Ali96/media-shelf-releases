"""Official trade-site search *links* (PoE1). The app never runs searches and
never reads prices from the trade site: it only builds a URL that the user
opens in their own browser.

To pre-fill mod filters it needs the trade site's stat ids. Those come from the
public static list /api/trade/data/stats, downloaded once and again only when
the imported game data version changes (cached in data/trade_stats.json).
Verified 2026-11-26: list reachable, league ids match poe.ninja names ("Covens"),
and the ?q= link opens with all filters applied (when already logged in).
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

import httpx

from .. import config
from ..engine.item import ItemState, ItemView, _tier_family
from ..engine.modpool import eligible_pool
from ..knowledge.gamedata import GameData

STATS_URL = "https://www.pathofexile.com/api/trade/data/stats"
SEARCH_URL = "https://www.pathofexile.com/trade/search/{league}?q={query}"
CACHE = config.DATA_DIR / "trade_stats.json"

_RANGE = re.compile(r"\(([-\d.]+)-([-\d.]+)\)")
_NUM = re.compile(r"[-\d.]*\d")


class TradeError(Exception):
    pass


def load_stats(game_version: str, client: httpx.Client | None = None) -> dict[str, str]:
    """explicit stat text -> trade id, e.g. '+# to maximum Life' -> 'explicit.stat_3299347043'."""
    if CACHE.exists():
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached.get("game_version") == game_version:
            return cached["explicit"]
    client = client or httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT})
    r = client.get(STATS_URL)
    if r.status_code != 200:
        raise TradeError(f"trade stat list not available (HTTP {r.status_code})")
    groups = {g.get("id"): g for g in (r.json().get("result") or [])}
    if "explicit" not in groups:
        raise TradeError("unexpected trade stat list: no 'explicit' group")
    explicit = {e["text"]: e["id"] for e in groups["explicit"].get("entries", []) if "text" in e and "id" in e}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"game_version": game_version, "explicit": explicit}), encoding="utf-8")
    return explicit


def _pattern(line: str) -> str:
    return _NUM.sub("#", _RANGE.sub("#", line))


def _first_number(line: str) -> float | None:
    m = _RANGE.search(line)
    if m:
        return float(m.group(1))
    m = _NUM.search(line)
    return float(m.group(0)) if m else None


_ELEMENTAL = re.compile(r"^local_(minimum|maximum)_added_(fire|cold|lightning)_damage$")


def stat_filters(gd: GameData, item: ItemState, wants: list, explicit: dict[str, str]) -> tuple[list[dict], list[str], float | None]:
    """Trade filters for the wanted (non-bench) mods, plus a minimum Elemental DPS.

    A single-value line gets a minimum from the worst accepted tier. 'Adds # to #'
    lines get no stat minimum (how the site combines the two values is not
    verified); for weapon fire/cold/lightning mods the lowest possible damage is
    instead turned into a minimum Elemental DPS (lowest rolls x base attacks per
    second: attack speed mods can only raise it, so it never hides a match)."""
    view = ItemView(gd, item)
    tags = view.tags()
    by_type = {}
    for e in eligible_pool(gd, item.with_(rarity="rare", explicits=())):
        by_type.setdefault(e.mod.type, e.mod)
    filters, notes = [], []
    edps = 0.0
    for w in wants:
        if w.bench:
            notes.append(f"{w.mod_type}: left out, you craft it on the bench.")
            continue
        mod = by_type.get(w.mod_type)
        if mod is None:
            notes.append(f"{w.mod_type}: cannot roll on this base, left out.")
            continue
        family = [gd.mods[i] for i in _tier_family(gd, view.base, mod, frozenset(tags))]
        worst = family[min(w.max_tier, len(family)) - 1] if family else mod
        local = any(s.startswith("local_") for s, _, _ in mod.stats)
        elemental = [lo for s, lo, _ in worst.stats if _ELEMENTAL.match(s)]
        if view.base.attack_time_ms and len(elemental) == 2:
            edps += sum(elemental) / 2 * 1000 / view.base.attack_time_ms
        for line in worst.text.split("\n"):
            pat = _pattern(line)
            negative = " reduced " in f" {pat} "
            if negative:
                pat = pat.replace("reduced", "increased")
            tid = (explicit.get(f"{pat} (Local)") if local else None) or explicit.get(pat)
            if tid is None:
                notes.append(f"{w.mod_type}: no trade filter found for “{line}”, left out.")
                continue
            f = {"id": tid}
            if pat.count("#") == 1 and (n := _first_number(line)) is not None:
                f["value"] = {"max": -n} if negative else {"min": n}  # 'reduced' values are negative on the site
            elif pat.count("#") > 1 and len(elemental) != 2:
                notes.append(f"{w.mod_type}: filter without minimum (two-value mod).")
            filters.append(f)
    if edps:
        notes.append(f"Elemental DPS at least {edps:.0f} (lowest rolls of your accepted tiers, base attack speed).")
    return filters, notes, round(edps, 1) or None


def search_url(league: str, base_name: str, filters: list[dict], min_edps: float | None = None) -> str:
    query = {
        "query": {
            "status": {"option": "online"},
            "type": base_name,
            "stats": [{"type": "and", "filters": filters}],
            "filters": {"type_filters": {"filters": {"rarity": {"option": "nonunique"}}}},
        },
        "sort": {"price": "asc"},
    }
    if min_edps:
        query["query"]["filters"]["weapon_filters"] = {"filters": {"edps": {"min": min_edps}}}
    return SEARCH_URL.format(league=quote(league), query=quote(json.dumps(query, separators=(",", ":"))))
