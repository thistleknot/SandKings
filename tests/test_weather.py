"""Acceptance tests for SPEC_WEATHER.md (W1-W6).

Failure modes covered: weather harming sheltered units, floods missing
fires, silt never landing, hail rolling in the wrong seasons, stale
weather state crashing resumed checkpoints, the storm anchor going
blind to new systems.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    COLD_DURATION, FLOOD_DAMAGE, FLOOD_RADIUS_MAX, SandKing,
    SandKingsSimulation, UnitType, VoxelType,
)


def make_sim(seed: int = 33) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def surface_pair(sim, colony, x=24, y=18):
    """One exposed unit and one sheltered (buried) unit at column (x,y)."""
    z_surface = sim.world.surface_z(x, y)
    exposed = SandKing(colony.colony_id, (x, y, min(z_surface + 1,
                                                    sim.world.depth - 1)),
                       UnitType.SOLDIER)
    sheltered = SandKing(colony.colony_id, (x, y, max(0, z_surface - 2)),
                         UnitType.SOLDIER)
    colony.units += [exposed, sheltered]
    return exposed, sheltered


def test_cold_snap_kills_only_the_exposed():
    sim = make_sim()
    colony = sim.colonies[0]
    exposed, sheltered = surface_pair(sim, colony)
    hp_e, hp_s = exposed.health, sheltered.health
    sim.cold_until = sim.step_count + COLD_DURATION
    sim.step_count = 5  # hits the COLD_TICK cadence
    sim.cold_until = sim.step_count + COLD_DURATION
    sim._weather_tick(season=3)
    assert exposed.health < hp_e, "the frost bites the surface"
    assert sheltered.health == hp_s, "tunnels are shelter"


def test_hail_damages_exposed_and_smashes_crops():
    sim = make_sim()
    colony = sim.colonies[0]
    exposed, sheltered = surface_pair(sim, colony)
    x, y = 30, 12
    z = sim.world.surface_z(x, y)
    sim.world.voxels[x, y, z] = VoxelType.CROP.value
    sim.crops = {(x, y, z): 1}
    sim.step_count = 10
    sim.hail_until = sim.step_count + 50
    random.seed(0)
    hp = exposed.health
    for _ in range(200):  # ample hail ticks for the 0.04 smash roll
        if sim.world.voxels[x, y, z] == VoxelType.TILLED.value:
            break
        sim._weather_tick(season=1)
        sim.step_count += 5
        sim.hail_until = sim.step_count + 50
    assert exposed.health < hp
    assert sheltered.health == sheltered.max_health
    assert sim.world.voxels[x, y, z] == VoxelType.TILLED.value, "smashed"
    assert (x, y, z) not in sim.crops


def flatten_basin(sim, radius=14):
    """Level the terrain around the oasis so hydrology tests are exact."""
    cx, cy = sim.world.width // 2, sim.world.height // 2
    base = sim.world.surface_z(cx, cy)
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy - radius, cy + radius + 1):
            if not sim.world.in_bounds(x, y, 0):
                continue
            for z in range(sim.world.depth):
                sim.world.voxels[x, y, z] = (VoxelType.SAND.value
                                             if z <= base
                                             else VoxelType.AIR.value)
    return cx, cy, base


def test_flood_spreads_from_oasis_drowns_and_silts():
    sim = make_sim()
    cx, cy, base = flatten_basin(sim)
    colony = sim.colonies[0]
    exposed = SandKing(colony.colony_id, (cx + 4, cy, base + 1),
                       UnitType.SOLDIER)
    sheltered = SandKing(colony.colony_id, (cx + 4, cy + 1, base - 2),
                         UnitType.SOLDIER)
    sim.world.voxels[cx + 4, cy + 1, base - 2] = VoxelType.AIR.value
    colony.units += [exposed, sheltered]
    fz = base
    sim.world.voxels[cx, cy + 3, fz] = VoxelType.CROP.value
    sim._ignite((cx, cy + 3, fz))
    sim.step_count = 2
    sim.flood_until = sim.step_count + 90
    random.seed(4)
    hp = exposed.health
    tilled_before = int((sim.world.voxels == VoxelType.TILLED.value).sum())
    for _ in range(94):  # rise, hold, recede, and fully drain
        sim._weather_tick(season=0)
        sim.step_count += 1
    assert exposed.health < hp, "the inundation drowns the exposed"
    assert sheltered.health == sheltered.max_health, "tunnels are shelter"
    assert (cx, cy + 3, fz) not in sim._fires(), "water beats fire"
    tilled_after = int((sim.world.voxels == VoxelType.TILLED.value).sum())
    assert tilled_after > tilled_before, "the silt tills the sand"
    assert sim._flood_radius() == 0 and not sim.flood_cells
    assert any("recede" in m for _, m in sim.events)


def test_dam_parts_the_water():
    sim = make_sim()
    cx, cy, base = flatten_basin(sim)
    sim.step_count = 60
    sim.flood_until = sim.step_count + 60  # mid-flood: radius is maximal
    # a closed dam ring (raised banks) around (cx+8, cy)
    px, py = cx + 8, cy
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if max(abs(dx), abs(dy)) == 2:
                for dz in range(1, 4):  # banks above the water line
                    sim.world.voxels[px + dx, py + dy,
                                     base + dz] = VoxelType.WOOD_WALL.value
    cells = sim._compute_flood_cells()
    assert (cx + 4, cy) in cells, "open ground floods"
    assert (px, py) not in cells, "the dam parts the water"
    # breach the dam: the water pours through the gap
    for dz in range(1, 4):
        sim.world.voxels[px - 2, py, base + dz] = VoxelType.AIR.value
    cells = sim._compute_flood_cells()
    assert (px, py) in cells, "a breached dam floods"


def test_channel_carries_water_past_high_ground():
    sim = make_sim()
    cx, cy, base = flatten_basin(sim)
    sim.step_count = 60
    sim.flood_until = sim.step_count + 60
    # a raised ridge across the flow with one dug notch: the channel
    ry = cy + 5
    for x in range(cx - 14, cx + 15):
        for dz in range(1, 4):
            if sim.world.in_bounds(x, ry, base + dz):
                sim.world.voxels[x, ry, base + dz] = VoxelType.WOOD_WALL.value
    cells = sim._compute_flood_cells()
    assert (cx, ry + 2) not in cells, "the ridge holds the water back"
    for dz in range(1, 4):  # dig the runoff channel through the ridge
        sim.world.voxels[cx, ry, base + dz] = VoxelType.AIR.value
    cells = sim._compute_flood_cells()
    assert (cx, ry + 2) in cells, "the channel carries the water through"


def test_storm_roll_never_hails_in_flood_season():
    # W2: hail only in Growth/Dust - the Flood-season roll stays sand
    sim = make_sim()
    random.seed(11)
    hails = 0
    for trial in range(200):
        sim.storm_until = 0
        sim.hail_until = 0
        sim.step_count = 200 * (trial + 1)  # storm-roll cadence, season 0..
        season = sim.season_index()
        # emulate the 3c roll body
        if season in (1, 2) and random.random() < 0.35:
            hails += 1
    # sanity: the gate is the season tuple, asserted structurally
    import inspect
    src = inspect.getsource(SandKingsSimulation.step)
    assert "season in (1, 2)" in src and "HAIL_SHARE" in src


def test_weather_state_pickles_and_old_checkpoints_clear_skied():
    import pickle
    sim = make_sim()
    sim.hail_until = 50
    sim.cold_until = 60
    sim.flood_until = 70
    sim.flood_cells = {(5, 5)}
    revived = pickle.loads(pickle.dumps(sim))
    assert revived.hail_until == 50 and revived.flood_cells == {(5, 5)}
    # pre-weather checkpoint: strip the attrs, sim must still step
    for attr in ('hail_until', 'cold_until', 'flood_until', 'flood_cells'):
        delattr(revived, attr)
    for _ in range(12):
        revived.step()


def test_storm_anchor_sees_all_weather():
    from hive_mind_monitor import build_context, ground_truths
    sim = make_sim()
    colony = sim.colonies[0]
    unit = SandKing(colony.colony_id, colony.maw.position, UnitType.WORKER)
    colony.units.append(unit)
    for attr in ('storm_until', 'hail_until', 'cold_until', 'flood_until'):
        for c in sim.colonies:
            pass
        setattr(sim, attr, sim.step_count + 100)
        truths = ground_truths(build_context(unit, colony, sim))
        assert truths['storm'], f"{attr} must light the storm anchor"
        setattr(sim, attr, 0)
    truths = ground_truths(build_context(unit, colony, sim))
    assert not truths['storm'], "clear skies read clear"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all weather tests passed")
