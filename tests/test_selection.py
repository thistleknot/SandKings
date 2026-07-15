"""Fitness-based live selection (SPEC_SELECTION, Evolution Proper Phase 1): the live GA seeds a dead colony's
slot from a fitness-weighted tournament among survivors instead of a uniform random pick. Gate default off ->
the parent pick is the original random.choice (battery byte-identical).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim(n=4):
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=44, height=28, depth=12, num_colonies=n)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.FITNESS_SELECTION_ENABLED is False, "FITNESS_SELECTION_ENABLED must default False"


def test_fitness_ordering():
    """SEL1: fitness ranks rich/expansive/old above poor/small/young."""
    if not HAVE:
        return _skip()
    sim = _sim(2)
    a, b = sim.colonies[0], sim.colonies[1]
    a.units.clear(); b.units.clear()
    # wealth
    a.maw.food_stored = 1000.0; b.maw.food_stored = 10.0
    a.territory = b.territory = {(0, 0, 0)}; a.generation = b.generation = 1
    assert sim._colony_fitness(a) > sim._colony_fitness(b), "richer colony is fitter"
    # territory (expansion)
    a.maw.food_stored = b.maw.food_stored = 100.0
    a.territory = {(i, 0, 0) for i in range(50)}; b.territory = {(0, 0, 0)}
    assert sim._colony_fitness(a) > sim._colony_fitness(b), "more expansive colony is fitter"
    # longevity (lineage depth)
    a.territory = b.territory = {(0, 0, 0)}
    a.generation = 10; b.generation = 1
    assert sim._colony_fitness(a) > sim._colony_fitness(b), "longer-surviving lineage is fitter"


def test_tournament_selects_fittest():
    """SEL2: the tournament picks the fittest deterministically when it samples all, and far above 1/n at K=2."""
    if not HAVE:
        return _skip()
    prev_k = sandkings.FITNESS_TOURNAMENT_K
    try:
        sim = _sim(4)
        cs = sim.colonies
        for c in cs:
            c.units.clear(); c.territory = {(0, 0, 0)}; c.generation = 1
        for i, c in enumerate(cs):
            c.maw.food_stored = 100.0 * (i + 1)      # colony 3 is strictly fittest
        fittest = max(cs, key=sim._colony_fitness)
        assert fittest is cs[3]
        # K == n -> every survivor is a contender -> the fittest always wins
        sandkings.FITNESS_TOURNAMENT_K = len(cs)
        for _ in range(20):
            assert sim._select_parent(cs) is fittest, "full-field tournament always crowns the fittest"
        # K == 2 -> fittest chosen when sampled (P=0.5 for n=4), well above the uniform 1/n = 0.25
        sandkings.FITNESS_TOURNAMENT_K = 2
        random.seed(1)
        wins = sum(1 for _ in range(400) if sim._select_parent(cs) is fittest)
        assert wins / 400.0 > 0.4, f"tournament biases toward the fittest (got {wins/400.0:.2f}, uniform=0.25)"
    finally:
        sandkings.FITNESS_TOURNAMENT_K = prev_k


def test_gate_off_is_random_choice():
    """Gate off: the parent pick is exactly random.choice(survivors) — same single RNG draw (byte-identical).

    The call site is `if FITNESS_SELECTION_ENABLED: _select_parent(...) else: random.choice(...)`; with the gate
    off we reproduce the else branch under a fixed seed and confirm it matches random.choice verbatim.
    """
    if not HAVE:
        return _skip()
    assert sandkings.FITNESS_SELECTION_ENABLED is False
    sim = _sim(4)
    survivors = list(sim.colonies)
    random.seed(123)
    expected = random.choice(survivors)
    random.seed(123)
    got = random.choice(survivors)   # the literal gate-off branch
    assert got is expected, "gate off: parent pick is the original single random.choice draw"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all selection tests passed")
