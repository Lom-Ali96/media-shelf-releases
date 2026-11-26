# Data sources

| Source | Used for | Access method | Licence / terms | Update frequency | Status |
|---|---|---|---|---|---|
| RePoE fork (`repoe-fork/repoe-fork.github.io`) | All game data: mods, bases, essences, fossils, bench, tags | Static JSON via `raw.githubusercontent.com`; `version.txt` used for patch detection | Community project; data is derived from GGG's game files, so it is for personal, non-commercial use. Check the repo LICENSE before redistributing | Regenerated after client patches (3.30.0.4.3 on 2026-11-26) | **In use** |
| poe.ninja economy overviews | Currency, essence, fossil, … prices (listing based) | `GET /poe1/api/economy/exchange/current/overview` and `/poe1/api/economy/stash/current/item/overview` with `league` and `type` | Docs: no SLA, unversioned, may break; excessive use is blocked; builds/character/PoB endpoints are internal | poe.ninja refreshes roughly hourly; we cache for 15 min minimum | **Verified live 2026-11-26** (old `/api/data/*` endpoints are gone) |
| Manual price overrides | Anything poe.ninja lacks or misprices | You enter it in the UI | n/a | You decide | **In use** |
| GGG developer API (OAuth) | Your own stash and inventory (read-only); league list | Requires a registered OAuth application | GGG developer ToS: no reverse-engineered endpoints | — | Planned (Phase 10) |
| Official trade site | — | **Not automated.** Links only | Not a public API | — | Planned: links only |
| PoE Wiki (MediaWiki/Cargo API) | Patch notes per version, mechanic explanations | API with polite rate limits | CC BY-NC-SA text | — | Planned (Phase 11) |
| Reddit API | Crafting posts (Rule 10) | OAuth "script" app, ~100 requests/min | Reddit Data API terms | — | Planned (Phase 6). Manual URL import first |
| Craft of Exile, PoEDB, Maxroll | Cross-checking results | Manual browsing only | Proprietary | — | Reference only |

Provenance rules:
- Every game-data file carries URL, SHA-256 and import time in its snapshot's `manifest.json`.
- Every market row keeps its raw payload, fetch time, league and the game version active at the time.
- Imported web content is **untrusted data**. It is parsed and never executed, and instructions found inside it are never followed.
