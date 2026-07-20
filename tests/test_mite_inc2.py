"""SPEC_MITE_STORM Increment 2 — herbal cure (crops) + quarantine (healthy-fraction). Gated MITE_HERBAL_ENABLED;
off => the Inc-1 water-only behaviour is untouched (battery byte-identical, enforced by run_tests._GATE_NAMES).

Clauses:
- default gate off
- HERBAL CURE: an infested host fully surrounded by ripe crops is cured (crop-density-derived rate -> 1.0)
- QUARANTINE: a quarantined host does not spread the contagion to a healthy neighbour
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import sandkings as sk


def _small():
    return sk.SandKingsSimulation(width=14, height=14, depth=6, num_colonies=2)


def _clear_ring(sim, x, y, z, vox):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            sim.world.set_voxel(x + dx, y + dy, z, vox)


def test_mite_inc2_gate_default_off():
    assert sk.MITE_HERBAL_ENABLED is False, "Increment 2 gate defaults off (battery byte-identical)"


def test_herbal_cure_by_surrounding_crops():
    random.seed(0)
    sk.MITE_STORM_ENABLED = True
    sk.MITE_HERBAL_ENABLED = True
    try:
        sim = _small()
        u = sim.colonies[0].units[0]
        u.position = [7, 7, 3]
        x, y, z = u.position
        _clear_ring(sim, x, y, z, sk.VoxelType.CROP_RIPE)   # 8 crop neighbours -> cure prob = 8/8 = 1.0
        sim.world.set_voxel(x, y, z, sk.VoxelType.AIR)
        u.infested = True
        u.quarantined = False
        sim._mite_infest_tick()
        assert u.infested is False, "a host ringed by ripe crops is herbally cured"
    finally:
        sk.MITE_STORM_ENABLED = False
        sk.MITE_HERBAL_ENABLED = False


def test_quarantine_blocks_spread():
    random.seed(0)
    sk.MITE_STORM_ENABLED = True
    sk.MITE_HERBAL_ENABLED = True
    try:
        sim = _small()
        c = sim.colonies[0]
        if len(c.units) < 2:
            print("SKIP (colony too small)")
            return
        u, v = c.units[0], c.units[1]
        u.position = [7, 7, 3]
        v.position = [8, 7, 3]                              # healthy neighbour, adjacent
        _clear_ring(sim, 7, 7, 3, sk.VoxelType.AIR)         # no water, no crop -> no cure path fires
        u.infested = True
        u.quarantined = True                                # already isolated by the colony
        u.health = 10                                       # survives one poison tick (POISON_DAMAGE=3)
        v.infested = False
        sim._mite_infest_tick()
        assert v.infested is False, "a quarantined host does not jump the contagion to a healthy neighbour"
    finally:
        sk.MITE_STORM_ENABLED = False
        sk.MITE_HERBAL_ENABLED = False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all mite inc2 tests passed")
