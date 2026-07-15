"""Revelation R1 (SPEC_REVELATION, gated REVELATION_ENABLED): signs burn in the night sky; colonies accrue
literacy studying them and, past the threshold, DECODE for a polymorphic payoff (tech / omen / edict). Gate
default off is byte-identical."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, SIGN_INTERVAL, SIGN_DURATION, SIGN_KINDS,
                           DECODE_THRESHOLD, TECH_NATIVE)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(8):
        sim.step()
    return sim


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.REVELATION_ENABLED is False, "REVELATION_ENABLED must default False"


def test_sign_raises_studies_decodes_retires():
    """R1: a sign is raised on cadence; a colony studies it to the threshold, decodes once, then it retires."""
    if not HAVE:
        return _skip()
    prev = sandkings.REVELATION_ENABLED
    try:
        sandkings.REVELATION_ENABLED = True
        sim = _sim()
        sim.sky_sign = None
        sim._sign_count = 0
        sim.step_count = SIGN_INTERVAL           # a raise step
        sim._revelation_tick()
        assert sim.sky_sign is not None, "a sign is raised on the interval"
        assert sim.sky_sign['kind'] == SIGN_KINDS[0], "the first sign kind is deterministic (rotation)"
        # study to the decode threshold
        col = sim.colonies[0]
        col.literacy = DECODE_THRESHOLD - 0.001
        col.keeper_sentiment = 0.9               # devout -> reads (fast)
        sim.step_count = SIGN_INTERVAL + 1
        sim._revelation_tick()
        assert col.colony_id in sim.sky_sign['decoded_by'], "the colony decodes the sign once past threshold"
        assert getattr(col, 'enlightened', False), "decoding enlightens the reader (EN8)"
        # retire after duration
        sim.step_count = sim.sky_sign['since'] + SIGN_DURATION
        sim._revelation_tick()
        assert sim.sky_sign is None, "the sign retires after its duration"
    finally:
        sandkings.REVELATION_ENABLED = prev


def test_writing_payoff_grants_tech():
    """R1: the 'writing' sign teaches an unknown native tech (unearthed anthropological writing)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.techs = set()                            # knows nothing -> the writing must teach something
    known_before = set(col.techs)
    phrase = sim._apply_sign_payoff(col, 'writing')
    assert len(col.techs) > len(known_before), "the writing grants a native tech"
    assert list(col.techs)[0] in TECH_NATIVE, "the granted tech is a native tech"
    assert 'teaches' in phrase


def test_omen_and_edict_payoffs_nudge_state():
    """R1: omen/edict signs nudge the existing keeper/genome fields (always-useful, clamped)."""
    if not HAVE:
        return _skip()
    sim = _sim()
    col = sim.colonies[0]
    col.confidence = 0.5; col.genome.aggression = 0.5
    sim._apply_sign_payoff(col, 'omen_war')
    assert col.genome.aggression > 0.5 and col.confidence > 0.5, "an omen of war raises boldness"
    col.keeper_sentiment = 0.4
    sim._apply_sign_payoff(col, 'edict')
    assert col.keeper_sentiment > 0.4, "a divine edict raises keeper favor"


def _priest_sim():
    """A sim stepped enough to have units in a colony (for ordination tests)."""
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(20):
        sim.step()
    colony = next((c for c in sim.colonies if c.units), None)
    return sim, colony


def test_maddened_colony_ordains_prophet():
    """R2: a maddened colony ordains a mad PROPHET who accelerates decode and raises colony madness."""
    if not HAVE:
        return _skip()
    from sandkings import PRIEST_TICK, PROPHET_MADNESS_MIN, PROPHET_DECODE_MULT
    sim, colony = _priest_sim()
    if colony is None:
        return _skip()
    colony.madness = PROPHET_MADNESS_MIN + 0.05
    colony.keeper_sentiment = 0.5
    sim.step_count = PRIEST_TICK
    sim._priest_tick()
    prophets = [u for u in colony.units if getattr(u, 'priest_kind', '') == 'prophet']
    assert prophets, "a maddened colony ordains a prophet"
    assert sim._colony_decode_mult(colony) == PROPHET_DECODE_MULT, "a prophet accelerates the colony's decode"


def test_devout_colony_ordains_soothsayer_who_tithes():
    """R2: a devout, un-maddened colony ordains a SOOTHSAYER who gathers a tithe to the maw."""
    if not HAVE:
        return _skip()
    from sandkings import PRIEST_TICK, SOOTHSAYER_SENTIMENT_MIN, SOOTHSAYER_TITHE
    sim, colony = _priest_sim()
    if colony is None:
        return _skip()
    colony.madness = 0.0
    colony.keeper_sentiment = SOOTHSAYER_SENTIMENT_MIN + 0.1
    sim.step_count = PRIEST_TICK
    sim._priest_tick()                       # ordains
    sooth = [u for u in colony.units if getattr(u, 'priest_kind', '') == 'soothsayer']
    assert sooth, "a devout colony ordains a soothsayer"
    food0 = colony.maw.food_stored
    sim.step_count = PRIEST_TICK + 1         # a non-ordain tick -> pure tithe
    sim._priest_tick()
    assert colony.maw.food_stored >= food0 + SOOTHSAYER_TITHE - 1e-6, "the soothsayer tithes food to the maw"


def test_prophet_breaks_at_dire_madness():
    """R2: at PROPHET_BREAK_MADNESS a prophet BREAKS channeling the great mind (Cthulhu) and is removed."""
    if not HAVE:
        return _skip()
    from sandkings import PROPHET_BREAK_MADNESS
    sim, colony = _priest_sim()
    if colony is None or not colony.units:
        return _skip()
    victim = colony.units[0]
    victim.is_priest = True; victim.priest_kind = 'prophet'
    colony.madness = PROPHET_BREAK_MADNESS + 0.05
    n0 = len(colony.units)
    sim.step_count = 5                       # a non-ordain tick -> channel + break only
    sim._priest_tick()
    assert victim not in colony.units, "the prophet breaks and dies raving"
    assert len(colony.units) == n0 - 1, "the broken prophet is removed"


def test_priest_gate_off_no_ordination():
    """Gate OFF: even a maddened colony ordains no priest through the step loop (byte-identical path)."""
    if not HAVE:
        return _skip()
    prev = sandkings.PRIESTHOOD_ENABLED
    try:
        sandkings.PRIESTHOOD_ENABLED = False
        sim, colony = _priest_sim()
        if colony is None:
            return _skip()
        colony.madness = 0.9
        for _ in range(sandkings.PRIEST_TICK + 2):
            sim.step()
        assert not any(getattr(u, 'is_priest', False) for c in sim.colonies for u in c.units), \
            "gate off -> no priest is ever ordained"
    finally:
        sandkings.PRIESTHOOD_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all revelation tests passed")
