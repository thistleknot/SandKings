"""Fauna ecology (SPEC_FAUNA_ECOLOGY, Phase 2): an overgrown guppy shoal turns predatory — big guppies snap
at exposed spawn near the oasis and surface as huntable predator Beasts. Gate default off -> the guppy tick is
byte-identical (no predation, no draws)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    import sandkings
    from sandkings import SandKingsSimulation, GUPPY_CAP, GUPPY_BITE_DAMAGE, FAUNA, OASIS_RADIUS
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim(n=2):
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=n)
    for _ in range(8):          # populate units + the world
        sim.step()
    return sim


def _place_at_oasis(sim, unit):
    cx, cy = sim.world.width // 2, sim.world.height // 2
    z = sim.world.surface_z(cx, cy) + 1
    unit.position = (cx, cy, z)


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.GUPPY_PREDATOR_ENABLED is False, "GUPPY_PREDATOR_ENABLED must default False"
    assert 'guppy' in FAUNA and FAUNA['guppy'][0] == 0.0, "guppy is a keeper-only (weight-0) predator species"


def test_overgrown_shoal_bites_exposed_spawn():
    """An overgrown shoal bites an exposed unit near the water (damage applied)."""
    if not HAVE:
        return _skip()
    pmax, pk = sandkings.GUPPY_BITE_MAX, sandkings.GUPPY_BITE_K
    sandkings.GUPPY_BITE_MAX = 1.0; sandkings.GUPPY_BITE_K = 10.0   # guarantee a bite at max shoal
    try:
        sim = _sim(2)
        colony = next((c for c in sim.colonies if c.units), None)
        assert colony is not None, "need a colony with units"
        colony.genome.resilience = 0.0        # no damage resist, so the full bite lands
        unit = colony.units[0]
        _place_at_oasis(sim, unit)
        unit.health = unit.max_health
        sim.guppy_pop = float(GUPPY_CAP)      # maximally overgrown
        hp0 = unit.health
        sim._guppy_predation()
        assert unit.health < hp0, "the overgrown shoal must bite an exposed unit at the oasis"
    finally:
        sandkings.GUPPY_BITE_MAX = pmax; sandkings.GUPPY_BITE_K = pk


def test_predator_guppies_surface_as_beasts():
    """A big shoal surfaces huntable predator guppy Beasts (visible threat)."""
    if not HAVE:
        return _skip()
    psurf = sandkings.GUPPY_SURFACE_P
    sandkings.GUPPY_SURFACE_P = 1.0           # guarantee a surfacing this call
    try:
        sim = _sim(2)
        sim.guppy_pop = float(GUPPY_CAP)
        before = sum(1 for b in sim._fauna() if b.species == 'guppy')
        sim._guppy_predation()
        after = sum(1 for b in sim._fauna() if b.species == 'guppy')
        assert after > before, "an overgrown shoal must surface predator guppy Beasts"
    finally:
        sandkings.GUPPY_SURFACE_P = psurf


def test_gate_off_tick_never_predates():
    """Gate off: even a maxed shoal never predates (the guppy tick is byte-identical)."""
    if not HAVE:
        return _skip()
    # GUPPY_PREDATOR_ENABLED is the module default (False); guppies on so the tick body runs.
    pg = sandkings.GUPPIES_ENABLED
    sandkings.GUPPIES_ENABLED = True
    try:
        from sandkings import GUPPY_TICK
        sim = _sim(2)
        colony = next((c for c in sim.colonies if c.units), None)
        unit = colony.units[0]
        _place_at_oasis(sim, unit); unit.health = unit.max_health
        sim.guppy_pop = float(GUPPY_CAP)
        sim.step_count = GUPPY_TICK            # tick-aligned so _guppy_tick body executes
        guppies_before = sum(1 for b in sim._fauna() if b.species == 'guppy')
        sim._guppy_tick()
        assert unit.health == unit.max_health, "gate off: no predation bite"
        assert sum(1 for b in sim._fauna() if b.species == 'guppy') == guppies_before, "gate off: no predator guppies"
    finally:
        sandkings.GUPPIES_ENABLED = pg


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all fauna-ecology tests passed")
