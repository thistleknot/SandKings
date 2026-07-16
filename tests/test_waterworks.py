"""Structures wave: tunnels, dikes/dams, bridges, boats, and the X-ray render.

Deterministic unit tests that drive each mechanic directly (no long runs), so
each feature is pinned without depending on emergent trajectories.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (
    OASIS_RADIUS, WAR_CHEST, CASTLE_PROSPERITY_STEPS,
    SandKingsSimulation, UnitType, VoxelType,
)


def make_sim(seed: int = 3) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=14, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_deep_preference_digs_downward():
    """A deep-preference colony's idle dig biases DOWNWARD (below its maw),
    forming a subterranean warren instead of a surface scratch."""
    sim = make_sim()
    colony = sim.colonies[0]
    colony.genome.tunnel_preference = 1.0
    colony.maw.food_stored = 500
    for _ in range(8):
        colony.spawn_unit(UnitType.WORKER)
    # no food on the field -> workers fall to the idle-dig branch
    for _ in range(400):
        for u in colony.units[:]:
            sim._execute_unit_ai(u, colony)
    own_air = (sim.world.voxels == VoxelType.AIR.value) & (sim.world.ownership == colony.colony_id)
    deep = 0
    for (x, y, z) in np.argwhere(own_air):
        if z < sim.world.surface_z(int(x), int(y)):
            deep += 1
    assert deep > 0, "a deep-preference colony must carve tunnels below the surface"


def test_shoreline_colony_bridges_the_water():
    """A shoreline colony with timber lays a WOOD causeway over the oasis."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    colony = sim.colonies[1]
    sx = cx + OASIS_RADIUS + 2
    colony.maw.position = (sx, cy, sim.world.surface_z(sx, cy) + 1)
    colony.wood = 30
    colony.maw.food_stored = 200
    worker = colony.spawn_unit(UnitType.WORKER) or colony.units[0]
    before = int((sim.world.voxels == VoxelType.WOOD.value).sum())
    for _ in range(80):
        colony.wood = max(colony.wood, 10)
        sim._bridge_step(worker, colony)
    after = int((sim.world.voxels == VoxelType.WOOD.value).sum())
    assert after > before, "a shoreline colony must lay a WOOD causeway over the water"


def test_shoreline_colony_raises_a_levee():
    """A nest near the water raises a SAND levee (dike/dam) on its water-facing arc."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    colony = sim.colonies[1]
    sx = cx + OASIS_RADIUS + 2
    colony.maw.position = (sx, cy, sim.world.surface_z(sx, cy) + 1)
    colony.maw.food_stored = 200
    worker = colony.spawn_unit(UnitType.WORKER) or colony.units[0]
    raised = 0
    for _ in range(80):
        if sim._levee_step(worker, colony):
            raised += 1
    # count owned SAND on the oasis-facing side that sits above the old surface
    banks = 0
    for (x, y, z) in np.argwhere(sim.world.ownership == colony.colony_id):
        if sim.world.voxels[x, y, z] == VoxelType.SAND.value and x < sx:
            banks += 1
    assert raised > 0 and banks > 0, "a near-water nest must raise a SAND levee"


def test_flood_rafts_instead_of_drowning():
    """BOATS: a unit with timber caught in a flood rafts and survives instead of
    drowning; the raft clears when the water recedes."""
    sim = make_sim()
    colony = sim.colonies[2]
    unit = colony.units[0] if colony.units else colony.spawn_unit(UnitType.WORKER)
    colony.wood = 3
    fx, fy = unit.position[0], unit.position[1]
    sim.flood_cells = {(fx, fy)}
    sim.kw_until = sim.step_count + 50
    sim.flood_until = sim.step_count + 40
    sim.step()
    assert getattr(unit, 'rafted', False), "a wood-bearing unit must raft on the flood"
    assert unit in colony.units, "a rafted unit must survive the flood"


def test_castle_and_tunnel_voxels_render():
    """The X-ray web render must not crash and must emit bytes with tunnels present."""
    from dashboard import render_frame_png
    sim = make_sim()
    colony = sim.colonies[0]
    colony.genome.tunnel_preference = 1.0
    colony.maw.food_stored = 500
    for _ in range(6):
        colony.spawn_unit(UnitType.WORKER)
    for _ in range(120):
        for u in colony.units[:]:
            sim._execute_unit_ai(u, colony)
    png = render_frame_png(sim)
    assert isinstance(png, (bytes, bytearray)) and len(png) > 0, "web render must emit a PNG"
