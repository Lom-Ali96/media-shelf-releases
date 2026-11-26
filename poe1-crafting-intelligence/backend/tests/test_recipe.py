import random
from collections import Counter

import pytest

from poeci.engine.actions import InvalidAction, apply
from poeci.engine.item import ItemState, ItemView, ModInstance
from poeci.engine.planner import Want, plan_routes
from poeci.engine.recipe import Condition, Recipe, Step, cost_of, run_once, validate
from poeci.engine.simulate import ModRequirement

from .conftest import RING

FIRE = ModRequirement("FireResistance")


def rare(gd, *mods):
    return ItemState(RING, 84, "rare", tuple(ModInstance(m, (1,)) for m in mods))


def test_harvest_reforge_always_contains_the_tag(gd):
    r = random.Random(1)
    for _ in range(200):
        it = apply(gd, rare(gd, "Life3"), "harvest_reforge", r, tag="fire")
        assert any("fire" in m.implicit_tags for _, m in ItemView(gd, it).mods())
    with pytest.raises(InvalidAction):
        apply(gd, ItemState(RING, 84, "normal"), "harvest_reforge", r, tag="fire")  # needs a rare


def test_harvest_add_remove_and_beast_swaps(gd):
    r = random.Random(2)
    start = rare(gd, "Life3", "Phys1", "Cold1", "Str1")
    it = apply(gd, start, "harvest_add_remove", r, tag="fire")
    assert len(it.explicits) == 4 and any(mi.mod_id.startswith("Fire") for mi in it.explicits)
    lynx = apply(gd, start, "beast_suffix_for_prefix", r)
    v = ItemView(gd, lynx)
    assert v.count("prefix") == 1 and v.count("suffix") == 3
    with pytest.raises(InvalidAction):  # no prefix to remove
        apply(gd, rare(gd, "Cold1"), "beast_suffix_for_prefix", r)


def test_recipe_until_check_goto_and_restart(gd):
    r = random.Random(3)
    start = rare(gd, "Life3")
    # Chaos until fire res appears: always ends in success, cost = number of Chaos used.
    rec = Recipe("chaos", (Step("chaos", until=Condition(all_of=(FIRE,))),), Condition(all_of=(FIRE,)))
    ok, used = run_once(gd, rec, start, r)
    assert ok and set(used) == {"Chaos Orb"}
    # A failing check with restart ends the try at once.
    bad = Recipe("x", (Step("scouring", check=Condition(all_of=(FIRE,))),), Condition())
    assert run_once(gd, bad, start, r) == (False, Counter({"Orb of Scouring": 1}))
    # goto loops back: chaos once, check, retry until met.
    loop = Recipe("y", (Step("chaos", check=Condition(all_of=(FIRE,)), on_fail="goto:0"),), Condition(all_of=(FIRE,)))
    ok, used = run_once(gd, loop, start, r)
    assert ok and used["Chaos Orb"] >= 1
    with pytest.raises(InvalidAction):
        validate(Recipe("z", (Step("chaos", on_fail="goto:7"),), Condition()))


def test_costs(gd):
    it = rare(gd, "Life3")
    assert cost_of(gd, "harvest_reforge", {"tag": "life"}, it) == {"Wild Crystallised Lifeforce": 75}
    assert cost_of(gd, "fossil", {"fossil_names": ["Scorched Fossil"]}, it) == {"Scorched Fossil": 1, "Primitive Chaotic Resonator": 1}
    assert cost_of(gd, "beast_prefix_for_suffix", {}, it) == {"Farric Wolf Alpha": 1}


def test_planner_offers_harvest_and_lock_routes(gd):
    wants = [Want("IncreasedLife", 3), Want("FireResistance", 2)]
    names = [r.name for r in plan_routes(gd, RING, 84, wants, budget_s=0.1)]
    assert "Harvest reforge: fire (experimental)" in names
    assert "Lock prefixes, scour, exalt" in names and "Lock suffixes, scour, exalt" not in names  # no suffix lock in test data


def test_fracture_swap_and_same_type_reforge(gd):
    r = random.Random(4)
    four = rare(gd, "Life3", "Phys1", "Fire2", "Str1")
    fr = apply(gd, four, "fracturing", r)
    assert sum(mi.fractured for mi in fr.explicits) == 1
    with pytest.raises(InvalidAction):
        apply(gd, rare(gd, "Life3", "Fire2"), "fracturing", r)  # needs 4 mods
    sw = apply(gd, four, "harvest_swap", r, kind="resistance", from_element="fire", to_element="cold")
    assert any(mi.mod_id.startswith("Cold") for mi in sw.explicits) and not any(mi.mod_id.startswith("Fire") for mi in sw.explicits)
    assert cost_of(gd, "harvest_swap", {"kind": "damage", "from_element": "fire", "to_element": "cold"}, four) == {
        "Wild Crystallised Lifeforce": 300, "Primal Crystallised Lifeforce": 300, "Crystallised Rancour": 1}
    same = apply(gd, four, "harvest_reforge_same", r)
    assert len(same.explicits) >= 4  # never fewer mods (assumption)


def test_missing_action_parameters_are_refused(gd):
    with pytest.raises(InvalidAction, match="missing kind"):
        apply(gd, rare(gd, "Fire2"), "harvest_swap", random.Random(0))
    with pytest.raises(InvalidAction, match="missing essence_name"):
        apply(gd, ItemState(RING, 84), "essence", random.Random(0))


def test_planner_offers_fracture_route(gd):
    wants = [Want("IncreasedLife", 3), Want("FireResistance", 2)]
    routes = {r.name: r for r in plan_routes(gd, RING, 84, wants, budget_s=0.2)}
    frac = routes["Fracture, then Chaos (experimental)"]
    assert frac.tries > 0 and "Fracturing Orb" in (frac.expected_units or frac.at_least_units)
