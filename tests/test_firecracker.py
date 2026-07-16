"""Acceptance for SPEC_ARENA AR8 - firecracker disaster + flies + mouse.

Failure modes: the firecracker not lighting flammable / not scorching an exposed
unit, the new fauna not classified/releasable, and a bound keeper still igniting.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (KEEPER_GIFTS, KEEPER_NEUTRAL, FAUNA, SandKing,
                       SandKingsSimulation, UnitType, VoxelType)


def make_sim(seed: int = 4) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


def test_new_fauna_classified_and_releasable():
    assert 'fly' in KEEPER_GIFTS and 'mouse' in KEEPER_NEUTRAL
    assert 'fly' in FAUNA and 'mouse' in FAUNA
    sim = make_sim()
    for sp in ('fly', 'mouse'):
        before = len(sim._fauna())
        sim.keeper_release(sp)
        assert len(sim._fauna()) > before, f"{sp} released"


def test_firecracker_lights_fire_and_scorches():
    sim = make_sim()
    cx, cy = 20, 15
    z = sim.world.surface_z(cx, cy)
    sim.world.voxels[cx, cy, z] = VoxelType.CROP.value  # something flammable
    colony = sim.colonies[0]
    u = SandKing(colony.colony_id, (cx + 1, cy, z), UnitType.WORKER)
    colony.units.append(u)
    hp = u.health
    sim.keeper_ignite(cx, cy)
    assert sim._fires(), "the firecracker lit a fire"
    assert u.health < hp or u not in colony.units, "an exposed unit is scorched"


def test_bound_keeper_cannot_ignite():
    sim = make_sim()
    sim.keeper_bound = True
    sim._hand_stayed_logged = False
    cx, cy = 20, 15
    z = sim.world.surface_z(cx, cy)
    sim.world.voxels[cx, cy, z] = VoxelType.CROP.value
    sim.keeper_ignite(cx, cy)
    assert not sim._fires(), "the bound god cannot light a firecracker"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all firecracker tests passed")
