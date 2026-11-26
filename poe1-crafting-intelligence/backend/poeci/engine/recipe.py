"""Multi-step crafting recipes: ordered steps with repeat-until and check/branch.

A step applies one action, either once or repeatedly until a condition holds.
After the step an optional check decides what happens if it is not met:
"restart" ends this try as a failure (the next try starts from the start item
again) or "goto:N" jumps to step N (0-based) on the same item.

Example (lock-and-reforge):
  0. chaos              until: wanted suffixes present, and a prefix slot is open
  1. bench_craft lock   ("Suffixes cannot be changed", a crafted prefix)
  2. chaos              until: wanted prefixes present (suffixes are protected)
  3. remove_crafted     (frees the slot again)
"""
from __future__ import annotations

import json
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..knowledge.gamedata import GameData
from .actions import ACTIONS, InvalidAction, apply, missing_params
from .item import ItemState, ItemView, UnsupportedMechanic
from .simulate import ModRequirement, Target

HARVEST = json.loads((Path(__file__).parents[1] / "knowledge" / "harvest_crafts.json").read_text(encoding="utf-8"))
MAX_JUMPS = 10_000  # guards a goto loop that can never end


@dataclass(frozen=True)
class Condition:
    all_of: tuple[ModRequirement, ...] = ()
    any_of: tuple[ModRequirement, ...] = ()
    min_open_prefixes: int = 0
    min_open_suffixes: int = 0
    min_mods: int = 0
    fractured: tuple[str, ...] = ()  # mod types that must be fractured

    def met(self, gd: GameData, item: ItemState) -> bool:
        if len(item.explicits) < self.min_mods:
            return False
        if self.fractured:
            done = {gd.mods[mi.mod_id].type for mi in item.explicits if mi.fractured}
            if not set(self.fractured) <= done:
                return False
        if self.all_of and not Target(list(self.all_of)).met_by(gd, item):
            return False
        if self.any_of and not any(Target([r]).met_by(gd, item) for r in self.any_of):
            return False
        if self.min_open_prefixes or self.min_open_suffixes:
            v = ItemView(gd, item)
            if v.open_slots("prefix") < self.min_open_prefixes or v.open_slots("suffix") < self.min_open_suffixes:
                return False
        return True


@dataclass(frozen=True)
class Step:
    action: str
    params: dict = field(default_factory=dict, hash=False)
    until: Condition | None = None
    max_repeats: int = 5000
    check: Condition | None = None
    on_fail: str = "restart"  # "restart" or "goto:N"
    label: str = ""


@dataclass(frozen=True)
class Recipe:
    name: str
    steps: tuple[Step, ...]
    target: Condition


def bench_option(gd: GameData, mod_id: str) -> dict | None:
    return next((o for o in gd.bench_options if (o.get("actions") or {}).get("add_explicit_mod") == mod_id), None)


def _names(gd: GameData, cost: dict) -> dict[str, float]:
    return {(gd.bases[k].name if k in gd.bases else k): v for k, v in (cost or {}).items()}


def cost_of(gd: GameData, action: str, params: dict, item: ItemState) -> dict[str, float]:
    """Currency used by one application of `action` (names as on poe.ninja)."""
    info = ACTIONS[action]
    if info.currency:
        return {info.currency: 1}
    if action == "essence":
        return {params["essence_name"]: 1}
    if action == "fossil":
        n = len(params["fossil_names"])
        kind = "Chaotic" if item.rarity == "rare" else "Alchemical"
        size = {1: "Primitive", 2: "Potent", 3: "Powerful", 4: "Prime"}[n]
        return {**{f: 1 for f in params["fossil_names"]}, f"{size} {kind} Resonator": 1}
    if action == "bench_craft":
        return _names(gd, (bench_option(gd, params["mod_id"]) or {}).get("cost"))
    if action == "remove_crafted":
        opt = next((o for o in gd.bench_options if (o.get("actions") or {}).get("remove_crafted_mods")), None)
        return _names(gd, (opt or {}).get("cost"))
    if action == "harvest_reforge_same":
        return {HARVEST["_lifeforce"][k]: v for k, v in HARVEST["reforge_same_types"].items()}
    if action == "harvest_swap":
        sw = HARVEST["swap"]
        out: dict[str, float] = {}
        for el in (params["from_element"].lower(), params["to_element"].lower()):
            name = HARVEST["_lifeforce"][sw["element_lifeforce"][el]]
            out[name] = out.get(name, 0) + sw["amount"]
        if params["kind"] == "damage":
            out.update({HARVEST["_lifeforce"][k]: v for k, v in sw["damage_extra"].items()})
        return out
    if action in ("harvest_reforge", "harvest_add_remove"):
        table = HARVEST["reforge" if action == "harvest_reforge" else "add_remove"]
        if params["tag"] not in table:
            raise InvalidAction(f"no Harvest craft for tag {params['tag']!r}")
        return {HARVEST["_lifeforce"][k]: v for k, v in table[params["tag"]].items()}
    raise InvalidAction(f"no cost known for {action}")


def run_once(gd: GameData, recipe: Recipe, start: ItemState, rng: random.Random,
             deadline: float | None = None) -> tuple[bool, Counter] | None:
    """One try of the recipe. Returns (success, currency used), or None if the
    time budget ran out mid-try (the caller discards that try)."""
    item, used, i, jumps = start, Counter(), 0, 0
    while i < len(recipe.steps):
        s = recipe.steps[i]
        try:
            if s.until is None:
                used.update(cost_of(gd, s.action, s.params, item))
                item = apply(gd, item, s.action, rng, **s.params)
            else:
                for _ in range(s.max_repeats):
                    if s.until.met(gd, item):
                        break
                    if deadline is not None and time.monotonic() > deadline:
                        return None
                    used.update(cost_of(gd, s.action, s.params, item))
                    item = apply(gd, item, s.action, rng, **s.params)
                else:
                    return False, used  # gave up on this step
        except (InvalidAction, UnsupportedMechanic):
            return False, used  # the action became impossible on this item: the try fails
        if s.check is not None and not s.check.met(gd, item):
            if s.on_fail.startswith("goto:"):
                jumps += 1
                if jumps > MAX_JUMPS:
                    return False, used
                i = int(s.on_fail.split(":", 1)[1])
                continue
            return False, used
        i += 1
    return recipe.target.met(gd, item), used


def validate(recipe: Recipe) -> None:
    for n, s in enumerate(recipe.steps):
        if s.action not in ACTIONS:
            raise InvalidAction(f"step {n + 1}: unknown action {s.action!r}")
        if missing := missing_params(s.action, s.params):
            raise InvalidAction(f"step {n + 1} ({ACTIONS[s.action].name}): choose {', '.join(missing)}")
        if s.on_fail != "restart":
            if not s.on_fail.startswith("goto:") or not s.on_fail[5:].isdigit() or int(s.on_fail[5:]) >= len(recipe.steps):
                raise InvalidAction(f"step {n + 1}: on_fail must be 'restart' or 'goto:<step index, starting at 0>'")


def recipe_from_json(name: str, steps: list[dict], wants: list[ModRequirement]) -> Recipe:
    """Steps as stored/edited in the UI: {action, params, repeat: once|until_wanted|until_mods,
    mods: [mod types for until_mods]}. The target is every wanted mod."""
    by_type = {w.mod_type: w for w in wants}
    out = []
    for n, s in enumerate(steps):
        repeat = s.get("repeat", "once")
        if repeat == "until_wanted":
            until = Condition(all_of=tuple(wants))
        elif repeat == "until_mods":
            missing = [m for m in s.get("mods", []) if m not in by_type]
            if missing or not s.get("mods"):
                raise InvalidAction(f"step {n + 1}: 'until these mods' needs wanted mod types, got {missing or 'none'}")
            until = Condition(all_of=tuple(by_type[m] for m in s["mods"]))
        elif repeat == "once":
            until = None
        else:
            raise InvalidAction(f"step {n + 1}: unknown repeat {repeat!r}")
        out.append(Step(s["action"], dict(s.get("params") or {}), until=until))
    recipe = Recipe(name, tuple(out), Condition(all_of=tuple(wants)))
    validate(recipe)
    return recipe
