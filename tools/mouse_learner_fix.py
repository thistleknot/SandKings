"""MOUSE — cheapest learner fix for the sample-inefficient maw-RL. Minutes, not hours.

The maw-RL is variance-bound (H2). Two ZERO-new-network levers, ordered cheapest-first:
  lr   : bigger step / update  (FREE — same #updates, same compute)
  B    : bigger parallel batch (variance ~1/B, costs B episodes/update)
Fixed small episode budget per arm (equal compute). Metric: fraction-of-optimum reached + episodes-to-25%-lift.
Pick the least-overhead arm that clears a real lift; only build a critic if lr+batch can't.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

D = mb.MAW_DIRECTIVE_DIM; OBS = 8
BUDGET = 3000                     # episodes/arm — mouse-sized
ARMS = [("base    lr3e-3 B8",  3e-3,  8),
        ("+lr     lr3e-2 B8",  3e-2,  8),
        ("+lr+    lr1e-1 B8",  1e-1,  8),
        ("+batch  lr3e-3 B64", 3e-3, 64),
        ("+both   lr3e-2 B64", 3e-2, 64)]


def run(lr, B):
    torch.manual_seed(0); np.random.seed(0)
    rl = mb.ColonyMawRL(obs_dim=OBS, update_every=B, warm_start=torch.full((D,), 0.5), lr=lr)
    obs = torch.zeros(OBS)
    recent, curve, base = [], [], None
    for ep in range(BUDGET):
        d = rl.act(obs).reshape(-1)[:D]
        rl.observe_reward(float(d.mean()))          # optimum 1.0
        recent.append(float(d.mean()))
        if len(recent) >= 150:
            p = float(np.mean(recent[-150:]))
            if base is None: base = p
            curve.append((ep, (p - base) / (1.0 - base + 1e-9)))
    final = curve[-1][1] if curve else 0.0
    ep25 = next((e for e, f in curve if f >= 0.25), None)
    return final, ep25


print(f"MOUSE — maw-RL learner fix  (budget {BUDGET} episodes/arm)")
print(f"{'arm':22} {'final_frac':>11} {'ep->25%lift':>12}")
best = None
for name, lr, B in ARMS:
    final, ep25 = run(lr, B)
    tag = f"{ep25}" if ep25 else ">budget"
    print(f"{name:22} {final:>11.3f} {tag:>12}")
    if ep25 is not None and (best is None or ep25 < best[1]):
        best = (name, ep25, final)
print("\n--- verdict ---")
if best:
    print(f"Cheapest confirmed lift: {best[0].strip()} -> 25% in {best[1]} episodes (final {best[2]:.2f}).")
    print("If '+lr' alone clears it, that's a FREE fix (no extra compute) — ship that before batching/critic.")
else:
    print("No lr/batch arm cleared 25% within budget -> the levers aren't enough; a CRITIC (A2C/PPO baseline) is the "
          "next test. But check the 'final_frac' column: if it's rising with lr/B, just raise the budget.")
