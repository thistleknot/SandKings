"""Acceptance tests for SPEC_SEMIPERMEABLE.md (SP1–SP8, SPA-1–SPA-6).

Failure modes covered: jitter non-identity at sd>0, soft_gate missing the hard
gate at temp==0, sun_effective not drawn, multiple skies per day, determinism
loss with positive variance, drift of the mean from the setpoint.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (
    BIOME_TICK, SUN_HOURS_DEFAULT, SUN_MAX, SUN_MIN, SUN_JITTER_SD,
    SUN_OSC_AMP, SUN_OSC_PERIOD, SUN_EMA_ALPHA, EPS_POWER,
    SandKingsSimulation, jitter, soft_gate, power_ratio,
    CAPTURE_CHANCE, CAPTURE_CENTER, CAPTURE_TEMP, CAPTURE_HEALTH,
    BARGAIN_TEMP, BARGAIN_MODE_NONE, BARGAIN_MODE_WAGE, BARGAIN_MODE_SUBJUGATE, BARGAIN_MODE_ANNIHILATE,
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


# SP9 Capture Membrane Tests (SPA-7 through SPA-11)

class RandomSpy:
    """Count random.random() draws; optionally force the returned roll."""
    def __init__(self, forced=None):
        self.count = 0
        self.forced = forced
        self.original = random.random
    def __call__(self):
        self.count += 1
        return self.original() if self.forced is None else self.forced


def _capture_probe(enforcers, defenders, capture_chance, capture_temp,
                   capture_center=0.5, forced_roll=None, seed=50):
    """Force one _try_capture call with controlled dominance counts + stance.

    Returns (result: bool, draw_count: int). Stubs _subjugate_stance -> True and
    _dominance_counts -> (enforcers, defenders); both the flat gate (via the
    delegating _local_dominance) and the soft gate then read those counts.
    """
    import sandkings
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sandkings.CAPTURE_CHANCE = capture_chance
    sandkings.CAPTURE_TEMP = capture_temp
    sandkings.CAPTURE_CENTER = capture_center
    # pick two distinct alive colonies + a unit from each
    alive = [c for c in sim.colonies if c.is_alive() and c.units]
    captor_colony, victim_colony = alive[0], alive[1]
    captor_unit = captor_colony.units[0]
    victim = victim_colony.units[0]
    sim._subjugate_stance = lambda cc, vc: True
    sim._dominance_counts = lambda cc, cu, v, vc: (enforcers, defenders)
    spy = RandomSpy(forced=forced_roll)
    old = random.random
    random.random = spy
    try:
        result = sim._try_capture(captor_colony, captor_unit, victim, victim_colony)
    finally:
        random.random = old
        sandkings.CAPTURE_CHANCE = 0.0
        sandkings.CAPTURE_TEMP = 0.0
        sandkings.CAPTURE_CENTER = 0.5
    return result, spy.count


def test_spa7_identity_and_rng_count():
    """SPA-7: IDENTITY + RNG-count (gating; keeps the 42-suite battery green).
    With CAPTURE_TEMP == 0.0, _try_capture's return AND draw count match the
    pre-SP9 flat path."""
    test_cases = [
        # (capture_chance, (E, D), forced_roll, expect_result, expect_draws)
        (0.0, (0, 0), None, False, 0),  # gate 1: CAPTURE_CHANCE <= 0
        (1.0, (0, 0), None, False, 0),  # hard wall, enforcers < 1
        (1.0, (1, 1), None, False, 0),  # hard wall, defenders > 0
        (1.0, (1, 0), 0.0, True, 1),   # past wall, roll < 1.0 => True
        (0.5, (1, 0), 0.99, False, 1), # past wall, roll >= 0.5 => False
    ]
    for capture_chance, (E, D), forced_roll, expect_result, expect_draws in test_cases:
        result, draw_count = _capture_probe(
            enforcers=E, defenders=D,
            capture_chance=capture_chance, capture_temp=0.0,
            forced_roll=forced_roll
        )
        assert result == expect_result, \
            f"SPA-7 fail: CAPTURE_CHANCE={capture_chance}, (E,D)=({E},{D}): expected result={expect_result}, got {result}"
        assert draw_count == expect_draws, \
            f"SPA-7 fail: CAPTURE_CHANCE={capture_chance}, (E,D)=({E},{D}): expected draws={expect_draws}, got {draw_count}"


def test_spa8_local_dominance_truth_table():
    """SPA-8: _local_dominance truth table UNCHANGED.
    For a matrix of (E, D) in {0,1,2} × {0,1,2}, assert
    _local_dominance(...) == (E >= 1 and D == 0)."""
    import sandkings
    random.seed(42)
    np.random.seed(42)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    alive = [c for c in sim.colonies if c.is_alive() and c.units]
    captor_colony, victim_colony = alive[0], alive[1]
    captor_unit = captor_colony.units[0]
    victim = victim_colony.units[0]

    for E in [0, 1, 2]:
        for D in [0, 1, 2]:
            expected = (E >= 1 and D == 0)
            sim._dominance_counts = lambda cc, cu, v, vc, e=E, d=D: (e, d)
            result = sim._local_dominance(captor_colony, captor_unit, victim, victim_colony)
            assert result == expected, \
                f"SPA-8 fail: (E,D)=({E},{D}): expected {expected}, got {result}"


def test_spa9_power_ratio_formula():
    """SPA-9: power_ratio formula and bounds.
    power_ratio(1,0)==1.0; power_ratio(0,0)==0.0; power_ratio(1,1)==0.5;
    power_ratio(3,1)==0.75; power_ratio(0,5)==0.0; monotone non-decreasing."""
    assert power_ratio(1, 0) == 1.0, "power_ratio(1,0) must be 1.0"
    assert power_ratio(0, 0) == 0.0, "power_ratio(0,0) must be 0.0"
    assert power_ratio(1, 1) == 0.5, "power_ratio(1,1) must be 0.5"
    assert power_ratio(3, 1) == 0.75, "power_ratio(3,1) must be 0.75"
    assert power_ratio(0, 5) == 0.0, "power_ratio(0,5) must be 0.0"

    # All results in [0,1]
    for E in range(0, 5):
        for D in range(0, 5):
            r = power_ratio(E, D)
            assert 0.0 <= r <= 1.0, f"power_ratio({E},{D}) = {r} out of bounds"

    # Monotone non-decreasing in enforcers with defenders fixed
    for D in range(0, 3):
        prev = power_ratio(0, D)
        for E in range(1, 5):
            curr = power_ratio(E, D)
            assert curr >= prev, \
                f"power_ratio not monotone: ({E-1},{D})={prev} > ({E},{D})={curr}"
            prev = curr


def test_spa10_soft_membrane():
    """SPA-10: SOFT MEMBRANE with CAPTURE_TEMP > 0.
    The hard wall is relaxed; captured case has p in (0,1); p monotonically rises
    with power_ratio."""
    # Probability shape: p(E, D) = CAPTURE_CHANCE * soft_gate(power_ratio(E, D), 0.5, 0.15)
    # temp is scale-matched to power_ratio's [0,1] domain: (1.0-0.5)/0.15 ~= 3.3, so the
    # logistic saturates near 0/1 at the extremes (a real S-curve). A sun-domain temp like
    # 2.0 would make the gate nearly flat (0.44..0.56) on a [0,1] metric.
    capture_chance = 1.0
    capture_temp = 0.15
    capture_center = 0.5

    def p(E, D):
        return capture_chance * soft_gate(power_ratio(E, D), capture_center, capture_temp)

    # Contested case (1,1) flat mode rejects but soft mode has p in (0,1)
    p_contested = p(1, 1)
    assert 0.0 < p_contested < 1.0, f"p(1,1) must be in (0,1), got {p_contested}"

    # Uncontested case (1,0) has p near 1.0
    p_uncontested = p(1, 0)
    # soft_gate(1.0, 0.5, 2.0) should be close to 1.0
    assert p_uncontested > 0.9, f"p(1,0) must be high (>0.9), got {p_uncontested}"

    # p rises monotonically across power_ratio battery
    battery = [(1, 3), (1, 1), (3, 1), (1, 0)]  # increasing power_ratio
    prev_p = None
    for E, D in battery:
        curr_p = p(E, D)
        if prev_p is not None:
            assert curr_p >= prev_p, \
                f"p not monotone: p({battery[battery.index((E,D))-1]})={prev_p} > p({E},{D})={curr_p}"
        prev_p = curr_p

    # Draw actually taken on the contested case with forced_roll=0.0
    result, draw_count = _capture_probe(
        enforcers=1, defenders=1,
        capture_chance=1.0, capture_temp=0.15,
        forced_roll=0.0
    )
    assert result is True, "SPA-10 contested (1,1) with forced_roll=0.0 must return True"
    assert draw_count == 1, f"SPA-10 contested must draw exactly once, got {draw_count}"

    # No captor case returns False with 0 draws
    result, draw_count = _capture_probe(
        enforcers=0, defenders=0,
        capture_chance=1.0, capture_temp=2.0
    )
    assert result is False, "SPA-10 no captor (0,0) must return False"
    assert draw_count == 0, f"SPA-10 no captor must draw zero times, got {draw_count}"


def test_spa11_canon_under_softness():
    """SPA-11: Canon reproducibility under softness.
    Two same-seed sims with CAPTURE_TEMP == 2.0, CAPTURE_CENTER == 0.5,
    CAPTURE_CHANCE bumped produce identical capture outcome sequences."""
    import sandkings
    original_capture_chance = sandkings.CAPTURE_CHANCE
    original_capture_temp = sandkings.CAPTURE_TEMP
    original_capture_center = sandkings.CAPTURE_CENTER

    sandkings.CAPTURE_CHANCE = 0.4
    sandkings.CAPTURE_TEMP = 2.0
    sandkings.CAPTURE_CENTER = 0.5

    try:
        seed = 99
        # First run
        random.seed(seed)
        np.random.seed(seed)
        sim1 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        # Enable subjugation stance on first colony for captures
        if sim1.colonies:
            sim1.colonies[0].subjugation_stance = True

        thralls1 = []
        for _ in range(50):
            sim1.step()
            for unit in sim1.colonies[0].units if sim1.colonies else []:
                if getattr(unit, 'laboring_for', -1) >= 0:
                    thralls1.append((unit.unit_id, unit.laboring_for))

        # Second run with same seed
        random.seed(seed)
        np.random.seed(seed)
        sim2 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        if sim2.colonies:
            sim2.colonies[0].subjugation_stance = True

        thralls2 = []
        for _ in range(50):
            sim2.step()
            for unit in sim2.colonies[0].units if sim2.colonies else []:
                if getattr(unit, 'laboring_for', -1) >= 0:
                    thralls2.append((unit.unit_id, unit.laboring_for))

        # Sequences should be identical
        assert thralls1 == thralls2, \
            f"Canon under softness failed: sequences differ\n  seq1: {thralls1}\n  seq2: {thralls2}"
    finally:
        sandkings.CAPTURE_CHANCE = original_capture_chance
        sandkings.CAPTURE_TEMP = original_capture_temp
        sandkings.CAPTURE_CENTER = original_capture_center


# SP10 Oscillator + EMA Observer Tests (SPA-12 through SPA-17)

def test_spa12_identity_oscillator_zero():
    """SPA-12: IDENTITY (gating; keeps the battery byte-identical).
    With SUN_OSC_AMP == 0.0 and SUN_JITTER_SD == 0.0, over a run >= 3·BIOME_TICK
    steps: sun_effective == sun_hours on every day (byte-identical to SP5).
    Under a random.gauss counting spy, the SP10 draw+EMA block adds zero gauss draws.
    sun_ema_mean converges to sun_hours."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_jitter_sd = sandkings.SUN_JITTER_SD

    sandkings.SUN_OSC_AMP = 0.0
    sandkings.SUN_JITTER_SD = 0.0

    try:
        # Spy on gauss draws
        gauss_count = {'count': 0}
        original_gauss = random.gauss

        def counting_gauss(mu, sigma):
            gauss_count['count'] += 1
            return original_gauss(mu, sigma)

        random.gauss = counting_gauss
        try:
            sim = make_sim()
            # Run for at least 3*BIOME_TICK steps, stepping through boundaries
            for step in range(1, 3 * BIOME_TICK + 10):
                sim.step_count = step
                sim._biome_tick()
                assert sim.sun_effective == sim.sun_hours, \
                    f"step {step}: sun_effective {sim.sun_effective} != sun_hours {sim.sun_hours}"

            # Assert zero gauss draws
            assert gauss_count['count'] == 0, \
                f"SPA-12: expected 0 gauss draws, got {gauss_count['count']}"

            # Assert sun_ema_mean converges to sun_hours
            assert abs(sim.sun_ema_mean - sim.sun_hours) < 1e-9, \
                f"SPA-12: sun_ema_mean {sim.sun_ema_mean} not converged to sun_hours {sim.sun_hours}"
        finally:
            random.gauss = original_gauss
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_JITTER_SD = original_jitter_sd


def test_spa13_oscillator_mean_only():
    """SPA-13: OSCILLATOR (mean-only).
    With SUN_OSC_AMP = 3.0, SUN_JITTER_SD = 0.0, SUN_OSC_PERIOD = 5 * BIOME_TICK,
    sun_hours = 12: sample one sun_effective per biome-day over >= one full period.
    Assert for every sample abs(sun_effective - (12 + 3.0*math.sin(...))) < 1e-9.
    Assert peak-to-peak span ~= 2*3.0 == 6.0 (tolerance ±0.2)."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_osc_period = sandkings.SUN_OSC_PERIOD
    original_jitter_sd = sandkings.SUN_JITTER_SD

    sandkings.SUN_OSC_AMP = 3.0
    sandkings.SUN_OSC_PERIOD = 5 * BIOME_TICK
    sandkings.SUN_JITTER_SD = 0.0

    try:
        sim = make_sim()
        sim.sun_hours = 12.0

        samples = []
        # Sample over at least one full period: SUN_OSC_PERIOD days
        for day in range(sandkings.SUN_OSC_PERIOD + 1):
            sim.step_count = day * BIOME_TICK if day > 0 else 1
            sim._biome_tick()
            # Expected value for this day
            expected = 12.0 + 3.0 * math.sin(2.0 * math.pi * day / sandkings.SUN_OSC_PERIOD)
            actual = sim.sun_effective
            assert abs(actual - expected) < 1e-9, \
                f"SPA-13: day {day} expected {expected}, got {actual}"
            samples.append(actual)

        # Assert peak-to-peak is approximately 6.0 (±0.2)
        peak_to_peak = max(samples) - min(samples)
        assert abs(peak_to_peak - 6.0) <= 0.2, \
            f"SPA-13: peak-to-peak {peak_to_peak} not within 6.0±0.2"
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_OSC_PERIOD = original_osc_period
        sandkings.SUN_JITTER_SD = original_jitter_sd


def test_spa14_ema_tracks_keeper_step():
    """SPA-14: EMA tracks a keeper step.
    SUN_OSC_AMP = 0.0. Start sun_hours = 12, SUN_JITTER_SD = 0.0; step to steady
    state so sun_ema_mean ~= 12. Then keeper_set_sun(18) and sample sun_ema_mean
    once per day. Assert monotonically increasing, each > 12 and <= 18, converges
    toward 18. Separately: run to steady state with SUN_JITTER_SD = 0.0 (sun_ema_sd ~= 0)
    versus SUN_JITTER_SD = 2.0 (sun_ema_sd > 0) and assert positive-SD is strictly greater."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_jitter_sd = sandkings.SUN_JITTER_SD

    # Test 1: EMA tracks a keeper step (monotonic, no overshoot, convergence)
    sandkings.SUN_OSC_AMP = 0.0
    sandkings.SUN_JITTER_SD = 0.0

    try:
        sim = make_sim()
        sim.sun_hours = 12.0

        # Step to steady state
        for _ in range(10 * BIOME_TICK):
            sim.step_count += 1
            sim._biome_tick()

        # At steady state, should be at 12
        assert abs(sim.sun_ema_mean - 12.0) < 0.1, \
            f"SPA-14: not at steady state, sun_ema_mean = {sim.sun_ema_mean}"

        # Now step sun to 18
        sim.keeper_set_sun(18.0)
        ema_sequence = []

        # Step and collect sun_ema_mean after each day boundary
        for _ in range(20 * BIOME_TICK):
            sim.step_count += 1
            if sim.step_count % BIOME_TICK == 0:
                sim._biome_tick()
                ema_sequence.append(sim.sun_ema_mean)
            else:
                sim._biome_tick()

        # Assert monotonically increasing
        for i in range(1, len(ema_sequence)):
            assert ema_sequence[i] >= ema_sequence[i - 1], \
                f"SPA-14: EMA not monotone at index {i}: {ema_sequence[i - 1]} > {ema_sequence[i]}"

        # Assert all in (12, 18]
        for val in ema_sequence:
            assert 12.0 < val <= 18.0, \
                f"SPA-14: EMA value {val} outside (12, 18]"

        # Assert converges toward 18
        assert abs(ema_sequence[-1] - 18.0) < 0.5, \
            f"SPA-14: final EMA {ema_sequence[-1]} not close to 18"

        # Test 2: Compare sd with and without jitter
        sandkings.SUN_JITTER_SD = 0.0
        sim2a = make_sim()
        sim2a.sun_hours = 12.0
        for _ in range(20 * BIOME_TICK):
            sim2a.step_count += 1
            sim2a._biome_tick()
        sd_no_jitter = sim2a.sun_ema_sd

        sandkings.SUN_JITTER_SD = 2.0
        sim2b = make_sim()
        sim2b.sun_hours = 12.0
        for _ in range(20 * BIOME_TICK):
            sim2b.step_count += 1
            sim2b._biome_tick()
        sd_with_jitter = sim2b.sun_ema_sd

        assert sd_with_jitter > sd_no_jitter, \
            f"SPA-14: sd_with_jitter {sd_with_jitter} not > sd_no_jitter {sd_no_jitter}"
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_JITTER_SD = original_jitter_sd


def test_spa15_z_normalization():
    """SPA-15: z / normalization.
    SUN_OSC_AMP = 0.0, SUN_JITTER_SD = 2.0, sun_hours = 12. Step many days;
    collect sim._sun_z(). Assert every value is finite, long-run mean ~= 0
    (tolerance ±0.3 over >= 200 days). Also assert _sun_z() is computable
    at init and equals 0.0 (sun_effective == sun_ema_mean)."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_jitter_sd = sandkings.SUN_JITTER_SD

    sandkings.SUN_OSC_AMP = 0.0
    sandkings.SUN_JITTER_SD = 2.0

    try:
        sim = make_sim()
        sim.sun_hours = 12.0

        # Assert _sun_z() at init is 0.0 (sun_effective == sun_ema_mean)
        z_init = sim._sun_z()
        assert z_init == 0.0, \
            f"SPA-15: _sun_z() at init must be 0.0, got {z_init}"

        # Step many days and collect z
        z_samples = []
        for _ in range(200 * BIOME_TICK + 10):
            sim.step_count += 1
            sim._biome_tick()
            z_samples.append(sim._sun_z())

        # Assert all finite
        for z in z_samples:
            assert math.isfinite(z), \
                f"SPA-15: _sun_z() returned non-finite value {z}"

        # Assert long-run mean ~= 0 (±0.3)
        z_mean = np.mean(z_samples)
        assert abs(z_mean) <= 0.3, \
            f"SPA-15: long-run z mean {z_mean} not within ±0.3"
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_JITTER_SD = original_jitter_sd


def test_spa16_acyclic_daylight_independent_water():
    """SPA-16: ACYCLIC (daylight ⊥ water).
    SUN_OSC_AMP = 3.0, SUN_JITTER_SD = 0.0 (so sun_effective is a PURE function
    of step_count and sun_hours — NO RNG is consumed). Build two sims with SAME seed
    but very different starting water: sim_a.water_level = 0.05 and
    sim_b.water_level = 0.95. Step both the same number of days, collecting
    sun_effective sequence. Assert the two sequences are BYTE-IDENTICAL."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_jitter_sd = sandkings.SUN_JITTER_SD

    sandkings.SUN_OSC_AMP = 3.0
    sandkings.SUN_JITTER_SD = 0.0

    try:
        seed = 77

        # Sim A: water_level = 0.05
        random.seed(seed)
        np.random.seed(seed)
        sim_a = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        sim_a.water_level = 0.05
        sim_a.water_target = 0.05

        seq_a = []
        for _ in range(100 * BIOME_TICK + 10):
            sim_a.step_count += 1
            if sim_a.step_count == 1 or sim_a.step_count % BIOME_TICK == 0:
                sim_a._biome_tick()
                seq_a.append(sim_a.sun_effective)

        # Sim B: water_level = 0.95
        random.seed(seed)
        np.random.seed(seed)
        sim_b = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        sim_b.water_level = 0.95
        sim_b.water_target = 0.95

        seq_b = []
        for _ in range(100 * BIOME_TICK + 10):
            sim_b.step_count += 1
            if sim_b.step_count == 1 or sim_b.step_count % BIOME_TICK == 0:
                sim_b._biome_tick()
                seq_b.append(sim_b.sun_effective)

        # Assert sequences are byte-identical
        assert len(seq_a) == len(seq_b), \
            f"SPA-16: sequence lengths differ: {len(seq_a)} vs {len(seq_b)}"
        for i, (a, b) in enumerate(zip(seq_a, seq_b)):
            assert a == b, \
                f"SPA-16: sequence mismatch at index {i}: {a} != {b}"
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_JITTER_SD = original_jitter_sd


def test_spa17_canon_under_dynamism():
    """SPA-17: CANON under dynamism.
    SUN_OSC_AMP = 3.0, SUN_JITTER_SD = 1.0, SUN_OSC_PERIOD default.
    Two runs, each preceded by SAME random.seed(s); np.random.seed(s),
    sample one sun_effective per biome-day over >= 10·BIOME_TICK steps.
    Assert the two sequences are IDENTICAL."""
    import sandkings
    original_osc_amp = sandkings.SUN_OSC_AMP
    original_jitter_sd = sandkings.SUN_JITTER_SD

    sandkings.SUN_OSC_AMP = 3.0
    sandkings.SUN_JITTER_SD = 1.0

    try:
        seed = 88

        # First run
        random.seed(seed)
        np.random.seed(seed)
        sim1 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)

        seq1 = []
        for _ in range(10 * BIOME_TICK + 10):
            sim1.step_count += 1
            if sim1.step_count == 1 or sim1.step_count % BIOME_TICK == 0:
                sim1._biome_tick()
                seq1.append(sim1.sun_effective)

        # Second run with same seed
        random.seed(seed)
        np.random.seed(seed)
        sim2 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)

        seq2 = []
        for _ in range(10 * BIOME_TICK + 10):
            sim2.step_count += 1
            if sim2.step_count == 1 or sim2.step_count % BIOME_TICK == 0:
                sim2._biome_tick()
                seq2.append(sim2.sun_effective)

        # Sequences should be identical
        assert len(seq1) == len(seq2), \
            f"SPA-17: sequence lengths differ: {len(seq1)} vs {len(seq2)}"
        for i, (v1, v2) in enumerate(zip(seq1, seq2)):
            assert v1 == v2, \
                f"SPA-17: sequence mismatch at index {i}: {v1} != {v2}"
    finally:
        sandkings.SUN_OSC_AMP = original_osc_amp
        sandkings.SUN_JITTER_SD = original_jitter_sd


# SP11 Bargain-Mode Membrane Tests (SPA-18 through SPA-21)

def _bargain_probe(ev_wage, ev_brute, ev_destroy, temp, seed=50, forced_roll=None):
    """Force one _bargain_pair_mode call with controlled EVs + temperature.

    Returns (mode: str, draw_count: int). Stubs the three _bargain_ev_* methods to
    return fixed EVs; strong/weak still resolves via composite_power on two real
    alive colonies (their actual power is irrelevant — the EVs are stubbed).
    Sets/restores sandkings.BARGAIN_TEMP in a finally.
    """
    import sandkings
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sandkings.BARGAIN_TEMP = temp
    alive = [c for c in sim.colonies if c.is_alive() and c.units]
    a, b = alive[0], alive[1]
    sim._bargain_ev_wage    = lambda s, w: ev_wage
    sim._bargain_ev_brute   = lambda s, w: ev_brute
    sim._bargain_ev_destroy = lambda s, w: ev_destroy
    spy = RandomSpy(forced=forced_roll)
    old = random.random
    random.random = spy
    try:
        mode = sim._bargain_pair_mode(a, b)
    finally:
        random.random = old
        sandkings.BARGAIN_TEMP = 0.0
    return mode, spy.count


def test_spa18_identity_and_zero_rng():
    """SPA-18 — IDENTITY + ZERO RNG (gating; keeps the battery byte-identical).
    With BARGAIN_TEMP == 0.0, _bargain_pair_mode's return AND draw count match
    the pre-SP11 hard argmax. Compare against a LOCAL reference _argmax_mode(ew, eb, ed)
    that reproduces the exact pre-SP11 >=chain, and assert both mode == _argmax_mode(...)
    AND draw_count == 0 for every row."""
    def _argmax_mode(ew, eb, ed):
        """Pre-SP11 hard argmax reference implementation."""
        best = max(ew, eb, ed)
        if best <= 0.0:
            return BARGAIN_MODE_NONE
        if ew >= eb and ew >= ed:
            return BARGAIN_MODE_WAGE
        if eb >= ed:
            return BARGAIN_MODE_SUBJUGATE
        return BARGAIN_MODE_ANNIHILATE

    test_cases = [
        (10, 1, 1),      # clear WAGE
        (1, 10, 1),      # clear SUBJUGATE
        (1, 1, 10),      # clear ANNIHILATE
        (0.0, -1.0, -2.0),  # best<=0 guard
        (-1.0, -2.0, -3.0),  # best<=0 guard
        (5, 5, 5),       # three-way tie -> WAGE
        (1, 5, 5),       # tie e_brute==e_destroy -> SUBJUGATE
        (5, 5, 1),       # tie e_wage==e_brute -> WAGE
        (1, 5, 3),       # e_brute strict max
    ]

    for ev_wage, ev_brute, ev_destroy in test_cases:
        expected_mode = _argmax_mode(ev_wage, ev_brute, ev_destroy)
        mode, draw_count = _bargain_probe(ev_wage, ev_brute, ev_destroy, temp=0.0)
        assert mode == expected_mode, \
            f"SPA-18 fail: ({ev_wage},{ev_brute},{ev_destroy}) expected {expected_mode}, got {mode}"
        assert draw_count == 0, \
            f"SPA-18 fail: ({ev_wage},{ev_brute},{ev_destroy}) expected 0 draws, got {draw_count}"


def test_spa19_softmax_shape():
    """SPA-19 — SOFTMAX SHAPE (temp>0).
    With BARGAIN_TEMP > 0, sample many times and assert:
    - Equal EVs (5,5,5) -> ~uniform (each ~1/3)
    - Approximates softmax for (2,1,0) -> softmax ~(0.665, 0.245, 0.090)
    - Dominant EV (10,0,0) -> >0.95 for WAGE."""
    import sandkings
    original_temp = sandkings.BARGAIN_TEMP

    try:
        # Test 1: Equal EVs -> ~uniform
        sandkings.BARGAIN_TEMP = 1.0
        random.seed(50)
        np.random.seed(50)
        sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        alive = [c for c in sim.colonies if c.is_alive() and c.units]
        a, b = alive[0], alive[1]
        sim._bargain_ev_wage    = lambda s, w: 5.0
        sim._bargain_ev_brute   = lambda s, w: 5.0
        sim._bargain_ev_destroy = lambda s, w: 5.0

        counts = {BARGAIN_MODE_WAGE: 0, BARGAIN_MODE_SUBJUGATE: 0, BARGAIN_MODE_ANNIHILATE: 0}
        for _ in range(3000):
            mode = sim._bargain_pair_mode(a, b)
            counts[mode] += 1

        total = sum(counts.values())
        freqs = {k: counts[k] / total for k in counts}
        # Each should be ~1/3 (tolerance ±0.05)
        for mode, freq in freqs.items():
            assert abs(freq - 1.0/3) < 0.05, \
                f"SPA-19 equal EVs: {mode} freq {freq} not ~1/3"

        # Test 2: Dominant EV -> near-deterministic
        sandkings.BARGAIN_TEMP = 0.5
        random.seed(51)
        np.random.seed(51)
        sim2 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        alive2 = [c for c in sim2.colonies if c.is_alive() and c.units]
        a2, b2 = alive2[0], alive2[1]
        sim2._bargain_ev_wage    = lambda s, w: 10.0
        sim2._bargain_ev_brute   = lambda s, w: 0.0
        sim2._bargain_ev_destroy = lambda s, w: 0.0

        wage_count = 0
        for _ in range(200):
            mode = sim2._bargain_pair_mode(a2, b2)
            if mode == BARGAIN_MODE_WAGE:
                wage_count += 1

        wage_freq = wage_count / 200
        assert wage_freq > 0.95, \
            f"SPA-19 dominant EV: WAGE freq {wage_freq} not > 0.95"

    finally:
        sandkings.BARGAIN_TEMP = original_temp


def test_spa20_one_draw_zero_on_none():
    """SPA-20 — ONE DRAW / ZERO ON NONE.
    With BARGAIN_TEMP > 0:
    - (5,5,5) at temp=1.0 -> draw_count == 1
    - (0,-1,-2) at temp=1.0 -> NONE and draw_count == 0 (best<=0 guard)
    - (10,1,1) at temp=0.0 -> draw_count == 0 (identity path)"""
    # Test 1: soft path draws exactly one
    mode, draw_count = _bargain_probe(5, 5, 5, temp=1.0)
    assert draw_count == 1, \
        f"SPA-20 soft path (5,5,5): expected 1 draw, got {draw_count}"

    # Test 2: NONE guard (best<=0) draws zero
    mode, draw_count = _bargain_probe(0.0, -1.0, -2.0, temp=1.0)
    assert mode == BARGAIN_MODE_NONE, \
        f"SPA-20 NONE guard: expected NONE, got {mode}"
    assert draw_count == 0, \
        f"SPA-20 NONE guard: expected 0 draws, got {draw_count}"

    # Test 3: identity path draws zero
    mode, draw_count = _bargain_probe(10, 1, 1, temp=0.0)
    assert draw_count == 0, \
        f"SPA-20 identity path (10,1,1): expected 0 draws, got {draw_count}"


def test_spa21_canon_under_softness():
    """SPA-21 — CANON under softness.
    Two probe loops, each preceded by SAME random.seed(s); np.random.seed(s),
    BARGAIN_TEMP set to same > 0 value, stubbed EVs near-uniform (e.g. (3,2,1)),
    collect sequence of sampled modes over >= 200 calls; assert the two sequences
    are IDENTICAL."""
    import sandkings
    original_temp = sandkings.BARGAIN_TEMP

    try:
        sandkings.BARGAIN_TEMP = 1.0
        seed = 123

        # First loop
        random.seed(seed)
        np.random.seed(seed)
        sim1 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        alive1 = [c for c in sim1.colonies if c.is_alive() and c.units]
        a1, b1 = alive1[0], alive1[1]
        sim1._bargain_ev_wage    = lambda s, w: 3.0
        sim1._bargain_ev_brute   = lambda s, w: 2.0
        sim1._bargain_ev_destroy = lambda s, w: 1.0

        seq1 = []
        for _ in range(200):
            mode = sim1._bargain_pair_mode(a1, b1)
            seq1.append(mode)

        # Second loop with same seed
        random.seed(seed)
        np.random.seed(seed)
        sim2 = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
        alive2 = [c for c in sim2.colonies if c.is_alive() and c.units]
        a2, b2 = alive2[0], alive2[1]
        sim2._bargain_ev_wage    = lambda s, w: 3.0
        sim2._bargain_ev_brute   = lambda s, w: 2.0
        sim2._bargain_ev_destroy = lambda s, w: 1.0

        seq2 = []
        for _ in range(200):
            mode = sim2._bargain_pair_mode(a2, b2)
            seq2.append(mode)

        # Sequences should be identical
        assert len(seq1) == len(seq2), \
            f"SPA-21: sequence lengths differ: {len(seq1)} vs {len(seq2)}"
        for i, (m1, m2) in enumerate(zip(seq1, seq2)):
            assert m1 == m2, \
                f"SPA-21: sequence mismatch at index {i}: {m1} != {m2}"
    finally:
        sandkings.BARGAIN_TEMP = original_temp


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all semipermeable tests passed")
