"""Fishing (SPEC_FLORA FL1): a worker beside a WATER voxel draws the shared oasis shoal into a FOOD
voxel; generalizes past the oasis-holder; lean under the Chill ice. Gate default off -> no-op
(battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, VoxelType, UnitType,
                           FISH_YIELD, FISH_MIN_STOCK, FISHING_ENABLED, SEASON_LENGTH)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)


def _worker(sim, colony):
    for u in colony.units:
        if u.unit_type == UnitType.WORKER:
            return u
    return colony.units[0]


def _setup_water(sim, x, y):
    """Place a WATER voxel and an adjacent AIR-surrounded worker cell; return (worker_pos, water_pos,
    deposit_pos). Clears the deposit cell to AIR so a catch can land."""
    z = sim.world.surface_z(x, y) + 1
    wpos = (x, y, z)                       # worker cell (AIR above ground)
    watpos = (x + 1, y, z)                 # water 6-adjacent to the worker
    sim.world.voxels[watpos] = VoxelType.WATER.value
    deposit = (x + 1, y, z + 1)            # first (0,0,1) deposit offset above the water
    sim.world.voxels[deposit] = VoxelType.AIR.value
    return wpos, watpos, deposit


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert FISHING_ENABLED is False, "FISHING_ENABLED must default False (battery byte-identical)"


def test_fishing_off_is_noop():
    if not HAVE:
        return _skip()
    sim = _sim(); sim.guppy_pop = 100.0
    colony = sim.colonies[0]; unit = _worker(sim, colony)
    wpos, _, _ = _setup_water(sim, 10, 10)
    unit.position = wpos
    assert sim._fish_step(unit, colony) is False, "gate off: fishing must be a no-op"
    assert sim.guppy_pop == 100.0, "gate off: the shoal must be untouched"


def test_worker_by_water_catches():
    if not HAVE:
        return _skip()
    prev = sandkings.FISHING_ENABLED; sandkings.FISHING_ENABLED = True
    try:
        sim = _sim(); sim.guppy_pop = 100.0
        sim.step_count = SEASON_LENGTH  # season 1 (Growth) — no Chill throttle
        colony = sim.colonies[0]; unit = _worker(sim, colony)
        wpos, _, deposit = _setup_water(sim, 10, 10)
        unit.position = wpos
        assert sim._fish_step(unit, colony) is True, "a worker by water must fish"
        assert sim.guppy_pop == 100.0 - FISH_YIELD, "fishing draws FISH_YIELD from the shared shoal"
        assert sim.world.voxels[deposit] == VoxelType.FOOD.value, "the catch surfaces as FOOD"
    finally:
        sandkings.FISHING_ENABLED = prev


def test_non_oasis_colony_can_fish():
    if not HAVE:
        return _skip()
    prev = sandkings.FISHING_ENABLED; sandkings.FISHING_ENABLED = True
    try:
        sim = _sim(); sim.guppy_pop = 100.0
        sim.step_count = SEASON_LENGTH
        colony = sim.colonies[0]; unit = _worker(sim, colony)
        wpos, _, deposit = _setup_water(sim, 3, 3)   # a corner, far from the oasis disc
        unit.position = wpos
        assert sim._fish_step(unit, colony) is True, "fishing keys off WATER, not the oasis disc"
        assert sim.world.voxels[deposit] == VoxelType.FOOD.value
    finally:
        sandkings.FISHING_ENABLED = prev


def test_no_fish_below_min_stock():
    if not HAVE:
        return _skip()
    prev = sandkings.FISHING_ENABLED; sandkings.FISHING_ENABLED = True
    try:
        sim = _sim(); sim.guppy_pop = FISH_MIN_STOCK  # at the floor -> shoal rebuilds, no catch
        sim.step_count = SEASON_LENGTH
        colony = sim.colonies[0]; unit = _worker(sim, colony)
        wpos, _, _ = _setup_water(sim, 12, 12)
        unit.position = wpos
        assert sim._fish_step(unit, colony) is False, "no fishing at/below FISH_MIN_STOCK"
        assert sim.guppy_pop == FISH_MIN_STOCK
    finally:
        sandkings.FISHING_ENABLED = prev


def test_chill_throttles_the_catch():
    if not HAVE:
        return _skip()
    prev = sandkings.FISHING_ENABLED; sandkings.FISHING_ENABLED = True
    try:
        sim = _sim()
        colony = sim.colonies[0]; unit = _worker(sim, colony)
        wpos, _, deposit = _setup_water(sim, 15, 15)
        unit.position = wpos

        def count_catches(season_step, n):
            sim.step_count = season_step
            catches = 0
            for _ in range(n):
                sim.guppy_pop = 100.0                        # keep the shoal stocked
                sim.world.voxels[deposit] = VoxelType.AIR.value
                sim._fish_step(unit, colony)
                if sim.world.voxels[deposit] == VoxelType.FOOD.value:
                    catches += 1
            return catches

        random.seed(0)
        growth = count_catches(SEASON_LENGTH, 40)             # season 1: every attempt lands
        chill = count_catches(3 * SEASON_LENGTH, 40)          # season 3: throttled under ice
        assert growth == 40, f"growth season should always catch, got {growth}"
        assert chill < growth, f"Chill must throttle the catch (got {chill} vs {growth})"
        assert chill <= 24, f"Chill catch rate should be ~25%, got {chill}/40"
    finally:
        sandkings.FISHING_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all fishing tests passed")
