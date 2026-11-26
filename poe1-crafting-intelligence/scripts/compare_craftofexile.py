"""Compare our mod pools with Craft of Exile's data, tier by tier.

Both read their weights from the game's mods.dat, so this does not test the raw
numbers; it tests how this app *applies* them: which mods may roll on a base
(matched by affix, mod group and required item level), item-level gates,
generation multipliers, exclusions (Royale, essence-only...).

Usage (downloads poec_data.json, ~9 MB, once into data/):
    .venv\\Scripts\\python scripts\\compare_craftofexile.py [item_level]
Exit code 1 if any difference is found.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx  # noqa: E402

from poeci import config  # noqa: E402
from poeci.engine.item import ItemState  # noqa: E402
from poeci.engine.modpool import eligible_pool  # noqa: E402
from poeci.knowledge import importer  # noqa: E402
from poeci.knowledge.gamedata import GameData  # noqa: E402

COE_URL = "https://www.craftofexile.com/json/data/main/poec_data.json"
CACHE = config.DATA_DIR / "craftofexile_poec_data.json"
BASES = ["Two-Stone Ring", "Onyx Amulet", "Stygian Vise", "Two-Toned Boots", "Spiked Gloves", "Hubris Circlet",
         "Vaal Regalia", "Spine Bow", "Imbued Wand", "Cobalt Jewel"]


def load_coe() -> dict:
    if not CACHE.exists():
        r = httpx.get(COE_URL, headers={"User-Agent": config.USER_AGENT}, timeout=120)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    raw = CACHE.read_text(encoding="utf-8")
    return json.loads(raw[raw.index("{"):])


def coe_tiers(d: dict, base_name: str, ilvl: int) -> tuple[dict, dict]:
    """(affix, mod group, required level) -> weight, plus a readable name per key."""
    bid = next(b for b in d["bitems"]["seq"] if b["name_bitem"] == base_name)["id_base"]
    mods = {m["id_modifier"]: m for m in d["modifiers"]["seq"]}
    out, names = defaultdict(float), {}
    for mid in d["basemods"].get(bid, []):
        m = mods[mid]
        if m["affix"] not in ("prefix", "suffix") or m["id_mgroup"] != "1":  # 1 = normal pool (no influence etc.)
            continue
        group = (json.loads(m["modgroups"]) if m["modgroups"] else [m["modgroup"]])[0]
        for t in d["tiers"][mid].get(bid, []):
            if int(t["ilvl"]) <= ilvl and int(t["weighting"]) > 0:
                key = (m["affix"], group, int(t["ilvl"]))
                out[key] += int(t["weighting"])
                names[key] = m["name_modifier"]
    return out, names


def our_tiers(gd: GameData, base_name: str, ilvl: int) -> tuple[dict, dict]:
    b = gd.bases_by_name[base_name]
    out, names = defaultdict(float), {}
    for e in eligible_pool(gd, ItemState(b.id, ilvl, "rare")):
        key = (e.mod.generation_type, e.mod.groups[0], e.mod.required_level)
        out[key] += e.weight
        names[key] = f"{e.mod.id}: {e.mod.text}".replace("\n", " / ")
    return out, names


def main() -> int:
    ilvl = int(sys.argv[1]) if len(sys.argv) > 1 else 86
    gd = GameData.from_dir(importer.latest_snapshot())
    d = load_coe()
    problems = 0
    for base in BASES:
        coe, coe_names = coe_tiers(d, base, ilvl)
        ours, our_names = our_tiers(gd, base, ilvl)
        only_coe = sorted(set(coe) - set(ours))
        only_ours = sorted(set(ours) - set(coe))
        diff = sorted(k for k in set(coe) & set(ours) if abs(coe[k] - ours[k]) > 0.5)
        tot = {a: (sum(v for k, v in coe.items() if k[0] == a), sum(v for k, v in ours.items() if k[0] == a))
               for a in ("prefix", "suffix")}
        ok = not (only_coe or only_ours or diff)
        problems += not ok
        print(f"{'OK  ' if ok else 'DIFF'} {base:16} tiers CoE {len(coe):3} / ours {len(ours):3}   "
              f"total weight prefix {tot['prefix'][0]:.0f}/{tot['prefix'][1]:.0f}  suffix {tot['suffix'][0]:.0f}/{tot['suffix'][1]:.0f}")
        for k in only_coe[:8]:
            print(f"     only in Craft of Exile: {k} w={coe[k]:.0f}  {coe_names[k]}")
        for k in only_ours[:8]:
            print(f"     only in ours:           {k} w={ours[k]:.0f}  {our_names[k]}")
        for k in diff[:8]:
            print(f"     weight differs:         {k} CoE {coe[k]:.0f} vs ours {ours[k]:.0f}  {our_names[k]}")
    print(f"\n{problems} of {len(BASES)} bases differ (item level {ilvl}).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
