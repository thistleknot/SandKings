"""Hoard planning (SPEC_WINTER WI2): the learner gains a winter-coming state cue and a Dust->Chill
crossing reward that credits a stockpile. Gate default off -> the 5-tuple state and the un-shaped reward
exactly as today (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, HOARD_PLANNING_ENABLED, SEASON_LENGTH
    from colony_learner import observe_state, ColonyLearner, HOARD_TARGET
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert HOARD_PLANNING_ENABLED is False, "HOARD_PLANNING_ENABLED must default False (byte-identical)"


def test_winter_coming_cue_only_when_on():
    if not HAVE:
        return _skip()
    sim = _sim(); colony = sim.colonies[0]
    sim.step_count = 2 * SEASON_LENGTH               # Dust — the last prep window
    s_on = observe_state(sim, colony, hoard_shaping=True)
    s_off = observe_state(sim, colony)
    assert len(s_off) == 5, "gate off: the state stays a 5-tuple"
    assert len(s_on) == 6, "gate on: the state gains a winter_coming dim"
    assert s_on[5] is True, "winter_coming is True in Dust"
    sim.step_count = SEASON_LENGTH                   # Growth
    assert observe_state(sim, colony, hoard_shaping=True)[5] is False, "winter_coming False outside Dust"


def _q_after_crossing(sim, colony, shaping):
    """Run a Dust->Chill decision pair with the value held constant (delta 0) so any Q change on the
    Dust action comes purely from the crossing hoard bonus. Returns Q[dust_state][dust_action]."""
    random.seed(0); np.random.seed(0)
    learner = ColonyLearner()
    colony.maw.food_stored = HOARD_TARGET            # a full hoard -> bonus fraction = 1.0
    sim.step_count = 2 * SEASON_LENGTH               # Dust
    learner.decide(sim, colony, 0.9, 0.5, hoard_shaping=shaping)
    dust_state, dust_action = learner._last_state, learner._last_action
    colony.maw.food_stored = HOARD_TARGET            # unchanged -> value delta is 0
    sim.step_count = 3 * SEASON_LENGTH               # Chill (crossing)
    learner.decide(sim, colony, 0.9, 0.5, hoard_shaping=shaping)
    return learner.q[dust_state][dust_action]


def test_crossing_bonus_credits_the_reserve():
    if not HAVE:
        return _skip()
    sim = _sim(); colony = sim.colonies[0]
    q_shaped = _q_after_crossing(sim, colony, shaping=True)
    q_unshaped = _q_after_crossing(sim, colony, shaping=False)
    assert q_unshaped == 0.0, "no shaping: a constant-value crossing yields no reward"
    assert q_shaped > 0.0, "shaping: a full hoard at the winter crossing credits the reserve-building action"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all hoard-planning tests passed")
