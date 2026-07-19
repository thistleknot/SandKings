"""SPEC_ENSEMBLE_EMBED — the runtime learned mixture. Torch-required (skips without). Pins: gate default off,
relative-representation alignment, missing-npz fallback, the MaskedMind byte-identity anchor (gate off ⇒ plain
nn.Embedding), and that the mixture LEARNS (loss drops, mix.grad nonzero) while the member tables stay FROZEN."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

try:
    import torch
    import ensemble_embed as ee
    import tongue as _tongue
    HAVE = _tongue.MaskedMind is not None
except Exception:
    HAVE = False


def _skip():
    print("SKIP (ensemble_embed unavailable — no torch)")
    return True


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert ee.ENSEMBLE_EMBED_ENABLED is False, "gate off by default (battery byte-identical)"


def test_relative_representation_aligns_heterogeneous_dims():
    """Two members of DIFFERENT raw dims map to the SAME anchor-frame width, L2-normalized → comparable."""
    if not HAVE:
        return _skip()
    rng = np.random.RandomState(0)
    anchors = list(range(8))
    a = ee.relative_representation(rng.randn(20, 50).astype("float32"), anchors)    # GloVe-like 50-d
    b = ee.relative_representation(rng.randn(20, 384).astype("float32"), anchors)   # MiniLM-like 384-d
    assert a.shape == b.shape == (20, 8), "both aligned to (vocab, #anchors)"
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-4), "rows L2-normalized (comparable)"


def test_load_missing_returns_none():
    if not HAVE:
        return _skip()
    assert ee.load_ensemble(os.path.join(os.path.dirname(__file__), "no_such_ensemble.npz")) is None


def test_mixture_forward_shape_and_frozen_members():
    if not HAVE:
        return _skip()
    members = np.random.RandomState(1).randn(3, 12, 32).astype("float32")
    mix = ee.build_mixture(members)
    ids = torch.tensor([0, 5, 11])
    out = mix(ids)
    assert out.shape == (3, 32), "forward returns (len(ids), D)"
    params = {n for n, _ in mix.named_parameters()}
    assert "mix" in params and any("residual" in n for n in params), "mix + residual are learnable"
    assert "members" in dict(mix.named_buffers()), "member tables are a frozen buffer, not a Parameter"


def test_mixture_learns_and_members_stay_frozen():
    """The blend is LEARNED: fitting the mixture to a target drops the loss and produces nonzero mix gradients,
    while the frozen member buffer is never mutated."""
    if not HAVE:
        return _skip()
    torch.manual_seed(0)
    members = torch.randn(3, 10, 32)
    mix = ee.build_mixture(members.numpy())
    before = mix.members.clone()
    target = members[2].clone()                        # the task 'wants' member 2's geometry
    ids = torch.arange(10)
    opt = torch.optim.SGD(mix.parameters(), lr=0.5)
    losses = []
    for _ in range(50):
        opt.zero_grad()
        loss = ((mix(ids) - target) ** 2).mean()
        loss.backward()
        assert mix.mix.grad is not None and mix.mix.grad.abs().sum() > 0, "mix receives gradient"
        opt.step()
        losses.append(loss.item())
    assert losses[-1] < losses[0], f"mixture learns (loss {losses[0]:.3f} -> {losses[-1]:.3f})"
    assert torch.equal(mix.members, before), "member tables stay FROZEN"


def test_maskedmind_byte_identical_off_and_mixture_on():
    """Gate off ⇒ MaskedMind.emb is a plain nn.Embedding (byte-identical); a matching npz + gate on ⇒ a mixture."""
    if not HAVE:
        return _skip()
    ee.ENSEMBLE_EMBED_ENABLED = False
    off = _tongue.MaskedMind(12)
    assert isinstance(off.emb, torch.nn.Embedding), "gate off -> plain random table"

    tmp = os.path.join(os.path.dirname(__file__), "_tmp_ensemble.npz")
    ee.save_ensemble(ee.EnsembleBundle(
        members=np.random.RandomState(2).randn(4, 12, ee.ENSEMBLE_ANCHORS).astype("float32"),
        tokens=[str(i) for i in range(12)], names=["m0", "m1", "m2", "m3"]), tmp)
    old_path, ee.ENSEMBLE_PATH = ee.ENSEMBLE_PATH, tmp
    try:
        ee.ENSEMBLE_EMBED_ENABLED = True
        on = _tongue.MaskedMind(12)
        assert type(on.emb).__name__ == "MixtureEmbedding", "gate on + matching npz -> learned mixture"
    finally:
        ee.ENSEMBLE_EMBED_ENABLED = False
        ee.ENSEMBLE_PATH = old_path
        os.remove(tmp)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all ensemble_embed tests passed")
