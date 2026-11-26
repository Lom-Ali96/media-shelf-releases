"""Crafting coverage dashboard data: what is supported, and how well."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .gamedata import GameData

REGISTRY_PATH = Path(__file__).with_name("mechanics_registry.json")
STATUSES = [
    "implemented_verified",
    "implemented_partially_verified",
    "experimental",
    "discovered_not_implemented",
    "unsupported",
    "outdated",
    "removed",
    "unknown",
]


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def coverage_report(gd: GameData | None) -> dict:
    reg = load_registry()
    mechs = reg["mechanics"]
    counts = Counter(m["status"] for m in mechs)
    report = {
        "registry_verified_for_patch": reg["verified_for_patch"],
        "registry_last_reviewed": reg["last_reviewed"],
        "mechanics_total": len(mechs),
        "by_status": {s: counts.get(s, 0) for s in STATUSES},
        "missing": [m for m in mechs if m["status"] in ("discovered_not_implemented", "unsupported", "unknown")],
        "mechanics": mechs,
        "honesty_note": (
            "Coverage is measured against this registry, which is itself incomplete. "
            "It is not a claim of complete coverage of PoE1 crafting."
        ),
    }
    if gd is not None:
        s = gd.summary()
        report["game_data"] = {
            "game_version": s["game_version"],
            "craftable_bases_in_data": s["craftable_bases"],
            "affix_mods_in_data": s["affix_mods"],
            "essences_in_data": s["essences"],
            "fossil_like_items_in_data": s["fossils"],
            "bench_options_in_data": s["bench_options"],
        }
    return report
