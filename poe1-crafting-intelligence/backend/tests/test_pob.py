import base64
import zlib

import pytest
from fastapi.testclient import TestClient

from poeci.api.app import create_app
from poeci.parsing import pob

RING_ITEM = """Rarity: RARE
Doom Loop
Test Ring
Unique ID: abc
Item Level: 84
LevelReq: 60
Implicits: 1
{tags:life}+5 to maximum Life
{range:1}+(40-49) to maximum Life
+43% to Fire Resistance
{crafted}{range:0.5}+(16-20)% to Cold Resistance"""

PB_ITEM = """Rarity: MAGIC
Test Ring of the Brute
Implicits: 0
+10 to Strength"""

XML = f"""<PathOfBuilding><Items activeItemSet="2">
<Item id="1">{RING_ITEM}</Item><Item id="2">{PB_ITEM}</Item><Item id="3">Rarity: RARE
Unused
Test Ring
Implicits: 0</Item>
<ItemSet id="1"><Slot name="Ring 1" itemId="3"/></ItemSet>
<ItemSet id="2"><Slot name="Ring 1" itemId="1"/><Slot name="Ring 2" itemId="2"/><Slot name="Amulet" itemId="0"/></ItemSet>
</Items></PathOfBuilding>"""


def code(xml: str) -> str:
    return base64.urlsafe_b64encode(zlib.compress(xml.encode())).decode()


def test_to_clipboard_resolves_ranges_tags_and_implicits():
    text = pob.to_clipboard(RING_ITEM)
    assert text.splitlines()[:3] == ["Rarity: Rare", "Doom Loop", "Test Ring"]
    assert "Item Level: 84" in text
    assert "+5 to maximum Life (implicit)" in text
    assert "+49 to maximum Life\n" in text  # {range:1} -> top of 40-49
    assert "+18% to Cold Resistance (crafted)" in text  # {range:0.5} of 16-20
    assert "Unique ID" not in text


def test_items_uses_active_set_and_flags_assumed_item_level():
    items = pob.items(code(XML))
    assert [e["slot"] for e in items] == ["Ring 1", "Ring 2"]  # set 2 only, empty slot skipped
    assert items[0]["item_level_assumed"] is False
    assert items[1]["item_level_assumed"] is True
    assert f"Item Level: {pob.ASSUMED_ITEM_LEVEL}" in items[1]["text"]


@pytest.mark.parametrize("bad, msg", [
    ("https://pobb.in/abc", "link"),
    ("not a code!!", "not a Path of Building code"),
    (code("<PathOfBuilding><Items>"), "broken"),
    (code("<PathOfBuilding/>"), "no items"),
])
def test_bad_codes_are_refused(bad, msg):
    with pytest.raises(pob.PobError, match=msg):
        pob.items(bad)


def test_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(pob, "MAX_XML_BYTES", 1000)
    with pytest.raises(pob.PobError, match="too large"):
        pob.decode(code("<a>" + "x" * 5000 + "</a>"))


def test_pob_api(gd, conn):
    c = TestClient(create_app(gd, conn))
    r = c.post("/api/pob", json={"code": code(XML)}).json()
    ring = r["items"][0]
    assert ring["base"] == "Test Ring" and ring["mods"] == 3 and ring["matched"] == 3
    assert c.post("/api/pob", json={"code": "garbage"}).status_code == 422
