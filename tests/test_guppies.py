"""Guppy pond dynamics battery (SPEC_GUPPIES). Pins the pure consumer-resource model:
bounded, persists at healthy water, RECOVERS after a crash, declines under drought, and yields a
catch only above the floor. Plus the gate-off default guard. Pure function -> fast, no sim."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandkings import (guppy_dynamics, GUPPIES_ENABLED, GUPPY_CAP, ALGAE_CAP,
                       GUPPY_YIELD_MIN, GUPPY_SEED, ALGAE_SEED)


def _run(guppy, algae, water, ticks):
    for _ in range(ticks):
        guppy, algae, catch = guppy_dynamics(guppy, algae, water)
    return guppy, algae


def test_gate_default_off():
    assert GUPPIES_ENABLED is False, "GUPPIES_ENABLED must default False (battery byte-identical)"


def test_bounded_across_permutations():
    """Never escapes [0,cap] or goes NaN, from a battery of starting states over a long horizon."""
    states = [(0, 0), (GUPPY_SEED, ALGAE_SEED), (GUPPY_CAP, ALGAE_CAP),
              (GUPPY_CAP * 2, ALGAE_CAP * 2), (5, 0), (0, ALGAE_CAP), (1, 1)]
    waters = [0.2, 0.6, 1.0]
    for g0, a0 in states:
        for w in waters:
            g, a = g0, a0
            for _ in range(500):
                g, a, c = guppy_dynamics(g, a, w)
                assert 0.0 <= g <= GUPPY_CAP + 1e-6, f"guppy out of bounds: {g} (start {g0},{a0},w={w})"
                assert 0.0 <= a <= ALGAE_CAP + 1e-6, f"algae out of bounds: {a}"
                assert g == g and a == a, "NaN in pond"
                assert c >= 0


def test_persists_at_healthy_water():
    """A seeded pond at healthy water settles to a POSITIVE equilibrium (the ecosystem lives)."""
    g, a = _run(GUPPY_SEED, ALGAE_SEED, 0.8, 800)
    assert g > 5.0, f"pond collapsed at healthy water: guppy={g:.2f}"
    assert a > 5.0, f"algae collapsed: {a:.2f}"


def test_recovers_after_crash():
    """Crash the shoal to near-zero; with algae present it BREEDS back (replication works)."""
    g, a = _run(GUPPY_SEED, ALGAE_SEED, 0.8, 400)     # reach equilibrium
    equilibrium = g
    g2, a2 = _run(2.0, a, 0.8, 400)                    # crash guppies, keep algae, let recover
    assert g2 > 10.0, f"shoal failed to recover from crash: {g2:.2f}"
    assert abs(g2 - equilibrium) < equilibrium * 0.5, "recovery should approach the prior equilibrium"


def test_drought_thins_the_pond():
    """Lower water -> less algae -> a smaller pond than at healthy water."""
    g_wet, _ = _run(GUPPY_SEED, ALGAE_SEED, 1.0, 800)
    g_dry, _ = _run(GUPPY_SEED, ALGAE_SEED, 0.2, 800)
    assert g_dry < g_wet, f"drought should thin the pond: dry={g_dry:.2f} wet={g_wet:.2f}"


def test_catch_only_above_floor():
    """No harvest below the floor; a catch appears once the shoal is healthy."""
    _, _, c_low = guppy_dynamics(GUPPY_YIELD_MIN - 5, ALGAE_CAP, 0.8)
    assert c_low == 0, "no catch below the yield floor"
    _, _, c_high = guppy_dynamics(GUPPY_CAP, ALGAE_CAP, 0.8)
    assert c_high > 0, "a healthy shoal must yield a catch"


def test_gate_off_no_pond_state():
    """Gate off (default): the sim never seeds pond state — battery byte-identical."""
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, GUPPY_TICK as GT
    random.seed(0); np.random.seed(0)
    assert sandkings.GUPPIES_ENABLED is False
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
    for _ in range(GT * 2 + 1):
        sim.step()
    assert getattr(sim, 'guppy_pop', None) is None, "gate off: no pond state should appear"


def test_gate_on_pond_lives():
    """Gate on: the pond seeds from the get go and persists (guppy_pop>0, algae set), no crash."""
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, GUPPY_TICK as GT
    random.seed(1); np.random.seed(1)
    prev = sandkings.GUPPIES_ENABLED
    sandkings.GUPPIES_ENABLED = True
    try:
        sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
        for _ in range(GT * 30):
            sim.step()
        assert getattr(sim, 'guppy_pop', None) is not None and sim.guppy_pop > 0.0
        assert getattr(sim, 'algae', None) is not None
    finally:
        sandkings.GUPPIES_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all guppy tests passed")
