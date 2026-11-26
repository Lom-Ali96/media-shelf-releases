# Known limitations (milestone 1)

- No mechanic is "verified" yet; there has been no external cross-check (see TESTING.md).
- `magic_mod_count` (Transmutation/Alteration 1 vs 2 mods) and `rare_jewel_mod_count` are placeholder 50/50 assumptions.
- Fossils are experimental: forced or added mods, special fossils, sockets and quality are not modelled.
- Not modelled at all: Harvest, Bestiary, fracturing currency, influence-adding currencies, Eldritch, veiled mods, recombinators, corruption outcomes, cluster jewels, catalysts, enchantments, sockets.
- Partial locks ("1/2 Prefix Modifiers cannot be changed") are refused.
- How the lock metamods are obtained in 3.30 is unverified (they are not bench options in the 3.30 data).
- The poe.ninja adapter was verified live on 2026-11-26, but poe.ninja has no SLA and changes its API without notice. There is no automatic league discovery yet; you type poe.ninja's short league name (e.g. `Covens`). Exchange-traded items (currency, essences, fossils, …) have no listing count, only trade volume.
- Prices are listing prices. There is no rare-item valuation, pathfinding, profit scanner or capital advisor yet.
- Route Planner: compares only fixed standard methods (Chaos spam, Essence spam, Alteration → Regal → Exalt, one final bench craft). Fossils, Harvest, beasts, metamod tricks, fracturing and multimod are not included, so a cheaper route may exist. Base item price is only included when you enter it as a manual price (poe.ninja base prices depend on item level and influence). Each route gets about 2 seconds of simulation; rare targets therefore show a minimum cost, not an estimate. The 95% cost range is shown only for routes where every try costs the same. The Alteration route depends on the placeholder `magic_mod_count`. Essence spam assumes Shrieking/Deafening essences can reforge rares (no Scouring needed); this is still open in TODO.md.
- Path of Building import reads rolled values, not tiers: values that fit two tiers are reported as ambiguous. Items made inside PoB have no item level; 86 is assumed and marked. Unique items and variant lines are not analysed.
- Fossil routes are experimental (weights not yet checked against Craft of Exile); special fossils (Glyphic, Tangled, Hollow, Faceted, Sanctified, Gilded, Bloodstained, Fractured) are not used.
- The Elemental DPS minimum in trade links counts all elements, so an item with weak wanted mods but another strong element can still show up.
- Planning is CPU-heavy (pure Python, about 2 s per route); several plans at once slow each other down.
- ROI uses the sale price you enter and the *expected* cost of the cheapest route when you saved; it does not refresh automatically and ignores bad-luck risk. Trade links set no minimum for two-value mods ("Adds # to #"). There is no automatic rare-item valuation (the app must not read the trade site).
- Basic-format (Ctrl+C) parsing can be ambiguous; the app says so. Use Ctrl+Alt+C.
- Mod values are stored as the raw game-file integers: for example, life regeneration per minute in the files versus per second on the item text.
- Simulation speed is about 0.27 ms per Chaos Orb on a bow (0.5 ms on a ring) in pure Python, after the mod-pool cache. A request is capped at 5 million attempts × runs.
- The UI is a single HTML page; there are no charts yet.
