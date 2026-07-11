"""Acceptance tests for SPEC_TECH.md (TE1-TE6) - the tech foundation.

Foreign gifts (abacus/watch/calculator/pi) and native techs (fire, ...). T1 lays
the data model, revises the ladder, and recognises fire. Failure modes covered:
tech state not pickling/inheriting, the ladder order/pi-only-escape breaking,
fire not recognised, the registry missing an id, and the state not being
default-neutral / the evolution sim not inert.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (GIFT_LADDER, TECH_FOREIGN, TECH_NATIVE, TECH_REGISTRY,
                       SandKing, SandKingsSimulation, UnitType)


def make_sim(seed: int = 5) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def _worker(sim, colony):
    mx, my, mz = colony.maw.position
    u = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    colony.units.append(u)
    return u


def test_registry_covers_every_tech():
    assert GIFT_LADDER == ('abacus', 'watch', 'calculator', 'pi')
    for t in TECH_FOREIGN:
        assert TECH_REGISTRY[t]['kind'] == 'foreign'
    for t in TECH_NATIVE:
        assert TECH_REGISTRY[t]['kind'] == 'native'
    assert set(TECH_REGISTRY) == set(TECH_FOREIGN) | set(TECH_NATIVE)


def test_tech_state_defaults_and_pickles_and_inherits():
    import pickle
    sim = make_sim()
    c = sim.colonies[0]
    assert c.techs == set() and c.tech_xp == {}, "empty by default"
    c.techs.add('farming')
    c.tech_xp['farming'] = 0.5
    revived = pickle.loads(pickle.dumps(sim))
    assert revived.colonies[0].techs == {'farming'}
    # single-parent respawn copies the bloodline's techs
    for other in sim.colonies[1:]:
        other.techs = {'metallurgy'}
    v = sim.colonies[0]
    v.maw.alive = False
    v.units.clear()
    sim._respawn_colony(v.colony_id)
    assert 'metallurgy' in sim.colonies[0].techs, "tech survives in the blood"


def test_foreign_ladder_grants_tech_and_only_pi_escapes():
    from machines import VM_FUEL
    sim = make_sim()
    c = sim.colonies[0]
    u = _worker(sim, c)
    sim._claim_gift(c, 'abacus', u)
    assert 'abacus' in c.techs and c.machine_arc == 'known'
    assert not getattr(c, 'controllers', None), "abacus grants no machine"
    sim._claim_gift(c, 'calculator', u)
    assert 'calculator' in c.techs
    assert c.controllers and max(ct.fuel_cap for ct in c.controllers) == VM_FUEL, \
        "calculator is a plain VM - cannot reach the terminal"
    sim._claim_gift(c, 'pi', u)
    assert 'pi' in c.techs
    assert any(ct.fuel_cap > VM_FUEL for ct in c.controllers), \
        "ONLY the pi yields a terminal-capable controller (the escape key)"


def test_fielding_a_torch_grants_fire():
    sim = make_sim()
    c = sim.colonies[0]
    assert 'fire' not in c.techs
    c.at_war = True
    c.wood = 2
    c.bone = 0  # so the spear doesn't consume the wood first
    c.maw.food_stored = 500
    c.spawn_unit(UnitType.SOLDIER, sim.step_count)
    assert 'fire' in c.techs, "a torch-bearing soldier IS the fire tech"


def test_build_state_exposes_techs():
    from dashboard import build_state
    sim = make_sim()
    sim.colonies[0].techs = {'fire', 'farming'}
    state = build_state(sim)
    col = next(c for c in state['colonies'] if c['id'] == 0)
    assert col['techs'] == ['farming', 'fire'], "sorted techs surfaced"


def test_default_neutral_and_evolution_inert():
    import pickle
    sim = make_sim()
    for _ in range(15):
        sim.step()  # no tech granted -> nothing changes
    assert all(c.techs == set() for c in sim.colonies if c.is_alive())
    pickle.loads(pickle.dumps(sim)).step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_grant_tech" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tech tests passed")
