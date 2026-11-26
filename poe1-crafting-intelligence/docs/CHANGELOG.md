# Changelog

## Unreleased

- Route Planner (`engine/planner.py`, `POST /api/plan`, *Route Planner* tab): ranks Chaos spam, Essence spam (strongest essence per wanted mod) and Alteration → Regal → Exalt by expected cost (Wald's identity over independent tries), with an optional final bench craft priced from the bench data. Unhit targets report a 95% minimum. Item Analyzer has a *Plan routes for this item* button.
- poe.ninja adapter moved to the live `/poe1/api/economy/...` endpoints (the old ones return 404); an unknown league is reported instead of silently saving nothing.
- 35 automated tests.

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
