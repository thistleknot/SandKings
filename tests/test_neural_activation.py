"""Acceptance tests for SPEC_NEURAL_ACTIVATION_TRACKING.md.

Preconditions: PyTorch installed; run from repo root or via pytest.
Failure modes covered: vestigial pruning, unreachable code regression,
1D/2D input mismatch, deepcopy breakage.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def test_dead_neuron_is_pruned_others_untouched():
    brain = make_brain()
    with torch.no_grad():
        brain.encoder[0].bias[7] = -1e6  # neuron 7 of first layer never fires
        before = brain.encoder[0].weight.data.clone()

    run_forwards(brain, PRUNE_WARMUP_PASSES + 50)
    pruned = brain.prune_weights(threshold=0.01)

    w = brain.encoder[0].weight.data
    assert torch.all(w[7] == 0), "dead neuron row must be zeroed"
    assert brain.encoder[0].bias.data[7] == 0, "dead neuron bias must be zeroed"
    assert pruned >= w.shape[1], f"return must count zeroed weights, got {pruned}"
    live_rows = [i for i in range(w.shape[0]) if i != 7]
    # Live rows that fired must be untouched (compare to pre-run snapshot)
    usage = brain.activation_stats["encoder.0"].get_usage_ratio()
    for i in live_rows:
        if usage[i] > 0.01:
            assert torch.equal(w[i], before[i]), f"live row {i} was modified"


def test_warmup_guard_blocks_early_pruning():
    brain = make_brain()
    with torch.no_grad():
        brain.encoder[0].bias[3] = -1e6
    run_forwards(brain, PRUNE_WARMUP_PASSES - 10)
    snapshot = brain.encoder[0].weight.data.clone()
    pruned = brain.prune_weights(threshold=0.01)
    assert pruned == 0, "no pruning before warm-up"
    assert torch.equal(brain.encoder[0].weight.data, snapshot)


def test_forward_accepts_1d_and_2d():
    brain = make_brain()
    x = torch.randn(40)
    out1 = brain.forward(x)
    out2 = brain.forward(x.unsqueeze(0))
    assert out1.shape == (32,)
    assert out2.shape == (1, 32)
    assert torch.allclose(out1, out2.squeeze(0))


def test_ema_bounded_and_keys_per_layer():
    brain = make_brain()
    run_forwards(brain, 200)
    for key in ("encoder.0", "encoder.2"):
        assert key in brain.activation_stats, f"missing stats key {key}"
        ema = brain.activation_stats[key].get_usage_ratio()
        assert ema.dim() == 1, "per-neuron EMA expected"
        assert torch.all(ema >= 0) and torch.all(ema <= 1)
    assert 0 < ACTIVATION_EMA_DECAY < 1


def test_deepcopy_isolated():
    brain = make_brain()
    run_forwards(brain, PRUNE_WARMUP_PASSES + 10)
    clone = copy.deepcopy(brain)
    clone.forward(torch.randn(40))  # must not raise
    clone.prune_weights(threshold=0.01)  # must not raise
    passes_orig = brain.activation_stats["encoder.0"].total_forward_passes
    passes_clone = clone.activation_stats["encoder.0"].total_forward_passes
    assert passes_clone == passes_orig + 1
    assert brain.activation_stats["encoder.0"].total_forward_passes == passes_orig


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
