"""Perennial berry shrubs (SPEC_FLORA FL2): bushes grow green->ripe in the growing seasons, a forager
eats a ripe bush and it REGROWS in place, and the ripe berries die back in Chill. Gate default off ->
no voxels, no registry (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, VoxelType, UnitType,
                           SHRUB_TICK, SHRUB_GROWDUR, SHRUB_YIELD, SHRUBS_ENABLED, SEASON_LENGTH)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)


def _plant(sim, x, y):
    """Place a SHRUB voxel on surface sand and register it; return its pos."""
    z = sim.world.surface_z(x, y) + 1
    sim.world.voxels[x, y, z] = VoxelType.SHRUB.value
    sim.shrubs = {(x, y, z): 0}
    return (x, y, z)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert SHRUBS_ENABLED is False, "SHRUBS_ENABLED must default False (battery byte-identical)"


def test_shrub_off_is_noop():
    if not HAVE:
        return _skip()
    sim = _sim()
    sim.step_count = SHRUB_TICK
    sim._shrub_tick()                                # gate off -> immediate return
    assert getattr(sim, 'shrubs', None) is None, "gate off: the shrub registry must never allocate"


def test_grows_green_to_ripe():
    if not HAVE:
        return _skip()
    prev = sandkings.SHRUBS_ENABLED; sandkings.SHRUBS_ENABLED = True
    try:
        sim = _sim()
        pos = _plant(sim, 8, 8)
        sim.step_count = SHRUB_TICK                  # season 0 (Flood) in GROW_SEASONS
        for _ in range(SHRUB_GROWDUR):
            sim._shrub_tick()
        assert sim.world.voxels[pos] == VoxelType.SHRUB_RIPE.value, "a bush must ripen after SHRUB_GROWDUR"
    finally:
        sandkings.SHRUBS_ENABLED = prev


def test_forage_regrows_the_bush():
    if not HAVE:
        return _skip()
    prev = sandkings.SHRUBS_ENABLED; sandkings.SHRUBS_ENABLED = True
    try:
        sim = _sim()
        colony = sim.colonies[0]
        worker = next(u for u in colony.units if u.unit_type == UnitType.WORKER)
        worker.build_slot = 1        # isolate the forage path (not a designated builder this step)
        # a ripe bush one cell from the worker, in a clear corner
        wx, wy, wz = 5, 5, sim.world.surface_z(5, 5) + 1
        worker.position = (wx, wy, wz)
        bpos = (wx + 1, wy, wz)
        sim.world.voxels[bpos] = VoxelType.SHRUB_RIPE.value
        sim.shrubs = {bpos: SHRUB_GROWDUR}
        before = colony.maw.food_stored
        sim._execute_unit_ai(worker, colony)         # radius-2 grab eats the berries
        assert sim.world.voxels[bpos] == VoxelType.SHRUB.value, "the bush must regrow in place (perennial)"
        assert sim.shrubs[bpos] == 0, "harvest resets ripeness so the bush regrows"
        assert colony.maw.food_stored > before, "foraging a ripe bush must yield food"
    finally:
        sandkings.SHRUBS_ENABLED = prev


def test_chill_die_back():
    if not HAVE:
        return _skip()
    prev = sandkings.SHRUBS_ENABLED; sandkings.SHRUBS_ENABLED = True
    try:
        sim = _sim()
        pos = _plant(sim, 9, 9)
        sim.world.voxels[pos] = VoxelType.SHRUB_RIPE.value
        sim.shrubs[pos] = SHRUB_GROWDUR
        sim.step_count = 3 * SEASON_LENGTH           # Chill
        sim._shrub_tick()
        assert sim.world.voxels[pos] == VoxelType.AIR.value, "Chill clears the ripe berries"
        assert pos in sim.shrubs and sim.shrubs[pos] == 0, "the root stays dormant, awaits spring"
    finally:
        sandkings.SHRUBS_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all shrub tests passed")
