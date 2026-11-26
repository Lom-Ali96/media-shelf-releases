# Changelog

## Unreleased

- Route Planner (`engine/planner.py`, `POST /api/plan`, *Route Planner* tab): ranks Chaos spam, Essence spam (strongest essence per wanted mod) and Alteration → Regal → Exalt by expected cost (Wald's identity over independent tries), with an optional final bench craft priced from the bench data. Unhit targets report a 95% minimum. Item Analyzer has a *Plan routes for this item* button.
- poe.ninja adapter moved to the live `/poe1/api/economy/...` endpoints (the old ones return 404); an unknown league is reported instead of silently saving nothing.
- ROI: trade-site search links with the wanted mods pre-filled (`market/trade.py`; stat ids from the public static list `/api/trade/data/stats`, cached per game version), sale price entry, profit/ROI per route, and an ROI board of saved crafts (`saved_plans` table, `GET/POST /api/plans`, `DELETE /api/plans/{key}`).
- Path of Building import (`parsing/pob.py`, `POST /api/pob`): equipped items of the active item set, converted to Ctrl+C text; hybrid lines are paired in either order.
- Item Analyzer: bench crafts that fit the item now (validated by the bench action, priced), and *Find similar on trade* (`POST /api/items/trade_link`).
- Planner: experimental fossil-spam routes; Resonator prices fetched by default.
- Trade links: minimum Elemental DPS for weapon fire/cold/lightning mods.
- Royale event mods excluded from rollable affixes (poedb: "Royale Modifiers").
- Speed: mod pools cached (~2.8x faster Chaos simulation on a bow, ~1.9x on a ring).
- Fix (found by the new stress test): the shared SQLite connection crashed under concurrent requests; it is now locked.
- `scripts/stress_test.py`.
- Route Planner: *Copy for Reddit* button per route (markdown with readable target mods, steps, cost, alternatives and data sources). Plan response now includes readable wanted-mod texts (`worst_accepted_mods`, shared with the trade links).
- Fix: a broken regular expression in the page script (bench-craft list) stopped every tab from working; `test_web.py` now checks the page script with `node --check`.
- Craft Ideas tab: `knowledge/craft_ideas.json` (11 starter targets, validated against the game data), `GET /api/ideas`, `budget_s` option on `POST /api/plan` (0.2–3 s per route).
- Verification: `scripts/compare_craftofexile.py` compares our mod pools with Craft of Exile's data tier by tier. 10 bases × item level 30/68/86: 29/30 identical; the wand mana-leech difference is explained (our value follows the game file's generation weight). New registry entry `pool.spawn_weights` = implemented_verified (first verified mechanic); reference test added.
- 3.30 mechanics research (docs/MECHANICS_3_30.md): full 3.30.0 patch notes, game data, poedb Harvest (73 crafts) and Bestiary (78 recipes) lists; registry updated with sources (partial locks are new bench crafts; Harvest, beastcrafting, recombinators, double corruption exist; Gwennen data unpublished).
- Multi-step recipes (`engine/recipe.py`): steps with repeat-until, check, restart or goto, and the real cost of every action (currency, essences, fossils + resonators, bench data, lifeforce, beasts).
- New experimental actions: Harvest tag reforge, Harvest add/remove (`knowledge/harvest_crafts.json`), Farric Lynx/Wolf beastcrafts. Simulator gets a Harvest tag field and now prices every action type.
- Planner: Harvest tag-reforge routes and the multi-step "Lock prefixes/suffixes, scour, exalt" route. Fix found while building it: partial locks share the mod group of the full lock, so the lock is now selected by mod type.
- Beast prices fetched by default.
- Fracturing Orb (experimental; poedb rule), Harvest element swaps (same tier number) and Harvest "more likely the same modifier types" (×90 from an outdated report, flagged in assumptions.json). Recipe conditions gain `min_mods` and `fractured`.
- Planner: "Fracture, then Chaos" route (fracture the hardest wanted mod, restart on a wrong fracture). Simulator: Harvest swap field.
- Fix: an action called without its required parameters (e.g. an essence without a name) crashed with HTTP 500; the engine now answers "missing …".
- Recipes tab: paste a Reddit post or guide → suggested steps (`parsing/recipe_text.py`), step editor (repeat once / until all wanted / until chosen mods, bench-craft picker), **Simulate and compare** against the app's best route, saved-recipe library filterable by base (`saved_recipes`, `/api/recipes*`, `/api/bench_options`).
- Idea collector: items from the Item Analyzer (with the price seen) or the PoB import become craft ideas, grouped under 10 / 10–100 / over 100 divine with planned cost and profit (`saved_ideas`, `/api/ideas/collect`, `/api/ideas/collected*`).
- Recipe validation names the step and the missing detail; partial locks are not offered in the bench picker; readable step descriptions.
- Fix: a regex word boundary (``) had been written as a hidden backspace character; new test scans all code for control characters.
- 71 automated tests.

## 0.1.0 (2026-11-26): Milestone 1

- Phase 0 research report, architecture, schema, roadmap.
- Versioned game-data importer (RePoE, game client 3.30.0.4.3).
- Rules engine: exact mod pools, tiers, influence tags, metamods (multimod, cannot roll attack/caster, prefix/suffix lock), 14 actions.
- Simulator: seeded Monte Carlo with Wilson intervals and percentiles; exact single-step probabilities.
- Clipboard parser for Ctrl+C and Ctrl+Alt+C.
- Crafting coverage registry (44 mechanics) and patch gate.
- poe.ninja adapter (cached), manual price overrides, SQLite with migrations.
- Local web UI: Overview, Mod Pool, Item Analyzer, Simulator, Coverage, Settings.
- 31 automated tests.
