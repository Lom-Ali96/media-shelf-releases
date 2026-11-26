import pytest
from fastapi.testclient import TestClient

from poeci.api.app import create_app
from poeci.engine.actions import InvalidAction
from poeci.engine.recipe import recipe_from_json
from poeci.engine.simulate import ModRequirement
from poeci.parsing.recipe_text import suggest

POST = ("Took a Test Ring, ilvl 84. Spammed Deafening Essence of Test until I got fire res, "
        "then bench crafted 'Prefixes cannot be changed', scoured, and exalted until it hit. "
        "Used Scorched fossils on the next one. Annul if bad.")


def test_suggest_orders_steps_and_reads_repeats(gd):
    r = suggest(gd, POST)
    assert r["base"] == "Test Ring"
    steps = [(s["action"], s["repeat"]) for s in r["steps"]]
    assert steps == [("essence", "until_wanted"), ("bench_craft", "once"), ("scouring", "once"),
                     ("exalted", "until_wanted"), ("fossil", "until_wanted"), ("annulment", "once")]
    assert r["steps"][1]["params"] == {"mod_id": "XMasterItemGenerationCannotChangePrefixes"}
    assert r["steps"][4]["params"] == {"fossil_names": ["Scorched Fossil"]}


def test_suggest_adds_alchemy_and_ignores_unknown_text(gd):
    r = suggest(gd, "chaos spam a Test Ring until good")
    assert [s["action"] for s in r["steps"]] == ["alchemy", "chaos"]
    assert suggest(gd, "hello world")["steps"] == []


def test_recipe_from_json_validation():
    wants = [ModRequirement("FireResistance", 2)]
    with pytest.raises(InvalidAction, match="choose mod_id"):
        recipe_from_json("x", [{"action": "bench_craft"}], wants)
    with pytest.raises(InvalidAction, match="wanted mod types"):
        recipe_from_json("x", [{"action": "chaos", "repeat": "until_mods", "mods": ["Nope"]}], wants)


def test_simulate_compare_and_library(gd, conn):
    c = TestClient(create_app(gd, conn))
    body = {"name": "Reddit ring", "base": "Test Ring", "item_level": 84,
            "wants": [{"mod_type": "FireResistance", "max_tier": 2}],
            "steps": [{"action": "alchemy"}, {"action": "chaos", "repeat": "until_wanted"}], "budget_s": 0.2}
    r = c.post("/api/recipes/simulate", json=body).json()
    assert r["recipe"]["successes"] > 0 and r["app_best"] is not None and r["app_routes"] >= 2
    assert r["recipe"]["steps"][1] == "Chaos Orb, repeat until FireResistance"
    assert c.post("/api/recipes/simulate", json={**body, "steps": [{"action": "bench_craft"}]}).status_code == 422
    rid = c.post("/api/recipes", json={**body, "source_url": "https://example.org/post"}).json()["id"]
    assert [d["id"] for d in c.get("/api/recipes", params={"base": "Test Ring"}).json()] == [rid]
    assert c.get("/api/recipes", params={"base": "Other"}).json() == []
    c.delete(f"/api/recipes/{rid}")
    assert c.get("/api/recipes").json() == []
    opts = c.get("/api/bench_options", params={"base": "Test Ring"}).json()
    assert any(o["text"] == "Prefix Modifiers cannot be changed" for o in opts)


def test_collected_ideas_price_groups(gd, conn):
    c = TestClient(create_app(gd, conn))
    item = "Item Class: Rings\nRarity: Rare\nDoom Loop\nTest Ring\n--------\nItem Level: 84\n--------\n+45 to maximum Life\n+43% to Fire Resistance\n"
    assert c.post("/api/ideas/collect", json={"text": item}).status_code == 422  # no league yet
    c.post("/api/settings", json={"league": "Covens"})
    c.post("/api/market/override", json={"name": "Divine Orb", "chaos_value": 100})
    for price in (500, 5000, 50000, None):
        assert c.post("/api/ideas/collect", json={"text": item, "price_chaos": price}).status_code == 200
    r = c.get("/api/ideas/collected").json()
    assert {k: len(v) for k, v in r["groups"].items()} == {"under_10_div": 1, "10_to_100_div": 1, "over_100_div": 1, "no_price": 1}
    idea = r["groups"]["under_10_div"][0]
    assert {w["mod_type"] for w in idea["wants"]} == {"IncreasedLife", "FireResistance"}
    c.post(f"/api/ideas/collected/{idea['id']}/result", json={"best_route": "Chaos spam", "best_cost_chaos": 200})
    again = c.get("/api/ideas/collected").json()["groups"]["under_10_div"][0]
    assert again["profit_chaos"] == 300
    c.delete(f"/api/ideas/collected/{idea['id']}")
    assert c.get("/api/ideas/collected").json()["groups"]["under_10_div"] == []
    assert c.post("/api/ideas/collect", json={"text": "hello"}).status_code == 422
