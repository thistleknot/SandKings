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
    ca = next((c for c in sim.colonies if c.colony_id == a), None)
    cb = next((c for c in sim.colonies if c.colony_id == b), None)
    if (ca is not None and cb is not None and getattr(ca, 'house', '')
            and getattr(ca, 'house', '') == getattr(cb, 'house', '')):
        return False  # kin (D1)
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
