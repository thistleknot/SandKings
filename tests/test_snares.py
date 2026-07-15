"""Snares (SPEC_FOOD_WEB Phase 3): a WEB voxel near water passively catches guppies into FOOD; a WEB on
land catches crickets. Gate default off -> no-op (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, VoxelType, SNARE_YIELD, SNARE_TICK, SNARES_ENABLED
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert SNARES_ENABLED is False, "SNARES_ENABLED must default False (battery byte-identical)"


def test_snare_off_is_noop():
    if not HAVE:
        return _skip()
    sim = _sim()
    sim.guppy_pop = 100.0
    cx, cy = sim.world.width // 2, sim.world.height // 2
    z = sim.world.surface_z(cx, cy) + 1
    sim.world.voxels[cx, cy, z] = VoxelType.WEB.value
    sim.step_count = SNARE_TICK
    sim._snare_tick()                                # gate off -> returns immediately
    assert sim.guppy_pop == 100.0, "gate off: a web must NOT catch guppies"


def test_web_near_water_catches_guppies():
    if not HAVE:
        return _skip()
    prev = sandkings.SNARES_ENABLED
    sandkings.SNARES_ENABLED = True
    try:
        sim = _sim()
        sim.guppy_pop = 100.0
        cx, cy = sim.world.width // 2, sim.world.height // 2       # oasis centre = near water
        z = sim.world.surface_z(cx, cy) + 1
        sim.world.voxels[cx, cy, z] = VoxelType.WEB.value
        sim.step_count = SNARE_TICK
        sim._snare_tick()
        assert sim.guppy_pop == 100.0 - SNARE_YIELD, "a web by the water must catch guppies"
        # the catch surfaced as a FOOD voxel above the web
        assert sim.world.voxels[cx, cy, z + 1] == VoxelType.FOOD.value
    finally:
        sandkings.SNARES_ENABLED = prev


def test_web_on_land_catches_crickets():
    if not HAVE:
        return _skip()
    prev = sandkings.SNARES_ENABLED
    sandkings.SNARES_ENABLED = True
    try:
        sim = _sim()
        sim.cricket_pop = 80.0
        # a corner far from the oasis -> land, catches crickets not guppies
        x, y = 3, 3
        z = sim.world.surface_z(x, y) + 1
        sim.world.voxels[x, y, z] = VoxelType.WEB.value
        sim.step_count = SNARE_TICK
        sim._snare_tick()
        assert sim.cricket_pop == 80.0 - SNARE_YIELD, "a web on land must catch crickets"
    finally:
        sandkings.SNARES_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all snare tests passed")
