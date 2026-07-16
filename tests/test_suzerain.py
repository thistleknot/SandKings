"""Aztec/Cortes new order (SPEC_SUZERAIN): a dominant power imposes tributary vassalage, a Pax suppresses
vassal wars, tribute flows and accrues resentment, and revolt reopens war. Gate default off -> the
coalition/hegemon exactly as today and hostile() byte-identical."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, SUZERAIN_ENABLED
    from politics import (hostile, TRIBUTE_INTERVAL, TRIBUTE_RATE, TRIBUTE_RESENTMENT,
                          REVOLT_RESENTMENT)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim(n=3):
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=n)
    for i, c in enumerate(sim.colonies):        # distinct houses -> none are kin
        c.house = f"H{i}"
    sim._kin_epoch = getattr(sim, '_kin_epoch', 0) + 1
    return sim


def _impose(sim):
    """Make colony 0 dominant and impose the order; return (overlord, vassals)."""
    sim.colonies[0].maw.food_stored = 5000.0    # power share past SUZERAIN_ENTER/n
    sim._update_hegemon()
    return sim.colonies[0], sim.colonies[1:]


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert SUZERAIN_ENABLED is False, "SUZERAIN_ENABLED must default False (battery byte-identical)"


def test_imposition_and_pax():
    if not HAVE:
        return _skip()
    prev = sandkings.SUZERAIN_ENABLED; sandkings.SUZERAIN_ENABLED = True
    try:
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        d = sim._diplomacy()
        assert overlord.overlord_of == {v.colony_id for v in vassals}, "the strongest imposes on all others"
        for v in vassals:
            assert v.tributary_to == overlord.colony_id, "each weaker colony becomes a tributary"
        assert d.hegemon is None, "suzerainty supersedes the coalition (no hegemon)"
        a, b = vassals[0].colony_id, vassals[1].colony_id
        assert hostile(sim, a, b) is False, "Pax: co-vassals do not war"
        assert hostile(sim, overlord.colony_id, a) is False, "Pax: overlord and vassal do not war"
    finally:
        sandkings.SUZERAIN_ENABLED = prev


def test_tribute_flows_and_accrues_resentment():
    if not HAVE:
        return _skip()
    prev = sandkings.SUZERAIN_ENABLED; sandkings.SUZERAIN_ENABLED = True
    try:
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]
        sim.step_count = TRIBUTE_INTERVAL - v.colony_id   # (step + cid) % INTERVAL == 0 for this vassal
        v.maw.food_stored = 200.0
        v.overlord_grudge = 0.0
        o_before = overlord.maw.food_stored
        total_before = v.maw.food_stored + overlord.maw.food_stored
        sim._tribute_tick()
        assert abs(v.maw.food_stored - 180.0) < 1e-6, "vassal renders TRIBUTE_RATE of its food"
        assert abs(overlord.maw.food_stored - (o_before + 20.0)) < 1e-6, "overlord receives the tribute"
        assert abs((v.maw.food_stored + overlord.maw.food_stored) - total_before) < 1e-6, \
            "tribute MOVES food, never mints it (conservation)"
        assert v.overlord_grudge == TRIBUTE_RESENTMENT, "each tribute accrues non-decaying resentment"
    finally:
        sandkings.SUZERAIN_ENABLED = prev


def test_revolt_reopens_war():
    if not HAVE:
        return _skip()
    prev = sandkings.SUZERAIN_ENABLED; sandkings.SUZERAIN_ENABLED = True
    try:
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]
        v.overlord_grudge = REVOLT_RESENTMENT   # one more tribute tips it over
        v.maw.food_stored = 100.0
        sim.step_count = TRIBUTE_INTERVAL - v.colony_id
        sim._tribute_tick()
        d = sim._diplomacy()
        assert v.tributary_to == -1, "the revolting vassal is freed"
        assert v.colony_id not in overlord.overlord_of, "the overlord loses the vassal"
        assert d.war_target.get(v.colony_id) == overlord.colony_id, "the freed vassal turns on its overlord"
        assert hostile(sim, v.colony_id, overlord.colony_id) is True, "Pax lifts — war resumes (no freeze)"
    finally:
        sandkings.SUZERAIN_ENABLED = prev


def test_gate_off_coalition_as_today():
    if not HAVE:
        return _skip()
    sim = _sim(3)                                # gate off (module default); no sim.suzerain_enabled
    overlord, vassals = _impose(sim)
    d = sim._diplomacy()
    assert d.hegemon == overlord.colony_id, "gate off: the strongest is the coalition target, as today"
    for v in vassals:
        assert getattr(v, 'tributary_to', -1) == -1, "gate off: no vassalage imposed"
    sim._tribute_tick()                          # gate off -> no-op
    assert hostile(sim, vassals[0].colony_id, vassals[1].colony_id) is True, \
        "gate off: hostile() unchanged (no Pax)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all suzerain tests passed")
