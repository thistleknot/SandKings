"""Acceptance for SPEC_TECH TE11 - gunpowder & the catapult (the siege tier).

A native tech with prereqs is RESEARCHED (gunpowder from fire+metal, catapult
from masonry+gunpowder); a catapult at war hurls a shot across the board.
Failure modes: prereq research not developing the tech, the catapult not landing
a shot / not gated on war+range, gunpowder giving no firepower.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import CATAPULT_RELOAD, SandKingsSimulation, UnitType


def make_sim(seed: int = 8) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_gunpowder_and_catapult_are_researched_from_prereqs():
    sim = make_sim()
    c = sim.colonies[0]
    c.techs = {'fire', 'metallurgy'}
    c.tech_xp = {'fire': 1.0, 'metallurgy': 1.0}
    c.maw.position = (5, 5, c.maw.position[2])  # isolate from teachers
    for _ in range(30):
        sim._tech_tick()
    assert 'gunpowder' in c.techs, "gunpowder emerges from fire + metal"
    c.techs.add('masonry')
    for _ in range(40):
        sim._tech_tick()
    assert 'catapult' in c.techs, "the catapult emerges from masonry + gunpowder"


def test_catapult_hurls_a_shot_and_wounds_the_enemy_maw():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    a.techs = {'catapult'}
    a.tech_xp = {'catapult': 1.0}
    sim._diplomacy()
    sim.diplomacy.war_target[a.colony_id] = b.colony_id
    z = a.maw.position[2]
    a.maw.position = (10, 10, z)
    b.maw.position = (24, 10, z)  # within CATAPULT_RANGE
    b.maw.health = 100
    sim.step_count = CATAPULT_RELOAD  # a reload boundary
    before = b.maw.health
    sim._catapult_tick()
    assert b.maw.health < before, "the shot struck the enemy maw"
    assert any("catapult hurls" in m for _, m in sim.events), "the siege is chronicled"


def test_catapult_needs_a_war_target():
    sim = make_sim()
    a = sim.colonies[0]
    a.techs = {'catapult'}
    a.tech_xp = {'catapult': 1.0}
    sim.step_count = CATAPULT_RELOAD  # no war target set
    sim._catapult_tick()
    assert not any("catapult hurls" in m for _, m in sim.events), "no war, no shot"


def test_gunpowder_soldier_hits_harder():
    sim = make_sim()
    c = sim.colonies[0]
    c.at_war = True
    c.maw.food_stored = 999
    c.tech_xp = {}
    c.spawn_unit(UnitType.SOLDIER, 0)
    base = c.units[-1].attack
    c.tech_xp = {'gunpowder': 1.0}
    c.spawn_unit(UnitType.SOLDIER, 0)
    armed = c.units[-1].attack
    assert armed > base, "gunpowder is firepower"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tech-siege tests passed")
