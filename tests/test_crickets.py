"""Cricket swarm dynamics battery (SPEC_FOOD_WEB, Phase 1). Pins the pure terrestrial consumer-resource
model: bounded, persists on plant matter, BOOMS when dry (Dust), CRASHES in flood/frost, yields a catch
only above the floor. Plus the gate-off default/no-state guard and a gate-on in-sim liveness check."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

from sandkings import (cricket_dynamics, CRICKETS_ENABLED, CRICKET_CAP, CRICKET_SEED,
                       CRICKET_YIELD_MIN, CRICKET_TICK)


def _run(cricket, forage, dry, flood, frost, ticks):
    for _ in range(ticks):
        cricket, catch = cricket_dynamics(cricket, forage, dry, flood, frost)
    return cricket


def test_gate_default_off():
    assert CRICKETS_ENABLED is False, "CRICKETS_ENABLED must default False (battery byte-identical)"


def test_bounded_across_permutations():
    starts = [0, CRICKET_SEED, CRICKET_CAP, CRICKET_CAP * 2, 5, 1]
    for c0 in starts:
        for forage in (0.0, 0.5, 1.0):
            for dry in (False, True):
                for flood in (False, True):
                    for frost in (False, True):
                        c = c0
                        for _ in range(400):
                            c, catch = cricket_dynamics(c, forage, dry, flood, frost)
                            assert 0.0 <= c <= CRICKET_CAP + 1e-6, f"cricket OOB {c} (start {c0})"
                            assert c == c, "NaN in swarm"
                            assert catch >= 0


def test_persists_with_plant_matter():
    """A swarm with forage and no flood/frost settles to a POSITIVE equilibrium."""
    c = _run(CRICKET_SEED, 0.6, dry=False, flood=False, frost=False, ticks=500)
    assert c > 5.0, f"swarm collapsed with plant matter: {c:.2f}"


def test_dry_boom_beats_wet():
    """Crickets BOOM in the dry season — the dry equilibrium exceeds the non-dry one."""
    dry_eq = _run(CRICKET_SEED, 0.6, dry=True, flood=False, frost=False, ticks=500)
    wet_eq = _run(CRICKET_SEED, 0.6, dry=False, flood=False, frost=False, ticks=500)
    assert dry_eq > wet_eq, f"dry must boom the swarm: dry={dry_eq:.1f} wet={wet_eq:.1f}"


def test_flood_and_frost_crash_the_swarm():
    base = _run(CRICKET_SEED, 0.6, dry=True, flood=False, frost=False, ticks=300)
    flooded = _run(base, 0.6, dry=True, flood=True, frost=False, ticks=60)
    frozen = _run(base, 0.6, dry=True, flood=False, frost=True, ticks=60)
    assert flooded < base * 0.3, f"a flood must drown the swarm: {base:.1f}->{flooded:.1f}"
    assert frozen < base * 0.3, f"frost must kill the swarm: {base:.1f}->{frozen:.1f}"


def test_catch_only_above_floor():
    _, c_low = cricket_dynamics(CRICKET_YIELD_MIN - 5, 0.6, True, False, False)
    assert c_low == 0, "no catch below the yield floor"
    _, c_high = cricket_dynamics(CRICKET_CAP, 0.6, True, False, False)
    assert c_high > 0, "a thriving swarm must yield a catch"


def test_guppy_extra_food_lifts_breeding():
    """Phase 2 coupling: crickets/droppings washed in (extra_food) breed MORE guppies; 3-arg call
    is byte-identical to extra_food=0 (back-compat with the shipped guppy tests)."""
    from sandkings import guppy_dynamics
    g0, a0, w = 40.0, 30.0, 0.6                       # low algae so the supplement matters
    g_plain, _, _ = guppy_dynamics(g0, a0, w, extra_food=0.0)
    g_fed, _, _ = guppy_dynamics(g0, a0, w, extra_food=0.5)
    assert g_fed > g_plain, f"extra food must lift guppy breeding: {g_plain:.3f} vs {g_fed:.3f}"
    assert guppy_dynamics(g0, a0, w) == guppy_dynamics(g0, a0, w, extra_food=0.0), "3-arg back-compat"


def test_gate_off_no_state():
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, CRICKET_TICK as CT
    random.seed(0); np.random.seed(0)
    assert sandkings.CRICKETS_ENABLED is False
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
    for _ in range(CT * 2 + 1):
        sim.step()
    assert getattr(sim, 'cricket_pop', None) is None, "gate off: no swarm state should appear"


def test_gate_on_swarm_lives():
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, CRICKET_TICK as CT
    random.seed(1); np.random.seed(1)
    prev = sandkings.CRICKETS_ENABLED
    sandkings.CRICKETS_ENABLED = True
    try:
        sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
        for _ in range(CT * 25):
            sim.step()
        assert getattr(sim, 'cricket_pop', None) is not None and sim.cricket_pop > 0.0
    finally:
        sandkings.CRICKETS_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all cricket tests passed")
