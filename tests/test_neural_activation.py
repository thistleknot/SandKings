"""Acceptance tests for SPEC_NEURAL_ACTIVATION_TRACKING.md.

Preconditions: PyTorch installed; run from repo root or via pytest.
Failure modes covered: vestigial pruning, unreachable code regression,
1D/2D input mismatch, deepcopy breakage.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import torch

from neural_hive import (
    ACTIVATION_EMA_DECAY,
    PRUNE_WARMUP_PASSES,
    HiveMindBrain,
)


def make_brain(seed: int = 0) -> HiveMindBrain:
    torch.manual_seed(seed)
    return HiveMindBrain()


def run_forwards(brain: HiveMindBrain, n: int, seed: int = 1):
    torch.manual_seed(seed)
    for _ in range(n):
        brain.forward(torch.randn(40))


def test_dead_prototype_is_pruned():
    """A Kanerva prototype that (almost) never wins has its readout column zeroed;
    the maw's memory sheds dead cells (SDM pruning)."""
    brain = make_brain()
    run_forwards(brain, PRUNE_WARMUP_PASSES + 10)     # populate usage + pass warmup
    with torch.no_grad():
        brain.proto_usage.ema[5] = 0.0                # force prototype 5 dead
        brain.readout.weight.data[:, 5] = 1.0         # ensure its column is nonzero
    pruned = brain.prune_weights(threshold=0.01)
    assert brain.readout.weight.data[:, 5].abs().sum() == 0, "dead prototype column zeroed"
    assert pruned >= brain.readout.weight.shape[0], f"must count zeroed weights, got {pruned}"


def test_warmup_guard_blocks_early_pruning():
    brain = make_brain()
    run_forwards(brain, PRUNE_WARMUP_PASSES - 10)
    with torch.no_grad():
        brain.proto_usage.ema[3] = 0.0                # dead, but still in warm-up
    snapshot = brain.readout.weight.data.clone()
    assert brain.prune_weights(threshold=0.01) == 0, "no pruning before warm-up"
    assert torch.equal(brain.readout.weight.data, snapshot)


def test_forward_accepts_1d_and_2d():
    brain = make_brain()
    x = torch.randn(40)
    out1 = brain.forward(x)
    out2 = brain.forward(x.unsqueeze(0))
    assert out1.shape == (32,)
    assert out2.shape == (1, 32)


def test_proto_usage_ema_bounded():
    brain = make_brain()
    run_forwards(brain, 200)
    ema = brain.proto_usage.get_usage_ratio()
    assert ema.dim() == 1 and ema.shape[0] == brain.kanerva.n_protos, "per-prototype EMA"
    assert torch.all(ema >= 0) and torch.all(ema <= 1)
    assert 0 < ACTIVATION_EMA_DECAY < 1


def test_deepcopy_isolated():
    brain = make_brain()
    run_forwards(brain, PRUNE_WARMUP_PASSES + 10)
    clone = copy.deepcopy(brain)
    clone.forward(torch.randn(40))  # must not raise
    clone.prune_weights(threshold=0.01)  # must not raise
    passes_orig = brain.proto_usage.total_forward_passes
    assert clone.proto_usage.total_forward_passes == passes_orig + 1
    assert brain.proto_usage.total_forward_passes == passes_orig


def test_fold_soldier_layer_still_works():
    """Structural guard: encoder[-2] contract used by folding must survive."""
    from neural_hive import SoldierLayer

    brain = make_brain()
    soldier = SoldierLayer()
    assert brain.fold_soldier_layer(soldier, performance_score=0.9) is True
    assert brain.folded_layer_count == 1


def test_soldier_memory_shapes_and_temporal_effect():
    from neural_hive import SoldierLayer

    torch.manual_seed(3)
    soldier = SoldierLayer()
    encoding = torch.randn(32)
    out1 = soldier.forward(encoding)
    out2 = soldier.forward(encoding)  # same input, evolved hidden state
    assert out1.shape == (7,)
    assert not torch.allclose(out1, out2), "memory must make behavior temporal"
    assert soldier.hidden is not None and not soldier.hidden.requires_grad
    batch = soldier.forward(encoding.unsqueeze(0))
    assert batch.shape == (1, 7)


def test_soldier_memory_resets_on_clone_and_mate():
    from neural_hive import SoldierLayer

    torch.manual_seed(4)
    a, b = SoldierLayer(), SoldierLayer()
    a.forward(torch.randn(32))
    assert a.hidden is not None
    assert a.clone().hidden is None, "clone starts with blank memory"
    child = a.mate(b)
    assert child.hidden is None, "offspring starts with blank memory"
    # mate must mix/mutate memory parameters too (spec N10)
    assert not torch.equal(child.memory.weight_ih, a.memory.weight_ih)
    assert not torch.equal(child.memory.weight_ih, b.memory.weight_ih)


def test_soldier_memory_survives_pickle_and_deepcopy():
    import pickle
    from neural_hive import SoldierLayer

    torch.manual_seed(5)
    soldier = SoldierLayer()
    soldier.forward(torch.randn(32))
    for revived in (pickle.loads(pickle.dumps(soldier)), copy.deepcopy(soldier)):
        assert torch.equal(revived.hidden, soldier.hidden)
        revived.forward(torch.randn(32))  # must keep stepping


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all neural activation tests passed")
