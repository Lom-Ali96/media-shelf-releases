"""Crafting actions as pure state transitions: (game data, item, rng) -> new item.

Each action
  * validates the item first and raises InvalidAction with a human reason,
  * never mutates its input (ItemState is frozen),
  * records which assumptions it relied on (see knowledge/assumptions.json).

Only actions listed in ACTIONS are supported; everything else is reported as
unsupported by the coverage registry instead of being approximated.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..knowledge.gamedata import GameData, Mod
from .item import JEWEL_DOMAINS, ItemState, ItemView, ModInstance
from .modpool import WeightFn, eligible_pool

_ASSUMPTIONS = json.loads((Path(__file__).parents[1] / "knowledge" / "assumptions.json").read_text())


class InvalidAction(Exception):
    pass


def assumption(name: str) -> dict:
    return _ASSUMPTIONS[name]


def _weighted_choice(rng: random.Random, items: list, weights: list[float]):
    return rng.choices(items, weights=weights, k=1)[0]


def _count_from(rng: random.Random, name: str) -> int:
    dist = assumption(name)["value"]
    return int(_weighted_choice(rng, list(dist.keys()), list(dist.values())))


def roll_values(mod: Mod, rng: random.Random) -> tuple[int, ...]:
    return tuple(rng.randint(lo, hi) for _, lo, hi in mod.stats)


def _instance(mod: Mod, rng: random.Random, crafted: bool = False) -> ModInstance:
    return ModInstance(mod.id, roll_values(mod, rng), crafted=crafted)


def add_random_mod(gd: GameData, item: ItemState, rng: random.Random, weight_fn: WeightFn | None = None) -> ItemState | None:
    pool = eligible_pool(gd, item, weight_fn=weight_fn)
    if not pool:
        return None
    entry = _weighted_choice(rng, pool, [e.weight for e in pool])
    return item.with_(explicits=item.explicits + (_instance(entry.mod, rng),))


def fill_to(gd: GameData, item: ItemState, total: int, rng: random.Random, weight_fn: WeightFn | None = None) -> ItemState:
    """Add random mods one at a time until `total` explicits or no legal mod remains."""
    while len(item.explicits) < total:
        nxt = add_random_mod(gd, item, rng, weight_fn)
        if nxt is None:
            break
        item = nxt
    return item


def _rare_count_name(view: ItemView) -> str:
    return "rare_jewel_mod_count" if view.base.domain in JEWEL_DOMAINS else "rare_mod_count"


def _require(cond: bool, reason: str):
    if not cond:
        raise InvalidAction(reason)


def _common_checks(view: ItemView):
    _require(view.base.craftable, f"{view.base.name} cannot be crafted with currency")
    _require(not view.item.corrupted, "item is corrupted")
    view.check_supported()


# ---------------------------------------------------------------- actions
def transmutation(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "normal", "Orb of Transmutation needs a normal item")
    return fill_to(gd, item.with_(rarity="magic"), _count_from(rng, "magic_mod_count"), rng)


def alteration(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "magic", "Orb of Alteration needs a magic item")
    kept = tuple(mi for mi in item.explicits if v.is_protected(mi))
    return fill_to(gd, item.with_(explicits=kept), _count_from(rng, "magic_mod_count"), rng)


def augmentation(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "magic", "Orb of Augmentation needs a magic item")
    _require(len(item.explicits) < 2, "magic item already has 2 mods")
    out = add_random_mod(gd, item, rng)
    _require(out is not None, "no modifier can be added")
    return out


def regal(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "magic", "Regal Orb needs a magic item")
    _require(v.base.domain != "flask", "flasks cannot be rare")
    out = add_random_mod(gd, item.with_(rarity="rare"), rng)
    return out or item.with_(rarity="rare")


def _reforge_rare(gd, item, rng, forced: tuple[ModInstance, ...] = (), weight_fn=None):
    v = ItemView(gd, item)
    kept = tuple(mi for mi in item.explicits if v.is_protected(mi)) + forced
    base_item = item.with_(rarity="rare", explicits=kept)
    return fill_to(gd, base_item, _count_from(rng, _rare_count_name(v)), rng, weight_fn)


def alchemy(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "normal", "Orb of Alchemy needs a normal item")
    _require(v.base.domain != "flask", "flasks cannot be rare")
    return _reforge_rare(gd, item, rng)


def chaos(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Chaos Orb needs a rare item")
    return _reforge_rare(gd, item, rng)


def exalted(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Exalted Orb needs a rare item")
    _require(v.open_slots("prefix") + v.open_slots("suffix") > 0, "no open affix")
    out = add_random_mod(gd, item, rng)
    _require(out is not None, "no modifier can be added")
    return out


def annulment(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity in ("magic", "rare"), "Orb of Annulment needs a magic or rare item")
    removable = [i for i, mi in enumerate(item.explicits) if not v.is_protected(mi)]
    _require(bool(removable), "no removable modifier")
    idx = rng.choice(removable)  # uniform over removable explicit mods
    return item.with_(explicits=tuple(mi for i, mi in enumerate(item.explicits) if i != idx))


def scouring(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity in ("magic", "rare"), "Orb of Scouring needs a magic or rare item")
    kept = tuple(mi for mi in item.explicits if v.is_protected(mi))
    return item.with_(explicits=kept, rarity=item.rarity if kept else "normal")


def divine(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(bool(item.explicits), "no explicit modifiers")
    new = tuple(
        mi if mi.fractured else ModInstance(mi.mod_id, roll_values(gd.mods[mi.mod_id], rng), mi.fractured, mi.crafted)
        for mi in item.explicits
    )
    return item.with_(explicits=new)


def essence(gd, item, rng, *, essence_name: str, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(essence_name in gd.essences_by_name, f"unknown essence {essence_name!r}")
    _, ess = gd.essences_by_name[essence_name]
    mod_id = (ess.get("mods") or {}).get(v.base.item_class)
    _require(mod_id is not None, f"{essence_name} has no modifier for {v.base.item_class}")
    restriction = ess.get("item_level_restriction")
    _require(restriction is None or item.item_level <= restriction, f"{essence_name} only works on items up to item level {restriction}")
    # Shrieking (level 6), Deafening (7) and corruption-only essences can reforge rares.
    can_reforge = ess.get("level", 0) >= 6 or ess.get("type", {}).get("is_corruption_only")
    _require(item.rarity == "normal" or (item.rarity == "rare" and can_reforge),
             "this essence needs a normal item (Shrieking/Deafening also work on rares)")
    forced = (_instance(gd.mods[mod_id], rng),)
    return _reforge_rare(gd, item.with_(explicits=()) if item.rarity == "normal" else item, rng, forced)


def fossil_weight_fn(gd: GameData, fossil_names: list[str]) -> WeightFn:
    """EXPERIMENTAL: multiply each mod's weight by every matching fossil tag weight / 100."""
    fossils = []
    for name in fossil_names:
        _require(name in gd.fossils_by_name, f"unknown fossil {name!r}")
        fossils.append(gd.fossils_by_name[name][1])

    def fn(mod: Mod, w: float) -> float:
        for f in fossils:
            for entry in (f.get("negative_mod_weights") or []) + (f.get("positive_mod_weights") or []):
                if entry["tag"] in mod.implicit_tags:
                    w *= entry["weight"] / 100.0
        return w

    return fn


def fossil(gd, item, rng, *, fossil_names: list[str], **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(1 <= len(fossil_names) <= 4, "a resonator holds 1 to 4 fossils")
    _require(item.rarity in ("normal", "rare"), "fossils need a normal or rare item")
    return _reforge_rare(gd, item, rng, weight_fn=fossil_weight_fn(gd, fossil_names))


def bench_craft(gd, item, rng, *, mod_id: str, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity in ("magic", "rare"), "bench crafts need a magic or rare item")
    option = next((o for o in gd.bench_options if (o.get("actions") or {}).get("add_explicit_mod") == mod_id), None)
    _require(option is not None, f"{mod_id} is not a crafting bench option in game data {gd.version}")
    _require(v.base.item_class in option.get("item_classes", []), f"cannot be crafted on {v.base.item_class}")
    mod = gd.mods[mod_id]
    _require(v.open_slots(mod.generation_type) > 0, f"no open {mod.generation_type}")
    _require(not v.groups().intersection(mod.groups), "item already has a modifier of this group")
    crafted = sum(1 for mi in item.explicits if mi.crafted)
    limit = 3 if v.multimod else 1
    _require(crafted < limit, "item already has the maximum number of crafted modifiers")
    return item.with_(explicits=item.explicits + (_instance(mod, rng, crafted=True),))


def remove_crafted(gd, item, rng, **_):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(any(mi.crafted for mi in item.explicits), "no crafted modifiers")
    return item.with_(explicits=tuple(mi for mi in item.explicits if not mi.crafted))


@dataclass(frozen=True)
class ActionInfo:
    id: str
    name: str
    fn: Callable
    currency: str | None  # poe.ninja / in-game name used for pricing
    assumptions: tuple[str, ...] = ()
    status: str = "implemented_partially_verified"


ACTIONS: dict[str, ActionInfo] = {
    a.id: a
    for a in [
        ActionInfo("transmutation", "Orb of Transmutation", transmutation, "Orb of Transmutation", ("magic_mod_count",)),
        ActionInfo("alteration", "Orb of Alteration", alteration, "Orb of Alteration", ("magic_mod_count",)),
        ActionInfo("augmentation", "Orb of Augmentation", augmentation, "Orb of Augmentation"),
        ActionInfo("regal", "Regal Orb", regal, "Regal Orb"),
        ActionInfo("alchemy", "Orb of Alchemy", alchemy, "Orb of Alchemy", ("rare_mod_count",)),
        ActionInfo("chaos", "Chaos Orb", chaos, "Chaos Orb", ("rare_mod_count",)),
        ActionInfo("exalted", "Exalted Orb", exalted, "Exalted Orb"),
        ActionInfo("annulment", "Orb of Annulment", annulment, "Orb of Annulment"),
        ActionInfo("scouring", "Orb of Scouring", scouring, "Orb of Scouring"),
        ActionInfo("divine", "Divine Orb", divine, "Divine Orb"),
        ActionInfo("essence", "Essence", essence, None, ("rare_mod_count",)),
        ActionInfo("fossil", "Fossils (resonator)", fossil, None, ("rare_mod_count",), status="experimental"),
        ActionInfo("bench_craft", "Crafting bench: add modifier", bench_craft, None),
        ActionInfo("remove_crafted", "Crafting bench: remove crafted modifiers", remove_crafted, None),
    ]
}


def apply(gd: GameData, item: ItemState, action_id: str, rng: random.Random, **params) -> ItemState:
    if action_id not in ACTIONS:
        raise InvalidAction(f"unknown or unsupported action {action_id!r}")
    return ACTIONS[action_id].fn(gd, item, rng, **params)
