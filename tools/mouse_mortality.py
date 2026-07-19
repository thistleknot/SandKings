"""MORTALITY MOUSE — the fair test for the log-of-experience cadence (die-off is the whole point).

An immortal mouse says "just update as often as possible" (RLOO floor). But colonies DIE OFF, and the log cadence is
FOR that: a young colony updates at the floor so it learns before it dies; an established survivor updates less
(diminishing returns — it has already learned), saving compute. So the honest metric is not lift alone but
LIFT-AT-DEATH vs TOTAL UPDATES (compute) across a die-off lifespan distribution.

Sample colonies with exponential die-off (most die young), run the REAL ColonyMawRL to each one's death on a
target-tracking reward, and compare cadence policies on lift-at-death AND compute. The log wins if it holds ~floor
lift at materially less compute — the balance-objective-with-compute payoff.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

D = mb.MAW_DIRECTIVE_DIM; OBS = 8
TARGET = torch.tensor([0.9, 0.1, 0.5, 0.2, 0.8, 0.3, 0.7])[:D]
N_COLONIES = 48
rng = np.random.RandomState(0)
# exponential die-off in ACTS (maw acts, i.e. POP_TICK cycles); clamp to a sane band. Most die young.
LIFESPANS = np.clip(rng.exponential(20, N_COLONIES).astype(int) + 5, 5, 160)


def run_colony(cadence, lifespan):
    torch.manual_seed(0); np.random.seed(0)
    fixed = None if cadence == 'adaptive' else cadence
    rl = mb.ColonyMawRL(obs_dim=OBS, update_every=(fixed or 8),
                        warm_start=torch.full((D,), 0.5), adaptive_cadence=(cadence == 'adaptive'))
    obs = torch.zeros(OBS)
    dists = []
    for _ in range(lifespan):                       # live `lifespan` acts, then die
        d = rl.act(obs).reshape(-1)[:D]
        rl.observe_reward(-float(((d - TARGET) ** 2).mean()))
        dists.append(float(((d - TARGET) ** 2).mean()))
    start = dists[0]; end = float(np.mean(dists[-3:]))
    lift = (start - end) / (start + 1e-9)
    return lift, rl.updates


print(f"MORTALITY MOUSE — {N_COLONIES} colonies, exponential die-off (median lifespan {int(np.median(LIFESPANS))} acts)")
print(f"{'cadence':16} {'mean lift@death':>15} {'mean updates':>13} {'lift/update':>12}")
res = {}
for cad in [8, 2, 'adaptive']:
    lifts, ups = [], []
    for L in LIFESPANS:
        lf, u = run_colony(cad, int(L))
        lifts.append(lf); ups.append(u)
    ml, mu = float(np.mean(lifts)), float(np.mean(ups))
    res[str(cad)] = (ml, mu)
    name = f"fixed ue={cad}" if cad != 'adaptive' else "ADAPTIVE log(e)"
    print(f"{name:16} {ml:>15.3f} {mu:>13.1f} {ml/max(mu,1e-9):>12.4f}")

la, ua = res['adaptive']; l2, u2 = res['2']
print("\n--- verdict ---")
keeps_lift = la >= l2 - 0.05
saves_compute = ua < u2 * 0.85
if keeps_lift and saves_compute:
    print(f"WIN: adaptive holds ~floor lift ({la:.2f} vs {l2:.2f}) at {100*(1-ua/u2):.0f}% LESS compute "
          f"({ua:.1f} vs {u2:.1f} updates) — die-off front-loading + diminishing-returns saving confirmed.")
elif saves_compute:
    print(f"PARTIAL: adaptive saves {100*(1-ua/u2):.0f}% compute but lift drops ({la:.2f} vs floor {l2:.2f}) — "
          f"a compute/lift trade, not a free win; ship only if the compute matters more than the lift gap.")
else:
    print(f"NO WIN: adaptive ({la:.2f} lift, {ua:.1f} upd) does not beat fixed RLOO-floor ({l2:.2f}, {u2:.1f}) on "
          f"this die-off mix — the fixed floor (a real constant) is the honest choice.")
