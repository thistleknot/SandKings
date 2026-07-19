"""SPEC_BREATH — the Breathing Net. Evolvable neural capacity (brain_hidden, read_reach) as a FLOATING (mean, sdev)
quantity held in a SEMI-PERMEABLE range, drifting in LOG proportions so it can't run away, ANNEALED by the existing
GA. Pure numpy/stdlib (no torch) so it loads and unit-tests anywhere.

This module only shapes how the *evolvable* genes MUTATE — it never touches the frozen Kanerva SDM / GRU (design
law); a width change is absorbed by EV4 `graft_into`. Gated: `BREATH_ENABLED` default False ⇒ `ColonyGenome.mutate`
runs the exact pre-Breath hard-clamp drift ⇒ battery byte-identical.
"""
import math
import random as _r
from typing import Dict, Optional

BREATH_ENABLED = False        # gate; entrypoint flips baseline-on (opt-out --no-breath). Default off = byte-identical.
BREATH_MEAN_PULL = 0.2        # strength of mean-reversion toward the population mean
BREATH_SOFT_MARGIN = 0.5      # log-scaled coefficient of the semi-permeable overshoot past the per-colony band
                              # (the HARD limit is the shared compute budget, DERIVED below — not this soft wall)


def _soft_bound(v: float, lo: float, hi: float, margin: float) -> float:
    """Semi-permeable membrane (NOT a hard clamp): inside [lo,hi] pass through; beyond, tanh-squash the overshoot
    into a log-scaled margin so a value MAY sit a little past the band but never far."""
    span = max(hi - lo, 1.0)
    m = max(1.0, margin * math.log2(max(span, 2.0)))
    if v > hi:
        return hi + m * math.tanh((v - hi) / m)
    if v < lo:
        return lo - m * math.tanh((lo - v) / m)
    return v


def breathe(current: float, mean: float, sdev: float, soft_lo: float, soft_hi: float, rng=_r) -> int:
    """SPEC_BREATH BR1: propose the next capacity. (1) float toward the population mean; (2) log-damp the step so big
    values move slowly and never blow up; (3) semi-permeable soft bound. Deterministic given `rng`; one gauss draw.
    Identity: a settled population (sdev==0 and current==mean) returns mean."""
    cur = max(1.0, float(current))
    drift = BREATH_MEAN_PULL * (float(mean) - cur) + rng.gauss(0.0, max(0.0, float(sdev)))
    step = drift / math.log2(max(cur, 2.0))                     # log-damped
    return int(round(_soft_bound(cur + step, float(soft_lo), float(soft_hi), BREATH_SOFT_MARGIN)))


class PopulationBreath:
    """SPEC_BREATH BR2: a rolling EMA of a trait's (mean, sdev) across the living colonies — the 'quasi-static mean
    and sdev' the population maintains. The band floats with the survivors; annealing does the culling."""

    def __init__(self, alpha: float = 0.9):
        self.alpha = alpha
        self.mean: Optional[float] = None
        self.var: float = 0.0
        self.total: Optional[float] = None      # EMA of the SUM across colonies (the used compute)

    def observe(self, values) -> None:
        vals = [float(v) for v in values]
        if not vals:
            return
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / len(vals) if len(vals) > 1 else 0.0
        tot = sum(vals)
        if self.mean is None:
            self.mean, self.var, self.total = m, v, tot
        else:
            self.mean = self.alpha * self.mean + (1 - self.alpha) * m
            self.var = self.alpha * self.var + (1 - self.alpha) * v
            self.total = self.alpha * self.total + (1 - self.alpha) * tot

    def sample(self, current, soft_lo, soft_hi, rng=_r) -> int:
        mean = self.mean if self.mean is not None else float(current)
        return breathe(current, mean, self.var ** 0.5, soft_lo, soft_hi, rng)


_POP: Dict[str, PopulationBreath] = {}


def observe_population(name: str, values) -> None:
    """Update the floating (mean, sdev) for a named trait across the living colonies (gated caller)."""
    _POP.setdefault(name, PopulationBreath()).observe(values)


def sample_trait(name: str, current, soft_lo, soft_hi, rng=_r) -> int:
    """SPEC_BREATH BR3: breathe one mutation of a named trait, throttled by the shared compute budget — DERIVED, no
    magic constant: total budget = N · geometric_mean(soft_lo, soft_hi) (the log-center of the trait's own band), so
    the fair share is the natural midpoint of the bounds already in the code. A colony grows above its fair share
    only by a LOG LAW of the ABSOLUTE headroom the others leave — nets are a floating ratio of a fixed pool: when the
    total is used up, growth stops and only annealing (a rival shrinking/dying) frees room. No observed population
    (`pb.total is None`, unit tests) ⇒ only the soft band applies."""
    pb = _POP.setdefault(name, PopulationBreath())
    eff_hi = float(soft_hi)
    if pb.total and pb.mean and pb.mean > 0:
        n = max(1.0, pb.total / pb.mean)                       # ~ number of colonies sharing the pool
        fair = (float(soft_lo) * float(soft_hi)) ** 0.5        # fair share = geometric mean of THIS trait's bounds
        others = max(0.0, pb.total - pb.mean)                  # sum of the OTHER colonies (this one ≈ the mean)
        room = max(0.0, n * fair - others)                     # ABSOLUTE headroom the budget (N·fair) leaves this one
        eff_hi = fair + math.log2(1.0 + max(0.0, room - fair)) # LOG LAW: grow above the fair share only log-of-slack
        eff_hi = max(float(soft_lo), min(float(soft_hi), eff_hi))
    return pb.sample(current, soft_lo, eff_hi, rng)
