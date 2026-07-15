"""The political world: trust ledgers, truces, war targets, coalitions.

Governed by SPEC_POLITICS.md (P1-P15). Directional trust per ordered
colony pair, built slowly by honored commitments and shared blood,
destroyed quickly by violence and betrayal, decaying toward forgiveness
(Axelrod); coalitions balance against capability, not sentiment (Waltz);
betrayal poisons standing with every observer (Nowak/Sigmund).

Preconditions: stdlib + dataclasses only; pickles with the sim. Failure
modes: `hostile()` defaults to all-hostile when a sim carries no
diplomacy (evolution sims stay pure combat).
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Tuple

TRUST_DECAY = 0.999          # per step; half-life ~693 steps (P2)
ALLY_TRUST = 40.0            # latch on (mutual)
ALLY_EXIT = 25.0             # latch off (either direction)
FRIENDLY = 15.0
HOSTILE = -25.0
NEMESIS = -60.0              # refuses all truces
TRUCE_DURATION = 400         # = one season
GRUDGE_LOCK = 600            # steps a betrayal blocks truces from the betrayer
BETRAYAL_COOLDOWN = 800      # per betrayer
REJECT_COOLDOWN = 100        # re-proposal wait after refusal
GIFT_COOLDOWN = 150          # per (giver, recipient)
GIFT_WINDOW = 500            # diminishing-returns window
GIFT_TRUST_FOOD = 12.0
GIFT_TRUST_GOLD = 18.0
TRUST_UNIT_KILL = -4.0
TRUST_MAW_HP = -0.08         # per HP of siege damage
TRUST_FIRST_BLOOD = -10.0
TRUST_CROP_RAID = -6.0       # per razed/raided voxel
TRUST_TRUCE_TICK = 0.02      # honored truce, per step, each direction
TRUST_JOINT_WAR = 0.05       # co-belligerence, per step, each direction
TRUST_COALITION = 0.08       # alignment drift, per step, capped
COALITION_CAP = 60.0
BETRAYAL_VICTIM = -60.0
BETRAYAL_OBSERVER = -20.0
VICTORS_QUARREL = -10.0
HEGEMON_ENTER = 1.6          # x equal share
HEGEMON_EXIT = 1.3
# Suzerainty (SPEC_SUZERAIN, War & Survival arc Phase 4): a power strong enough past a HIGHER threshold
# imposes a tributary order instead of being ganged up on (supersedes the coalition above SUZERAIN_ENTER).
SUZERAIN_ENTER = 2.4         # x equal share to IMPOSE vassalage (above HEGEMON_ENTER)
SUZERAIN_EXIT = 1.8          # x equal share below which the order crumbles (hysteresis)
TRIBUTE_INTERVAL = 200       # steps between coerced tribute renderings
TRIBUTE_RATE = 0.10          # fraction of a vassal's food owed per interval
TRIBUTE_RESENTMENT = 10.0    # non-decaying grudge a vassal accrues per tribute (revolt fuel)
REVOLT_RESENTMENT = 50.0     # overlord_grudge at which a vassal revolts (~5 tributes)
TRIBUTE_TRUST_HIT = -3.0     # diplomatic-trust nudge per tribute (flavor for other readers; decays)
# Repression & Resistance (SPEC_REPRESSION, Phase 5): the tribute order becomes two-sided — the overlord pays
# to repress (iron fist), the vassal sabotages back, and repression breeds a simmering long-memory that shortens
# each next fuse (the krypteia paradox). All deterministic; gated REPRESSION_ENABLED (byte-identical off).
REPRESSION_COST_FOOD = 12.0  # food the iron fist costs the overlord per repressed vassal per interval
REPRESSION_CALM = 8.0        # grudge the fist suppresses per repression (< TRIBUTE_RESENTMENT: repressed vassal still climbs)
REPRESSION_RESENTMENT = 1.0  # krypteia long-memory (subjugation_memory) bred per repression
MEMORY_ACCEL_K = 0.5         # subjugation_memory's contribution to per-tribute grudge accrual
SABOTAGE_WITHHOLD_K = 0.6    # tribute-withholding scale vs grudge_norm
SABOTAGE_WITHHOLD_CAP = 0.5  # max fraction of owed tribute a resentful vassal withholds
SABOTAGE_DAMAGE_K = 0.025    # fraction of overlord food a resentful vassal spoils per interval (destroyed) — kept
                             # low so sabotage reads as an income-drag, not an acute power-collapse (a design
                             # preference; the revolt-vs-dissolution timing is driven by the krypteia horizon, WW1)
SABOTAGE_MIN_GRUDGE = 20.0   # grudge below which a vassal does not yet sabotage
# Wage vs Whip (SPEC_DIFFUSE_RESISTANCE, Phase 6): the overlord's disposition sets the extraction style —
# an aggressive (Mycenae/Sparta) overlord rules by the whip (fast krypteia -> revolt), a peaceable (Minoan)
# one by the wage (softened grudge -> durable order, plus a small permanent foot-drag). hardness = aggression.
WHIP_MEMORY_K = 4.0          # hard-order krypteia acceleration (memory_gain *= 1 + WHIP_MEMORY_K*hardness)
WAGE_GRUDGE_FLOOR = 0.5      # soft-order grudge-accrual floor (grudge_mult in [WAGE_GRUDGE_FLOOR, 1])
DIFFUSE_DRAG = 0.10          # max permanent foot-drag withholding for the softest order (the anarchist drag)
DIPLOMACY_INTERVAL = 25
COOP_YIELD_BONUS = 0.25      # jointly tended crops (P10)
RESPAWN_SHADOW = 0.25        # inbound trust carryover factor (P12)
RESPAWN_SHADOW_CLAMP = 15.0


@dataclass
class Relation:
    """a's stance toward b (directional). Trust in [-100, 100]."""
    trust: float = 0.0
    last_gift_sent: int = -10**9
    gifts_in_window: int = 0
    window_start: int = -10**9
    last_gift_received: int = -10**9
    last_betrayed_by: int = -10**9   # step b last betrayed a
    last_hostility: int = -10**9     # step of last hostile act from b

    def adjust(self, delta: float):
        self.trust = max(-100.0, min(100.0, self.trust + delta))


class Diplomacy:
    """All political state for one sim; lives at sim.diplomacy (P1)."""

    def __init__(self):
        self.relations: Dict[Tuple[int, int], Relation] = {}
        self.truce_until: Dict[FrozenSet[int], int] = {}
        self.war_target: Dict[int, Optional[int]] = {}
        self.hegemon: Optional[int] = None
        self.rejected_at: Dict[FrozenSet[int], int] = {}
        self.last_betrayal: Dict[int, int] = {}      # betrayer -> step
        self.allied: Dict[FrozenSet[int], bool] = {}  # ally latch (P2)
        self.restless_logged: Dict[int, int] = {}

    def rel(self, a: int, b: int) -> Relation:
        key = (a, b)
        if key not in self.relations:
            self.relations[key] = Relation()
        return self.relations[key]

    def trust(self, a: int, b: int) -> float:
        return self.rel(a, b).trust

    def truce_active(self, a: int, b: int, step: int) -> bool:
        return self.truce_until.get(frozenset((a, b)), -1) > step

    def update_ally_latch(self, a: int, b: int) -> bool:
        """Mutual >= ALLY_TRUST latches on; either < ALLY_EXIT unlatches."""
        key = frozenset((a, b))
        latched = self.allied.get(key, False)
        ta, tb = self.trust(a, b), self.trust(b, a)
        if latched:
            if ta < ALLY_EXIT or tb < ALLY_EXIT:
                self.allied[key] = False
        else:
            if ta >= ALLY_TRUST and tb >= ALLY_TRUST:
                self.allied[key] = True
        return self.allied.get(key, False)

    def ally(self, a: int, b: int) -> bool:
        return self.allied.get(frozenset((a, b)), False)

    def co_belligerents(self, a: int, b: int) -> bool:
        h = self.hegemon
        return (h is not None and a != h and b != h
                and self.war_target.get(a) == h and self.war_target.get(b) == h)

    def decay(self):
        for rel in self.relations.values():
            rel.trust *= TRUST_DECAY

    def clear_slot(self, colony_id: int, step: int):
        """T5 death cascade: treaties/targets/grudges die with the colony;
        inbound trust becomes the P12 folk-memory shadow at respawn time."""
        for key in [k for k in self.truce_until if colony_id in k]:
            del self.truce_until[key]
        for key in [k for k in self.rejected_at if colony_id in k]:
            del self.rejected_at[key]
        for key in [k for k in self.allied if colony_id in k]:
            del self.allied[key]
        self.war_target.pop(colony_id, None)
        for cid, target in list(self.war_target.items()):
            if target == colony_id:
                self.war_target[cid] = None
        self.last_betrayal.pop(colony_id, None)
        # outbound reset now; inbound shadow applied at respawn (P12)
        for (a, b) in list(self.relations.keys()):
            if a == colony_id:
                del self.relations[(a, b)]

    def apply_respawn_shadow(self, colony_id: int):
        """Others keep a dampened memory of the banner (P12)."""
        for (a, b), rel in self.relations.items():
            if b == colony_id:
                rel.trust = max(-RESPAWN_SHADOW_CLAMP,
                                min(RESPAWN_SHADOW_CLAMP,
                                    RESPAWN_SHADOW * rel.trust))
                rel.last_betrayed_by = -10**9


def hostile(sim, a: int, b: int) -> bool:
    """The single combat gate (P9). All-hostile when no diplomacy exists.

    D1 amendment: colonies of the same house are kin - never hostile.
    Kinship outranks even grievance; a house does not war on itself.
    """
    if a == b:
        return False
    if a < 0 or b < 0:
        return True
    diplomacy = getattr(sim, 'diplomacy', None)
    if diplomacy is None:
        return True
    # kin check (D1) via an O(1) map - hostile() runs millions of times
    # per soak inside the combat loops; the map rebuilds only when a
    # house is founded or a slot respawns (sim._kin_epoch bumps)
    epoch = getattr(sim, '_kin_epoch', 0)
    cache = getattr(sim, '_kin_map', None)
    if cache is None or cache[0] != epoch:
        cache = (epoch, {c.colony_id: getattr(c, 'house', '')
                         for c in sim.colonies})
        sim._kin_map = cache
    house_a = cache[1].get(a, '')
    if house_a and house_a == cache[1].get(b, ''):
        return False  # kin (D1)
    # SPEC_SUZERAIN SZ2: the Pax — overlord<->vassal and co-vassals of one overlord do not war.
    # Epoch-cached like the kin map; gated so the battery (no sim.suzerain_enabled) is byte-identical.
    if getattr(sim, 'suzerain_enabled', False):
        s_epoch = getattr(sim, '_suzerain_epoch', 0)
        s_cache = getattr(sim, '_suzerain_map', None)
        if s_cache is None or s_cache[0] != s_epoch:
            s_cache = (s_epoch, {c.colony_id: getattr(c, 'tributary_to', -1)
                                 for c in sim.colonies
                                 if getattr(c, 'tributary_to', -1) >= 0})
            sim._suzerain_map = s_cache
        smap = s_cache[1]
        oa, ob = smap.get(a, -1), smap.get(b, -1)
        if oa == b or ob == a:
            return False  # overlord <-> its vassal
        if oa >= 0 and oa == ob:
            return False  # co-vassals of the same overlord
    step = sim.step_count
    if diplomacy.truce_active(a, b, step):
        return False
    if diplomacy.ally(a, b):
        return False
    if diplomacy.co_belligerents(a, b):
        return False
    return True


def power(colony) -> float:
    """Capability index (P7): what realists balance against."""
    ore = getattr(colony, 'ore', {})
    return (colony.maw.food_stored + 15.0 * len(colony.units)
            + 0.2 * colony.maw.health
            + 25.0 * ore.get('copper', 0) + 10.0 * ore.get('gold', 0))
