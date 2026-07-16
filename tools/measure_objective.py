"""Reproducible objective-metric harness for the maw/spawn RL (see objective.md).

Runs a headless neural sim with the RL gate on, snapshots each colony's directive over time, and
prints the objective.md metrics (I1-I5, G1/G3/G5) as one JSON line. Ungameable: reads the actual
directive tensors + genome, not the drama log. This is the tool behind progress.md's metric rows.

Usage (from the repo root, with a Python 3.10 interpreter):
    python tools/measure_objective.py [STEPS] [SEED]
Defaults: STEPS=1700, SEED=7. Prints "METRICS_JSON {...}".
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np
import torch
import sandkings
from sandkings import SandKingsSimulation, UnitType
from neural_hive import HiveMindBrain, SoldierLayer

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 1700
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 7


def build_sim(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    sandkings.MAW_RL_ENABLED = True
    if os.environ.get("DRQ_LEARNED_BASIS") == "1":   # A/B the learned encoder basis (Bundle 5)
        import neural_hive; neural_hive.LEARNED_BASIS_ENABLED = True
    sim = SandKingsSimulation(width=48, height=32, depth=12, num_colonies=4)
    for c in sim.colonies:
        c.genome.use_neural = True
        if c.genome.brain is None:
            c.genome.brain = HiveMindBrain()
        for u in c.units:
            if u.unit_type == UnitType.SOLDIER and getattr(u, 'brain_layer', None) is None:
                u.brain_layer = SoldierLayer(); u.brain_layer.steps_alive = 0
    return sim


def pairwise_div(dmap):
    ids = [k for k in dmap if dmap[k]]
    if len(ids) < 2:
        return 0.0
    ds = [np.array(dmap[i]) for i in ids]
    tot, n = 0.0, 0
    for i in range(len(ds)):
        for j in range(i + 1, len(ds)):
            tot += float(np.linalg.norm(ds[i] - ds[j])); n += 1
    return tot / n if n else 0.0


def main():
    sim = build_sim(SEED)
    instincts = {c.colony_id: (float(getattr(c.genome, 'aggression', .5)),
                               float(getattr(c.genome, 'expansion_rate', .5)),
                               float(getattr(c.genome, 'tunnel_preference', .5)))
                 for c in sim.colonies}
    snaps, levels = [], []
    events0 = len(getattr(sim, 'events', []))

    def grab():
        d = {}
        for c in sim.colonies:
            v = getattr(c, 'maw_directive', None)
            if v is not None:
                d[c.colony_id] = [float(x) for x in v.reshape(-1)]
        return d

    for step in range(STEPS):
        sim.step()
        if step % 100 == 99:
            snaps.append(grab())
            levels.append((step, {c.colony_id: float(getattr(c, '_maw_rl_prev', 0.0))
                                  for c in sim.colonies}))

    final = snaps[-1] if snaps else {}
    mid = snaps[len(snaps) // 2] if snaps else {}
    I2 = pairwise_div(final)
    I3 = float(np.mean([abs(x - 0.5) for v in final.values() for x in v])) if final else 0.0
    div_mid = pairwise_div(mid)
    I5 = (I2 / div_mid) if div_mid > 1e-9 else None
    if len(levels) >= 2:
        xs = np.array([s for s, _ in levels], float)
        ys = np.array([np.mean(list(m.values())) for _, m in levels], float)
        I1 = float(np.polyfit(xs, ys, 1)[0])
    else:
        I1 = None
    first = snaps[0] if snaps else {}
    pairs = [(first[cid][:3], list(instincts[cid])) for cid in first
             if cid in instincts and len(first[cid]) >= 3]
    if pairs:
        a = np.array([p[0] for p in pairs]).reshape(-1)
        b = np.array([p[1] for p in pairs]).reshape(-1)
        G5 = float(np.corrcoef(a, b)[0, 1]) if a.std() > 1e-9 and b.std() > 1e-9 else None
    else:
        G5 = None
    events = len(getattr(sim, 'events', [])) - events0
    out = {
        "steps": STEPS, "seed": SEED,
        "I1_reward_trend_slope": round(I1, 5) if I1 is not None else None,
        "I2_divergence_end": round(I2, 4),
        "I3_expressiveness": round(I3, 4),
        "I5_anticollapse_ratio": round(I5, 3) if I5 is not None else None,
        "I4_updates": {c.colony_id: (getattr(getattr(c, 'maw_rl', None), 'updates', 0),
                                     getattr(getattr(c, 'spawn_rl', None), 'updates', 0))
                       for c in sim.colonies},
        "G1_alive": sum(1 for c in sim.colonies if getattr(c.maw, 'alive', False)),
        "G3_events_per_100": round(events / (STEPS / 100.0), 2),
        "G5_personality_corr_early": round(G5, 3) if G5 is not None else None,
        "any_nan": any(any(x != x for x in v) for v in final.values()),
    }
    print("METRICS_JSON " + json.dumps(out))


if __name__ == "__main__":
    main()
