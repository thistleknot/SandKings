"""MOUSE SWEEP for H1 — does PARALLEL data collection (bigger batch per update) buy confirmed lift at least compute?

The maw-RL is sample-inefficient because REINFORCE gradient variance ~ 1/batch. The keeper's lever: collect RL data
at MORE points IN PARALLEL (N colonies / parallel sims pooling into ONE shared policy) => bigger effective batch per
update => lower-variance gradient => FEWER updates to a lift. But each update costs B episodes, so the real question
is the efficient frontier: which B reaches a confirmed lift with the LEAST TOTAL COMPUTE (episodes = forward/backward).

Controlled: real ColonyMawRL, `update_every = B` (B parallel data points per update). Same learnable bandit
(maximize directive mean; optimum 1.0). Fixed COMPUTE budget per arm (equal total episodes) so arms are compared at
equal overhead. Metric: fraction-of-optimum reached, and episodes-to-25%-lift (compute-to-confirmed-lift). Scale/
cadence-independent (episodes, not steps) so it TRANSLATES: in-game, B parallel actors give B episodes per act-cycle.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

D = mb.MAW_DIRECTIVE_DIM
OBS = 8
BUDGET_EPISODES = 24000                     # equal compute per arm
BATCHES = [8, 16, 32, 64, 128, 256]         # parallel-collection points per update (B)
THRESH = 0.25                               # "confirmed lift" = 25% of the learnable gain (90% is out of budget)


def run_arm(B, seed=0):
    torch.manual_seed(seed); np.random.seed(seed)
    warm = torch.full((D,), 0.5)
    rl = mb.ColonyMawRL(obs_dim=OBS, update_every=B, warm_start=warm)
    obs = torch.zeros(OBS)
    base = None
    curve = []                              # (total_episodes, fraction_of_optimum)
    ep = 0
    recent = []
    while ep < BUDGET_EPISODES:
        d = rl.act(obs).reshape(-1)[:D]
        r = float(d.mean())                 # optimum 1.0
        recent.append(r)
        rl.observe_reward(r); ep += 1
        if len(recent) >= 200:
            perf = float(np.mean(recent[-200:]))
            if base is None:
                base = perf
            curve.append((ep, (perf - base) / (1.0 - base + 1e-9)))
    ep_to_thresh = next((e for e, f in curve if f >= THRESH), None)
    final = curve[-1][1] if curve else 0.0
    return dict(B=B, updates=rl.updates, final_frac=final, ep_to_thresh=ep_to_thresh)


print(f"MOUSE SWEEP — parallel-collection batch B vs lift & compute  (budget={BUDGET_EPISODES} episodes/arm)")
print(f"{'B':>5} {'updates':>8} {'final_frac':>11} {'episodes->25%lift':>18}  efficiency")
rows = []
for B in BATCHES:
    r = run_arm(B)
    rows.append(r)
    eff = f"{r['ep_to_thresh']} ep" if r['ep_to_thresh'] else ">budget (no 25% lift)"
    print(f"{B:>5} {r['updates']:>8} {r['final_frac']:>11.3f} {str(r['ep_to_thresh'] or '-'):>18}  {eff}")

reached = [r for r in rows if r['ep_to_thresh'] is not None]
print("\n--- verdict ---")
if reached:
    best = min(reached, key=lambda r: r['ep_to_thresh'])
    print(f"CONFIRMED LIFT is reachable. Most compute-efficient: B={best['B']} hits 25% lift in {best['ep_to_thresh']} episodes "
          f"({best['updates'] if False else best['ep_to_thresh']//best['B']} updates).")
    # in-game translation
    print(f"IN-GAME translation: B parallel actors (colonies/parallel-sims pooling one policy) give B episodes per act-cycle.")
    print(f"  At B={best['B']} you need {best['ep_to_thresh']} episodes = {best['ep_to_thresh']//best['B']} update-cycles.")
    print(f"  With {best['B']} colonies pooling, that's ~{best['ep_to_thresh']//best['B']} act-cycles; at POP_TICK_INTERVAL=50 that's "
          f"~{(best['ep_to_thresh']//best['B'])*50} steps -- vs current ~4 updates/1700 steps.")
else:
    print("No B reached a 25% lift within budget -> parallelism alone is INSUFFICIENT; the learner needs a variance "
          "fix beyond batching (value baseline/critic -> PPO, or higher lr). Batching helps but doesn't close it.")
print("\nRead the frontier: if episodes->25% DROPS then flattens as B grows, that knee is the efficient parallel width.")
