"""Suggest crafting steps from free text (a Reddit post, a guide, your notes).

Free text is not reliable enough to trust blindly: this only *suggests* steps
in the order the methods are first mentioned. The user checks and edits them
in the Recipes tab before simulating. Nothing is guessed that the text does
not name: e.g. a bench craft without a recognisable mod is left for the user.
"""
from __future__ import annotations

import re

from ..engine.recipe import HARVEST
from ..knowledge.gamedata import GameData

# (pattern, action, params) checked case-insensitively; first match position orders the steps.
KEYWORDS: list[tuple[str, str, dict]] = [
    (r"\btransmut\w*|\btransmute\b", "transmutation", {}),
    (r"\balteration\b|\balt(s|ed|ing)?\b(?! ?\+ ?f4)", "alteration", {}),
    (r"\baug(ment)?\w*\b", "augmentation", {}),
    (r"\bregal\w*", "regal", {}),
    (r"\balch(emy|ed|ing)?\b", "alchemy", {}),
    (r"\bchaos( orbs?)?( ?spam\w*| ?roll\w*)?\b(?! res)", "chaos", {}),
    (r"\bexalt\w*", "exalted", {}),
    (r"\bannul\w*", "annulment", {}),
    (r"\bscour\w*", "scouring", {}),
    (r"\bdivine orb\b|\bdivin(e|ing) (it|the item)\b", "divine", {}),
    (r"\bfractur(e|ed|ing)( orb)?\b(?! fossil)", "fracturing", {}),
    (r"\b(remove|removing) (the )?crafted\b", "remove_crafted", {}),
    (r"\blynx\b", "beast_suffix_for_prefix", {}),
    (r"\bwolf\b", "beast_prefix_for_suffix", {}),
    (r"\bbench ?craft\w*|\bcraft(ed)? (on|at) the bench\b", "bench_craft", {}),
]
REPEATING = {"chaos", "alteration", "essence", "fossil", "harvest_reforge", "harvest_reforge_same"}
NEEDS_RARE = {"chaos", "exalted", "harvest_reforge", "harvest_reforge_same", "fracturing", "harvest_add_remove",
              "beast_suffix_for_prefix", "beast_prefix_for_suffix"}


def _lock_mod(gd: GameData, item_class: str | None, side: str) -> str | None:
    want = "ItemGenerationCannotChangePrefixes" if side == "prefix" else "ItemGenerationCannotChangeSuffixes"
    for o in gd.bench_options:
        mid = (o.get("actions") or {}).get("add_explicit_mod")
        if mid in gd.mods and gd.mods[mid].type == want and (item_class is None or item_class in o.get("item_classes", [])):
            return mid
    return None


def suggest(gd: GameData, text: str, base_name: str | None = None) -> dict:
    low = text.lower()
    if base_name is None:  # the longest base name mentioned in the text
        names = sorted((n for n in gd.bases_by_name if n and gd.bases_by_name[n].craftable and n.lower() in low), key=len)
        base_name = names[-1] if names else None
    item_class = gd.bases_by_name[base_name].item_class if base_name in gd.bases_by_name else None
    found: list[tuple[int, str, dict, str]] = []  # (position, action, params, matched text)

    for pattern, action, params in KEYWORDS:
        # bench crafts are often mentioned more than once (a lock, then a finishing craft)
        for m in (re.finditer(pattern, low) if action == "bench_craft" else filter(None, [re.search(pattern, low)])):
            found.append((m.start(), action, params, m.group(0)))
    # Essences: full name, or "essence of X" -> the strongest tier of that essence.
    by_suffix: dict[str, tuple[int, str]] = {}
    for name, (_, ess) in gd.essences_by_name.items():
        if " of " in name:
            suffix = name.split(" of ", 1)[1].lower()
            if ess.get("level", 0) > by_suffix.get(suffix, (-1, ""))[0]:
                by_suffix[suffix] = (ess.get("level", 0), name)
    for name in gd.essences_by_name:
        if (i := low.find(name.lower())) >= 0:
            found.append((i, "essence", {"essence_name": name}, name))
    for suffix, (_, name) in by_suffix.items():
        if (m := re.search(rf"essences? of {re.escape(suffix)}\b", low)) and not any(f[1] == "essence" for f in found):
            found.append((m.start(), "essence", {"essence_name": name}, m.group(0)))
    # Fossils: every fossil named goes into one resonator step.
    # a fossil counts only when its name is followed by "fossil(s)" within a few words ("Metallic + Prismatic fossils")
    fossils = sorted((m.start(), n) for n in gd.fossils_by_name if n
                     for m in [re.search(rf"\b{re.escape(n.lower().split()[0])}\b(\W+\w+){{0,3}}?\W+fossils?\b", low)] if m)
    if fossils:
        found.append((fossils[0][0], "fossil", {"fossil_names": [n for _, n in fossils][:4]}, ", ".join(n for _, n in fossils)))
    # Harvest: "harvest/reforge ... <tag>" within a few words.
    for tag in HARVEST["reforge"]:
        if (m := re.search(rf"(harvest|reforge)\W+(\w+\W+){{0,4}}{tag}\b|\b{tag}\W+(reforge|harvest)", low)):
            found.append((m.start(), "harvest_reforge", {"tag": tag}, m.group(0)))
    if re.search(r"more likely", low) and "harvest" in low:
        found.append((low.find("more likely"), "harvest_reforge_same", {}, "more likely"))
    # Locks: "prefixes cannot be changed" / "lock prefixes" -> the bench meta-craft.
    for side in ("prefix", "suffix"):
        if (m := re.search(rf"{side}es (can ?not|can't) be changed|lock(ed|ing)? (the )?{side}es", low)):
            mid = _lock_mod(gd, item_class, side)
            if mid:
                found.append((m.start(), "bench_craft", {"mod_id": mid}, m.group(0)))

    found.sort(key=lambda f: f[0])
    specific = [pos for pos, a, p, _ in found if a == "bench_craft" and p]
    steps, notes = [], []
    for pos, action, params, matched in found:
        if steps and steps[-1]["action"] == action and steps[-1]["params"] == params:
            continue
        if action == "bench_craft" and not params and any(abs(pos - q) < 60 for q in specific):
            continue  # "bench crafted 'Suffixes cannot be changed'": the specific lock step covers it
        # "exalted until I got ..." -> repeat until the wanted mods appear
        until = re.match(r"[ \t]+(\w+[ \t]+){0,2}?until\b", low[pos + len(matched):])  # same clause only
        steps.append({"action": action, "params": dict(params),
                      "repeat": "until_wanted" if action in REPEATING or until else "once",
                      "mods": [], "matched": matched})
    if steps and steps[0]["action"] in NEEDS_RARE:
        steps.insert(0, {"action": "alchemy", "params": {}, "repeat": "once", "mods": [], "matched": "(added: needs a rare item)"})
        notes.append("Added an Orb of Alchemy first, because the first step needs a rare item.")
    for s in steps:
        if s["action"] == "bench_craft" and not s["params"]:
            notes.append("A bench craft is mentioned but not which one: pick it in the step.")
    if base_name is None:
        notes.append("No base type found in the text: choose it above.")
    return {"base": base_name, "steps": steps, "notes": notes}
