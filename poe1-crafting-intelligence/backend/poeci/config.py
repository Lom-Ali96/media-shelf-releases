"""Central configuration. Everything is overridable with environment variables so
nothing machine-specific is hard-coded."""
from __future__ import annotations

import os
from pathlib import Path

# Project root = folder that contains backend/, docs/, data/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("POECI_DATA_DIR", PROJECT_ROOT / "data"))
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DB_PATH = Path(os.environ.get("POECI_DB_PATH", DATA_DIR / "poeci.sqlite3"))

# RePoE fork: community export of the PoE1 game files (GGPK), regenerated each patch.
# Served from GitHub's raw CDN, which is a static file host (no scraping involved).
REPOE_RAW_BASE = os.environ.get(
    "POECI_REPOE_BASE",
    "https://raw.githubusercontent.com/repoe-fork/repoe-fork.github.io/master",
)
REPOE_FILES = [
    "mods.json",
    "base_items.json",
    "item_classes.json",
    "essences.json",
    "fossils.json",
    "crafting_bench_options.json",
    "tags.json",
    "mod_types.json",
]

# poe.ninja economy endpoints (the only part of poe.ninja documented for third parties).
POE_NINJA_BASE = os.environ.get("POECI_POE_NINJA_BASE", "https://poe.ninja")
# Be polite: never call a market endpoint more often than this per (endpoint, league, type).
MARKET_CACHE_SECONDS = int(os.environ.get("POECI_MARKET_CACHE_SECONDS", "900"))

USER_AGENT = "poeci-personal-crafting-tool/0.1 (personal, non-commercial)"
