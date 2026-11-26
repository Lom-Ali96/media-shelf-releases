# Roadmap, backlog and acceptance criteria

✅ done · 🟡 partial · ⬜ not started

## Milestones

| Phase | Deliverable | State | Acceptance criteria |
|---|---|---|---|
| 0 Research | RESEARCH_REPORT, ARCHITECTURE, schema, roadmap | ✅ | Docs exist; claims marked verified/known/open |
| 1 Foundation | Local app, data import, versioning, search, coverage | ✅ | `python -m poeci` serves UI; importer stores a versioned snapshot with SHA-256; coverage tab lists every registry entry; tests pass |
| 2 Core rules | ItemState, pools, basic currencies, essence, bench, metamods | 🟡 | ✅ pool probabilities sum to 1 on 6 real bases; ✅ sampler passes chi-square vs exact; ⬜ **10+ reference cases cross-checked against Craft of Exile**, after which these mechanics become "verified" |
| 3 Advanced mechanics | Harvest, Bestiary, fracture, influence currencies, Eldritch, recombinators, corruption, 3.30 league crafting | ⬜ | Each mechanic: registry entry, implementation, reference tests, status ≥ partially verified |
| 4 Simulator | Conditional recipes, cost distributions, charts, background jobs | 🟡 | ✅ seeded reproducible MC with CI and percentiles; ⬜ multi-step conditional recipes; ⬜ background jobs with cancel; ⬜ charts (React) |
| 5 Market | poe.ninja, conversion, history, trade links | 🟡 | ✅ adapter, cache, overrides; ⬜ live verification; ⬜ divine conversion in UI; ⬜ trade links; ⬜ freshness badges |
| 6 Community recipes | Manual import, extraction, validation, library | ⬜ | Recipe JSON schema; manual import of a Reddit or text guide yields steps or *explicitly listed missing info*; validation classifies into the 7 statuses |
| 7 Pathfinding | MDP over abstract states, strategy templates | ⬜ | For 5 reference targets, it finds a strategy within 10% of the best known community method's expected cost, and labels it optimal or best-found |
| 8 Item advisor | Live assistant, continuation advice, recovery | ⬜ | Paste → next-best action with EV; re-paste updates the plan; sunk cost ignored |
| 9 Profit scanner | Candidate generation, EV/ROI, risk, budgets | ⬜ | Every opportunity shows conservative/expected sale price, loss probability, confidence and data age |
| 10 Capital | Inventory, advisor, shopping lists, P&L | ⬜ | Risk profile caps exposure; shopping list nets out owned items at opportunity cost |
| 11 Continuous | Scheduler, invalidation, alerts, patch impact report | ⬜ | New `version.txt` → import → regression tests → impact report → affected recipes flagged |
| 12 Advanced | Build demand, reverse crafting, backtesting, AI assistant, OCR | ⬜ | Assistant answers only via tool calls into engines; every number cites its source |
| 13 Finalise | Packaging, backups, docs | ⬜ | One-click start on Windows; backup and restore tested |

## Feature dependency matrix (main edges)

| Feature | Depends on |
|---|---|
| Simulator | Rules engine, assumptions |
| Cost / profit | Simulator, Market |
| Pathfinder | Rules engine, Simulator, Market (for cost objective) |
| Recipe validation | Rules engine, Simulator, Market, patch gate |
| Live assistant | Parser, Pathfinder |
| Profit scanner | Pathfinder or recipe library, Market, valuation |
| Capital advisor / progression | Profit scanner, inventory, portfolio simulation |
| Alerts | Scanner, update engine |
| AI assistant | All engines exposed as tools |

## Prioritised backlog (next up first)

1. **P0:** Reference-case suite vs Craft of Exile for ring, body armour and jewel (chaos, alt/aug/regal, exalt, essence). Promote statuses.
2. **P0:** Read the full 3.30.0 to 3.30.0c patch notes; update the registry (league crafting, recombinators, Harvest availability, lock metamods).
3. **P0:** Resolve placeholder assumptions (magic 1/2 mod split, rare jewel 3/4 split) with sourced data.
4. **P1:** Verify the poe.ninja adapter live; add a league picker sourced from the documented leagues endpoint; add divine/chaos toggle.
5. **P1:** Multi-step recipes (a recipe = ordered steps with repeat-until/if conditions), executed by the simulator.
6. **P1:** NumPy-vectorised reforge sampler (aiming for 10× speed).
7. **P1:** Fossils: forced or added mods, Glyphic/Tangled specials; Harvest per 3.30 data.
8. **P1:** React + TypeScript frontend shell with charts (cost distribution histogram).
9. **P2:** Manual recipe import and validation (Phase 6 MVP).
10. **P2:** MDP pathfinder prototype on the abstract state space.

## Complexity estimate

| Phase | Relative effort |
|---|---|
| 2 (finish) | M |
| 3 | XL (long tail of mechanics) |
| 4 | M |
| 5 | S–M |
| 6 | L |
| 7 | XL |
| 8 | M |
| 9 | L |
| 10 | M |
| 11 | M |
| 12 | XL |
| 13 | S |
