"""Acceptance tests for SPEC_FACES.md (F1-F5) — the sentiment carvings.

Canon: a colony carves its SENTIMENT toward the keeper (not a literal
face); it sours GRADUALLY, the early warning of rebellion. Failure modes
covered: instant (non-gradual) souring, souring not faster than recovery,
wrong band mapping, the warning double-firing, unbounded sentiment, and
the carving not purging.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (CARVE_SYMBOLS, SENTIMENT_RECOVER, SENTIMENT_SOUR,
                       SandKingsSimulation, VoxelType)


def make_sim(seed: int = 88) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    sim.keeper_auto = False
    return sim


def test_symbol_set_is_sentiment_not_faces():
    assert set(CARVE_SYMBOLS) == {"devout", "wary", "hateful", "machine"}


def test_band_tracks_favor_gradually():
    sim = make_sim()
    c = sim.colonies[0]
    # the band follows the favor scalar (gradual), not the attitude directly
    c.keeper_sentiment = 0.2
    assert sim._update_sentiment(c) == "hateful", "low favor -> hateful"
    c.keeper_sentiment = 0.5
    assert sim._update_sentiment(c) == "wary", "mid favor -> wary"
    c.keeper_fed_step = sim.step_count  # reverent so it doesn't drift down
    c.keeper_sentiment = 0.9
    assert sim._update_sentiment(c) == "devout", "high favor -> devout"
    # a colony under wrath does NOT jump straight to hateful - it passes
    # through wary as favor decays (the visible warning)
    c.worshipped = True
    sim.keeper_drought(True)
    c.keeper_fed_step = -10**9
    c.keeper_sentiment = 0.7
    seen = {sim._update_sentiment(c) for _ in range(8)}
    assert "wary" in seen, "souring passes through wary (look to your faces)"
    assert "hateful" in seen, "and reaches hateful"


def test_souring_is_gradual_and_faster_than_recovery():
    sim = make_sim()
    c = sim.colonies[0]
    c.worshipped = True
    c.keeper_sentiment = 1.0
    sim.keeper_drought(True)
    # one tick must not slam it to zero - it drifts
    before = c.keeper_sentiment
    sim._update_sentiment(c)
    assert c.keeper_sentiment == round(before - SENTIMENT_SOUR, 10) or \
        abs(c.keeper_sentiment - (before - SENTIMENT_SOUR)) < 1e-9
    assert c.keeper_sentiment > 0.0, "gradual, not instant"
    # souring step must exceed the recovery step (cruelty remembered)
    assert SENTIMENT_SOUR > SENTIMENT_RECOVER


def test_sentiment_recovers_under_manna_and_stays_bounded():
    sim = make_sim()
    c = sim.colonies[0]
    c.keeper_sentiment = 0.1
    c.keeper_fed_step = sim.step_count  # reverent
    for _ in range(50):
        sim._update_sentiment(c)
    assert c.keeper_sentiment == 1.0 or c.keeper_sentiment <= 1.0
    assert 0.0 <= c.keeper_sentiment <= 1.0
    # and it climbed
    assert c.keeper_sentiment > 0.1


def test_warning_fires_once_and_rearms():
    sim = make_sim()
    c = sim.colonies[0]
    c.worshipped = True
    sim.keeper_drought(True)
    c.keeper_sentiment = 0.4
    for _ in range(6):  # drive it into hateful
        sim._update_sentiment(c)
    warns = [m for _, m in sim.events if "hateful mask" in m]
    assert len(warns) == 1, "the warning fires once on the first turn"
    # recover to devout, then fall again -> re-warns
    sim.keeper_drought(False)
    c.keeper_fed_step = sim.step_count
    c.keeper_sentiment = 0.9
    assert sim._update_sentiment(c) == "devout"  # re-arms
    c.keeper_fed_step = -10**9
    sim.drought = True
    c.worshipped = True
    c.keeper_sentiment = 0.2
    for _ in range(4):
        sim._update_sentiment(c)
    assert len([m for _, m in sim.events if "hateful mask" in m]) == 2


def test_carving_is_sentiment_glyph_and_purges():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.breached = True  # AW1: keeper-face carvings need awareness
    sim.step_count = 200
    sim._keeper_tick()
    carv = sim._carvings()
    faces = {CARVE_SYMBOLS[b] for b in ("devout", "wary", "hateful")}
    assert any(v in faces for v in carv.values()), "a sentiment glyph carved"
    pos = next(p for p, v in carv.items() if v in faces)
    sim.world.voxels[pos] = VoxelType.AIR.value
    sim.step_count = 400
    sim._keeper_tick()
    assert pos not in sim.carvings, "disturbed sand forgets"


def test_state_pickles_and_evolution_inert():
    import pickle
    sim = make_sim()
    sim.colonies[0].keeper_sentiment = 0.2
    for _ in range(20):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert hasattr(revived.colonies[0], "keeper_sentiment")
    revived.step()
    from sandkings_evolution import EnhancedSandKingsSimulation
    assert "_update_sentiment" not in \
        EnhancedSandKingsSimulation.step.__code__.co_names


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all faces tests passed")
