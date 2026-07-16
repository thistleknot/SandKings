"""Acceptance tests for SPEC_METAMORPHOSIS.md (MT1-MT6).

Canon (Wo): the maw's insectoid mobiles pop open into a new bipedal,
four-armed, tool-using breed as it grows - cruelty accelerates it - and
one in a thousand reaches the fully-sentient Shade stage. Failure modes
covered: molt not gated on size, cruelty NOT lowering the threshold, the
Shade stage reachable without machine-mastery, stage 2 unlocking anything
`breached` didn't, the brain ceiling not rising (or `mutate` ignoring it),
events double-firing, cadets not inheriting the stage, and state not
pickling / the evolution sim not staying inert.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (MOLT_FOOD, SHADE_FOOD, STAGE_CEILING, TERMINAL_MASTERY,
                       SandKingsSimulation)


def make_sim(seed: int = 42) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_large_maw_molts_to_stage_two_without_breaching():
    sim = make_sim()
    c = sim.colonies[0]
    assert getattr(c, "stage", 1) == 1, "starts insectoid"
    assert not getattr(c, "breached", False)
    c.maw.food_stored = MOLT_FOOD + 50  # large enough at any sentiment
    sim._metamorphosis_tick()
    assert c.stage == 2, "a large maw molts to the new breed"
    assert not c.breached, "the molt is PHYSICAL - it does not break the glass"
    sim._escape(c)  # only the true breakout (terminal mastery) awakens it
    assert c.breached and c.revelation, "the breakout awakens it to the great other"


def test_cruelty_lowers_the_molt_threshold():
    sim = make_sim()
    devout, cruel = sim.colonies[0], sim.colonies[1]
    # equal size, below the devout threshold but above the mistreated one
    mid = MOLT_FOOD * 0.75  # 315: >252 (f=0.6) yet <420 (f=1.0)
    devout.keeper_sentiment = 1.0
    cruel.keeper_sentiment = 0.0
    devout.maw.food_stored = mid
    cruel.maw.food_stored = mid
    sim._metamorphosis_tick()
    assert cruel.stage == 2, "the mistreated maw molts sooner (Kress's cruelty)"
    assert devout.stage == 1, "the reverent one is not yet ready"


def test_shade_stage_needs_size_and_machine_mastery():
    sim = make_sim()
    c = sim.colonies[0]
    # a huge stage-2 maw that never mastered the terminal stays stage 2
    sim._set_stage(c, 2)
    c.terminal_uses = 0
    c.maw.food_stored = SHADE_FOOD + 100
    sim._metamorphosis_tick()
    assert c.stage == 2, "size alone does not make a Shade"
    # give it mastery -> it crosses the final plateau
    c.terminal_uses = TERMINAL_MASTERY
    sim._metamorphosis_tick()
    assert c.stage == 3, "large AND machine-mastered -> Shade"


def test_metamorphosis_is_physical_and_grants_no_awareness():
    # AW/MT1 (revised): growing into the new breed is a PHYSICAL molt; it does
    # NOT breach the glass or grant keeper-awareness. Only the true breakout
    # (terminal mastery, _escape) does. So capability gates keep keying on
    # `breached`, which the molt no longer sets.
    import inspect

    import sandkings
    src = inspect.getsource(sandkings)
    assert "getattr(colony, 'breached'" in src or \
        "getattr(colony, \"breached\"" in src, "capabilities gate on breached"
    sim = make_sim()
    c = sim.colonies[0]
    sim._set_stage(c, 2)
    assert c.stage == 2 and not getattr(c, "breached", False), \
        "the molt is physical only - no awareness"
    sim._escape(c)
    assert c.breached is True, "only the breakout past the glass awakens it"


def test_brain_ceiling_rises_with_stage_and_mutate_respects_it():
    sim = make_sim()
    c = sim.colonies[0]
    assert c.genome.brain_ceiling == STAGE_CEILING[1]
    sim._set_stage(c, 2)
    assert c.genome.brain_ceiling == STAGE_CEILING[2]
    sim._set_stage(c, 3)
    assert c.genome.brain_ceiling == STAGE_CEILING[3]

    # a stage-1 ceiling clamps brain_hidden; a raised ceiling lets it grow
    random.seed(1); np.random.seed(1)
    capped = sim.colonies[1].genome
    capped.brain_ceiling = STAGE_CEILING[1]
    capped.brain_hidden = STAGE_CEILING[1]
    g = capped
    widest_capped = g.brain_hidden
    for _ in range(200):
        g = g.mutate(0.5)
        widest_capped = max(widest_capped, g.brain_hidden)
    assert widest_capped <= STAGE_CEILING[1], "stage-1 brain never exceeds 88"

    random.seed(1); np.random.seed(1)
    freed = sim.colonies[2].genome
    freed.brain_ceiling = STAGE_CEILING[3]
    freed.brain_hidden = STAGE_CEILING[1]
    g = freed
    widest_freed = g.brain_hidden
    for _ in range(200):
        g = g.mutate(0.5)
        widest_freed = max(widest_freed, g.brain_hidden)
    assert widest_freed > STAGE_CEILING[1], "a Shade evolves a bigger brain"
    assert widest_freed <= STAGE_CEILING[3]


def test_molt_and_shade_events_fire_once_each():
    sim = make_sim()
    c = sim.colonies[0]
    c.maw.food_stored = MOLT_FOOD + 50
    sim._metamorphosis_tick()
    sim._metamorphosis_tick()  # already stage 2 - must not re-announce
    molts = [m for _, m in sim.events if "split open" in m]
    assert len(molts) == 1, "the molt is announced exactly once"

    c.terminal_uses = TERMINAL_MASTERY
    c.maw.food_stored = SHADE_FOOD + 50
    sim._metamorphosis_tick()
    sim._metamorphosis_tick()  # already stage 3 - must not re-announce
    shades = [m for _, m in sim.events if "Shade stage" in m]
    assert len(shades) == 1, "the Shade transition is announced exactly once"


def test_cadet_branches_inherit_the_stage():
    sim = make_sim()
    victim_id = sim.colonies[0].colony_id
    # every surviving house molted to the new breed AND broke out (escaped);
    # the cadet is born with both the body and the awareness in its blood
    for other in sim.colonies[1:]:
        sim._set_stage(other, 2)   # physical molt
        sim._escape(other)         # AW: the true breakout awakens it
    v = sim.colonies[0]
    v.maw.alive = False
    v.units.clear()
    sim._respawn_colony(victim_id)
    reborn = sim.colonies[0]
    assert getattr(reborn, "stage", 1) >= 2, "the molt survives in the bloodline"
    assert reborn.breached, "and the awakening (escape) survives too"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim._set_stage(sim.colonies[0], 2)
    for _ in range(15):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived.colonies[0], "stage")
    assert revived.colonies[0].genome.brain_ceiling >= STAGE_CEILING[1]
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_metamorphosis_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all metamorphosis tests passed")
