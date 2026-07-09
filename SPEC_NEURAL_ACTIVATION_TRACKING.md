# Spec: Neural Hive (`neural_hive.py` — activation tracking, pruning, folding, soldier memory)

Layer: **Requirements** + one **Behavioral** block (`HiveMindBrain.forward`).
Governs: `ActivationStats`, `HiveMindBrain` (`forward`, `prune_weights`,
`fold_soldier_layer`, `mutate`), `SoldierLayer` (`forward`/memory, `mate`,
`clone`), and the state encode/decode interface, plus their integration
points in `sandkings.py`. Status: draft → implement → reconcile (log at
bottom). Requirement IDs N1-N10 are stable.

## 1. Defect originally corrected

`HiveMindBrain.forward` had an early `return` leaving unreachable code, and
the live tracking recorded `(param.abs() > 1e-6)` weight masks — "weight is
currently nonzero" — not activation frequency. As a result `prune_weights`
could only re-zero already-zero weights: pruning, as documented in
NEURAL_HIVE_IMPLEMENTATION.md, was vestigial. This spec redefined tracking
as per-neuron post-ReLU firing frequency so pruning does what the docs
claim. (The spec has since grown to govern folding, memory, and the neural
interfaces — see N9, N10, and section 6.)

## 2. Implementation Requirements

- Constant: `ACTIVATION_EMA_DECAY = 0.99` — EMA smoothing horizon (~100 passes).
- Constant: `PRUNE_WARMUP_PASSES = 100` — minimum recorded forward passes before
  any pruning may occur (protects live neurons from early-run EMA noise).
- `activation_stats` is keyed by Linear-layer names (`encoder.0`,
  `encoder.2`); it is not referenced outside `neural_hive.py`.
- `HiveMindBrain.encoder` MUST remain an `nn.Sequential` with the layout
  `[Linear, ReLU, Linear, ReLU]` — `fold_soldier_layer` addresses
  `self.encoder[-2]` and MUST keep working unchanged.
- `prune_weights(threshold: float = 0.01) -> int` signature and integer
  return MUST be unchanged (caller: the neural-pruning phase of
  `SandKingsSimulation.step`).
- `folded_layer_count` is the only performance counter on `HiveMindBrain`
  (the never-incremented `battles_survived`/`total_kills` were removed).

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
  (`ColonyGenome.mutate` deepcopies the whole brain).
- **N8** `get_usage_ratio()` MUST return the per-neuron EMA tensor, or a
  0-dim zero tensor when no passes have been recorded (callers already treat
  `dim() == 0` as "no data").
- **N9** When `fold_soldier_layer` blends a soldier layer (7×32) into the
  encoder's final Linear (32×64), it MUST blend only the overlapping
  submatrix `weight[:rows, :cols]` where `rows = min(soldier.out,
  encoder.out)` and `cols = min(soldier.in, encoder.in)` (biases:
  `[:rows]`). Gate (score ≥ 0.7), alpha (0.1 × score), and
  `folded_layer_count` semantics are unchanged.
  *Rationale:* the original full-tensor blend was dimensionally impossible
  and raised RuntimeError whenever a dying soldier scored ≥ 0.7 — a
  pre-existing defect exposed by acceptance testing.
- **N10** `SoldierLayer` MUST maintain per-soldier recurrent memory: a
  `GRUCell(encoding_dim → encoding_dim)` between the shared Maw encoding
  and the output head. The hidden state is detached every step (no
  autograd graph growth), starts at zeros for fresh, cloned, and mated
  layers, and MUST survive pickle and deepcopy. It persists across steps
  for a soldier's life *given a constant input shape*: a call whose batch
  shape differs from the stored hidden state resets the memory to zeros
  (in live play the encoding shape is constant, so persistence holds).
  `mate()` MUST apply the uniform-crossover + Gaussian-mutation scheme to
  ALL parameters (memory and output); it relies on identical parameter
  registration order across instances and MUST assert structural identity
  before zipping (`zip` would otherwise truncate silently). `clone()`
  copies the full `state_dict`. `fold_soldier_layer` (N9) keeps reading
  only the output head — memory is per-soldier identity and dies with the
  soldier. `forward` MUST accept `(encoding_dim,)` and `(1, encoding_dim)`
  inputs as before.
  *Rationale:* implements the "Memory: temporal patterns" future-work item
  (GRU over LSTM: one gate fewer, same temporal reach at this scale).
  *S1 amendment (SPEC_SENTIENCE): between forward passes, resonance may
  blend a soldier's hidden state toward in-range squadmates' states
  (vectorized `(1-a)H + a(W @ H)`, detached). The hidden state remains
  runtime-only and never a Parameter, so probes (N2), folding (N9), and
  mating compose unchanged.*

## 4. Behavioral Spec — `HiveMindBrain.forward`

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

## 5. Interface contracts

- **State encoding** (`encode_soldier_state` → 40-dim float tensor):
  own position normalized `[0:3]`; maw-relative position `[3:6]`;
  health fraction `[6]`; retreating flag `[7]`; nearest-enemy direction
  `[8:11]` and distance `[11]`; 27 local-voxel features `[12:39]` as
  scalar voxel-type values (NOT one-hot); colony food level `[39]`.
  `input_dim = 40` on `HiveMindBrain` matches this layout by contract.
- **Action decoding** (`decode_soldier_action` on 7 action probabilities):
  indices 0-5 are the six axis-aligned unit moves; index 6 is attack
  (attacks resolve via `_resolve_conflicts`, not here).
- **Soldier fitness** (`get_performance_score`): 0.0 when
  `steps_alive == 0`; else `kills·0.4 + (steps_alive/100)·0.3 +
  (damage_dealt / max(1, damage_taken))·0.2 + (food_gathered/10)·0.1`,
  clipped to [0, 1]. Feeds the N9 fold gate.
- **Maw mutation** (`HiveMindBrain.mutate(rate)`): Gaussian noise on every
  parameter; with 10% probability per parameter tensor, a 5% random mask
  of weights flips sign (polarity reversal). Called at half the genome
  mutation rate (slow Maw evolution).
- **Combat-mating integration** (in `sandkings.py::_resolve_conflicts`):
  when two enemy SOLDIERS with brain layers are adjacent during combat,
  a 5% roll mates them; the offspring layer spawns in a new soldier for
  the larger colony, gated on that colony's `food_stored > 10`.

## 6. Acceptance (Given/When/Then)

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
- (N9) Given a soldier scoring ≥ 0.7, When folded, Then it returns True and
  `folded_layer_count` increments without a shape error
  (`test_fold_soldier_layer_still_works`).
- (N10) Given the same encoding twice, Then outputs differ (memory evolves)
  and hidden is detached (`test_soldier_memory_shapes_and_temporal_effect`);
  Given clone/mate, Then offspring memory starts blank and mate mixes and
  mutates memory parameters (`test_soldier_memory_resets_on_clone_and_mate`);
  Given pickle/deepcopy after a forward, Then hidden state survives and the
  revived layer keeps stepping
  (`test_soldier_memory_survives_pickle_and_deepcopy`).

## 7. Reconciliation Log

- 2026-07-08 (spec one-over) — Retitled and rescoped: the spec now names
  everything it actually governs (folding, soldier memory, interfaces).
  N10 gained the shape-gated hidden-reset caveat and the mate() structural
  assert (added to code); section 5 documents the previously-unspecced
  interface contracts (state layout, action map, fitness formula, Maw
  mutation, combat-mating integration); N9/N10 acceptance scenarios added
  citing their tests; dead counters `battles_survived`/`total_kills`
  removed from code and noted in section 2; stale line-number references
  replaced with symbol names. Suite: 9 tests green.
- 2026-07-07 (Round I) — N10 soldier GRU memory implemented; mate()
  crossover extended to all parameters; 3 memory tests added (9 total).
- 2026-07-07 — Implemented as specced (N1-N8). N9 was added mid-implementation
  when the acceptance test for the encoder[-2] structural guard exposed the
  pre-existing `fold_soldier_layer` shape mismatch; fixed with the overlap
  blend as specced. All acceptance scenarios pass
  (`tests/test_neural_activation.py`, 6 tests at the time).
