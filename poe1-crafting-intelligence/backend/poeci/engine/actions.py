"""Crafting actions as pure state transitions: (game data, item, rng) -> new item.

Each action
  * validates the item first and raises InvalidAction with a human reason,
  * never mutates its input (ItemState is frozen),
  * records which assumptions it relied on (see knowledge/assumptions.json).

Only actions listed in ACTIONS are supported; everything else is reported as
unsupported by the coverage registry instead of being approximated.
"""
from __future__ import annotations

import inspect
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..knowledge.gamedata import GameData, Mod
from .item import JEWEL_DOMAINS, ItemState, ItemView, ModInstance, _tier_family, spawn_weight, tier_index
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


def _reforge_rare(gd, item, rng, forced: tuple[ModInstance, ...] = (), weight_fn=None, count: int | None = None,
                  keep_locked: bool = True):
    """Reroll a rare. Fractured mods always stay; mods protected by a prefix/suffix lock stay only
    when `keep_locked` (Chaos, Harvest). Essences and fossils ignore the locks (Maxroll crafting
    resources, read 2026-11-26), so they pass keep_locked=False."""
    v = ItemView(gd, item)
    kept = tuple(mi for mi in item.explicits if (v.is_protected(mi) if keep_locked else mi.fractured)) + forced
    base_item = item.with_(rarity="rare", explicits=kept)
    return fill_to(gd, base_item, count or _count_from(rng, _rare_count_name(v)), rng, weight_fn)


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
    return _reforge_rare(gd, item.with_(explicits=()) if item.rarity == "normal" else item, rng, forced, keep_locked=False)


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
    return _reforge_rare(gd, item, rng, weight_fn=fossil_weight_fn(gd, fossil_names), keep_locked=False)


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


# ------------------------------------------------- Harvest and Bestiary (EXPERIMENTAL)
# Craft lists come from knowledge/harvest_crafts.json and docs/MECHANICS_3_30.md. The
# order of rolling (tagged mod first, then fill) is the common understanding, not a
# published rule, so these actions are experimental until cross-checked.
def _add_tagged(gd, item, rng, tag: str, gen_types=("prefix", "suffix")) -> ItemState | None:
    pool = [e for e in eligible_pool(gd, item, gen_types=gen_types) if tag is None or tag in e.mod.implicit_tags]
    if not pool:
        return None
    entry = _weighted_choice(rng, pool, [e.weight for e in pool])
    return item.with_(explicits=item.explicits + (_instance(entry.mod, rng),))


def _remove_random(item: ItemState, v: ItemView, rng, gen_type: str | None = None) -> ItemState:
    idx = [i for i, (mi, m) in enumerate(v.mods()) if not v.is_protected(mi) and gen_type in (None, m.generation_type)]
    _require(bool(idx), f"no removable {gen_type or 'modifier'}")
    drop = rng.choice(idx)
    return item.with_(explicits=tuple(mi for i, mi in enumerate(item.explicits) if i != drop))


def harvest_reforge(gd, item, rng, *, tag: str, **_):
    """Reforge a Rare item with new random modifiers, including a <tag> modifier."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Harvest reforges need a rare item")
    kept = tuple(mi for mi in item.explicits if v.is_protected(mi))
    out = _add_tagged(gd, item.with_(explicits=kept), rng, tag)
    _require(out is not None, f"no '{tag}' modifier can roll on this item")
    return fill_to(gd, out, _count_from(rng, _rare_count_name(v)), rng)


def harvest_add_remove(gd, item, rng, *, tag: str, **_):
    """Add a new <tag> modifier and remove a random modifier (non-influenced items)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "this Harvest craft needs a rare item")
    _require(not item.influences, "not usable on influenced items")
    out = _add_tagged(gd, _remove_random(item, v, rng), rng, tag)
    _require(out is not None, f"no '{tag}' modifier can be added")
    return out


def harvest_reforge_same(gd, item, rng, **_):
    """Reforge a Rare item, being more likely to receive the same modifier types.
    Weight multiplier and 'never fewer mods' come from assumptions.json (outdated report)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Harvest reforges need a rare item")
    present = {m.type for _, m in v.mods() if not v.is_protected(_)}
    mult = assumption("harvest_same_type_multiplier")["value"]
    weight_fn = lambda mod, w: w * mult if mod.type in present else w  # noqa: E731
    count = _count_from(rng, _rare_count_name(v))
    if assumption("harvest_same_type_keeps_mod_count")["value"]:
        count = max(count, len(item.explicits))
    return _reforge_rare(gd, item, rng, weight_fn=weight_fn, count=count)


_ELEMENTS = ("Fire", "Cold", "Lightning")


def harvest_swap(gd, item, rng, *, kind: str, from_element: str, to_element: str, **_):
    """Change a <from> resistance/damage modifier into a similar-tier <to> modifier."""
    v = ItemView(gd, item)
    _common_checks(v)
    src, dst = from_element.title(), to_element.title()
    _require(src in _ELEMENTS and dst in _ELEMENTS and src != dst, "elements must be two of fire, cold, lightning")
    _require(kind in ("resistance", "damage"), "kind must be resistance or damage")
    marker = "Resist" if kind == "resistance" else "Damage"
    tags = v.tags()
    for i, (mi, m) in enumerate(v.mods()):
        if mi.crafted or src not in m.type or marker not in m.type or any(e in m.type for e in _ELEMENTS if e != src):
            continue  # hybrids (two elements) are not swappable
        target_type = m.type.replace(src, dst, 1)
        twin = next((x for x in gd.affix_mods_by_domain.get(v.base.domain, [])
                     if x.type == target_type and x.generation_type == m.generation_type), None)
        if twin is None:
            continue
        family = _tier_family(gd, v.base, twin, frozenset(tags))
        if not family:
            continue
        tier, _n = tier_index(gd, v.base, m, tags)
        new = gd.mods[family[min(max(tier, 1), len(family)) - 1]]  # "similar tier": same tier number
        out = list(item.explicits)
        out[i] = ModInstance(new.id, roll_values(new, rng), mi.fractured, mi.crafted)
        return item.with_(explicits=tuple(out))
    raise InvalidAction(f"no {src.lower()} {kind} modifier that can be changed to {dst.lower()}")


def fracturing(gd, item, rng, **_):
    """Fracturing Orb: fracture a random modifier on a rare item with at least 4 modifiers
    (not influenced, not already fractured). Crafted mods excluded: see assumptions.json."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Fracturing Orb needs a rare item")
    _require(len(item.explicits) >= 4, "Fracturing Orb needs at least 4 modifiers")
    _require(not item.influences, "Fracturing Orb cannot be used on influenced items")
    _require(not any(mi.fractured for mi in item.explicits), "item is already fractured")
    skip_crafted = assumption("fracture_excludes_crafted")["value"]
    idx = [i for i, mi in enumerate(item.explicits) if not (skip_crafted and mi.crafted)]
    pick = rng.choice(idx)
    out = list(item.explicits)
    out[pick] = ModInstance(out[pick].mod_id, out[pick].values, True, out[pick].crafted)
    return item.with_(explicits=tuple(out))


def _beast_swap(gd, item, rng, remove: str, add: str):
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "this beastcraft only works on rare items")
    out = _add_tagged(gd, _remove_random(item, v, rng, remove), rng, None, gen_types=(add,))
    _require(out is not None, f"no {add} can be added")
    return out


def beast_suffix_for_prefix(gd, item, rng, **_):
    """Farric Lynx Alpha: add a suffix, remove a random prefix."""
    return _beast_swap(gd, item, rng, "prefix", "suffix")


def beast_prefix_for_suffix(gd, item, rng, **_):
    """Farric Wolf Alpha: add a prefix, remove a random suffix."""
    return _beast_swap(gd, item, rng, "suffix", "prefix")


def beast_metamod(gd, item, rng, *, mod_id: str, **_):
    """Wild Bristle Matron: add a crafted meta-modifier of your choice to a non-unique item.
    pohx's 3.30 RF helmet guide (pohx.net/crafts/elder-rf-helmet, Nov 2026) uses it to add
    'Suffixes Cannot Be Changed'; it is placed like the bench craft (slot, crafted-mod limit)."""
    _require(mod_id in gd.mods and gd.mods[mod_id].type.startswith("ItemGeneration")
             and not gd.mods[mod_id].type.endswith("Count"), "choose a meta-modifier (lock, multimod, cannot roll ...)")
    return bench_craft(gd, item, rng, mod_id=mod_id)


# ------------------------------------------------------------ influence (EXPERIMENTAL)
INFLUENCES = ("shaper", "elder", "crusader", "hunter", "redeemer", "warlord")


def influence_exalt(gd, item, rng, *, influence: str, **_):
    """<Influence>'s Exalted Orb: give an uninfluenced rare that influence and add one of its
    mods (weights from that influence's own pool, verified against Craft of Exile)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(influence in INFLUENCES, f"influence must be one of {', '.join(INFLUENCES)}")
    _require(item.rarity == "rare", "influence Exalted Orbs need a rare item")
    _require(not item.influences, "item is already influenced")
    _require(v.open_slots("prefix") + v.open_slots("suffix") > 0, "no open affix")
    plain = {e.mod.id for e in eligible_pool(gd, item)}
    with_infl = item.with_(influences=frozenset({influence}))
    pool = [e for e in eligible_pool(gd, with_infl) if e.mod.id not in plain]
    _require(bool(pool), f"no {influence} modifier can roll on this item")
    entry = _weighted_choice(rng, pool, [e.weight for e in pool])
    return with_infl.with_(explicits=item.explicits + (_instance(entry.mod, rng),))


# ------------------------------------------------------------ Eldritch (EXPERIMENTAL)
# Rules from Maxroll (crafting resources + Eldritch guide, read 2026-11-26): six implicit
# tiers; Embers give a Searing Exarch implicit, Ichors an Eater of Worlds implicit; the side
# with the higher tier is dominant and decides whether Eldritch Exalted/Annulment act on
# prefixes (Exarch) or suffixes (Eater); not on Shaper/Elder/conqueror items. That a currency
# rolls exactly its own tier is an assumption (assumptions.json: eldritch_currency_tier).
ELDRITCH_TIERS = {1: "Lesser", 2: "Greater", 3: "Grand", 4: "Exceptional", 5: "Exquisite", 6: "Perfect"}
ELDRITCH_SIDES = {"exarch": "searing_exarch_implicit", "eater": "eater_of_worlds_implicit"}


def eldritch_tier(mod_id: str | None) -> int:
    m = re.search(r"(\d+)\D*$", mod_id or "")
    return int(m.group(1)) if m else 0


def dominant_side(item: ItemState) -> str | None:
    ex, ea = eldritch_tier(item.exarch), eldritch_tier(item.eater)
    if ex == ea:
        return None  # a tie is not documented: refuse rather than guess
    return "exarch" if ex > ea else "eater"


def eldritch_currency(gd, item, rng, *, side: str, tier: int, **_):
    """Lesser/Greater/Grand/Exceptional Eldritch Ember (exarch) or Ichor (eater)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(side in ELDRITCH_SIDES and tier in (1, 2, 3, 4), "side must be exarch/eater and tier 1-4")
    _require(item.rarity != "unique", "not usable on unique items")
    _require(not item.influences, "Eldritch implicits cannot be added to Shaper, Elder or conqueror items")
    tags = v.tags()
    pool = [m for m in gd.mods.values() if m.generation_type == ELDRITCH_SIDES[side] and m.domain == v.base.domain
            and eldritch_tier(m.id) == tier and spawn_weight(m, tags) > 0]
    _require(bool(pool), "no Eldritch implicit of this tier can roll on this item")
    pick = _weighted_choice(rng, pool, [spawn_weight(m, tags) for m in pool])
    return item.with_(**{side: pick.id})


def _eldritch_side(item: ItemState) -> str:
    side = dominant_side(item)
    _require(side is not None, "needs a dominant Eldritch implicit (the two tiers are equal or missing)")
    return "prefix" if side == "exarch" else "suffix"


def eldritch_exalted(gd, item, rng, **_):
    """Eldritch Exalted Orb: add a prefix (Exarch dominant) or suffix (Eater dominant)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity == "rare", "Eldritch Exalted Orb needs a rare item")
    gen = _eldritch_side(item)
    _require(v.open_slots(gen) > 0, f"no open {gen}")
    out = _add_tagged(gd, item, rng, None, gen_types=(gen,))
    _require(out is not None, f"no {gen} can be added")
    return out


def eldritch_annulment(gd, item, rng, **_):
    """Eldritch Orb of Annulment: remove a random prefix (Exarch) or suffix (Eater)."""
    v = ItemView(gd, item)
    _common_checks(v)
    _require(item.rarity in ("magic", "rare"), "needs a magic or rare item")
    return _remove_random(item, v, rng, _eldritch_side(item))


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
        ActionInfo("harvest_reforge", "Harvest: reforge with a tagged modifier", harvest_reforge, None, ("rare_mod_count",), status="experimental"),
        ActionInfo("harvest_add_remove", "Harvest: add a tagged modifier, remove a random one", harvest_add_remove, None, status="experimental"),
        ActionInfo("harvest_reforge_same", "Harvest: reforge, more likely the same modifier types", harvest_reforge_same, None,
                   ("rare_mod_count", "harvest_same_type_multiplier", "harvest_same_type_keeps_mod_count"), status="experimental"),
        ActionInfo("harvest_swap", "Harvest: change a resistance/damage modifier to another element", harvest_swap, None, status="experimental"),
        ActionInfo("fracturing", "Fracturing Orb", fracturing, "Fracturing Orb", ("fracture_excludes_crafted",), status="experimental"),
        ActionInfo("influence_exalt", "Influence Exalted Orb (Shaper's, Elder's, Crusader's, Hunter's, Redeemer's, Warlord's)",
                   influence_exalt, None, status="experimental"),
        ActionInfo("eldritch_currency", "Eldritch Ember / Ichor (Lesser to Exceptional)", eldritch_currency, None,
                   ("eldritch_currency_tier",), status="experimental"),
        ActionInfo("eldritch_exalted", "Eldritch Exalted Orb", eldritch_exalted, "Eldritch Exalted Orb", status="experimental"),
        ActionInfo("eldritch_annulment", "Eldritch Orb of Annulment", eldritch_annulment, "Eldritch Orb of Annulment", status="experimental"),
        ActionInfo("beast_suffix_for_prefix", "Beastcraft (Farric Lynx Alpha): add a suffix, remove a random prefix", beast_suffix_for_prefix, "Farric Lynx Alpha", status="experimental"),
        ActionInfo("beast_prefix_for_suffix", "Beastcraft (Farric Wolf Alpha): add a prefix, remove a random suffix", beast_prefix_for_suffix, "Farric Wolf Alpha", status="experimental"),
        ActionInfo("beast_metamod", "Beastcraft (Wild Bristle Matron): add a meta-modifier", beast_metamod, "Wild Bristle Matron", status="experimental"),
    ]
}


def apply(gd: GameData, item: ItemState, action_id: str, rng: random.Random, **params) -> ItemState:
    if action_id not in ACTIONS:
        raise InvalidAction(f"unknown or unsupported action {action_id!r}")
    if missing := missing_params(action_id, params):
        raise InvalidAction(f"{ACTIONS[action_id].name}: missing {', '.join(missing)}")
    return ACTIONS[action_id].fn(gd, item, rng, **params)


def missing_params(action_id: str, params: dict) -> list[str]:
    """Required keyword parameters of an action that `params` does not provide."""
    sig = inspect.signature(ACTIONS[action_id].fn)
    return [n for n, p in sig.parameters.items() if p.kind is p.KEYWORD_ONLY and p.default is p.empty and n not in params]
