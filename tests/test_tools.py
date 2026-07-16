"""Acceptance tests for SPEC_TOOLS.md (TL1-TL6).

Failure modes covered: telemetry growing unbounded, the regression
missing a planted slope, both backends disagreeing on direction, the
tool nudging the wrong disposition or reachable without a pi, the feed
not pickling, and the dashboard endpoint missing.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

import telemetry as tel_mod
from telemetry import (TELEMETRY_HISTORY, TELEMETRY_INTERVAL, Telemetry,
                       predict_food)
from sandkings import SandKingsSimulation, VoxelType


def make_sim(seed: int = 61) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def rows_with_slope(slope: float, n: int = 20, base: float = 100.0):
    return [{"step": i * TELEMETRY_INTERVAL,
             "food": base + slope * i * TELEMETRY_INTERVAL} for i in range(n)]


def test_telemetry_records_bounded_rows():
    sim = make_sim()
    tel = sim._telemetry()
    for _ in range(TELEMETRY_HISTORY + 30):
        sim.step_count += TELEMETRY_INTERVAL
        tel.record(sim)
    for colony in sim.colonies:
        hist = tel.history(colony.colony_id)
        assert len(hist) <= TELEMETRY_HISTORY, "the ring is bounded"
        if hist:
            assert {"step", "food", "pop", "at_war"} <= hist[0].keys()


def test_predict_food_recovers_slope_both_backends():
    for backend_name in ("sklearn", "numpy"):
        if backend_name == "sklearn":
            try:
                import sklearn  # noqa: F401
            except Exception:
                continue
        # pin the backend under test
        saved = tel_mod.REGRESSION_BACKENDS
        tel_mod.REGRESSION_BACKENDS = tuple(
            b for b in saved if b[0] == backend_name)
        try:
            up = predict_food(rows_with_slope(0.5))
            down = predict_food(rows_with_slope(-0.5))
            assert up is not None and up[1] > 0, (backend_name, "rising")
            assert down is not None and down[1] < 0, (backend_name, "falling")
        finally:
            tel_mod.REGRESSION_BACKENDS = saved
    assert predict_food(rows_with_slope(0.5, n=2)) is None, "needs >= 3 rows"


def test_predict_tool_nudges_by_trend_pi_only():
    from machines import Controller, PI_FUEL
    sim = make_sim()
    colony = sim.colonies[0]
    # plant a FALLING food history for this colony
    tel = sim._telemetry()
    for r in rows_with_slope(-0.4):
        tel.rows[colony.colony_id].append({**r, "pop": 5, "maw_hp": 100.0,
                                           "at_war": False, "season": 0,
                                           "oasis": False, "attitude": "none"})
    # no pi -> the terminal tool is unreachable
    colony.controllers = [Controller(colony.colony_id)]
    colony.machine_arc = 'claimed'
    colony.controllers[0].operate_ticks = 999
    pat0 = colony.genome.patience
    sim._actuate(colony, 7, 4)
    assert colony.genome.patience == pat0, "no pi, no prediction"
    # pi -> falling trend makes it hoard (patience up)
    colony.controllers = [Controller(colony.colony_id, fuel=PI_FUEL)]
    colony.controllers[0].operate_ticks = 999
    sim._actuate(colony, 7, 4)
    assert colony.genome.patience > pat0, "foresaw lean times, hoarded"
    assert any("foresees lean times" in m for _, m in sim.events)


def test_predict_tool_grows_on_rising_trend():
    from machines import Controller, PI_FUEL
    sim = make_sim(seed=2)
    colony = sim.colonies[0]
    tel = sim._telemetry()
    for r in rows_with_slope(0.6):
        tel.rows[colony.colony_id].append({**r, "pop": 5, "maw_hp": 100.0,
                                           "at_war": False, "season": 0,
                                           "oasis": False, "attitude": "none"})
    colony.controllers = [Controller(colony.colony_id, fuel=PI_FUEL)]
    colony.machine_arc = 'claimed'
    colony.controllers[0].operate_ticks = 999
    fert0 = colony.genome.fertility
    sim._actuate(colony, 7, 4)
    assert colony.genome.fertility > fert0, "foresaw plenty, grew"


def test_telemetry_pickles_and_endpoint():
    import pickle
    sim = make_sim()
    for _ in range(6):
        sim.step_count += TELEMETRY_INTERVAL
        sim._telemetry().record(sim)
    revived = pickle.loads(pickle.dumps(sim))
    assert revived._telemetry().history(sim.colonies[0].colony_id)
    # dashboard feed
    from dashboard import TerrariumRunner, create_app
    from fastapi.testclient import TestClient
    client = TestClient(create_app(TerrariumRunner(sim)))
    r = client.get("/api/telemetry")
    assert r.status_code == 200 and isinstance(r.json(), dict)


def test_evolution_sim_inert():
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_predict_tool' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tools tests passed")
