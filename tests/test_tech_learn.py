"""Acceptance tests for SPEC_TECH TE7-TE9 - native tech acquisition.

Houses learn native tech by PRACTICE (doing), OBSERVATION (watching a neighbor -
faster from a friend than a foe), and by spending GRAINS (the currency's first
sink). Failure modes covered: practice not accruing/learning, observation
ignoring range or relationship, grains not spent, proficiency not surfaced, and
the engine not staying inert in the evolution sim.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import TECH_LEARN_XP, SandKingsSimulation


def make_sim(seed: int = 6) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def _ally(sim, a, b):
    sim._diplomacy()
    sim.diplomacy.allied[frozenset((a, b))] = True


def test_practice_accrues_and_learns_at_the_threshold():
    sim = make_sim()
    c = sim.colonies[0]
    assert 'farming' not in c.techs
    for _ in range(20):  # 20 * 0.02 = 0.4 > TECH_LEARN_XP
        sim._practice(c, 'farming')
    assert 'farming' in c.techs and c.tech_xp['farming'] >= TECH_LEARN_XP


def test_observe_learns_from_a_neighbor_in_range():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    b.techs = {'farming'}
    b.tech_xp = {'farming': 1.0}
    z = a.maw.position[2]
    a.maw.position = (20, 15, z)
    b.maw.position = (22, 15, z)  # within TECH_OBSERVE_RANGE
    _ally(sim, a.colony_id, b.colony_id)  # friends teach fast
    for _ in range(12):
        sim._tech_tick()
    assert 'farming' in a.techs, "learned by watching an ally"


def test_observe_is_gated_by_range():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    b.techs = {'metallurgy'}
    b.tech_xp = {'metallurgy': 1.0}
    z = a.maw.position[2]
    a.maw.position = (5, 5, z)
    b.maw.position = (42, 30, z)  # far beyond range
    for _ in range(30):
        sim._tech_tick()
    assert 'metallurgy' not in a.techs, "too far to observe"


def test_allies_teach_faster_than_foes():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    b.techs = {'plow'}
    b.tech_xp = {'plow': 1.0}
    z = a.maw.position[2]
    a.maw.position = (20, 15, z)
    b.maw.position = (21, 15, z)
    for _ in range(5):   # default: hostile -> weight 0.25
        sim._tech_tick()
    hostile_xp = a.tech_xp.get('plow', 0.0)
    a.tech_xp['plow'] = 0.0
    a.techs.discard('plow')
    _ally(sim, a.colony_id, b.colony_id)
    for _ in range(5):   # allied -> weight 1.0
        sim._tech_tick()
    assert a.tech_xp.get('plow', 0.0) > hostile_xp, "you learn faster from a friend"


def test_grains_buy_research_and_debit_currency():
    sim = make_sim()
    c = sim.colonies[0]
    c.currency = 20.0
    c.tech_xp = {'metallurgy': 0.1}  # partway - a valid research target
    # isolate it so observation can't also feed metallurgy
    z = c.maw.position[2]
    c.maw.position = (5, 5, z)
    before = c.currency
    sim._tech_tick()
    assert c.currency < before, "grains spent on research (the sink)"
    assert c.tech_xp['metallurgy'] > 0.1, "research advanced"


def test_proficiency_surfaced_and_evolution_inert():
    from dashboard import build_state
    sim = make_sim()
    sim.colonies[0].techs = {'farming'}
    sim.colonies[0].tech_xp = {'farming': 0.6}
    col = next(c for c in build_state(sim)['colonies'] if c['id'] == 0)
    assert col['tech_xp'].get('farming') == 0.6
    import pickle
    pickle.loads(pickle.dumps(sim)).step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_tech_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tech-learn tests passed")
