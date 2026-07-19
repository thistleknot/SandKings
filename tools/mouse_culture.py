"""TWO MOUSE BATTERIES for SPEC_COMPREHENSION_RL — small, seconds, no game. Confirm LIFT before shipping anything.

Battery 1 (maw-RL side): does the comprehension + Maslow(need_met) gate MATERIALLY route learned behavior?
  reward = survival·d[0] + need_met·(floor+k)·d[1].  Expect the learned OBJECTIVE dim d[1] to RISE with comprehension
  k under plenty, and COLLAPSE under famine (need_met=0) — nature > nurture. Survival dim d[0] stays high throughout.

Battery 2 (Tongue side): does TRANSMISSION spread knowledge a colony would NOT otherwise have?
  Colony B learns only concept-set B. A peer transmits concept-set A (B trains on the received triplets via the REAL
  MaskedMind.observe_triplet). Expect B's recovery on set-A concepts to jump from ~chance (never seen) to elevated —
  materially comprehending what it was TAUGHT, not what it discovered. A control B (never taught) stays at chance.

Both are cadence/scale-independent (episodes, not game steps) so they translate. Ship an increment only if its
battery shows lift.
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch
import maw_brain as mb

FLOOR = 0.1   # BOOTSTRAP_FLOOR proxy for the mouse


# ---------------- Battery 1: comprehension + Maslow gate routes the maw objective ----------------
def battery1(episodes=600):
    D = mb.MAW_DIRECTIVE_DIM; OBS = 8

    def arm(need_met, k):
        torch.manual_seed(0); np.random.seed(0)
        rl = mb.ColonyMawRL(obs_dim=OBS, warm_start=torch.full((D,), 0.5))
        obs = torch.zeros(OBS)
        for _ in range(episodes):
            d = rl.act(obs).reshape(-1)[:D]
            surv, obj = float(d[0]), float(d[1])          # d0 = survival lever, d1 = objective lever
            r = surv + need_met * (FLOOR + k) * obj       # SPEC_COMPREHENSION_RL reward
            rl.observe_reward(r)
        d = rl.act(obs).reshape(-1)[:D].detach()
        return float(d[0]), float(d[1])

    plenty_hi = arm(1.0, 1.0)     # plenty + full comprehension  -> should pursue objective
    plenty_lo = arm(1.0, 0.0)     # plenty + illiterate          -> weak objective (floor only)
    famine    = arm(0.0, 1.0)     # famine (Maslow gate shut)    -> survival only, objective collapses
    print("BATTERY 1 — comprehension + Maslow gate (survival d0, objective d1):")
    print(f"  plenty k=1 : survival {plenty_hi[0]:.3f}  objective {plenty_hi[1]:.3f}")
    print(f"  plenty k=0 : survival {plenty_lo[0]:.3f}  objective {plenty_lo[1]:.3f}")
    print(f"  FAMINE     : survival {famine[0]:.3f}  objective {famine[1]:.3f}")
    routes = (plenty_hi[1] > plenty_lo[1] + 0.02) and (plenty_hi[1] > famine[1] + 0.02)
    print("  VERDICT: " + ("LIFT — understanding+plenty raises objective pursuit; famine collapses it to survival "
                           "(nature>nurture confirmed)" if routes else
                           "NO material routing — the gate does not change learned behavior; DO NOT SHIP I1 as-is"))
    return routes


# ---------------- Battery 2: transmission spreads knowledge (real MaskedMind) ----------------
def battery2(train_steps=400):
    from tongue import MaskedMind, _HAVE_TORCH
    from fol_tongue import FOL_ROLE_TOKENS
    if not _HAVE_TORCH:
        print("BATTERY 2 skipped (no torch)"); return True
    VOCAB = ["rain", "feeds", "crop", "sun", "warms", "soil"] + list(FOL_ROLE_TOKENS)
    vid = {w: i for i, w in enumerate(VOCAB)}
    rS, rP, rO = (vid[t] for t in FOL_ROLE_TOKENS)
    setA = (vid["rain"], vid["feeds"], vid["crop"])     # feeds(rain, crop)   — A's tribal knowledge
    setB = (vid["sun"],  vid["warms"], vid["soil"])     # warms(sun, soil)    — B's own knowledge

    def slots(t):
        return [(rS, t[0]), (rP, t[1]), (rO, t[2])]

    def recov(mm, hidden, t):                            # eval comprehension: mean masked-slot recovery over the 3 slots
        ids = [t[0], t[1], t[2]]
        return float(np.mean([mm.recovery(hidden, ids, [ids[j]]) for j in range(3)]))

    def make():
        torch.manual_seed(0); np.random.seed(0)
        mm = MaskedMind(len(VOCAB))
        hidden = torch.randn(mm.head.in_features // 2)
        return mm, hidden

    rng = random.Random(0)
    # TAUGHT colony: learns its own set B, then RECEIVES set A (transmission), trains on it.
    mm, h = make()
    for _ in range(train_steps): mm.observe_triplet(h, slots(setB), rng)
    a_before = recov(mm, h, setA)                       # B has never seen A -> ~chance
    for _ in range(train_steps): mm.observe_triplet(h, slots(setA), rng)   # <-- transmission
    a_after = recov(mm, h, setA)
    # CONTROL colony: same total steps but ALL on set B (never taught A).
    mmc, hc = make()
    for _ in range(train_steps * 2): mmc.observe_triplet(hc, slots(setB), rng)
    a_control = recov(mmc, hc, setA)

    print("BATTERY 2 — transmission spreads knowledge (recovery on set-A concept B never discovered):")
    print(f"  taught  B: set-A recovery  before {a_before:.2f}  ->  after transmission {a_after:.2f}")
    print(f"  control B (never taught A): set-A recovery {a_control:.2f}")
    helped = (a_after > a_before + 0.15) and (a_after > a_control + 0.15)
    print("  VERDICT: " + ("LIFT — B materially comprehends a concept it was TAUGHT, not one it found; "
                           "communication spreads knowledge" if helped else
                           "NO material spread — transmission did not raise comprehension of taught concepts; "
                           "DO NOT SHIP I2 as-is"))
    return helped


if __name__ == "__main__":
    b1 = battery1()
    print()
    b2 = battery2()
    print(f"\n=== SHIP GATE ===  I1(comprehension gate): {'PASS' if b1 else 'FAIL'}   I2(transmission): {'PASS' if b2 else 'FAIL'}")
