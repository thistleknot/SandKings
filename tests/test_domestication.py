"""Domestication core (SPEC_DOMESTICATION, gated): a unit adjacent to a WILD beast may tame it, danger-scaled
(harmless easy, predators near-impossible); a tamed beast (getattr `owner` = colony_id) no longer hunts or
strikes its owner. Gate default off -> the fauna tick never tames (byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, Beast, FAUNA, TAME_DANGER_CEIL
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim_with_beast(species):
    """A sim with `species` placed on top of colony 0's first unit (Chebyshev 0 -> adjacent)."""
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(8):
        sim.step()
    colony = next((c for c in sim.colonies if c.units), None)
    assert colony is not None
    unit = colony.units[0]
    _, hp, atk, pack, hunt, bounty = FAUNA[species]
    beast = Beast(species, unit.position, hp, atk, hunt, bounty, spawned_at=0)
    sim._fauna().append(beast)
    return sim, colony, unit, beast


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.DOMESTICATION_ENABLED is False, "DOMESTICATION_ENABLED must default False"


def test_harmless_beast_tames():
    """A harmless beast (hunt_range 0) adjacent to a unit is tamed -> owner = that colony."""
    if not HAVE:
        return _skip()
    prev = sandkings.TAME_BASE; sandkings.TAME_BASE = 1.0   # guarantee the roll
    try:
        sim, colony, unit, beast = _sim_with_beast('ant')
        sim._taming_tick()
        assert getattr(beast, 'owner', -1) == colony.colony_id, "an adjacent unit tames a harmless beast"
    finally:
        sandkings.TAME_BASE = prev


def test_danger_ceiling_is_untameable():
    """A beast at/above the danger ceiling can never be tamed (p <= 0) — you don't tame a lion."""
    if not HAVE:
        return _skip()
    prev = sandkings.TAME_BASE; sandkings.TAME_BASE = 1.0
    try:
        sim, colony, unit, beast = _sim_with_beast('ant')
        beast.hunt_range = TAME_DANGER_CEIL                 # at the ceiling -> tameability 0
        sim._taming_tick()
        assert getattr(beast, 'owner', -1) == -1, "a beast at the danger ceiling is untameable"
    finally:
        sandkings.TAME_BASE = prev


def test_tamed_beast_spares_its_owner():
    """A tamed predator never strikes (combat) or hunts (AI) its owner's spawn."""
    if not HAVE:
        return _skip()
    sim, colony, unit, beast = _sim_with_beast('spider')    # a predator (hunt_range > 0)
    beast.owner = colony.colony_id
    beast.provoked = True
    unit.health = unit.max_health
    hp0 = unit.health
    sim._beast_combat(beast)                                # owner unit excluded from `adjacent` -> no strike
    assert unit.health == hp0, "a tamed beast never strikes its owner"
    sim._beast_ai(beast)                                    # nearest excludes the owner -> no crash, no targeting


def test_gate_off_never_tames():
    """Gate off (module default): the fauna tick never tames, even with a guaranteed roll."""
    if not HAVE:
        return _skip()
    assert sandkings.DOMESTICATION_ENABLED is False
    prev = sandkings.TAME_BASE; sandkings.TAME_BASE = 1.0
    try:
        sim, colony, unit, beast = _sim_with_beast('ant')
        sim._fauna_tick()                                   # gate off -> _taming_tick not called
        assert getattr(beast, 'owner', -1) == -1, "gate off: no taming"
    finally:
        sandkings.TAME_BASE = prev


def test_upkeep_feeds_or_frees():
    """DM3: a fed owner pays upkeep and keeps the beast; a starving owner loses it after the starve limit."""
    if not HAVE:
        return _skip()
    from sandkings import TAME_UPKEEP, TAME_STARVE_LIMIT
    sim, colony, unit, beast = _sim_with_beast('ant')
    beast.owner = colony.colony_id
    colony.maw.food_stored = 100.0
    sim._tame_upkeep()
    assert getattr(beast, 'owner', -1) == colony.colony_id, "a fed tame is kept"
    assert abs(colony.maw.food_stored - (100.0 - TAME_UPKEEP)) < 1e-6, "upkeep is charged to the owner"
    colony.maw.food_stored = 0.0
    for _ in range(TAME_STARVE_LIMIT):
        sim._tame_upkeep()
    assert getattr(beast, 'owner', -1) == -1, "an unfed tame goes feral after the starve limit"


def test_tamed_harmless_forages_for_owner():
    """DM4: a tamed harmless beast delivers adjacent FOOD to its owner's maw (labor + livestock yield)."""
    if not HAVE:
        return _skip()
    from sandkings import VoxelType, TAME_FORAGE_YIELD
    sim, colony, unit, beast = _sim_with_beast('ant')
    beast.owner = colony.colony_id
    bx, by, bz = beast.position
    nb = (min(bx + 1, sim.world.width - 1), by, bz)          # an adjacent cell
    sim.world.voxels[nb] = VoxelType.FOOD.value
    food0 = colony.maw.food_stored
    sim._tamed_work(beast, colony.colony_id)
    assert colony.maw.food_stored >= food0 + TAME_FORAGE_YIELD - 1e-6, \
        "a tamed forager delivers food to its owner's maw"
    assert sim.world.voxels[nb] != VoxelType.FOOD.value, "the foraged food is consumed"


def test_tamed_bee_makes_honey():
    """DM4: a tamed bee produces honey (a food store) that feeds its owner's hive."""
    if not HAVE:
        return _skip()
    from sandkings import HONEY_YIELD
    sim, colony, unit, beast = _sim_with_beast('bee')
    beast.owner = colony.colony_id
    honey0 = getattr(colony, 'honey', 0.0)
    food0 = colony.maw.food_stored
    sim._tamed_work(beast, colony.colony_id)
    assert getattr(colony, 'honey', 0.0) >= honey0 + HONEY_YIELD - 1e-6, "a tamed bee makes honey"
    assert colony.maw.food_stored >= food0 + HONEY_YIELD - 1e-6, "honey feeds the hive"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all domestication tests passed")
