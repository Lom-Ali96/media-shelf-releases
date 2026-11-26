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
- 53 automated tests.

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
