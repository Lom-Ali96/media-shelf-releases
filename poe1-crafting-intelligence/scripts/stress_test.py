"""Stress test: a throwaway app instance (temp DB, port 8799), fuzzed inputs, every
craftable base, one plan per item class, and concurrent requests. Your real database
is not touched. Any HTTP 500 or exception is a bug; 4xx with a clear message is the
expected answer to bad input. Takes about 5 minutes. Run from the project folder:

    .venv\\Scripts\\python scripts\\stress_test.py
"""
import concurrent.futures as cf
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx  # noqa: E402
import uvicorn  # noqa: E402

from poeci.api.app import create_app  # noqa: E402
from poeci.knowledge import importer  # noqa: E402
from poeci.knowledge.gamedata import GameData  # noqa: E402
from poeci.storage import db  # noqa: E402

gd = GameData.from_dir(importer.latest_snapshot())
conn = db.connect(Path(tempfile.mkdtemp()) / "stress.sqlite3")
server = uvicorn.Server(uvicorn.Config(create_app(gd, conn), port=8799, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)
C = httpx.Client(base_url="http://127.0.0.1:8799", timeout=120)
bugs = []


def call(method, path, **kw):
    try:
        r = C.request(method, path, **kw)
    except Exception as e:  # noqa: BLE001
        bugs.append((path, kw.get("json", kw.get("params")), f"EXC {e!r}"))
        return None
    if r.status_code >= 500:
        bugs.append((path, str(kw.get("json", kw.get("params")))[:200], f"{r.status_code} {r.text[:300]}"))
    return r


C.post("/api/settings", json={"league": "Covens"})
weird = ["", " ", "\x00", "ä" * 5000, "Rarity: Rare\n" * 3000, "Item Level: 99999999999999999999", "Item Level: -5",
         "Rarity: Rare\nX\nSpine Bow\n--------\nItem Level: 85\n--------\n" + "Adds 1 to 2 Fire Damage\n" * 400,
         "{ Prefix Modifier \"\" (Tier: 999) }", "Rarity: Unique\nFoo\nSpine Bow\n--------\nItem Level: 1", "<script>alert(1)</script>"]
for t in weird:
    call("POST", "/api/items/parse", json={"text": t})
    call("POST", "/api/items/trade_link", json={"text": t})
    call("POST", "/api/pob", json={"code": t})
for body in [{"base": "Spine Bow", "item_level": 0, "wants": [{"mod_type": "X"}]},
             {"base": "Spine Bow", "item_level": 85, "wants": []},
             {"base": "Spine Bow", "item_level": 85, "wants": [{"mod_type": "LocalLightningDamageTwoHand", "max_tier": -3}]},
             {"base": "Spine Bow", "item_level": 85, "wants": [{"mod_type": "Nope"}]},
             {"base": "Spine Bow", "item_level": 85, "wants": [{"mod_type": "CriticalStrikeMultiplier"}] * 12},
             {"base": "Spine Bow", "item_level": 85, "wants": [{"mod_type": "CriticalStrikeMultiplier", "bench": True},
                                                              {"mod_type": "LocalLightningDamageTwoHand", "bench": True}]},
             {"base": "Spine Bow", "item_level": 85, "influences": ["shaper", "nonsense"], "wants": [{"mod_type": "CriticalStrikeMultiplier"}]},
             {"base": "Chaos Orb", "item_level": 85, "wants": [{"mod_type": "IncreasedLife"}]},
             {"base": "", "wants": [{"mod_type": "IncreasedLife"}]}]:
    call("POST", "/api/plan", json=body)
call("POST", "/api/plans", json={"base": "Spine Bow", "wants": [], "sale_chaos": 1e308, "best_cost_chaos": 1e308})
call("POST", "/api/market/override", json={"name": "Chaos Orb", "chaos_value": -1})
call("DELETE", "/api/plans/does-not-exist")
for params in [{"base": "Spine Bow", "ilvl": -1}, {"base": "Spine Bow", "ilvl": 10**9}, {"base": "x"}, {"base": "Spine Bow", "influences": ",,,"}]:
    call("GET", "/api/modpool", params=params)
call("POST", "/api/simulate", json={"base": "Spine Bow", "action": "nope", "target": []})
call("POST", "/api/simulate", json={"base": "Spine Bow", "action": "essence", "params": {"essence_name": "x"}, "target": []})
call("POST", "/api/simulate", json={"base": "Spine Bow", "action": "chaos", "rarity": "unique", "target": []})
print("fuzz done, bugs so far:", len(bugs))

t0 = time.time()
classes = {}
for b in gd.craftable_bases:
    r = call("GET", "/api/modpool", params={"base": b.name, "ilvl": 86})
    if r is not None and r.status_code == 200 and r.json()["mods"]:
        classes.setdefault(b.item_class, (b.name, r.json()["mods"][0]["type"]))
print(f"modpool for {len(gd.craftable_bases)} bases in {time.time() - t0:.1f}s")
t0 = time.time()
for cls, (base, mtype) in classes.items():
    call("POST", "/api/plan", json={"base": base, "item_level": 86, "wants": [{"mod_type": mtype, "max_tier": 99}]})
print(f"plans for {len(classes)} item classes in {time.time() - t0:.1f}s")

t0 = time.time()
plan = {"base": "Sapphire Ring", "item_level": 84, "wants": [{"mod_type": "IncreasedLife", "max_tier": 3}]}
with cf.ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(call, "POST", "/api/plan", json=plan) for _ in range(6)]
    futs += [ex.submit(call, "POST", "/api/plans", json={**plan, "item_level": 70 + i, "sale_chaos": 10 + i}) for i in range(30)]
    futs += [ex.submit(call, "GET", "/api/plans") for _ in range(30)]
    futs += [ex.submit(call, "POST", "/api/items/parse", json={"text": weird[7]}) for _ in range(20)]
    codes = [f.result().status_code if f.result() is not None else None for f in futs]
print(f"concurrency: {len(codes)} requests in {time.time() - t0:.1f}s, status codes {sorted(set(codes), key=str)}")

print(f"\nBUGS: {len(bugs)}")
for b in bugs[:40]:
    print(" ", b)
server.should_exit = True
sys.exit(1 if bugs else 0)
