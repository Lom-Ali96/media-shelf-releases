# Crafting knowledge: where it comes from

Collected 2026-11-26. For each source: what it gives, how it can be used, and how far to trust it. Rule of thumb: **game files > official patch notes > tools that read the game files > measured community data > guides that only state things**.

## 1. Game data (most reliable)

| Source | What it gives | Used by the app |
|---|---|---|
| [RePoE export](https://github.com/repoe-fork/repoe-fork.github.io) (`data/*.json`) | Mods with spawn and generation weights, bases, essences, fossils, bench options with costs, item classes, tags | ✅ the whole engine (`knowledge/importer.py`) |
| RePoE `stat_translations.json`, `mods_by_base.json` | Mod text per stat, precomputed pools | not yet (could improve text matching) |
| [poe-dat-viewer](https://snosme.github.io/poe-dat-viewer/) | Raw game tables (e.g. `mods.dat` spawn weights, Harvest and Bestiary tables) | manual checks |
| Official trade data `/api/trade/data/stats` and `/filters` | Trade stat ids, filter names | ✅ trade links |
| Official currency exchange API (public, hourly history) | Currency trade history per league | not yet (an alternative to poe.ninja for currency) |

## 2. Official text

| Source | What it gives | Note |
|---|---|---|
| [Patch notes forum](https://www.pathofexile.com/forum/view-forum/patch-notes) (3.30.0 = thread 4013680) | Every change per patch and hotfix | ✅ read in full for 3.30.0; hotfixes 3.30.0b–d only partly. The poewiki copies block automated reading |
| [Developer docs](https://www.pathofexile.com/developer/docs) | API rules, OAuth scopes, ladder, public stash API | ✅ read: app registration is currently closed; no API gives other players' equipment |

## 3. Tools that read the game files

| Source | What it gives | Used by the app |
|---|---|---|
| [Craft of Exile](https://www.craftofexile.com) data file `json/data/main/poec_data.json` | Every base, mod tier and weight, the **six influence pools**, veiled, essence, Delve and Incursion mods, **Eldritch implicits** (≈670 entries with tiers and weights), Maven data | ✅ `scripts/compare_craftofexile.py`: 62 of 64 pool cases identical (10 bases, 9 × 6 influences); the 2 differences are a Craft of Exile quirk with the wand generation weight |
| Craft of Exile [FAQ](https://www.craftofexile.com/faq), [basics](https://www.craftofexile.com/basics), [metamods](https://www.craftofexile.com/metamods) | The assumptions behind its simulator | ✅ read: Annulment = equal chance per removable mod; Harvest "same types" ×90 (second-hand, 2020); "more common" ×10 is an extrapolation; Sanctified Fossil formula from a 1000-item test |
| [poedb.tw](https://poedb.tw/us/) | Game-data pages: Harvest (73 crafts), Bestiary recipes (78), Fracturing Orb, Recombinator, league pages | ✅ Harvest costs, beast list, Fracturing rules. Some tables have no patch label |

## 4. Measured community data

| Source | What it gives | Status |
|---|---|---|
| Recombinator odds (Reddit "The Complete Guide to Recombinators", r/pathofexile post v0nm0c; "Butsicles' research" quoted by an [aoeah 3.29 guide](https://www.aoeah.com/news/4757--poe-329-recombinator-guide-modes-odds-unpredictable--predictable-recomb-tips); table on [poedb](https://poedb.tw/us/Recombinator)) | How many mods survive for a pool of 1–6 mods; exclusive-mod rule; base choice | ⚠️ **two tables disagree** (e.g. pool of 4: 10/60/30 vs 10/55/35) and 3.30 changed pools of 1–3 again. Recorded, not used |
| Memory Strands tier table ([Maxroll](https://maxroll.gg/poe/resources/crafting-resources)) | Tier floors per strand count | labelled community testing; not modelled |
| Chaos/Alchemy 4/5/6 mods = 8:3:1 | Mod count on rares | ✅ in `assumptions.json` (community-measured) |

## 5. Guides (useful for rules, numbers need checking)

| Source | What it gives | Used |
|---|---|---|
| [Maxroll crafting resources](https://maxroll.gg/poe/resources/crafting-resources) (updated 2026-11-13) | Rules: essences and fossils ignore prefix/suffix locks, Harvest reforges respect them; attack/caster metamods; Eldritch dominance; Awakener's Orb; Orb of Dominance; veiled-exalt tricks | ✅ essence/fossil lock rule now in the engine |
| [Maxroll Eldritch implicits](https://maxroll.gg/poe/crafting/eldritch-implicits) | Six tiers (Lesser…Perfect), Embers/Ichors up to Exceptional, Orb of Conflict (one implicit up, the other down; 50/50 at equal tiers) | recorded; Eldritch not modelled yet |
| Maxroll [Harvest](https://maxroll.gg/poe/crafting/harvest-crafting-guide) and [fossil](https://maxroll.gg/poe/crafting/fossils-resonators) guides | Practical use | not read in full |

## 6. Open-source simulators (to compare code and edge cases)

- [PoETheoryCraft](https://github.com/Sectoidfodder/PoETheoryCraft) (C#; essences, fossils, metamods; its author made the Sanctified Fossil test)
- [poecraft2](https://github.com/OliverOrton/poecraft2) (C++ engine + SQLite; exact strategy planner)
- [poe-crafting-sim](https://github.com/Maraleroo/poe-crafting-sim) (Rust/WebAssembly)
- [Rasslabsya4el/crafting-system](https://github.com/Rasslabsya4el/crafting-system) (issue #85 discusses 3.29 Eldritch currencies)

## 7. Not reachable automatically

- **poewiki.net** blocks automated reading (bot protection). Read it in your browser.
- **Reddit** refuses automated reading; Claude in Chrome (your browser) can read posts when connected, and the app takes pasted text.

## Open questions and where to look next

| Question | Best next source |
|---|---|
| Which mod does a partial lock ("1 Prefix Modifier cannot be changed") protect? | an in-game test (cheap), then patch hotfix notes |
| Transmutation/Alteration: 1 or 2 mods, real split | community data collection (none found); an in-game sample of ~200 alts would settle it |
| Rare jewel: 3 or 4 mods | same |
| Harvest "more likely": ×90 (Craft of Exile, old) or ×10 (Maxroll, unsourced)? | poe-dat-viewer Harvest tables, or an in-game sample |
| Recombinator odds in 3.30 | the Reddit guide's 3.30 update, if any |
| Eldritch Ember/Ichor outcome weights | Craft of Exile data (`eldritch_red` / `eldritch_blue` entries) and RePoE (`searing_exarch_implicit` / `eater_of_worlds_implicit` mods) |
| Gwennen coin-flip options | not published yet |
