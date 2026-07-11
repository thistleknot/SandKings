"""Acceptance for SPEC_TECH TE12 - tech diffusion by BARTER and CONQUEST.

Failure modes: a conqueror not seizing the fallen enemy's tech; a truce not
carrying a peace-dividend tech from the richer house to the poorer.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import SandKingsSimulation


def make_sim(seed: int = 9) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_conquest_plunders_the_fallen_tech():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    b.techs = {'metallurgy', 'masonry'}
    b.tech_xp = {'metallurgy': 1.0, 'masonry': 1.0}
    sim._diplomacy()
    sim.diplomacy.war_target[a.colony_id] = b.colony_id  # a is the aggressor
    b.maw.alive = False
    b.units.clear()
    sim._check_maw_deaths()
    assert {'metallurgy', 'masonry'} <= a.techs, "the victor seized the tech"
    assert any("plunders the secrets" in m for _, m in sim.events)


def test_no_plunder_without_a_war():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    b.techs = {'metallurgy'}
    b.maw.alive = False
    b.units.clear()
    sim._check_maw_deaths()  # nobody was at war with b
    assert 'metallurgy' not in a.techs, "a bystander does not inherit the tech"


def test_truce_barters_a_tech_from_richer_to_poorer():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    a.techs = {'farming', 'metallurgy'}
    a.tech_xp = {'farming': 1.0, 'metallurgy': 1.0}
    b.techs = set()
    b.tech_xp = {}
    # a starving colony sues for peace; two fresh houses can truce
    assert sim._propose_truce(a, b), "the truce was struck"
    assert b.techs, "the peace was sealed with a shared technology"
    assert any("to seal the peace" in m for _, m in sim.events)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tech-diffusion tests passed")
