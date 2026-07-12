"""Acceptance tests for SPEC_EVOLUTION.md (EV1-EV6).

Failure modes covered: architecture genes escaping bounds, a variable-
depth brain producing the wrong encoding shape, crossover ignoring a
parent, grafting across different topologies raising a shape error, the
sexual respawn not recombining, and evolved brains breaking pickle.
Skips cleanly when torch is unavailable.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import ColonyGenome, SandKingsSimulation

try:
    import torch
    from neuroevolution import (BRAIN_DEPTH_MAX, BRAIN_HIDDEN_MAX,
                                BRAIN_HIDDEN_MIN, architecture_of, build_brain,
                                crossover_genome, graft_into)
    HAVE_TORCH = True
except Exception:
    HAVE_TORCH = False


def _skip():
    print("SKIP (torch unavailable)")
    return True


def test_architecture_genes_mutate_in_bounds():
    random.seed(0)
    np.random.seed(0)
    g = ColonyGenome()
    g.use_neural = False  # bounds test needs no brain build
    g.brain_hidden, g.brain_depth = 24, 1
    for _ in range(200):
        g = g.mutate(0.3)
        assert BRAIN_HIDDEN_MIN <= g.brain_hidden <= BRAIN_HIDDEN_MAX
        assert 1 <= g.brain_depth <= BRAIN_DEPTH_MAX


def test_build_brain_valid_at_every_depth():
    if not HAVE_TORCH:
        return _skip()
    for depth in range(1, BRAIN_DEPTH_MAX + 1):
        g = ColonyGenome()
        g.use_neural = True
        g.brain_hidden, g.brain_depth = 64, depth
        brain = build_brain(g)
        out = brain(torch.zeros(40))
        assert out.shape == (32,), (depth, out.shape)
        # SDM encoder: the readout maps the Kanerva memory (M prototypes) -> the
        # encoding_dim=32 the SoldierLayer consumes. Fixed shape at every depth.
        from neural_hive import KANERVA_PROTOS
        assert brain.readout.out_features == 32
        assert brain.readout.in_features == KANERVA_PROTOS


def test_crossover_draws_from_both_parents():
    if not HAVE_TORCH:
        return _skip()
    random.seed(3)
    np.random.seed(3)
    a = ColonyGenome()
    a.use_neural = True
    a.aggression, a.brain_hidden, a.brain_depth = 0.1, 40, 1
    a.brain = build_brain(a)
    b = ColonyGenome()
    b.use_neural = True
    b.aggression, b.brain_hidden, b.brain_depth = 0.9, 120, 3
    b.brain = build_brain(b)
    aggs, archs = set(), set()
    for _ in range(30):
        c = crossover_genome(a, b, 0.0)  # rate 0 -> genes are parent values
        aggs.add(round(c.aggression, 3))
        archs.add(architecture_of(c))
        assert c.brain(torch.randn(40)).shape == (32,)
    assert aggs == {0.1, 0.9}, "each disposition comes from a parent"
    assert len(archs) >= 2, "architecture recombines across parents"


def test_graft_across_different_topologies():
    if not HAVE_TORCH:
        return _skip()
    small = ColonyGenome()
    small.use_neural = True
    small.brain_hidden, small.brain_depth = 32, 1
    big = ColonyGenome()
    big.use_neural = True
    big.brain_hidden, big.brain_depth = 128, 3
    child = build_brain(big)
    graft_into(child, build_brain(small))  # different shapes: overlap only
    assert child(torch.zeros(40)).shape == (32,), "grafted child still runs"


def test_sexual_respawn_recombines():
    if not HAVE_TORCH:
        return _skip()
    random.seed(7)
    np.random.seed(7)
    from neural_hive import HiveMindBrain
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=3)
    sim.harsh = True
    for colony in sim.colonies:
        colony.genome.use_neural = True
        colony.genome.brain_hidden = 48 + 16 * colony.colony_id
        colony.genome.brain = build_brain(colony.genome)
    # kill colony 0; two neural survivors remain -> sexual reproduction
    victim = sim.colonies[0]
    victim.maw.alive = False
    victim.units.clear()
    sim._respawn_colony(victim.colony_id)
    child = sim.colonies[0]
    assert child.genome.use_neural and child.genome.brain is not None
    assert child.genome.brain(torch.zeros(40)).shape == (32,)


def test_courtship_prefers_allied_pair():
    if not HAVE_TORCH:
        return _skip()
    random.seed(1)
    np.random.seed(1)
    sim = SandKingsSimulation(width=40, height=30, depth=10, num_colonies=4)
    sim.harsh = True
    for c in sim.colonies:
        c.genome.use_neural = True
        c.genome.brain = build_brain(c.genome)
    d = sim._diplomacy()
    d.rel(1, 2).trust = 60
    d.rel(2, 1).trust = 60
    d.update_ally_latch(1, 2)
    a, b, mode = sim._choose_mates([c for c in sim.colonies])
    assert mode == "courtship"
    assert {a.colony_id, b.colony_id} == {1, 2}, "allied pair courts"


def test_union_founds_new_house_and_supersedure_grudge():
    if not HAVE_TORCH:
        return _skip()
    random.seed(11)
    np.random.seed(11)
    torch.manual_seed(11)
    sim = SandKingsSimulation(width=44, height=32, depth=10, num_colonies=4)
    sim.harsh = True
    for c in sim.colonies:
        c.genome.use_neural = True
        c.genome.brain = build_brain(c.genome)
    d = sim._diplomacy()
    d.rel(1, 2).trust = 60
    d.rel(2, 1).trust = 60
    d.update_ally_latch(1, 2)
    parent_houses = {sim._house_name(c) for c in sim.colonies}
    sim.colonies[1].genome.loyalty = 0.1  # a resentful newborn
    sim.colonies[2].genome.loyalty = 0.1
    victim = sim.colonies[0]
    victim.maw.alive = False
    victim.units.clear()
    sim._respawn_colony(victim.colony_id)
    child = sim.colonies[0]
    assert child.generation == 1, "a union founds a new house"
    assert any("born of their union" in m for _, m in sim.events)
    # supersedure: the low-loyalty child holds a grudge against a parent
    assert any("resents its parent" in m for _, m in sim.events)
    grudges = sim._house_grudges()
    assert any(victim_house == sim._house_name(child)
               for (victim_house, _traitor) in grudges), \
        "the newborn's grudge is recorded against a parent house"


def test_evolved_genome_pickles():
    if not HAVE_TORCH:
        return _skip()
    import pickle
    a = ColonyGenome()
    a.use_neural = True
    a.brain_hidden, a.brain_depth = 72, 2
    a.brain = build_brain(a)
    b = ColonyGenome()
    b.use_neural = True
    b.brain_hidden, b.brain_depth = 96, 1
    b.brain = build_brain(b)
    child = crossover_genome(a, b, 0.2)
    revived = pickle.loads(pickle.dumps(child))
    assert revived.brain(torch.zeros(40)).shape == (32,)
    assert revived.brain_hidden == child.brain_hidden


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all evolution tests passed")
