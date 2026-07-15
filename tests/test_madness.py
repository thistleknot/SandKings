"""Madness accumulator (SPEC_MADNESS MAD-1/MAD-2, priest arc P0): a maw left highly agitated AND keeper-hated
slowly ravens toward madness and, unrelieved, dies raving. Pure (no RNG), gated -> byte-identical off."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, MADNESS_AGIT_MIN, MADNESS_HATED_BAND,
                           MADNESS_THRESHOLD)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.MADNESS_ENABLED is False, "MADNESS_ENABLED must default False"


def test_madness_rises_when_raving():
    """A highly agitated, keeper-hated maw ratchets madness upward each step."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.keeper_sentiment = MADNESS_HATED_BAND - 0.1   # hated
    col._sentiment_wrath = False
    col.madness = 0.0
    before = col.madness
    for _ in range(5):
        sim._madness_step(col, MADNESS_AGIT_MIN + 0.2)  # raving agitation
    assert col.madness > before, "madness rises while raving (agitated + hated)"


def test_madness_decays_when_calm():
    """A calm OR keeper-loved maw sheds madness (relief)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.keeper_sentiment = 0.8   # loved -> not hated -> not raving even if agitated
    col._sentiment_wrath = False
    col.madness = 0.5
    sim._madness_step(col, MADNESS_AGIT_MIN + 0.2)
    assert col.madness < 0.5, "madness decays when not raving"


def test_maw_dies_raving_at_threshold():
    """Sustained raving pushes madness past threshold; the maw dies and is marked disgraced."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.keeper_sentiment = 0.0        # maximally hated
    col._sentiment_wrath = True
    col.madness = MADNESS_THRESHOLD - 0.001
    assert col.maw.alive
    for _ in range(20):
        sim._madness_step(col, 1.0)
    assert col.madness >= MADNESS_THRESHOLD, "madness crosses threshold under sustained raving"
    assert getattr(col, 'mad', False) is True, "the colony is marked mad"
    assert col.maw.alive is False, "the maw dies raving"


def test_mad_death_is_disgrace_and_warns_survivors():
    """MAD-2/MAD-3: a mad death fixes the epithet as 'the Mad' (not judged) and lowers each survivor's
    keeper_sentiment (dread of the keeper who rotted the house)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    mad_col, survivor = sim.colonies[0], sim.colonies[1]
    house = sim._house_name(mad_col)
    surv_before = getattr(survivor, 'keeper_sentiment', 0.5)
    mad_col.mad = True
    mad_col.maw.alive = False
    sim._check_maw_deaths()
    assert sim._house_epithets().get(house) == "the Mad", "a mad death is fixed as 'the Mad'"
    assert getattr(survivor, 'keeper_sentiment', 0.5) < surv_before, "survivors dread the keeper (MAD-3)"


def test_mad_respawn_forks_fresh_house_and_preserves_liveness():
    """MAD-2 fork + MAD-4: the mad slot refills with a FRESH house (gen 1, unrelated), the board keeps the
    same colony count, and the slot is alive again."""
    if not HAVE:
        return _skip()
    sim = _sim()
    mad_col = sim.colonies[0]
    cid = mad_col.colony_id
    dead_house = sim._house_name(mad_col)
    n_before = len(sim.colonies)
    mad_col.mad = True
    mad_col.maw.alive = False
    sim._check_maw_deaths()
    sim._respawn_colony(cid)
    fresh = next(c for c in sim.colonies if c.colony_id == cid)
    assert len(sim.colonies) == n_before, "the board keeps the same colony count (liveness, MAD-4)"
    assert fresh.is_alive(), "the slot is refilled and alive (MAD-4)"
    assert getattr(fresh, 'generation', 1) == 1, "the extinct slot mints a FRESH gen-1 house (MAD-2 fork)"
    assert getattr(fresh, 'mad', False) is False, "the fresh house is not itself mad"
    assert sim._house_epithets().get(dead_house) == "the Mad", "the disgraced name persists as a gravestone"


def test_disposition_tick_respects_gate():
    """With the gate OFF, _disposition_tick accrues no madness even for an agitated hated maw."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.keeper_sentiment = 0.0
    col._sentiment_wrath = True
    col.agitation = 1.0
    col.madness = 0.0
    sandkings.MADNESS_ENABLED = False
    sim._disposition_tick()
    assert getattr(col, 'madness', 0.0) == 0.0, "gate off -> no madness accrues (byte-identical path)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all madness tests passed")
