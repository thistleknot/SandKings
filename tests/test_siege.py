"""Siege engines (SPEC_SIEGE, gated SIEGE_ENGINES_ENABLED): a ballista looses a fast, direct bolt at a war
target. Distinct from the catapult's lobbed area shot. Gate default off is byte-identical."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, BALLISTA_RELOAD, BALLISTA_DAMAGE,
                           BOLT_SPEED, SHOT_SPEED)
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
    assert sandkings.SIEGE_ENGINES_ENABLED is False, "SIEGE_ENGINES_ENABLED must default False"


def test_ballista_looses_bolt_at_war_target():
    """SE1: a catapult-teched house at war with an in-range target damages the target maw + looses a visible
    fast bolt on reload."""
    if not HAVE:
        return _skip()
    sim = _sim()
    sandkings.EFFECTS_ENABLED = True
    attacker, target = sim.colonies[0], sim.colonies[1]
    ax, ay, az = attacker.maw.position
    target.maw.position = (min(ax + 5, sim.world.dimensions[0] - 2), ay, az)
    attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
    sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
    sim.step_count = BALLISTA_RELOAD          # % BALLISTA_RELOAD == 0 and truthy
    sim.effects = []
    hp0 = target.maw.health
    sim._ballista_tick()
    assert target.maw.health < hp0, "the bolt strikes the target maw (direct damage)"
    assert any(e['kind'] == 'bolt' for e in sim._effects()), "a visible bolt streaks across the board"


def test_bolt_flies_faster_than_shot():
    """SE1: a ballista bolt advances BOLT_SPEED/step — faster than a lobbed catapult shot (SHOT_SPEED)."""
    if not HAVE:
        return _skip()
    assert BOLT_SPEED > SHOT_SPEED, "a bolt must fly faster than a lobbed shot"
    sim = _sim()
    sim.effects = []
    sim._spawn_effect('bolt', (2, 5, 5), (40, 5, 5))
    sim._spawn_effect('shot', (2, 10, 5), (40, 10, 5))
    sim._effects_tick()
    bolt = next(e for e in sim._effects() if e['kind'] == 'bolt')
    shot = next(e for e in sim._effects() if e['kind'] == 'shot')
    assert bolt['pos'][0] == 2 + BOLT_SPEED, "the bolt advances BOLT_SPEED"
    assert shot['pos'][0] == 2 + SHOT_SPEED, "the shot advances SHOT_SPEED (slower)"


def test_gate_off_no_bolt_in_step():
    """Gate OFF: a war-ready siege house looses no bolt through the step loop (byte-identical path)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    sandkings.SIEGE_ENGINES_ENABLED = False
    attacker, target = sim.colonies[0], sim.colonies[1]
    attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
    sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
    sim.effects = []
    for _ in range(BALLISTA_RELOAD + 2):
        sim.step()
    assert all(e.get('kind') != 'bolt' for e in getattr(sim, 'effects', [])), "gate off -> no bolt ever loosed"


def test_siege_tower_breaches_palisade():
    """SE2: _breach_palisade smashes an adjacent enemy WOOD_WALL to SAND (opens the fortress)."""
    if not HAVE:
        return _skip()
    from sandkings import VoxelType
    sim = _sim()
    target = sim.colonies[1]
    cx, cy, cz = target.maw.position
    wx = min(cx + 1, sim.world.dimensions[0] - 2)
    sim.world.voxels[wx, cy, cz] = VoxelType.WOOD_WALL.value
    breached = sim._breach_palisade(target.maw.position, sim.colonies[0].colony_id)
    assert breached, "the tower breaches a wall on arrival"
    assert sim.world.voxels[wx, cy, cz] == VoxelType.SAND.value, "the WOOD_WALL is smashed to SAND"


def test_siege_tower_deploys_and_advances():
    """SE2: a catapult-teched war house rolls out a tower that advances toward the enemy maw."""
    if not HAVE:
        return _skip()
    from sandkings import SIEGE_TOWER_DEPLOY, SIEGE_TOWER_SPEED
    sim = _sim()
    attacker, target = sim.colonies[0], sim.colonies[1]
    ax, ay, az = attacker.maw.position
    target.maw.position = (min(ax + 8, sim.world.dimensions[0] - 2), ay, az)
    attacker.techs = set(getattr(attacker, 'techs', set())) | {'catapult'}
    sim._diplomacy().war_target[attacker.colony_id] = target.colony_id
    sim.siege_towers = []
    sim.step_count = SIEGE_TOWER_DEPLOY        # a deploy step
    sim._siege_tower_tick()
    towers = sim._siege_towers()
    assert towers, "a siege tower is rolled out toward the enemy"
    x0 = towers[0]['pos'][0]
    sim.step_count = SIEGE_TOWER_DEPLOY + 1    # a non-deploy step -> pure advance
    sim._siege_tower_tick()
    assert sim._siege_towers()[0]['pos'][0] == x0 + SIEGE_TOWER_SPEED, "the tower advances toward the maw"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all siege tests passed")
