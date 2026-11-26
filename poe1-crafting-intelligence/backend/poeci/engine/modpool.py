"""Which modifiers can roll next, and with what exact probability."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..knowledge.gamedata import GameData, Mod
from .item import ItemState, ItemView, generation_multiplier, spawn_weight

WeightFn = Callable[[Mod, float], float]  # (mod, current weight) -> new weight


@dataclass(frozen=True)
class PoolEntry:
    mod: Mod
    weight: float
    probability: float


def eligible_pool(
    gd: GameData,
    item: ItemState,
    *,
    gen_types: tuple[str, ...] = ("prefix", "suffix"),
    weight_fn: WeightFn | None = None,
    apply_metamods: bool = True,
) -> list[PoolEntry]:
    """All mods that can be *added* to `item` by one random roll, with exact
    probabilities (weights normalised over the pool).

    Rules applied (in order):
      * same domain as the base (rings roll "item" mods, flasks "flask" mods...)
      * prefix/suffix only, and only where that affix type still has an open slot
      * not essence-only
      * required item level <= item level
      * no mod sharing a modifier group with a mod already on the item
      * spawn weight from the first matching tag (base tags + influence tags +
        tags added by existing mods) times the generation-weight multiplier
      * metamods: "Cannot roll Attack/Caster Modifiers" remove those mods
      * optional weight_fn (fossils etc.)
    """
    view = ItemView(gd, item)
    view.check_supported()
    tags = frozenset(view.tags())
    taken = view.groups()
    open_types = [g for g in gen_types if view.open_slots(g) > 0]
    no_attack = apply_metamods and view.cannot_roll_attack
    no_caster = apply_metamods and view.cannot_roll_caster
    entries: list[tuple[Mod, float]] = []
    for m, w in _candidates(gd, view.base.domain, tags, item.item_level):
        if m.generation_type not in open_types:
            continue
        if not taken.isdisjoint(m.groups):
            continue
        if no_attack and "attack" in m.implicit_tags:
            continue
        if no_caster and "caster" in m.implicit_tags:
            continue
        if weight_fn is not None:
            w = weight_fn(m, w)
        if w > 0:
            entries.append((m, w))
    total = sum(w for _, w in entries)
    return [PoolEntry(m, w, w / total) for m, w in entries] if total else []


def _candidates(gd: GameData, domain: str, tags: frozenset[str], ilvl: int) -> list[tuple[Mod, float]]:
    """Mods that could roll on an item with these tags and item level, ignoring
    slots and groups. Cached per game-data instance: this is the hot path of
    every simulation."""
    cache = gd.__dict__.setdefault("_candidate_cache", {})
    key = (domain, tags, ilvl)
    hit = cache.get(key)
    if hit is None:
        hit = []
        for m in gd.affix_mods_by_domain.get(domain, []):
            if m.is_essence_only or m.required_level > ilvl:
                continue
            w = spawn_weight(m, tags)
            if w <= 0:
                continue
            w *= generation_multiplier(m, tags)
            if w > 0:
                hit.append((m, w))
        cache[key] = hit
    return hit


def probability_of(pool: list[PoolEntry], predicate: Callable[[Mod], bool]) -> float:
    return sum(e.probability for e in pool if predicate(e.mod))
