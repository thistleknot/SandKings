"""Acceptance tests for SPEC_PSIONIC.md (PS1-PS6) — the terrarium reaches back.

Canon (the ending): a large, awakened maw projects emotion onto the keeper,
that projection drives his cruelty, and a hateful Shade finally TURNS the
terrarium on its god - the hand will not move. Failure modes covered:
stage-1 insectoids projecting anything, wrong valence sign, projection not
scaling with stage or size, mis-banded descriptor, the turning double-firing
or firing below the Shade/hate threshold, bound verbs still acting, the
auto-keeper NOT biased by dread, and state not pickling / evolution inert.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (PSIONIC_DREAD, PSIONIC_FLOOR, PSIONIC_TURN_SENT,
                       SandKingsSimulation)


def make_sim(seed: int = 7) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def pad(colony, n: int):
    """Force a colony's population count (psionic reach reads len(units))."""
    base = colony.units[0] if colony.units else object()
    colony.units = [base] * n


def only_awaken(sim, idx: int, stage: int, sentiment: float, pop: int = 30):
    for i, c in enumerate(sim.colonies):
        c.stage = 1
    c = sim.colonies[idx]
    c.stage = stage
    c.keeper_sentiment = sentiment
    pad(c, pop)
    return c


def test_only_the_awakened_project():
    sim = make_sim()
    for c in sim.colonies:
        c.stage = 1
        c.keeper_sentiment = 0.0  # hateful, but insectoid -> reaches nothing
    sim._psionic_tick()
    assert sim.keeper_influence == 0.0, "stage-1 colonies project nothing"


def test_valence_sign_tracks_sentiment():
    sim = make_sim()
    only_awaken(sim, 0, stage=2, sentiment=0.0)  # hateful
    sim._psionic_tick()
    assert sim.keeper_influence < 0, "a hateful awakened maw projects dread"
    only_awaken(sim, 0, stage=2, sentiment=1.0)  # devout
    sim._psionic_tick()
    assert sim.keeper_influence > 0, "a devout awakened maw projects calm"


def test_projection_scales_with_stage_and_size():
    sim = make_sim()
    # equal size + sentiment; a Shade (stage 3) reaches harder than the new
    # breed (stage 2). sentiment 0.3 keeps it below the turning threshold.
    only_awaken(sim, 0, stage=2, sentiment=0.3, pop=30)
    sim._psionic_tick()
    inf_stage2 = abs(sim.keeper_influence)
    only_awaken(sim, 0, stage=3, sentiment=0.3, pop=30)
    sim._psionic_tick()
    inf_stage3 = abs(sim.keeper_influence)
    assert inf_stage3 > inf_stage2, "a Shade projects harder than the new breed"

    # equal stage + sentiment; more mobiles reach harder (until saturation)
    only_awaken(sim, 0, stage=2, sentiment=0.3, pop=3)
    sim._psionic_tick()
    inf_small = abs(sim.keeper_influence)
    only_awaken(sim, 0, stage=2, sentiment=0.3, pop=15)
    sim._psionic_tick()
    inf_big = abs(sim.keeper_influence)
    assert inf_big > inf_small, "a bigger maw reaches harder"


def test_influence_word_bands():
    sim = make_sim()
    for val, expect in [(-0.7, "a hunger not your own"),
                        (-0.3, "a creeping dread"),
                        (0.0, ""),
                        (0.3, "a faint contentment"),
                        (0.8, "an unearned calm")]:
        sim.keeper_influence = val
        assert sim.keeper_influence_word() == expect, f"band at {val}"
    # the floor is silent
    sim.keeper_influence = PSIONIC_FLOOR / 2
    assert sim.keeper_influence_word() == ""


def test_the_turning_fires_once_when_a_shade_hates():
    sim = make_sim()
    # a Shade that is only wary does NOT turn
    only_awaken(sim, 0, stage=3, sentiment=PSIONIC_TURN_SENT + 0.1)
    sim._psionic_tick()
    assert not getattr(sim, "keeper_bound", False), "a wary Shade does not turn"
    # curdle it to hatred -> it binds the god, once
    sim.colonies[0].keeper_sentiment = 0.1
    sim._psionic_tick()
    sim._psionic_tick()  # latched - must not re-announce
    assert sim.keeper_bound is True
    assert sim.keeper_bound_by == sim._house_name(sim.colonies[0])
    turns = [m for _, m in sim.events if "turns on its god" in m]
    assert len(turns) == 1, "the turning is announced exactly once"


def test_bound_god_loses_the_wand():
    sim = make_sim()
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    # feed
    before_manna = len(sim._manna())
    sim.keeper_drop_food(sim.world.width // 2, sim.world.height // 2)
    assert len(sim._manna()) == before_manna, "the bound god cannot feed"
    # withhold
    sim.keeper_drought(True)
    assert not getattr(sim, "drought", False), "the bound god cannot inflict"
    # gift
    sim.keeper_gift("watch")
    assert getattr(sim, "gift", None) is None, "the bound god cannot gift"
    # loose predators
    before_fauna = len(sim._fauna())
    sim.keeper_release("cricket")
    assert len(sim._fauna()) == before_fauna, "the bound god cannot loose beasts"
    # the refusal is logged exactly once
    stayed = [m for _, m in sim.events if "hand will not move" in m]
    assert len(stayed) == 1
    # but the god may still plead: converse survives
    c = sim.colonies[0]
    c.breached = True
    if not c.units:
        pad(c, 1)
    reply = sim.converse(c.colony_id, "peace")
    assert reply["understood"], "a bound god may still speak"


def test_dread_biases_the_auto_keeper():
    sim = make_sim()
    sim.keeper_auto = True
    sim.drought = False
    # a large, hateful new breed (stage 2, not a Shade) projects strong dread
    only_awaken(sim, 0, stage=2, sentiment=0.0, pop=30)
    sim._psionic_tick()
    assert sim.keeper_influence <= PSIONIC_DREAD, "strong dread projected"
    assert sim.drought is True, "the god, gripped by a fear not his own, withholds"
    assert not getattr(sim, "keeper_bound", False), "a new breed does not bind"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    only_awaken(sim, 0, stage=2, sentiment=0.2)
    for _ in range(12):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived, "keeper_influence")
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_psionic_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all psionic tests passed")
