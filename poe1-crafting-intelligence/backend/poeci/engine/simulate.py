"""Target specs, exact single-step probabilities, and Monte Carlo simulation."""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field

from ..knowledge.gamedata import GameData
from .actions import ACTIONS, InvalidAction, apply, assumption
from .item import ItemState, ItemView, tier_index
from .modpool import eligible_pool


@dataclass(frozen=True)
class ModRequirement:
    """Require a mod of this `type` (e.g. 'IncreasedLife') at tier <= max_tier."""

    mod_type: str
    max_tier: int = 99


@dataclass
class Target:
    required: list[ModRequirement] = field(default_factory=list)

    def met_by(self, gd: GameData, item: ItemState) -> bool:
        view = ItemView(gd, item)
        tags = view.tags()
        for req in self.required:
            ok = False
            for mi, m in view.mods():
                if m.type == req.mod_type:
                    tier, _ = tier_index(gd, view.base, m, tags)
                    if mi.crafted or tier == 0 or tier <= req.max_tier:
                        ok = True
                        break
            if not ok:
                return False
        return True


def exact_next_mod_probability(gd: GameData, item: ItemState, target: Target) -> float:
    """Exact P(one random added mod satisfies at least one still-missing requirement).

    Valid for Exalted / Regal / Augmentation style actions that add exactly one mod."""
    view = ItemView(gd, item)
    present = {m.type for _, m in view.mods()}
    missing = [r for r in target.required if r.mod_type not in present]
    pool = eligible_pool(gd, item)
    tags = view.tags()
    p = 0.0
    for e in pool:
        for r in missing:
            if e.mod.type == r.mod_type and tier_index(gd, view.base, e.mod, tags)[0] <= r.max_tier:
                p += e.probability
                break
    return p


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _percentile(sorted_vals: list[int], q: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, max(0, math.ceil(q * len(sorted_vals)) - 1))
    return sorted_vals[idx]


@dataclass
class SimulationResult:
    action: str
    runs: int
    max_attempts: int
    seed: int
    successes: int
    per_attempt_probability: float
    per_attempt_ci95: tuple[float, float]
    attempts_mean: float | None
    attempts_median: float | None
    attempts_p90: int | None
    attempts_p95: int | None
    attempts_p99: int | None
    success_within_cap: float
    assumptions: list[dict]
    notes: list[str]


def simulate_repeat_until(
    gd: GameData,
    start: ItemState,
    action_id: str,
    target: Target,
    *,
    runs: int = 1000,
    max_attempts: int = 2000,
    seed: int = 1,
    params: dict | None = None,
) -> SimulationResult:
    """Apply `action_id` repeatedly to `start` until `target` is met (or the cap).

    'Repeat' means each attempt is applied to the *previous result* (e.g. spamming
    Chaos Orbs on the same rare). Per-attempt success probability is estimated
    over all attempts made and reported with a 95% Wilson interval."""
    params = params or {}
    rng = random.Random(seed)
    attempts_needed: list[int] = []
    total_attempts = 0
    total_hits = 0
    for _ in range(runs):
        item = start
        for k in range(1, max_attempts + 1):
            item = apply(gd, item, action_id, rng, **params)
            total_attempts += 1
            if target.met_by(gd, item):
                total_hits += 1
                attempts_needed.append(k)
                break
    attempts_needed.sort()
    info = ACTIONS[action_id]
    notes = ["Monte Carlo estimate, not an exact probability."]
    if info.status != "implemented_partially_verified":
        notes.append(f"Action status: {info.status}.")
    p = total_hits / total_attempts if total_attempts else 0.0
    return SimulationResult(
        action=action_id,
        runs=runs,
        max_attempts=max_attempts,
        seed=seed,
        successes=len(attempts_needed),
        per_attempt_probability=p,
        per_attempt_ci95=wilson_interval(total_hits, total_attempts),
        attempts_mean=statistics.fmean(attempts_needed) if attempts_needed else None,
        attempts_median=statistics.median(attempts_needed) if attempts_needed else None,
        attempts_p90=_percentile(attempts_needed, 0.90) if attempts_needed else None,
        attempts_p95=_percentile(attempts_needed, 0.95) if attempts_needed else None,
        attempts_p99=_percentile(attempts_needed, 0.99) if attempts_needed else None,
        success_within_cap=len(attempts_needed) / runs if runs else 0.0,
        assumptions=[{"name": a, **assumption(a)} for a in info.assumptions],
        notes=notes,
    )


__all__ = [
    "ModRequirement",
    "Target",
    "exact_next_mod_probability",
    "simulate_repeat_until",
    "wilson_interval",
    "InvalidAction",
]
