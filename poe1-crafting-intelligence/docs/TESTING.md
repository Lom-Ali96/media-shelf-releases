# Testing

Run all tests:

```
.venv\Scripts\python -m pytest -q backend    (Windows)
.venv/bin/python -m pytest -q backend        (Linux/macOS)
```

| File | Covers |
|---|---|
| `tests/conftest.py` | Hand-written mini game data with exactly known weights |
| `test_engine.py` | Pool rules (item-level gating, zero weights, essence-only, influence, groups, slots), metamods, tiers, every action's validation and protection rules, bench limits, essences, fossils, divine ranges |
| `test_simulation.py` | Chi-square check of the sampler against exact probabilities, exact Exalted probability, seeded reproducibility, Wilson intervals |
| `test_parser_market_api.py` | Basic, advanced and magic item parsing; out-of-range values never guessed; poe.ninja parsing and cache with a mocked transport; overrides; patch-gate warnings; API smoke test |
| `test_realdata.py` (`realdata`) | Reference facts on the real 3.30 data: Virile = T1 life on rings, pools sum to 1 on 6 bases, influence widens pools, real advanced item parses, Royale mods never roll |
| `test_planner.py` | Route planner: Wald cost, bench finish, essence/fossil selection (blocking fossils never offered), impossible targets give a minimum, bad input, API |
| `test_trade_roi.py` | Trade link building (worst-tier minimums, "reduced" sign, eDPS filter), stat-list cache per game version, ROI board, analyzer bench list and "find similar" |
| `test_pob.py` | Path of Building codes: decoding, `{range}`/`{crafted}`/implicits, active item set, assumed item level, refused inputs (links, garbage, broken XML, decompression bomb) |
| `test_realdata.py::test_mod_pools_match_craft_of_exile` | The 30 Craft of Exile reference cases (skipped until `data/craftofexile_poec_data.json` exists) |
| `test_recipe.py` | Harvest/beast actions, recipe engine (until, check, goto, restart, validation), costs, Harvest and lock routes in the planner |
| `test_recipes_api.py` | Step suggestions from text, recipe validation, simulate + compare, recipe library, collected ideas and their price groups |
| `test_web.py` | The page's JavaScript has no syntax error (`node --check`; skipped without Node.js). Regression for the broken-tabs bug |
| `test_storage.py` | The shared database connection under 16 threads (regression for the stress-test crash) |

### Stress test

`scripts\stress_test.py` starts a throwaway copy of the app (temporary database, port 8799; your data is not touched), sends broken and extreme inputs to every endpoint, loads the mod pool of every craftable base, plans one craft per item class and fires 86 requests at once. Any HTTP 500 is reported as a bug; the script exits with code 1 if it finds one. About 5 minutes:

```
.venv\Scripts\python scripts\stress_test.py
```

2026-11-26 run: fuzzing found nothing; all 1,135 bases loaded (17 s); 32 item-class plans (~5 s each); concurrency found a real bug (shared SQLite connection used by several threads → HTTP 500 and dropped connections), fixed with a locked connection; rerun: 86/86 requests OK.

**Promotion rule:** a mechanic moves to `implemented_verified` only after at least 3 reference cases agree with an independent source (Craft of Exile or a logged in-game test) within the Monte Carlo confidence interval. Those cases are then added as tests.

M1 result: **31 passed** (including the real-data tests). Now: **72 passed**.

### Cross-check with Craft of Exile

`scripts\compare_craftofexile.py [item level]` downloads Craft of Exile's public data file once (`data/craftofexile_poec_data.json`, ~9 MB) and compares, for 10 bases, every rollable tier (affix, mod group, required item level, weight) with ours. Both sides read weights from the game's `mods.dat`, so this checks how the app applies them (pool rules, item-level gates, generation multipliers, exclusions), not the raw numbers.

2026-11-26 result: 29 of 30 cases identical. Extended the same day to influence pools (9 bases × 6 influences): 62 of 64 cases identical at item level 86; both differences are the wand generation-weight quirk below. Imbued Wand, item level ≥ 50: local mana leech CoE 1000 vs ours 500. Our 500 = spawn weight 1000 × the data's 50% generation weight for `wand_can_roll_caster_modifiers`; CoE applies that 50% to the matching life-leech mod (both 500) but not to mana leech, so we keep ours. CoE also rounds 12.5 to 12 (negligible).
