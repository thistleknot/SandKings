"""FAST H1 probe (~150 steps, seconds): is the maw-RL actually LEARNING beyond its warm-start instinct, or just
tracking it? The final-fitness ablation is slow+noisy because the RL warm-starts AT the baseline and needs many
steps to diverge. This measures the DYNAMICS directly instead of the endpoint:

  - reward_slope : per-step trend of the maw reward (`_maw_rl_prev`). > 0 ⇒ the policy is improving on its objective.
  - directive_drift : mean |maw_directive - genome instinct|. > 0 and growing ⇒ the policy has MOVED off warm-start.
  - updates : REINFORCE updates actually applied (0 ⇒ the RL never learned; machinery dead).
  - fitness Δ (RL-on - RL-off), same seed : the endpoint, shown for reference (expected ~0 at short horizon).

Verdict leans H1 (real RL) if reward_slope > 0 AND directive drifts AND updates > 0; leans H2 (instinct only) if the
policy never moves off warm-start. Honest: short horizon, single seed — a dynamics read, not the settled outcome.
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch, sandkings
from sandkings import SandKingsSimulation, UnitType
from neural_hive import HiveMindBrain, SoldierLayer

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 150
SEED = 7


def build(rl_on):
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    sandkings.MAW_RL_ENABLED = rl_on
    sim = SandKingsSimulation(width=48, height=32, depth=12, num_colonies=4)
    for c in sim.colonies:
        c.genome.use_neural = True
        if c.genome.brain is None:
            c.genome.brain = HiveMindBrain()
        for u in c.units:
            if u.unit_type == UnitType.SOLDIER and getattr(u, 'brain_layer', None) is None:
                u.brain_layer = SoldierLayer(); u.brain_layer.steps_alive = 0
    return sim


def fitness(sim):
    return float(np.mean([len(c.units) + c.maw.food_stored/50.0
                          + len(getattr(c, 'territory', ()))/100.0 + (2.0 if c.maw.alive else 0.0)
                          for c in sim.colonies]))


def run(rl_on):
    sim = build(rl_on)
    instinct = {c.colony_id: np.array([float(getattr(c.genome, 'aggression', .5)),
                                       float(getattr(c.genome, 'expansion_rate', .5)),
                                       float(getattr(c.genome, 'tunnel_preference', .5))]) for c in sim.colonies}
    rewards, drifts = [], []
    for _ in range(STEPS):
        sim.step()
        rewards.append(float(np.mean([float(getattr(c, '_maw_rl_prev', 0.0)) for c in sim.colonies])))
        d = []
        for c in sim.colonies:
            v = getattr(c, 'maw_directive', None)
            if v is not None:
                d.append(float(np.mean(np.abs(np.asarray(v).reshape(-1)[:3] - instinct[c.colony_id]))))
        drifts.append(float(np.mean(d)) if d else 0.0)
    xs = np.arange(len(rewards), dtype=float)
    slope = float(np.polyfit(xs, rewards, 1)[0]) if len(rewards) >= 2 else None
    updates = sum(getattr(getattr(c, 'maw_rl', None), 'updates', 0) for c in sim.colonies)
    return dict(fit=fitness(sim), slope=slope, drift_end=drifts[-1] if drifts else 0.0,
                drift_start=drifts[0] if drifts else 0.0, updates=updates)


on = run(True); off = run(False)
print(f"STEPS={STEPS} seed={SEED}")
print(f"RL-on : fitness {on['fit']:.2f}  reward_slope {on['slope']:+.3e}  directive_drift {on['drift_start']:.3f}->{on['drift_end']:.3f}  updates {on['updates']}")
print(f"RL-off: fitness {off['fit']:.2f}  (frozen warm-start; updates {off['updates']})")
print(f"fitness d (on-off) {on['fit']-off['fit']:+.2f}")
learning = (on['slope'] is not None and on['slope'] > 0) and (on['drift_end'] > on['drift_start']) and on['updates'] > 0
print("VERDICT: " + ("RL is LEARNING (reward up + policy moved off warm-start + updates applied) -> leans H1"
                     if learning else
                     "RL policy did NOT clearly move off warm-start at this horizon -> leans H2 / inconclusive"))
