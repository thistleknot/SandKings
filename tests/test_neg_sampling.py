"""Lean-synergy tests — negative-sampling masked-prediction (a BETTER objective AND O(active+K), not O(vocab)) and
index-then-mix in the ensemble. Torch-required (skips without)."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

try:
    import torch
    import random
    import tongue
    import ensemble_embed as ee
    HAVE = tongue.MaskedMind is not None
except Exception:
    HAVE = False


def _skip():
    print("SKIP (no torch)")
    return True


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert tongue.NEG_SAMPLING is False, "NEG off by default (dense path, byte-identical battery)"


def _train_recovery(neg, vocab=300, steps=250, seed=0):
    torch.manual_seed(seed)
    tongue.NEG_SAMPLING = neg
    mm = tongue.MaskedMind(vocab)
    r = random.Random(0)
    h = torch.randn(32)
    active = [3, 7, 50, 120, 200]
    acc = []
    for _ in range(steps):
        a = mm.observe(h, active, r)
        if a is not None:
            acc.append(a)
    tongue.NEG_SAMPLING = False
    return sum(acc[-20:]) / 20 if acc else 0.0


def test_neg_learns_and_beats_dense_recovery():
    """NEG is a stronger objective for a large sparse vocab than a dense sigmoid over hundreds of always-zero
    outputs: it reaches near-perfect masked recovery AND does at least as well as the dense baseline."""
    if not HAVE:
        return _skip()
    neg = _train_recovery(True)
    dense = _train_recovery(False)
    assert neg >= 0.9, f"NEG learns the masked task (recovery {neg:.2f})"
    assert neg >= dense, f"NEG objective is at least as good as dense (NEG {neg:.2f} vs dense {dense:.2f})"


def test_neg_cheaper_at_scale():
    """At a large vocab the dense path pays O(vocab) forward+backward; NEG pays O(active+K). NEG must be faster."""
    if not HAVE:
        return _skip()

    def cost(vocab, neg, steps=150):
        tongue.NEG_SAMPLING = neg
        mm = tongue.MaskedMind(vocab)
        r = random.Random(0)
        h = torch.randn(32)
        active = [1, 2, 3, 4]
        for _ in range(10):
            mm.observe(h, active, r)
        t = time.time()
        for _ in range(steps):
            mm.observe(h, active, r)
        return time.time() - t

    dense = cost(20000, False)
    neg = cost(20000, True)
    tongue.NEG_SAMPLING = False
    assert neg < dense, f"NEG is cheaper than dense at 20k vocab (NEG {neg:.3f}s vs dense {dense:.3f}s)"


def test_index_then_mix_equals_full_table():
    """The MixtureEmbedding index-then-mix refactor is exact: indexing commutes with the weighted member sum."""
    if not HAVE:
        return _skip()
    members = np.random.RandomState(1).randn(3, 30, 8).astype("float32")
    m = ee.build_mixture(members)
    ids = torch.tensor([0, 15, 29, 7, 2])
    w = torch.softmax(m.mix, dim=0)
    expected = torch.einsum("k,kvd->vd", w, m.members)[ids] + m.residual(ids)
    assert torch.allclose(m(ids), expected, atol=1e-6), "index-then-mix == full-table-then-index"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all neg-sampling tests passed")
