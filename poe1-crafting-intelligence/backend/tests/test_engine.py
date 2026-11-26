import random

import pytest

from poeci.engine.actions import InvalidAction, apply
from poeci.engine.item import ItemState, ItemView, ModInstance, UnsupportedMechanic, tier_index
from poeci.engine.modpool import eligible_pool

from .conftest import RING


def ids(pool):
    return {e.mod.id for e in pool}


def test_pool_probabilities_are_exact_normalised_weights(gd):
    pool = eligible_pool(gd, ItemState(RING, 84, "rare"))
    assert abs(sum(e.probability for e in pool) - 1) < 1e-12
    # weights: Life1-3 3000, Phys 500, Spell 500, Fire1-2 2000, Cold 1000, Str 1000 = 8000
    by = {e.mod.id: e.probability for e in pool}
    assert by["Life3"] == pytest.approx(1000 / 8000)
    assert by["Phys1"] == pytest.approx(500 / 8000)


def test_item_level_gates_mods(gd):
    low = ids(eligible_pool(gd, ItemState(RING, 40, "rare")))
    assert "Life2" in low and "Life3" not in low and "Fire2" not in low


def test_zero_weight_and_essence_only_never_roll(gd):
    p = ids(eligible_pool(gd, ItemState(RING, 100, "rare")))
    assert "WeaponOnly" not in p and "EssLife" not in p and "ShaperCrit" not in p


def test_influence_adds_its_mods(gd):
    p = ids(eligible_pool(gd, ItemState(RING, 84, "rare", influences=frozenset({"shaper"}))))
    assert "ShaperCrit" in p


def test_group_exclusion_and_affix_caps(gd):
    item = ItemState(RING, 84, "rare", (ModInstance("Life1"),))
    p = ids(eligible_pool(gd, item))
    assert not {"Life1", "Life2", "Life3"} & p
    full_prefix = ItemState(RING, 84, "rare", (ModInstance("Life1"), ModInstance("Phys1"), ModInstance("Spell1")))
    assert all(e.mod.generation_type == "suffix" for e in eligible_pool(gd, full_prefix))
    magic = ItemState(RING, 84, "magic", (ModInstance("Life1"),))
    assert all(e.mod.generation_type == "suffix" for e in eligible_pool(gd, magic))


def test_cannot_roll_attack_metamod(gd):
    item = ItemState(RING, 84, "rare", (ModInstance("XItemGenerationCannotRollAttackAffixes", crafted=True),))
    assert "Phys1" not in ids(eligible_pool(gd, item))
    assert "Spell1" in ids(eligible_pool(gd, item))


def test_tiers(gd):
    base = gd.bases[RING]
    assert tier_index(gd, base, gd.mods["Life3"]) == (1, 3)
    assert tier_index(gd, base, gd.mods["Life1"]) == (3, 3)


def test_actions_validate(gd):
    rng = random.Random(0)
    with pytest.raises(InvalidAction):
        apply(gd, ItemState(RING, 84, "normal"), "chaos", rng)
    with pytest.raises(InvalidAction):
        apply(gd, ItemState(RING, 84, "rare", corrupted=True), "chaos", rng)
    with pytest.raises(InvalidAction):
        apply(gd, ItemState("Metadata/Items/Rings/Old", 84, "normal"), "alchemy", rng)


def test_alchemy_and_chaos_respect_caps(gd):
    rng = random.Random(1)
    for _ in range(300):
        it = apply(gd, ItemState(RING, 84, "normal"), "alchemy", rng)
        v = ItemView(gd, it)
        assert it.rarity == "rare" and 1 <= len(it.explicits) <= 6
        assert v.count("prefix") <= 3 and v.count("suffix") <= 3
        assert len(v.groups()) == len(it.explicits)  # no duplicate groups


def test_annulment_never_removes_fractured(gd):
    rng = random.Random(2)
    item = ItemState(RING, 84, "rare", (ModInstance("Life3", fractured=True), ModInstance("Fire1")))
    for _ in range(50):
        out = apply(gd, item, "annulment", rng)
        assert out.explicits == (ModInstance("Life3", fractured=True),)


def test_prefix_lock_keeps_prefixes_through_chaos_and_scour(gd):
    rng = random.Random(3)
    item = ItemState(RING, 84, "rare", (ModInstance("Life3"), ModInstance("XMasterItemGenerationCannotChangePrefixes", crafted=True)))
    for _ in range(50):
        out = apply(gd, item, "chaos", rng)
        assert ModInstance("Life3") in out.explicits
    out = apply(gd, item, "scouring", rng)
    assert out.explicits == (ModInstance("Life3"),) and out.rarity == "rare"


def test_essences_and_fossils_ignore_locks_but_keep_fractured(gd):
    rng = random.Random(4)
    locked = ItemState(RING, 84, "rare", (ModInstance("Phys1"), ModInstance("XMasterItemGenerationCannotChangePrefixes", crafted=True)))
    kept_by_essence = sum(ModInstance("Phys1") in apply(gd, locked, "essence", rng, essence_name="Deafening Essence of Test").explicits
                          for _ in range(100))
    kept_by_fossil = sum(ModInstance("Phys1") in apply(gd, locked, "fossil", rng, fossil_names=["Scorched Fossil"]).explicits
                         for _ in range(100))
    assert kept_by_essence < 100 and kept_by_fossil < 100  # the lock does not protect the prefix
    fractured = ItemState(RING, 84, "rare", (ModInstance("Phys1", fractured=True),))
    assert all(ModInstance("Phys1", fractured=True) in apply(gd, fractured, "fossil", rng, fossil_names=["Scorched Fossil"]).explicits
               for _ in range(30))


def test_partial_lock_is_refused_not_guessed(gd):
    item = ItemState(RING, 84, "rare", (ModInstance("XMasterItemGenerationCannotChangeOnePrefixes", crafted=True),))
    with pytest.raises(UnsupportedMechanic):
        eligible_pool(gd, item)


def test_bench_craft_limits(gd):
    rng = random.Random(4)
    item = ItemState(RING, 84, "rare", (ModInstance("Life3"),))
    one = apply(gd, item, "bench_craft", rng, mod_id="CraftedCold")
    with pytest.raises(InvalidAction):  # second crafted mod without multimod
        apply(gd, one, "bench_craft", rng, mod_id="XItemGenerationCannotRollAttackAffixes")
    multi = apply(gd, item, "bench_craft", rng, mod_id="XItemGenerationCanHaveMultipleCraftedMods")
    multi = apply(gd, multi, "bench_craft", rng, mod_id="CraftedCold")
    assert sum(m.crafted for m in multi.explicits) == 2
    with pytest.raises(InvalidAction):  # same group as an existing mod
        apply(gd, ItemState(RING, 84, "rare", (ModInstance("Cold1"),)), "bench_craft", rng, mod_id="CraftedCold")
    assert apply(gd, one, "remove_crafted", rng).explicits == (ModInstance("Life3"),)


def test_essence_forces_mod_and_respects_restrictions(gd):
    rng = random.Random(5)
    out = apply(gd, ItemState(RING, 30, "normal"), "essence", rng, essence_name="Whispering Essence of Test")
    assert out.rarity == "rare" and any(m.mod_id == "Life1" for m in out.explicits)
    with pytest.raises(InvalidAction):  # item level above restriction
        apply(gd, ItemState(RING, 84, "normal"), "essence", rng, essence_name="Whispering Essence of Test")
    with pytest.raises(InvalidAction):  # low essence cannot reforge a rare
        apply(gd, ItemState(RING, 30, "rare"), "essence", rng, essence_name="Whispering Essence of Test")
    out = apply(gd, ItemState(RING, 84, "rare"), "essence", rng, essence_name="Deafening Essence of Test")
    assert any(m.mod_id == "EssLife" for m in out.explicits)


def test_fossil_blocks_and_boosts(gd):
    rng = random.Random(6)
    seen = set()
    for _ in range(200):
        out = apply(gd, ItemState(RING, 84, "normal"), "fossil", rng, fossil_names=["Scorched Fossil"])
        seen |= {m.mod_id for m in out.explicits}
    assert "Cold1" not in seen and ("Fire1" in seen or "Fire2" in seen)


def test_divine_keeps_values_in_range(gd):
    rng = random.Random(7)
    item = ItemState(RING, 84, "rare", (ModInstance("Life3", (100,)),))
    for _ in range(100):
        (mi,) = apply(gd, item, "divine", rng).explicits
        assert 100 <= mi.values[0] <= 114
