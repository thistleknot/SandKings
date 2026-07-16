"""Integration test for the gated maw-RL hook (sandkings._maw_rl_tick).

Gate-off => no maw_rl state appears (hook returns immediately; battery byte-identical).
Gate-on  => the hook runs on the batch clock, builds obs from the FROZEN encoder, and
sets colony.maw_directive without crashing. Small sim + few steps to stay fast.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np

try:
    import torch
    import sandkings
    from sandkings import SandKingsSimulation, UnitType
    from neural_hive import HiveMindBrain, SoldierLayer
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (torch/sandkings unavailable)")
    return True


def _neural_sim(seed=0):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)
    for c in sim.colonies:
        c.genome.use_neural = True
        if c.genome.brain is None:
            c.genome.brain = HiveMindBrain()
        for u in c.units:
            if u.unit_type == UnitType.SOLDIER and getattr(u, 'brain_layer', None) is None:
                u.brain_layer = SoldierLayer(); u.brain_layer.steps_alive = 0
    return sim


def test_gate_off_no_maw_rl_state():
    if not HAVE:
        return _skip()
    assert sandkings.MAW_RL_ENABLED is False, "default gate must be off"
    sim = _neural_sim()
    for _ in range(120):
        sim.step()
    assert all(getattr(c, 'maw_directive', None) is None for c in sim.colonies), \
        "gate off: no directive should be produced"
    assert all(getattr(c, 'maw_rl', None) is None for c in sim.colonies)
    assert all(getattr(c, 'spawn_rl', None) is None for c in sim.colonies), \
        "gate off: no spawn residual should be created"


def test_gate_on_sets_directive():
    if not HAVE:
        return _skip()
    prev = sandkings.MAW_RL_ENABLED
    sandkings.MAW_RL_ENABLED = True
    try:
        sim = _neural_sim(seed=1)
        for _ in range(120):          # crosses batch boundaries (POP_TICK_INTERVAL=50, staggered)
            sim.step()
        got = [c for c in sim.colonies if getattr(c, 'maw_directive', None) is not None]
        assert got, "gate on: expected at least one maw_directive after a batch boundary"
        from maw_brain import MAW_DIRECTIVE_DIM
        for c in got:
            assert tuple(c.maw_directive.shape) == (MAW_DIRECTIVE_DIM,), c.maw_directive.shape
            assert getattr(c, 'maw_rl', None) is not None
        # the spawn residual (15%) is created as soon as a neural soldier acts under the gate
        assert any(getattr(c, 'spawn_rl', None) is not None for c in sim.colonies), \
            "gate on: expected the spawn residual (15%) to be created"
    finally:
        sandkings.MAW_RL_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all maw integration tests passed")
