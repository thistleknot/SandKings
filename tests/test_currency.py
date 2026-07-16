"""Acceptance tests for SPEC_CURRENCY.md (CU1-CU5).

Failure modes covered: an accurate forecast minting nothing, a wild one
minting anyway, scoring before the target step, a dead colony scoring,
the forecast not clearing, the ledger not accumulating to the house/sim
totals, and the ledger not pickling.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import GRAIN_MINT, GRAIN_SCALE, SandKingsSimulation


def make_sim(seed: int = 71) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_accurate_forecast_mints_wild_one_does_not():
    sim = make_sim()
    good, bad = sim.colonies[0], sim.colonies[1]
    good.maw.food_stored = 100.0
    bad.maw.food_stored = 100.0
    # good foresaw ~exactly; bad was wildly off
    good._forecast = (100.0, sim.step_count)   # error 0 -> full mint
    bad._forecast = (100.0 + 5 * GRAIN_SCALE, sim.step_count)  # error >> 1
    sim._score_forecasts()
    assert abs(good.currency - GRAIN_MINT) < 1e-6, "a true forecast mints full"
    assert bad.currency == 0.0, "a wild forecast mints nothing"
    assert abs(sim.grains_minted - GRAIN_MINT) < 1e-6
    house = sim._house_name(good)
    assert abs(sim._house_grains()[house] - GRAIN_MINT) < 1e-6
    assert good._forecast is None and bad._forecast is None, "forecasts clear"
    assert any("mints" in m for _, m in sim.events)


def test_scoring_waits_for_the_target_step():
    sim = make_sim()
    c = sim.colonies[0]
    c.maw.food_stored = 80.0
    c._forecast = (80.0, sim.step_count + 100)  # not due yet
    sim._score_forecasts()
    assert c.currency == 0.0 and c._forecast is not None, "not scored early"
    sim.step_count += 100
    sim._score_forecasts()
    assert c.currency > 0 and c._forecast is None, "scored once due"


def test_dead_colony_forecast_is_void():
    sim = make_sim()
    c = sim.colonies[0]
    c._forecast = (100.0, sim.step_count)
    c.maw.alive = False
    sim._score_forecasts()
    assert c.currency == 0.0 and c._forecast is None, "a dead maw's bet voids"


def test_partial_accuracy_scales_reward():
    sim = make_sim()
    c = sim.colonies[0]
    c.maw.food_stored = 100.0
    c._forecast = (100.0 + 0.5 * GRAIN_SCALE, sim.step_count)  # error 0.5
    sim._score_forecasts()
    assert abs(c.currency - 0.5 * GRAIN_MINT) < 1e-6, "reward scales with accuracy"


def test_ledger_pickles_and_dashboard_exposes_grains():
    import pickle
    sim = make_sim()
    c = sim.colonies[0]
    c.maw.food_stored = 100.0
    c._forecast = (100.0, sim.step_count)
    sim._score_forecasts()
    revived = pickle.loads(pickle.dumps(sim))
    assert revived.grains_minted > 0
    from dashboard import TerrariumRunner, create_app, build_state
    assert "grains_minted" in build_state(sim)
    from fastapi.testclient import TestClient
    client = TestClient(create_app(TerrariumRunner(sim)))
    r = client.get("/api/ledger")
    assert r.status_code == 200 and "houses" in r.json()


def test_evolution_sim_inert():
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_score_forecasts' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all currency tests passed")
