"""Two-sided tribute order (SPEC_REPRESSION, Phase 5): a vassal withholds and spoils tribute (RR1), the
overlord pays to suppress the grudge (RR2 iron fist), repression breeds a persistent subjugation_memory that
accelerates accrual (RR3 krypteia), and the revolt loop still closes (RR4). Gate default off -> _tribute_tick
is byte-identical to Phase 4.

Isolation trick: _tribute_tick re-imports its politics constants every call, so a test can neutralize one
clause by monkeypatching a politics constant (e.g. REPRESSION_COST_FOOD huge -> repression never affordable)
and restore it after.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import politics
    import sandkings
    from sandkings import SandKingsSimulation
    from politics import (TRIBUTE_RATE, TRIBUTE_INTERVAL, TRIBUTE_RESENTMENT, REVOLT_RESENTMENT,
                          REPRESSION_COST_FOOD, REPRESSION_CALM, REPRESSION_RESENTMENT, MEMORY_ACCEL_K,
                          SABOTAGE_WITHHOLD_K, SABOTAGE_WITHHOLD_CAP, SABOTAGE_DAMAGE_K, SABOTAGE_MIN_GRUDGE)
    HAVE = True
except Exception:
    HAVE = False

EPS = 1e-6


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
    """Make colony 0 dominant and impose the order; return (overlord, vassals). Requires SUZERAIN on."""
    sim.colonies[0].maw.food_stored = 5000.0
    sim._update_hegemon()
    return sim.colonies[0], sim.colonies[1:]


def _arm_vassal(sim, v):
    """Set step_count so ONLY vassal v renders tribute this tick (staggered trigger)."""
    sim.step_count = TRIBUTE_INTERVAL - v.colony_id


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.REPRESSION_ENABLED is False, "REPRESSION_ENABLED must default False (battery byte-identical)"


def test_sabotage_withholds_and_damages():
    """RR1: a high-grudge vassal renders LESS (withheld part stays with it) and spoils overlord food."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    politics.REPRESSION_COST_FOOD = 1e18        # neutralize RR2 so RR1 is isolated
    try:
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]; _arm_vassal(sim, v)
        v.maw.food_stored = 200.0; v.overlord_grudge = 40.0     # grudge_norm = 0.8
        overlord.maw.food_stored = 100.0
        gn = 40.0 / REVOLT_RESENTMENT
        withhold = min(SABOTAGE_WITHHOLD_CAP, SABOTAGE_WITHHOLD_K * gn)
        rendered = TRIBUTE_RATE * 200.0 * (1.0 - withhold)
        spoil = SABOTAGE_DAMAGE_K * gn * 100.0
        sim._tribute_tick()
        assert rendered < TRIBUTE_RATE * 200.0, "a resentful vassal renders less than the full tribute"
        assert abs(v.maw.food_stored - (200.0 - rendered)) < EPS, "withheld food stays with the vassal (conserved)"
        assert abs(v.maw.food_stored + rendered - 200.0) < EPS, "vassal food == kept + rendered (conservation)"
        assert abs(overlord.maw.food_stored - (100.0 - spoil + rendered)) < EPS, \
            "overlord = start - spoil + tribute (net destruction from sabotage)"
        assert overlord.maw.food_stored < 100.0 + rendered - EPS, "covert damage destroyed overlord food"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr
        politics.REPRESSION_COST_FOOD = cost


def test_zero_grudge_renders_full_no_sabotage():
    """RR1 control: a content (zero-grudge) vassal renders the full tribute and spoils nothing."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    politics.REPRESSION_COST_FOOD = 1e18
    try:
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]; _arm_vassal(sim, v)
        v.maw.food_stored = 200.0; v.overlord_grudge = 0.0
        overlord.maw.food_stored = 100.0
        full = TRIBUTE_RATE * 200.0
        sim._tribute_tick()
        assert abs(v.maw.food_stored - (200.0 - full)) < EPS, "content vassal renders the full tribute"
        assert abs(overlord.maw.food_stored - (100.0 + full)) < EPS, "no spoil below SABOTAGE_MIN_GRUDGE"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr
        politics.REPRESSION_COST_FOOD = cost


def test_repression_suppresses_and_costs():
    """RR2: an affordable overlord pays REPRESSION_COST_FOOD to cut the grudge; a broke one cannot."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    try:
        # Affordable overlord (rich): grudge is cut, food drops by the fist's cost beyond the tribute.
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]; _arm_vassal(sim, v)
        v.maw.food_stored = 200.0; v.overlord_grudge = 10.0; v.subjugation_memory = 0.0
        overlord.maw.food_stored = 1000.0
        withhold = min(SABOTAGE_WITHHOLD_CAP, SABOTAGE_WITHHOLD_K * (10.0 / REVOLT_RESENTMENT))
        rendered = TRIBUTE_RATE * 200.0 * (1.0 - withhold)
        sim._tribute_tick()
        assert abs(overlord.maw.food_stored - (1000.0 + rendered - REPRESSION_COST_FOOD)) < EPS, \
            "overlord loses REPRESSION_COST_FOOD beyond the tribute it received"
        assert abs(v.overlord_grudge - (10.0 + TRIBUTE_RESENTMENT - REPRESSION_CALM)) < EPS, \
            "the fist suppresses the grudge by REPRESSION_CALM"
        assert v.overlord_grudge < 10.0 + TRIBUTE_RESENTMENT, "repressed grudge is below the un-repressed accrual"
        assert abs(v.subjugation_memory - REPRESSION_RESENTMENT) < EPS, "repression breeds krypteia memory"

        # Broke overlord: tiny tribute keeps it below the cost -> no repression, grudge climbs the full amount.
        sim2 = _sim(3); sim2.suzerain_enabled = True
        o2, vs2 = _impose(sim2)
        v2 = vs2[0]; _arm_vassal(sim2, v2)
        v2.maw.food_stored = 10.0; v2.overlord_grudge = 10.0; v2.subjugation_memory = 0.0
        o2.maw.food_stored = 5.0                 # even after tribute stays < REPRESSION_COST_FOOD
        sim2._tribute_tick()
        assert abs(v2.overlord_grudge - (10.0 + TRIBUTE_RESENTMENT)) < EPS, \
            "a broke overlord cannot repress -> grudge climbs the full effective resentment"
        assert getattr(v2, 'subjugation_memory', 0.0) == 0.0, "no repression -> no memory bred"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr


def test_krypteia_memory_persists_and_accelerates():
    """RR3: memory survives a revolt and raises future accrual (effective_resentment)."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    try:
        # memory survives _revolt (deliberately NOT reset, unlike overlord_grudge)
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]
        v.subjugation_memory = 5.0; v.overlord_grudge = 30.0
        sim._revolt(v, overlord)
        assert v.overlord_grudge == 0.0, "_revolt zeroes the grudge"
        assert v.tributary_to == -1, "_revolt frees the vassal"
        assert abs(getattr(v, 'subjugation_memory', 0.0) - 5.0) < EPS, "subjugation_memory persists across revolt"

        # higher memory -> more grudge accrual per interval (repression neutralized to isolate RR3)
        politics.REPRESSION_COST_FOOD = 1e18
        sim2 = _sim(3); sim2.suzerain_enabled = True
        o2, vs2 = _impose(sim2)
        va, vb = vs2[0], vs2[1]
        for x in (va, vb):
            _arm_vassal(sim2, x)
        va.maw.food_stored = vb.maw.food_stored = 100.0
        va.overlord_grudge = vb.overlord_grudge = 0.0
        va.subjugation_memory = 0.0; vb.subjugation_memory = 10.0
        # tick each vassal at its own staggered step
        _arm_vassal(sim2, va); sim2._tribute_tick()
        _arm_vassal(sim2, vb); sim2._tribute_tick()
        assert abs(va.overlord_grudge - TRIBUTE_RESENTMENT) < EPS, "zero-memory vassal accrues the base resentment"
        assert abs(vb.overlord_grudge - (TRIBUTE_RESENTMENT + MEMORY_ACCEL_K * 10.0)) < EPS, \
            "memory raises accrual by MEMORY_ACCEL_K * memory"
        assert vb.overlord_grudge > va.overlord_grudge, "a longer-crushed house resents faster"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr
        politics.REPRESSION_COST_FOOD = cost


def test_revolt_loop_still_closes():
    """RR4: driving the grudge past REVOLT_RESENTMENT still triggers _revolt (war resumes)."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    politics.REPRESSION_COST_FOOD = 1e18        # no suppression, so the grudge tips over cleanly
    try:
        from politics import hostile
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]; _arm_vassal(sim, v)
        v.maw.food_stored = 50.0; v.overlord_grudge = REVOLT_RESENTMENT   # accrual tips it past the line
        sim._tribute_tick()
        d = sim._diplomacy()
        assert v.tributary_to == -1, "the revolting vassal is freed"
        assert d.war_target.get(v.colony_id) == overlord.colony_id, "the freed vassal turns on its overlord"
        assert hostile(sim, v.colony_id, overlord.colony_id) is True, "Pax lifts — war resumes"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr
        politics.REPRESSION_COST_FOOD = cost


def test_gate_off_tribute_byte_identical():
    """Gate off: full tribute, no sabotage, no repression, subjugation_memory never created (== Phase 4)."""
    if not HAVE:
        return _skip()
    ps = sandkings.SUZERAIN_ENABLED
    sandkings.SUZERAIN_ENABLED = True           # suzerain on, repression OFF (module default)
    try:
        assert sandkings.REPRESSION_ENABLED is False
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim)
        v = vassals[0]; _arm_vassal(sim, v)
        v.maw.food_stored = 200.0; v.overlord_grudge = 30.0
        o_before = overlord.maw.food_stored
        full = TRIBUTE_RATE * 200.0
        sim._tribute_tick()
        assert abs(v.maw.food_stored - (200.0 - full)) < EPS, "gate off: full tribute rendered"
        assert abs(overlord.maw.food_stored - (o_before + full)) < EPS, "gate off: overlord gains exactly the tribute"
        assert abs(v.overlord_grudge - (30.0 + TRIBUTE_RESENTMENT)) < EPS, "gate off: grudge climbs by TRIBUTE_RESENTMENT"
        assert not hasattr(v, 'subjugation_memory'), "gate off: subjugation_memory is never created"
    finally:
        sandkings.SUZERAIN_ENABLED = ps


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all repression tests passed")
