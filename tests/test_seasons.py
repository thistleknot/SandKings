"""Acceptance tests for SPEC_SEASONS_AND_STONE.md (T16-T27).

Preconditions: numpy; seeded sims. Failure modes covered: dole-clamp
regression, crop-lifecycle timing drift, oasis exemptions, ore outside
its host strata, learner divergence, old-checkpoint breakage.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import sandkings as sk
from sandkings import (
    CROP_GROWDUR,
    CROP_YIELD,
    FARM_STOP_FOOD,
    MINE_TIME,
    SEASON_LENGTH,
    SEED_COST,
    SandKing,
    SandKingsSimulation,
    UnitType,
    VoxelType,
    VoxelWorld,
)


def make_sim(seed: int = 61, harsh: bool = True, **kw) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3, **kw)
    sim.harsh = harsh
    return sim


def clear_units(sim):
    for c in sim.colonies:
        c.units.clear()


# --- T16 season clock ---

def test_season_clock_derived_and_logged():
    sim = make_sim()
    assert sim.season_index() == 0 and sim.year() == 0
    sim.step_count = SEASON_LENGTH - 1
    clear_units(sim)
    sim.step()  # crosses into Growth
    assert sim.season_index() == 1
    assert any("Growth season begins" in m for _, m in sim.events)
    sim.step_count = 4 * SEASON_LENGTH - 1
    sim.step()
    assert sim.year() == 1 and sim.season_index() == 0


def test_dole_shrinks_by_season_and_clamp_scales():
    sim = make_sim(harsh=True)
    placed = {}
    for season, start in ((0, 0), (1, SEASON_LENGTH), (2, 2 * SEASON_LENGTH),
                          (3, 3 * SEASON_LENGTH)):
        sim.step_count = start + 1
        # clear all surface food so placement isn't blocked
        v = sim.world.voxels
        v[v == VoxelType.FOOD.value] = VoxelType.AIR.value
        placed[season] = sim._feed_terrarium()
    assert placed[0] > placed[1] > placed[2] > placed[3] > 0
    assert placed[3] <= 12, f"Chill dole must not floor at 16 (got {placed[3]})"
    sim.harsh = False
    sim.step_count = 3 * SEASON_LENGTH + 1  # Chill, year 0: ramp floors dole at 1.0
    assert sim.dole_factor() == 1.0


# --- T19/T20 crop lifecycle ---

def test_crop_lifecycle_timing_and_harvest():
    sim = make_sim()
    clear_units(sim)
    colony = sim.colonies[0]
    pos = (5, 5, 6)
    sim.world.voxels[pos] = VoxelType.CROP.value
    sim.world.voxels[5, 5, 7:] = VoxelType.AIR.value
    sim.world.ownership[pos] = colony.colony_id
    sim._crops()[pos] = 0
    sim.step_count = 1  # Flood
    for _ in range(CROP_GROWDUR // sk.CROP_TICK):
        sim._grow_crops()
    assert sim.world.voxels[pos] == VoxelType.CROP_RIPE.value
    assert pos not in sim._crops()
    # harvest via the radius-2 grab
    worker = SandKing(colony.colony_id, (5, 5, 7), UnitType.WORKER)
    colony.units.append(worker)
    food_before = colony.maw.food_stored
    sim._execute_unit_ai(worker, colony)
    assert colony.maw.food_stored == food_before + CROP_YIELD
    assert sim.world.voxels[pos] == VoxelType.TILLED.value, "soil endures"


def test_dust_stalls_and_chill_kills():
    sim = make_sim()
    pos = (5, 5, 6)
    sim.world.voxels[pos] = VoxelType.CROP.value
    sim.world.voxels[5, 5, 7:] = VoxelType.AIR.value
    sim.world.ownership[pos] = 0
    sim._crops()[pos] = 10
    sim.step_count = 2 * SEASON_LENGTH + 1  # Dust
    sim._grow_crops()
    assert sim._crops()[pos] == 10, "Dust stalls growth"
    sim.step_count = 3 * SEASON_LENGTH + 1  # Chill
    sim._grow_crops()
    assert sim.world.voxels[pos] == VoxelType.SAND.value, "the frost takes it"
    assert pos not in sim._crops()
    assert any("frost takes" in m for _, m in sim.events)


def test_oasis_exempt_and_double_speed():
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    pos = (cx, cy, 6)
    sim.world.voxels[pos] = VoxelType.CROP.value
    sim.world.voxels[cx, cy, 7:] = VoxelType.AIR.value
    sim._crops()[pos] = 0
    sim.step_count = 3 * SEASON_LENGTH + 1  # Chill - oasis doesn't care
    ticks_needed = CROP_GROWDUR // sk.CROP_TICK
    for _ in range(ticks_needed // 2):
        sim._grow_crops()
    assert sim.world.voxels[pos] == VoxelType.CROP_RIPE.value, \
        "oasis crops grow at x2 in any season"


def test_burial_kills_crop():
    sim = make_sim()
    pos = (5, 5, 6)
    sim.world.voxels[pos] = VoxelType.CROP.value
    sim.world.voxels[5, 5, 7] = VoxelType.SAND.value  # drift on top
    sim._crops()[pos] = 30
    sim.step_count = 1
    sim._grow_crops()
    assert sim.world.voxels[pos] == VoxelType.SAND.value
    assert pos not in sim._crops()


# --- T18 worker priorities + T17 seed-corn math ---

def test_worker_prefers_wild_food_over_farming():
    sim = make_sim()
    clear_units(sim)
    colony = sim.colonies[0]
    colony.farming = True
    colony.maw.food_stored = 500
    mx, my, mz = colony.maw.position
    worker = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    colony.units.append(worker)
    sim.world.voxels[mx + 2, my, mz] = VoxelType.FOOD.value
    food_before = colony.maw.food_stored
    sim.step_count = 1
    sim._execute_unit_ai(worker, colony)
    assert colony.maw.food_stored == food_before + sk.HARVEST_YIELD, \
        "wild food outranks farming"


def test_sowing_pays_seed_cost_and_refuses_when_broke():
    sim = make_sim()
    clear_units(sim)
    colony = sim.colonies[0]
    colony.farming = True
    mx, my, mz = colony.maw.position
    worker = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    colony.units.append(worker)
    plot = (mx + 2, my, mz)
    sim.world.voxels[plot] = VoxelType.TILLED.value
    sim.world.voxels[mx + 2, my, mz + 1:] = VoxelType.AIR.value
    sim.world.ownership[plot] = colony.colony_id
    sim.step_count = 1
    colony.maw.food_stored = SEED_COST - 1
    assert not sim._farm_step(worker, colony) or \
        sim.world.voxels[plot] != VoxelType.CROP.value, "refused when broke"
    colony.maw.food_stored = 100.0
    sim._farm_step(worker, colony)
    assert sim.world.voxels[plot] == VoxelType.CROP.value
    assert colony.maw.food_stored == 100.0 - SEED_COST
    assert CROP_YIELD / SEED_COST == 8, "the temptation ratio M/N"


def test_farming_flag_hysteresis():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.farming = False
    colony.maw.food_stored = 45.0
    clear_units(sim)
    for _ in range(30):
        sim.step()
        colony.maw.food_stored = 45.0
    assert not colony.farming, "45 < start gate: stays off"
    colony.farming = True
    for _ in range(5):
        sim.step()
        colony.maw.food_stored = 45.0
    assert colony.farming, "45 > stop gate: stays on"


# --- T21 raze ---

def test_at_war_soldier_razes_enemy_field():
    sim = make_sim()
    clear_units(sim)
    attacker, victim = sim.colonies[0], sim.colonies[1]
    attacker.at_war = True
    plot = (12, 12, 6)
    sim.world.voxels[plot] = VoxelType.TILLED.value
    sim.world.ownership[plot] = victim.colony_id
    soldier = SandKing(attacker.colony_id, (12, 13, 6), UnitType.SOLDIER)
    attacker.units.append(soldier)
    sim.step_count = 1
    sim._execute_unit_ai(soldier, attacker)
    assert sim.world.voxels[plot] == VoxelType.SAND.value
    assert any("razes" in m for _, m in sim.events)


# --- T22 oasis spawn ---

def test_lucky_maw_and_oasis_holder():
    sim = make_sim(seed=63)
    assert sim.oasis_holder() is not None, "one lucky colony wakes at the oasis"
    assert any("wakes beside the oasis" in m for _, m in sim.events)
    cx, cy = sim.world.width // 2, sim.world.height // 2
    outside = [c for c in sim.colonies if c.colony_id != sim.oasis_holder()]
    for c in outside:
        mx, my, _ = c.maw.position
        assert (mx - cx) ** 2 + (my - cy) ** 2 > sk.OASIS_RADIUS ** 2, \
            "non-lucky maws start outside the disc"


# --- T23 ore generation ---

def test_ore_hosted_in_correct_strata():
    world = VoxelWorld(80, 40, 20, seed=9)
    substrate = 20 // 5
    bands = {substrate + 2, substrate + 3, int(20 * 0.45), int(20 * 0.45) + 1}
    copper = np.argwhere(world.voxels == VoxelType.COPPER_ORE.value)
    gold = np.argwhere(world.voxels == VoxelType.GOLD_ORE.value)
    assert 10 <= len(copper) <= 80, f"copper count {len(copper)}"
    assert 4 <= len(gold) <= 18, f"gold count {len(gold)}"
    assert all(int(z) in bands for _, _, z in copper), "copper outside strata"
    assert all(int(z) in (substrate - 2, substrate - 1) for _, _, z in gold), \
        "gold outside the deep layer"
    tiny = VoxelWorld(20, 10, 5, seed=9)
    assert not (tiny.voxels >= VoxelType.COPPER_ORE.value).any(), \
        "no ore in shallow test worlds"


# --- T24/T25 mining, armor, spill ---

def test_mining_hauling_and_strike_event():
    sim = make_sim()
    clear_units(sim)
    colony = sim.colonies[0]
    colony.maw.food_stored = 500
    mx, my, mz = colony.maw.position
    ore_pos = (mx + 1, my, mz)
    sim.world.voxels[ore_pos] = VoxelType.COPPER_ORE.value
    sim.world.voxels[mx + 2, my, mz] = VoxelType.AIR.value  # exposure face
    worker = SandKing(colony.colony_id, (mx + 2, my, mz), UnitType.WORKER)
    worker.mine_target = ore_pos
    colony.units.append(worker)
    sim.step_count = 1
    for _ in range(MINE_TIME):
        sim._mine_step(worker, colony)
    assert worker.carrying == 'copper'
    assert sim.world.voxels[ore_pos] == VoxelType.AIR.value
    assert any("strikes copper" in m for _, m in sim.events)
    sim._haul_step(worker, colony)  # already within 2 of the maw
    assert colony.ore['copper'] == 1 and worker.carrying is None


def test_copper_armor_consumed_at_spawn():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.maw.food_stored = 100
    colony.ore['copper'] = 1
    colony.spawn_unit(UnitType.SOLDIER)
    soldier = colony.units[-1]
    assert soldier.armored and soldier.max_health == 20 + sk.COPPER_ARMOR_HP
    assert colony.ore['copper'] == 0
    colony.spawn_unit(UnitType.SOLDIER)
    assert not colony.units[-1].armored, "no copper, no armor"


def test_ore_spills_on_maw_death():
    sim = make_sim()
    victim = sim.colonies[1]
    victim.ore['gold'] = 2
    victim.maw.take_damage(10**6)
    before = int((sim.world.voxels == VoxelType.GOLD_ORE.value).sum())
    sim._check_maw_deaths()
    after = int((sim.world.voxels == VoxelType.GOLD_ORE.value).sum())
    assert after >= before + 1, "stored gold scatters as re-minable voxels"


# --- T26 learner ---

def test_learner_prefers_rewarded_posture():
    from colony_learner import POSTURES, ColonyLearner
    np.random.seed(3)
    random.seed(3)
    learner = ColonyLearner()
    learner.epsilon = 0.0  # pure greedy for the test
    state = (0, 1, 0, False, False)
    farm_idx = POSTURES.index("FARM")
    row = learner._qrow(state)
    for _ in range(50):  # simulate: FARM got rewarded historically
        row[farm_idx] += 0.2 * (1.0 - row[farm_idx])
    assert learner.best_posture(state) == "FARM"


def test_learner_biases_farm_gate_and_pickles():
    import pickle
    sim = make_sim()
    colony = sim.colonies[0]
    learner = sim._learner(colony.colony_id)
    learner.posture = "FARM"
    colony.farming = False
    colony.maw.food_stored = 50  # between 45 (0.75 gate) and 60
    clear_units(sim)
    sim.step_count = 24
    sim.step()  # decision tick fires at 25... posture may change; force after
    learner.posture = "FARM"
    colony.farming = False
    colony.maw.food_stored = 50
    sim.step()
    # gate = 60 * 0.75 = 45 < 50 -> farming turns on under FARM posture
    assert colony.farming
    blob = pickle.dumps(sim)
    revived = pickle.loads(blob)
    assert revived.learners[colony.colony_id].posture in ("FORAGE", "FARM",
                                                          "RAID", "FORTIFY")


# --- compatibility ---

def test_old_checkpoint_attrs_resume():
    sim = make_sim()
    for colony in sim.colonies:
        for attr in ('farming', 'ore', 'ore_struck', 'milestones'):
            if hasattr(colony, attr):
                delattr(colony, attr)
    for attr in ('crops', 'learners', 'harsh', '_raze_logged', '_frost_logged'):
        if hasattr(sim, attr):
            delattr(sim, attr)
    for _ in range(50):
        sim.step()  # must not raise


def test_enhanced_sim_inert_on_round1():
    from sandkings_evolution import EnhancedSandKingsSimulation
    random.seed(7)
    np.random.seed(7)
    sim = EnhancedSandKingsSimulation(width=48, height=36, depth=12,
                                      num_colonies=3)
    for _ in range(200):
        sim.step()
    assert not hasattr(sim, 'crops') or not sim.crops, "no crops in evolution"
    assert not any(getattr(c, 'ore', {}).get('copper') for c in sim.colonies), \
        "no mining in evolution"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all seasons tests passed")
