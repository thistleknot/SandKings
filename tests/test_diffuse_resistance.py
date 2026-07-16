"""Wage vs Whip (SPEC_DIFFUSE_RESISTANCE, Phase 6): the overlord's disposition sets the extraction style — a
whip (aggressive) order breeds krypteia memory fast and revolts (WW1), a wage (soft) order softens grudge and
endures (WW2) while the subjugated foot-drag a small permanent amount (WW3). Gate default off -> _tribute_tick
reproduces Phase 5 exactly.

Isolation: _tribute_tick re-imports its constants every call, so neutralize repression with a huge
REPRESSION_COST_FOOD to read a clean accrual, and set overlord.genome.aggression to pick the hardness.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import politics
    import sandkings
    from sandkings import SandKingsSimulation
    from politics import (TRIBUTE_RATE, TRIBUTE_INTERVAL, TRIBUTE_RESENTMENT, REVOLT_RESENTMENT,
                          REPRESSION_RESENTMENT, SABOTAGE_WITHHOLD_K, SABOTAGE_WITHHOLD_CAP,
                          WHIP_MEMORY_K, WAGE_GRUDGE_FLOOR, DIFFUSE_DRAG)
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
    for i, c in enumerate(sim.colonies):
        c.house = f"H{i}"
    sim._kin_epoch = getattr(sim, '_kin_epoch', 0) + 1
    return sim


def _impose(sim, agg=0.75):
    """Dominant colony 0 imposes the order; set its disposition (hardness). Returns (overlord, vassals)."""
    sim.colonies[0].maw.food_stored = 5000.0
    sim._update_hegemon()
    sim.colonies[0].genome.aggression = agg
    return sim.colonies[0], sim.colonies[1:]


def _arm(sim, v):
    sim.step_count = TRIBUTE_INTERVAL - v.colony_id


def _phase5_withhold(grudge):
    gn = min(1.0, grudge / REVOLT_RESENTMENT)
    return min(SABOTAGE_WITHHOLD_CAP, SABOTAGE_WITHHOLD_K * gn)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.DIFFUSE_RESISTANCE_ENABLED is False, "DIFFUSE_RESISTANCE_ENABLED must default False"


def test_whip_breeds_more_memory_than_wage():
    """WW1: memory_gain scales with hardness -> an aggressive overlord's krypteia compounds faster."""
    if not HAVE:
        return _skip()
    ps, pr, pd = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED
    sandkings.SUZERAIN_ENABLED = sandkings.REPRESSION_ENABLED = sandkings.DIFFUSE_RESISTANCE_ENABLED = True
    try:
        mem = {}
        for agg in (1.0, 0.5):
            sim = _sim(3); sim.suzerain_enabled = True
            overlord, vassals = _impose(sim, agg=agg)
            v = vassals[0]; _arm(sim, v)
            v.maw.food_stored = 200.0; v.overlord_grudge = 10.0; v.subjugation_memory = 0.0
            overlord.maw.food_stored = 1000.0            # rich -> repression fires
            sim._tribute_tick()
            mem[agg] = v.subjugation_memory
        assert abs(mem[1.0] - REPRESSION_RESENTMENT * (1.0 + WHIP_MEMORY_K * 1.0)) < EPS, "whip memory gain"
        assert abs(mem[0.5] - REPRESSION_RESENTMENT * (1.0 + WHIP_MEMORY_K * 0.5)) < EPS, "wage memory gain"
        assert mem[1.0] > mem[0.5], "the whip breeds resentment faster than the wage"
    finally:
        sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED = ps, pr, pd


def test_wage_accrues_less_grudge_than_whip():
    """WW2: grudge accrual is scaled by grudge_mult<1 for a soft order -> it endures longer."""
    if not HAVE:
        return _skip()
    ps, pr, pd = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = sandkings.REPRESSION_ENABLED = sandkings.DIFFUSE_RESISTANCE_ENABLED = True
    politics.REPRESSION_COST_FOOD = 1e18                 # neutralize repression -> clean accrual
    try:
        g = {}
        for agg in (1.0, 0.5):
            sim = _sim(3); sim.suzerain_enabled = True
            overlord, vassals = _impose(sim, agg=agg)
            v = vassals[0]; _arm(sim, v)
            v.maw.food_stored = 100.0; v.overlord_grudge = 10.0; v.subjugation_memory = 0.0
            sim._tribute_tick()
            g[agg] = v.overlord_grudge
        assert abs(g[1.0] - (10.0 + TRIBUTE_RESENTMENT * 1.0)) < EPS, "whip: near-full accrual"
        soft_mult = WAGE_GRUDGE_FLOOR + (1.0 - WAGE_GRUDGE_FLOOR) * 0.5
        assert abs(g[0.5] - (10.0 + TRIBUTE_RESENTMENT * soft_mult)) < EPS, "wage: softened accrual"
        assert g[0.5] < g[1.0], "a wage order accrues grudge slower — it endures longer"
    finally:
        sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED = ps, pr, pd
        politics.REPRESSION_COST_FOOD = cost


def test_diffuse_drag_soft_only():
    """WW3: a soft order adds a permanent foot-drag; a pure whip (hardness=1) adds none."""
    if not HAVE:
        return _skip()
    ps, pr, pd = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED
    cost = politics.REPRESSION_COST_FOOD
    sandkings.SUZERAIN_ENABLED = sandkings.REPRESSION_ENABLED = sandkings.DIFFUSE_RESISTANCE_ENABLED = True
    politics.REPRESSION_COST_FOOD = 1e18                 # keep overlord food off the vassal's rendered amount
    try:
        rendered = {}
        for agg in (1.0, 0.5):
            sim = _sim(3); sim.suzerain_enabled = True
            overlord, vassals = _impose(sim, agg=agg)
            v = vassals[0]; _arm(sim, v)
            v.maw.food_stored = 200.0; v.overlord_grudge = 10.0
            before = v.maw.food_stored
            sim._tribute_tick()
            rendered[agg] = before - v.maw.food_stored
        p5 = TRIBUTE_RATE * 200.0 * (1.0 - _phase5_withhold(10.0))         # Phase-5 amount, no diffuse drag
        assert abs(rendered[1.0] - p5) < EPS, "pure whip (hardness=1) adds zero diffuse drag"
        soft_withhold = min(0.95, _phase5_withhold(10.0) + DIFFUSE_DRAG * 0.5)
        assert abs(rendered[0.5] - TRIBUTE_RATE * 200.0 * (1.0 - soft_withhold)) < EPS, "soft order foot-drags"
        assert rendered[0.5] < rendered[1.0], "a soft-order vassal renders less (diffuse foot-drag)"
    finally:
        sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED, sandkings.DIFFUSE_RESISTANCE_ENABLED = ps, pr, pd
        politics.REPRESSION_COST_FOOD = cost


def test_gate_off_matches_phase5():
    """Gate off: DIFFUSE off (REPRESSION on) reproduces the Phase-5 formulas exactly (multipliers neutral)."""
    if not HAVE:
        return _skip()
    ps, pr = sandkings.SUZERAIN_ENABLED, sandkings.REPRESSION_ENABLED
    sandkings.SUZERAIN_ENABLED = True; sandkings.REPRESSION_ENABLED = True
    try:
        assert sandkings.DIFFUSE_RESISTANCE_ENABLED is False
        sim = _sim(3); sim.suzerain_enabled = True
        overlord, vassals = _impose(sim, agg=1.0)
        v = vassals[0]; _arm(sim, v)
        v.maw.food_stored = 200.0; v.overlord_grudge = 10.0; v.subjugation_memory = 0.0
        overlord.maw.food_stored = 1000.0
        p5 = TRIBUTE_RATE * 200.0 * (1.0 - _phase5_withhold(10.0))
        sim._tribute_tick()
        # Phase-5 memory gain is REPRESSION_RESENTMENT (memory_mult neutral), grudge = 10 + 10 - REPRESSION_CALM
        from politics import REPRESSION_CALM
        assert abs(v.maw.food_stored - (200.0 - p5)) < EPS, "gate off: Phase-5 withhold only (no diffuse drag)"
        assert abs(v.subjugation_memory - REPRESSION_RESENTMENT) < EPS, "gate off: no memory acceleration"
        assert abs(v.overlord_grudge - (10.0 + TRIBUTE_RESENTMENT - REPRESSION_CALM)) < EPS, \
            "gate off: Phase-5 grudge (no softening)"
    finally:
        sandkings.SUZERAIN_ENABLED = ps; sandkings.REPRESSION_ENABLED = pr


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all diffuse-resistance tests passed")
