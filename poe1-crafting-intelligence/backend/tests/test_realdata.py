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
