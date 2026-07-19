"""TIGHTEST H1 test (~seconds, no sim): can ColonyMawRL's REINFORCE actually LEARN when fed updates at full rate?

Decouples the two questions the in-game ablation tangled:
  (A) CAN the RL learn?  -> this test: rip it out, feed a fixed contextual-bandit reward, update at full rate.
  (B) DOES the sim feed it enough updates? -> arithmetic, already answered: acts every 50 steps, updates every 8
      acts = 1 update / 400 steps = ~4 updates / 1700-step game.

Setup: warm-start the policy to a NEUTRAL instinct (0.5^7), then reward it for emitting a TARGET directive far from
that warm-start. If REINFORCE works, reward rises and the learned directive moves warm-start -> target across
updates. If it stays at warm-start, the learner itself is weak. Either way you get a curve now, not in 20 minutes.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

torch.manual_seed(0); np.random.seed(0)
D = mb.MAW_DIRECTIVE_DIM                       # 7
OBS = 8
warm = torch.full((D,), 0.5)                   # neutral genome instinct
rl = mb.ColonyMawRL(obs_dim=OBS, warm_start=warm)
obs = torch.zeros(OBS)                          # fixed context (bandit)
target = torch.tensor([0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9])[:D]   # far from the 0.5 warm-start

UPDATES_WANTED = 150
curve, batch_r = [], []
c = 0
while rl.updates < UPDATES_WANTED and c < UPDATES_WANTED * mb.MAW_UPDATE_EVERY * 3:
    d = rl.act(obs)
    r = -float(torch.mean(torch.abs(d.reshape(-1)[:D] - target)))   # closeness reward in ~[-0.5, 0]
    batch_r.append(r)
    prev = rl.updates
    rl.observe_reward(r)
    if rl.updates > prev:
        curve.append((rl.updates, float(np.mean(batch_r)))); batch_r = []
    c += 1

learned = rl.act(obs).detach().numpy().reshape(-1)[:D]
print(f"cycles={c}  updates={rl.updates}")
print("update :  mean reward   (curve, higher=closer to target, max 0)")
for i in range(0, len(curve), max(1, len(curve) // 12)):
    u, rr = curve[i]
    bar = "#" * int((rr + 0.5) * 40)
    print(f"  {u:3d}  : {rr:+.3f}  {bar}")
early = np.mean([r for _, r in curve[:5]]) if len(curve) >= 5 else (curve[0][1] if curve else 0)
late = np.mean([r for _, r in curve[-5:]]) if len(curve) >= 5 else (curve[-1][1] if curve else 0)
print(f"\nreward  early {early:+.3f} -> late {late:+.3f}   (rise {late-early:+.3f})")
print(f"warm-start : {[0.5]*D}")
print(f"target     : {target.numpy().round(2).tolist()}")
print(f"learned    : {learned.round(2).tolist()}")
d_warm = float(np.mean(np.abs(learned - 0.5)))
d_tgt = float(np.mean(np.abs(learned - target.numpy())))
print(f"|learned-warm|={d_warm:.3f}  |learned-target|={d_tgt:.3f}  (moved toward target if warm-dist grows, target-dist shrinks)")
learns = (late > early + 0.03) and (d_tgt < d_warm)
print("\nVERDICT: " + ("RL LEARNS at full update rate — machinery is REAL; in-game it's UPDATE-STARVED (~4/game), "
                       "not broken. => H2 is a CADENCE artifact, not a dead learner."
                       if learns else
                       "RL does NOT learn even at full rate — the learner itself is weak/broken (stronger H2)."))
