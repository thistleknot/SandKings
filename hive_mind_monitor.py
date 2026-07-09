"""Hive mind monitor: concept probes, thoughts, and decision logging.

Governed by SPEC_HIVE_MONITOR.md. Translates each soldier's GRU hidden
state into human-readable thoughts via per-colony linear probes trained
online against measurable ground truths (M1/M2); every anchor passing the
probability and accuracy gates emits a word from its embedding-derived
cluster (M3, thought_vocabulary.json). Rule-based units get instincts —
the same lexicon evaluated directly on state.

Preconditions: numpy only (hidden states arrive as numpy arrays; no torch,
no pygame). Failure modes: a missing vocabulary JSON degrades to
seed-word-only clusters; probes are per-colony and never shared.
"""

import json
import os
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

PROBE_LR = 0.05          # online logistic-regression step size (M2)
PROBE_ACC_DECAY = 0.99   # accuracy EMA horizon
THOUGHT_MIN_P = 0.6      # decoded probability gate (M3)
THOUGHT_MIN_ACC = 0.65   # probe accuracy gate: below this the mind is unreadable
THOUGHT_MAX = 4          # display truncation only — all passing anchors emit
THOUGHT_CAPS_P = 0.85    # decoded p above which the word renders in CAPS
DECISION_LOG_LEN = 30    # per-colony decision entries kept (M4)
HIDDEN_DIM = 32          # soldier GRU hidden size (spec N10)

ANCHOR_SEEDS = [
    "food", "hunger", "war", "defense", "underground", "danger", "flee",
    "hunt", "wounded", "home", "feast", "buried", "crowd", "alone", "rich",
    "storm", "death", "enemy", "victory", "siege", "jealousy", "love",
    "clueless", "harvest", "farm", "drought", "gold", "ally", "betrayed",
    "gratitude", "dread", "machine", "radiation", "fire", "monster",
]

_VOCAB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "thought_vocabulary.json")


def _load_vocabulary() -> Dict[str, List[str]]:
    """Embedding-derived clusters (M9); seed-only fallback when missing."""
    try:
        with open(_VOCAB_PATH, encoding="utf-8") as fh:
            clusters = json.load(fh)["clusters"]
    except (OSError, KeyError, json.JSONDecodeError):
        clusters = {}
    return {seed: clusters.get(seed) or [seed] for seed in ANCHOR_SEEDS}


VOCABULARY = _load_vocabulary()


def word_for(anchor: str, p: float) -> str:
    """Cluster word scaled by decoded probability: mild neighbor near the
    gate, seed word near certainty, CAPS above THOUGHT_CAPS_P (M3)."""
    cluster = VOCABULARY[anchor]
    span = max(1e-9, 1.0 - THOUGHT_MIN_P)
    index = int((p - THOUGHT_MIN_P) / span * len(cluster))
    word = cluster[min(max(index, 0), len(cluster) - 1)]
    return word.upper() if p > THOUGHT_CAPS_P else word


def build_context(unit, colony, sim) -> Dict[str, float]:
    """One pass of the shared measurements every M1 predicate reads."""
    x, y, z = unit.position
    world = sim.world

    from politics import hostile as _hostile
    enemy_dist = float("inf")
    enemy_maw_cheb = float("inf")
    for other in sim.colonies:
        if not _hostile(sim, colony.colony_id, other.colony_id):
            continue  # P9: allies aren't danger (jealousy stays unfiltered)
        for enemy in other.units:
            d = (abs(enemy.position[0] - x) + abs(enemy.position[1] - y)
                 + abs(enemy.position[2] - z))
            if d < enemy_dist:
                enemy_dist = d
        if other.is_alive():
            m = other.maw.position
            c = max(abs(m[0] - x), abs(m[1] - y), abs(m[2] - z))
            if c < enemy_maw_cheb:
                enemy_maw_cheb = c

    allies_3 = allies_6 = wounded_ally_2 = 0
    for ally in colony.units:
        if ally is unit:
            continue
        d = (abs(ally.position[0] - x) + abs(ally.position[1] - y)
             + abs(ally.position[2] - z))
        if d <= 3:
            allies_3 += 1
        if d <= 6:
            allies_6 += 1
        if d <= 2 and ally.health < ally.max_health * 0.5:
            wounded_ally_2 += 1

    richest_enemy_food = max(
        (c.maw.food_stored for c in sim.colonies
         if c.colony_id != colony.colony_id and c.is_alive()), default=0.0)

    w, h, d3 = world.dimensions
    x0, x1 = max(0, x - 3), min(w, x + 4)
    y0, y1 = max(0, y - 3), min(h, y + 4)
    z0, z1 = max(0, z - 3), min(d3, z + 4)
    box3 = world.voxels[x0:x1, y0:y1, z0:z1]
    bx, by, bz = x - x0, y - y0, z - z0
    box2 = box3[max(0, bx - 2):bx + 3, max(0, by - 2):by + 3,
                max(0, bz - 2):bz + 3]

    solid = 0
    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                       (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        nx, ny, nz = x + dx, y + dy, z + dz
        if world.in_bounds(nx, ny, nz) and world.get_voxel(nx, ny, nz).is_solid():
            solid += 1

    mx, my, mz = colony.maw.position
    from sandkings import BOOTSTRAP_FLOOR, VoxelType, WAR_CHEST, UnitType

    return {
        "enemy_dist": enemy_dist,
        "enemy_maw_cheb": enemy_maw_cheb,
        "tilled_2": int((box2 == VoxelType.TILLED.value).sum()),
        "crop_ripe_2": int((box2 == VoxelType.CROP_RIPE.value).sum()),
        "season": sim.season_index() if callable(getattr(sim, 'season_index', None)) else 0,
        "carrying_ore": getattr(unit, 'carrying', None) in ('copper', 'gold'),
        "colony_gold": getattr(colony, 'ore', {}).get('gold', 0),
        "device_3": sum(
            1 for d in getattr(colony, 'devices', [])
            if d.position is not None
            and max(abs(d.position[0] - x), abs(d.position[1] - y),
                    abs(d.position[2] - z)) <= 3),
        "carrying_salvage": getattr(unit, 'carrying', None) == 'salvage',
        "rad_here": (sim.radiation_at(x, y)
                     if callable(getattr(sim, 'radiation_at', None)) else 0.0),
        "has_ally": _political(sim, colony, "has_ally"),
        "recently_betrayed": _political(sim, colony, "recently_betrayed"),
        "recent_gift": _political(sim, colony, "recent_gift"),
        "hegemon_other": _political(sim, colony, "hegemon_other"),
        "allies_3": allies_3,
        "allies_6": allies_6,
        "wounded_ally_2": wounded_ally_2,
        "richest_enemy_food": richest_enemy_food,
        "food_2": int((box2 == VoxelType.FOOD.value).sum()),
        "corpse_2": int((box2 == VoxelType.CORPSE.value).sum()),
        "corpse_3": int((box3 == VoxelType.CORPSE.value).sum()),
        "solid_6": solid,
        "maw_dist": abs(mx - x) + abs(my - y) + abs(mz - z),
        "below_surface": z < world.surface_z(x, y),
        "colony_food": colony.maw.food_stored,
        "at_war": colony.at_war,
        "storm": getattr(sim, "storm_until", 0) > sim.step_count,
        "fire_3": any(max(abs(fx - x), abs(fy - y), abs(fz - z)) <= 3
                      for fx, fy, fz in (getattr(sim, 'fires', None) or {})),
        "beast_6": any(abs(b.position[0] - x) + abs(b.position[1] - y)
                       + abs(b.position[2] - z) <= 6
                       for b in (getattr(sim, 'fauna', None) or [])),
        "retreating": unit.retreating,
        "wounded": unit.health < unit.max_health * 0.5,
        "is_soldier": unit.unit_type == UnitType.SOLDIER,
        "kills": getattr(unit.brain_layer, "kills", 0) if unit.brain_layer else 0,
        "foraging_range": colony.genome.foraging_range,
        "hunger_floor": 2 * BOOTSTRAP_FLOOR,
        "war_chest": WAR_CHEST,
    }


def _political(sim, colony, key: str) -> bool:
    """Colony-level relation facts for the P14 anchors (guarded)."""
    diplomacy = getattr(sim, 'diplomacy', None)
    if diplomacy is None:
        return False
    cid = colony.colony_id
    step = sim.step_count
    if key == "has_ally":
        return any(diplomacy.ally(cid, c.colony_id)
                   or diplomacy.truce_active(cid, c.colony_id, step)
                   for c in sim.colonies if c.colony_id != cid)
    if key == "recently_betrayed":
        return any(step - rel.last_betrayed_by < 300
                   for (a, _b), rel in diplomacy.relations.items() if a == cid)
    if key == "recent_gift":
        return any(step - rel.last_gift_received < 300
                   for (a, _b), rel in diplomacy.relations.items() if a == cid)
    if key == "hegemon_other":
        return diplomacy.hegemon is not None and diplomacy.hegemon != cid
    return False


def ground_truths(ctx: Dict) -> Dict[str, bool]:
    """The M1 lexicon evaluated on one unit's context."""
    fr = ctx["foraging_range"]
    return {
        "food": ctx["food_2"] > 0,
        "hunger": ctx["colony_food"] < ctx["hunger_floor"],
        "war": bool(ctx["at_war"]),
        "defense": ctx["enemy_dist"] <= fr and ctx["maw_dist"] <= 6,
        "underground": bool(ctx["below_surface"]),
        "danger": ctx["enemy_dist"] <= 5,
        "flee": bool(ctx["retreating"]),
        "hunt": bool(ctx["is_soldier"]) and ctx["enemy_dist"] <= fr
                and not ctx["retreating"],
        "wounded": bool(ctx["wounded"]),
        "home": ctx["maw_dist"] <= 5,
        "feast": ctx["corpse_2"] > 0,
        "buried": ctx["solid_6"] >= 4,
        "crowd": ctx["allies_3"] >= 3,
        "alone": ctx["allies_6"] == 0,
        "rich": ctx["colony_food"] > ctx["war_chest"],
        "storm": bool(ctx["storm"]),
        "death": ctx["corpse_3"] >= 2,
        "enemy": ctx["enemy_dist"] <= fr,
        "victory": ctx["kills"] >= 1,
        "siege": ctx["enemy_maw_cheb"] <= 2,
        "jealousy": ctx["richest_enemy_food"] > 2 * max(1.0, ctx["colony_food"]),
        "love": ctx["wounded_ally_2"] > 0,
        "clueless": (ctx["enemy_dist"] <= 4 and not ctx["retreating"]
                     and not ctx["is_soldier"]),
        "harvest": ctx["crop_ripe_2"] > 0,
        "farm": ctx["tilled_2"] > 0,
        "drought": ctx["season"] in (2, 3),
        "gold": bool(ctx["carrying_ore"]) or ctx["colony_gold"] >= 1,
        "ally": bool(ctx["has_ally"]),
        "betrayed": bool(ctx["recently_betrayed"]),
        "gratitude": bool(ctx["recent_gift"]),
        "dread": bool(ctx["hegemon_other"]),
        "machine": ctx["device_3"] > 0 or bool(ctx["carrying_salvage"]),
        "radiation": ctx["rad_here"] >= 0.5,
        "fire": bool(ctx["fire_3"]),
        "monster": bool(ctx["beast_6"]),
    }


def instincts_for(unit, colony, sim) -> List[str]:
    """Ground-truth-active anchors as seed words, lexicon order (M3)."""
    truths = ground_truths(build_context(unit, colony, sim))
    return [seed for seed in ANCHOR_SEEDS if truths[seed]]


class ConceptProbe:
    """Online logistic readout of the soldier hidden state for one anchor.

    predict() gives the decoded probability; update() does one SGD step
    against ground truth and folds thresholded correctness into an
    accuracy EMA. Plain numpy state: pickles with the sim (M6).
    """

    def __init__(self, dim: int = HIDDEN_DIM):
        # derive from the global stream so seeded tests are reproducible
        rng = np.random.default_rng(int(np.random.randint(0, 2**31)))
        self.w = (rng.standard_normal(dim) * 0.01).astype(np.float64)
        self.b = 0.0
        self.accuracy = 0.5
        self.observations = 0

    def predict(self, hidden: np.ndarray) -> float:
        z = float(self.w @ hidden) + self.b
        return float(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))

    def update(self, hidden: np.ndarray, truth: bool) -> float:
        p = self.predict(hidden)
        grad = p - float(truth)
        self.w -= PROBE_LR * grad * hidden
        self.b -= PROBE_LR * grad
        correct = (p >= 0.5) == bool(truth)
        self.accuracy = (PROBE_ACC_DECAY * self.accuracy
                         + (1 - PROBE_ACC_DECAY) * float(correct))
        self.observations += 1
        return p


class HiveMindMonitor:
    """Per-colony translation layer: probes, thoughts, decision log."""

    def __init__(self, colony_id: int):
        self.colony_id = colony_id
        self.probes: Dict[str, ConceptProbe] = {
            seed: ConceptProbe() for seed in ANCHOR_SEEDS}
        self.decisions: deque = deque(maxlen=DECISION_LOG_LEN)

    def observe_neural(self, unit, colony, sim, hidden: np.ndarray) -> str:
        """Probe update + decoded thought for a neural soldier (M2/M3).

        The thought is cached on `unit.thought` (dies with the unit).
        """
        ctx = build_context(unit, colony, sim)
        truths = ground_truths(ctx)
        emitted: List[Tuple[float, str]] = []
        for seed in ANCHOR_SEEDS:
            # setdefault: monitors resumed from before a lexicon growth (M10)
            probe = self.probes.setdefault(seed, ConceptProbe())
            p = probe.update(hidden, truths[seed])
            if p >= THOUGHT_MIN_P and probe.accuracy >= THOUGHT_MIN_ACC:
                emitted.append((p, seed))
        emitted.sort(reverse=True)
        words = [word_for(seed, p) for p, seed in emitted]
        unit.thought = " ".join(words) if words else "..."
        return unit.thought

    def observe_instincts(self, unit, colony, sim) -> str:
        """Instinct caching for rule-based units / non-soldiers (M3)."""
        active = instincts_for(unit, colony, sim)
        unit.thought = " ".join(active) if active else "..."
        return unit.thought

    def log_decision(self, step: int, actor: str, event: str,
                     thought: Optional[str] = None) -> None:
        self.decisions.append((step, actor, event, thought or "..."))

    def colony_thought(self, sim, colony) -> str:
        """Aggregate mood: the three most widely active anchors right now."""
        counts = {seed: 0 for seed in ANCHOR_SEEDS}
        for unit in colony.units:
            truths = ground_truths(build_context(unit, colony, sim))
            for seed in ANCHOR_SEEDS:
                counts[seed] += int(truths[seed])
        active = [(n, s) for s, n in counts.items() if n > 0]
        active.sort(reverse=True)
        return " ".join(s for _, s in active[:3]) or "..."

    def concept_rows(self, sim, colony) -> List[Tuple[str, float, int]]:
        """(anchor, probe accuracy, currently-active count) for the manager."""
        counts = {seed: 0 for seed in ANCHOR_SEEDS}
        for unit in colony.units:
            truths = ground_truths(build_context(unit, colony, sim))
            for seed in ANCHOR_SEEDS:
                counts[seed] += int(truths[seed])
        return [(seed, self.probes.setdefault(seed, ConceptProbe()).accuracy,
                 counts[seed])
                for seed in ANCHOR_SEEDS]
