"""MOUSE MODEL for the maw-RL — the controlled, accelerated test the game can't give us fast.

Principle (test-in-mice): isolate the REAL ColonyMawRL, feed it updates at FULL rate in a controlled bandit, and
measure LEARNING vs NUMBER OF UPDATES. That curve is cadence-independent — it's a property of the learner (lr,
variance, arch), NOT of wall-clock steps — so it TRANSLATES: whatever K updates the mouse needs to learn, the game
needs the SAME K updates, however many steps that takes at its cadence.

Reads out:
  - K = updates to reach 90% of the learnable optimum (the mouse's answer).
  - Translation: in-game the maw gets 1 update / (MAW_UPDATE_EVERY * POP_TICK_INTERVAL) steps, so K updates need
    K * that-many steps at the current cadence — and what the cadence must become to fit K updates in a normal game.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

torch.manual_seed(0); np.random.seed(0)
D = mb.MAW_DIRECTIVE_DIM
OBS = 8
warm = torch.full((D,), 0.5)
rl = mb.ColonyMawRL(obs_dim=OBS, warm_start=warm)
obs = torch.zeros(OBS)

# Controlled bandit: reward = mean of the directive (push ALL dims up toward 1.0). Learnable optimum = 1.0.
MAX_UPDATES = 1500
perf = []                                    # (update_idx, mean-directive-this-batch) = normalized performance in [0,1]
batch = []
c = 0
while rl.updates < MAX_UPDATES and c < MAX_UPDATES * mb.MAW_UPDATE_EVERY * 3:
    d = rl.act(obs).reshape(-1)[:D]
    r = float(d.mean())                      # optimum = 1.0
    batch.append(r)
    prev = rl.updates
    rl.observe_reward(r)
    if rl.updates > prev:
        perf.append((rl.updates, float(np.mean(batch)))); batch = []
    c += 1

us = np.array([u for u, _ in perf]); ys = np.array([p for _, p in perf])
base = ys[0]                                  # start (~0.5 warm-start)
opt = 1.0
def frac(y): return (y - base) / (opt - base + 1e-9)
K90 = next((int(u) for u, y in perf if frac(y) >= 0.90), None)   # updates to 90% of learnable gain
K50 = next((int(u) for u, y in perf if frac(y) >= 0.50), None)

print("MOUSE MODEL — maw-RL update-efficiency (real ColonyMawRL, full-rate updates)")
print(f"directive mean: start {base:.3f} -> end {ys[-1]:.3f}  (optimum 1.0)")
print("update :  perf   frac-of-optimum")
for i in range(0, len(perf), max(1, len(perf) // 12)):
    u, y = perf[i]
    print(f"  {u:4d}  : {y:.3f}   {frac(y)*100:4.0f}%   {'#'*int(frac(y)*40)}")
print(f"\nK50 (updates to 50% of learnable gain): {K50}")
print(f"K90 (updates to 90% of learnable gain): {K90}")

# ---- TRANSLATION to the game (cadence-independent update count) ----
try:
    import importlib, sandkings
    POP = getattr(sandkings, 'POP_TICK_INTERVAL', 50)
except Exception:
    POP = 50
steps_per_update = mb.MAW_UPDATE_EVERY * POP
K = K90 or MAX_UPDATES
print(f"\nTRANSLATION (the leap that makes the mouse worth it):")
print(f"  in-game cadence NOW: 1 update / (MAW_UPDATE_EVERY {mb.MAW_UPDATE_EVERY} * POP_TICK_INTERVAL {POP}) = {steps_per_update} steps/update")
print(f"  a normal game ~1700 steps => {1700//steps_per_update} updates  (mouse says it needs ~{K}) => {'STARVED' if (1700//steps_per_update) < K else 'ENOUGH'}")
print(f"  to give the maw K={K} updates within 1700 steps, cadence must drop to ~{max(1,1700//max(K,1))} steps/update")
print(f"  e.g. MAW_UPDATE_EVERY=2, POP_TICK_INTERVAL=10 => {2*10} steps/update => {1700//(2*10)} updates/game "
      f"({'ENOUGH' if 1700//(2*10) >= K else 'still short'})")
