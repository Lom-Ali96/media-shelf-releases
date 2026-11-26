# Changelog

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
