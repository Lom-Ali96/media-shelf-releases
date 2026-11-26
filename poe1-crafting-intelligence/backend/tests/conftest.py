"""Shared fixtures: a tiny hand-written game-data snapshot in RePoE format, so
rules can be tested with exactly known weights and without network access."""
from __future__ import annotations

import json

import pytest

from poeci.knowledge.gamedata import GameData
from poeci.knowledge.importer import latest_snapshot
from poeci.storage import db


def _mod(name, gen, group, typ, lvl, weights, text, stat=("s", 1, 10), tags=(), adds=(), domain="item", essence_only=False):
    return {
        "name": name, "domain": domain, "generation_type": gen, "groups": [group], "type": typ,
        "required_level": lvl, "spawn_weights": [{"tag": t, "weight": w} for t, w in weights],
        "generation_weights": [], "implicit_tags": list(tags), "adds_tags": list(adds),
        "is_essence_only": essence_only, "text": text,
        "stats": [{"id": stat[0], "min": stat[1], "max": stat[2]}],
    }


MODS = {
    # Life: 3 tiers, prefix. Weights 1000 each on rings ("default").
    "Life1": _mod("Hale", "prefix", "IncreasedLife", "IncreasedLife", 1, [("default", 1000)], "+(3-9) to maximum Life", ("life", 3, 9), ("life",)),
    "Life2": _mod("Robust", "prefix", "IncreasedLife", "IncreasedLife", 30, [("default", 1000)], "+(40-49) to maximum Life", ("life", 40, 49), ("life",)),
    "Life3": _mod("Virile", "prefix", "IncreasedLife", "IncreasedLife", 70, [("default", 1000)], "+(100-114) to maximum Life", ("life", 100, 114), ("life",)),
    # Attack prefix that adds a tag, weight 500 on rings
    "Phys1": _mod("Glinting", "prefix", "PhysAdd", "PhysAdd", 1, [("ring", 500), ("default", 0)], "Adds (1-2) to (3-4) Physical Damage to Attacks", ("phys", 1, 2), ("attack", "damage"), ("has_attack_mod",)),
    # Caster prefix 500 on rings
    "Spell1": _mod("Apprentice's", "prefix", "SpellDamage", "SpellDamage", 1, [("ring", 500), ("default", 0)], "(5-9)% increased Spell Damage", ("spell", 5, 9), ("caster", "damage")),
    # Suffixes
    "Fire1": _mod("of the Whelpling", "suffix", "FireResistance", "FireResistance", 1, [("default", 1000)], "+(6-11)% to Fire Resistance", ("fire", 6, 11), ("fire", "resistance")),
    "Fire2": _mod("of the Magma", "suffix", "FireResistance", "FireResistance", 72, [("default", 1000)], "+(42-45)% to Fire Resistance", ("fire", 42, 45), ("fire", "resistance")),
    "Cold1": _mod("of the Inuit", "suffix", "ColdResistance", "ColdResistance", 1, [("default", 1000)], "+(6-11)% to Cold Resistance", ("cold", 6, 11), ("cold", "resistance")),
    "Str1": _mod("of the Brute", "suffix", "Strength", "Strength", 1, [("default", 1000)], "+(8-12) to Strength", ("str", 8, 12), ("attribute",)),
    # Zero weight on rings (weapon only) - must never appear
    "WeaponOnly": _mod("Heavy", "prefix", "LocalPhys", "LocalPhys", 1, [("weapon", 1000), ("default", 0)], "(40-49)% increased Physical Damage"),
    # Shaper-only suffix
    "ShaperCrit": _mod("of Shaping", "suffix", "CritShaper", "CritShaper", 68, [("ring_shaper", 1000), ("default", 0)], "(10-15)% increased Global Critical Strike Chance", ("crit", 10, 15), ("critical",)),
    # Essence-only
    "EssLife": _mod("Essences", "prefix", "IncreasedLife", "IncreasedLife", 1, [("default", 0)], "+(115-120) to maximum Life", ("life", 115, 120), ("life",), essence_only=True),
    # Crafted bench mod + metamods
    "CraftedCold": _mod("of Craft", "suffix", "ColdResistance", "ColdResistance", 1, [("default", 0)], "+(16-20)% to Cold Resistance", ("cold", 16, 20), domain="crafted"),
    "XItemGenerationCannotRollAttackAffixes": _mod("of Spellcraft", "suffix", "ItemGenerationCannotRollAttackAffixes", "ItemGenerationCannotRollAttackAffixes", 1, [("default", 0)], "Cannot roll Attack Modifiers", domain="crafted"),
    "XItemGenerationCanHaveMultipleCraftedMods": _mod("of Crafting", "suffix", "ItemGenerationCanHaveMultipleCraftedMods", "ItemGenerationCanHaveMultipleCraftedMods", 1, [("default", 0)], "Can have up to 3 Crafted Modifiers", domain="crafted"),
    "XMasterItemGenerationCannotChangePrefixes": _mod("of the Order", "suffix", "ItemGenerationCannotChangePrefixes", "ItemGenerationCannotChangePrefixes", 1, [("default", 0)], "Prefix Modifiers cannot be changed", domain="crafted"),
    # Eldritch implicits (tier = trailing digit): one Exarch family, one Eater family
    "ExarchSpeedEldritchImplicit1": dict(_mod("", "searing_exarch_implicit", "ExSpeed", "ExSpeed", 1, [("default", 1000)], "5% increased Movement Speed"), stats=[]),
    "ExarchSpeedEldritchImplicit3": dict(_mod("", "searing_exarch_implicit", "ExSpeed", "ExSpeed", 1, [("default", 1000)], "7% increased Movement Speed"), stats=[]),
    "EaterLifeEldritchImplicit2": dict(_mod("", "eater_of_worlds_implicit", "EaLife", "EaLife", 1, [("default", 1000)], "+20 to maximum Life"), stats=[]),
    "XMasterItemGenerationCannotChangeOnePrefixes": _mod("of the Order", "suffix", "ItemGenerationCannotChangeOnePrefixes", "X", 1, [("default", 0)], "1 Prefix Modifier cannot be changed", domain="crafted"),
}

BASES = {
    "Metadata/Items/Rings/Ring1": {"domain": "item", "item_class": "Ring", "name": "Test Ring", "tags": ["ring", "default"],
                                     "implicits": [], "drop_level": 1, "release_state": "released"},
    "Metadata/Items/Rings/Old": {"domain": "item", "item_class": "Ring", "name": "Legacy Ring", "tags": ["ring", "default"],
                                   "implicits": [], "drop_level": 1, "release_state": "legacy"},
}
ITEM_CLASSES = {"Ring": {"name": "Rings", "influence_tags": ["ring_crusader", "ring_elder", "ring_basilisk", "ring_eyrie", "ring_shaper", "ring_adjudicator"]}}
ESSENCES = {
    "E1": {"name": "Whispering Essence of Test", "level": 1, "item_level_restriction": 35, "mods": {"Ring": "Life1"}, "type": {"tier": 1, "is_corruption_only": False}},
    "E7": {"name": "Deafening Essence of Test", "level": 7, "item_level_restriction": None, "mods": {"Ring": "EssLife"}, "type": {"tier": 1, "is_corruption_only": False}},
}
FOSSILS = {
    "F1": {"name": "Scorched Fossil", "positive_mod_weights": [{"tag": "fire", "weight": 1000}], "negative_mod_weights": [{"tag": "cold", "weight": 0}]},
}
BENCH = [
    {"actions": {"add_explicit_mod": "CraftedCold"}, "item_classes": ["Ring"], "cost": {}, "master": "Bench"},
    {"actions": {"add_explicit_mod": "XItemGenerationCannotRollAttackAffixes"}, "item_classes": ["Ring"], "cost": {}, "master": "Bench"},
    {"actions": {"add_explicit_mod": "XItemGenerationCanHaveMultipleCraftedMods"}, "item_classes": ["Ring"], "cost": {}, "master": "Bench"},
    {"actions": {"add_explicit_mod": "XMasterItemGenerationCannotChangePrefixes"}, "item_classes": ["Ring"], "cost": {}, "master": "Bench"},
]

RING = "Metadata/Items/Rings/Ring1"


@pytest.fixture(scope="session")
def snapshot_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("snap")
    files = {"mods.json": MODS, "base_items.json": BASES, "item_classes.json": ITEM_CLASSES,
             "essences.json": ESSENCES, "fossils.json": FOSSILS, "crafting_bench_options.json": BENCH}
    for name, data in files.items():
        (d / name).write_text(json.dumps(data))
    (d / "manifest.json").write_text(json.dumps({"game_version": "3.30.0.1"}))
    return d


@pytest.fixture(scope="session")
def gd(snapshot_dir):
    return GameData.from_dir(snapshot_dir)


@pytest.fixture()
def conn():
    return db.connect(":memory:")


@pytest.fixture(scope="session")
def real_gd():
    snap = latest_snapshot()
    if snap is None:
        pytest.skip("no real game-data snapshot imported")
    return GameData.from_dir(snap)
