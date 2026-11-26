import random

import pytest

from poeci.engine.actions import InvalidAction, apply, dominant_side
from poeci.engine.item import ItemState, ItemView, ModInstance
from poeci.engine.recipe import cost_of
from poeci.parsing.clipboard import ItemParser

from .conftest import RING


def rare(*mods, **kw):
    return ItemState(RING, 84, "rare", tuple(ModInstance(m, (1,)) for m in mods), **kw)


def test_influence_exalt_adds_influence_and_its_mod(gd):
    out = apply(gd, rare("Life3"), "influence_exalt", random.Random(1), influence="shaper")
    assert out.influences == frozenset({"shaper"}) and out.explicits[-1].mod_id == "ShaperCrit"
    with pytest.raises(InvalidAction, match="already influenced"):
        apply(gd, out, "influence_exalt", random.Random(1), influence="hunter")
    with pytest.raises(InvalidAction, match="no hunter modifier"):  # test data has no hunter mods
        apply(gd, rare("Life3"), "influence_exalt", random.Random(1), influence="hunter")
    assert cost_of(gd, "influence_exalt", {"influence": "shaper"}, out) == {"Shaper's Exalted Orb": 1}


def test_eldritch_currency_dominance_exalt_and_annul(gd):
    r = random.Random(2)
    item = apply(gd, rare("Life3", "Cold1"), "eldritch_currency", r, side="exarch", tier=3)
    assert item.exarch == "ExarchSpeedEldritchImplicit3" and dominant_side(item) == "exarch"
    item = apply(gd, item, "eldritch_currency", r, side="eater", tier=2)
    assert item.eater == "EaterLifeEldritchImplicit2" and dominant_side(item) == "exarch"  # tier 3 beats 2
    v = ItemView(gd, apply(gd, item, "eldritch_exalted", r))
    assert v.count("prefix") == 2  # Exarch dominant -> a prefix was added
    assert ItemView(gd, apply(gd, item, "eldritch_annulment", r)).count("prefix") == 0
    assert dominant_side(rare("Life3", exarch="ExarchSpeedEldritchImplicit1", eater="EaterLifeEldritchImplicit2")) == "eater"
    tie = rare("Life3", exarch="ExarchSpeedEldritchImplicit3", eater="EaterLifeEldritchImplicit3")
    assert dominant_side(tie) is None  # equal tiers: undocumented, so no side is assumed
    with pytest.raises(InvalidAction, match="dominant"):
        apply(gd, tie, "eldritch_annulment", r)
    with pytest.raises(InvalidAction, match="dominant"):
        apply(gd, rare("Life3"), "eldritch_exalted", r)  # no Eldritch implicit at all
    with pytest.raises(InvalidAction, match="Shaper, Elder or conqueror"):
        apply(gd, rare("Life3", influences=frozenset({"shaper"})), "eldritch_currency", r, side="exarch", tier=1)
    assert cost_of(gd, "eldritch_currency", {"side": "eater", "tier": 4}, item) == {"Exceptional Eldritch Ichor": 1}


def test_parser_reads_eldritch_implicits(gd):
    text = ("Item Class: Rings\nRarity: Rare\nDoom Loop\nTest Ring\n--------\nItem Level: 84\n--------\n"
            "7% increased Movement Speed (implicit)\n+20 to maximum Life (implicit)\n--------\n+45 to maximum Life\n")
    p = ItemParser(gd).parse(text)
    assert (p.exarch, p.eater) == ("ExarchSpeedEldritchImplicit3", "EaterLifeEldritchImplicit2")
    assert p.to_item_state().exarch == "ExarchSpeedEldritchImplicit3"
