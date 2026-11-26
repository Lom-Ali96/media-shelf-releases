# Crafting coverage

The live source of truth is `backend/poeci/knowledge/mechanics_registry.json`, shown in the app's **Coverage** tab. This file explains the statuses.

| Status | Meaning |
|---|---|
| implemented_verified | Implemented, **and** reference cases cross-checked against an independent tool or in-game test pass |
| implemented_partially_verified | Implemented from game data plus community-established rules; internal tests pass; no external cross-check yet |
| experimental | Implemented with known gaps; results are labelled |
| discovered_not_implemented | Known to exist in 3.30; no engine support |
| unsupported | Deliberately not handled; the engine refuses rather than guesses |
| outdated / removed | No longer in the current game |
| unknown | Existence or behaviour in the current patch is not established |

State at 2026-11-26 (patch 3.30): 44 registry entries.

| Status | Count |
|---|---|
| implemented_verified | 0 |
| implemented_partially_verified | 20 |
| experimental | 1 |
| discovered_not_implemented | 16 |
| unsupported | 3 |
| unknown | 3 |
| removed | 1 |

**No claim of 100% coverage is made.** The registry itself is incomplete. In particular, the full 3.30 patch notes have not yet been reviewed for new crafting mechanics.
