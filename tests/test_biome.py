"""Acceptance tests for SPEC_BIOME.md (BI1-BI7) - the closed biome & the panel.

Weather emerges from a global water budget and the keeper's sunlight, set behind
the glass. Failure modes covered: the biome changing the DEFAULT balance
(breaking existing tests), the water cycle not responding to sun/reservoir, no
weather emerging at the extremes, low water not biting the dole/crops, and the
panel failing while the terrarium is turned.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (DRY_THRESHOLD, SUN_MAX, SUN_MIN, WATER_LEVEL_DEFAULT,
                       SandKingsSimulation)


def make_sim(seed: int = 5, harsh: bool = False) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    sim.harsh = harsh
    return sim


def test_defaults_are_neutral():
    sim = make_sim(harsh=True)
    assert sim.water_level == WATER_LEVEL_DEFAULT
    sim.step_count = 1  # season 0 (Flood): dole 1.0
    assert sim.dole_factor() == 1.0, "default water does not cut the dole"
    assert sim._biome_growth_units() == 1, "default crop growth unchanged"
    assert not sim._is_dry()


def test_sun_evaporates_and_reservoir_recharges():
    sim = make_sim()
    sim.keeper_set_sun(SUN_MAX)  # long, drying days
    start = sim.water_level
    for k in range(1, 200):
        sim.step_count = k
        sim._biome_tick()
    assert sim.water_level < start, "the sun evaporates the budget"
    sim.keeper_set_water(0.9)  # fill the reservoir, short days
    sim.keeper_set_sun(SUN_MIN)
    low = sim.water_level
    for k in range(200, 600):
        sim.step_count = k
        sim._biome_tick()
    assert sim.water_level > low, "the reservoir recharges"


def test_wet_emerges_a_flood():
    sim = make_sim()
    sim.keeper_set_water(1.0)
    sim.water_level = 0.9
    fired = False
    for k in range(1, 500):
        sim.step_count = k
        sim._biome_tick()
        if getattr(sim, 'flood_until', 0) > sim.step_count:
            fired = True
            break
    assert fired, "an abundant reservoir spills a flood"


def test_dry_and_hot_emerges_heat():
    sim = make_sim()
    sim.keeper_set_water(0.0)
    sim.water_level = 0.1
    sim.keeper_set_sun(SUN_MAX)
    fired = False
    for k in range(1, 700):
        sim.step_count = k
        sim._biome_tick()
        if getattr(sim, 'arena_heat_until', 0) > sim.step_count:
            fired = True
            break
    assert fired, "low water under a high sun bakes the sands"


def test_short_days_emerge_a_chill():
    sim = make_sim()
    sim.keeper_set_sun(SUN_MIN)
    fired = False
    for k in range(1, 700):
        sim.step_count = k
        sim._biome_tick()
        if getattr(sim, 'arena_cold_until', 0) > sim.step_count:
            fired = True
            break
    assert fired, "short days bring a creeping cold"


def test_low_water_is_dry_and_cuts_dole_and_stalls_crops():
    sim = make_sim(harsh=True)
    sim.water_level = 0.1
    assert sim._is_dry()
    sim.step_count = 1  # Flood season - would be dole 1.0 at full water
    assert sim.dole_factor() < 1.0, "low water is a soft drought"
    assert sim._biome_growth_units() == 0, "crops stall when dry"
    assert DRY_THRESHOLD == 0.35


def test_panel_survives_the_turning():
    sim = make_sim()
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    sim.keeper_set_water(0.2)
    sim.keeper_set_sun(SUN_MAX)
    assert sim.water_target == 0.2 and sim.sun_hours == SUN_MAX, \
        "the diffuser is beyond the glass - the panel works when bound"
    before = len(sim._fauna())
    sim.keeper_release('spider')
    assert len(sim._fauna()) == before, "the HAND is still bound (PS5)"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim.keeper_set_sun(SUN_MAX)
    for _ in range(15):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived, "water_level")
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_biome_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all biome tests passed")
