# PoE1 Crafting Intelligence

A personal, local, evidence-based crafting assistant for **Path of Exile 1**. It never plays the game for you: it analyses, simulates and explains.

**Current state: milestone 1** (game data 3.30.0.4.3, league *Covens of Umbra*):

- **Versioned game data**, imported from the RePoE export of the game files, with SHA-256 provenance.
- **Mod Pool:** every mod a base can roll, with its tier and *exact* probability. Handles item level, influences and metamods.
- **Item Analyzer:** paste an item (Ctrl+C or Ctrl+Alt+C) to see its mods, tiers and open affixes, which currencies are legal on it, which **bench crafts fit right now** (with cost), and a **Find similar on trade** link.
- **Path of Building import:** paste a PoB code (also from poe.ninja character pages) to load every equipped item and analyse it.
- **Route Planner:** pick the mods you want (or click *Plan routes for this item* in the Item Analyzer), set the worst tier you'd accept, optionally finish one mod on the crafting bench. It compares the standard methods (Chaos spam, Essence spam, Fossil spam (experimental), Alteration → Regal → Exalt) by expected cost in chaos/divine, with step lists, the chance per try and the assumptions used. Targets that never hit in the simulation get a *minimum* cost instead of a guess. **Copy for Reddit** copies a route (target mods in game text, steps, expected cost, the other methods compared, data sources) as ready-to-post markdown, so you can ask the community whether it is optimal.
- **Guide library:** Craft of Exile's guide index (52 guides with links, author, patch) plus 10 written guides turned into recipes you can load, simulate and compare (pohx's current 3.30 RF crafts, GhazzyTV's fossil crafts); each marked 3.30 or older patch.
- **Mod Pool** in a two-column prefix/suffix view: influence buttons, tag filters (show / hide), groups with tiers, click a tier to add it as a wanted mod, then *Plan routes* or *Use in Recipes*.
- **Recipes (Reddit / guides):** paste a crafting post; the app suggests the steps (essences, fossils, Harvest, locks, scour, exalt, bench crafts…) in order, you check and edit them, then **Simulate and compare** shows that recipe's cost next to the app's best route for the same target. Save recipes to a library and filter it by base ("which saved crafts exist for this base?").
- **Idea collector:** *Add to craft ideas* in the Item Analyzer (a pasted game/trade item with the price you saw) or *Add as idea* in the Path of Building import. Craft Ideas plans all of them and groups them **under 10 div / 10–100 div / over 100 div** with expected profit.
- **Craft Ideas:** a starter list of 11 common craft targets (editable JSON). One click plans all of them (about 40 s); you check each sale price with its trade link and the profit appears. Saved ideas join the ROI board.
- **Verified mod pools:** the mod pools and weights were cross-checked tier by tier against Craft of Exile (29 of 30 reference cases identical, the one difference explained); see `scripts/compare_craftofexile.py`.
- **ROI:** each plan gets a *Check prices on the trade site* button (a pre-filled search you open yourself; the app never searches or reads the trade site). Enter the sale price to see profit and ROI per route, and save it to the **ROI board**, which lists your crafts by expected profit.
- **Simulator:** repeat a currency until a target is hit. Reports a Monte Carlo estimate with a 95% interval, attempt percentiles, expected cost when prices are known, and the assumptions used.
- **Coverage dashboard:** every known mechanic and how well it is supported. It does not claim 100%.
- **Patch gate:** if game data moves to a patch the rules weren't reviewed for, every result is flagged.
- **Market:** poe.ninja prices (cached and polite) plus manual price overrides.

Start here:
1. [docs/INSTALLATION.md](docs/INSTALLATION.md): Windows setup in 5 commands.
2. [docs/RESEARCH_REPORT.md](docs/RESEARCH_REPORT.md): Phase 0 research, feasibility, tools and sources.
3. [docs/ROADMAP.md](docs/ROADMAP.md): milestones, backlog and acceptance criteria.
4. [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md): what it can't do yet.

Other docs:
- [ARCHITECTURE](docs/ARCHITECTURE.md)
- [DATABASE_SCHEMA](docs/DATABASE_SCHEMA.md)
- [DATA_SOURCES](docs/DATA_SOURCES.md)
- [API_INTEGRATIONS](docs/API_INTEGRATIONS.md)
- [CRAFTING_RULES](docs/CRAFTING_RULES.md)
- [CRAFTING_COVERAGE](docs/CRAFTING_COVERAGE.md)
- [RESOURCES](docs/RESOURCES.md): where crafting knowledge comes from, how reliable each source is, open questions
- [MECHANICS_3_30](docs/MECHANICS_3_30.md): what exists in 3.30 and the build order for missing mechanics
- [PROBABILITY_MODELS](docs/PROBABILITY_MODELS.md)
- [COMMUNITY_RESEARCH](docs/COMMUNITY_RESEARCH.md)
- [MARKET_ANALYSIS](docs/MARKET_ANALYSIS.md)
- [SECURITY](docs/SECURITY.md)
- [TESTING](docs/TESTING.md)
- [UPDATE_GUIDE](docs/UPDATE_GUIDE.md)
- [CHANGELOG](docs/CHANGELOG.md)
- [TODO](docs/TODO.md)

Quick start (once installed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1     # then open http://127.0.0.1:8765
```

Not affiliated with Grinding Gear Games. Game data © Grinding Gear Games; for personal, non-commercial use.
