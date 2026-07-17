"""Affordances (SPEC_AFFORDANCES, Evolution Proper Phase 2): a capability's presence is a LIABILITY = a non-additive
product of two existing temperament genes, quantized to an ordinal level and passed through a soft cut (soft_gate).
Gate default off -> no affordance behavior (battery byte-identical). This suite currently covers AF1 (the pure
liability primitive); AF2-AF5 clauses land as those phases are implemented.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import random
    import numpy as np
    import sandkings
    import politics
    from sandkings import (ColonyGenome, SandKingsSimulation, VoxelType, Beast, FAUNA,
                           _affordance_liability, _affordance_level,
                           _affordance_p, AFFORDANCE_MAP, AFF_LEVELS, AFF_CENTER)
    _ORIG_HOSTILE = politics.hostile   # restore after any scorched-earth test so the patch never leaks in-battery
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim(n=2):
    random.seed(0); np.random.seed(0)
    return SandKingsSimulation(width=44, height=28, depth=12, num_colonies=n)


def _scorch_setup():
    """Build a captor soldier adjacent to an enemy-owned field, at war and hostile. Returns (sim, captor, unit, tgt).
    politics.hostile is stubbed True so the test does not depend on relation internals (the helper imports it at call
    time). Caller sets the captor's genome traits and toggles AFFORDANCES_ENABLED."""
    sim = _sim(2)
    captor, victim = sim.colonies[0], sim.colonies[1]
    captor.at_war = True
    unit = captor.units[0]
    unit.position = (10, 10, 6)
    tgt = (11, 10, 6)
    sim.world.voxels[tgt] = VoxelType.CROP.value
    sim.world.ownership[tgt] = victim.colony_id
    politics.hostile = lambda *a, **k: True
    return sim, captor, unit, tgt


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.AFFORDANCES_ENABLED is False, "AFFORDANCES_ENABLED must default False"


def test_liability_products():
    """AF1: liability = the non-additive product of the two mapped genes; ('inv', g) inverts; neutral -> 0.25."""
    if not HAVE:
        return _skip()
    neutral = ColonyGenome()  # all temperament genes 0.5
    for key in AFFORDANCE_MAP:
        assert abs(_affordance_liability(neutral, key) - 0.25) < 1e-9, f"{key} neutral liability is 0.25"
    # scorched_earth = aggression * (1 - loyalty)
    g = ColonyGenome(); g.aggression = 0.8; g.loyalty = 0.2
    assert abs(_affordance_liability(g, 'scorched_earth') - 0.64) < 1e-9, "0.8 * (1-0.2) = 0.64"
    # the inv term drives it to zero when loyalty is total
    g2 = ColonyGenome(); g2.aggression = 1.0; g2.loyalty = 1.0
    assert _affordance_liability(g2, 'scorched_earth') == 0.0, "perfect loyalty -> no scorched earth"
    # builds_granaries = patience * expansion_rate (the real gene name)
    g3 = ColonyGenome(); g3.patience = 0.6; g3.expansion_rate = 0.5
    assert abs(_affordance_liability(g3, 'builds_granaries') - 0.30) < 1e-9, "0.6 * 0.5 = 0.30"
    # keeps_livestock = patience * resilience
    g4 = ColonyGenome(); g4.patience = 0.9; g4.resilience = 0.4
    assert abs(_affordance_liability(g4, 'keeps_livestock') - 0.36) < 1e-9, "0.9 * 0.4 = 0.36"


def test_level_buckets():
    """AF1: _affordance_level buckets a liability into 0..AFF_LEVELS-1, monotone non-decreasing."""
    if not HAVE:
        return _skip()
    prev = -1
    for liab in [0.0, 0.1, 0.24, 0.25, 0.3, 0.5, 0.74, 0.75, 0.9, 1.0]:
        lvl = _affordance_level(liab)
        assert 0 <= lvl < AFF_LEVELS, f"level {lvl} in [0,{AFF_LEVELS})"
        assert lvl >= prev, f"monotone non-decreasing (liab {liab} -> {lvl} < prev {prev})"
        prev = lvl
    assert _affordance_level(1.0) == AFF_LEVELS - 1, "top liability -> top bucket (clipped)"
    assert _affordance_level(0.0) == 0, "zero liability -> bucket 0"


def test_softcut_identity_zero_rng():
    """AF1: with AFF_TEMP==0 (default), _affordance_p is the hard step (1.0 if liability > AFF_CENTER else 0.0) and
    consumes zero RNG draws (soft_gate is pure — the CALLER draws)."""
    if not HAVE:
        return _skip()
    assert sandkings.AFF_TEMP == 0.0, "AFF_TEMP defaults 0.0 (identity)"
    # counting spy on the module RNG the sim's determinism rides
    count = {"n": 0}
    orig = random.random
    def spy():
        count["n"] += 1
        return orig()
    random.random = spy
    try:
        for liab in [0.0, 0.1, AFF_CENTER - 1e-6, AFF_CENTER, AFF_CENTER + 1e-6, 0.5, 1.0]:
            p = _affordance_p(liab)
            assert p == (1.0 if liab > AFF_CENTER else 0.0), f"hard step at AFF_CENTER (liab {liab} -> {p})"
    finally:
        random.random = orig
    assert count["n"] == 0, f"_affordance_p consumes no RNG (got {count['n']})"


def test_scorched_earth_ignites():
    """AF3: a cruel-AND-faithless house at war ignites an adjacent enemy field (reusing _ignite)."""
    if not HAVE:
        return _skip()
    prev = sandkings.AFFORDANCES_ENABLED
    try:
        sandkings.AFFORDANCES_ENABLED = True
        sim, captor, unit, tgt = _scorch_setup()
        captor.genome.aggression = 1.0; captor.genome.loyalty = 0.0   # liability 1.0 -> p 1.0 (AFF_TEMP=0)
        assert sim._scorched_earth_step(unit, captor) is True, "cruel-faithless house torches the field"
        assert tgt in sim._fires(), "the enemy crop is now burning (reused the fire registry)"
    finally:
        sandkings.AFFORDANCES_ENABLED = prev
        politics.hostile = _ORIG_HOSTILE


def test_scorched_earth_gentle_declines():
    """AF3: a loyal, gentle house does not scorch even in the same at-war/adjacency state (trait gate)."""
    if not HAVE:
        return _skip()
    prev = sandkings.AFFORDANCES_ENABLED
    try:
        sandkings.AFFORDANCES_ENABLED = True
        sim, captor, unit, tgt = _scorch_setup()
        captor.genome.aggression = 0.1; captor.genome.loyalty = 1.0   # liability 0.0 -> p 0.0
        assert sim._scorched_earth_step(unit, captor) is False, "the trait soft-cut blocks a gentle house"
        assert tgt not in sim._fires(), "no fire was lit"
    finally:
        sandkings.AFFORDANCES_ENABLED = prev
        politics.hostile = _ORIG_HOSTILE


def test_scorched_earth_needs_war():
    """AF3: the war-footing precondition gates the affordance (no burning in peacetime)."""
    if not HAVE:
        return _skip()
    prev = sandkings.AFFORDANCES_ENABLED
    try:
        sandkings.AFFORDANCES_ENABLED = True
        sim, captor, unit, tgt = _scorch_setup()
        captor.at_war = False
        captor.genome.aggression = 1.0; captor.genome.loyalty = 0.0
        assert sim._scorched_earth_step(unit, captor) is False, "peacetime blocks scorched earth"
    finally:
        sandkings.AFFORDANCES_ENABLED = prev
        politics.hostile = _ORIG_HOSTILE


def test_livestock_trait_gate():
    """AF5: the keeps-livestock decision (patience*resilience) permits a husbandry temperament, blocks a low one.
    Non-neural colonies have no directive -> trait-only (policy term permits)."""
    if not HAVE:
        return _skip()
    sim = _sim(2)
    c = sim.colonies[0]
    c.genome.patience = 1.0; c.genome.resilience = 1.0        # liability 1.0 -> take
    assert sim._affordance_take(c, 'keeps_livestock') is True, "a husbandry temperament keeps livestock"
    c.genome.patience = 0.1; c.genome.resilience = 0.1        # liability 0.01 < AFF_CENTER -> block
    assert sim._affordance_take(c, 'keeps_livestock') is False, "a low-husbandry house does not"


def _sim_with_ant():
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=2)
    for _ in range(8):
        sim.step()
    colony = next((c for c in sim.colonies if c.units), None)
    assert colony is not None
    unit = colony.units[0]
    _, hp, atk, pack, hunt, bounty = FAUNA['ant']                # ant: hunt_range 0 -> tameable
    beast = Beast('ant', unit.position, hp, atk, hunt, bounty, spawned_at=0)
    sim._fauna().append(beast)
    return sim, colony, beast


def test_livestock_gates_taming():
    """AF5: with the affordance gate on, only a husbandry house tames; a low-trait house is skipped (no taming).
    TAME_BASE=1.0 makes the taming roll deterministic once the affordance permits."""
    if not HAVE:
        return _skip()
    prev_dom = sandkings.DOMESTICATION_ENABLED
    prev_aff = sandkings.AFFORDANCES_ENABLED
    prev_tb = sandkings.TAME_BASE
    try:
        sandkings.DOMESTICATION_ENABLED = True
        sandkings.AFFORDANCES_ENABLED = True
        sandkings.TAME_BASE = 1.0
        # low-trait: every colony blocked -> beast stays wild
        sim, colony, beast = _sim_with_ant()
        for c in sim.colonies:
            c.genome.patience = 0.1; c.genome.resilience = 0.1
        sim._taming_tick()
        assert getattr(beast, 'owner', -1) < 0, "a low-husbandry world tames nothing (affordance blocks the draw)"
        # husbandry house tames
        sim2, colony2, beast2 = _sim_with_ant()
        for c in sim2.colonies:
            c.genome.patience = 0.1; c.genome.resilience = 0.1
        colony2.genome.patience = 1.0; colony2.genome.resilience = 1.0
        sim2._taming_tick()
        assert getattr(beast2, 'owner', -1) == colony2.colony_id, "a husbandry house tames the beast"
    finally:
        sandkings.DOMESTICATION_ENABLED = prev_dom
        sandkings.AFFORDANCES_ENABLED = prev_aff
        sandkings.TAME_BASE = prev_tb


def test_granary_trait_gate():
    """AF4: the builds_granaries decision = patience*expansion_rate (+ policy). A patient-expansive house takes it."""
    if not HAVE:
        return _skip()
    sim = _sim(2)
    c = sim.colonies[0]
    c.genome.patience = 1.0; c.genome.expansion_rate = 1.0        # liability 1.0 -> take
    assert sim._affordance_take(c, 'builds_granaries') is True, "a patient-expansive house builds granaries"
    c.genome.patience = 0.2; c.genome.expansion_rate = 0.2        # liability 0.04 < AFF_CENTER -> block
    assert sim._affordance_take(c, 'builds_granaries') is False, "a low house does not"


def test_granary_build_and_shelter():
    """AF4: a granary is raised on the odd maw-ring cells (counts, costs 2 food, never-rot GRANARY voxel) and shelters
    the winter store — a granary house keeps the bootstrap floor when the Chill lifts it; an ungranaried house does not."""
    if not HAVE:
        return _skip()
    prev_aff = sandkings.AFFORDANCES_ENABLED
    prev_win = sandkings.WINTER_BITE_ENABLED
    try:
        sandkings.AFFORDANCES_ENABLED = True
        sim = _sim(2)
        c0, c1 = sim.colonies[0], sim.colonies[1]
        mx, my, mz = c0.maw.position
        sign = 1 if sim.world.in_bounds(mx + 3, my, mz) else -1     # r = PALISADE_RING+1 = 3; (±3+0)%2 == 1 -> odd cell
        tgt = (mx + 3 * sign, my, mz)
        sim.world.voxels[tgt] = VoxelType.AIR.value
        sim.world.ownership[tgt] = -1
        unit = c0.units[0]
        unit.position = (mx + 2 * sign, my, mz)                    # Chebyshev 1 from tgt (unique nearest odd cell)
        food0 = c0.maw.food_stored
        assert sim._granary_step(unit, c0) is True, "granary raised on the ring"
        assert sim.world.voxels[tgt] == VoxelType.GRANARY.value, "a GRANARY voxel now stands"
        assert getattr(c0, 'granaries', 0) == 1, "the granary is counted"
        assert c0.maw.food_stored == food0 - 2, "labor is fed (2 food)"
        # winter shelter: the Chill lifts the floor for all, but the granary house keeps it
        sandkings.WINTER_BITE_ENABLED = True
        sim.step_count = 3 * sandkings.SEASON_LENGTH               # season_index() == 3 (the Chill)
        assert sim.season_index() == 3
        c0.maw.food_stored = 1.0
        c1.maw.food_stored = 1.0                                   # c1 has no granary
        sim._feed_terrarium()
        assert c0.maw.food_stored >= sandkings.BOOTSTRAP_FLOOR, "a granary shelters the winter store"
        assert c1.maw.food_stored < sandkings.BOOTSTRAP_FLOOR, "an ungranaried house starves in the Chill"
    finally:
        sandkings.AFFORDANCES_ENABLED = prev_aff
        sandkings.WINTER_BITE_ENABLED = prev_win


def test_directive_dim_extended():
    """AF2: the maw directive carries 7 channels — d0-3 core + d4-6 affordances."""
    if not HAVE:
        return _skip()
    import maw_brain
    assert maw_brain.MAW_DIRECTIVE_DIM == 7, "directive extended to 7 (4 core + 3 affordance) channels"


def test_apply_directive_ignores_affordance_channels():
    """AF2: apply_directive tilts only on d0-d2; the affordance channels d4-d6 leave move/attack untouched, so a
    neutral core is still identity and the tilt is invariant to the affordance channels (movement/attack regression)."""
    if not HAVE:
        return _skip()
    import torch, maw_brain
    probs = torch.tensor([0.1, 0.1, 0.2, 0.2, 0.15, 0.15, 0.1])       # 7 actions, sums to 1
    neutral = torch.tensor([0.5, 0.5, 0.5, 0.5, 0.9, 0.1, 0.7])       # neutral core, arbitrary affordance channels
    out = maw_brain.apply_directive(probs, neutral)
    assert torch.allclose(out, probs, atol=1e-6), "neutral d0-d2 -> identity; affordance channels ignored"
    d_lo = torch.tensor([0.8, 0.6, 0.5, 0.5, 0.0, 0.0, 0.0])
    d_hi = torch.tensor([0.8, 0.6, 0.5, 0.5, 1.0, 1.0, 1.0])
    assert torch.allclose(maw_brain.apply_directive(probs, d_lo),
                          maw_brain.apply_directive(probs, d_hi), atol=1e-6), "tilt invariant to affordance channels"


def test_warm_start_affordance_channels():
    """AF2: the d4-d6 channels warm-start from the genome affordance levels — a high-level trait initializes its
    channel hot (>0.5), a zero-level trait cold (<0.5). Deterministic act with zero-init readout returns sigmoid(bias)."""
    if not HAVE:
        return _skip()
    import torch, maw_brain
    obs = torch.zeros(42)
    warm = torch.tensor([0.5, 0.5, 0.5, 0.5, 1.0, 0.0, 0.5])          # d4 hot, d5 cold, d6 mid
    pol = maw_brain.MawPolicy(obs_dim=42, directive_dim=7, warm_start=warm)
    d, _lp = pol.act(obs, deterministic=True)
    d = d.reshape(-1)
    assert d.numel() == 7, "directive is 7-d"
    assert float(d[4]) > 0.5, "a maxed affordance level warm-starts its channel hot"
    assert float(d[5]) < 0.5, "a zero affordance level warm-starts its channel cold"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all affordance tests passed")
