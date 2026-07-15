"""Maw forage-mode lever (SPEC_FOOD_WEB Phase 4): the maw's directive d3 biases which food guild the
colony's foragers steer to. Tests the _find_food_target `prefer` discount directly (deterministic)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    from sandkings import SandKingsSimulation, VoxelType, OASIS_RADIUS
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def test_forage_mode_biases_target():
    if not HAVE:
        return _skip()
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=60, height=40, depth=12, num_colonies=2)
    w, h, d = sim.world.dimensions
    cx, cy = w // 2, h // 2
    z = d - 2
    oasis_food = (cx, cy, z)                    # near the oasis (aquatic)
    land_food = (cx + 14, cy, z)               # away from the oasis (terrestrial)
    for (x, y, zz) in (oasis_food, land_food):
        sim.world.voxels[x, y, zz] = VoxelType.FOOD.value
    pos = (cx + 8, cy, z)                       # forager: land food is nearer (dist 6 vs 8)
    assert sim._find_food_target(pos, 30) == land_food, "no bias -> nearest (land) food"
    assert sim._find_food_target(pos, 30, prefer='aquatic') == oasis_food, \
        "aquatic -> the discounted oasis food wins despite being farther"
    assert sim._find_food_target(pos, 30, prefer='terrestrial') == land_food, \
        "terrestrial -> the land food is preferred"


def test_forage_mode_classification():
    """_forage_mode maps directive d3 to a guild, and is None when the maw-RL is off."""
    if not HAVE:
        return _skip()
    import sandkings
    import torch
    random.seed(1); np.random.seed(1)
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
    c = sim.colonies[0]
    c.maw_directive = torch.tensor([0.5, 0.5, 0.5, 0.1])   # d3 low -> aquatic
    prev = sandkings.MAW_RL_ENABLED
    assert sim._forage_mode(c) is None, "gate off -> no forage bias"
    sandkings.MAW_RL_ENABLED = True
    try:
        assert sim._forage_mode(c) == 'aquatic'
        c.maw_directive = torch.tensor([0.5, 0.5, 0.5, 0.5]); assert sim._forage_mode(c) == 'hunt'
        c.maw_directive = torch.tensor([0.5, 0.5, 0.5, 0.9]); assert sim._forage_mode(c) == 'terrestrial'
        c.maw_directive = torch.tensor([0.5, 0.5, 0.5])       # a 3-dim (old) directive -> no d3
        assert sim._forage_mode(c) is None
    finally:
        sandkings.MAW_RL_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all forage-mode tests passed")
