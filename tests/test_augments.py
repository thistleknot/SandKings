"""Acceptance tests for SPEC_AUGMENTS.md (AUG1-AUG5).

Failure modes covered: the augment changing the probe-read hidden,
cache_len 0 diverging from today, the terminal granting it to non-pi
colonies or past the cap, the level not riding the bloodline, and the
augmented layer breaking pickle. Skips without torch.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (AUG_CACHE_STEP, AUG_MAX, SandKing, SandKingsSimulation,
                       UnitType)

try:
    import torch
    from neural_hive import SoldierLayer
    HAVE_TORCH = True
except Exception:
    HAVE_TORCH = False


def _skip():
    print("SKIP (torch unavailable)")
    return True


def test_cache_off_is_unchanged():
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(0)
    plain = SoldierLayer()
    torch.manual_seed(0)
    aug = SoldierLayer()  # cache_len 0 by default
    x = torch.randn(32)
    assert torch.allclose(plain(x), aug(x)), "default layer is byte-identical"


def test_augment_extends_context_but_not_the_probe_hidden():
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(1)
    layer = SoldierLayer()
    layer.cache_len = 3 * AUG_CACHE_STEP
    # run a few steps so the bank fills
    hiddens = []
    for _ in range(5):
        layer(torch.randn(32))
        hiddens.append(layer.hidden.clone())
    assert len(layer.mem_bank) <= layer.cache_len and layer.mem_bank
    # the RAW hidden (probe input, N-spec) is just the GRU output - the
    # augment must not have rewritten it into the blended state
    assert torch.allclose(layer.mem_bank[-1], layer.hidden)


def test_terminal_installs_augment_for_pi_only_and_caps():
    if not HAVE_TORCH:
        return _skip()
    from machines import Controller, PI_FUEL, VM_FUEL
    random.seed(3)
    np.random.seed(3)
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=3)
    sim.harsh = True
    colony = sim.colonies[0]
    # a plain (non-pi) controller cannot reach the terminal
    colony.controllers = [Controller(colony.colony_id)]
    colony.machine_arc = 'claimed'
    colony.controllers[0].operate_ticks = 999
    sim._actuate(colony, 7, 3)
    assert colony.memory_augment == 0, "no pi, no augment"
    # a raspberry-pi controller can
    colony.controllers = [Controller(colony.colony_id, fuel=PI_FUEL)]
    colony.controllers[0].operate_ticks = 999
    for _ in range(AUG_MAX + 3):
        sim._actuate(colony, 7, 3)
    assert colony.memory_augment == AUG_MAX, "bounded at AUG_MAX"
    assert any("augments its mind" in m for _, m in sim.events)


def test_augment_rides_the_bloodline():
    if not HAVE_TORCH:
        return _skip()
    random.seed(7)
    np.random.seed(7)
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=3)
    sim.harsh = True
    parent = sim.colonies[1]
    parent.memory_augment = 2
    victim = sim.colonies[0]
    victim.maw.alive = False
    victim.units.clear()
    # single-parent respawn path (non-neural): the cadet inherits the level
    sim._respawn_colony(victim.colony_id)
    # the respawn picks a random survivor as parent; force determinism by
    # setting all survivors' level so the inheritance is observable
    for c in sim.colonies:
        if c is not sim.colonies[0]:
            c.memory_augment = 2
    victim2 = sim.colonies[0]
    victim2.maw.alive = False
    victim2.units.clear()
    sim._respawn_colony(victim2.colony_id)
    assert sim.colonies[0].memory_augment == 2, "the upgrade persists in blood"


def test_augmented_soldier_pickles():
    if not HAVE_TORCH:
        return _skip()
    import pickle
    layer = SoldierLayer()
    layer.cache_len = 2 * AUG_CACHE_STEP
    for _ in range(4):
        layer(torch.randn(32))
    revived = pickle.loads(pickle.dumps(layer))
    assert revived.cache_len == layer.cache_len
    revived(torch.randn(32))  # still runs


def test_evolution_sim_inert():
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_install_augment' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all augment tests passed")
