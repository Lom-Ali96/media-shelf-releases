# Phase 0 — Research and feasibility report

Date: 2026-11-26. Scope: Path of Exile 1 only.

**How to read this report.** Each claim is marked:
- **[verified]**: checked during this session against a live source, which is named.
- **[known]**: established knowledge about the tool or source that I could not re-check live here. The development container's network policy blocked poe.ninja, pathofexile.com, poewiki.net and poedb.tw. Re-check these on your PC before relying on them.
- **[open]**: unknown; needs research.

---

## 1. Current game state

| Item | Value | Status |
|---|---|---|
| Current league | **3.30 "Covens of Umbra"**, started 2026-11-13, ends 2027-03-19 | [verified] web search, arpg-timeline.com / poewiki Version_3.30.0 |
| Latest patch | 3.30.0c (hotfix 3.30.0b dated 2026-11-15) | [verified] web search |
| Game data available to tools | RePoE export of client **3.30.0.4.3**, regenerated 2026-11-26 | [verified] downloaded; `version.txt` |
| Notable 3.30 changes | Scarabs removed and replaced by "Threads"; Atlas tree overhaul (150 points); Mirage becomes core; Ultimatum reward changes | [verified] web search (patch-note summaries) |
| 3.30 crafting-specific changes | Not yet established | [open]: read the full 3.30.0 patch notes on your PC and update `mechanics_registry.json` |
| Example found in the data | "Prefix/Suffix Modifiers cannot be changed" mods still exist in the game files but are **not** crafting-bench options in 3.30 data | [verified] from the imported data |

The last row shows why the registry must never assume a mechanic carried over from a previous league.

## 2. Existing tools: analysis

| Tool | What it offers | Reuse potential | Notes |
|---|---|---|---|
| **Craft of Exile** (+ beta) | The most complete PoE1 crafting simulator: mod pools, weights, emulator, calculators for essences, fossils, Harvest and more | **Reference only.** Closed source; no public API [known] | Best cross-validation target for this engine's probabilities. Do not scrape it. |
| **PoEStash** | [open] could not verify scope or maintenance | unknown | Check manually |
| **PoEDB** (poedb.tw) | Datamined mods, weights, bases and patch diffs; very fast to update after patches | Reference / manual lookup. No documented public API [known] | Useful to diff patches by hand |
| **PoE Wiki** (poewiki.net) | Mechanics explanations, version history; MediaWiki with Cargo tables | Text is CC BY-NC-SA [known]; Cargo API usable for personal use with polite rate limits | Good for *patch notes per version* |
| **RePoE** (repoe-fork) | JSON export of game files: mods, bases, essences, fossils, bench options, tags, stat translations | **Used directly.** Served as static files from GitHub | [verified] reachable; current to 3.30.0.4.3 |
| **PyPoE** | Python GGPK parser that generates RePoE | Indirect | Only needed if RePoE stops updating |
| **Path of Building Community** | Build calculator; data exports (also mirrored by repoe-fork `pob-data`) | MIT licence [known]; uniques data is hand-maintained | Needed later for build-demand features |
| **poe.ninja** | Economy overviews (currency and item prices), build stats | Economy endpoints only. Docs say: no SLA, may break without notice, excessive use is blocked; builds/character/PoB endpoints are internal [verified via search snippets of poe.ninja/docs/api] | Adapter written; needs a live check on your PC |
| **Official trade site** | Live listings | **Not for automated use** (no public trade API for third parties) [known] | We generate trade *links* only |
| **GGG developer API** | OAuth APIs: account/characters/stashes (user-authorised), public stash river (registered apps only), league list, currency-exchange history (added 2025) | Account stash access for **your own** inventory is feasible with an OAuth app registration [known] | Registration needs a GGG-approved app; manual inventory is the fallback |
| **Maxroll** | Build guides | Read manually; no API | Use for demand research by hand |
| **Reddit** | Crafting showcases and Rule-10 explanations | Official API: OAuth, ~100 requests/min, personal "script" apps allowed [known] | Phase 6, as manual URL import first |
| **YouTube** | Crafting guides | Data API cannot download other people's captions [known] | Paste transcripts manually |

## 3. Feature comparison matrix

| Feature | Craft of Exile | PoEDB | poe.ninja | PoB | **This app (M1)** | This app (planned) |
|---|---|---|---|---|---|---|
| Mod pool + exact weights | ✅ | ✅ (view) | – | – | ✅ | ✅ |
| Currency emulator | ✅ | – | – | – | ✅ basic currencies + essence + bench (+ experimental fossils) | all mechanics |
| Mass simulation with confidence intervals | partial | – | – | – | ✅ | ✅ faster |
| Patch-version awareness / invalidation | manual | ✅ diffs | – | – | ✅ status and warnings | full diff reports |
| Item clipboard parsing | ✅ | – | – | ✅ | ✅ both formats | ✅ |
| Market prices | partial | – | ✅ | – | ✅ adapter + manual overrides | history, trends |
| Automatic pathfinding | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (Phase 7) |
| Profit scanner / capital advice | ❌ | ❌ | partial | ❌ | ❌ | ✅ (Phases 9–10) |
| Community recipe validation | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (Phase 6) |

The planned differentiators are pathfinding, validated recipes and capital-aware advice. No existing tool combines them.

## 4. Reusable open-source components

- **RePoE data (in use).** It replaces writing our own GGPK parser. It is the single largest saving.
- **PoB data exports** (repoe-fork `pob-data`): uniques and base stats, for valuation and build-demand work later.
- **Statistics tooling:** NumPy/SciPy for vectorised simulation once profiling justifies it. The current pure-Python engine does about 0.5 ms per Chaos Orb roll.
- **Not reused:** Craft of Exile code (proprietary), poe.ninja internals, and anything behind a login.

## 5. Data sources: permitted use (summary; details in DATA_SOURCES.md)

| Source | Automated access | How we use it |
|---|---|---|
| RePoE on GitHub raw | ✅ static files | Game-data snapshots; version check |
| poe.ninja economy endpoints | ✅ politely, cached; no SLA | Prices (listing-based, not sales) |
| GGG OAuth APIs | ✅ with a registered app | Optional: your own stash/inventory |
| Official trade website | ❌ | Generate search links only |
| Reddit API | ✅ OAuth personal app | Later; manual URL import first |
| PoE Wiki Cargo/MediaWiki API | ✅ politely | Later: patch notes per version |
| Craft of Exile, PoEDB, Maxroll | ❌ no API | Manual reference only |

## 6. Current-patch crafting mechanics inventory and coverage matrix

The registry is kept as data in `backend/poeci/knowledge/mechanics_registry.json` and shown live in the app's **Coverage** tab. At this milestone:

| Status | Count | Examples |
|---|---|---|
| implemented, verified | 0 | Nothing is called "verified" until reference cases pass (TESTING.md) |
| implemented, partially verified | 20 | Transmutation through Divine; Essences; bench add/remove; multimod; cannot-roll-attack/caster; prefix/suffix lock effect; jewels; flasks |
| experimental | 1 | Fossils (tag-weight multipliers only) |
| discovered, not implemented | 16 | Harvest, Bestiary, fracturing, influence currencies, Eldritch, veiled, catalysts, cluster jewels, … |
| unsupported | 3 | Partial locks (the engine refuses them), maps, gems |
| unknown | 3 | Recombinators in 3.30, double corruption in 3.30, 3.30 league crafting |
| removed | 1 | Scarabs (3.30) |

In the imported 3.30 data: 1,135 craftable bases, 12,901 affix mods, 107 essences, 445 fossil/resonator entries and 782 bench options.

## 7. Technical feasibility

| Area | Feasible? | Main risk |
|---|---|---|
| Game knowledge database | ✅ high | Mechanics that are not in the game files (mod-count distributions, Harvest rules) need community data |
| Rules engine + exact single-step probabilities | ✅ high | Long tail of special interactions |
| Monte Carlo simulation | ✅ | Speed (vectorise later) |
| Pathfinding | ⚠️ medium | The state space is huge, so it needs strategy templates plus bounded search (see ARCHITECTURE.md §6) |
| Market prices for currency and materials | ✅ | poe.ninja may change; prices are listings, not sales |
| Rare-item valuation | ⚠️ low–medium | No permitted bulk access to rare listings. Needs manual price imports or your own sales history, so expect low confidence |
| Community research automation | ⚠️ medium | Policies and rate limits; extraction quality. Start with manual URL/text import |
| Fully automatic patch synchronisation | ✅ for data; ⚠️ for rules | Rule changes in patch notes still need human review. The app enforces this with `verified_for_patch` |

## 8. Major technical challenges (ranked)

1. **Correctness of rules not in the game files.** Mod-count distributions, Harvest, recombinators, Eldritch currency. Mitigation: `assumptions.json` with sources, flagged in every result, and cross-checks against Craft of Exile.
2. **Pathfinding search space.** Mitigation: model it as a Markov decision process over *abstracted* states (which target mods are present plus open slots), not full item states; seed it with known strategy templates.
3. **Rare valuation without bulk trade data.** Mitigation: be explicit about low confidence; use manual comparables and your own sales history.
4. **Patch churn.** Mitigation: versioned snapshots, the patch gate, and real-data regression tests.
5. **Pure-Python speed.** Mitigation: caching (done, about 15× faster), then NumPy vectorisation, then Rust only if profiling demands it.

## 9. Effort, maintenance and costs

- **Development effort, rough:** Phases 1–5 take about 6–10 focused weeks for one developer using AI assistance. Phases 6–12 take another 3–6 months. Most of the time goes into correctness work on mechanics, not UI.
- **Ongoing maintenance:** about 2–6 hours per league launch (import data, read patch notes, update registry and assumptions, run tests) and about 1 hour per hotfix.
- **Operating costs:** €0 by default. Everything runs locally and all data sources used are free. An optional external AI API for Phase 12 would cost a few €/month at personal volumes. A local model costs €0 but needs a decent GPU.

## 10. Available now vs. needs data or authorisation

**Implemented now:** game-data import and versioning, mod pools with exact probabilities, the crafting emulator for basic currencies, Essences and the bench, Monte Carlo simulation, the clipboard parser, coverage dashboard, patch gate, and poe.ninja adapter with manual price overrides.

**Needs data or authorisation:**
- Live poe.ninja verification (run on your PC).
- GGG OAuth app registration for automatic stash/inventory import.
- Reddit API app for community research.
- Reliable rare-item sale data (unavailable; manual only).
- Community sources for mod-count distributions and Harvest rules.
