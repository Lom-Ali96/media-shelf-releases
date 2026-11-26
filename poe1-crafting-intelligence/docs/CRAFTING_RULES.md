# Crafting rules as implemented

Each rule below is implemented in `backend/poeci/engine/`. Their verification status lives in the registry.

## Mod pool (exact)

A mod can be added by a random roll if **all** of the following hold:
1. Its `domain` equals the base's domain: `item` for gear, `flask`, `jewel`, `abyss_jewel` or `affliction_jewel` (cluster).
2. It is a prefix or suffix, and that affix type still has an open slot.
   - Magic: 1 prefix and 1 suffix.
   - Rare: 3 + 3, or 2 + 2 on jewels.
3. It is not essence-only.
4. `required_level <= item level`.
5. It shares no modifier group with a mod already on the item.
6. **Spawn weight:** the first entry in the mod's `spawn_weights` whose tag the item has decides the weight. Item tags are the base tags, plus influence tags such as `ring_shaper`, plus `adds_tags` of mods already on the item.
7. The weight is multiplied by the first matching `generation_weights` entry divided by 100.
8. Metamods "Cannot roll Attack/Caster Modifiers" remove mods tagged `attack`/`caster`.

The probability of each mod is its weight divided by the pool total. This is exact given the game data.

## Tiers

Mods of the same `type` and affix type that can spawn on the base, ordered by required level from highest to lowest. Tier 1 is the best. This matches the in-game advanced description.

## Actions

| Action | Rule | Depends on assumption |
|---|---|---|
| Transmutation | normal → magic with 1–2 mods | `magic_mod_count` (placeholder) |
| Alteration | reroll magic, keep protected mods | `magic_mod_count` |
| Augmentation | magic with 1 mod → add 1 | — |
| Regal | magic → rare + 1 mod | — |
| Alchemy / Chaos | (re)forge rare to N mods, keeping protected mods | `rare_mod_count` (community-measured) |
| Exalted | rare with an open affix → add 1 | — |
| Annulment | remove one removable mod, chosen uniformly | — |
| Scouring | remove all unprotected mods; normal if none remain | rarity with fractured mods is unverified |
| Divine | reroll values of non-fractured mods | — |
| Essence | forced mod + rare reforge. Lower essences: normal items only, item-level cap. Shrieking/Deafening/corruption-only: normal or rare | `rare_mod_count` |
| Fossil | experimental: weight × (tag weight / 100) per matching mod tag | `rare_mod_count` |
| Bench add | only options present in this patch's bench data for this item class; open slot; no group clash; 1 crafted mod (3 with multimod) | — |
| Bench remove crafted | remove all crafted mods | — |

**Protected mods:** fractured mods, prefixes while "Prefix Modifiers cannot be changed" is present, and suffixes likewise.

**Refused:** corrupted items, unreleased or legacy bases, and partial locks ("1/2 Prefix Modifiers cannot be changed", new 3.30 bench crafts for 1/2 Divine), which raise `UnsupportedMechanic` until it is sourced which mod a partial lock protects.
