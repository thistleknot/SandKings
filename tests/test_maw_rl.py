"""Acceptance tests for maw_brain.MawPolicy (the real-RL maw head, 85% tier).

Failure modes covered: policy fails to learn (dead gradient / wrong sign), directive
out of bounds, deterministic act drawing noise, non-picklable policy, and the
identity-at-neutral gate default.

The learning test is the make-or-break: on a toy objective (reward = -||directive - target||^2)
a correct REINFORCE implementation must move the deterministic directive measurably toward
the target. Stochastic, so seeded and asserted as *improvement*, not exact convergence.
Skips cleanly if torch is unavailable.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    from maw_brain import MawPolicy, MAW_RL_ENABLED, MAW_DIRECTIVE_DIM
    HAVE_TORCH = True
except Exception:
    HAVE_TORCH = False


def _skip():
    print("SKIP (torch unavailable)")
    return True


def test_gate_default_off():
    # Identity-at-neutral: the sim must never build/run a policy at neutral.
    if not HAVE_TORCH:
        return _skip()
    assert MAW_RL_ENABLED is False, "MAW_RL_ENABLED must default False (byte-identical battery)"


def test_directive_bounded_and_shaped():
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(0)
    p = MawPolicy(obs_dim=32)
    obs = torch.randn(32)
    d, lp = p.act(obs)
    assert d.shape == (MAW_DIRECTIVE_DIM,)
    assert torch.all(d > 0) and torch.all(d < 1), "directive must be in (0,1)"
    assert torch.isfinite(d).all() and torch.isfinite(lp).all()
    # batched
    db, lpb = p.act(torch.randn(4, 32))
    assert db.shape == (4, MAW_DIRECTIVE_DIM)


def test_deterministic_draws_no_noise():
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(1)
    p = MawPolicy(obs_dim=8)
    obs = torch.randn(8)
    d1, lp1 = p.act(obs, deterministic=True)
    d2, lp2 = p.act(obs, deterministic=True)
    assert torch.equal(d1, d2), "deterministic act must be reproducible (no sampling)"
    assert float(lp1) == 0.0 and float(lp2) == 0.0


def test_policy_learns_toy_objective():
    """REINFORCE must push the directive toward a fixed target on a dense reward."""
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(7)
    obs_dim = 4
    p = MawPolicy(obs_dim=obs_dim, directive_dim=3)
    opt = p.make_optimizer(lr=5e-2)
    obs = torch.ones(obs_dim)                      # fixed context
    target = torch.tensor([0.9, 0.1, 0.5])

    def dist_to_target():
        d, _ = p.act(obs, deterministic=True)
        return float(torch.mean((d.detach() - target) ** 2))

    start = dist_to_target()
    K = 32                                          # episodes per batch-REINFORCE update
    for _ in range(200):
        lps, rs = [], []
        for _ in range(K):
            d, lp = p.act(obs)                      # sample (d already detached)
            rs.append(-float(torch.mean((d - target) ** 2)))
            lps.append(lp)
        p.update(lps, rs, opt)
    end = dist_to_target()
    assert end < start * 0.4, f"policy failed to learn: start={start:.4f} end={end:.4f}"


def test_update_changes_params():
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(3)
    p = MawPolicy(obs_dim=6, directive_dim=2)
    opt = p.make_optimizer()
    before = [q.detach().clone() for q in p.parameters()]
    d1, lp1 = p.act(torch.randn(6))
    d2, lp2 = p.act(torch.randn(6))
    p.update([lp1, lp2], [1.0, -1.0], optimizer=opt)   # differing rewards -> nonzero advantage
    after = list(p.parameters())
    assert any(not torch.equal(b, a) for b, a in zip(before, after)), "update must change params"


def test_policy_pickles():
    if not HAVE_TORCH:
        return _skip()
    import pickle
    p = MawPolicy(obs_dim=10)
    revived = pickle.loads(pickle.dumps(p))
    d, _ = revived.act(torch.randn(10), deterministic=True)
    assert d.shape == (MAW_DIRECTIVE_DIM,)


def test_apply_directive_identity_and_tilt():
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import apply_directive
    probs = torch.tensor([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.4])   # 7 actions, sums to 1
    neutral = torch.full((MAW_DIRECTIVE_DIM,), 0.5)
    out = apply_directive(probs, neutral)
    assert torch.allclose(out, probs, atol=1e-6), "directive 0.5 must be identity"
    aggr = neutral.clone(); aggr[0] = 0.95
    out2 = apply_directive(probs, aggr)
    assert out2[6] > probs[6], "high aggression must raise the attack prob"
    assert abs(float(out2.sum()) - 1.0) < 1e-5, "stays a distribution"
    # batched
    pb = probs.unsqueeze(0).repeat(3, 1)
    ob = apply_directive(pb, aggr)
    assert ob.shape == (3, 7) and torch.allclose(ob.sum(-1), torch.ones(3), atol=1e-5)


def test_colony_maw_rl_learns():
    """The per-colony two-timescale wrapper learns over cycles (act/observe/update loop)."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL
    torch.manual_seed(5)
    rl = ColonyMawRL(obs_dim=4, update_every=8)
    obs = torch.ones(4)
    target = torch.full((MAW_DIRECTIVE_DIM,), 0.8)

    def dist():
        d, _ = rl.policy.act(obs, deterministic=True)
        return float(torch.mean((d - target) ** 2))

    start = dist()
    reward = 0.0
    for _ in range(8 * 60):                     # 480 cycles -> ~60 updates
        rl.observe_reward(reward)
        d = rl.act(obs)
        reward = -float(torch.mean((d - target) ** 2))
    end = dist()
    assert rl.updates >= 50, f"expected ~60 updates, got {rl.updates}"
    assert end < start * 0.5, f"colony maw RL failed to learn: {start:.4f}->{end:.4f}"


def test_colony_maw_rl_pickles():
    if not HAVE_TORCH:
        return _skip()
    import pickle
    from maw_brain import ColonyMawRL
    rl = ColonyMawRL(obs_dim=8, update_every=4)
    rl.act(torch.randn(8))                      # creates a pending grad tensor
    revived = pickle.loads(pickle.dumps(rl))    # __getstate__ must drop it cleanly
    revived.observe_reward(1.0)
    d = revived.act(torch.randn(8))
    assert d.shape == (MAW_DIRECTIVE_DIM,)


def test_reinforce_signsgd_learns():
    """signSGD mode (sign-quantized gradient) still converges on the toy objective."""
    if not HAVE_TORCH:
        return _skip()
    import maw_brain
    torch.manual_seed(11)
    p = MawPolicy(obs_dim=4, directive_dim=3)
    opt = p.make_optimizer(lr=5e-2)
    obs = torch.ones(4)
    target = torch.tensor([0.9, 0.1, 0.5])

    def dist():
        d, _ = p.act(obs, deterministic=True)
        return float(torch.mean((d - target) ** 2))

    start = dist()
    prev = maw_brain.MAW_SIGN_SGD
    maw_brain.MAW_SIGN_SGD = True
    try:
        for _ in range(250):
            lps, rs = [], []
            for _ in range(32):
                d, lp = p.act(obs)
                rs.append(-float(torch.mean((d - target) ** 2)))
                lps.append(lp)
            p.update(lps, rs, opt)
    finally:
        maw_brain.MAW_SIGN_SGD = prev
    end = dist()
    assert end < start * 0.6, f"signSGD failed to learn: {start:.4f}->{end:.4f}"


def test_colony_spawn_rl_multi_update():
    """Reproduces the cross-update stale-pending autograd bug: many units, many updates."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonySpawnRL
    torch.manual_seed(4)
    srl = ColonySpawnRL(enc_dim=8, update_every=8)

    class U:
        pass

    units = [U() for _ in range(5)]                  # distinct id() per unit
    perf = {id(u): 0.0 for u in units}
    for _ in range(200):
        for u in units:
            res = srl.act(u, torch.randn(8), perf[id(u)])   # must not raise
            perf[id(u)] += 0.01
            assert res.abs().max() <= srl.policy.clip + 1e-5
    assert srl.updates >= 3, f"expected several updates, got {srl.updates}"


def test_apply_residual_identity():
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import apply_residual
    probs = torch.tensor([0.2, 0.1, 0.1, 0.2, 0.1, 0.1, 0.2])
    out = apply_residual(probs, torch.zeros(7))
    assert torch.allclose(out, probs, atol=1e-6), "zero residual must be identity"


def test_spawn_residual_bounded_and_identity():
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import SpawnResidualPolicy
    torch.manual_seed(2)
    p = SpawnResidualPolicy(enc_dim=8)
    res_det, lp = p.act(torch.randn(8), deterministic=True)
    assert torch.allclose(res_det, torch.zeros(7), atol=1e-6), "zero-init deterministic = identity"
    assert float(lp) == 0.0
    res, _ = p.act(torch.randn(8))                       # sampled
    assert torch.all(res.abs() <= p.clip + 1e-5), "residual must stay within +/-clip"


def test_spawn_residual_learns():
    """Shared spawn residual learns by batch-REINFORCE on a local reward."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import SpawnResidualPolicy
    torch.manual_seed(9)
    p = SpawnResidualPolicy(enc_dim=8)
    opt = p.make_optimizer(lr=5e-2)
    enc = torch.ones(8)

    def det_r3():
        res, _ = p.act(enc, deterministic=True)
        return float(res[3])

    start = det_r3()
    K = 32
    for _ in range(150):
        lps, rs = [], []
        for _ in range(K):
            res, lp = p.act(enc)
            rs.append(float(res[3]))                    # reward = residual on action 3
            lps.append(lp)
        p.update(lps, rs, opt)
    end = det_r3()
    assert end > start + 0.02, f"spawn residual failed to learn: {start:.3f}->{end:.3f}"
    res, _ = p.act(enc)
    assert torch.all(res.abs() <= p.clip + 1e-5), "residual stays bounded after training"


def test_warm_start_matches_instinct():
    """Warm-start ('never tabula rasa'): the untrained deterministic directive EQUALS the
    genome instinct vector, independent of obs (zero final weights + logit bias)."""
    if not HAVE_TORCH:
        return _skip()
    ws = torch.tensor([0.9, 0.2, 0.6])                 # aggression, mobility, verticality
    p = MawPolicy(obs_dim=5, directive_dim=3, warm_start=ws)
    for _ in range(4):
        d, _ = p.act(torch.randn(5), deterministic=True)
        assert torch.allclose(d, ws, atol=1e-4), f"warm-start not honored: {d} vs {ws}"


def test_entropy_bonus_resists_collapse():
    """With CONSTANT rewards the RLOO advantage is 0, so only the entropy bonus drives the
    update — it must LIFT log_std (sustained exploration, the anti-collapse guarantee)."""
    if not HAVE_TORCH:
        return _skip()
    torch.manual_seed(13)
    p = MawPolicy(obs_dim=4, directive_dim=3)
    opt = p.make_optimizer(lr=0.1)
    ls0 = float(p.log_std.mean())
    obs = torch.ones(4)
    for _ in range(20):
        lps = [p.act(obs)[1] for _ in range(8)]
        p.update(lps, [1.0] * 8, opt)                  # constant reward -> zero advantage
    assert float(p.log_std.mean()) > ls0, "entropy bonus failed to raise exploration"


def test_maw_dream_consolidates_elites():
    """Dreaming (elite self-distillation) moves the deterministic directive TOWARD the high-reward
    memories and must NOT touch log_std (exploration preserved)."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL
    torch.manual_seed(21)
    rl = ColonyMawRL(obs_dim=4)
    obs = torch.ones(4)
    target = torch.full((MAW_DIRECTIVE_DIM,), 0.85)
    for _ in range(8):                                        # elites AT target, distractors away
        rl._mem.append((obs.clone(), target.clone(), 5.0))
        rl._mem.append((obs.clone(), torch.full((MAW_DIRECTIVE_DIM,), 0.15), -5.0))
    before = float(torch.mean((rl.policy.act(obs, deterministic=True)[0] - target) ** 2))
    ls_before = rl.policy.log_std.detach().clone()
    for _ in range(20):
        rl.dream()
    after = float(torch.mean((rl.policy.act(obs, deterministic=True)[0] - target) ** 2))
    assert after < before, f"dream failed to consolidate toward elites: {before:.4f}->{after:.4f}"
    assert rl.dreams == 20
    assert torch.equal(rl.policy.log_std, ls_before), "dreaming must not change log_std"


def test_dream_mid_pg_batch_no_stale_graph():
    """Repro (live-run bug): dreaming mutates policy weights while on-policy PG log_probs are pending;
    a subsequent PG update must NOT raise the stale-graph autograd error (dream drops the PG buffer)."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL, MAW_DREAM_TOPK
    torch.manual_seed(31)
    rl = ColonyMawRL(obs_dim=4, update_every=8)
    r = 0.0
    dreamed = False
    for i in range(30):
        rl.observe_reward(r)
        d = rl.act(torch.randn(4))
        r = float(d.sum())
        if not dreamed and len(rl._mem) >= MAW_DREAM_TOPK:
            rl.dream()                       # mid-stream dream while a PG batch is partially accumulated
            dreamed = True
    for _ in range(30):                       # keep running -> PG update() fires; must not raise
        rl.observe_reward(r); d = rl.act(torch.randn(4)); r = float(d.sum())
    assert dreamed and rl.updates >= 1 and rl.dreams >= 1


def test_maw_dream_noop_when_insufficient():
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL
    rl = ColonyMawRL(obs_dim=4)
    assert rl.dream() is None and rl.dreams == 0, "dream must no-op below MAW_DREAM_TOPK memories"


def test_maw_memory_ring_and_dream_through_cycle():
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL, MAW_DREAM_BUFFER
    rl = ColonyMawRL(obs_dim=4, update_every=10000)          # high threshold: isolate the memory path
    r = 0.0
    for _ in range(MAW_DREAM_BUFFER + 20):
        rl.observe_reward(r); d = rl.act(torch.randn(4)); r = float(d.sum())
    assert len(rl._mem) == MAW_DREAM_BUFFER, "memory must be a capped ring buffer"
    assert rl.dream() is not None, "enough memories -> dream runs"


def test_colony_maw_rl_pickles_with_memories():
    if not HAVE_TORCH:
        return _skip()
    import pickle
    from maw_brain import ColonyMawRL
    rl = ColonyMawRL(obs_dim=6, update_every=10000)
    r = 0.0
    for _ in range(12):
        rl.observe_reward(r); d = rl.act(torch.randn(6)); r = float(d.sum())
    revived = pickle.loads(pickle.dumps(rl))
    assert len(revived._mem) == len(rl._mem) and revived._pending_mem is None
    revived.dream()                                          # must not raise post-revive


def test_patience_to_gamma_interior_band():
    """patience gene maps into the interior discount band [LO,HI] — never 0 or 1 (chess λ≈0.9)."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import patience_to_gamma, MAW_GAMMA_LO, MAW_GAMMA_HI
    assert abs(patience_to_gamma(0.0) - MAW_GAMMA_LO) < 1e-9
    assert abs(patience_to_gamma(1.0) - MAW_GAMMA_HI) < 1e-9
    mid = patience_to_gamma(0.5)
    assert MAW_GAMMA_LO < mid < MAW_GAMMA_HI, "midpoint must be interior"
    assert patience_to_gamma(0.9) > patience_to_gamma(0.1), "more patience -> larger gamma"
    assert patience_to_gamma(2.0) == MAW_GAMMA_HI and patience_to_gamma(-1.0) == MAW_GAMMA_LO  # clamped


def test_discounted_returns_math():
    """G_t = r_t + gamma*r_{t+1} + ... computed backward over the buffer."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import _discounted_returns
    r = [1.0, 0.0, 2.0]
    g = 0.5
    out = _discounted_returns(r, g)
    assert abs(out[2] - 2.0) < 1e-9
    assert abs(out[1] - (0.0 + 0.5 * 2.0)) < 1e-9          # 1.0
    assert abs(out[0] - (1.0 + 0.5 * 1.0)) < 1e-9          # 1.5
    assert len(_discounted_returns([], g)) == 0


def test_colony_maw_gamma_learns():
    """The maw wrapper still learns the toy objective with discounting on (patient gamma)."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import ColonyMawRL
    torch.manual_seed(6)
    rl = ColonyMawRL(obs_dim=4, update_every=8, gamma=0.9)
    obs = torch.ones(4)
    target = torch.full((MAW_DIRECTIVE_DIM,), 0.3)

    def dist():
        d, _ = rl.policy.act(obs, deterministic=True)
        return float(torch.mean((d - target) ** 2))

    start = dist()
    reward = 0.0
    for _ in range(8 * 60):
        rl.observe_reward(reward)
        d = rl.act(obs)
        reward = -float(torch.mean((d - target) ** 2))
    assert rl.gamma == 0.9 and rl.updates >= 50
    assert dist() < start * 0.6, f"gamma-discounted maw RL failed to learn: {start:.4f}->{dist():.4f}"


def test_apply_directive_verticality():
    """d2 verticality tilts the vertical moves (idx 4,5 = +z,-z); identity at neutral 0.5."""
    if not HAVE_TORCH:
        return _skip()
    from maw_brain import apply_directive
    probs = torch.full((7,), 1.0 / 7.0)
    neutral = torch.full((3,), 0.5)
    assert torch.allclose(apply_directive(probs, neutral), probs, atol=1e-6), "0.5 must be identity"
    vert = neutral.clone(); vert[2] = 0.95
    out = apply_directive(probs, vert)
    assert out[4] > probs[4] and out[5] > probs[5], "high verticality must raise vertical moves"
    assert abs(float(out.sum()) - 1.0) < 1e-5, "stays a distribution"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all maw RL tests passed")
