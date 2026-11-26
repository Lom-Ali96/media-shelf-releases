
import httpx
import pytest
from fastapi.testclient import TestClient

from poeci.api.app import create_app
from poeci.market import poeninja
from poeci.parsing.clipboard import ItemParser
from poeci.updates import versions

BASIC = """Item Class: Rings
Rarity: Rare
Doom Loop
Test Ring
--------
Item Level: 84
--------
+110 to maximum Life
+44% to Fire Resistance
+18% to Cold Resistance (crafted)
--------
Shaper Item
"""

ADVANCED = """Item Class: Rings
Rarity: Rare
Doom Loop
Test Ring
--------
Item Level: 84
--------
{ Prefix Modifier "Virile" (Tier: 1) — Life }
+110(100-114) to maximum Life
{ Suffix Modifier "of the Magma" (Tier: 1) — Elemental, Fire, Resistance }
+44(42-45)% to Fire Resistance
"""


def test_parse_basic(gd):
    item = ItemParser(gd).parse(BASIC)
    assert item.base_id == "Metadata/Items/Rings/Ring1" and item.item_level == 84 and item.influences == ["shaper"]
    assert [m.mod_id for m in item.mods] == ["Life3", "Fire2", "CraftedCold"]
    assert item.mods[2].crafted
    state = item.to_item_state()
    assert state is not None and state.influences == frozenset({"shaper"})


def test_parse_advanced(gd):
    item = ItemParser(gd).parse(ADVANCED)
    assert item.advanced_format
    assert [(m.mod_id, m.values) for m in item.mods] == [("Life3", [110.0]), ("Fire2", [44.0])]


def test_parse_magic_name_and_out_of_range_value(gd):
    text = "Item Class: Rings\nRarity: Magic\nVirile Test Ring\n--------\nItem Level: 80\n--------\n+500 to maximum Life\n"
    item = ItemParser(gd).parse(text)
    assert item.base_name == "Test Ring"
    assert item.mods[0].status == "unmatched"  # 500 is outside every tier: never guessed
    assert item.to_item_state() is None


def test_parse_garbage_does_not_crash(gd):
    item = ItemParser(gd).parse("hello world")
    assert item.warnings


def test_poeninja_parsing_and_cache(conn):
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        # Shapes as served live by poe.ninja on 2026-11-26.
        if "/exchange/" in str(request.url):
            return httpx.Response(200, json={
                "core": {"primary": "chaos", "rates": {"divine": 0.005}},
                "lines": [{"id": "divine", "primaryValue": 180.5}, {"id": "no-name", "primaryValue": 1}],
                "items": [{"id": "divine", "name": "Divine Orb"}]})
        return httpx.Response(200, json={"lines": [{"name": "Goliath Talisman", "chaosValue": 3.2, "divineValue": 0.02, "listingCount": 40, "variant": "Shaper"}]})

    client = poeninja.PoeNinja(conn, httpx.Client(transport=httpx.MockTransport(handler)))
    s1 = client.fetch("Covens of Umbra", "Currency")
    s2 = client.fetch("Covens of Umbra", "Currency")  # cached: no second request
    assert s1 == s2 and len(calls) == 1
    client.fetch("Covens of Umbra", "BaseType")
    assert "/stash/current/item/" in calls[-1]
    assert poeninja.price_of(conn, "Covens of Umbra", "Divine Orb")["chaos_value"] == 180.5
    assert poeninja.price_of(conn, "Covens of Umbra", "Goliath Talisman")["is_listing_price"] is True
    with pytest.raises(poeninja.MarketError):
        poeninja.parse_overview("Essence", {"lines": [], "core": {"primary": "divine"}})
    empty = poeninja.PoeNinja(conn, httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"core": {"primary": "chaos"}, "lines": [], "items": []}))))
    with pytest.raises(poeninja.MarketError, match="league name"):
        empty.fetch("Wrong League", "Fossil")
    poeninja.set_override(conn, "Covens of Umbra", "Divine Orb", 200, "my trade")
    assert poeninja.price_of(conn, "Covens of Umbra", "Divine Orb")["source"] == "manual override"
    with pytest.raises(poeninja.MarketError):
        poeninja.parse_overview("Currency", {"unexpected": True})


def test_version_status_flags_patch_mismatch(conn):
    ok = versions.status(conn, "3.30.0.4.3")
    assert ok["rules_verified_for_current_data"] is True
    bad = versions.status(conn, "3.31.0.1")
    assert bad["rules_verified_for_current_data"] is False
    assert any("3.31" in w for w in bad["warnings"])
    versions.record_check(conn, "remote_game_data", "3.30.1.0", "test")
    assert any("Newer game data" in w for w in versions.status(conn, "3.30.0.4.3")["warnings"])


def test_api_smoke(gd, conn):
    c = TestClient(create_app(gd, conn))
    assert c.get("/").status_code == 200
    s = c.get("/api/status").json()
    assert s["imported_game_data"] == "3.30.0.1"
    pool = c.get("/api/modpool", params={"base": "Test Ring", "ilvl": 84}).json()
    assert abs(sum(m["probability"] for m in pool["mods"]) - 1) < 1e-9
    parsed = c.post("/api/items/parse", json={"text": BASIC}).json()
    assert parsed["item_state_complete"] and parsed["open_prefixes"] == 2
    sim = c.post("/api/simulate", json={"base": "Test Ring", "rarity": "rare", "action": "chaos",
                                         "target": [{"mod_type": "IncreasedLife", "max_tier": 1}], "runs": 50}).json()
    assert 0 < sim["per_attempt_probability"] < 1
    bad = c.post("/api/simulate", json={"base": "Test Ring", "rarity": "normal", "action": "chaos",
                                         "target": [{"mod_type": "IncreasedLife"}], "runs": 5})
    assert bad.status_code == 422
    cov = c.get("/api/coverage").json()
    assert cov["mechanics_total"] > 30 and "honesty_note" in cov
    c.post("/api/settings", json={"league": "Covens of Umbra"})
    assert c.post("/api/market/override", json={"name": "Chaos Orb", "chaos_value": 1}).status_code == 200
