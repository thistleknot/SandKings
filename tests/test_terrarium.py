"""Acceptance tests for SPEC_TERRARIUM_LIVENESS.md.

Preconditions: numpy; no display needed. Failure modes covered: closed food
system regression, absorbing dead state, unkillable maws, cavern collapse,
respawn slot corruption.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    BOOTSTRAP_FLOOR,
    FEED_INTERVAL,
    HARVEST_YIELD,
    MAW_MAX_HEALTH,
    RESPAWN_DELAY,
    RESPAWN_FOOD,
    Colony,
    ColonyGenome,
    SandKing,
    SandKingsSimulation,
    UnitType,
    VoxelType,
    VoxelWorld,
)


def make_sim(seed: int = 11, **kwargs) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=40, height=30, depth=12, num_colonies=3, **kwargs)


# --- Terrain (T8) ---

def test_terrain_height_variation_and_bounds():
    world = VoxelWorld(80, 40, 20, seed=7)
    substrate = 20 // 5
    heights = np.array([[world.surface_z(x, y) for y in range(1, 39)]
                        for x in range(1, 79)], dtype=float)
    assert heights.std() > 1.5, f"terrain too flat: std={heights.std():.2f}"
    interior = heights[(heights > 0)]
    assert interior.max() <= int(0.85 * 20) + 1, "surface above bound (+1 for surface food)"


def test_terrain_caverns_strata_glass_and_settled():
    world = VoxelWorld(80, 40, 20, seed=7)
    substrate = 20 // 5
    v = world.voxels
    # caverns: AIR strictly between substrate and some column's surface
    interior_air = 0
    for x in range(1, 79):
        for y in range(1, 39):
            top = world.surface_z(x, y)
            col = v[x, y, substrate:top]
            interior_air += int((col == VoxelType.AIR.value).sum())
    assert interior_air > 0, "no caverns generated"
    # strata: STONE above the substrate line
    assert (v[1:-1, 1:-1, substrate:] == VoxelType.STONE.value).any(), "no strata stone"
    # glass shell intact
    assert (v[0, :, :] == VoxelType.GLASS.value).all()
    assert (v[-1, :, :] == VoxelType.GLASS.value).all()
    assert (v[:, 0, :] == VoxelType.GLASS.value).all()
    assert (v[:, -1, :] == VoxelType.GLASS.value).all()
    assert (v[:, :, 0] == VoxelType.GLASS.value).all()
    # gravity-settled: apply_gravity is a no-op
    before = v.copy()
    world.apply_gravity()
    assert np.array_equal(before, world.voxels), "terrain not settled at generation"


def test_terrain_generates_at_tiny_depth():
    world = VoxelWorld(20, 10, 5, seed=3)  # existing viewer tests use this size
    assert world.voxels.shape == (20, 10, 5)


# --- Feeding (T1) ---

def test_feeding_places_surface_food_and_floors_reserves():
    sim = make_sim()
    starving = sim.colonies[0]
    starving.units.clear()
    starving.maw.food_stored = 1
    before = (sim.world.voxels == VoxelType.FOOD.value).copy()
    placed = sim._feed_terrarium()
    after = sim.world.voxels == VoxelType.FOOD.value
    new_food = np.argwhere(after & ~before)
    assert placed >= 4 * len(sim.colonies) * 0.5, f"too little food placed: {placed}"
    assert len(new_food) == placed
    for x, y, z in new_food:
        assert not before[x, y, z], "was AIR before"
        assert sim.world.voxels[x, y, z - 1] != VoxelType.AIR.value, "food must rest on terrain"
    assert starving.maw.food_stored >= BOOTSTRAP_FLOOR


# --- Bootstrap (T2) ---

def test_bootstrap_revives_unitless_colony():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.units.clear()
    colony.maw.food_stored = 5
    sim.step()
    assert len(colony.units) == 1
    assert colony.units[0].unit_type == UnitType.WORKER


# --- Maw combat + regen (T4) ---

def test_maw_takes_siege_damage_and_regens():
    sim = make_sim()
    attacker_colony, target_colony = sim.colonies[0], sim.colonies[1]
    mx, my, mz = target_colony.maw.position
    soldier = SandKing(attacker_colony.colony_id, (mx + 1, my, mz), UnitType.SOLDIER)
    attacker_colony.units.append(soldier)
    hp_before = target_colony.maw.health
    sim._resolve_conflicts()
    assert target_colony.maw.health == hp_before - soldier.attack
    # regen blocked while besieged
    sim._apply_maw_regen()
    assert target_colony.maw.health == hp_before - soldier.attack
    # regen resumes when the siege lifts
    attacker_colony.units.remove(soldier)
    sim._apply_maw_regen()
    assert target_colony.maw.health > hp_before - soldier.attack


# --- Colony death cascade (T5) + respawn (T6) ---

def test_maw_death_cascade_and_respawn():
    sim = make_sim()
    victim = sim.colonies[2]
    victim_id = victim.colony_id
    dead_genome_aggression = victim.genome.aggression
    unit_positions = [u.position for u in victim.units]
    victim.maw.take_damage(MAW_MAX_HEALTH + 1)
    assert not victim.maw.alive

    sim._check_maw_deaths()
    assert victim_id in sim.pending_respawns
    assert sim.pending_respawns[victim_id] == sim.step_count + RESPAWN_DELAY
    assert not victim.units, "fallen colony's units become corpses"
    for pos in unit_positions:
        assert sim.world.voxels[pos] == VoxelType.CORPSE.value
    assert not (sim.world.ownership == victim_id).any(), "ownership cleared"
    assert not sim.pheromones.trails[:, :, :, victim_id, :].any(), "pheromones zeroed"

    # not due yet
    sim._process_respawns()
    assert not sim.colonies[2].is_alive()

    # fast-forward and respawn
    sim.step_count += RESPAWN_DELAY
    sim._process_respawns()
    arrival = sim.colonies[2]
    assert arrival.is_alive()
    assert arrival.colony_id == victim_id, "slot keeps its id (color + pheromone channel)"
    assert arrival.maw.food_stored <= RESPAWN_FOOD, "arrival food is RESPAWN_FOOD minus starter workers"
    assert len(arrival.units) == 3
    assert victim_id not in sim.pending_respawns
    # min distance from living maws
    w, h, _ = sim.world.dimensions
    min_distance = int(0.1 * ((w**2 + h**2) ** 0.5))
    ax, ay, _ = arrival.maw.position
    for other in sim.colonies:
        if other is arrival or not other.is_alive():
            continue
        ox, oy, _ = other.maw.position
        assert ((ax - ox) ** 2 + (ay - oy) ** 2) ** 0.5 >= min_distance


# --- Worker foraging (T3) ---

def test_worker_forages_distant_food():
    sim = make_sim()
    colony = sim.colonies[0]
    for other in sim.colonies:
        other.units.clear()
    colony.maw.food_stored = 500  # no starvation interference

    # open-air corridor with one worker and food 6 voxels away
    z = sim.world.depth - 2
    sim.world.voxels[2:20, 2:5, z] = VoxelType.AIR.value
    worker = SandKing(colony.colony_id, (3, 3, z), UnitType.WORKER)
    colony.units.append(worker)
    sim.world.voxels[9, 3, z] = VoxelType.FOOD.value

    food_before = colony.maw.food_stored
    for _ in range(20):
        sim._execute_unit_ai(worker, colony)
        if colony.maw.food_stored > food_before:
            break
    assert colony.maw.food_stored == food_before + HARVEST_YIELD, \
        "worker must reach and harvest food within 20 steps"
    assert worker.forage_target is None, "target cleared after harvest"


def test_forage_target_invalidated_when_eaten():
    sim = make_sim()
    colony = sim.colonies[0]
    target = (5, 5, sim.world.depth - 2)
    sim.world.voxels[target] = VoxelType.FOOD.value
    worker = SandKing(colony.colony_id, (20, 20, sim.world.depth - 2), UnitType.WORKER)
    worker.forage_target = target
    colony.units.append(worker)
    sim.world.voxels[target] = VoxelType.AIR.value  # someone else ate it
    sim._execute_unit_ai(worker, colony)
    assert worker.forage_target != target, "stale target must be dropped"


# --- Vectorized CA parity (perf fix must preserve semantics) ---

def _territory_spread_reference(world, colonies):
    """Original per-voxel implementation of the Conway territory rules."""
    new_ownership = world.ownership.copy()
    for colony in colonies:
        if not colony.is_alive():
            continue
        coords = np.where(world.ownership == colony.colony_id)
        for x, y, z in zip(*coords):
            neighbors = world.get_neighbors_3d((x, y, z), radius=1)
            same = sum(1 for n in neighbors
                       if world.ownership[n] == colony.colony_id)
            if same < 2 or same > 5:
                new_ownership[x, y, z] = -1
            for nx, ny, nz in neighbors:
                if (world.ownership[nx, ny, nz] == -1 and
                        world.get_voxel(nx, ny, nz) == VoxelType.AIR):
                    count = sum(1 for nn in world.get_neighbors_3d((nx, ny, nz))
                                if world.ownership[nn] == colony.colony_id)
                    if count >= 3:
                        new_ownership[nx, ny, nz] = colony.colony_id
    return new_ownership


def test_territory_spread_matches_reference():
    from sandkings import CellularAutomata
    sim = make_sim(seed=5)
    rng = np.random.default_rng(5)
    # scatter random territory for every colony through the air
    for colony in sim.colonies:
        cells = rng.integers([1, 1, 1], np.array(sim.world.dimensions) - 1, size=(60, 3))
        for x, y, z in cells:
            if sim.world.voxels[x, y, z] == VoxelType.AIR.value:
                sim.world.ownership[x, y, z] = colony.colony_id
    expected = _territory_spread_reference(sim.world, sim.colonies)
    CellularAutomata.apply_territory_spread(sim.world, sim.colonies)
    assert np.array_equal(sim.world.ownership, expected), \
        "vectorized CA diverges from the reference rules"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all terrarium tests passed")
