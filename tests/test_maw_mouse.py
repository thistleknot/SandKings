"""Mouse-setting regression tests — pin the ISOLATED, cadence-independent behaviours the tools/mouse_*.py studies
established, so a future change that silently breaks the learner (or the culture coupling) fails here in seconds
instead of in a game. Each is a controlled micro-harness on the REAL components (no sim.step). See
[[mouse-model-testing]]. Loose thresholds (well inside the measured margins) so they gate regressions, not noise.
"""
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    import maw_brain as mb
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (no torch)")
    return True


def test_maw_learns_target_bandit():
    """The maw-RL learner is FUNCTIONAL: on an isolated target-tracking bandit (the shape of the real Δsnap reward,
    not a monotone proxy — that trap gave a reckless lr), it reduces distance-to-target with the DEFAULT constants.
    Pins 'the learner works given updates' — the mouse finding under-pinning the H2 disposition."""
    if not HAVE:
        return _skip()
    D = mb.MAW_DIRECTIVE_DIM
    torch.manual_seed(0); np.random.seed(0)
    rl = mb.ColonyMawRL(obs_dim=8, warm_start=torch.full((D,), 0.5))
    obs = torch.zeros(8)
    target = torch.tensor([0.9, 0.1, 0.5, 0.2, 0.8, 0.3, 0.7])[:D]
    dists = []
    for _ in range(800):
        d = rl.act(obs).reshape(-1)[:D]
        rl.observe_reward(-float(((d - target) ** 2).mean()))
        dists.append(float(((d - target) ** 2).mean()))
    start = float(np.mean(dists[:150])); end = float(np.mean(dists[-150:]))
    lift = (start - end) / (start + 1e-9)
    assert lift > 0.15, f"maw-RL failed to learn the target bandit at full update rate: lift {lift:.3f}"


def test_comprehension_gate_routes_objective():
    """SPEC_COMPREHENSION_RL: reward = survival + need_met*(floor+k)*objective routes learned behaviour — objective
    pursuit RISES with comprehension k under plenty and COLLAPSES under famine (need_met=0). Pins the Maslow gate."""
    if not HAVE:
        return _skip()
    D = mb.MAW_DIRECTIVE_DIM
    FLOOR = 0.1

    def obj_dim(need_met, k, episodes=600):
        torch.manual_seed(0); np.random.seed(0)
        rl = mb.ColonyMawRL(obs_dim=8, warm_start=torch.full((D,), 0.5))
        obs = torch.zeros(8)
        for _ in range(episodes):
            d = rl.act(obs).reshape(-1)[:D]
            rl.observe_reward(float(d[0]) + need_met * (FLOOR + k) * float(d[1]))
        return float(rl.act(obs).reshape(-1)[:D][1].detach())

    plenty_hi = obj_dim(1.0, 1.0)
    plenty_lo = obj_dim(1.0, 0.0)
    famine = obj_dim(0.0, 1.0)
    assert plenty_hi > plenty_lo + 0.01, f"comprehension did not raise objective pursuit ({plenty_hi:.3f} vs {plenty_lo:.3f})"
    assert plenty_hi > famine + 0.01, f"famine did not collapse the objective (nature>nurture): {plenty_hi:.3f} vs {famine:.3f}"


def test_transmission_spreads_knowledge():
    """SPEC_COMPREHENSION_RL I2: a colony comprehends a concept it never discovered, only after a peer transmits it
    (trains on the received triplet via MaskedMind.observe_triplet). Pins 'communication materially spreads knowledge'."""
    if not HAVE:
        return _skip()
    from tongue import MaskedMind, _HAVE_TORCH
    from fol_tongue import FOL_ROLE_TOKENS
    if not _HAVE_TORCH:
        return _skip()
    VOCAB = ["rain", "feeds", "crop", "sun", "warms", "soil"] + list(FOL_ROLE_TOKENS)
    vid = {w: i for i, w in enumerate(VOCAB)}
    rS, rP, rO = (vid[t] for t in FOL_ROLE_TOKENS)
    setA = (vid["rain"], vid["feeds"], vid["crop"])
    setB = (vid["sun"], vid["warms"], vid["soil"])

    def slots(t):
        return [(rS, t[0]), (rP, t[1]), (rO, t[2])]

    def recov(mm, h, t):
        ids = [t[0], t[1], t[2]]
        return float(np.mean([mm.recovery(h, ids, [ids[j]]) for j in range(3)]))

    torch.manual_seed(0); np.random.seed(0)
    mm = MaskedMind(len(VOCAB))
    h = torch.randn(mm.head.in_features // 2)
    rng = random.Random(0)
    for _ in range(400):
        mm.observe_triplet(h, slots(setB), rng)
    before = recov(mm, h, setA)                      # never taught A -> ~chance
    for _ in range(400):
        mm.observe_triplet(h, slots(setA), rng)      # transmission
    after = recov(mm, h, setA)
    assert after > before + 0.3, f"transmission did not spread the taught concept: {before:.2f}->{after:.2f}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
