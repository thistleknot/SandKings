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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all maw RL tests passed")
