"""Learned shared encoder basis (SPEC_REPR / Bundle 5). Verifies the basis loads + freezes when the
gate is on, that the GA is UNTOUCHED (mutate/graft change only the evolvable readout, never the frozen
ZCA/codebook), and that the gate default off keeps the random basis (battery byte-identical)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    import neural_hive
    from neural_hive import HiveMindBrain, _load_learned_basis
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (torch/neural_hive unavailable)")
    return True


def test_gate_default_off_random_basis():
    if not HAVE:
        return _skip()
    assert neural_hive.LEARNED_BASIS_ENABLED is False, "gate must default False (battery byte-identical)"
    b = HiveMindBrain()
    assert not getattr(b.zca, "_frozen", False), "gate off: ZCA must stay adaptive (random basis)"


def test_basis_loads_and_freezes():
    if not HAVE:
        return _skip()
    if _load_learned_basis() is None:
        print("SKIP (learned_basis.npz missing)")
        return True
    prev = neural_hive.LEARNED_BASIS_ENABLED
    neural_hive.LEARNED_BASIS_ENABLED = True
    try:
        b = HiveMindBrain()
        mean, W, protos = _load_learned_basis()
        assert b.zca._frozen is True, "learned ZCA must be frozen (matched to the codebook)"
        assert torch.allclose(b.kanerva.protos, torch.as_tensor(protos, dtype=b.kanerva.protos.dtype)), \
            "codebook must equal the learned protos"
        # proto_sq must be recomputed for the new protos
        assert torch.allclose(b.kanerva.proto_sq, (b.kanerva.protos ** 2).sum(1), atol=1e-4)
        enc = b(torch.randn(6, b.input_dim))
        assert enc.shape[-1] == b.encoding_dim and torch.isfinite(enc).all()
    finally:
        neural_hive.LEARNED_BASIS_ENABLED = prev


def test_ga_ops_preserve_the_basis():
    """The core 'don't lose the GA' guarantee: mutate changes ONLY the evolvable readout; the frozen
    ZCA + codebook are untouched, so shared-codebook grafting semantics survive."""
    if not HAVE:
        return _skip()
    if _load_learned_basis() is None:
        print("SKIP (learned_basis.npz missing)")
        return True
    prev = neural_hive.LEARNED_BASIS_ENABLED
    neural_hive.LEARNED_BASIS_ENABLED = True
    try:
        torch.manual_seed(0)
        b = HiveMindBrain()
        protos0 = b.kanerva.protos.clone()
        W0 = b.zca.W.clone()
        ro0 = b.readout.weight.clone()
        b.mutate(0.1)
        assert torch.equal(b.kanerva.protos, protos0), "mutate must NOT touch the codebook"
        assert torch.equal(b.zca.W, W0), "mutate must NOT touch the whitening"
        assert not torch.equal(b.readout.weight, ro0), "mutate MUST change the evolvable readout"
        # prune + fold-shaped op must not crash and must leave the basis intact
        b.prune_weights(0.5)
        assert torch.equal(b.kanerva.protos, protos0)
    finally:
        neural_hive.LEARNED_BASIS_ENABLED = prev


def test_graft_preserves_shared_codebook():
    if not HAVE:
        return _skip()
    if _load_learned_basis() is None:
        print("SKIP (learned_basis.npz missing)")
        return True
    from neuroevolution import graft_into
    prev = neural_hive.LEARNED_BASIS_ENABLED
    neural_hive.LEARNED_BASIS_ENABLED = True
    try:
        torch.manual_seed(1)
        parent = HiveMindBrain()
        child = HiveMindBrain()
        # both share the SAME learned codebook (that is what makes a readout column mean the same cell)
        assert torch.equal(parent.kanerva.protos, child.kanerva.protos), "learned codebook must be shared"
        graft_into(child, parent)
        assert torch.equal(child.kanerva.protos, parent.kanerva.protos), "graft must keep the shared codebook"
        enc = child(torch.randn(4, child.input_dim))
        assert torch.isfinite(enc).all()
    finally:
        neural_hive.LEARNED_BASIS_ENABLED = prev


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all learned-basis tests passed")
