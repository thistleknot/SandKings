"""Acceptance tests for SPEC_TIMBER_AND_FLAME.md T48b (hornets - the venom scourge).

Hornets are a fragile, fast-flying swarm with venom breadth: they spread
stings to fresh (un-envenomed) targets rather than focus-firing one victim.
They are relentless (never flee) and spawn in large packs (6-10).

Tests verify: swarm spawn, venom sting, breadth (multiple poisoned units),
relentlessness (no fleeing), fragility (hp=8), roster integration, and glyph.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    Beast, FAUNA, FAUNA_EVENTS, HORNET_SPEED, HORNET_STING_DURATION, KEEPER_FAUNA,
    KEEPER_WRATH, SandKing, SandKingsSimulation, UnitType, VoxelType,
)
from live_view import BEAST_GLYPHS


def make_sim(seed: int = 77) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_hornet_1_swarm_spawn():
    """HORNET-1: keeper_release('hornets') spawns 6-10 hornets."""
    sim = make_sim()
    # Verify pack range is (6, 10) in FAUNA
    assert FAUNA['hornets'][3] == (6, 10), "pack range is (6, 10)"
    # Construct one hornet to verify species
    beast = Beast('hornets', (10, 10, 5), 8, 4, 30, 1, spawned_at=0)
    assert beast.species == 'hornets'
    # Use keeper_release to spawn a deterministic pack
    sim.keeper_release('hornets')
    hornets = [b for b in sim._fauna() if b.species == 'hornets']
    assert 6 <= len(hornets) <= 10, f"spawned {len(hornets)} hornets in range [6,10]"
    assert all(b.species == 'hornets' for b in hornets), "all fauna are hornets"


def test_hornet_2_venom_sting():
    """HORNET-2: a hornet sting sets poisoned_until and deals damage."""
    sim = make_sim()
    colony = sim.colonies[0]
    # Place a hornet
    hornet = Beast('hornets', (10, 10, 5), 8, 4, 30, 1, spawned_at=0)
    sim._fauna().append(hornet)
    # Place a worker adjacent (Chebyshev 1)
    worker = SandKing(colony.colony_id, (11, 10, 5), UnitType.WORKER)
    colony.units.append(worker)
    pre_health = worker.health
    # Combat: hornet strikes
    sim._beast_combat(hornet)
    # Verify venom: poisoned_until is set
    assert worker.poisoned_until == sim.step_count + HORNET_STING_DURATION, \
        f"worker.poisoned_until={worker.poisoned_until}, expected {sim.step_count + HORNET_STING_DURATION}"
    # Verify damage: health decreased
    assert worker.health < pre_health, f"health {worker.health} < pre {pre_health}"


def test_hornet_3_breadth():
    """HORNET-3: 3 hornets adjacent to 3 units envenoms multiple targets."""
    sim = make_sim()
    colony = sim.colonies[0]
    # Place 3 hornets in a cluster
    for i in range(3):
        hornet = Beast('hornets', (10 + i, 10, 5), 8, 4, 30, 1, spawned_at=0)
        sim._fauna().append(hornet)
    # Place 3 workers each adjacent to at least one hornet
    units = []
    for i in range(3):
        worker = SandKing(colony.colony_id, (10 + i, 11, 5), UnitType.WORKER)
        colony.units.append(worker)
        units.append(worker)
    # Run one combat round for each hornet
    for b in list(sim._fauna()):
        if b.species == 'hornets':
            sim._beast_combat(b)
    # Verify breadth: more than one unit is poisoned
    poisoned_count = sum(1 for u in units
                        if getattr(u, 'poisoned_until', 0) > sim.step_count)
    assert poisoned_count > 1, f"only {poisoned_count} unit poisoned; expected > 1 (breadth)"


def test_hornet_4_relentless():
    """HORNET-4: hornets do not flee (fleeing stays False)."""
    sim = make_sim()
    colony = sim.colonies[0]
    hornet = Beast('hornets', (10, 10, 5), 8, 4, 30, 1, spawned_at=0)
    sim._fauna().append(hornet)
    worker = SandKing(colony.colony_id, (11, 10, 5), UnitType.WORKER)
    colony.units.append(worker)
    # Combat
    sim._beast_combat(hornet)
    # Verify: fleeing is False (unlike bird which sets it to True)
    assert hornet.fleeing is False, "hornet.fleeing is False (relentless)"


def test_hornet_5_fragile():
    """HORNET-5: hornets with hp=8 die quickly via fight-back."""
    sim = make_sim()
    colony = sim.colonies[0]
    hornet = Beast('hornets', (10, 10, 5), 8, 4, 30, 1, spawned_at=0)
    sim._fauna().append(hornet)
    # Place a soldier (high attack) adjacent; provoke or hunt so fight-back triggers
    soldier = SandKing(colony.colony_id, (11, 10, 5), UnitType.SOLDIER)
    colony.units.append(soldier)
    pre_fauna_count = len(sim._fauna())
    # Combat multiple times to ensure the hornet dies
    for _ in range(2):
        if hornet in sim._fauna():
            sim._beast_combat(hornet)
    # Verify: hornet is removed
    assert hornet not in sim._fauna(), "hornet removed from fauna"
    assert len(sim._fauna()) < pre_fauna_count, "fauna count decreased"
    # Verify: CORPSE voxel placed (bounty dropped)
    assert any("slain" in m for _, m in sim.events), "'slain' logged in events"


def test_hornet_6_roster():
    """HORNET-6: hornets in FAUNA, FAUNA_EVENTS, KEEPER_WRATH, KEEPER_FAUNA."""
    # Verify constants
    assert 'hornets' in FAUNA, "'hornets' in FAUNA"
    assert 'hornets' in FAUNA_EVENTS, "'hornets' in FAUNA_EVENTS"  # KeyError on missing
    assert 'hornets' in KEEPER_WRATH, "'hornets' in KEEPER_WRATH"
    assert 'hornets' in KEEPER_FAUNA, "'hornets' in KEEPER_FAUNA"
    # Verify keeper_release accepts hornets (doesn't refuse)
    sim = make_sim()
    sim.keeper_release('hornets')
    assert len(sim._fauna()) > 0, "keeper_release('hornets') spawned fauna"
    assert any(b.species == 'hornets' for b in sim._fauna()), \
        "spawned fauna includes hornets"


def test_hornet_7_glyph():
    """HORNET-7: hornets have a unique swarm glyph (∴ after the graphics legibility redesign)."""
    assert 'hornets' in BEAST_GLYPHS, "'hornets' in BEAST_GLYPHS"
    g = BEAST_GLYPHS['hornets']
    assert g == '∴', f"BEAST_GLYPHS['hornets'] == '∴' (got {g!r})"
    # Verify uniqueness: no other beast shares the glyph
    glyphs = list(BEAST_GLYPHS.values())
    assert glyphs.count(g) == 1, "the hornets glyph appears exactly once in BEAST_GLYPHS"
