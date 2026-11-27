"""Route planner: rank standard crafting methods for a target by expected cost.

A *route* is one well-known method built only from actions in actions.ACTIONS
(no invented mechanics). Each route is simulated as independent *tries*; a try
ends in success or failure, and a failed try is repeated from scratch. By
Wald's identity the expected currency spent until the first success is
(currency used over all tries) / (successful tries).

Routes:
  * Alchemy, then Chaos spam
  * Essence spam (one route per essence that guarantees a wanted mod)
  * Fossil spam and Harvest tag-reforge spam (experimental)
  * Lock prefixes/suffixes, scour, exalt and Fracture-then-Chaos (multi-step
    recipes, engine/recipe.py)
  * Transmute + Alteration/Augmentation for up to 1 prefix + 1 suffix,
    Regal, then Exalted Orbs (scour and restart on failure)
A wanted mod marked `bench` is not rolled for: the route keeps a slot open and
finishes with that bench craft.

Not covered yet (so real best routes can be cheaper): partial locks, Harvest
add/remove and swaps as route templates, beastcrafting templates, recombinators,
fracturing, influence currencies. See docs/MECHANICS_3_30.md.
"""
from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass, field

from ..knowledge.gamedata import GameData, Mod
from .actions import ACTIONS, InvalidAction, apply, assumption
from .item import ItemState, ItemView, UnsupportedMechanic, _tier_family, tier_index
from .modpool import eligible_pool
from .recipe import HARVEST, Condition, Recipe, Step, cost_of, run_once
from .simulate import ModRequirement, Target, wilson_interval


def _fmt(cost: dict) -> str:
    return ", ".join(f"{v:g} {k}" for k, v in cost.items())


@dataclass(frozen=True)
class Want:
    mod_type: str
    max_tier: int = 99
    bench: bool = False  # finish with a bench craft instead of rolling it


@dataclass
class Route:
    name: str
    steps: list[str]
    tries: int
    successes: int
    try_success_ci95: tuple[float, float]
    expected_units: dict[str, float]  # currency name -> expected count until success
    units_range: tuple[dict[str, float], dict[str, float]] | None  # from the 95% interval
    at_least_units: dict[str, float] | None  # lower bound when no try succeeded
    assumptions: list[dict]
    notes: list[str] = field(default_factory=list)


class BenchCraft:
    def __init__(self, gd: GameData, base_item_class: str, want: Want):
        options = [
            o for o in gd.bench_options
            if (mid := (o.get("actions") or {}).get("add_explicit_mod")) in gd.mods
            and gd.mods[mid].type == want.mod_type and base_item_class in o.get("item_classes", [])
        ]
        if not options:
            raise InvalidAction(f"no crafting bench option for {want.mod_type} on {base_item_class}")
        best = max(options, key=lambda o: o.get("bench_tier", 0))
        self.mod_id = best["actions"]["add_explicit_mod"]
        self.gen_type = gd.mods[self.mod_id].generation_type
        self.cost = {(gd.bases[k].name if k in gd.bases else k): v for k, v in best.get("cost", {}).items()}
        self.text = gd.mods[self.mod_id].text


def _ready(gd: GameData, item: ItemState, rolled: Target, bench: BenchCraft | None) -> bool:
    if not rolled.met_by(gd, item):
        return False
    return bench is None or ItemView(gd, item).open_slots(bench.gen_type) > 0


def _run(try_fn, budget_s: float, max_successes: int, rng) -> tuple[int, int, Counter, bool]:
    """Run tries until the time budget or enough successes. A try_fn returns
    (success, currency used), or None when it ran out of time mid-try (discarded).
    Also reports whether every try cost exactly the same."""
    tries = successes = 0
    used: Counter = Counter()
    first, same_cost = None, True
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline and successes < max_successes:
        res = try_fn(rng, deadline)
        if res is None:
            break
        ok, u = res
        tries += 1
        successes += ok
        used.update(u)
        first = first if first is not None else dict(u)
        same_cost = same_cost and dict(u) == first
    return tries, successes, used, same_cost


def _route(name, steps, action_ids, tries, successes, used, same_cost, fixed, notes) -> Route:
    lo, hi = wilson_interval(successes, tries)
    per_try = {k: v / tries for k, v in used.items()} if tries else {}

    def total(p: float) -> dict[str, float]:
        out = {k: v / p for k, v in per_try.items()}
        for k, v in fixed.items():
            out[k] = out.get(k, 0) + v
        return out

    expected = total(successes / tries) if successes else {}
    # The interval on the success chance only bounds the cost when every try costs the same.
    rng_ = (total(hi), total(lo)) if successes and lo > 0 and same_cost else None
    at_least = None
    if not tries:
        notes = notes + ["The time budget ran out before one try finished: this route needs a very large number of "
                         "attempts. Relax tiers or untick mods."]
    elif not successes:
        at_least = total(hi)
        notes = notes + [f"Never succeeded in {tries} simulated tries: the chance per try is below {hi:.2%} (95%). "
                         "The cost shown is a minimum. Relax tiers or untick mods."]
    elif successes < 30:
        notes = notes + [f"Only {successes} successful tries simulated: the estimate is rough."]
    names = sorted({a for aid in action_ids for a in ACTIONS[aid].assumptions})
    return Route(name, steps, tries, successes, (lo, hi), expected, rng_, at_least,
                 [{"name": a, **assumption(a)} for a in names], notes)


def simulate_recipe(gd: GameData, start: ItemState, recipe: Recipe, *, seed: int = 1,
                    budget_s: float = 3.0, max_successes: int = 400) -> Route:
    """Simulate a user/community recipe exactly like a planner route (Wald cost per success)."""
    def try_fn(r, deadline):
        return run_once(gd, recipe, start, r, deadline)

    actions = sorted({s.action for s in recipe.steps})
    steps = [describe_step(gd, s) for s in recipe.steps]
    return _route(recipe.name, steps, actions, *_run(try_fn, budget_s, max_successes, random.Random(seed)), {}, [])


def describe_step(gd: GameData, s: Step) -> str:
    """A recipe step in plain words, e.g. 'Essence: Deafening Essence of Wrath, until the wanted mods appear'."""
    p = s.params
    detail = (p.get("essence_name") or ", ".join(p.get("fossil_names", [])) or p.get("tag")
              or (gd.mods[p["mod_id"]].text.replace("\n", " / ") if p.get("mod_id") in gd.mods else "")
              or " ".join(x for x in (p.get("kind"), p.get("from_element"), "to" if p.get("to_element") else None, p.get("to_element")) if x))
    text = ACTIONS[s.action].name + (f": {detail}" if detail else "")
    if s.until is not None:
        wanted = ", ".join(r.mod_type for r in s.until.all_of)
        text += f", repeat until {wanted}" if wanted else ", repeat"
    if s.check is not None:
        need = ", ".join(r.mod_type for r in s.check.all_of)
        back = f"go back to step {int(s.on_fail[5:]) + 1}" if s.on_fail.startswith("goto:") else "start over"
        text += f"; if {need} is missing: {back}"
    return text


def worst_accepted_mods(gd: GameData, item: ItemState, wants: list[Want]) -> dict[str, Mod]:
    """For each wanted mod type that can roll on this base: the mod of the worst
    accepted tier (its text shows the lowest values the user accepts)."""
    view = ItemView(gd, item)
    tags = frozenset(view.tags())
    by_type: dict[str, Mod] = {}
    for e in eligible_pool(gd, item.with_(rarity="rare", explicits=())):
        by_type.setdefault(e.mod.type, e.mod)
    out = {}
    for w in wants:
        if (mod := by_type.get(w.mod_type)) is not None:
            family = [gd.mods[i] for i in _tier_family(gd, view.base, mod, tags)]
            out[w.mod_type] = family[min(w.max_tier, len(family)) - 1] if family else mod
    return out


def plan_routes(gd: GameData, base_id: str, item_level: int, wants: list[Want], *,
                influences: frozenset[str] = frozenset(), seed: int = 1,
                budget_s: float = 2.0, max_successes: int = 400) -> list[Route]:
    if not wants:
        raise InvalidAction("choose at least one wanted modifier")
    normal = ItemState(base_id, item_level, "normal", influences=influences)
    view = ItemView(gd, normal)
    bench_wants = [w for w in wants if w.bench]
    if len(bench_wants) > 1:
        raise InvalidAction("only one bench-crafted mod is supported (multimod is not planned yet)")
    bench = BenchCraft(gd, view.base.item_class, bench_wants[0]) if bench_wants else None
    rolled_wants = [w for w in wants if not w.bench]
    rolled = Target([ModRequirement(w.mod_type, w.max_tier) for w in rolled_wants])
    finish = [f"Bench craft: {bench.text} ({', '.join(f'{v} {k}' for k, v in bench.cost.items())})"] if bench else []
    fixed_bench = dict(bench.cost) if bench else {}
    rng = random.Random(seed)
    routes: list[Route] = []

    def add(fixed: dict, result: tuple, name: str, steps: list[str], action_ids: list[str], notes=()):
        merged = Counter(fixed)
        merged.update(fixed_bench)
        routes.append(_route(name, steps + finish, action_ids, *result, dict(merged), list(notes)))

    # 1. Alchemy, then Chaos spam (each Chaos reforge is independent of the last).
    rare = apply(gd, normal, "alchemy", rng)

    def chaos_try(r, _deadline):
        return _ready(gd, apply(gd, rare, "chaos", r), rolled, bench), {"Chaos Orb": 1}

    add({"Orb of Alchemy": 1}, _run(chaos_try, budget_s, max_successes, rng),
        "Chaos spam", ["Orb of Alchemy on the base", "Chaos Orb until the wanted mods appear"], ["alchemy", "chaos"])

    # 2. Essence spam: for each wanted mod type, the strongest essence that guarantees it.
    best_ess: dict[str, tuple[int, str, dict]] = {}
    for ename, (_, ess) in gd.essences_by_name.items():
        mid = (ess.get("mods") or {}).get(view.base.item_class)
        if mid not in gd.mods or gd.mods[mid].type not in {w.mod_type for w in rolled_wants}:
            continue
        restr = ess.get("item_level_restriction")
        if restr is not None and item_level > restr:
            continue
        mtype = gd.mods[mid].type
        if ess.get("level", 0) > best_ess.get(mtype, (-1,))[0]:
            best_ess[mtype] = (ess.get("level", 0), ename, ess)
    for _, ename, ess in best_ess.values():
        reforges_rare = ess.get("level", 0) >= 6 or ess.get("type", {}).get("is_corruption_only")
        per = {ename: 1} if reforges_rare else {ename: 1, "Orb of Scouring": 1}

        def ess_try(r, _deadline, ename=ename, per=per):
            return _ready(gd, apply(gd, normal, "essence", r, essence_name=ename), rolled, bench), per

        try:
            res = _run(ess_try, budget_s, max_successes, rng)
        except (InvalidAction, UnsupportedMechanic):
            continue
        how = "" if reforges_rare else " (Orb of Scouring before each one)"
        add({}, res, f"Essence spam: {ename}", [f"{ename} until the other wanted mods appear{how}"], ["essence"])

    # 3. Fossil spam (EXPERIMENTAL like the fossil action): simple fossils only (tag weights,
    #    no forced/added mods), never one that blocks a wanted mod. One route per helpful
    #    fossil, plus one with all helpful fossils together (max 4, one resonator socket each).
    pool_rare = {e.mod.type: e.mod for e in eligible_pool(gd, normal.with_(rarity="rare"))}
    wanted_tags = [set(pool_rare[w.mod_type].implicit_tags) for w in rolled_wants if w.mod_type in pool_rare]
    helpful: list[tuple[int, str]] = []
    for fname, (_, fos) in gd.fossils_by_name.items():
        if fos.get("added_mods") or fos.get("forced_mods") or fos.get("allowed_tags") or fos.get("forbidden_tags") \
                or fos.get("rolls_lucky") or fos.get("corrupted_essence_chance") or fos.get("sell_price_mods"):
            continue
        boost = {e["tag"] for e in fos.get("positive_mod_weights") or [] if e["weight"] > 100}
        block = {e["tag"] for e in fos.get("negative_mod_weights") or [] if e["weight"] == 0}
        if any(t & block for t in wanted_tags):
            continue
        hits = sum(1 for t in wanted_tags if t & boost)
        if hits:
            helpful.append((hits, fname))
    helpful.sort(reverse=True)
    combos = [[f] for _, f in helpful[:3]]
    if len(helpful) > 1:
        combos.append([f for _, f in helpful[:4]])
    resonators = {1: "Primitive Chaotic Resonator", 2: "Potent Chaotic Resonator",
                  3: "Powerful Chaotic Resonator", 4: "Prime Chaotic Resonator"}
    for combo in combos:
        per = {f: 1 for f in combo}
        per[resonators[len(combo)]] = 1

        def fos_try(r, _deadline, combo=combo, per=per):
            return _ready(gd, apply(gd, normal, "fossil", r, fossil_names=combo), rolled, bench), per

        add({}, _run(fos_try, budget_s, max_successes, rng), f"Fossil spam: {' + '.join(combo)} (experimental)",
            [f"{resonators[len(combo)]} with {', '.join(combo)} until the wanted mods appear"], ["fossil"],
            notes=["Fossil weighting is experimental (not yet checked against Craft of Exile)."])

    # 4. Harvest tag reforge spam (EXPERIMENTAL): for each wanted mod its most specific
    #    Harvest tag (the tag with the smallest total weight in this pool).
    tag_weight: Counter = Counter()
    for e in eligible_pool(gd, normal.with_(rarity="rare")):
        for t in e.mod.implicit_tags:
            tag_weight[t] += e.weight
    harvest_tags: list[str] = []
    for w in rolled_wants:
        tags = [t for t in (pool_rare[w.mod_type].implicit_tags if w.mod_type in pool_rare else ()) if t in HARVEST["reforge"]]
        if tags and (t := min(tags, key=lambda t: tag_weight[t])) not in harvest_tags:
            harvest_tags.append(t)
    for tag in harvest_tags[:3]:
        per = cost_of(gd, "harvest_reforge", {"tag": tag}, rare)

        def hv_try(r, _deadline, tag=tag, per=per):
            return _ready(gd, apply(gd, rare, "harvest_reforge", r, tag=tag), rolled, bench), per

        add({"Orb of Alchemy": 1}, _run(hv_try, budget_s, max_successes, rng), f"Harvest reforge: {tag} (experimental)",
            ["Orb of Alchemy on the base",
             f"Harvest: reforge including a {tag} modifier ({_fmt(per)}) until the wanted mods appear"],
            ["alchemy", "harvest_reforge"],
            notes=["Harvest rolling order (tagged mod first, then fill) is experimental."])

    # 5. Lock + scour + exalt (multi-step recipe): roll one side with Chaos, lock it on the
    #    bench, scour (removes the other side AND the lock, which sits on the other side),
    #    then Exalted Orbs into the free slots. A failed try starts again from a fresh
    #    Alchemy. (Chaos on a locked item would also remove the lock, so it is not used.)
    sides = {g: [w for w in rolled_wants if w.mod_type in pool_rare and pool_rare[w.mod_type].generation_type == g]
             for g in ("prefix", "suffix")}
    max_aff = ItemView(gd, rare).max_affixes()
    req = lambda ws: tuple(ModRequirement(w.mod_type, w.max_tier) for w in ws)  # noqa: E731
    bench_room = {f"min_open_{bench.gen_type}es": 1} if bench else {}
    for locked, other in (("suffix", "prefix"), ("prefix", "suffix")):
        if not sides[locked] or not sides[other] or len(sides[other]) > max_aff:
            continue
        group = "ItemGenerationCannotChangeSuffixes" if locked == "suffix" else "ItemGenerationCannotChangePrefixes"
        opt = next((o for o in gd.bench_options
                    if (mid := (o.get("actions") or {}).get("add_explicit_mod")) in gd.mods
                    # by type: the partial locks ("1/2 ... cannot be changed") share the group
                    and gd.mods[mid].type == group and view.base.item_class in o.get("item_classes", [])), None)
        if opt is None:
            continue
        lock = gd.mods[opt["actions"]["add_explicit_mod"]]
        recipe = Recipe(f"Lock {locked}es", (
            Step("chaos", until=Condition(all_of=req(sides[locked]), **{f"min_open_{lock.generation_type}es": 1})),
            Step("bench_craft", {"mod_id": lock.id}),
            Step("scouring"),
            Step("exalted", until=Condition(all_of=req(sides[other]))),  # fails the try once the item is full
        ), target=Condition(all_of=req(rolled_wants), **bench_room))

        def lock_try(r, deadline, recipe=recipe):
            return run_once(gd, recipe, rare, r, deadline)

        add({"Orb of Alchemy": 1}, _run(lock_try, budget_s, max_successes, rng), f"Lock {locked}es, scour, exalt",
            ["Orb of Alchemy on the base",
             f"Chaos Orb until the wanted {locked}es appear (and a {lock.generation_type} slot is free)",
             f"Bench craft '{lock.text}' ({_fmt(cost_of(gd, 'bench_craft', {'mod_id': lock.id}, rare))})",
             f"Orb of Scouring: removes all {other}es and the lock, your {locked}es stay",
             f"Exalted Orb until the wanted {other}es appear",
             "If the item fills up without them: start again from a fresh Orb of Alchemy"],
            ["alchemy", "chaos", "bench_craft", "scouring", "exalted"])

    # 6. Fracture the hardest wanted mod, then Chaos for the rest (EXPERIMENTAL like the orb).
    #    A wrong fracture ruins the base: the try fails and starts again on a new base.
    if len(rolled_wants) >= 2 and not influences:
        tags_rare = ItemView(gd, rare).tags()

        def chance(w: Want) -> float:
            return sum(e.probability for e in eligible_pool(gd, normal.with_(rarity="rare"))
                       if e.mod.type == w.mod_type and tier_index(gd, view.base, e.mod, tags_rare)[0] <= w.max_tier)

        hardest = min(rolled_wants, key=chance)
        rest = [w for w in rolled_wants if w is not hardest]
        frac = Recipe("Fracture", (
            Step("chaos", until=Condition(all_of=req([hardest]), min_mods=4)),
            Step("fracturing", check=Condition(fractured=(hardest.mod_type,))),
            Step("chaos", until=Condition(all_of=req(rest))),
        ), target=Condition(all_of=req(rolled_wants), **bench_room))

        def frac_try(r, deadline, recipe=frac):
            return run_once(gd, recipe, rare, r, deadline)

        add({"Orb of Alchemy": 1}, _run(frac_try, budget_s, max_successes, rng), "Fracture, then Chaos (experimental)",
            ["Orb of Alchemy on the base",
             f"Chaos Orb until {hardest.mod_type} appears on an item with at least 4 mods",
             "Fracturing Orb: if it fractures a different mod, the base is lost: start again on a new base",
             f"Chaos Orb until the rest appear ({', '.join(w.mod_type for w in rest)}); the fractured mod always stays"],
            ["alchemy", "chaos", "fracturing"],
            notes=["Every failed fracture also costs a new base item (not included unless you set its price).",
                   "Fracturing is experimental: crafted mods are assumed not to be fracturable."])

    # 7. Alteration for up to 1 prefix + 1 suffix, Regal, then Exalted Orbs.
    pool = {e.mod.type: e for e in eligible_pool(gd, normal.with_(rarity="magic"))}
    magic: dict[str, Want] = {}
    for w in sorted(rolled_wants, key=lambda w: pool[w.mod_type].probability if w.mod_type in pool else 1):
        g = pool[w.mod_type].mod.generation_type if w.mod_type in pool else None
        if g and g not in magic:
            magic[g] = w
    if magic:
        magic_target = Target([ModRequirement(w.mod_type, w.max_tier) for w in magic.values()])
        reserved = 1 if bench else 0

        def alt_try(r, deadline):
            used = Counter({"Orb of Scouring": 1, "Orb of Transmutation": 1, "Regal Orb": 1})
            it = apply(gd, normal, "transmutation", r)
            while not magic_target.met_by(gd, it):
                if time.monotonic() > deadline:
                    return None
                v = ItemView(gd, it)
                if len(it.explicits) < 2 and any(m.type in {w.mod_type for w in magic.values()} for _, m in v.mods()):
                    it = apply(gd, it, "augmentation", r)
                    used["Orb of Augmentation"] += 1
                else:
                    it = apply(gd, it, "alteration", r)
                    used["Orb of Alteration"] += 1
            it = apply(gd, it, "regal", r)
            while not rolled.met_by(gd, it):
                v = ItemView(gd, it)
                if v.open_slots("prefix") + v.open_slots("suffix") <= reserved:
                    break
                it = apply(gd, it, "exalted", r)
                used["Exalted Orb"] += 1
            return _ready(gd, it, rolled, bench), used

        wanted_magic = " + ".join(w.mod_type for w in magic.values())
        add({}, _run(alt_try, budget_s, max_successes, rng), "Alteration, Regal, Exalt",
            ["Orb of Transmutation on the base",
             f"Orb of Alteration (Augmentation when one wanted mod is alone) until: {wanted_magic}",
             "Regal Orb", "Exalted Orb into the open affixes until the rest appear",
             "If it fails: Orb of Scouring and start again"],
            ["transmutation", "alteration", "augmentation", "regal", "exalted", "scouring"],
            notes=["Counts one Orb of Scouring per try, also the first (small overcount)."])
    return routes


__all__ = ["Want", "Route", "BenchCraft", "plan_routes", "simulate_recipe", "worst_accepted_mods"]
