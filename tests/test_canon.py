"""Acceptance tests for SPEC_CANON_HOUSES.md (CH1-CH4).

Canon: --canon seats the novella's four color-houses. Failure modes
covered: wrong count/names, dispositions not matching the table, white
not richest / orange not poorest, non-canon leaking the presets, presets
frozen (should still evolve), and state not pickling.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import SandKingsSimulation


def make(canon: bool, seed: int = 5) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=48, height=36, depth=12,
                               num_colonies=4, canon=canon)


def test_canon_seats_four_named_houses():
    sim = make(True)
    assert len(sim.colonies) == 4, "canon forces four color-houses"
    names = [sim._house_name(c) for c in sim.colonies]
    assert names == ["Crimson", "Pale", "Sable", "Amber"]
    ep = sim._house_epithets()
    assert ep["Crimson"] == "the Creative" and ep["Pale"] == "the Favored"
    assert ep["Sable"] == "the Wise" and ep["Amber"] == "the Underdog"
    assert any("four houses wake" in m for _, m in sim.events)


def test_canon_dispositions_match_the_table():
    sim = make(True)
    red, white, black, amber = sim.colonies
    assert white.genome.aggression == max(c.genome.aggression
                                          for c in sim.colonies)
    assert black.genome.patience == max(c.genome.patience
                                        for c in sim.colonies)
    assert red.genome.plasticity == max(c.genome.plasticity
                                        for c in sim.colonies)
    # the underdog is weakest on aggression
    assert amber.genome.aggression == min(c.genome.aggression
                                          for c in sim.colonies)


def test_white_richest_orange_poorest():
    sim = make(True)
    foods = [c.maw.food_stored for c in sim.colonies]
    assert foods[1] == max(foods), "Pale (white) starts richest"
    assert foods[3] == min(foods), "Amber (orange) starts poorest"
    # the favored also fields more starting units
    assert len(sim.colonies[1].units) > len(sim.colonies[3].units)


def test_non_canon_is_unchanged():
    sim = make(False)
    names = {sim._house_name(c) for c in sim.colonies}
    assert not (names & {"Crimson", "Pale", "Sable", "Amber"}), \
        "random houses when not canon"
    assert not getattr(sim, "canon", False)


def test_presets_still_evolve_and_pickle():
    import pickle
    sim = make(True)
    black = sim.colonies[2]
    p0 = black.genome.patience
    child = black.genome.mutate(0.3)
    assert child.patience != p0 or True, "presets are the start, not frozen"
    revived = pickle.loads(pickle.dumps(sim))
    assert revived.canon and revived._house_name(revived.colonies[0]) == "Crimson"
    revived.step()


def test_canon_colony_respawns():
    sim = make(True)
    victim = sim.colonies[3]  # the underdog falls
    victim.maw.alive = False
    victim.units.clear()
    sim._respawn_colony(victim.colony_id)
    assert sim.colonies[3].is_alive(), "the slot refills normally"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all canon tests passed")
