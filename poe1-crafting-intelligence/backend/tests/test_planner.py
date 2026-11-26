import pytest
from fastapi.testclient import TestClient

from poeci.api.app import create_app
from poeci.engine.actions import InvalidAction
from poeci.engine.planner import Want, plan_routes

from .conftest import RING


def test_routes_cost_and_bench_finish(gd):
    wants = [Want("FireResistance", 1), Want("IncreasedLife", 3), Want("ColdResistance", bench=True)]
    routes = {r.name: r for r in plan_routes(gd, RING, 84, wants, budget_s=0.3, max_successes=200)}
    assert {"Chaos spam", "Alteration, Regal, Exalt"} <= set(routes)
    chaos = routes["Chaos spam"]
    assert chaos.successes > 0
    # Wald: one Chaos per try, so expected Chaos = tries / successes; one Alchemy up front.
    assert chaos.expected_units["Chaos Orb"] == pytest.approx(chaos.tries / chaos.successes)
    assert chaos.expected_units["Orb of Alchemy"] == 1
    assert chaos.units_range is not None  # every Chaos try costs the same
    assert routes["Alteration, Regal, Exalt"].units_range is None  # Alteration counts vary per try
    assert all(r.steps[-1].startswith("Bench craft") for r in routes.values())
    # Life essences: Deafening is offered; Whispering is not (item level 84 is above its limit of 35).
    assert "Essence spam: Deafening Essence of Test" in routes
    assert not any("Whispering" in n for n in routes)


def test_fossil_routes_boost_and_never_block(gd):
    # Test data: Scorched Fossil boosts "fire" and blocks "cold".
    fire = [r.name for r in plan_routes(gd, RING, 84, [Want("FireResistance", 2)], budget_s=0.1)]
    assert "Fossil spam: Scorched Fossil (experimental)" in fire
    cold = [r.name for r in plan_routes(gd, RING, 84, [Want("ColdResistance")], budget_s=0.1)]
    assert not any(n.startswith("Fossil") for n in cold)


def test_impossible_target_reports_a_minimum(gd):
    # ShaperCrit needs Shaper influence: on a plain ring it can never roll.
    routes = plan_routes(gd, RING, 84, [Want("CritShaper")], budget_s=0.1)
    chaos = next(r for r in routes if r.name == "Chaos spam")
    assert chaos.successes == 0 and not chaos.expected_units
    assert chaos.at_least_units and "minimum" in chaos.notes[-1]


def test_planner_refuses_bad_input(gd):
    with pytest.raises(InvalidAction):
        plan_routes(gd, RING, 84, [])
    with pytest.raises(InvalidAction):
        plan_routes(gd, RING, 84, [Want("Strength", bench=True)])  # no bench option for Strength


def test_plan_api(gd, conn):
    c = TestClient(create_app(gd, conn))
    r = c.post("/api/plan", json={"base": "Test Ring", "item_level": 84, "wants": [{"mod_type": "FireResistance", "max_tier": 2}]})
    assert r.status_code == 200
    body = r.json()
    assert body["routes"] and body["routes"][0]["successes"] > 0
    assert c.post("/api/plan", json={"base": "Nope", "wants": [{"mod_type": "X"}]}).status_code == 404


def test_ideas_flag_problems_and_plan_budget_is_bounded(gd, conn):
    c = TestClient(create_app(gd, conn))
    ideas = c.get("/api/ideas").json()
    assert ideas and all(i["problem"] for i in ideas)  # the mini test data has none of these bases
    body = {"base": "Test Ring", "item_level": 84, "wants": [{"mod_type": "FireResistance"}]}
    assert c.post("/api/plan", json={**body, "budget_s": 60}).status_code == 422
    assert c.post("/api/plan", json={**body, "budget_s": 0.2}).status_code == 200
