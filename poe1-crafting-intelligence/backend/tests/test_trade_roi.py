import json
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from poeci.api.app import create_app
from poeci.engine.item import ItemState
from poeci.engine.planner import Want
from poeci.market import trade

from .conftest import RING

EXPLICIT = {"+# to maximum Life": "explicit.life", "+#% to Fire Resistance": "explicit.fire",
            "#% increased Attribute Requirements": "explicit.attr"}


def test_pattern_and_reduced():
    assert trade._pattern("Adds 2 to (10-11) Lightning Damage") == "Adds # to # Lightning Damage"
    assert trade._pattern("+(2-2.4)% of Life") == "+#% of Life"
    assert trade._first_number("+(30-34)% to Global Critical Strike Multiplier") == 30


def test_stat_filters_use_worst_accepted_tier(gd):
    item = ItemState(RING, 84)
    wants = [Want("IncreasedLife", 2), Want("FireResistance", 1), Want("ColdResistance", bench=True), Want("CritShaper")]
    filters, notes = trade.stat_filters(gd, item, wants, EXPLICIT)
    # Life T2 on an ilvl 84 ring is "Robust" +(40-49): minimum 40. Fire T1 is +(42-45)%.
    assert {"id": "explicit.life", "value": {"min": 40.0}} in filters
    assert {"id": "explicit.fire", "value": {"min": 42.0}} in filters
    assert any("bench" in n for n in notes) and any("CritShaper" in n for n in notes)


def test_search_url_round_trip():
    url = trade.search_url("Covens", "Spine Bow", [{"id": "explicit.x", "value": {"min": 5}}])
    assert url.startswith("https://www.pathofexile.com/trade/search/Covens?q=")
    q = json.loads(unquote(url.split("?q=", 1)[1]))
    assert q["query"]["type"] == "Spine Bow" and q["query"]["stats"][0]["filters"][0]["id"] == "explicit.x"


def test_load_stats_caches_per_game_version(tmp_path, monkeypatch):
    monkeypatch.setattr(trade, "CACHE", tmp_path / "trade_stats.json")
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"result": [{"id": "explicit", "entries": [{"id": "explicit.life", "text": "+# to maximum Life"}]}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert trade.load_stats("3.30.0", client) == {"+# to maximum Life": "explicit.life"}
    trade.load_stats("3.30.0", client)
    assert len(calls) == 1  # cached
    trade.load_stats("3.31.0", client)
    assert len(calls) == 2  # new game data -> refreshed
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": []})))
    with pytest.raises(trade.TradeError):
        trade.load_stats("3.32.0", bad)


def test_roi_board(gd, conn):
    c = TestClient(create_app(gd, conn))
    plan = {"base": "Test Ring", "item_level": 84, "wants": [{"mod_type": "FireResistance", "max_tier": 2}]}
    assert c.post("/api/plans", json={**plan, "sale_chaos": 50}).status_code == 422  # no league yet
    c.post("/api/settings", json={"league": "Covens"})
    assert c.post("/api/plans", json={**plan, "sale_chaos": 0}).status_code == 422  # must be > 0
    c.post("/api/plans", json={**plan, "sale_chaos": 50, "best_route": "Chaos spam", "best_cost_chaos": 20})
    c.post("/api/plans", json={**plan, "sale_chaos": 60, "best_route": "Chaos spam", "best_cost_chaos": 20})  # update, not duplicate
    c.post("/api/market/override", json={"name": "Test Ring", "chaos_value": 10})
    rows = c.get("/api/plans").json()
    assert len(rows) == 1
    assert rows[0]["profit_chaos"] == pytest.approx(30) and rows[0]["roi"] == pytest.approx(1.0)  # 60 - 20 - 10
    c.delete(f"/api/plans/{rows[0]['key']}")
    assert c.get("/api/plans").json() == []
