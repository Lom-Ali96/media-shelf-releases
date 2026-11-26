# Architecture

## 1. Principles

- **Engines are independent Python packages.** The UI talks to them only through the HTTP API.
- **Game rules are deterministic code plus versioned data.** An AI model is never an authority on weights, mechanics, prices or probabilities.
- **Every number carries provenance:** game data version, the assumptions it used, market snapshot and timestamp.
- **The app refuses instead of guessing.** Unsupported mechanics raise `UnsupportedMechanic`, and ambiguous item lines are reported as ambiguous.

## 2. Engines and folders

```
backend/poeci/
├── knowledge/   Game Knowledge Engine
│   ├── importer.py            download + version RePoE snapshots (data/snapshots/<ver>/)
│   ├── gamedata.py            typed, indexed read-only view (Mod, Base, GameData)
│   ├── mechanics_registry.json  every known mechanic + status  (coverage source of truth)
│   ├── assumptions.json       numbers NOT in game files, with source/status
│   └── coverage.py            coverage dashboard data
├── engine/      Crafting Rules Engine + Simulation Engine
│   ├── item.py                ItemState (immutable), ItemView, tiers, spawn-weight rule, metamods
│   ├── modpool.py             eligible pool + exact probabilities (cached hot path)
│   ├── actions.py             each currency = pure function (gd, item, rng) -> item
│   ├── simulate.py            targets, exact one-step probability, Monte Carlo, Wilson CIs
│   └── planner.py             route planner: standard methods ranked by expected cost
├── parsing/     clipboard.py  Ctrl+C / Ctrl+Alt+C item parser
│                pob.py        Path of Building code -> equipped items as Ctrl+C text
├── market/      poeninja.py   Market Engine (adapter, cache, overrides, price lookup)
├── updates/     versions.py   Update Engine (patch gate, version checks)
├── storage/     db.py + migrations/*.sql   SQLite for user + market state
├── api/         app.py        FastAPI: the only interface the UI uses
└── web/         index.html    M1 UI (single page, no build step)
```

Planned packages, created when their phase starts:
- `optimize/`: Optimization Engine (Phase 7).
- `research/`: Community Research and Validation Engines (Phase 6).
- `capital/`: Personal Capital Engine (Phase 10).
- `assistant/`: AI Assistant (Phase 12).

## 3. Engine interfaces (contracts)

```python
# Knowledge
GameData.from_dir(path) -> GameData
GameData.mods / .bases / .essences / .fossils / .bench_options / .version

# Rules
eligible_pool(gd, item, *, weight_fn=None) -> list[PoolEntry(mod, weight, probability)]
actions.apply(gd, item, action_id, rng, **params) -> ItemState     # raises InvalidAction / UnsupportedMechanic
ACTIONS[action_id] -> ActionInfo(currency, assumptions, status)

# Simulation
Target([ModRequirement(mod_type, max_tier)])
exact_next_mod_probability(gd, item, target) -> float               # exact
simulate_repeat_until(gd, start, action, target, runs, seed) -> SimulationResult (estimate + CI + assumptions)

# Market
PoeNinja(conn).fetch(league, category) -> snapshot_id                # cached, rate-limited
price_of(conn, league, name) -> {chaos_value, source, as_of, is_listing_price}

# Update
versions.status(conn, imported_version) -> {rules_verified_for_current_data, warnings, ...}
```

Planned contracts:

```python
# Optimization (Phase 7)
find_strategies(gd, start, target, budget, prices, objective) -> list[Strategy]
# Strategy = policy: state-abstraction -> action, with expected cost, variance,
# success probability, assumptions, and "proven optimal" vs "best found" flag.

# Validation (Phase 6)
validate_recipe(gd, recipe) -> ValidationResult(status, simulated_cost, issues, confidence)

# Capital (Phase 10)
allocate(capital, inventory, risk_profile, opportunities) -> Plan
```

## 4. Data flow

```
RePoE (GitHub raw) ──importer──▶ data/snapshots/<game ver>/  ──▶ GameData
poe.ninja economy ──adapter──▶ SQLite market_snapshots/prices
Pasted item ──parser──▶ ItemState ─┐
                                  ├──▶ rules engine ──▶ simulation ──▶ API ──▶ UI
mechanics_registry + assumptions ─┘                         ▲
versions.status (patch gate) ───────────────────────────────┘ flags every result
```

## 5. Patch gate

`mechanics_registry.json.verified_for_patch` holds the patch the rules were last reviewed against, for example `3.30`. If the imported game data has a different major.minor version, `rules_verified_for_current_data` becomes false. The UI then shows a red warning on every simulation until a human reviews the patch notes and bumps the value. Data updates are automatic; rule sign-off is deliberately manual.

## 6. Pathfinding design (Phase 7)

Brute-forcing item states is impossible: there are about 200 mods per base and up to 6 affix slots. The plan:

1. **State abstraction.** Map a full item to `(which target families are present at an acceptable tier, open prefixes, open suffixes, rarity, metamods, protected mods)`. Mods that are not targets only matter for slot counts and group blocking.
2. **Action model.** Get each abstract transition probability from the rules engine: exactly for single-mod actions, and by simulation with caching for reforges.
3. **Solve** the result as a stochastic shortest-path / MDP problem with value iteration over the small abstract space, minimising expected cost. Variance and budget-ruin probability come from the resulting policy by simulation.
4. **Seed with strategy templates** (essence spam, then annul/exalt; prefix lock plus chaos; fractured bases; …) to rank human-understandable plans and add search candidates.
5. **Report honesty.** "Optimal within the modelled action set" versus "best found within limits".

## 7. Technology choices and why

| Choice | Why |
|---|---|
| Python + FastAPI + Pydantic | Fast iteration, strong numeric ecosystem, typed API |
| SQLite (stdlib `sqlite3` with SQL migrations) | Zero setup on Windows. SQLAlchemy and PostgreSQL only if multi-device sync is needed |
| JSON snapshots for game data | Data comes as JSON per patch and is immutable per version; reproducibility is free |
| Single-page HTML UI for M1 | No Node.js toolchain needed to start. **React + TypeScript + Vite** come in Phase 4–5 when charts and crafting trees need it; the API stays the same |
| Pure Python engine | Correctness first. NumPy vectorisation next; Rust only if profiling shows it is needed |
| Optional Tauri packaging | Later; a local web app is enough |
