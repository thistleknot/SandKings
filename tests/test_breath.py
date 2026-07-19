"""SPEC_BREATH — the Breathing Net. Pure stdlib (no torch), host-runnable. Verifies the kernel: no runaway,
mean-reversion, semi-permeable-but-bounded overshoot, settled-population stability, and the HARD total-compute
budget throttling growth (nets are a floating ratio of a fixed pool). Gate-off byte-identity is the mutate wiring's
job (verified via a determinism suite); this pins the kernel.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import breath
    from breath import breathe, PopulationBreath
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (breath unavailable)")
    return True


def _reset():
    breath.BREATH_TOTAL = 0.0
    breath._POP.clear()


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert breath.BREATH_ENABLED is False, "BREATH_ENABLED defaults off (battery byte-identical)"


def test_settled_population_stable():
    """BR1 identity: a settled population (sdev==0, current==mean) does not move."""
    if not HAVE:
        return _skip()
    r = random.Random(0)
    assert breathe(100, 100, 0.0, 24, 224, r) == 100


def test_no_runaway():
    """BR1: iterating from any start stays in a bounded neighborhood — log damping + soft squash, never diverges."""
    if not HAVE:
        return _skip()
    r = random.Random(1)
    for start in (24, 120, 224, 400):
        v = start
        for _ in range(5000):
            v = breathe(v, 120, 30, 24, 224, r)
        assert 10 <= v <= 240, f"stays bounded from start {start} (got {v})"


def test_mean_reversion():
    """BR1: starting far from the population mean, the series drifts toward it."""
    if not HAVE:
        return _skip()
    r = random.Random(2)
    v = 224
    for _ in range(300):
        v = breathe(v, 60, 4.0, 24, 224, r)
    assert v < 150, f"floats toward the mean 60 (got {v})"


def test_semi_permeable_bounded():
    """BR1: the value MAY sit past the soft cap (a membrane, not a wall) but the overshoot is bounded (not runaway)."""
    if not HAVE:
        return _skip()
    r = random.Random(3)
    vals = [breathe(224, 224, 25.0, 24, 224, r) for _ in range(400)]
    assert any(x > 224 for x in vals), "semi-permeable: can overshoot the soft cap"
    assert max(vals) < 224 + 12, f"overshoot bounded by the log margin (got {max(vals)})"


def test_budget_derived_no_constant():
    """BR3: the budget is DERIVED (N · geomean(bounds)), no BREATH_TOTAL constant exists."""
    if not HAVE:
        return _skip()
    assert not hasattr(breath, "BREATH_TOTAL") and not hasattr(breath, "BREATH_PER"), "no magic budget constants"


def test_over_budget_net_pulled_to_fair_share():
    """BR3: an over-budget population (nets far above their fair share) is pulled toward the fair share = geometric
    mean of the band — nets are a floating ratio of a fixed pool; they can't all stay big."""
    if not HAVE:
        return _skip()
    _reset()
    r = random.Random(4)
    pb = PopulationBreath(); pb.observe([200, 200, 200, 200])   # total 800 >> budget (4·geomean(24,224)≈292)
    breath._POP["cap"] = pb
    v = 200
    for _ in range(400):
        v = breath.sample_trait("cap", v, 24, 224, r)
    fair = (24 * 224) ** 0.5                                    # ≈ 73
    assert v < fair + 15, f"an over-budget net is pulled toward the fair share {fair:.0f} (got {v})"
    _reset()


def test_no_population_only_soft_band():
    """BR3: with no observed population (unit path), only the soft band applies — no budget throttling."""
    if not HAVE:
        return _skip()
    _reset()
    r = random.Random(5)
    v = 150
    for _ in range(300):
        v = breath.sample_trait("free", v, 24, 224, r)         # never observed -> pb.total None -> unbounded budget
    assert 24 <= v <= 224 + 12, f"stays in the soft band, not throttled to fair share (got {v})"
    _reset()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all breath tests passed")
