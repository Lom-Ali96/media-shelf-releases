# Testing

Run all tests:

```
.venv\Scripts\python -m pytest -q backend    (Windows)
.venv/bin/python -m pytest -q backend        (Linux/macOS)
```

| File | Covers |
|---|---|
| `tests/conftest.py` | Hand-written mini game data with exactly known weights |
| `test_engine.py` | Pool rules (item-level gating, zero weights, essence-only, influence, groups, slots), metamods, tiers, every action's validation and protection rules, bench limits, essences, fossils, divine ranges |
| `test_simulation.py` | Chi-square check of the sampler against exact probabilities, exact Exalted probability, seeded reproducibility, Wilson intervals |
| `test_parser_market_api.py` | Basic, advanced and magic item parsing; out-of-range values never guessed; poe.ninja parsing and cache with a mocked transport; overrides; patch-gate warnings; API smoke test |
| `test_realdata.py` (`realdata`) | Reference facts on the real 3.30 data: Virile = T1 life on rings, pools sum to 1 on 6 bases, influence widens pools, real advanced item parses |

**Promotion rule:** a mechanic moves to `implemented_verified` only after at least 3 reference cases agree with an independent source (Craft of Exile or a logged in-game test) within the Monte Carlo confidence interval. Those cases are then added as tests.

M1 result: **31 passed** (including the real-data tests).
