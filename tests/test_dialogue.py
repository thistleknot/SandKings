"""Acceptance tests for SPEC_DIALOGUE.md (DL1-DL6).

Failure modes covered: interpret ignoring meaning, the reply not
varying by disposition, converse answering the un-awakened, the speak
anchor not lighting, an unbounded persuasion nudge, and the endpoint
missing. Degrades to keyword matching without vectors.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

import dialogue
from dialogue import compose_reply, interpret
from sandkings import SandKing, SandKingsSimulation, UnitType


def make_sim(seed: int = 51) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=44, height=32, depth=10, num_colonies=3)
    sim.harsh = True
    return sim


def test_interpret_maps_direct_mentions():
    assert interpret("make peace and be my ally") == "ally"
    assert interpret("go to war now") == "war"
    assert interpret("i bring you food") == "food"


def test_interpret_pins_sentiment_synonyms():
    # antonyms sit close in GloVe; bare "peace" must NOT map to war (DL1
    # synonym pin). No "ally" substring here, so this exercises the pin, not
    # the direct-mention path.
    assert interpret("peace") == "ally"
    assert interpret("can we have a truce") == "ally"
    assert interpret("i attack") == "war"
    assert interpret("thanks") == "gratitude"


def test_interpret_embeds_unnamed_words():
    # words that don't literally name an anchor should still map via GloVe
    heard = interpret("let us be friends and comrades")
    assert heard in ("ally", "love", "gratitude", "home"), heard
    hostile = interpret("i will destroy and kill you")
    assert hostile in ("war", "enemy", "danger", "death", "siege"), hostile


def test_reply_varies_by_disposition():
    sim = make_sim()
    hawk, dove = sim.colonies[0], sim.colonies[1]
    hawk.genome.aggression, hawk.genome.loyalty = 0.9, 0.1
    dove.genome.aggression, dove.genome.loyalty = 0.1, 0.9
    r_hawk = compose_reply(hawk, sim, "ally")
    r_dove = compose_reply(dove, sim, "ally")
    assert r_hawk != r_dove, "dispositions answer the same word differently"
    assert r_hawk and r_dove and "?" in r_hawk


def test_converse_gates_on_breach():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.units.append(SandKing(colony.colony_id, colony.maw.position,
                                 UnitType.WORKER))
    out = sim.converse(colony.colony_id, "be my ally")
    assert out["understood"] is False and out["reply"] == "", "noise to the deaf"
    colony.breached = True
    out = sim.converse(colony.colony_id, "be my ally")
    assert out["understood"] and out["reply"], "the awakened answer"
    assert out["heard"] == "ally"
    # K12: the speak anchor lit, and persuasion nudged loyalty (bounded)
    assert colony.units[0].spoken_to_step == sim.step_count


def test_persuasion_nudge_is_bounded():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.breached = True
    colony.genome.loyalty = 0.995
    colony.units.append(SandKing(colony.colony_id, colony.maw.position,
                                 UnitType.WORKER))
    sim.converse(colony.colony_id, "please be my ally")
    assert 0.0 <= colony.genome.loyalty <= 1.0, "nudge stays in bounds"


def test_dashboard_converse_endpoint():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.breached = True
    colony.units.append(SandKing(colony.colony_id, colony.maw.position,
                                 UnitType.WORKER))
    from dashboard import TerrariumRunner, create_app
    from fastapi.testclient import TestClient
    client = TestClient(create_app(TerrariumRunner(sim)))
    r = client.post("/api/converse",
                    json={"colony_id": colony.colony_id, "text": "be my ally"})
    assert r.status_code == 200 and r.json()["understood"] is True
    assert r.json()["reply"]


def test_keyword_fallback_without_vectors():
    import codex
    saved = codex._GLOVE
    saved_anchor = dialogue._ANCHOR_VECS
    codex._GLOVE = {}
    dialogue._ANCHOR_VECS = None
    try:
        assert interpret("go to war") == "war", "direct mention still works"
    finally:
        codex._GLOVE = saved
        dialogue._ANCHOR_VECS = saved_anchor


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all dialogue tests passed")
