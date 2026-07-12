"""Acceptance tests for SPEC_POPULATION.md (POP-1..POP-4) - Phase 0 scaffolding.

Phase 0 is inert: with dynamic_population=False (the default), the sim must be
byte-identical to pre-Phase-0. The new fields and method are defined but unwired.

Test clauses:
- POP-1 (GATING): identity; legacy respawn contract holds; no RNG draws; 45-suite stays green
- POP-2: pop_state defaults POP_ACTIVE, getattr-guarded, pickles
- POP-3: scrub choke point (_deactivate_slot); ≥3 varied pre-states; clears all stale state except house_grudges
- POP-4: MAX_COLONIES constant exists; construction with num_colonies ∈ {2,4,8}
"""

import os
import pickle
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    RESPAWN_DELAY,
    RESPAWN_FOOD,
    MAX_COLONIES,
    DYNAMIC_POPULATION,
    POP_ACTIVE,
    POP_DORMANT,
    Colony,
    ColonyGenome,
    SandKing,
    SandKingsSimulation,
    UnitType,
    VoxelType,
)


def make_sim(seed: int = 11, **kwargs) -> SandKingsSimulation:
    """Make a fresh sim with optional seed override (mirroring test_terrarium.py)."""
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=40, height=30, depth=12, num_colonies=3, **kwargs)


# ============================================================================
# POP-1: IDENTITY (§4). Load-bearing.
# ============================================================================

def test_pop1_identity_flag_default_off():
    """dynamic_population flag defaults to False."""
    sim = make_sim()
    assert getattr(sim, 'dynamic_population', None) is False
    assert sim.dynamic_population == DYNAMIC_POPULATION
    assert DYNAMIC_POPULATION is False


def test_pop1_identity_legacy_respawn_contract():
    """Legacy respawn contract still holds: death→pending→respawn.

    Mirrors test_terrarium.py::test_maw_death_cascade_and_respawn.
    This is the load-bearing identity test: the full chain must work
    exactly as before Phase 0.
    """
    sim = make_sim()
    victim = sim.colonies[2]
    victim_id = victim.colony_id

    # Kill the maw
    victim.maw.take_damage(500 + 1)
    assert not victim.maw.alive

    # Check death cascade
    sim._check_maw_deaths()
    assert victim_id in sim.pending_respawns
    assert sim.pending_respawns[victim_id] == sim.step_count + RESPAWN_DELAY
    assert not victim.units, "fallen colony's units become corpses"
    assert not (sim.world.ownership == victim_id).any(), "ownership cleared"
    assert not sim.pheromones.trails[:, :, :, victim_id, :].any(), "pheromones zeroed"

    # Not due yet
    sim._process_respawns()
    assert not sim.colonies[2].is_alive()

    # Fast-forward and respawn
    sim.step_count += RESPAWN_DELAY
    sim._process_respawns()
    arrival = sim.colonies[2]
    assert arrival.is_alive()
    assert arrival.colony_id == victim_id, "slot keeps its id (color + pheromone channel)"
    assert arrival.maw.food_stored <= RESPAWN_FOOD
    assert len(arrival.units) == 3
    assert victim_id not in sim.pending_respawns


# ============================================================================
# POP-2: pop_state field (§2.3, §3.3).
# ============================================================================

def test_pop2_pop_state_defaults_active():
    """Fresh colony: pop_state == POP_ACTIVE."""
    sim = make_sim()
    for colony in sim.colonies:
        assert colony.pop_state == POP_ACTIVE


def test_pop2_pop_state_getattr_guarded_on_bare_instance():
    """Getattr guard: old/bare objects safely default to POP_ACTIVE."""
    # Create a bare instance without pop_state
    colony = object.__new__(Colony)
    colony.colony_id = 0

    # Guard on read
    assert getattr(colony, 'pop_state', POP_ACTIVE) == POP_ACTIVE

    # After normalization in a sim context (one step() call), it's there
    sim = make_sim()
    # Manually strip pop_state to simulate an old save
    for c in sim.colonies:
        if hasattr(c, 'pop_state'):
            del c.pop_state

    # One step normalizes it
    sim.step_count = 0  # reset to avoid skip logic
    old_count = sim.step_count
    sim.step()

    # Normalized
    for c in sim.colonies:
        assert hasattr(c, 'pop_state')
        assert c.pop_state == POP_ACTIVE


def test_pop2_pop_state_pickle_roundtrip():
    """Pickle round-trip preserves pop_state."""
    sim = make_sim()
    colony = sim.colonies[0]
    pickled = pickle.dumps(colony)
    restored = pickle.loads(pickled)
    assert restored.pop_state == POP_ACTIVE


# ============================================================================
# POP-3: Scrub choke point (§2.4, §3.1, §3.2). Permutation battery.
# ============================================================================

def test_pop3_scrub_p1_politics_and_ownership():
    """P1: politics + ownership scrub clean.

    Set inbound & outbound relations, a truce, an ally latch, a war target
    both directions, and paint ownership voxels. After scrub: all gone.
    """
    sim = make_sim()
    target_cid = 1
    other_cid = 0
    target_colony = sim.colonies[target_cid]

    # Paint ownership
    sim.world.ownership[5:10, 5:10, 5:8] = target_cid
    assert (sim.world.ownership == target_cid).any()

    # Set up politics: both directions. Real API (politics.Diplomacy):
    # relations keyed by (a,b) tuple -> Relation object; truce_until/allied
    # keyed by frozenset; war_target/last_betrayal keyed by int.
    d = sim._diplomacy()
    d.rel(other_cid, target_cid).adjust(50)   # outbound
    d.rel(target_cid, other_cid).adjust(30)   # inbound
    d.truce_until[frozenset((other_cid, target_cid))] = 1000
    d.allied[frozenset((other_cid, target_cid))] = True
    d.war_target[target_cid] = other_cid
    d.war_target[other_cid] = target_cid
    d.last_betrayal[target_cid] = 500

    # Verify setup
    assert (target_cid, other_cid) in d.relations or (other_cid, target_cid) in d.relations
    assert frozenset((other_cid, target_cid)) in d.truce_until
    assert frozenset((other_cid, target_cid)) in d.allied
    assert d.war_target.get(target_cid) == other_cid or d.war_target.get(other_cid) == target_cid
    assert d.last_betrayal.get(target_cid) == 500

    # Scrub
    sim._deactivate_slot(target_cid)

    # Assert clean
    assert target_colony.pop_state == POP_DORMANT
    assert not (sim.world.ownership == target_cid).any()
    for (a, b) in d.relations.keys():
        assert a != target_cid and b != target_cid
    for key in d.truce_until.keys():
        assert target_cid not in key
    for key in d.allied.keys():
        assert target_cid not in key
    assert d.war_target.get(target_cid) is None
    assert d.last_betrayal.get(target_cid) is None


def test_pop3_scrub_p2_thralls_gifts_pheromones():
    """P2: thralls + gifts + pheromones scrub clean.

    Make units in another colony laboring_for or gift_to the target.
    Deposit pheromones. After scrub: all gone.
    """
    sim = make_sim()
    target_cid = 1
    captor_colony = sim.colonies[target_cid]
    other_cid = 0
    other_colony = sim.colonies[other_cid]

    # Create thralls in other colony laboring for target
    thrall1 = SandKing(other_cid, (5, 5, 5), UnitType.WORKER)
    thrall1.laboring_for = target_cid
    thrall1.defiance = 0.5
    other_colony.units.append(thrall1)

    thrall2 = SandKing(other_cid, (6, 6, 6), UnitType.WORKER)
    thrall2.laboring_for = target_cid
    thrall2.defiance = 0.3
    other_colony.units.append(thrall2)

    # Create gift unit
    gift_unit = SandKing(other_cid, (7, 7, 7), UnitType.WORKER)
    gift_unit.gift_to = target_cid
    other_colony.units.append(gift_unit)

    # Deposit pheromones on target's channel
    sim.pheromones.trails[10:15, 10:15, 5:8, target_cid, 0] = 1.0
    assert sim.pheromones.trails[:, :, :, target_cid, :].any()

    # Scrub
    sim._deactivate_slot(target_cid)

    # Assert clean
    assert captor_colony.pop_state == POP_DORMANT
    for other in sim.colonies:
        if other.colony_id == target_cid:
            continue
        for unit in other.units:
            assert getattr(unit, 'laboring_for', -1) != target_cid
            assert getattr(unit, 'gift_to', -1) != target_cid
            # a released thrall's defiance is reset; units that were never
            # thralls may not carry the attribute at all (getattr-guarded)
            assert getattr(unit, 'defiance', 0.0) == 0.0
    assert not sim.pheromones.trails[:, :, :, target_cid, :].any()


def test_pop3_scrub_p3_disposition_monitors_learners_pending():
    """P3: disposition + monitors/learners + pending scrub clean.

    Set disposition off-neutral; touch monitors/learners; schedule pending respawn.
    After scrub: all reset/cleared.
    """
    sim = make_sim()
    target_cid = 1
    target_colony = sim.colonies[target_cid]

    # Set disposition off-neutral
    target_colony.favoritism = 0.8
    target_colony.agitation = 0.5
    target_colony.confidence = 0.2

    # Add to monitors and learners. `monitors` is ctor-initialized; `learners`
    # is created lazily on first neural use, so ensure it exists for the test.
    if not hasattr(sim, 'learners'):
        sim.learners = {}
    sim.monitors[target_cid] = "mock_monitor"
    sim.learners[target_cid] = "mock_learner"

    # Schedule a pending respawn
    sim.pending_respawns[target_cid] = sim.step_count + 100

    # Verify setup
    assert target_colony.favoritism != 0.0
    assert target_colony.agitation != 0.0
    assert target_colony.confidence != 0.5
    assert target_cid in sim.monitors
    assert target_cid in sim.learners
    assert target_cid in sim.pending_respawns

    # Scrub
    sim._deactivate_slot(target_cid)

    # Assert clean
    assert target_colony.pop_state == POP_DORMANT
    assert target_colony.favoritism == 0.0
    assert target_colony.agitation == 0.0
    assert target_colony.confidence == 0.5
    assert target_cid not in sim.monitors
    assert target_cid not in sim.learners
    assert target_cid not in sim.pending_respawns


def test_pop3_scrub_out_of_scope_house_grudges_intact():
    """Out-of-scope guard: house_grudges (keyed by NAME, not colony_id) survive.

    Slot scrub must not erase lineage grudges (they are dynasty property,
    not slot property).
    """
    sim = make_sim()
    target_cid = 1

    # Seed a house_grudges entry by house NAME (not colony_id)
    if not hasattr(sim, 'house_grudges'):
        sim.house_grudges = {}
    house_name = "House Crimson"
    sim.house_grudges[house_name] = 0.8  # grudge against the house lineage

    # Scrub the slot
    sim._deactivate_slot(target_cid)

    # Assert house_grudges by name is INTACT
    assert house_name in sim.house_grudges
    assert sim.house_grudges[house_name] == 0.8


# ============================================================================
# POP-4: MAX_COLONIES constant (§2.1).
# ============================================================================

def test_pop4_max_colonies_constant():
    """MAX_COLONIES == 8."""
    assert MAX_COLONIES == 8


def test_pop4_construction_num_colonies_2():
    """Construction with num_colonies=2 succeeds."""
    random.seed(42)
    np.random.seed(42)
    sim = SandKingsSimulation(width=40, height=30, depth=12, num_colonies=2)
    assert len(sim.colonies) == 2
    assert sim.pheromones.trails.shape[3] == 2
    assert sim.num_colonies <= MAX_COLONIES


def test_pop4_construction_num_colonies_4():
    """Construction with num_colonies=4 succeeds."""
    random.seed(43)
    np.random.seed(43)
    sim = SandKingsSimulation(width=40, height=30, depth=12, num_colonies=4)
    assert len(sim.colonies) == 4
    assert sim.pheromones.trails.shape[3] == 4
    assert sim.num_colonies <= MAX_COLONIES


def test_pop4_construction_num_colonies_8():
    """Construction with num_colonies=8 succeeds."""
    random.seed(44)
    np.random.seed(44)
    sim = SandKingsSimulation(width=40, height=30, depth=12, num_colonies=8)
    assert len(sim.colonies) == 8
    assert sim.pheromones.trails.shape[3] == 8
    assert sim.num_colonies <= MAX_COLONIES
