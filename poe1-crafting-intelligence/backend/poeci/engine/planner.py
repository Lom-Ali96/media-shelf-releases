"""Route planner: rank standard crafting methods for a target by expected cost.

A *route* is one well-known method built only from actions in actions.ACTIONS
(no invented mechanics). Each route is simulated as independent *tries*; a try
ends in success or failure, and a failed try is repeated from scratch. By
Wald's identity the expected currency spent until the first success is
(currency used over all tries) / (successful tries).

Routes:
  * Alchemy, then Chaos spam
  * Essence spam (one route per essence that guarantees a wanted mod)
  * Transmute + Alteration/Augmentation for up to 1 prefix + 1 suffix,
    Regal, then Exalted Orbs (scour and restart on failure)
A wanted mod marked `bench` is not rolled for: the route keeps a slot open and
finishes with that bench craft.

Not covered (so real best routes can be cheaper): fossils, Harvest, beasts,
metamod tricks, fracturing, influence currencies. See KNOWN_LIMITATIONS.md.
"""
from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass, field

from ..knowledge.gamedata import GameData, Mod
from .actions import ACTIONS, InvalidAction, apply, assumption
from .item import ItemState, ItemView, UnsupportedMechanic, _tier_family
from .modpool import eligible_pool
from .simulate import ModRequirement, Target, wilson_interval


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

    # 4. Alteration for up to 1 prefix + 1 suffix, Regal, then Exalted Orbs.
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


__all__ = ["Want", "Route", "BenchCraft", "plan_routes", "worst_accepted_mods"]
