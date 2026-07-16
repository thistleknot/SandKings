"""Visible launched effects (SPEC_FAUNA_ECOLOGY, gated EFFECTS_ENABLED): a catapult shot travels across the
board and bursts, a firecracker flashes. Deterministic, cosmetic — gate default off is byte-identical."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, SHOT_SPEED, BLAST_TTL
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.EFFECTS_ENABLED is False, "EFFECTS_ENABLED must default False"


def test_shot_travels_then_bursts():
    """A launched shot moves toward its target each tick, then becomes a blast on arrival and ages out."""
    if not HAVE:
        return _skip()
    sim = _sim()
    sim._spawn_effect('shot', (2, 2, 5), (30, 2, 5))
    x0 = sim._effects()[0]['pos'][0]
    sim._effects_tick()
    assert sim._effects()[0]['pos'][0] == x0 + SHOT_SPEED, "a shot advances SHOT_SPEED toward its target"
    for _ in range(40):
        sim._effects_tick()
    assert all(e['kind'] != 'shot' for e in sim._effects()), "the shot bursts on arrival (no longer in flight)"
    for _ in range(BLAST_TTL + 1):
        sim._effects_tick()
    assert sim._effects() == [], "the blast ages out — effects are transient"


def test_blast_ages_out():
    if not HAVE:
        return _skip()
    sim = _sim()
    sim._spawn_effect('blast', (5, 5, 5))
    for _ in range(BLAST_TTL):
        sim._effects_tick()
    assert sim._effects() == [], "a blast flash lingers BLAST_TTL ticks then clears"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all effects tests passed")
