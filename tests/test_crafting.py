"""Acceptance for SPEC_TECH TE13 - materials -> crafting + caltrops.

The keeper drops raw materials; a house with the tech crafts tools (else scrap).
Failure modes: crafting without the tech, a crafted item not buffing soldiers, a
copper-pipe cannon not unlocking the siege, tacks not scattering damaging
caltrops, and a bound keeper still crafting.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (SandKing, SandKingsSimulation, UnitType)


def make_sim(seed: int = 11) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def _nearest(sim, x, y):
    return min(sim.colonies, key=lambda c: (c.maw.position[0] - x) ** 2
              + (c.maw.position[1] - y) ** 2)


def test_material_plus_tech_crafts_and_buffs_soldiers():
    sim = make_sim()
    mx, my, _ = sim.colonies[0].maw.position
    c = _nearest(sim, mx, my)
    c.techs = {'metallurgy'}
    c.tech_xp = {'metallurgy': 1.0}
    c.at_war = True
    c.maw.food_stored = 999
    c.spawn_unit(UnitType.SOLDIER, 0)
    base = c.units[-1].attack
    sim.keeper_material('toothpick', mx, my)
    assert 'spear' in c.crafted, "toothpick + metallurgy -> spear"
    c.spawn_unit(UnitType.SOLDIER, 0)
    assert c.units[-1].attack > base, "the crafted spear arms the soldier"


def test_without_the_tech_it_is_scrap():
    sim = make_sim()
    mx, my, _ = sim.colonies[0].maw.position
    c = _nearest(sim, mx, my)
    c.techs = set()  # no metallurgy
    sim.keeper_material('toothpick', mx, my)
    assert not c.crafted, "a house without the craft makes only scrap"
    assert any("inert scrap" in m for _, m in sim.events)


def test_copper_pipe_cannon_unlocks_the_siege():
    sim = make_sim()
    mx, my, _ = sim.colonies[0].maw.position
    c = _nearest(sim, mx, my)
    c.techs = {'metallurgy'}
    c.tech_xp = {'metallurgy': 1.0}
    sim.keeper_material('copper_pipe', mx, my)
    assert 'cannon' in c.crafted
    assert 'catapult' in c.techs, "a copper-pipe cannon IS a siege engine"


def test_tacks_scatter_caltrops_that_prick():
    sim = make_sim()
    sim.keeper_material('tacks', 20, 15)
    assert getattr(sim, 'caltrops', None), "tacks became caltrops"
    pos = next(iter(sim.caltrops))
    colony = sim.colonies[0]
    u = SandKing(colony.colony_id, pos, UnitType.WORKER)
    colony.units.append(u)
    hp = u.health
    sim._caltrop_tick()
    assert u.health < hp or u not in colony.units, "a unit on a caltrop is pricked"


def test_bound_keeper_crafts_nothing_and_state_pickles():
    import pickle
    sim = make_sim()
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    mx, my, _ = sim.colonies[0].maw.position
    _nearest(sim, mx, my).techs = {'metallurgy'}
    sim.keeper_material('toothpick', mx, my)
    assert not any(c.crafted for c in sim.colonies), "the bound god crafts nothing"
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived.colonies[0], 'crafted')
    revived.step()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all crafting tests passed")
