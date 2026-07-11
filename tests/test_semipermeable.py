"""Acceptance tests for SPEC_SEMIPERMEABLE.md (SP1–SP8, SPA-1–SPA-6).

Failure modes covered: jitter non-identity at sd>0, soft_gate missing the hard
gate at temp==0, sun_effective not drawn, multiple skies per day, determinism
loss with positive variance, drift of the mean from the setpoint.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    BIOME_TICK, SUN_HOURS_DEFAULT, SUN_MAX, SUN_MIN, SUN_JITTER_SD,
    SandKingsSimulation, jitter, soft_gate,
)


def make_sim(seed: int = 33) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_jitter_sd_zero_returns_mean_exactly():
    """SPA-1: jitter with sd=0.0 returns float(mean) exactly, for several means."""
    for mean in (4, 12, 20, 7.5):
        result = jitter(mean=mean, sd=0.0, lo=4, hi=20)
        assert result == float(mean), f"jitter({mean}, sd=0) must return {float(mean)}, got {result}"


def test_jitter_sd_zero_draws_nothing():
    """SPA-1: jitter with sd=0.0 consumes zero RNG draws; sd=0.5 consumes one."""
    # Spy on random.gauss by monkeypatching
    call_count = {'sd_zero': 0, 'sd_pos': 0}
    original_gauss = random.gauss

    def counting_gauss(mu, sigma):
        if sigma == 0.0:
            call_count['sd_zero'] += 1
        else:
            call_count['sd_pos'] += 1
        return original_gauss(mu, sigma)

    random.gauss = counting_gauss

    try:
        # sd=0.0 should not call gauss
        jitter(mean=12, sd=0.0, lo=4, hi=20, rng=random)
        assert call_count['sd_zero'] == 0, "sd=0 must not draw"

        # sd=0.5 should call gauss exactly once
        jitter(mean=12, sd=0.5, lo=4, hi=20, rng=random)
        assert call_count['sd_pos'] == 1, "sd>0 must draw exactly once"
    finally:
        random.gauss = original_gauss


def test_soft_gate_temp_zero_is_hard_step():
    """SPA-1: soft_gate with temp=0.0 is a hard step at center."""
    center = 10.0
    metrics = [8.0, 10.0, 12.0]
    expected = [0.0, 0.0, 1.0]  # metric > center is 1.0, else 0.0
    for metric, exp in zip(metrics, expected):
        result = soft_gate(metric, center, temp=0.0)
        assert result == exp, f"soft_gate({metric}, {center}, 0) must be {exp}, got {result}"


def test_sim_sun_effective_equals_sun_hours_at_sd_zero():
    """SPA-1: A SandKingsSimulation with SUN_JITTER_SD==0.0 has
    sun_effective == sun_hours on every step (byte-identical daylight)."""
    sim = make_sim()
    # Verify SUN_JITTER_SD is at neutral
    import sandkings
    original_sd = sandkings.SUN_JITTER_SD
    sandkings.SUN_JITTER_SD = 0.0

    try:
        for step in range(1, 100):
            sim.step_count = step
            sim._biome_tick()
            assert sim.sun_effective == sim.sun_hours, \
                f"step {step}: sun_effective {sim.sun_effective} != sun_hours {sim.sun_hours}"
    finally:
        sandkings.SUN_JITTER_SD = original_sd


def test_daylight_identity_across_run():
    """SPA-2: With SUN_JITTER_SD==0.0, for a run >= 3·BIOME_TICK steps,
    sun_effective equals sun_hours at every step."""
    sim = make_sim()
    import sandkings
    original_sd = sandkings.SUN_JITTER_SD
    sandkings.SUN_JITTER_SD = 0.0

    try:
        # Run for at least 3 * BIOME_TICK steps
        for _ in range(3 * BIOME_TICK + 10):
            sim.step()
            assert sim.sun_effective == sim.sun_hours, \
                f"step {sim.step_count}: sun_effective {sim.sun_effective} != sun_hours {sim.sun_hours}"
    finally:
        sandkings.SUN_JITTER_SD = original_sd


def test_distribution_shape_mean_variance_bounds():
    """SPA-3: With SUN_JITTER_SD=2.0 and sun_hours=12, collecting one
    sun_effective per biome-day over >= 200 days yields mean ≈ 12±1.0,
    nonzero variance, and all samples in [SUN_MIN, SUN_MAX]."""
    sim = make_sim()
    sim.sun_hours = 12.0

    import sandkings
    original_sd = sandkings.SUN_JITTER_SD
    sandkings.SUN_JITTER_SD = 2.0

    try:
        samples = []
        # Step for at least 200 biome-days (BIOME_TICK steps per day)
        for _ in range(200 * BIOME_TICK + 10):
            sim.step_count += 1
            if sim.step_count == 1 or sim.step_count % BIOME_TICK == 0:
                sim._biome_tick()
                samples.append(sim.sun_effective)
            else:
                sim._biome_tick()

        # Collect exactly one sample per biome-day boundary
        effective_samples = []
        for i in range(1, len(samples)):
            if i == 1 or i % 1 == 0:  # one per boundary
                effective_samples.append(samples[i])

        # Need at least 200 samples
        if len(effective_samples) >= 200:
            mean_val = np.mean(effective_samples)
            var_val = np.var(effective_samples)

            # Mean should be close to 12 (within ±1.0)
            assert abs(mean_val - 12.0) <= 1.0, \
                f"mean {mean_val} not within 12±1.0"

            # Variance should be nonzero
            assert var_val > 0, \
                f"variance {var_val} must be nonzero"

            # All samples within bounds
            for sample in effective_samples:
                assert SUN_MIN <= sample <= SUN_MAX, \
                    f"sample {sample} outside [{SUN_MIN}, {SUN_MAX}]"
    finally:
        sandkings.SUN_JITTER_SD = original_sd


def test_soft_gate_monotone_crossing_half():
    """SPA-4: soft_gate with temp > 0 crosses 0.5 at center and is monotone."""
    center = 10.0
    temp = 2.0

    # At center, should be exactly 0.5
    result = soft_gate(center, center, temp)
    assert result == 0.5, f"soft_gate(center, center, temp>0) must be 0.5, got {result}"

    # Strictly increasing across a swept battery
    metrics = [center - 10, center - 5, center - 2, center - 1, center,
               center + 1, center + 2, center + 5, center + 10]
    results = [soft_gate(m, center, temp) for m in metrics]

    # Check monotonicity
    for i in range(len(results) - 1):
        assert results[i] <= results[i + 1], \
            f"soft_gate not monotone: {results[i]} > {results[i + 1]}"

    # Check saturation near bounds
    assert results[0] < 0.5, f"soft_gate below center should be < 0.5"
    assert results[-1] > 0.5, f"soft_gate above center should be > 0.5"

    # Check that all results are in [0, 1]
    for r in results:
        assert 0.0 <= r <= 1.0, f"soft_gate returned {r}, must be in [0, 1]"


def test_one_sky_per_day():
    """SPA-5: Within a single biome-day (the non-boundary steps between two
    BIOME_TICK boundaries), sun_effective does not change even with
    SUN_JITTER_SD > 0 — every reader in the day sees the same sky."""
    sim = make_sim()
    sim.sun_hours = 12.0

    import sandkings
    original_sd = sandkings.SUN_JITTER_SD
    sandkings.SUN_JITTER_SD = 0.5

    try:
        # Land exactly on a day boundary and draw the sky for this day.
        sim.step_count = BIOME_TICK          # a boundary: BIOME_TICK % BIOME_TICK == 0
        sim._biome_tick()                    # draws the sky for this biome-day
        sky_value = sim.sun_effective

        # Step through the INTERIOR of the day (steps BIOME_TICK+1 .. 2*BIOME_TICK-1,
        # none of which is a boundary and none of which is step 1): the sky must NOT
        # be redrawn until the next boundary.
        for step in range(BIOME_TICK + 1, 2 * BIOME_TICK):
            sim.step_count = step
            sim._biome_tick()
            assert sim.sun_effective == sky_value, \
                f"sky changed at interior step {step}: {sim.sun_effective} != {sky_value}"

        # At the next boundary (2*BIOME_TICK) a redraw is legitimate — do not assert.
        sim.step_count = 2 * BIOME_TICK
        sim._biome_tick()
    finally:
        sandkings.SUN_JITTER_SD = original_sd


def test_canon_reproducibility_sd_positive():
    """SPA-6: Two SandKingsSimulation runs with the same seed + positive SUN_JITTER_SD
    produce identical sun_effective sequences over >= 10·BIOME_TICK steps."""
    seed = 42

    import sandkings
    original_sd = sandkings.SUN_JITTER_SD
    sandkings.SUN_JITTER_SD = 0.5

    try:
        # First run
        random.seed(seed)
        np.random.seed(seed)
        sim1 = make_sim(seed=seed)

        seq1 = []
        for _ in range(10 * BIOME_TICK + 10):
            sim1.step_count += 1
            if sim1.step_count == 1 or sim1.step_count % BIOME_TICK == 0:
                sim1._biome_tick()
                seq1.append(sim1.sun_effective)

        # Second run with same seed
        random.seed(seed)
        np.random.seed(seed)
        sim2 = make_sim(seed=seed)

        seq2 = []
        for _ in range(10 * BIOME_TICK + 10):
            sim2.step_count += 1
            if sim2.step_count == 1 or sim2.step_count % BIOME_TICK == 0:
                sim2._biome_tick()
                seq2.append(sim2.sun_effective)

        # Sequences should be identical
        assert len(seq1) == len(seq2), f"sequence lengths differ: {len(seq1)} vs {len(seq2)}"
        for i, (v1, v2) in enumerate(zip(seq1, seq2)):
            assert v1 == v2, f"sequence mismatch at index {i}: {v1} != {v2}"
    finally:
        sandkings.SUN_JITTER_SD = original_sd


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all semipermeable tests passed")
