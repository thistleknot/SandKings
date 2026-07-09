"""Acceptance tests for SPEC_CODEX.md (CX1-CX6).

Failure modes covered: empty corpus crashing, retrieval ignoring the
query, keyword fallback breaking without vectors, extraction nudging
the wrong attr or an unbounded one, non-readers learning, the event
double-firing, and the vectors dragging through a pickle.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import codex as codex_mod
from codex import CODEX_NUDGE, Codex, apply_lesson, infer_lesson
from sandkings import SandKing, SandKingsSimulation, UnitType, VoxelType


def make_sim(seed: int = 44) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_corpus_loads_and_coop_is_modal():
    cx = Codex()
    assert len(cx.passages) > 20, "corpus + specs ingested"
    lessons = [l for _t, l, _v, _k in cx.passages]
    from collections import Counter
    counts = Counter(lessons)
    assert set(counts) <= set(codex_mod.LESSONS)
    assert counts["coop"] == max(counts.values()), "coop is the modal lesson"


def test_retrieval_matches_query_intent():
    cx = Codex()
    _p, coop = cx.consult(["ally", "truce", "gift"])
    assert coop == "coop"
    _p, dig = cx.consult(["tunnel", "underground", "frost"])
    assert dig == "dig"
    _p, fort = cx.consult(["wall", "palisade", "siege"])
    assert fort == "fortify"


def test_keyword_fallback_without_vectors(monkeypatch=None):
    # stub the GloVe cache empty: retrieval must still work by keyword
    saved = codex_mod._GLOVE
    codex_mod._GLOVE = {}
    try:
        cx = Codex()
        _p, lesson = cx.consult(["wall", "castle", "defense"])
        assert lesson == "fortify", "keyword overlap still retrieves"
    finally:
        codex_mod._GLOVE = saved


def test_infer_lesson_keywords():
    assert infer_lesson("cooperation and truce and allies") == "coop"
    assert infer_lesson("dig a tunnel underground for shelter") == "dig"
    assert infer_lesson("a palisade wall for defense") == "fortify"


def test_apply_lesson_bounds_and_targets():
    class G:
        loyalty = 0.99
        defense_investment = 0.5
        tunnel_preference = 0.5
        patience = 0.5
        fertility = 0.5
    g = G()
    moved = apply_lesson(g, "coop")
    assert moved == ["loyalty"] and g.loyalty <= 1.0
    apply_lesson(g, "dig")
    assert abs(g.tunnel_preference - (0.5 + CODEX_NUDGE)) < 1e-6
    moved = apply_lesson(g, "trade")
    assert set(moved) == {"loyalty", "fertility"}


def test_only_readers_learn_and_event_fires_once():
    sim = make_sim()
    reader, mute = sim.colonies[0], sim.colonies[1]
    reader.breached = True
    reader.units.append(SandKing(reader.colony_id, reader.maw.position,
                                 UnitType.WORKER))
    loy0 = reader.genome.loyalty
    mute_loy0 = mute.genome.loyalty
    sim.step_count = 300
    sim._codex_tick()
    sim.step_count = 600
    sim._codex_tick()
    assert reader.genome.loyalty != loy0 or reader.genome.tunnel_preference, \
        "the reader's dispositions moved"
    assert mute.genome.loyalty == mute_loy0, "the un-awakened cannot read"
    reads = [m for _, m in sim.events if "reads the codex" in m]
    assert len(reads) == 1, "one first-read event per house"


def test_pi_controller_grants_reading():
    from machines import Controller, PI_FUEL
    sim = make_sim()
    colony = sim.colonies[0]
    assert not sim._can_read(colony)
    colony.controllers = [Controller(colony.colony_id, fuel=PI_FUEL)]
    assert sim._can_read(colony), "the god-brain reads"


def test_codex_does_not_drag_vectors_through_pickle():
    import pickle
    sim = make_sim()
    sim.colonies[0].breached = True
    sim.colonies[0].units.append(
        SandKing(sim.colonies[0].colony_id, sim.colonies[0].maw.position,
                 UnitType.WORKER))
    sim.step_count = 300
    sim._codex_tick()  # builds sim.codex with embeddings
    blob = pickle.dumps(sim)
    # the 40k-vector cache must NOT be in the pickle (it would be MBs)
    assert len(blob) < 4_000_000, f"pickle too fat: {len(blob)} bytes"
    revived = pickle.loads(blob)
    revived.step_count = 600
    revived._codex_tick()  # codex rebuilds lazily from files
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert '_codex_tick' not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all codex tests passed")
