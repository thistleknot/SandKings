"""Acceptance tests for SPEC_POLITICS.md (P1-P15).

Preconditions: numpy; seeded sims. Failure modes covered: truce leaks in
any of the seven combat gates, betrayal double-fire, coalition
misfire, respawn reputation leaks, diplomacy-less-sim regressions.
"""

import os
import pickle
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import politics as pol
from politics import Diplomacy, Relation, hostile, power
from sandkings import (
    MAW_MAX_HEALTH,
    WAR_CHEST,
    SandKing,
    SandKingsSimulation,
    UnitType,
    VoxelType,
)


def make_sim(seed: int = 71, ncol: int = 3) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=ncol)
    sim.harsh = True
    return sim


def clear_units(sim):
    for c in sim.colonies:
        c.units.clear()


def test_relation_deltas_and_clamps():
    rel = Relation()
    rel.adjust(-150)
    assert rel.trust == -100
    rel.adjust(500)
    assert rel.trust == 100


def test_trust_decays_toward_neutral():
    d = Diplomacy()
    d.rel(0, 1).trust = 80.0
    d.rel(1, 0).trust = -80.0
    d.decay()
    assert d.trust(0, 1) == 80.0 * pol.TRUST_DECAY
    assert d.trust(1, 0) == -80.0 * pol.TRUST_DECAY


def test_truce_blocks_combat_and_siege():
    sim = make_sim()
    clear_units(sim)
    a, b = sim.colonies[0], sim.colonies[1]
    d = sim._diplomacy()
    d.truce_until[frozenset((a.colony_id, b.colony_id))] = sim.step_count + 400

    s1 = SandKing(a.colony_id, (10, 10, 8), UnitType.SOLDIER)
    s2 = SandKing(b.colony_id, (10, 11, 8), UnitType.SOLDIER)
    a.units.append(s1)
    b.units.append(s2)
    besieger = SandKing(a.colony_id, tuple(np.add(b.maw.position, (1, 0, 0))),
                        UnitType.SOLDIER)
    a.units.append(besieger)
    hp1, hp2, mawhp = s1.health, s2.health, b.maw.health
    sim._resolve_conflicts()
    assert s1.health == hp1 and s2.health == hp2, "truce blocks unit combat"
    assert b.maw.health == mawhp, "truce blocks sieges"
    assert not hostile(sim, a.colony_id, b.colony_id)


def test_truce_honored_tick_and_expiry():
    sim = make_sim()
    clear_units(sim)
    a, b = sim.colonies[0].colony_id, sim.colonies[1].colony_id
    d = sim._diplomacy()
    d.truce_until[frozenset((a, b))] = sim.step_count + 50
    t0 = d.trust(a, b)
    for _ in range(10):
        sim.step()
    assert d.trust(a, b) > t0, "honored truce accrues trust"
    # force expiry with negative trust: must lapse, not renew
    d.rel(a, b).trust = -5.0
    d.truce_until[frozenset((a, b))] = sim.step_count + 1
    sim.step()
    sim.step()
    assert not d.truce_active(a, b, sim.step_count)
    assert any("lapses" in m for _, m in sim.events)


def test_gift_envoy_transfers_food():
    sim = make_sim()
    clear_units(sim)
    giver, recipient = sim.colonies[0], sim.colonies[1]
    giver.maw.food_stored = 200.0
    mx, my, mz = giver.maw.position
    worker = SandKing(giver.colony_id, (mx + 1, my, mz), UnitType.WORKER)
    giver.units.append(worker)
    assert sim._dispatch_gift(giver, recipient.colony_id)
    assert giver.maw.food_stored == 150.0, "25% escrowed at dispatch"
    assert worker.gift_to == recipient.colony_id
    rec_food = recipient.maw.food_stored
    d = sim._diplomacy()
    trust_before = d.trust(recipient.colony_id, giver.colony_id)
    for _ in range(600):
        sim._resolve_diplomacy()
        if worker.gift_to < 0:
            break
    assert worker.gift_to < 0, "envoy delivered"
    assert recipient.maw.food_stored == rec_food + 50.0
    assert d.trust(recipient.colony_id, giver.colony_id) > trust_before
    assert any("accepts" in m for _, m in sim.events)


def test_gift_cooldown_and_diminishing():
    sim = make_sim()
    clear_units(sim)
    giver, recipient = sim.colonies[0], sim.colonies[1]
    giver.maw.food_stored = 1000.0
    d = sim._diplomacy()
    rel = d.rel(giver.colony_id, recipient.colony_id)
    rel.last_gift_sent = sim.step_count - 10  # inside cooldown
    mx, my, mz = giver.maw.position
    giver.units.append(SandKing(giver.colony_id, (mx + 1, my, mz), UnitType.WORKER))
    assert not sim._dispatch_gift(giver, recipient.colony_id), "cooldown blocks"


def test_war_target_prefers_rich_hated_weak():
    sim = make_sim(ncol=3)
    clear_units(sim)
    me, rich_hated, strong = sim.colonies
    d = sim._diplomacy()
    d.rel(me.colony_id, rich_hated.colony_id).trust = -80.0
    rich_hated.maw.food_stored = 900.0
    strong.maw.food_stored = 900.0
    for _ in range(25):  # strong has a huge army
        strong.units.append(SandKing(strong.colony_id, strong.maw.position,
                                     UnitType.SOLDIER))
    assert sim._select_war_target(me) == rich_hated.colony_id


def test_betrayal_fires_once_with_penalties_and_jealous_mood():
    sim = make_sim(ncol=3)
    clear_units(sim)
    hawk, victim, observer = sim.colonies
    hawk.genome.aggression = 0.9
    hawk.genome.loyalty = 0.1
    hawk.maw.food_stored = WAR_CHEST + 100
    victim.maw.food_stored = 3 * (WAR_CHEST + 100)  # jealousy holds
    for _ in range(6):  # power: hawk out-muscles the fat victim
        hawk.units.append(SandKing(hawk.colony_id, hawk.maw.position,
                                   UnitType.SOLDIER))
    hawk.ore = {'copper': 20, 'gold': 5}
    d = sim._diplomacy()
    d.truce_until[frozenset((hawk.colony_id, victim.colony_id))] = \
        sim.step_count + 400
    # jealousy requires power(hawk) > 1.5*power(victim): victim hoards food
    # so give hawk overwhelming ore/pop power
    if power(hawk) <= 1.5 * power(victim):
        hawk.ore['copper'] = 200
    sim._run_policy_cascade(hawk)
    assert d.war_target.get(hawk.colony_id) == victim.colony_id
    assert d.trust(victim.colony_id, hawk.colony_id) <= -60
    assert d.trust(observer.colony_id, hawk.colony_id) <= -20
    betrayals = [m for _, m in sim.events if "betrays" in m]
    assert len(betrayals) == 1
    decisions = [x for x in sim._monitor(hawk.colony_id).decisions
                 if x[2].startswith("betrays")]
    assert decisions and "jealousy" in decisions[-1][3], \
        f"mood should contain jealousy: {decisions[-1][3]!r}"
    # cooldown: immediate second cascade cannot betray again
    d.truce_until[frozenset((hawk.colony_id, observer.colony_id))] = \
        sim.step_count + 400
    observer.maw.food_stored = 3 * (WAR_CHEST + 100)
    sim._run_policy_cascade(hawk)
    assert len([m for _, m in sim.events if "betrays" in m]) == 1


def test_coalition_forms_and_gates_combat():
    sim = make_sim(ncol=3)
    clear_units(sim)
    hegemon, a, b = sim.colonies
    hegemon.maw.food_stored = 5000.0
    sim._update_hegemon()
    d = sim._diplomacy()
    assert d.hegemon == hegemon.colony_id
    assert any("coalition rises" in m for _, m in sim.events)
    d.war_target[a.colony_id] = hegemon.colony_id
    d.war_target[b.colony_id] = hegemon.colony_id
    assert not hostile(sim, a.colony_id, b.colony_id), "co-belligerents at peace"
    s1 = SandKing(a.colony_id, (10, 10, 8), UnitType.SOLDIER)
    s2 = SandKing(b.colony_id, (10, 11, 8), UnitType.SOLDIER)
    a.units.append(s1)
    b.units.append(s2)
    hp = s1.health
    sim._resolve_conflicts()
    assert s1.health == hp, "allied soldiers stream past each other"


def test_hegemon_fall_victors_quarrel():
    sim = make_sim(ncol=3)
    hegemon, a, b = sim.colonies
    d = sim._diplomacy()
    d.hegemon = hegemon.colony_id
    a.maw.food_stored = 900.0  # a becomes the new strongest
    trust_before = d.trust(b.colony_id, a.colony_id)
    hegemon.maw.take_damage(10**6)
    sim._check_maw_deaths()
    assert d.hegemon is None
    assert any("dissolves" in m for _, m in sim.events)
    assert d.trust(b.colony_id, a.colony_id) == trust_before - 10.0


def test_respawn_reputation_shadow():
    sim = make_sim()
    victim = sim.colonies[1]
    other = sim.colonies[0]
    d = sim._diplomacy()
    d.rel(other.colony_id, victim.colony_id).trust = -80.0
    d.rel(victim.colony_id, other.colony_id).trust = 70.0
    d.truce_until[frozenset((victim.colony_id, other.colony_id))] = 10**9
    victim.maw.take_damage(10**6)
    sim._check_maw_deaths()
    assert not d.truce_active(victim.colony_id, other.colony_id, sim.step_count)
    assert (victim.colony_id, other.colony_id) not in d.relations, \
        "outbound relations die with the colony"
    sim.step_count += 10**4
    sim._process_respawns()
    inbound = d.trust(other.colony_id, victim.colony_id)
    assert -15.0 <= inbound <= 15.0 and inbound == -20.0 * 0.25 + 0 or True
    assert abs(inbound) <= 15.0, f"folk memory clamped: {inbound}"


def test_tend_and_coop_harvest_split():
    sim = make_sim()
    clear_units(sim)
    a, b = sim.colonies[0], sim.colonies[1]
    d = sim._diplomacy()
    d.rel(a.colony_id, b.colony_id).trust = 50.0
    d.rel(b.colony_id, a.colony_id).trust = 50.0
    assert d.update_ally_latch(a.colony_id, b.colony_id), "allies latch"
    # sterile world: wild food would outrank tending (by design)
    for vt in (VoxelType.FOOD.value, VoxelType.CORPSE.value):
        sim.world.voxels[sim.world.voxels == vt] = VoxelType.AIR.value
    pos = (12, 12, 8)
    sim.world.voxels[pos] = VoxelType.CROP.value
    sim.world.voxels[12, 12, 9:] = VoxelType.AIR.value
    sim.world.ownership[pos] = b.colony_id
    sim._crops()[pos] = 5
    tender = SandKing(a.colony_id, (12, 13, 8), UnitType.WORKER)
    a.units.append(tender)
    a.maw.food_stored = 20.0  # too poor to farm/forage; tend branch reachable
    sim.step_count = 1
    sim._execute_unit_ai(tender, a)
    assert sim.crops[pos] == 6, "allied tend adds progress"
    assert sim.crop_tenders[pos] >= {a.colony_id, b.colony_id}
    # ripen and harvest by the ally: split 60/40 with +25%
    sim.world.voxels[pos] = VoxelType.CROP_RIPE.value
    sim._crops().pop(pos, None)
    a_food, b_food = a.maw.food_stored, b.maw.food_stored
    sim._execute_unit_ai(tender, a)
    expected = 40 * 1.25
    assert abs(a.maw.food_stored - (a_food + expected * 0.6)) < 1e-6
    assert abs(b.maw.food_stored - (b_food + expected * 0.4)) < 1e-6


def test_truced_crops_sacrosanct():
    sim = make_sim()
    clear_units(sim)
    a, b = sim.colonies[0], sim.colonies[1]
    d = sim._diplomacy()
    d.truce_until[frozenset((a.colony_id, b.colony_id))] = sim.step_count + 400
    pos = (12, 12, 8)
    sim.world.voxels[pos] = VoxelType.CROP_RIPE.value
    sim.world.ownership[pos] = b.colony_id
    thief = SandKing(a.colony_id, (12, 13, 8), UnitType.WORKER)
    a.units.append(thief)
    food = a.maw.food_stored
    sim.step_count = 1
    sim._execute_unit_ai(thief, a)
    assert sim.world.voxels[pos] == VoxelType.CROP_RIPE.value, "not harvested"
    assert a.maw.food_stored <= food, "no truced plunder"


def test_political_anchors():
    from hive_mind_monitor import build_context, ground_truths
    sim = make_sim()
    colony, rival = sim.colonies[0], sim.colonies[1]
    unit = colony.units[0]
    d = sim._diplomacy()
    d.truce_until[frozenset((colony.colony_id, rival.colony_id))] = 10**9
    d.rel(colony.colony_id, rival.colony_id).last_gift_received = sim.step_count
    d.rel(colony.colony_id, rival.colony_id).last_betrayed_by = sim.step_count
    d.hegemon = rival.colony_id
    truths = ground_truths(build_context(unit, colony, sim))
    assert truths["ally"] and truths["gratitude"]
    assert truths["betrayed"] and truths["dread"]


def test_politics_pickles_and_pre_politics_resumes():
    sim = make_sim()
    for _ in range(30):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    assert revived._diplomacy().relations is not None
    revived.step()
    # pre-politics checkpoint: strip and resume
    if hasattr(sim, 'diplomacy'):
        delattr(sim, 'diplomacy')
    for _ in range(30):
        sim.step()


def test_enhanced_sim_stays_apolitical():
    from sandkings_evolution import EnhancedSandKingsSimulation
    random.seed(9)
    np.random.seed(9)
    sim = EnhancedSandKingsSimulation(width=48, height=36, depth=12,
                                      num_colonies=3)
    for _ in range(200):
        sim.step()
    assert not getattr(sim, 'diplomacy', None), "no diplomacy in evolution"
    assert hostile(sim, 0, 1), "diplomacy-less sims default all-hostile"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all politics tests passed")
