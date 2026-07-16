"""Acceptance tests for SPEC_ARENA.md (AR1-AR7) — the keeper's arena console.

Gifts feed and teach, wrath torments (predators + non-lethal temperature),
neutrals wander. Failure modes covered: roster classes overlapping or drifting
from the release whitelist, small_spider missing/too strong, arena temperature
KILLING units (it must not), the temp endpoint unwired, a bound keeper still
acting, and state not pickling / evolution not inert.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (ARENA_TEMP_TICK, FAUNA, KEEPER_FAUNA, KEEPER_GIFTS,
                       KEEPER_NEUTRAL, KEEPER_WRATH, SandKingsSimulation,
                       VoxelType)


def make_sim(seed: int = 3) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_roster_partitions_and_small_spider():
    g, w, n = set(KEEPER_GIFTS), set(KEEPER_WRATH), set(KEEPER_NEUTRAL)
    assert not (g & w) and not (g & n) and not (w & n), "classes are disjoint"
    assert g | w | n == set(KEEPER_FAUNA), "the three classes ARE the roster"
    assert "small_spider" in FAUNA and "small_spider" in KEEPER_GIFTS
    _w, hp, atk, _pack, hunt, bounty = FAUNA["small_spider"]
    assert hp < 15 and bounty >= 3 and hunt == 0, "weak, non-hunting, good food"


def test_release_validates_and_spawns_each_class():
    sim = make_sim()
    for species in ("small_spider", "spider", "squirrel"):
        before = len(sim._fauna())
        sim.keeper_release(species)
        assert len(sim._fauna()) > before, f"{species} spawned"
    before = len(sim._fauna())
    sim.keeper_release("griffon")  # not in the roster
    assert len(sim._fauna()) == before, "off-roster species is refused"


def test_garage_species_is_the_roster():
    import dashboard
    assert dashboard.GARAGE_SPECIES is KEEPER_FAUNA, "no whitelist drift"


def test_arena_temperature_drains_but_never_kills():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.maw.food_stored = 300.0
    # force one unit to the surface so it is 'exposed'
    u = colony.units[0]
    sx, sy, _ = u.position
    u.position = (sx, sy, sim.world.surface_z(sx, sy))
    assert sim._exposed(u)
    hp_before = [unit.health for unit in colony.units]
    food_before = colony.maw.food_stored
    sim.step_count = 0  # a tick boundary
    sim.keeper_temperature("heat")
    assert getattr(sim, "arena_heat_until", 0) > 0
    for k in range(ARENA_TEMP_TICK):
        sim.step_count = k * ARENA_TEMP_TICK  # keep hitting the cadence
        sim._arena_tick()
    assert colony.maw.food_stored < food_before, "thermoregulation drains hoard"
    assert [unit.health for unit in colony.units] == hp_before, \
        "arena temperature is UNCOMFORTABLE, never lethal"


def test_arena_temperature_wilts_crops():
    sim = make_sim()
    ripe = VoxelType.CROP_RIPE.value
    # sow a patch of ripe crop on the surface
    sown = 0
    for x in range(4, 24):
        z = sim.world.surface_z(x, 8)
        if 0 <= z < sim.world.depth:
            sim.world.voxels[x, 8, z] = ripe
            sown += 1
    assert sown > 0
    sim.keeper_temperature("cold")
    for k in range(40):
        sim.step_count = k * ARENA_TEMP_TICK
        sim.arena_cold_until = sim.step_count + 100  # keep it running
        sim._arena_tick()
    remaining = int(np.count_nonzero(sim.world.voxels == ripe))
    assert remaining < sown, "the fields wilt under the wave"


def test_temp_endpoint_and_bound_keeper():
    from fastapi.testclient import TestClient

    from dashboard import TerrariumRunner, create_app
    sim = make_sim()
    client = TestClient(create_app(TerrariumRunner(sim)))
    assert client.post("/api/keeper/temp", json={"dir": "heat"}).status_code == 200
    assert getattr(sim, "arena_heat_until", 0) > 0
    assert client.post("/api/keeper/temp", json={"dir": "sideways"}).status_code == 400
    # PS5: a bound keeper cannot loose predators or change the temperature
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    before = len(sim._fauna())
    sim.keeper_release("spider")
    sim.keeper_temperature("cold")
    assert len(sim._fauna()) == before, "bound keeper cannot loose beasts"
    assert getattr(sim, "arena_cold_until", 0) <= sim.step_count, \
        "bound keeper cannot change the temperature"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim.keeper_temperature("heat")
    sim.keeper_release("small_spider")
    for _ in range(12):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_arena_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all arena tests passed")
