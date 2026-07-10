"""Acceptance tests for SPEC_HYDRO_HAND.md (HH1-HH5) - the hand's water & seeds.

Rain irrigates (never drowns); a deluge floods the open but spares whatever the
colonies dammed; seeds become tended crops. Failure modes covered: rain
drowning, the dam rule not sheltering, seeds not taking, a bound keeper still
acting, and state not pickling / evolution not inert.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (FLOOD_RISE, WATER_FLOOD_DUR, WATER_RAIN_DUR, SandKing,
                       SandKingsSimulation, UnitType, VoxelType)


def make_sim(seed: int = 5) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def _crops(sim):
    return int(np.count_nonzero(sim.world.voxels == VoxelType.CROP.value))


def test_rain_tills_and_boosts_crops_without_drowning():
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    z = sim.world.surface_z(cx + 1, cy)
    sim.world.voxels[cx + 1, cy, z] = VoxelType.CROP.value  # a crop at surface
    sim._crops()[(cx + 1, cy, z)] = 0
    colony = sim.colonies[0]
    u = SandKing(colony.colony_id, (cx, cy, sim.world.surface_z(cx, cy)),
                 UnitType.WORKER)
    colony.units.append(u)
    hp = u.health
    sim.keeper_water(cx, cy, big=False)
    for _ in range(WATER_RAIN_DUR):
        sim._keeper_water_tick()
        sim.step_count += 1
    assert u.health == hp, "rain never drowns"
    assert sim._crops().get((cx + 1, cy, z), 0) > 0, "the crop is watered"


def test_deluge_drowns_the_open_but_spares_the_dammed():
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    colony = sim.colonies[0]
    opener = SandKing(colony.colony_id, (cx, cy, sim.world.surface_z(cx, cy)),
                      UnitType.WORKER)
    # raise a bank at (cx+4,cy) above the water line - a dam
    dx, dy = cx + 4, cy
    base = sim.world.surface_z(dx, dy)
    for zz in range(base + 1, min(sim.world.depth, base + FLOOD_RISE + 3)):
        sim.world.voxels[dx, dy, zz] = VoxelType.SAND.value
    dammed = SandKing(colony.colony_id, (dx, dy, sim.world.surface_z(dx, dy)),
                      UnitType.WORKER)
    colony.units += [opener, dammed]
    oh, dh = opener.health, dammed.health
    sim.keeper_water(cx, cy, big=True)
    for _ in range(WATER_FLOOD_DUR):
        sim._keeper_water_tick()
        sim.step_count += 1
    assert opener.health < oh, "the open unit drowns in the deluge"
    assert dammed.health == dh, "behind a raised bank it is spared (terraforming)"


def test_seed_sows_tended_crops():
    sim = make_sim()
    before = _crops(sim)
    sim.keeper_seed(10, 10)
    assert _crops(sim) > before, "seeds become crops"
    # the sown crops joined the growth registry
    assert any(v == 0 for v in sim._crops().values())


def test_bound_keeper_cannot_water_or_seed():
    sim = make_sim()
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    sim.keeper_water(20, 15, big=True)
    assert getattr(sim, 'kw_until', 0) <= sim.step_count, "no water when bound"
    before = _crops(sim)
    sim.keeper_seed(20, 15)
    assert _crops(sim) == before, "no seeds when bound"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim.keeper_water(20, 15)
    sim.keeper_seed(20, 15)
    for _ in range(12):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_keeper_water_tick" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all hydro-hand tests passed")
