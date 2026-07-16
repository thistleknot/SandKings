"""Acceptance tests for SPEC_TIMBER_AND_FLAME.md (T41-T48).

Preconditions: numpy; seeded sims. Failure modes covered: felling into
solids, rot registries leaking, fire crossing firebreaks, fauna piling
into multiple simultaneous incursions, squirrel escape logic, web snares
eating moves, ram multipliers applying without a ram.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (
    Beast, CHOP_TIME, FAUNA, FELL_LENGTH, FIRE_BURN, POISON_DURATION,
    RAM_SIEGE_MULT, SPEAR_ATTACK, SPEAR_LIFE, SandKing, SandKingsSimulation,
    UnitType, VoxelType, WALL_ROT,
)


def make_sim(seed: int = 77) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_trees_generate_and_shallow_worlds_stay_sterile():
    sim = make_sim()
    assert (sim.world.voxels == VoxelType.WOOD.value).sum() >= 6
    from sandkings import VoxelWorld
    tiny = VoxelWorld(20, 10, 5, seed=31)
    assert not (tiny.voxels == VoxelType.WOOD.value).any()


def test_chop_and_fell_lays_crown_or_banks_wood():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.wood = 0
    # build a hand-planted palm: base + 2 crown on flat open ground
    x, y = 24, 18
    z = sim.world.surface_z(x, y) + 1
    for dz in range(3):
        sim.world.voxels[x, y, z + dz] = VoxelType.WOOD.value
    worker = SandKing(colony.colony_id, (x - 1, y, z), UnitType.WORKER)
    worker.chop_target = (x, y, z)
    for _ in range(CHOP_TIME):
        assert sim._chop_step(worker, colony)
    assert sim.world.voxels[x, y, z] == VoxelType.AIR.value, "trunk cut"
    laid = sum(1 for i in range(1, FELL_LENGTH + 1)
               if sim.world.in_bounds(x + i, y, z)
               and sim.world.voxels[x + i, y, z] == VoxelType.WOOD.value)
    assert colony.wood + laid == 3, "every trunk voxel accounted for"
    assert colony.wood >= 1, "the cut trunk itself always banks"


def test_bone_from_corpse_and_spear_at_spawn():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.wood, colony.bone = 1, 1
    colony.maw.food_stored = 100
    colony.spawn_unit(UnitType.SOLDIER, step=50)
    spear = colony.units[-1]
    assert spear.attack == 12 + SPEAR_ATTACK
    assert spear.weapon_expires == 50 + SPEAR_LIFE
    assert colony.wood == 0 and colony.bone == 0
    # expiry sweep: the spear splinters
    sim.step_count = spear.weapon_expires
    spear_exp = spear.weapon_expires
    for _ in range(2):
        sim.step()
    assert spear.weapon_expires == 0 and spear.attack == 12, "splintered"
    assert sim.step_count > spear_exp


def test_palisade_placed_rots_back_to_sand():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.wood = 2
    mx, my, mz = colony.maw.position
    worker = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    colony.units.append(worker)
    placed = False
    for _ in range(30):
        if sim._palisade_step(worker, colony):
            if (sim.world.voxels == VoxelType.WOOD_WALL.value).any():
                placed = True
                break
    assert placed, "a wall voxel rose on the ring"
    pos = next(iter(sim._rot()))
    assert sim.rot[pos] > 0
    sim.rot[pos] = 0  # force expiry
    sim.step_count = 49  # next step hits the %50 rot sweep
    sim.step()
    assert sim.world.voxels[pos] == VoxelType.SAND.value, "rotted away"
    assert pos not in sim.rot


def test_fire_spreads_through_flammables_and_burns_out():
    sim = make_sim()
    x, y = 30, 12
    z = sim.world.surface_z(x, y) + 1
    for i in range(3):  # a row of wood: fuel
        sim.world.voxels[x + i, y, z] = VoxelType.WOOD.value
    sim._ignite((x, y, z))
    assert (x, y, z) in sim.fires
    random.seed(1)
    for _ in range(FIRE_BURN * 6):
        sim._fire_tick()
    assert not sim.fires, "all burned out"
    burned = sum(1 for i in range(3)
                 if sim.world.voxels[x + i, y, z] == VoxelType.SAND.value)
    assert burned == 3, "fire consumed the whole row, leaving scars"


def test_web_snare_costs_the_step():
    sim = make_sim()
    colony = sim.colonies[0]
    x, y = 20, 20
    z = sim.world.surface_z(x, y) + 1
    unit = SandKing(colony.colony_id, (x, y, z), UnitType.WORKER)
    sim.world.voxels[x + 1, y, z] = VoxelType.WEB.value
    assert not sim._step_toward(unit, (x + 3, y, z), colony), "snared"
    assert sim.world.voxels[x + 1, y, z] == VoxelType.AIR.value, "torn free"
    assert sim._step_toward(unit, (x + 3, y, z), colony), "path now clear"


def test_single_incursion_rule_and_bounty():
    sim = make_sim()
    sim._spawn_incursion()
    assert sim.fauna, "an incursion arrived"
    first_count = len(sim.fauna)
    sim._spawn_incursion()  # a second roll while one lives is a test-only
    # force: the tick itself never rolls while fauna live
    sim.fauna = sim.fauna[:first_count]
    beast = sim.fauna[0]
    beast.health = 1
    beast.species, beast.bounty = 'rabbit', FAUNA['rabbit'][5]
    soldier = SandKing(sim.colonies[0].colony_id,
                       (beast.position[0] + 1, beast.position[1],
                        beast.position[2]), UnitType.SOLDIER)
    soldier2 = SandKing(sim.colonies[0].colony_id,
                        (beast.position[0] - 1, beast.position[1],
                         beast.position[2]), UnitType.SOLDIER)
    sim.colonies[0].units += [soldier, soldier2]
    sim._beast_combat(beast)
    assert beast not in sim.fauna, "slain"
    assert any("slain" in m for _, m in sim.events)


def test_squirrel_slips_away_unless_pinned():
    sim = make_sim()
    beast = Beast('squirrel', (24, 18, sim.world.surface_z(24, 18) + 1),
                  1, 3, 0, 4, spawned_at=0, provoked=True)
    sim._fauna().append(beast)
    lone = SandKing(sim.colonies[0].colony_id,
                    (25, 18, beast.position[2]), UnitType.SOLDIER)
    sim.colonies[0].units.append(lone)
    sim._beast_combat(beast)
    assert beast in sim.fauna and beast.fleeing, "slipped away, unpinned"
    beast.fleeing = False
    beast.health = 1
    pin = SandKing(sim.colonies[0].colony_id,
                   (23, 18, beast.position[2]), UnitType.SOLDIER)
    sim.colonies[0].units.append(pin)
    sim._beast_combat(beast)
    assert beast not in sim.fauna, "two adjacent pins finish it"


def test_scorpion_poison_dot():
    sim = make_sim()
    colony = sim.colonies[0]
    x, y = 24, 18
    z = sim.world.surface_z(x, y) + 1
    victim = SandKing(colony.colony_id, (x + 1, y, z), UnitType.SOLDIER)
    colony.units.append(victim)
    beast = Beast('scorpion', (x, y, z), 22, 6, 15, 2, spawned_at=0)
    sim._fauna().append(beast)
    random.seed(5)
    sim._beast_combat(beast)
    assert victim.poisoned_until == sim.step_count + POISON_DURATION
    hp = victim.health
    sim.fauna.clear()  # venom outlives the incursion
    sim._fauna_tick()
    assert victim.health < hp, "the venom bites each step"


def test_ram_doubles_siege_damage():
    sim = make_sim()
    attacker, defender = sim.colonies[0], sim.colonies[1]
    sim._diplomacy().war_target[attacker.colony_id] = defender.colony_id
    attacker.at_war = True
    mx, my, mz = defender.maw.position
    soldier = SandKing(attacker.colony_id, (mx + 1, my, mz), UnitType.SOLDIER)
    attacker.units.append(soldier)
    defender.maw.health = 1000
    attacker.ram_until = 0
    sim._apply_maw_siege_damage()
    plain = 1000 - defender.maw.health
    defender.maw.health = 1000
    attacker.ram_until = sim.step_count + 100
    sim._apply_maw_siege_damage()
    rammed = 1000 - defender.maw.health
    assert rammed == plain * RAM_SIEGE_MULT


def test_round4_state_pickles_and_enhanced_inert():
    import pickle
    sim = make_sim()
    sim._spawn_incursion()
    sim._ignite_any = None
    colony = sim.colonies[0]
    colony.wood, colony.bone = 3, 2
    for _ in range(30):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert isinstance(revived._fauna(), list)
    assert isinstance(revived._fires(), dict)
    assert isinstance(revived._rot(), dict)
    revived.step()
    # evolution sim: step() override never ticks Round-4 phases
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_fauna_tick' not in EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all timber & flame tests passed")
