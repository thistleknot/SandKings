"""Acceptance tests for SPEC_SENTIENCE.md (S1-S6).

Failure modes covered: resonance leaking across hostile lines, order
bias in the blend, speciation gate misfiring on kin, plasticity
escaping [0,1], dreams learning from an empty memory, old-checkpoint
learners lacking replay memories.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from colony_learner import ColonyLearner, POSTURES
from sandkings import (
    NEURAL_AVAILABLE, RESONANCE_ALPHA, SPECIATION_DIST, SandKing,
    SandKingsSimulation, UnitType, VoxelType,
)


def make_sim(seed: int = 21, neural: bool = False) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    if neural and NEURAL_AVAILABLE:
        from sandkings import HiveMindBrain, SoldierLayer
        for colony in sim.colonies:
            colony.genome.use_neural = True
            colony.genome.brain = HiveMindBrain()
    return sim


def plant_soldier(sim, colony, pos, hidden_scale=0.0):
    """A neural soldier with a controlled hidden state."""
    import torch
    from sandkings import SoldierLayer
    unit = SandKing(colony.colony_id, pos, UnitType.SOLDIER)
    unit.brain_layer = SoldierLayer()
    unit.brain_layer.hidden = torch.full((1, 32), float(hidden_scale))
    colony.units.append(unit)
    return unit


def test_resonance_spreads_within_colony_not_across_hostiles():
    if not NEURAL_AVAILABLE:
        return
    sim = make_sim(neural=True)
    a, b = sim.colonies[0], sim.colonies[1]
    z = sim.world.surface_z(24, 18) + 1
    alarmed = plant_soldier(sim, a, (24, 18, z), hidden_scale=1.0)
    calm = plant_soldier(sim, a, (25, 18, z), hidden_scale=0.0)
    stranger = plant_soldier(sim, b, (26, 18, z), hidden_scale=0.0)
    sim._resonance_tick()
    assert float(calm.brain_layer.hidden.mean()) > 0.05, \
        "the alarm spread to the squadmate"
    assert float(stranger.brain_layer.hidden.mean()) == 0.0, \
        "hostile minds do not mingle"
    # symmetric: the alarmed soldier is calmed toward the squad mean
    assert float(alarmed.brain_layer.hidden.mean()) < 1.0


def test_resonance_range_limit():
    if not NEURAL_AVAILABLE:
        return
    sim = make_sim(neural=True)
    a = sim.colonies[0]
    z = sim.world.surface_z(10, 10) + 1
    plant_soldier(sim, a, (10, 10, z), hidden_scale=1.0)
    far = plant_soldier(sim, a, (30, 30, z), hidden_scale=0.0)
    sim._resonance_tick()
    assert float(far.brain_layer.hidden.mean()) == 0.0, "out of earshot"


def test_resonance_of_reports_unity():
    if not NEURAL_AVAILABLE:
        return
    sim = make_sim(neural=True)
    a = sim.colonies[0]
    z = sim.world.surface_z(20, 20) + 1
    plant_soldier(sim, a, (20, 20, z), hidden_scale=0.5)
    plant_soldier(sim, a, (21, 20, z), hidden_scale=0.5)
    res, k = sim.resonance_of(a)
    assert k == 2 and res > 0.99, "identical minds read as unity"


def test_speciation_gates_conspecificity_but_never_kin():
    sim = make_sim()
    a, b = sim.colonies[0], sim.colonies[1]
    for t in ('aggression', 'tunnel_preference', 'expansion_rate',
              'defense_investment', 'fertility', 'resilience',
              'patience', 'loyalty'):
        setattr(a.genome, t, 0.05)
        setattr(b.genome, t, 0.95)
    assert sim._genome_distance(a.genome, b.genome) > SPECIATION_DIST
    assert not sim._conspecific(a, b)
    b.house, b.generation = sim._house_name(a), 2  # kin overrides distance
    assert sim._conspecific(a, b)
    b.house = "Other-House"
    sim._log_speciation(a, b)
    sim._log_speciation(a, b)  # throttled: one historical fact
    strange = [m for _, m in sim.events if "too strange" in m]
    assert len(strange) == 1
    from chronicle import salience_of
    assert salience_of(strange[0]) == 8, "speciation is history"


def test_plasticity_mutates_in_bounds_and_scales_learning():
    sim = make_sim()
    g = sim.colonies[0].genome
    g.plasticity = 0.9
    child = g.mutate(0.3)
    assert 0.0 <= child.plasticity <= 1.0
    # high plasticity learns faster than low on the same transition
    fast, slow = ColonyLearner(), ColonyLearner()
    for learner, plas in ((fast, 1.0), (slow, 0.0)):
        learner._last_state = ("s",)
        learner._last_action = 0
        learner._last_value = 0.0
        random.seed(2)
        colony = sim.colonies[0]
        colony.maw.food_stored = 500
        learner.decide(sim, colony, gamma=0.5, plasticity=plas)
    assert fast.q[("s",)][0] > slow.q[("s",)][0] > 0, \
        "plasticity scales the TD step"


def test_dreams_replay_only_with_memory():
    learner = ColonyLearner()
    learner.dream(gamma=0.5)  # empty memory: no crash, no learning
    assert not learner.q
    learner._replay().append((("s",), 1, 10.0, ("s2",)))
    random.seed(1)
    learner.dream(gamma=0.5, plasticity=1.0)
    assert learner.q[("s",)][1] > 0, "the dream consolidated the memory"


def test_old_checkpoint_learner_grows_replay_lazily():
    import pickle
    learner = ColonyLearner()
    if hasattr(learner, 'replay'):
        del learner.replay  # simulate a pre-S4 pickle
    revived = pickle.loads(pickle.dumps(learner))
    assert len(revived._replay()) == 0


def test_sentience_state_pickles_through_full_steps():
    import pickle
    sim = make_sim(neural=True)
    for _ in range(30):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_resonance_tick' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names, "evolution inert"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all sentience tests passed")
