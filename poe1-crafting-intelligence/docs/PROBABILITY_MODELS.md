# Probability models

## Exact

- **Next-mod distribution:** normalised weights of the eligible pool (see CRAFTING_RULES.md). Used by the Mod Pool tab and by `exact_next_mod_probability` for single-mod actions (Exalted, Regal, Augmentation).
- **Annulment:** uniform over removable mods.

## Monte Carlo (estimates)

Used for reforges (Chaos, Alchemy, Essence, Fossil). One reforge draws N mods sequentially without replacement of groups, recomputing the pool after each draw, because slots, groups and tags change. N comes from `assumptions.json`.

Each simulation reports:
- the per-attempt success probability with a **95% Wilson score interval**;
- attempts needed: mean, median, 90th/95th/99th percentiles;
- the share of runs that reached the target within the attempt cap;
- the assumptions used, with their sources and statuses;
- the seed (results are reproducible).

Expected cost is the mean number of attempts × the price per attempt. The 95% cost bound is the 95th-percentile attempts × the price. Neither includes the base item.

## Validation

- `test_sampler_matches_exact_distribution`: a chi-square test of 40,000 sampled rolls against the exact distribution.
- Planned: reference cases against Craft of Exile for the same base, item level and target.

## Known modelling assumptions

See `backend/poeci/knowledge/assumptions.json`.
- `rare_mod_count` 4/5/6 mods in the ratio 8:3:1 (community-measured).
- `magic_mod_count` and `rare_jewel_mod_count` are **placeholders**. Results that depend on them are labelled.
