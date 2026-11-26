"""HTTP API + single-page UI. Start with:  python -m poeci  (see INSTALLATION.md)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..engine.actions import ACTIONS, InvalidAction
from ..engine.item import ItemState, ItemView, UnsupportedMechanic, tier_index
from ..engine.modpool import eligible_pool
from ..engine.planner import BenchCraft, Want, plan_routes, simulate_recipe, worst_accepted_mods
from ..engine.recipe import cost_of, recipe_from_json
from ..engine.simulate import ModRequirement, Target, exact_next_mod_probability, simulate_repeat_until
from ..knowledge import importer
from ..knowledge.coverage import coverage_report
from ..knowledge.gamedata import GameData
from ..market import poeninja, trade
from ..parsing import pob, recipe_text
from ..parsing.clipboard import ItemParser
from ..storage import db
from ..updates import versions

WEB = Path(__file__).parents[1] / "web" / "index.html"
IDEAS = Path(__file__).parents[1] / "knowledge" / "craft_ideas.json"


class SettingsIn(BaseModel):
    league: str

class ParseIn(BaseModel):
    text: str = Field(max_length=20_000)

class PobIn(BaseModel):
    code: str = Field(max_length=2_000_000)

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
    budget_s: float = Field(2.0, ge=0.2, le=3.0)  # simulation seconds per route

class SavePlanIn(PlanIn):
    sale_chaos: float = Field(gt=0)
    best_route: str | None = None
    best_cost_chaos: float | None = Field(None, ge=0)

class SuggestIn(BaseModel):
    text: str = Field(max_length=50_000)
    base: str | None = None

class RecipeStepIn(BaseModel):
    action: str
    params: dict = Field(default_factory=dict)
    repeat: str = "once"  # once | until_wanted | until_mods
    mods: list[str] = Field(default_factory=list)

class RecipeIn(BaseModel):
    name: str = Field("My recipe", max_length=200)
    base: str
    item_level: int = Field(84, ge=1, le=100)
    influences: list[str] = Field(default_factory=list)
    wants: list[WantIn] = Field(min_length=1)
    steps: list[RecipeStepIn] = Field(min_length=1, max_length=40)
    source_url: str | None = Field(None, max_length=500)
    source_text: str | None = Field(None, max_length=50_000)
    compare: bool = True
    budget_s: float = Field(2.0, ge=0.2, le=3.0)

class CollectIn(BaseModel):
    text: str = Field(max_length=20_000)
    price_chaos: float | None = Field(None, gt=0)
    name: str | None = Field(None, max_length=200)
    source: str = Field("pasted", pattern="^(pasted|pob|manual)$")

class IdeaResultIn(BaseModel):
    best_route: str | None = None
    best_cost_chaos: float | None = Field(None, ge=0)

class FetchIn(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["Currency", "Essence", "Fossil", "Resonator", "Beast"])
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
            resp["bench_options"] = _bench_options(g, state, st.conn, league())
        return resp

    @app.post("/api/items/trade_link")
    def item_trade_link(body: ParseIn):
        """Search link for items like this one: same base, its rolled mods at their tier or better."""
        g = gd()
        if not league():
            raise HTTPException(422, "select a league first")
        parsed = ItemParser(g).parse(body.text)
        b = g.bases.get(parsed.base_id or "")
        if b is None:
            raise HTTPException(422, "base type not recognised")
        wants = [Want(g.mods[m.mod_id].type, m.tier or 99, bench=m.crafted) for m in parsed.mods if m.mod_id]
        try:
            filters, notes, min_edps = trade.stat_filters(
                g, ItemState(b.id, parsed.item_level or 1, influences=frozenset(parsed.influences)), wants,
                trade.load_stats(g.version))
        except Exception as e:  # noqa: BLE001 - shown to the user
            raise HTTPException(502, f"No trade link: {e}")
        skipped = sum(1 for m in parsed.mods if not m.mod_id)
        if skipped:
            notes.append(f"{skipped} mod(s) not identified exactly (ambiguous/unmatched) are left out.")
        return {"url": trade.search_url(league(), b.name, filters, min_edps), "notes": notes}

    @app.post("/api/pob")
    def pob_import(body: PobIn):
        """Equipped items from a Path of Building code, each converted to Ctrl+C text and parsed."""
        g = gd()
        try:
            entries = pob.items(body.code)
        except pob.PobError as e:
            raise HTTPException(422, str(e))
        parser = ItemParser(g)
        for e in entries:
            if "text" in e:
                p = parser.parse(e["text"])
                e.update(name=p.name, base=p.base_name, rarity=p.rarity, item_level=p.item_level,
                         mods=len(p.mods), matched=sum(m.status == "matched" for m in p.mods),
                         ambiguous=sum(m.status == "ambiguous" for m in p.mods), warnings=p.warnings)
        return {"items": entries, "assumed_item_level": pob.ASSUMED_ITEM_LEVEL}

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
        try:  # what one attempt uses: currency, essence, fossils + resonator, lifeforce, beast, bench cost
            cost = cost_of(g, body.action, body.params, start)
        except (InvalidAction, KeyError):
            cost = {}
        prices = {n: poeninja.price_of(st.conn, league(), n) for n in cost} if league() else {}
        price = None
        if cost and prices and all(prices.values()):
            price = {"chaos_value": sum(v * prices[n]["chaos_value"] for n, v in cost.items()), "uses": cost}
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
        wants = [Want(w.mod_type, w.max_tier, w.bench) for w in body.wants]
        infl = frozenset(i.lower() for i in body.influences)
        try:
            routes = plan_routes(g, b.id, body.item_level, wants, influences=infl, seed=body.seed, budget_s=body.budget_s)
        except (InvalidAction, UnsupportedMechanic) as e:
            raise HTTPException(422, str(e))
        lg = league()
        out = _price_routes(st.conn, lg, routes)
        out.sort(key=lambda d: (d["expected_chaos"] is None, d["expected_chaos"] or d["at_least_chaos"] or float("inf")))
        divine = poeninja.price_of(st.conn, lg, "Divine Orb") if lg else None
        base_price = poeninja.price_of(st.conn, lg, b.name) if lg else None
        trade_url, trade_notes = None, []
        if lg:
            try:
                filters, trade_notes, min_edps = trade.stat_filters(
                    g, ItemState(b.id, body.item_level, influences=infl), wants, trade.load_stats(g.version))
                trade_url = trade.search_url(lg, b.name, filters, min_edps)
            except Exception as e:  # noqa: BLE001 - the plan is still useful without a link
                trade_notes = [f"No trade link: {e}"]
        worst = worst_accepted_mods(g, ItemState(b.id, body.item_level, influences=infl), wants)
        wants_text = [{"mod_type": w.mod_type, "max_tier": w.max_tier, "bench": w.bench,
                       "text": BenchCraft(g, b.item_class, w).text if w.bench
                       else worst[w.mod_type].text if w.mod_type in worst else w.mod_type} for w in wants]
        key = _plan_key(body)
        saved = st.conn.execute("SELECT sale_chaos FROM saved_plans WHERE league=? AND key=?", (lg, key)).fetchone()
        return {"base": b.name, "routes": out, "divine_chaos": divine["chaos_value"] if divine else None,
                "base_price": base_price, "league": lg or None, "key": key, "item_level": body.item_level,
                "influences": sorted(infl), "wants_text": wants_text, "game_version": g.version,
                "prices_as_of": versions.status(st.conn, g.version).get("latest_market_update"),
                "trade_url": trade_url, "trade_notes": trade_notes, "saved_sale_chaos": saved["sale_chaos"] if saved else None,
                "rules_verified_for_current_data": versions.status(st.conn, g.version)["rules_verified_for_current_data"]}

    # ------------------------------------------------------------ community / saved recipes
    def _base(name: str):
        b = gd().bases_by_name.get(name) or gd().bases.get(name)
        if b is None:
            raise HTTPException(404, f"unknown base {name!r}")
        return b

    @app.post("/api/recipes/suggest")
    def recipe_suggest(body: SuggestIn):
        return recipe_text.suggest(gd(), body.text, body.base or None)

    @app.get("/api/bench_options")
    def bench_options(base: str):
        g, b = gd(), _base(base)
        out = []
        for o in g.bench_options:
            mid = (o.get("actions") or {}).get("add_explicit_mod")
            # partial locks ('1/2 ... cannot be changed') are not modelled yet, so they are not offered
            if mid in g.mods and b.item_class in o.get("item_classes", []) and not g.mods[mid].type.endswith("Count"):
                m = g.mods[mid]
                out.append({"mod_id": mid, "text": m.text, "affix": m.generation_type,
                            "cost": cost_of(g, "bench_craft", {"mod_id": mid}, ItemState(b.id, 1))})
        return sorted(out, key=lambda d: (d["affix"], d["text"]))

    @app.post("/api/recipes/simulate")
    def recipe_simulate(body: RecipeIn):
        """Simulate a pasted/edited recipe and, optionally, the app's own best route for the same target."""
        g, b = gd(), _base(body.base)
        infl = frozenset(i.lower() for i in body.influences)
        reqs = [ModRequirement(w.mod_type, w.max_tier) for w in body.wants]
        try:
            recipe = recipe_from_json(body.name, [s.model_dump() for s in body.steps], reqs)
            route = simulate_recipe(g, ItemState(b.id, body.item_level, influences=infl), recipe, budget_s=body.budget_s)
        except (InvalidAction, UnsupportedMechanic) as e:
            raise HTTPException(422, str(e))
        out = {"recipe": _price_routes(st.conn, league(), [route])[0], "app_best": None, "app_routes": 0}
        if body.compare:
            try:
                routes = plan_routes(g, b.id, body.item_level, [Want(w.mod_type, w.max_tier, w.bench) for w in body.wants],
                                     influences=infl, budget_s=body.budget_s)
                priced = _price_routes(st.conn, league(), routes)
                priced.sort(key=lambda d: (d["expected_chaos"] is None, d["expected_chaos"] or d["at_least_chaos"] or float("inf")))
                out.update(app_best=priced[0] if priced else None, app_routes=len(priced))
            except (InvalidAction, UnsupportedMechanic) as e:
                out["compare_error"] = str(e)
        divine = poeninja.price_of(st.conn, league(), "Divine Orb") if league() else None
        out["divine_chaos"] = divine["chaos_value"] if divine else None
        return out

    @app.post("/api/recipes")
    def recipe_save(body: RecipeIn):
        _base(body.base)
        cur = st.conn.execute(
            "INSERT INTO saved_recipes(name, source_url, source_text, base, item_level, influences, wants, steps, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (body.name, body.source_url, body.source_text, body.base, body.item_level, json.dumps(body.influences),
             json.dumps([w.model_dump() for w in body.wants]), json.dumps([s.model_dump() for s in body.steps]),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        st.conn.commit()
        return {"id": cur.lastrowid}

    @app.get("/api/recipes")
    def recipe_list(base: str | None = None):
        rows = st.conn.execute("SELECT * FROM saved_recipes WHERE (? IS NULL OR base = ?) ORDER BY id DESC", (base, base))
        out = []
        for r in rows:
            d = dict(r)
            for k in ("influences", "wants", "steps"):
                d[k] = json.loads(d[k])
            out.append(d)
        return out

    @app.delete("/api/recipes/{rid}")
    def recipe_delete(rid: int):
        st.conn.execute("DELETE FROM saved_recipes WHERE id = ?", (rid,))
        st.conn.commit()
        return {"deleted": rid}

    # ------------------------------------------------------------ collected craft ideas
    @app.post("/api/ideas/collect")
    def idea_collect(body: CollectIn):
        """Turn a pasted/imported item into a craft idea: its base, item level and identified mods
        at the item's own tiers (crafted mods become bench crafts)."""
        g = gd()
        if not league():
            raise HTTPException(422, "select a league first")
        parsed = ItemParser(g).parse(body.text)
        b = g.bases.get(parsed.base_id or "")
        if b is None or parsed.rarity == "Unique":
            raise HTTPException(422, "need a magic or rare item with a known base type")
        tags = ItemView(g, ItemState(b.id, parsed.item_level or 1, influences=frozenset(parsed.influences))).tags()
        wants, seen = [], set()
        for m in parsed.mods:
            if not m.mod_id or g.mods[m.mod_id].type in seen:
                continue
            mod = g.mods[m.mod_id]
            seen.add(mod.type)
            tier = m.tier or tier_index(g, b, mod, tags)[0] or 99
            wants.append({"mod_type": mod.type, "max_tier": tier, "bench": m.crafted, "text": mod.text})
        if not wants:
            raise HTTPException(422, "no modifier could be identified exactly (try Ctrl+Alt+C)")
        skipped = sum(1 for m in parsed.mods if not m.mod_id)
        cur = st.conn.execute(
            "INSERT INTO saved_ideas(league, name, base, item_level, influences, wants, price_chaos, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (league(), body.name or parsed.name or b.name, b.name, parsed.item_level or 84, json.dumps(parsed.influences),
             json.dumps(wants), body.price_chaos, body.source, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        st.conn.commit()
        return {"id": cur.lastrowid, "wants": len(wants), "skipped_mods": skipped}

    @app.get("/api/ideas/collected")
    def ideas_collected():
        """Collected ideas for the current league in three price groups (by the Divine Orb price)."""
        lg = league()
        divine = poeninja.price_of(st.conn, lg, "Divine Orb") if lg else None
        div = divine["chaos_value"] if divine else None
        groups = {"under_10_div": [], "10_to_100_div": [], "over_100_div": [], "no_price": []}
        for r in st.conn.execute("SELECT * FROM saved_ideas WHERE league = ? ORDER BY id DESC", (lg,)):
            d = dict(r)
            d["influences"], d["wants"] = json.loads(d["influences"]), json.loads(d["wants"])
            cost = d["best_cost_chaos"]
            d["profit_chaos"] = d["price_chaos"] - cost if (d["price_chaos"] and cost is not None) else None
            if not d["price_chaos"] or not div:
                groups["no_price"].append(d)
            else:
                in_div = d["price_chaos"] / div
                groups["under_10_div" if in_div < 10 else "10_to_100_div" if in_div <= 100 else "over_100_div"].append(d)
        for g_ in groups.values():
            g_.sort(key=lambda d: (d["profit_chaos"] is None, -(d["profit_chaos"] or 0)))
        return {"divine_chaos": div, "groups": groups}

    @app.post("/api/ideas/collected/{iid}/result")
    def idea_result(iid: int, body: IdeaResultIn):
        st.conn.execute("UPDATE saved_ideas SET best_route = ?, best_cost_chaos = ? WHERE id = ?",
                        (body.best_route, body.best_cost_chaos, iid))
        st.conn.commit()
        return {"id": iid}

    @app.delete("/api/ideas/collected/{iid}")
    def idea_delete(iid: int):
        st.conn.execute("DELETE FROM saved_ideas WHERE id = ?", (iid,))
        st.conn.commit()
        return {"deleted": iid}

    @app.get("/api/ideas")
    def ideas():
        """Starter craft targets (knowledge/craft_ideas.json), each checked against the game data."""
        g = gd()
        out = []
        for idea in json.loads(IDEAS.read_text(encoding="utf-8"))["ideas"]:
            b = g.bases_by_name.get(idea["base"])
            problem = None if b else f"unknown base {idea['base']!r}"
            if b:
                rollable = {e.mod.type for e in eligible_pool(g, ItemState(b.id, idea["item_level"], "rare"))}
                missing = [w["mod_type"] for w in idea["wants"] if not w.get("bench") and w["mod_type"] not in rollable]
                problem = f"cannot roll on this base: {', '.join(missing)}" if missing else None
            out.append({**idea, "problem": problem})
        return out

    @app.post("/api/plans")
    def save_plan(body: SavePlanIn):
        if not league():
            raise HTTPException(422, "select a league first")
        st.conn.execute(
            "INSERT INTO saved_plans(league, key, base, item_level, influences, wants, sale_chaos, best_route, best_cost_chaos, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(league, key) DO UPDATE SET sale_chaos=excluded.sale_chaos, "
            "best_route=excluded.best_route, best_cost_chaos=excluded.best_cost_chaos, updated_at=excluded.updated_at",
            (league(), _plan_key(body), body.base, body.item_level, json.dumps(body.influences),
             json.dumps([w.model_dump() for w in body.wants]), body.sale_chaos, body.best_route, body.best_cost_chaos,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        st.conn.commit()
        return {"key": _plan_key(body)}

    @app.get("/api/plans")
    def list_plans():
        """Saved crafts for the current league, best expected profit first."""
        out = []
        for r in st.conn.execute("SELECT * FROM saved_plans WHERE league=?", (league(),)):
            d = dict(r)
            d["influences"], d["wants"] = json.loads(d["influences"]), json.loads(d["wants"])
            base_price = poeninja.price_of(st.conn, league(), d["base"])
            d["base_price_chaos"] = base_price["chaos_value"] if base_price else None
            cost = d["best_cost_chaos"]
            d["profit_chaos"] = None if cost is None else d["sale_chaos"] - cost - (d["base_price_chaos"] or 0)
            d["roi"] = None if cost is None or cost + (d["base_price_chaos"] or 0) <= 0 else                 d["profit_chaos"] / (cost + (d["base_price_chaos"] or 0))
            out.append(d)
        out.sort(key=lambda d: (d["profit_chaos"] is None, -(d["profit_chaos"] or 0)))
        return out

    @app.delete("/api/plans/{key}")
    def delete_plan(key: str):
        st.conn.execute("DELETE FROM saved_plans WHERE league=? AND key=?", (league(), key))
        st.conn.commit()
        return {"deleted": key}

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


def _price_routes(conn, lg: str, routes: list) -> list[dict]:
    """Route dataclasses -> dicts with chaos prices (expected, range, minimum) and missing price names."""
    prices: dict[str, dict | None] = {}

    def chaos_of(units: dict[str, float] | None) -> float | None:
        if not units:
            return None
        for name in units:
            if name not in prices:
                prices[name] = poeninja.price_of(conn, lg, name) if lg else None
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
    return out


def _plan_key(body: PlanIn) -> str:
    wants = sorted((w.mod_type, w.max_tier, w.bench) for w in body.wants)
    raw = json.dumps([body.base, body.item_level, sorted(i.lower() for i in body.influences), wants])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _bench_options(g: GameData, item: ItemState, conn, lg: str) -> list[dict]:
    """Bench crafts that fit this item right now (validated by the bench_craft action), with cost."""
    import random

    view = ItemView(g, item)
    out, seen = [], set()
    for o in g.bench_options:
        mid = (o.get("actions") or {}).get("add_explicit_mod")
        if mid not in g.mods or view.base.item_class not in o.get("item_classes", []) or g.mods[mid].text in seen:
            continue
        try:
            ACTIONS["bench_craft"].fn(g, item, random.Random(0), mod_id=mid)
        except (InvalidAction, UnsupportedMechanic):
            continue
        seen.add(g.mods[mid].text)
        cost = {(g.bases[k].name if k in g.bases else k): v for k, v in (o.get("cost") or {}).items()}
        prices = [poeninja.price_of(conn, lg, n) if lg else None for n in cost]
        chaos = sum(v * p["chaos_value"] for v, p in zip(cost.values(), prices)) if all(prices) else None
        out.append({"text": g.mods[mid].text, "affix": g.mods[mid].generation_type, "cost": cost, "chaos": chaos})
    return sorted(out, key=lambda d: (d["affix"], d["text"]))


def _valid_actions(g: GameData, item: ItemState) -> list[dict]:
    import random

    out = []
    for a in ACTIONS.values():
        if a.id in ("essence", "fossil", "bench_craft", "harvest_reforge", "harvest_add_remove", "harvest_swap"):
            continue  # need parameters
        try:
            a.fn(g, item, random.Random(0))
            out.append({"id": a.id, "name": a.name, "valid": True})
        except (InvalidAction, UnsupportedMechanic) as e:
            out.append({"id": a.id, "name": a.name, "valid": False, "reason": str(e)})
    return out
