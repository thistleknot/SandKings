"""Winter bite (SPEC_WINTER WI1): in Chill the bootstrap floor lifts so an unprepared colony truly
starves, while a stockpiled one rides its non-decaying hoard. Gate default off -> the floor applies
exactly as today (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import (SandKingsSimulation, BOOTSTRAP_FLOOR, WINTER_BITE_ENABLED, SEASON_LENGTH)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=40, height=30, depth=10, num_colonies=2)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert WINTER_BITE_ENABLED is False, "WINTER_BITE_ENABLED must default False (battery byte-identical)"


def test_floor_applies_when_off():
    if not HAVE:
        return _skip()
    sim = _sim()
    sim.step_count = 3 * SEASON_LENGTH               # Chill
    for c in sim.colonies:
        c.maw.food_stored = 2.0                      # below the floor
    sim._feed_terrarium()
    for c in sim.colonies:
        assert c.maw.food_stored >= BOOTSTRAP_FLOOR, "gate off: the Chill floor must still apply"


def test_chill_lifts_the_floor_when_on():
    if not HAVE:
        return _skip()
    prev = sandkings.WINTER_BITE_ENABLED; sandkings.WINTER_BITE_ENABLED = True
    try:
        sim = _sim()
        sim.step_count = 3 * SEASON_LENGTH           # Chill
        unprepared = sim.colonies[0]; prepared = sim.colonies[1]
        unprepared.maw.food_stored = 2.0             # did not stockpile
        prepared.maw.food_stored = 300.0             # rode in with a hoard
        sim._feed_terrarium()
        assert unprepared.maw.food_stored == 2.0, "Chill: an unprepared colony is NOT floored — it starves"
        assert prepared.maw.food_stored >= 300.0, "Chill: a stockpiled colony keeps its reserve"
    finally:
        sandkings.WINTER_BITE_ENABLED = prev


def test_non_chill_still_floors_when_on():
    if not HAVE:
        return _skip()
    prev = sandkings.WINTER_BITE_ENABLED; sandkings.WINTER_BITE_ENABLED = True
    try:
        sim = _sim()
        sim.step_count = 0                           # Flood (season 0) — the bite is Chill-only
        for c in sim.colonies:
            c.maw.food_stored = 2.0
        sim._feed_terrarium()
        for c in sim.colonies:
            assert c.maw.food_stored >= BOOTSTRAP_FLOOR, "the floor lifts only in Chill, not other seasons"
    finally:
        sandkings.WINTER_BITE_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all winter tests passed")
