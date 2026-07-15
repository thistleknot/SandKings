"""Dog-eat-dog scarcity war (SPEC_SCARCITY_WAR): the starving declare war to raid (not stand down),
hunger raises aggression, and plunder moves food without minting it. Gate default off -> the prosperity
war and un-augmented aggression exactly as today (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, VoxelType, UnitType, SCARCITY_WAR_ENABLED,
                           HUNGER_WAR_FLOOR, SCARCITY_AGG_K, PLUNDER_FRAC, WAR_CHEST, FEED_INTERVAL,
                           HARVEST_YIELD, CANNIBAL_HUNGER_BONUS, BOOTSTRAP_FLOOR, SACK_RADIUS)
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
    assert SCARCITY_WAR_ENABLED is False, "SCARCITY_WAR_ENABLED must default False (battery byte-identical)"


def test_plunder_conserves_food():
    if not HAVE:
        return _skip()
    prev = sandkings.SCARCITY_WAR_ENABLED; sandkings.SCARCITY_WAR_ENABLED = True
    try:
        sim = _sim()
        loser, victor = sim.colonies[0], sim.colonies[1]
        loser.maw.food_stored = 100.0
        victor.maw.food_stored = 50.0
        total_before = loser.maw.food_stored + victor.maw.food_stored
        sim._plunder(loser, victor)
        assert abs(loser.maw.food_stored - 85.0) < 1e-9, "loser loses PLUNDER_FRAC of its food"
        assert abs(victor.maw.food_stored - 65.0) < 1e-9, "victor gains exactly what the loser lost"
        assert abs((loser.maw.food_stored + victor.maw.food_stored) - total_before) < 1e-9, \
            "plunder MOVES food, never mints it (conservation)"
    finally:
        sandkings.SCARCITY_WAR_ENABLED = prev


def test_plunder_off_is_noop():
    if not HAVE:
        return _skip()
    sim = _sim()
    loser, victor = sim.colonies[0], sim.colonies[1]
    loser.maw.food_stored = 100.0; victor.maw.food_stored = 50.0
    sim._plunder(loser, victor)                       # gate off -> no-op
    assert loser.maw.food_stored == 100.0 and victor.maw.food_stored == 50.0


def test_hunger_raises_aggression():
    if not HAVE:
        return _skip()
    sim = _sim()
    c = sim.colonies[0]
    c.confidence = 0.5; c.agitation = 0.0
    c.maw.food_stored = 40.0                           # below HUNGER_WAR_FLOOR

    eff_off = sim._aggression_eff(c)                   # gate off -> base only
    prev = sandkings.SCARCITY_WAR_ENABLED; sandkings.SCARCITY_WAR_ENABLED = True
    try:
        eff_hungry = sim._aggression_eff(c)            # gate on, starving -> desperation term
        c.maw.food_stored = 100.0                      # gate on, fed -> no desperation
        eff_fed = sim._aggression_eff(c)
    finally:
        sandkings.SCARCITY_WAR_ENABLED = prev
    assert eff_hungry > eff_off, "hunger must RAISE effective aggression when the gate is on"
    assert abs(eff_fed - eff_off) < 1e-9, "a fed colony's aggression is unchanged (desperation only when starving)"


def _prep_enemies(sim):
    """Place the two maws far apart so a single step has no combat, and clear any truce/alliance."""
    a, b = sim.colonies[0], sim.colonies[1]
    d = sim._diplomacy()
    d.war_target[a.colony_id] = None
    d.war_target[b.colony_id] = None
    return a, b, d


def test_starving_colony_declares_and_holds():
    if not HAVE:
        return _skip()
    prev = sandkings.SCARCITY_WAR_ENABLED; sandkings.SCARCITY_WAR_ENABLED = True
    try:
        sim = _sim()
        a, b, d = _prep_enemies(sim)
        sim.step_count = 50                            # not a feed tick (FEED_INTERVAL=100)
        for _ in range(3):
            a.maw.food_stored = 40.0                   # keep A desperate (< HUNGER_WAR_FLOOR)
            sim.step()
        assert d.war_target.get(a.colony_id) == b.colony_id, \
            "a starving colony raids its only eligible enemy"
        assert a.at_war is True, "and it stays on the warpath while hungry (no poverty stand-down)"
    finally:
        sandkings.SCARCITY_WAR_ENABLED = prev


def test_gate_off_hungry_colony_stands_down():
    if not HAVE:
        return _skip()
    sim = _sim()                                       # gate off (module default)
    a, b, d = _prep_enemies(sim)
    d.war_target[a.colony_id] = b.colony_id            # pretend A was at war
    sim.step_count = 50
    a.maw.food_stored = 40.0                           # poor: < WAR_CHEST/2
    sim.step()
    assert d.war_target.get(a.colony_id) is None, "gate off: a poor colony stands down at food < WAR_CHEST/2"


def _corpse_forage_gain(sim, colony, start_food):
    """A worker eats a CORPSE one cell away; return the colony's food gain."""
    worker = next(u for u in colony.units if u.unit_type == UnitType.WORKER)
    worker.build_slot = 1                              # isolate the forage path (not a builder this step)
    wx, wy, wz = 6, 6, sim.world.surface_z(6, 6) + 1
    worker.position = (wx, wy, wz)
    sim.world.voxels[wx + 1, wy, wz] = VoxelType.CORPSE.value
    colony.maw.food_stored = start_food
    before = colony.maw.food_stored
    sim._execute_unit_ai(worker, colony)
    return colony.maw.food_stored - before


def test_starving_cannibal_gets_the_bonus():
    if not HAVE:
        return _skip()
    prev = sandkings.SCARCITY_WAR_ENABLED; sandkings.SCARCITY_WAR_ENABLED = True
    try:
        sim = _sim()
        starving_gain = _corpse_forage_gain(sim, sim.colonies[0], start_food=5.0)   # < 2*BOOTSTRAP_FLOOR
        sim2 = _sim()
        fed_gain = _corpse_forage_gain(sim2, sim2.colonies[0], start_food=100.0)     # well fed
        assert abs(fed_gain - HARVEST_YIELD) < 1e-6, "a fed forager gets only the base corpse yield"
        assert abs(starving_gain - (HARVEST_YIELD + CANNIBAL_HUNGER_BONUS)) < 1e-6, \
            "a starving forager gets the cannibal hunger bonus on top of the base yield"
    finally:
        sandkings.SCARCITY_WAR_ENABLED = prev


def test_cannibal_bonus_off_is_base_only():
    if not HAVE:
        return _skip()
    sim = _sim()                                       # gate off
    gain = _corpse_forage_gain(sim, sim.colonies[0], start_food=5.0)
    assert abs(gain - HARVEST_YIELD) < 1e-6, "gate off: even a starving forager gets only the base yield"


def test_sack_besieger_attribution():
    if not HAVE:
        return _skip()
    prev = sandkings.SCARCITY_WAR_ENABLED; sandkings.SCARCITY_WAR_ENABLED = True
    try:
        sim = _sim()
        dead, besieger = sim.colonies[0], sim.colonies[1]
        d = sim._diplomacy()
        mx, my, mz = dead.maw.position
        # a besieger that declared war on `dead` with a unit adjacent to the fallen maw
        d.war_target[besieger.colony_id] = dead.colony_id
        u = besieger.units[0]
        u.position = (mx + 1, my, mz)
        assert sim._sack_besieger(dead) is besieger, "the warring adjacent colony is the sacker"
        # move the unit out of range -> no besieger
        u.position = (mx + SACK_RADIUS + 5, my, mz)
        assert sim._sack_besieger(dead) is None, "no sacker when no warring unit is within SACK_RADIUS"
        # in range but NOT at war -> no besieger
        u.position = (mx + 1, my, mz)
        d.war_target[besieger.colony_id] = None
        assert sim._sack_besieger(dead) is None, "no sacker without a declared war on the fallen"
    finally:
        sandkings.SCARCITY_WAR_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all scarcity-war tests passed")
