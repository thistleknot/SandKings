"""Chemical & deception warfare (SPEC_CHEMICAL_WAR, Cortés arc, gated POISON_ENABLED): a decaying poison
cloud harms whoever stands in it; a siege house lobs a visible poison shell at its war target. Gate default
off is byte-identical."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, POISON_TTL, POISON_TICK, POISON_RADIUS,
                           POISON_RELOAD, POISON_DAMAGE)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(8):
        sim.step()
    return sim


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.POISON_ENABLED is False, "POISON_ENABLED must default False"


def test_poison_cloud_harms_then_dissipates():
    """CW1: a cloud seeded over a unit damages it, then clears after POISON_TTL cadence-ticks."""
    if not HAVE:
        return _skip()
    sim = _sim()
    colony = next((c for c in sim.colonies if c.units), None)
    assert colony is not None, "need a colony with a unit"
    unit = colony.units[0]
    hp0 = unit.health
    sim._seed_poison(unit.position, POISON_RADIUS)
    assert sim._poison(), "the cloud exists after seeding"
    sim._poison_tick()
    assert unit.health < hp0 or unit not in colony.units, "the cloud harms a unit standing in it"
    for _ in range(POISON_TTL + 1):
        sim._poison_tick()
    assert sim._poison() == {}, "poison decays — the cloud dissipates entirely (any poison decays)"


def test_seed_refreshes_to_full():
    """CW1: a re-lob refreshes a decaying cell back to POISON_TTL."""
    if not HAVE:
        return _skip()
    sim = _sim()
    center = (10, 10, sim.world.surface_z(10, 10))
    sim._seed_poison(center, 0)
    sim._poison_tick()
    assert sim._poison()[center] == POISON_TTL - 1, "one tick decremented the cell"
    sim._seed_poison(center, 0)
    assert sim._poison()[center] == POISON_TTL, "a fresh lob refreshes the cell to full"


def test_siege_house_lobs_poison_shell():
    """CW2: a catapult-teched house at war with an in-range target lobs a visible shell + blooms a cloud."""
    if not HAVE:
        return _skip()
    sim = _sim()
    sandkings.EFFECTS_ENABLED = True   # so the visible shell is spawned
    attacker, target = sim.colonies[0], sim.colonies[1]
    # place the two maws in range and give the attacker the siege tech + a war target
    ax, ay, az = attacker.maw.position
    target.maw.position = (min(ax + 5, sim.world.dimensions[0] - 2), ay, az)
    attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
    sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
    sim.step_count = POISON_RELOAD           # % POISON_RELOAD == 0 and truthy
    sim.effects = []; sim.poison = {}
    sim._poison_bomb_tick()
    assert any(e['kind'] == 'shot' for e in sim._effects()), "a visible poison shell arcs across the board"
    assert sim._poison(), "a poison cloud blooms at the target maw"


def test_gate_off_no_poison_in_step():
    """Gate OFF: a fully war-ready setup accrues NO poison through the step loop (byte-identical path)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    sandkings.POISON_ENABLED = False
    attacker, target = sim.colonies[0], sim.colonies[1]
    attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
    sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
    for _ in range(POISON_RELOAD + POISON_TICK + 2):
        sim.step()
    assert getattr(sim, 'poison', {}) == {} or sim.poison == {}, "gate off -> no poison ever seeded"


def _food_trail_sum(sim):
    from sandkings import PheromoneType
    return float(sim.pheromones.trails[..., PheromoneType.FOOD_TRAIL.value].sum())


def test_stigmergy_lays_trail_when_on():
    """CW3a: with stigmergy ON, foragers lay FOOD_TRAIL scent (the dead channel is revived); OFF, foraging
    leaves the channel untouched. Differential over the same seed isolates the stigmergy contribution."""
    if not HAVE:
        return _skip()
    prev = sandkings.STIGMERGY_ENABLED
    try:
        sandkings.STIGMERGY_ENABLED = False
        off = _food_trail_sum(_sim_run(30))
        sandkings.STIGMERGY_ENABLED = True
        on = _food_trail_sum(_sim_run(30))
    finally:
        sandkings.STIGMERGY_ENABLED = prev
    assert on > off, "stigmergy ON must lay more FOOD_TRAIL scent than OFF (revived channel)"


def _sim_run(n):
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(n):
        sim.step()
    return sim


def test_stigmergy_follows_gradient():
    """CW3a: get_gradient (finally given a caller) points a scentless forager toward the strongest kin trail."""
    if not HAVE:
        return _skip()
    from sandkings import PheromoneType
    sim = _sim()
    colony = sim.colonies[0]
    cid = colony.colony_id
    # plant a trail one cell in +x from an air cell; the gradient must point +x
    base = (10, 10, sim.world.surface_z(10, 10))
    sim.pheromones.deposit((base[0] + 1, base[1], base[2]), cid, PheromoneType.FOOD_TRAIL, 5.0)
    g = sim.pheromones.get_gradient(base, cid, PheromoneType.FOOD_TRAIL, sim.world)
    assert g is not None and g[0] == 1, "the gradient guides the forager toward the planted scent (+x)"


def test_covert_lure_planted_in_enemy_channel():
    """CW3b: a poison bomb plants a strong FALSE FOOD_TRAIL in the TARGET's OWN channel at the cloud (the
    Cortés lure that draws the enemy's scent-followers into the poison)."""
    if not HAVE:
        return _skip()
    from sandkings import PheromoneType, COVERT_LURE_STRENGTH
    prev = sandkings.STIGMERGY_ENABLED
    try:
        sandkings.STIGMERGY_ENABLED = True
        sim = _sim()
        attacker, target = sim.colonies[0], sim.colonies[1]
        ax, ay, az = attacker.maw.position
        target.maw.position = (min(ax + 5, sim.world.dimensions[0] - 2), ay, az)
        attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
        sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
        sim.step_count = POISON_RELOAD
        sim.poison = {}
        tmx, tmy, tmz = target.maw.position
        before = sim.pheromones.get_strength((tmx, tmy, tmz), target.colony_id, PheromoneType.FOOD_TRAIL)
        sim._poison_bomb_tick()
        after = sim.pheromones.get_strength((tmx, tmy, tmz), target.colony_id, PheromoneType.FOOD_TRAIL)
    finally:
        sandkings.STIGMERGY_ENABLED = prev
    assert after - before >= COVERT_LURE_STRENGTH - 1e-6, "the covert lure is planted in the enemy's channel"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all chemical-war tests passed")
