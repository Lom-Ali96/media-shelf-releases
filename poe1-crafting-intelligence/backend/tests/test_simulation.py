import random
from collections import Counter

import pytest

from poeci.engine.actions import add_random_mod
from poeci.engine.item import ItemState, ModInstance
from poeci.engine.modpool import eligible_pool
from poeci.engine.simulate import ModRequirement, Target, exact_next_mod_probability, simulate_repeat_until, wilson_interval

from .conftest import RING


def test_sampler_matches_exact_distribution(gd):
    """Statistical validation: empirical frequencies of one random roll must match
    the exact probabilities (chi-square, df = pool size - 1, generous threshold)."""
    item = ItemState(RING, 84, "rare")
    pool = eligible_pool(gd, item)
    rng = random.Random(11)
    n = 40_000
    counts = Counter(add_random_mod(gd, item, rng).explicits[-1].mod_id for _ in range(n))
    chi2 = sum((counts[e.mod.id] - n * e.probability) ** 2 / (n * e.probability) for e in pool)
    # 99.9th percentile of chi-square with 8 df is ~26.1
    assert chi2 < 26.1, chi2


def test_exact_next_mod_probability(gd):
    item = ItemState(RING, 84, "rare", (ModInstance("Fire1"),))
    # pool: Life1..3, Phys, Spell, Cold, Str = 3000+500+500+1000+1000 = 6000; Life T1 = 1000
    p = exact_next_mod_probability(gd, item, Target([ModRequirement("IncreasedLife", 1)]))
    assert p == pytest.approx(1000 / 6000)


def test_simulation_is_reproducible_and_consistent(gd):
    start = ItemState(RING, 84, "rare")
    t = Target([ModRequirement("IncreasedLife", 1)])
    a = simulate_repeat_until(gd, start, "chaos", t, runs=300, seed=42)
    b = simulate_repeat_until(gd, start, "chaos", t, runs=300, seed=42)
    assert a == b
    assert a.success_within_cap == 1.0
    lo, hi = a.per_attempt_ci95
    assert lo <= a.per_attempt_probability <= hi
    assert a.attempts_median <= a.attempts_p90 <= a.attempts_p95 <= a.attempts_p99
    assert any(x["name"] == "rare_mod_count" for x in a.assumptions)


def test_wilson_interval():
    lo, hi = wilson_interval(50, 100)
    assert 0.40 < lo < 0.5 < hi < 0.60
    assert wilson_interval(0, 0) == (0.0, 1.0)
