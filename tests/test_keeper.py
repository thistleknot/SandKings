"""Acceptance tests for SPEC_KEEPER.md (K1-K12).

Failure modes covered: worship without a witnessed miracle, wrath
without prior faith, the dole surviving a drought, the cat in random
spawn rolls, the gift ladder skipping rungs, terminal commands
working without a pi, breach firing twice, awakened anchors leaking
to un-breached minds, the keeper's words heard by the deaf.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    FAUNA, GIFT_LADDER, KEEPER_MEMORY, SandKing, SandKingsSimulation,
    TERMINAL_MASTERY, TERMINAL_UNLOCK, UnitType, VoxelType,
)


def make_sim(seed: int = 88) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    sim.keeper_auto = False  # tests drive the keeper by hand
    return sim


def test_manna_attribution_not_the_dole():
    sim = make_sim()
    colony = sim.colonies[0]
    assert sim.keeper_attitude(colony) == 'none'
    # dole food gives no attribution
    sim._feed_terrarium()
    assert not colony.worshipped
    # a keeper drop, eaten, reveals the god (field cleared of dole food
    # first - the grab must find the manna, not the scatter). AW3: worship of
    # the hand only once the colony is AWARE of the great other (breached).
    colony.breached = True
    sim.world.voxels[sim.world.voxels == VoxelType.FOOD.value] = \
        VoxelType.AIR.value
    mx, my, _ = colony.maw.position
    sim.keeper_drop_food(mx, my)
    manna_pos = next(iter(sim.keeper_manna))
    worker = SandKing(colony.colony_id,
                      (manna_pos[0] + 1, manna_pos[1], manna_pos[2]),
                      UnitType.WORKER)
    colony.units.append(worker)
    for _ in range(6):  # a few grabs: each eats one manna voxel
        sim._execute_unit_ai(worker, colony)
        if colony.worshipped:
            break
    assert colony.worshipped, "the miracle was witnessed"
    assert sim.keeper_attitude(colony) == 'reverent'
    assert any("worship" in m for _, m in sim.events)


def test_drought_zeroes_dole_and_wrath_requires_faith():
    sim = make_sim()
    faithful, heathen = sim.colonies[0], sim.colonies[1]
    faithful.worshipped = True
    sim.keeper_drought(True)
    assert sim.dole_factor() == 0.0, "the god withholds everything"
    assert sim.keeper_attitude(faithful) == 'wrathful'
    assert sim.keeper_attitude(heathen) == 'none', \
        "betrayal requires prior faith"
    # the wrathful colony's carved sentiment curdles (F3, GRADUAL - it
    # passes through wary before the carve turns hateful and logs)
    bands = {sim._update_sentiment(faithful) for _ in range(12)}
    assert 'hateful' in bands
    assert any("hateful mask" in m for _, m in sim.events)
    sim.keeper_drought(False)
    assert sim.dole_factor() > 0.0
    assert sim.keeper_attitude(faithful) == 'none'


def test_cat_is_keeper_only_and_release_bypasses_incursion_rule():
    assert FAUNA['cat'][0] == 0.0 and FAUNA['cricket'][0] == 0.0
    sim = make_sim()
    sim._spawn_incursion()  # a natural incursion is active
    before = len(sim.fauna)
    sim.keeper_release('cricket')  # the keeper is above the rules
    assert len(sim.fauna) > before
    sim.keeper_release_cat()
    assert any(b.species == 'cat' for b in sim.fauna)


def test_cat_slain_triggers_grief_script():
    sim = make_sim(seed=7)
    sim.keeper_auto = True
    sim.keeper_release_cat()
    cat = next(b for b in sim.fauna if b.species == 'cat')
    cat.health = 1
    cat.provoked = True
    x, y, z = cat.position
    for dx in (-1, 1):
        s = SandKing(sim.colonies[0].colony_id, (x + dx, y, z),
                     UnitType.SOLDIER)
        sim.colonies[0].units.append(s)
    sim._beast_combat(cat)
    assert cat not in sim.fauna, "the cat is slain"
    assert getattr(sim, 'drought', False), "grief becomes drought"
    assert sim.keeper_grief_until > sim.step_count


def test_gift_ladder_advances_the_arc():
    sim = make_sim()
    colony = sim.colonies[0]
    mx, my, mz = colony.maw.position
    worker = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    colony.units.append(worker)
    for kind, arc in (('watch', 'known'), ('calculator', 'claimed'),
                      ('pi', 'claimed')):
        sim.keeper_gift(kind, pos=(worker.position[0], worker.position[1]))
        gx, gy, gz = sim.gift[0]
        worker.position = (gx, gy, gz)
        sim._keeper_tick()
        assert sim.gift is None, f"{kind} claimed"
        assert colony.machine_arc == arc
    from machines import PI_FUEL, VM_FUEL
    assert len(colony.controllers) == 2
    assert colony.controllers[-1].fuel_cap == PI_FUEL > VM_FUEL
    # default ladder order with no kind given (TE3: abacus first)
    sim2 = make_sim()
    sim2.keeper_gift()
    assert sim2.gifts_given == ['abacus']
    sim2.gift = None
    sim2.keeper_gift()
    assert sim2.gifts_given == ['abacus', 'watch']


def test_terminal_commands_and_the_breach_fires_once():
    from machines import Controller, PI_FUEL
    sim = make_sim()
    colony = sim.colonies[0]
    colony.controllers = [Controller(colony.colony_id, fuel=PI_FUEL)]
    colony.machine_arc = 'claimed'
    # locked until the pi has run enough scan cycles
    sim._actuate(colony, 7, 1)
    assert colony.terminal_uses == 0, "the terminal is still locked"
    colony.controllers[0].operate_ticks = TERMINAL_UNLOCK
    # ls /world/food: the machine reads the terrarium's files
    sim.world.voxels[sim.world.voxels == VoxelType.FOOD.value] = \
        VoxelType.AIR.value
    fx, fy = 10, 10
    fz = sim.world.surface_z(fx, fy) + 1
    sim.world.voxels[fx, fy, fz] = VoxelType.FOOD.value
    sim._actuate(colony, 7, 1)
    assert colony.terminal_uses == 1
    assert (fx, fy, fz) in colony.known_food
    # echo: the machine carves
    sim._actuate(colony, 7, 2)
    from sandkings import CARVE_SYMBOLS
    assert CARVE_SYMBOLS['machine'] in sim._carvings().values()
    colony.terminal_uses = TERMINAL_MASTERY - 1
    sim._actuate(colony, 7, 1)
    assert colony.breached, "mastery breaches the glass"
    breaches = [m for _, m in sim.events if "no longer a wall" in m]
    assert len(breaches) == 1
    sim._actuate(colony, 7, 1)
    breaches = [m for _, m in sim.events if "no longer a wall" in m]
    assert len(breaches) == 1, "the breach fires exactly once"


def test_awakened_anchors_gate_on_breach():
    from hive_mind_monitor import build_context, compose_utterance, ground_truths
    sim = make_sim()
    colony = sim.colonies[0]
    unit = SandKing(colony.colony_id, colony.maw.position, UnitType.WORKER)
    unit.thought = "hunger"
    colony.units.append(unit)
    truths = ground_truths(build_context(unit, colony, sim))
    assert not (truths['self'] or truths['god'] or truths['beyond']
                or truths['speak']), "words before minds: never"
    assert compose_utterance(unit, colony, sim) == ""
    colony.breached = True
    colony.keeper_fed_step = sim.step_count  # the god is present
    unit.spoken_to_step = sim.step_count
    truths = ground_truths(build_context(unit, colony, sim))
    assert truths['self'] and truths['god'] and truths['beyond'] \
        and truths['speak']
    utterance = compose_utterance(unit, colony, sim)
    assert "self" in utterance and "beyond" in utterance


def test_keeper_speak_heard_only_by_the_awakened():
    sim = make_sim()
    colony = sim.colonies[0]
    unit = SandKing(colony.colony_id, colony.maw.position, UnitType.WORKER)
    colony.units.append(unit)
    assert not sim.keeper_speak(unit), "words fall as noise"
    assert any("noise" in m for _, m in sim.events)
    colony.breached = True
    assert sim.keeper_speak(unit), "the awakened hear"
    assert unit.spoken_to_step == sim.step_count
    assert sim.keeper_attitude(colony) == 'reverent', "grace by word"
    assert any("SPEAKS" in m for _, m in sim.events)


def test_carvings_match_state_and_purge():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.breached = True  # AW1: keeper-face carvings need awareness
    colony.worshipped = True
    sim.keeper_drought(True)
    colony.keeper_sentiment = 0.1  # already soured (gradual band -> hateful)
    sim.step_count = 200  # carve tick
    sim._keeper_tick()
    from sandkings import CARVE_SYMBOLS
    assert CARVE_SYMBOLS['hateful'] in sim._carvings().values()
    pos = next(iter(sim.carvings))
    sim.world.voxels[pos] = VoxelType.AIR.value  # disturb the sand
    sim.step_count = 400
    sim._keeper_tick()
    assert pos not in sim.carvings, "disturbed sand forgets"


def test_keeper_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim.keeper_drop_food(24, 18)
    sim.keeper_gift('watch')
    colony = sim.colonies[0]
    colony.worshipped = True
    colony.breached = True
    for _ in range(20):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert revived.colonies[0].breached
    assert isinstance(revived._manna(), set)
    assert isinstance(revived._carvings(), dict)
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_keeper_tick' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all keeper tests passed")
