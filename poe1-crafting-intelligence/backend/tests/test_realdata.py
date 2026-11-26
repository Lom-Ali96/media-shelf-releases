"""Reference cases against the real imported game data (skipped if none imported).

These pin facts that are visible in-game, so a data or engine regression after a
patch shows up as a failing test instead of a silently wrong recommendation."""
import pytest

from poeci.engine.item import ItemState, tier_index
from poeci.engine.modpool import eligible_pool
from poeci.parsing.clipboard import ItemParser

pytestmark = pytest.mark.realdata


def test_sapphire_ring_life_tiers(real_gd):
    ring = real_gd.bases_by_name["Sapphire Ring"]
    assert real_gd.mods["IncreasedLife7"].name == "Virile"
    assert tier_index(real_gd, ring, real_gd.mods["IncreasedLife7"])[0] == 1


def test_pool_sums_to_one_for_many_bases(real_gd):
    for name in ["Sapphire Ring", "Vaal Regalia", "Hubris Circlet", "Stygian Vise", "Cobalt Jewel", "Divine Life Flask"]:
        b = real_gd.bases_by_name[name]
        rarity = "magic" if b.domain == "flask" else "rare"
        pool = eligible_pool(real_gd, ItemState(b.id, 86, rarity))
        assert pool, name
        assert abs(sum(e.probability for e in pool) - 1) < 1e-9, name


def test_royale_mods_never_roll(real_gd):
    for name in ["Spine Bow", "Two-Toned Boots", "Stygian Vise"]:
        b = real_gd.bases_by_name[name]
        pool = eligible_pool(real_gd, ItemState(b.id, 86, "rare"))
        assert not [e.mod.id for e in pool if "Royale" in e.mod.id], name


def test_influence_widens_pool(real_gd):
    b = real_gd.bases_by_name["Hubris Circlet"]
    plain = len(eligible_pool(real_gd, ItemState(b.id, 86, "rare")))
    shaper = len(eligible_pool(real_gd, ItemState(b.id, 86, "rare", influences=frozenset({"shaper"}))))
    assert shaper > plain


def test_parse_real_advanced_item(real_gd):
    text = """Item Class: Rings
Rarity: Rare
Kraken Coil
Sapphire Ring
--------
Item Level: 84
--------
{ Implicit Modifier — Elemental, Cold, Resistance }
+25(20-30)% to Cold Resistance
--------
{ Prefix Modifier "Virile" (Tier: 1) — Life }
+110(100-114) to maximum Life
{ Suffix Modifier "of the Magma" (Tier: 2) — Elemental, Fire, Resistance }
+44(42-45)% to Fire Resistance
"""
    item = ItemParser(real_gd).parse(text)
    assert [m.mod_id for m in item.mods] == ["IncreasedLife7", "FireResist7"]


def test_every_craft_idea_fits_the_game_data(real_gd, conn):
    from fastapi.testclient import TestClient

    from poeci.api.app import create_app

    ideas = TestClient(create_app(real_gd, conn)).get("/api/ideas").json()
    assert ideas and [i["name"] for i in ideas if i["problem"]] == []


def test_mod_pools_match_craft_of_exile(real_gd):
    """Reference cases behind pool.spawn_weights = implemented_verified (see mechanics_registry.json)."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).parents[2] / "scripts" / "compare_craftofexile.py"
    spec = importlib.util.spec_from_file_location("compare_coe", script)
    coe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coe)
    if not coe.CACHE.exists():
        pytest.skip("Craft of Exile data not downloaded (run scripts/compare_craftofexile.py once)")
    d = coe.load_coe()
    # Both explained in the registry notes: CoE skips the data's 50% wand generation weight on these.
    known = {("Imbued Wand", None, ("suffix", "ManaLeech", 50)),
             ("Imbued Wand", "hunter", ("prefix", "AddedLightningDamagePerIntelligence", 68))}
    for ilvl in (30, 68, 86):
        for base, influence in coe.CASES:
            theirs, _ = coe.coe_tiers(d, base, ilvl, influence)
            ours, _ = coe.our_tiers(real_gd, base, ilvl, influence)
            assert set(theirs) == set(ours), (base, influence, ilvl)
            bad = [k for k in theirs if abs(theirs[k] - ours[k]) > 0.5 and (base, influence, k) not in known]
            assert not bad, (base, influence, ilvl, bad)


def test_lock_meta_crafts_cost_what_the_3_30_patch_notes_say(real_gd):
    """Patch notes 3.30.0 (see docs/MECHANICS_3_30.md) vs the bench data."""
    cost = {}
    for o in real_gd.bench_options:
        mid = (o.get("actions") or {}).get("add_explicit_mod") or ""
        if "CannotChange" in mid:
            cost[mid] = {real_gd.bases[k].name: v for k, v in (o.get("cost") or {}).items()}
    assert cost["StrMasterItemGenerationCannotChangeOnePrefixes"] == {"Divine Orb": 1}
    assert cost["DexMasterItemGenerationCannotChangeTwoSuffixes"] == {"Divine Orb": 2}
    assert cost["StrMasterItemGenerationCannotChangePrefixes"] == {"Divine Orb": 4, "Sacred Orb": 1}
    assert cost["DexMasterItemGenerationCannotChangeSuffixesB"] == {"Divine Orb": 4, "Blessed Orb": 4}
    assert cost["StrMasterItemGenerationCannotChangePrefixesC"] == {"Divine Orb": 4, "Exalted Orb": 8}
