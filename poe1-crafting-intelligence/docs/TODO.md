# TODO

The ordered backlog is in ROADMAP.md. Open questions:

- [ ] What 3.30 crafting changes are there? (read the full 3.30.0–3.30.0c notes)
- [ ] Are recombinators available in 3.30?
- [ ] Where do the prefix/suffix lock metamods come from in 3.30?
- [ ] Source the Transmutation/Alteration 1-vs-2 mod split.
- [ ] Source the rare jewel 3-vs-4 mod split.
- [ ] Rarity after Scouring an item that keeps fractured mods.
- [ ] Do Shrieking/Deafening essences still reforge rares in 3.30? (confirm in game)
- [ ] 4 "Royale" mods (`LocalIncreasedAttackSpeed2Royale____`, `IncreasedAttackSpeed2Royale`, `IncreasedCastSpeed2Royale`, `MovementVelocity2Royale`) have normal spawn weights in the 3.30 RePoE data, so the engine includes them in pools for weapons, gloves, quivers, shields, wands, sceptres, amulets and boots. They very likely cannot roll in the real game (event-only). Verify (Craft of Exile / poedb), then exclude them in `modpool._candidates` and in tier families. Found 2026-11-26.
- [ ] Check that trade links (`?q=`) open with all filters applied.
- [x] Check the poe.ninja response shape live; leagues are at `/poe1/api/data/index-state` (2026-11-26).
