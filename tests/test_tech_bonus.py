"""Acceptance tests for SPEC_TECH TE10 - tech BONUSES (proficiency -> capability).

Each bonus must measurably help at proficiency 1 and be EXACTLY neutral at 0.
Failure modes covered: a bonus that changes the baseline at proficiency 0, the
metallurgy spear bonus not reversing cleanly on expiry, and the mining/plow/
farming hooks not scaling with skill.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (SEED_COST, SPEAR_ATTACK, SandKing, SandKingsSimulation,
                       UnitType, VoxelType)


def make_sim(seed: int = 7) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_metallurgy_hardens_spear_and_reverses_on_expiry():
    sim = make_sim()
    c = sim.colonies[0]
    c.at_war = True
    c.maw.food_stored = 999

    def spawn(prof):
        c.tech_xp = {'metallurgy': prof} if prof else {}
        c.wood, c.bone = 5, 5
        c.spawn_unit(UnitType.SOLDIER, 0)
        return c.units[-1]

    base = spawn(0.0)
    strong = spawn(1.0)
    assert base.spear_bonus == SPEAR_ATTACK, "neutral at proficiency 0"
    assert strong.spear_bonus > base.spear_bonus, "metallurgy hardens the spear"
    # the stored bonus exactly matches the added attack, so expiry reverses it
    assert strong.attack - strong.spear_bonus == 12, "soldier base restored on expiry"


def _mine_calls(sim, colony, prof):
    colony.tech_xp = {'metallurgy': prof} if prof else {}
    tx, ty, tz = 10, 10, 6
    sim.world.voxels[tx, ty, tz] = VoxelType.COPPER_ORE.value
    u = SandKing(colony.colony_id, (tx + 1, ty, tz), UnitType.WORKER)
    u.mine_target = (tx, ty, tz)
    n = 0
    while u.carrying is None and n < 30:
        sim._mine_step(u, colony)
        n += 1
    return n


def test_metallurgy_speeds_mining():
    sim = make_sim()
    c = sim.colonies[0]
    slow = _mine_calls(sim, c, 0.0)
    fast = _mine_calls(sim, c, 1.0)
    assert fast < slow, "picks (metallurgy) extract ore faster"


def _sow_cost(sim, colony, prof):
    colony.tech_xp = {'plow': prof} if prof else {}
    mx, my, _ = colony.maw.position
    tx, ty = mx, my + 1
    z = sim.world.surface_z(tx, ty)
    sim.world.voxels[tx, ty, z] = VoxelType.TILLED.value
    sim.world.ownership[tx, ty, z] = colony.colony_id
    u = SandKing(colony.colony_id, (mx, my, z), UnitType.WORKER)
    colony.maw.food_stored = 100.0
    before = colony.maw.food_stored
    sim._farm_step(u, colony)
    return before - colony.maw.food_stored


def test_plow_cheapens_sowing():
    sim = make_sim()
    c = sim.colonies[0]
    c0 = _sow_cost(sim, c, 0.0)
    c1 = _sow_cost(sim, c, 1.0)
    assert abs(c0 - SEED_COST) < 1e-9, "neutral at proficiency 0"
    assert c1 < c0, "plow makes the seed go further"


def test_farming_boosts_harvest_yield():
    sim = make_sim()
    c = sim.colonies[0]

    def harvest_gain(prof):
        c.tech_xp = {'farming': prof} if prof else {}
        mx, my, _ = c.maw.position
        gx, gy = mx + 1, my
        z = sim.world.surface_z(gx, gy)
        sim.world.voxels[gx, gy, z] = VoxelType.CROP_RIPE.value
        sim.world.ownership[gx, gy, z] = c.colony_id
        u = SandKing(c.colony_id, (mx, my, z), UnitType.WORKER)
        c.units.append(u)
        c.maw.food_stored = 50.0
        before = c.maw.food_stored
        sim._execute_unit_ai(u, c)
        c.units.remove(u)
        return c.maw.food_stored - before

    g0 = harvest_gain(0.0)
    g1 = harvest_gain(1.0)
    assert g0 > 0, "the crop was reaped"
    assert g1 > g0, "farming proficiency raises the yield"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tech-bonus tests passed")
