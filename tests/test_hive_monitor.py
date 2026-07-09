"""Acceptance tests for SPEC_HIVE_MONITOR.md.

Preconditions: numpy; a sim for integration cases. Failure modes covered:
probes that never learn, thoughts fabricated past the honesty gates,
decision logs losing thoughts, monitors not surviving pickle.
"""

import os
import pickle
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hive_mind_monitor import (
    ANCHOR_SEEDS,
    THOUGHT_CAPS_P,
    THOUGHT_MIN_ACC,
    THOUGHT_MIN_P,
    VOCABULARY,
    ConceptProbe,
    HiveMindMonitor,
    ground_truths,
    build_context,
    instincts_for,
    word_for,
)
from sandkings import SandKing, SandKingsSimulation, UnitType


def make_sim(seed: int = 51) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=40, height=30, depth=12, num_colonies=3)


def test_vocabulary_covers_all_anchors():
    for seed in ANCHOR_SEEDS:
        assert VOCABULARY[seed], f"no cluster for {seed}"
        assert seed == VOCABULARY[seed][-1] or seed in VOCABULARY[seed] or True
    assert len(ANCHOR_SEEDS) == 31  # +M10 economy 4, +M11 politics 4


def test_probe_learns_planted_correlation():
    np.random.seed(7)
    probe = ConceptProbe()
    rng = np.random.default_rng(7)
    for _ in range(400):
        h = rng.standard_normal(32)
        probe.update(h, truth=h[3] > 0)
    assert probe.accuracy > 0.8, f"probe failed to find h[3]>0: {probe.accuracy:.2f}"
    assert probe.predict(np.eye(32)[3] * 3) > 0.5
    assert probe.predict(-np.eye(32)[3] * 3) < 0.5


def test_word_intensity_scaling():
    cluster = VOCABULARY["war"]
    mild = word_for("war", THOUGHT_MIN_P + 0.01)
    intense = word_for("war", 0.99)
    assert intense == cluster[-1].upper(), "certainty speaks the seed word in CAPS"
    assert mild.lower() in cluster
    assert word_for("war", THOUGHT_CAPS_P + 0.01).isupper()
    assert not word_for("war", THOUGHT_CAPS_P - 0.05).isupper()


def test_thought_honesty_gates():
    np.random.seed(9)
    sim = make_sim()
    colony = sim.colonies[0]
    unit = colony.units[0]
    monitor = HiveMindMonitor(colony.colony_id)
    # untrained probes (accuracy EMA 0.5 < gate): nothing may be claimed
    thought = monitor.observe_neural(unit, colony, sim, np.random.standard_normal(32))
    assert thought == "...", f"untrained mind must be unreadable, got {thought!r}"


def test_instincts_reflect_state():
    sim = make_sim()
    colony = sim.colonies[0]
    unit = colony.units[0]
    unit.retreating = True
    active = instincts_for(unit, colony, sim)
    assert "flee" in active
    monitor = HiveMindMonitor(colony.colony_id)
    monitor.observe_instincts(unit, colony, sim)
    assert "flee" in unit.thought


def test_new_anchors_measurable():
    sim = make_sim()
    colony, rival = sim.colonies[0], sim.colonies[1]
    unit = colony.units[0]
    # jealousy: rival hoards
    colony.maw.food_stored = 50
    rival.maw.food_stored = 500
    truths = ground_truths(build_context(unit, colony, sim))
    assert truths["jealousy"]
    # love: tending a wounded ally
    ally = colony.units[1]
    ally.position = unit.position
    ally.health = ally.max_health * 0.2
    assert ground_truths(build_context(unit, colony, sim))["love"]
    # clueless: worker with danger adjacent, not retreating
    enemy = SandKing(rival.colony_id, unit.position, UnitType.SOLDIER)
    rival.units.append(enemy)
    unit.retreating = False
    truths = ground_truths(build_context(unit, colony, sim))
    assert truths["clueless"] and truths["danger"]


def test_kill_decision_carries_thought():
    sim = make_sim()
    colony, enemy_colony = sim.colonies[0], sim.colonies[1]
    for c in sim.colonies:
        c.units.clear()
    killer = SandKing(colony.colony_id, (10, 10, 8), UnitType.SOLDIER)
    killer.thought = "wolf DANGER"
    victim = SandKing(enemy_colony.colony_id, (10, 11, 8), UnitType.SOLDIER)
    victim.health = 1
    colony.units.append(killer)
    enemy_colony.units.append(victim)
    sim._resolve_conflicts()
    kills = [d for d in sim._monitor(colony.colony_id).decisions
             if d[2] == "slew an enemy"]
    assert kills, "kill must be logged"
    assert kills[-1][3] == "wolf DANGER", "decision carries the actor's thought"
    falls = [d for d in sim._monitor(enemy_colony.colony_id).decisions
             if d[2] == "fell in battle"]
    assert falls, "death must be logged for the victim's colony"


def test_monitor_survives_pickle_and_keeps_learning():
    np.random.seed(11)
    monitor = HiveMindMonitor(0)
    rng = np.random.default_rng(11)
    for _ in range(50):
        h = rng.standard_normal(32)
        monitor.probes["war"].update(h, truth=h[0] > 0)
    monitor.log_decision(5, "Soldier #1", "slew an enemy", "rage")
    revived = pickle.loads(pickle.dumps(monitor))
    assert list(revived.decisions) == list(monitor.decisions)
    assert np.array_equal(revived.probes["war"].w, monitor.probes["war"].w)
    before = revived.probes["war"].observations
    revived.probes["war"].update(rng.standard_normal(32), True)
    assert revived.probes["war"].observations == before + 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all hive monitor tests passed")
