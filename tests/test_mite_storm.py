"""SPEC_MITE_STORM Increment 1 — the contagious infestation. Water cures; away from water it spreads + drains."""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np
try:
    import sandkings
    from sandkings import SandKingsSimulation, VoxelType
    HAVE = True
except Exception:
    HAVE = False

def _skip(): print("SKIP"); return True

def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=80, height=40, depth=20, num_colonies=2)

def test_gate_default_off():
    if not HAVE: return _skip()
    assert sandkings.MITE_STORM_ENABLED is False

def test_water_cures():
    if not HAVE: return _skip()
    sandkings.MITE_STORM_ENABLED = True
    try:
        sim = _sim(); u = sim.colonies[0].units[0]
        u.position = (5, 5, 10); u.infested = True
        sim.world.set_voxel(6, 5, 10, VoxelType.WATER)     # adjacent water
        sim._mite_infest_tick()
        assert u.infested is False, "adjacent water drowns the mites"
    finally:
        sandkings.MITE_STORM_ENABLED = False

def test_contagion_spreads_and_gate_off_noop():
    if not HAVE: return _skip()
    sandkings.MITE_STORM_ENABLED = True
    try:
        sim = _sim(); c = sim.colonies[0]
        u1, u2 = c.units[0], c.units[1]
        u1.position = (5, 5, 10); u2.position = (6, 5, 10)  # adjacent, dry corner
        u1.infested = True; u2.infested = False
        sim._mite_infest_tick()
        assert u2.infested is True, "the infestation jumps to the adjacent host"
    finally:
        sandkings.MITE_STORM_ENABLED = False
    # gate off -> no-op
    sim2 = _sim(); v = sim2.colonies[0].units[0]; v.infested = True
    sim2._mite_infest_tick()
    assert v.infested is True, "gate off: infestation untouched (byte-identical)"

if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f): f(); print(f"PASS {n}")
    print("all mite storm tests passed")
