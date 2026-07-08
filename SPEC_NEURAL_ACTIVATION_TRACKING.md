# Spec: Neural Activation Tracking & Pruning (`neural_hive.py`)

Layer: **Requirements** + one **Behavioral** block (`HiveMindBrain.forward`).
Governs: `ActivationStats`, `HiveMindBrain.forward`, `HiveMindBrain.prune_weights`.
Status: draft → implement → reconcile (see Reconciliation Log at bottom).

## 1. Defect being corrected

`HiveMindBrain.forward` has an early `return` (`neural_hive.py:90`) leaving
unreachable code (:91-101), and the live tracking records `(param.abs() > 1e-6)`
weight masks — "weight is currently nonzero" — not activation frequency. As a
result `prune_weights` can only re-zero already-zero weights: pruning, as
documented in NEURAL_HIVE_IMPLEMENTATION.md ("weights used <1% zeroed every 50
steps"), is vestigial. This spec redefines tracking as per-neuron post-ReLU
firing frequency so pruning does what the docs claim.

## 2. Implementation Requirements

- Constant: `ACTIVATION_EMA_DECAY = 0.99` — EMA smoothing horizon (~100 passes).
- Constant: `PRUNE_WARMUP_PASSES = 100` — minimum recorded forward passes before
  any pruning may occur (protects live neurons from early-run EMA noise).
- `activation_stats` keys change from parameter names to Linear-layer names:
  `encoder.0`, `encoder.2`. `activation_stats` is not referenced outside
  `neural_hive.py` (verified), so re-keying is safe.
- `HiveMindBrain.encoder` MUST remain an `nn.Sequential` with the layout
  `[Linear, ReLU, Linear, ReLU]` — `fold_soldier_layer` addresses
  `self.encoder[-2]` and MUST keep working unchanged.
- `prune_weights(threshold: float = 0.01) -> int` signature and integer return
  MUST be unchanged (caller: `sandkings.py:733`).

## 3. Functional Requirements (EARS)

- **N1** When `forward(x)` runs, it MUST record, per Linear layer, which output
  neurons fired (post-ReLU activation > 0) into that layer's `ActivationStats`
  as an EMA: `ema ← decay·ema + (1−decay)·fired_fraction`, where
  `fired_fraction` per neuron is the mean over the batch dimension.
- **N2** `forward` MUST accept both `(input_dim,)` and `(batch, input_dim)`
  inputs and return the same encoding the encoder alone would produce.
- **N3** `forward` MUST contain no unreachable code.
- **N4** Activation recording MUST run under `torch.no_grad()` and MUST NOT
  alter the returned encoding.
- **N5** When `prune_weights(threshold)` is called and a layer's recorded
  passes < PRUNE_WARMUP_PASSES, that layer MUST be skipped (no pruning).
- **N6** When `prune_weights(threshold)` prunes, it MUST zero the weight row
  and bias entry of every neuron whose usage EMA ≤ threshold, and MUST return
  the count of newly zeroed weight elements (0 when nothing pruned).
- **N7** `ActivationStats` MUST survive `copy.deepcopy`
  (`ColonyGenome.mutate` deepcopies the whole brain, `sandkings.py:226`).
- **N8** `get_usage_ratio()` MUST return the per-neuron EMA tensor, or a
  0-dim zero tensor when no passes have been recorded (callers already treat
  `dim() == 0` as "no data").
- **N9** (defect found during acceptance testing, pre-existing) When
  `fold_soldier_layer` blends a soldier layer (7×32) into the encoder's final
  Linear (32×64), it MUST blend only the overlapping submatrix
  `weight[:rows, :cols]` where `rows = min(soldier.out, encoder.out)` and
  `cols = min(soldier.in, encoder.in)` (biases: `[:rows]`). The original code
  attempted a full-tensor blend, which is dimensionally impossible and raised
  RuntimeError whenever a dying soldier scored ≥ 0.7. Gate (score ≥ 0.7),
  alpha (0.1 × score), and `folded_layer_count` semantics are unchanged.

## 3b. N10 — Soldier memory (Round I)

- **N10** `SoldierLayer` MUST maintain per-soldier recurrent memory: a
  `GRUCell(encoding_dim -> encoding_dim)` between the shared Maw encoding
  and the output head. The hidden state persists across steps within a
  soldier's life, is detached every step (no autograd graph growth),
  starts at zeros for fresh, cloned, and mated layers, and MUST survive
  pickle and deepcopy. `mate()` MUST apply the uniform-crossover +
  Gaussian-mutation scheme to ALL parameters (memory and output);
  `clone()` copies the full `state_dict`. `fold_soldier_layer` (N9) keeps
  reading only the output head — memory is per-soldier identity and dies
  with the soldier. `forward` MUST accept `(encoding_dim,)` and
  `(1, encoding_dim)` inputs as before. This implements the
  NEURAL_HIVE_IMPLEMENTATION.md future-work item "Memory: temporal
  patterns" (GRU chosen over LSTM: one gate fewer, same temporal reach at
  this scale).

## 4. Behavioral Spec — `forward`

```
Input: x — tensor (input_dim,) or (batch, input_dim)
h ← x if x.dim() == 2 else x.unsqueeze(0)      # stats always see 2D
For i, layer in enumerate(encoder):
    h ← layer(h)
    If layer is ReLU:                           # h is post-ReLU output of encoder[i-1]
        With no_grad:
            fired ← (h > 0).float().mean(dim=0) # per-neuron batch fraction
            activation_stats[f"encoder.{i-1}"].update(fired)
Return h if x.dim() == 2 else h.squeeze(0)
Assert: output shape == encoder(x).shape
```

## 5. Acceptance (Given/When/Then)

- Given a fresh brain with one first-layer neuron forced dead (bias = −1e6),
  When 100+ forwards run on random inputs and `prune_weights(0.01)` is called,
  Then that neuron's weight row and bias are all zeros, the return count ≥
  input_dim, and every other neuron's weights are unchanged.
- Given fewer than PRUNE_WARMUP_PASSES forwards, When `prune_weights` is
  called, Then it returns 0 and no parameter changes.
- Given a `(40,)` input and the same values as a `(1, 40)` input, Then forward
  outputs are equal (shapes `(32,)` and `(1, 32)` respectively).
- Given 200 forwards, Then every EMA value lies in [0, 1].
- Given `copy.deepcopy(brain)`, Then the copy's forward and prune_weights work
  and mutating the copy's stats does not affect the original.

## 6. Reconciliation Log

- 2026-07-07 — Implemented as specced (N1-N8). N9 was added mid-implementation
  when the acceptance test for the encoder[-2] structural guard exposed the
  pre-existing `fold_soldier_layer` shape mismatch; fixed with the overlap
  blend as specced. All acceptance scenarios pass
  (`tests/test_neural_activation.py`, 6 tests).
