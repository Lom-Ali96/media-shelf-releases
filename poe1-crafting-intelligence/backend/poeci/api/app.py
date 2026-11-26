"""HTTP API + single-page UI. Start with:  python -m poeci  (see INSTALLATION.md)."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..engine.actions import ACTIONS, InvalidAction
from ..engine.item import ItemState, ItemView, UnsupportedMechanic, tier_index
from ..engine.modpool import eligible_pool
from ..engine.planner import Want, plan_routes
from ..engine.simulate import ModRequirement, Target, exact_next_mod_probability, simulate_repeat_until
from ..knowledge import importer
from ..knowledge.coverage import coverage_report
from ..knowledge.gamedata import GameData
from ..market import poeninja
from ..parsing.clipboard import ItemParser
from ..storage import db
from ..updates import versions

WEB = Path(__file__).parents[1] / "web" / "index.html"


class SettingsIn(BaseModel):
    league: str

class ParseIn(BaseModel):
    text: str

class Requirement(BaseModel):
    mod_type: str
    max_tier: int = 99

class SimIn(BaseModel):
    base: str
    item_level: int = 84
    rarity: str = "normal"
    influences: list[str] = Field(default_factory=list)
    item_text: str | None = None  # optional: start from a pasted item instead
    action: str
    params: dict = Field(default_factory=dict)
    target: list[Requirement]
    runs: int = Field(500, ge=1, le=20000)
    max_attempts: int = Field(1000, ge=1, le=20000)
    seed: int = 1

class WantIn(BaseModel):
    mod_type: str
    max_tier: int = 99
    bench: bool = False

class PlanIn(BaseModel):
    base: str
    item_level: int = Field(84, ge=1, le=100)
    influences: list[str] = Field(default_factory=list)
    wants: list[WantIn]
    seed: int = 1

class FetchIn(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["Currency", "Essence", "Fossil"])
    force: bool = False

class OverrideIn(BaseModel):
    name: str
    chaos_value: float
    note: str | None = None


class State:
    gd: GameData | None = None
    conn = None


def create_app(game_data: GameData | None = None, conn=None) -> FastAPI:
    app = FastAPI(title="PoE1 Crafting Intelligence", version=versions.ENGINE_VERSION)
    st = State()
    st.conn = conn or db.connect()
    if game_data is not None:
        st.gd = game_data
    else:
        snap = importer.latest_snapshot()
        st.gd = GameData.from_dir(snap) if snap else None

    def gd() -> GameData:
        if st.gd is None:
            raise HTTPException(503, "No game data imported. Run: python -m poeci.knowledge.importer")
        return st.gd

    def league() -> str:
        return db.get_setting(st.conn, "league", "") or ""

    # ------------------------------------------------------------ system
    @app.get("/", response_class=HTMLResponse)
    def index():
        return WEB.read_text(encoding="utf-8")

    @app.get("/api/status")
    def status():
        s = versions.status(st.conn, st.gd.version if st.gd else None)
        s["league"] = league() or None
        if not s["league"]:
            s["warnings"].append("No league selected (Settings). Market prices are per league.")
        if st.gd:
            s["game_data"] = st.gd.summary()
        return s

    @app.post("/api/updates/check")
    def check_updates():
        remote = versions.check_remote(st.conn)
        return {"remote_game_data": remote, "status": status()}

    @app.post("/api/settings")
    def save_settings(body: SettingsIn):
        db.set_setting(st.conn, "league", body.league.strip())
        return {"league": body.league.strip()}

    @app.get("/api/coverage")
    def coverage():
        return coverage_report(st.gd)

    # ------------------------------------------------------------ knowledge
    @app.get("/api/bases")
    def bases(q: str = "", limit: int = 50):
        return [
            {"id": b.id, "name": b.name, "item_class": b.item_class, "domain": b.domain, "drop_level": b.drop_level, "tags": b.tags}
            for b in gd().search_bases(q, limit)
        ]

    @app.get("/api/mods")
    def mods(q: str, limit: int = 100):
        return [
            {"id": m.id, "name": m.name, "text": m.text, "type": m.type, "generation_type": m.generation_type,
             "domain": m.domain, "required_level": m.required_level, "groups": m.groups, "tags": m.implicit_tags}
            for m in gd().search_mods(q, limit)
        ]

    @app.get("/api/modpool")
    def modpool(base: str, ilvl: int = 84, rarity: str = "rare", influences: str = ""):
        g = gd()
        b = g.bases_by_name.get(base) or g.bases.get(base)
        if b is None:
            raise HTTPException(404, f"unknown base {base!r}")
        infl = frozenset(i.strip().lower() for i in influences.split(",") if i.strip())
        item = ItemState(b.id, ilvl, rarity, influences=infl)
        tags = ItemView(g, item).tags()
        pool = eligible_pool(g, item)
        out = []
        for e in sorted(pool, key=lambda e: (e.mod.generation_type, e.mod.type, e.mod.required_level)):
            tier, ntiers = tier_index(g, b, e.mod, tags)
            out.append({"id": e.mod.id, "name": e.mod.name, "text": e.mod.text, "type": e.mod.type,
                        "affix": e.mod.generation_type, "tier": tier, "tiers": ntiers, "ilvl": e.mod.required_level,
                        "weight": e.weight, "probability": e.probability, "tags": e.mod.implicit_tags})
        return {"base": b.name, "item_class": b.item_class, "item_level": ilvl, "influences": sorted(infl),
                "tags": sorted(tags), "total_weight": sum(e.weight for e in pool), "mods": out,
                "probability_kind": "exact (normalised spawn weights from game data)"}

    # ------------------------------------------------------------ items
    @app.post("/api/items/parse")
    def parse_item(body: ParseIn):
        g = gd()
        parsed = ItemParser(g).parse(body.text)
        state = parsed.to_item_state()
        resp = asdict(parsed)
        for pm in resp["mods"]:
            if pm["mod_id"]:
                m = g.mods[pm["mod_id"]]
                pm["text"] = m.text
                pm["mod_type"] = m.type
        resp["item_state_complete"] = state is not None
        if state is not None:
            view = ItemView(g, state)
            resp["open_prefixes"] = view.open_slots("prefix")
            resp["open_suffixes"] = view.open_slots("suffix")
            resp["valid_actions"] = _valid_actions(g, state)
        return resp

    # ------------------------------------------------------------ simulation
    @app.post("/api/simulate")
    def simulate(body: SimIn):
        g = gd()
        if body.item_text:
            parsed = ItemParser(g).parse(body.item_text)
            start = parsed.to_item_state()
            if start is None:
                raise HTTPException(422, {"error": "item could not be fully identified", "warnings": parsed.warnings})
        else:
            b = g.bases_by_name.get(body.base) or g.bases.get(body.base)
            if b is None:
                raise HTTPException(404, f"unknown base {body.base!r}")
            start = ItemState(b.id, body.item_level, body.rarity, influences=frozenset(i.lower() for i in body.influences))
        target = Target([ModRequirement(r.mod_type, r.max_tier) for r in body.target])
        if body.runs * body.max_attempts > 5_000_000:
            raise HTTPException(422, "runs x max_attempts too large for an interactive request")
        try:
            res = simulate_repeat_until(g, start, body.action, target, runs=body.runs, max_attempts=body.max_attempts,
                                        seed=body.seed, params=body.params)
        except (InvalidAction, UnsupportedMechanic) as e:
            raise HTTPException(422, str(e))
        out = asdict(res)
        info = ACTIONS[body.action]
        price = poeninja.price_of(st.conn, league(), info.currency) if (info.currency and league()) else None
        out["price_per_attempt"] = price
        if price and res.attempts_mean is not None:
            out["expected_cost_chaos"] = res.attempts_mean * price["chaos_value"]
            out["p95_cost_chaos"] = (res.attempts_p95 or 0) * price["chaos_value"]
        if info.fn.__name__ in ("exalted", "regal", "augmentation"):
            try:
                out["exact_first_attempt_probability"] = exact_next_mod_probability(
                    g, start.with_(rarity="rare") if info.id == "regal" else start, target)
            except Exception:  # noqa: BLE001
                pass
        out["rules_verified_for_current_data"] = versions.status(st.conn, g.version)["rules_verified_for_current_data"]
        return out

    @app.post("/api/plan")
    def plan(body: PlanIn):
        g = gd()
        b = g.bases_by_name.get(body.base) or g.bases.get(body.base)
        if b is None:
            raise HTTPException(404, f"unknown base {body.base!r}")
        try:
            routes = plan_routes(g, b.id, body.item_level, [Want(w.mod_type, w.max_tier, w.bench) for w in body.wants],
                                 influences=frozenset(i.lower() for i in body.influences), seed=body.seed)
        except (InvalidAction, UnsupportedMechanic) as e:
            raise HTTPException(422, str(e))
        lg = league()
        prices: dict[str, dict | None] = {}

        def chaos_of(units: dict[str, float] | None) -> float | None:
            if not units:
                return None
            for name in units:
                if name not in prices:
                    prices[name] = poeninja.price_of(st.conn, lg, name) if lg else None
            if any(prices[n] is None for n in units):
                return None
            return sum(v * prices[n]["chaos_value"] for n, v in units.items())

        out = []
        for r in routes:
            d = asdict(r)
            d["expected_chaos"] = chaos_of(r.expected_units)
            d["range_chaos"] = [chaos_of(u) for u in r.units_range] if r.units_range else None
            d["at_least_chaos"] = chaos_of(r.at_least_units)
            d["missing_prices"] = sorted(n for n in (r.expected_units or r.at_least_units or {}) if prices.get(n) is None)
            out.append(d)
        out.sort(key=lambda d: (d["expected_chaos"] is None, d["expected_chaos"] or d["at_least_chaos"] or float("inf")))
        divine = poeninja.price_of(st.conn, lg, "Divine Orb") if lg else None
        base_price = poeninja.price_of(st.conn, lg, b.name) if lg else None
        return {"base": b.name, "routes": out, "divine_chaos": divine["chaos_value"] if divine else None,
                "base_price": base_price, "league": lg or None,
                "rules_verified_for_current_data": versions.status(st.conn, g.version)["rules_verified_for_current_data"]}

    @app.get("/api/actions")
    def actions():
        return [{"id": a.id, "name": a.name, "currency": a.currency, "status": a.status, "assumptions": a.assumptions}
                for a in ACTIONS.values()]

    @app.get("/api/essences")
    def essences(item_class: str | None = None):
        g = gd()
        out = []
        for _, e in g.essences.items():
            mid = (e.get("mods") or {}).get(item_class) if item_class else None
            if item_class and not mid:
                continue
            out.append({"name": e["name"], "level": e.get("level"), "max_item_level": e.get("item_level_restriction"),
                        "mod": g.mods[mid].text if mid and mid in g.mods else None})
        return sorted(out, key=lambda x: x["name"])

    # ------------------------------------------------------------ market
    @app.post("/api/market/fetch")
    def market_fetch(body: FetchIn):
        if not league():
            raise HTTPException(422, "select a league first")
        client = poeninja.PoeNinja(st.conn)
        done, errors = {}, {}
        for c in body.categories:
            try:
                done[c] = client.fetch(league(), c, st.gd.version if st.gd else None, force=body.force)
            except Exception as e:  # noqa: BLE001 - reported to the UI
                errors[c] = str(e)
        return {"snapshots": done, "errors": errors}

    @app.post("/api/market/override")
    def market_override(body: OverrideIn):
        if not league():
            raise HTTPException(422, "select a league first")
        poeninja.set_override(st.conn, league(), body.name, body.chaos_value, body.note)
        return poeninja.price_of(st.conn, league(), body.name)

    @app.get("/api/market/price")
    def market_price(name: str):
        p = poeninja.price_of(st.conn, league(), name)
        if p is None:
            raise HTTPException(404, "no price known")
        return p

    return app


def _valid_actions(g: GameData, item: ItemState) -> list[dict]:
    import random

    out = []
    for a in ACTIONS.values():
        if a.id in ("essence", "fossil", "bench_craft"):
            continue  # need parameters
        try:
            a.fn(g, item, random.Random(0))
            out.append({"id": a.id, "name": a.name, "valid": True})
        except (InvalidAction, UnsupportedMechanic) as e:
            out.append({"id": a.id, "name": a.name, "valid": False, "reason": str(e)})
    return out
