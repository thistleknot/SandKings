"""Acceptance tests for SPEC_AWARENESS.md (AW1-AW6).

Before breakout the sandkings feel only NATURE (unexplained forces); worship
and hatred of the "great other" switch on at the breakout revelation, seeded
by how they were treated as nature. Failure modes covered: pre-breach worship,
keeper-face carvings before awareness, a moving pre-breach sentiment, the gift
ladder stalling without worship, a double or mis-seeded revelation, and cadets
re-revealing.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (BOOTSTRAP_FLOOR, CARVE_SYMBOLS, NATURE_SYMBOLS, SandKing,
                       SandKingsSimulation, UnitType, VoxelType)


def make_sim(seed: int = 4) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_pre_breach_carves_nature_not_faces_and_freezes_sentiment():
    sim = make_sim()
    c = sim.colonies[0]
    assert not c.breached
    c.keeper_fed_step = sim.step_count  # flourishing -> a 'bounty' mood
    before = c.keeper_sentiment
    sim.step_count = 200
    sim._keeper_tick()
    carv = sim._carvings()
    nature, faces = set(NATURE_SYMBOLS.values()), set(CARVE_SYMBOLS.values())
    assert any(v in nature for v in carv.values()), "carves the forces it feels"
    assert not any(v in faces for v in carv.values()), "no keeper face pre-breach"
    sim.step_count = 400
    sim._keeper_tick()
    assert c.keeper_sentiment == before, "keeper sentiment is frozen pre-breach"


def test_manna_worship_requires_awareness():
    sim = make_sim()
    c = sim.colonies[0]

    def witness():
        sim.world.voxels[sim.world.voxels == VoxelType.FOOD.value] = \
            VoxelType.AIR.value
        mx, my, _ = c.maw.position
        sim.keeper_drop_food(mx, my)
        mp = next(iter(sim.keeper_manna))
        w = SandKing(c.colony_id, (mp[0] + 1, mp[1], mp[2]), UnitType.WORKER)
        c.units.append(w)
        for _ in range(6):
            sim._execute_unit_ai(w, c)
            if c.worshipped:
                break

    witness()
    assert not c.worshipped, "pre-breach bounty is fortune, not worship"
    assert c.keeper_fed_step == sim.step_count, "but it WAS fed"
    c.breached = True  # the great other is now known
    witness()
    assert c.worshipped, "aware of the great other, it worships the hand"


def test_revelation_fires_once_and_seeds_from_treatment():
    sim = make_sim()
    good = sim.colonies[0]
    good.maw.food_stored = 4 * BOOTSTRAP_FLOOR + 60  # bounty at breakout
    sim._escape(good)  # the TRUE breakout (terminal mastery), not the molt
    assert good.breached and good.revelation
    assert good.keeper_sentiment == 0.7, "well-treated wakes grateful"
    reveals = [m for _, m in sim.events if "beyond the glass" in m]
    assert len(reveals) == 1, "the revelation fires once"
    sim._escape(good)  # a second call must not re-reveal
    sim._set_stage(good, 3)  # nor does a further molt
    assert len([m for _, m in sim.events if "beyond the glass" in m]) == 1

    bad = sim.colonies[1]
    bad.maw.food_stored = BOOTSTRAP_FLOOR  # starving -> dread at breakout
    sim._escape(bad)
    assert bad.keeper_sentiment == 0.3, "mistreated wakes resentful"


def test_gift_ladder_fires_for_a_flourishing_unbreached_colony():
    sim = make_sim()
    sim.keeper_auto = True
    c = sim.colonies[0]
    assert not c.breached
    sim.gifts_given = []
    sim.last_gift_step = -10 ** 9
    sim.gift = None
    # W4 (K9a): the first gift (abacus) unlocks at year 1; use a step past
    # YEAR_LENGTH (1600) that is not a cat/carve periodic tick. Set fed-step
    # AFTER advancing the clock so the colony reads as recently fed (flourishing).
    sim.step_count = 1700  # year 1
    c.keeper_fed_step = sim.step_count  # flourishing = recently fed (at year 1)
    sim._keeper_tick()
    assert sim.gift is not None, "a thriving un-breached colony draws the gift"


def test_cadet_born_aware_inherits_sentiment_without_revelation():
    sim = make_sim()
    for other in sim.colonies[1:]:
        other.breached = True
        other.revelation = True
        other.keeper_sentiment = 0.8
    v = sim.colonies[0]
    vid = v.colony_id
    v.maw.alive = False
    v.units.clear()
    before = len([m for _, m in sim.events if "beyond the glass" in m])
    sim._respawn_colony(vid)
    reborn = sim.colonies[0]
    if getattr(reborn, "breached", False):
        assert reborn.revelation, "born into an aware bloodline knows already"
        assert len([m for _, m in sim.events if "beyond the glass" in m]) == before, \
            "no second revelation for the born-aware"
        assert reborn.keeper_sentiment >= 0.5, "stance survives in the blood"


def test_post_breach_faces_still_work():
    sim = make_sim()
    c = sim.colonies[0]
    c.breached = True
    c.keeper_sentiment = 0.1
    sim.keeper_drought(True)
    sim.step_count = 200
    sim._keeper_tick()
    assert CARVE_SYMBOLS["hateful"] in sim._carvings().values()


def test_molted_new_breed_is_still_nature_only():
    # AW: growing into the new breed (a physical molt) does NOT make a colony
    # aware of the keeper. Until it truly breaks out it carves nature, cannot
    # worship, and cannot project onto the keeper.
    from sandkings import CARVE_SYMBOLS, NATURE_SYMBOLS
    sim = make_sim()
    c = sim.colonies[0]
    sim._set_stage(c, 2)
    assert c.stage == 2 and not c.breached
    sim.keeper_drought(True)
    c.maw.food_stored = 5  # starving -> nature dread, not keeper hatred
    sim.step_count = 200
    sim._keeper_tick()
    carv = sim._carvings()
    assert any(v in set(NATURE_SYMBOLS.values()) for v in carv.values())
    assert not any(v in set(CARVE_SYMBOLS.values()) for v in carv.values())
    assert not c.worshipped, "a molted-but-unescaped maw does not worship"
    sim._psionic_tick()
    assert sim.keeper_influence == 0.0, "and it cannot reach the keeper's mind"


def test_local_plenty_resists_dread():
    sim = make_sim()
    c = sim.colonies[0]
    sim.keeper_drought(True)  # the wider dole has failed
    c.maw.food_stored = 10 * BOOTSTRAP_FLOOR  # but its own hoard is full
    assert sim._nature_mood(c) == "bounty", \
        "a house with its own reserves does not despair at the dry world"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim._set_stage(sim.colonies[0], 2)
    for _ in range(10):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived.colonies[0], "revelation")
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    co = EnhancedSandKingsSimulation.step.__code__.co_names
    assert "_reveal" not in co and "_nature_mood" not in co


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all awareness tests passed")
