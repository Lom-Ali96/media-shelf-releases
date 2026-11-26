# Crafting mechanics in 3.30 (Covens of Umbra): research

Researched 2026-11-26 for the "all crafting possibilities" goal. Every statement names its source. Status per mechanic lives in `backend/poeci/knowledge/mechanics_registry.json`; this file explains it and sets the build order.

## Sources

| Source | What it gave | Reliability |
|---|---|---|
| 3.30.0 patch notes, read in full via the patchbot.io mirror of the official notes (dated 2026-11-10) | All crafting changes in 3.30 | Official text; the poewiki copy blocks automated reading |
| 3.30 game data (RePoE export 3.30.0.4.3) | Bench options and costs, mods (incl. Eldritch implicits, unveiled, Delve) | Game files; bench costs match the patch notes exactly |
| poedb.tw/us/Horticrafting | All 73 Harvest crafts with lifeforce costs | Game-data mirror; table not labelled with a patch, site lists 3.30 |
| poedb.tw/us/Bestiary_Recipe | 78 beastcrafting recipes | Game-data mirror; **page states no patch version** |
| maxroll.gg 3.30 reveal summary | Harvest roots, beastcrafting without yellow beasts, Gwennen | Secondary |

## What changed in 3.30 that matters for crafting

- **Partial locks are new bench crafts.** "1 Prefix/Suffix Modifier cannot be changed" costs 1 Divine Orb, "2 ..." costs 2. In the game data under `StrMasterItemGenerationCannotChangeOne/TwoPrefixes` and the Dex suffix versions.
- **Full locks are bench crafts with item-type costs:** weapons 4 Divine + 1 Sacred, armour/quivers 4 Divine + 4 Blessed, jewellery 4 Divine + 8 Exalted. The recipe drops in Nightmare Maps. (This corrects an older note that said they were not bench options in the 3.30 data.)
- **Cannot roll Attack/Caster** no longer protects mods from Orbs of Annulment. The engine never protected them, so it already matches.
- **Harvest** is now Sacred Flora inside maps. Resistance swaps cost 300 + 300 lifeforce of two types; damage swaps also need 1 Crystallised Rancour. The fragment-conversion craft was removed.
- **Beastcrafting** no longer needs yellow beasts; flask-mod recipes need a red beast; Orbs of Binding can no longer be obtained.
- **Recombinators** exist: result item level = the selected input base; not usable on corrupted items; inputs with 1–3 total prefixes or suffixes give fewer on average.
- **Double corruption:** Altar of Corruption and Lapidary Lens can corrupt an item a second time; the Lens can destroy it.
- **Orbs of Chance** are rarer with a much higher unique chance; bench options that cost Chance now cost Alteration.
- **Essences:** new Essence of Trickery.
- **Gwennen (league crafting):** three sets of two options, a coin flip applies one option of the chosen set, paid with Broken Circle Artifacts. **No option list, odds or costs are published anywhere yet.**
- Unchanged / not mentioned: fossils and resonators, Fracturing Orb, Awakener's/Maven's Orb, Eldritch currencies, Exalted/Regal/Annulment mechanics.

## Harvest crafts available (poedb, 73 total)

- **Tag reforges** (reforge a rare, guaranteed one mod with that tag): Fire 50 Wild, Cold 50 Vivid, Lightning 50 Primal, Physical 50 Vivid, Life 75 Wild, Defence 75 Primal, Chaos 100 Vivid, Attack 75 Wild, Caster 75 Primal, Speed 150 Vivid, Critical 150 Primal; Minion/Elemental/Attribute/Mana/Drop cost 200 plus 1–3 Crystallised Rancour.
- **Reforge more / less likely to keep the same mod types:** 200 Wild each.
- **Add a tagged mod and remove a random mod** (non-influenced items): 15,000–20,000 lifeforce + 1 Sacred.
- **Resistance and damage type swaps** (similar tier), **influence reforges**, **enchants** (body armour, weapons), stack conversions (fossils, essences, oils…).
- **Not available:** keep-prefix/suffix reforges, lucky values, standalone augment or remove.

## Beastcrafting recipes for equipment (poedb, version unconfirmed)

- Add a suffix + remove a random prefix (Farric Lynx Alpha); add a prefix + remove a random suffix (Farric Wolf Alpha); rare items only.
- Add a crafted meta-modifier to a non-unique item (Wild Bristle Matron).
- Imprint of a magic item (Craicic Croaker); add a mod to Shaper/Elder/conqueror items; max links/sockets; aspects; flask suffixes.

## Build order (what to implement next, and what data each needs)

| # | Mechanic | Data available? | Open questions before building |
|---|---|---|---|
| 1 | ✅ **Multi-step recipes** (do X until Y, then Z; branch on result): `engine/recipe.py` | n/a (engine work) | none |
| 2 | ✅ full locks: planner route *Lock …, scour, exalt*. ⬜ partial locks | ✅ bench data with costs | Which mod a partial lock protects (chosen by the player or random) |
| 3 | ✅ Harvest tag reforges (experimental, planner route + Simulator). ✅ more likely (×90 from an outdated report, flagged). ⬜ less likely | ✅ craft list + costs | How "more/less likely" changes the weights (multiplier) must be sourced |
| 4 | ✅ Harvest add/remove and resistance/damage swaps (experimental actions; swap keeps the tier number) | ✅ list + costs | Swap = "similar tier" rule |
| 5 | ✅ Lynx/Wolf beastcrafts (experimental actions). ⬜ metamod beast, imprint | ✅ list | Beast prices: poe.ninja Beast category (fetched by default) |
| 6 | **Recombinators** | ⚠️ rules only | Outcome odds are community-measured; need a source |
| 7 | ✅ Fracturing Orb (experimental; planner route *Fracture, then Chaos*). ✅ influence Exalted Orbs, Eldritch Embers/Ichors + Eldritch Exalted/Annulment (experimental). ⬜ Eldritch Chaos, Orb of Conflict, Awakener's Orb, Orb of Dominance, veiled/unveil, double corruption | partly (mods in data) | Odds mostly unpublished; whether crafted mods can be fractured |
| – | Gwennen coin flip | ❌ no data | Wait until the option list is published |

Lifeforce, Rancour and beast prices: poe.ninja's economy covers some of these; anything missing is entered as a manual price (Settings).
