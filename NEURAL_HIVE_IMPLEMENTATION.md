# Neural Hive Mind Implementation Summary

## Overview
Implemented hierarchical neuroevolution system where each colony has a **Maw brain** (slow-evolving shared encoder) with **soldier layers** as "noodley appendages" (fast-evolving individual extensions).

## Architecture

```
                 🧠 Maw Brain (HiveMindBrain)
                      ↓
          Shared Encoder (40 → 64 → 32)
                      ↓
    ┌─────────────────┼─────────────────┐
    ↓                 ↓                 ↓
[Soldier₁ Layer]  [Soldier₂ Layer]  [Soldier₃ Layer]
 GRUCell(32,32)    GRUCell(32,32)    GRUCell(32,32)
   ↓ hidden          ↓ hidden          ↓ hidden
 Linear(32 → 7)    Linear(32 → 7)    Linear(32 → 7)
   ↓ softmax         ↓ softmax         ↓ softmax
  Actions           Actions           Actions
```

Each soldier layer carries **recurrent memory**: the 32-dim Maw encoding feeds a `GRUCell(32, 32)` whose hidden state persists across the soldier's life (detached each step so no autograd graph accumulates), then a `Linear(32 → 7)` + softmax produces action probabilities. Hidden state starts blank (zeros) for fresh, cloned, and mated layers.

### Components

#### 1. HiveMindBrain (Maw's Brain)
**Location**: `HiveMindBrain` class in `neural_hive.py`

**Structure**:
- Input: 40 features (soldier state encoding)
- Hidden: 64 neurons
- Output: 32-dimensional encoding (shared representation)

**Evolution Rate**: SLOW (mutation_rate * 0.5)
- Only mutates when Maw survives battles
- Represents long-term strategic memory

**Key Features**:
- **Activation Tracking**: `HiveMindBrain.forward` records per-neuron post-ReLU firing frequency as an EMA (decay 0.99) per Linear layer
- **Pruning**: Zeros the weight row AND bias of neurons whose firing EMA ≤ threshold (default 0.01), every 50 steps; skipped until 100 forward passes are recorded (warm-up guard)
- **Folding**: Incorporates high-performing soldier layers (≥0.7 score) via weighted blending of the overlapping submatrix
- **Performance Metrics**: Tracks folded_layer_count

#### 2. SoldierLayer (Individual Soldier Extensions)
**Location**: `SoldierLayer` class in `neural_hive.py`

**Structure**:
- Input: 32 (from Maw encoding)
- Recurrent memory: `GRUCell(32, 32)` — per-soldier hidden state persists across the soldier's life, detached each step, starts blank for fresh/cloned/mated layers
- Output head: `Linear(32 → 7)` + softmax → 7 actions (6 movement directions + attack)

**Evolution Rate**: FAST
- Mates during combat (5% chance when encountering enemies)
- Uniform crossover + Gaussian mutation (std=0.15) over ALL parameters (GRU memory + output head)
- `mate()` asserts structurally identical parents; offspring memory starts blank

**Performance Tracking**:
- `kills`: Number of enemies killed
- `damage_dealt`: Total damage output
- `damage_taken`: Damage absorbed
- `food_gathered`: Food collected
- `steps_alive`: Survival time

**Performance Score**:
```python
if steps_alive == 0:
    return 0.0
score = np.clip(
    kills * 0.4 +                                # Combat effectiveness
    (steps_alive / 100) * 0.3 +                  # Longevity
    (damage_dealt / max(1, damage_taken)) * 0.2 +  # Damage dealt vs taken
    (food_gathered / 10) * 0.1,                  # Resource collection
    0.0, 1.0
)
```

#### 3. State Encoding
**Location**: `encode_soldier_state()` in `neural_hive.py`

**40 Features**:
- Position (x, y, z, normalized): 3 features
- Maw position (relative): 3 features
- Health fraction: 1 feature
- Retreat flag: 1 feature
- Closest enemy direction (unit vector): 3 features
- Closest enemy distance (normalized): 1 feature
- 3×3×3 voxel neighborhood: 27 features (scalar voxel-type values, `float(voxel.value)` — not one-hot)
- Colony food (normalized): 1 feature

#### 4. Action Decoding
**Location**: `decode_soldier_action()` in `neural_hive.py`

**7 Actions**:
- 0-5: Movement (±x, ±y, ±z)
- 6: Attack (handled by combat system)

## Integration Points

### Colony Spawning
**Location**: `Maw.spawn_unit` in `sandkings.py`

When `use_neural=True`, new soldiers get assigned a `SoldierLayer`:
```python
if NEURAL_AVAILABLE and hasattr(self, 'genome') and self.genome.use_neural:
    unit.brain_layer = SoldierLayer()
    unit.brain_layer.steps_alive = 0
```

### Combat Resolution
**Location**: `_resolve_conflicts` in `sandkings.py`

**Three neural events during combat**:

1. **Mating** (5% chance):
   - Soldiers exchange genetic material during combat
   - Creates offspring layer via uniform crossover + mutation across ALL parameters (GRU memory + output head); offspring memory starts blank
   - Spawns new soldier with hybrid brain in stronger colony

2. **Kill Tracking**:
   - Increments `brain_layer.kills` for killer
   - Updates performance metrics

3. **Folding on Death**:
   - When soldier dies, check performance score
   - If score ≥ 0.7, blend the overlapping submatrix of the layer into Maw encoder (alpha = 0.1 × score)
   - Implements Lamarckian inheritance (acquired traits → germline)

### AI Execution
**Location**: soldier branch of `_execute_unit_ai` in `sandkings.py`

**Two AI paths**:
1. **Neural**: Forward pass through Maw → Soldier → Action. The Maw forward also records per-neuron activation stats as a side effect, and the soldier layer routes the encoding through its GRU memory before the output head.
2. **Rule-based**: Fallback enemy-seeking behavior

**Neural execution**:
```python
state_tensor = encode_soldier_state(unit, colony, world, enemy_positions)
encoding = colony.genome.brain(state_tensor)
action_probs = unit.brain_layer(encoding)
action_type, direction = decode_soldier_action(action_probs)
```

### Pruning
**Location**: `SandKingsSimulation.step()` in `sandkings.py`

Every 50 steps:
```python
pruned = colony.genome.brain.prune_weights(threshold=0.01)
# Zeros the weight row and bias of neurons whose firing EMA <= 0.01
# (no-op until 100 forward passes have been recorded)
```

## Usage

### Command Line
```bash
# Enable neural hive minds
python sandkings.py --steps 300 --num-colonies 3 --use-neural

# Rule-based mode (default)
python sandkings.py --steps 300 --num-colonies 3
```

### Initialization
```python
# Create colonies with neural brains
sim = SandKingsSimulation(num_colonies=3)

for colony in sim.colonies:
    colony.genome.use_neural = True
    colony.genome.brain = HiveMindBrain()
    
    # Assign layers to existing soldiers
    for unit in colony.units:
        if unit.unit_type == UnitType.SOLDIER:
            unit.brain_layer = SoldierLayer()
```

## Evolution Dynamics

### Hierarchical Time Scales
**Design inspired by biological neural systems**:

1. **Maw Brain (Slow)**:
   - Evolves over many battles
   - Represents colony-level strategic memory
   - Like DNA: stable, long-term adaptations

2. **Soldier Layers (Fast)**:
   - Evolve via combat mating
   - Represent individual tactical adaptations
   - Like antibodies: rapid, situation-specific responses

### Lamarckian Folding
**Key insight**: Successful tactics feed back into strategic memory

When soldier performs well (score ≥ 0.7):
```python
# Blend soldier's output head into the overlapping region of the
# Maw encoder's final Linear (soldier is 7×32, encoder is 32×64)
alpha = 0.1 * performance_score
rows, cols = min(7, 32), min(32, 64)  # overlapping submatrix
maw.weight[:rows, :cols] = (1 - alpha) * maw.weight[:rows, :cols] + alpha * soldier.weight[:rows, :cols]
maw.bias[:rows]          = (1 - alpha) * maw.bias[:rows]          + alpha * soldier.bias[:rows]
```

Only the overlapping submatrix is blended — the earlier full-tensor blend was dimensionally impossible (7×32 vs 32×64) and crashed whenever a dying soldier scored ≥ 0.7 (spec N9).

This creates **vertical inheritance** where acquired traits can influence the germline (Maw brain).

### Horizontal Gene Transfer
**Mating during combat** creates horizontal gene flow:
- Soldiers from different colonies exchange genetic material
- Creates hybrid offspring with traits from both parents
- Mimics bacterial conjugation or viral lateral transfer

### Network Pruning
**Efficiency optimization**:
- Track per-neuron post-ReLU firing frequency as an EMA (decay 0.99) per Linear layer during forward passes
- Zero the weight row AND bias of neurons whose firing EMA ≤ 0.01
- Warm-up guard: pruning is skipped until 100 forward passes are recorded
- Prevents bloat, maintains computational efficiency
- Analogous to synaptic pruning in biological brains

## Performance Metrics

### Individual Soldier Fitness
```python
def get_performance_score(self) -> float:
    if self.steps_alive == 0:
        return 0.0

    kill_score = self.kills * 0.4
    survival_score = (self.steps_alive / 100.0) * 0.3
    efficiency_score = (self.damage_dealt / max(1, self.damage_taken)) * 0.2
    gather_score = (self.food_gathered / 10.0) * 0.1

    return np.clip(kill_score + survival_score + efficiency_score + gather_score, 0.0, 1.0)
```

### Colony-Level Intelligence
- **folded_layer_count**: Number of successful soldiers incorporated

## Comparison: Neural vs Rule-Based

| Feature | Rule-Based | Neural Hive Mind |
|---------|-----------|-----------------|
| Decision Making | Hardcoded if/else | Learned weights |
| Evolution | Scalar parameters (aggression, etc.) | Neural network weights |
| Adaptation | Random mutation | Mating + folding + pruning |
| Memory | None | Maw brain encodes experience + per-soldier GRU hidden state |
| Inheritance | Vertical only | Vertical (folding) + horizontal (mating) |
| Complexity | Simple | Complex but biologically inspired |

## Testing Results

**Test command**:
```bash
python sandkings.py --steps 50 --num-colonies 3 --use-neural
```

**Output**:
```
============================================================
SAND KINGS SIMULATION
3D Voxel Terrarium with Cellular Automata
🧠 NEURAL HIVE MINDS ENABLED
   Maw brain + soldier layers with mating/folding/pruning
============================================================
✓ Neural hive minds initialized for all colonies

Running 50 steps...
100%|██████████████████████████████████████| 50/50 [00:25<00:00,  1.97it/s]

Step 50 | Colonies: 3/3
  Colony 0: 1 units, 4 food, 100 health
  Colony 1: 1 units, 4 food, 100 health
  Colony 2: 0 units, 2 food, 100 health

✓ Saved sandkings_2d.gif (2D cross-section)
✓ Saved sandkings_3d.gif (3D clustered view)

Simulation complete!
```

## Future Enhancements

### Implemented
1. **Memory**: ✅ Shipped as a per-soldier GRU (`GRUCell` in `SoldierLayer`) — one gate fewer than LSTM, same temporal reach at this scale (governed by spec N10)

### Potential Improvements
1. **Co-evolution**: Neural food-finding for workers
2. **Communication**: Soldier-to-soldier neural messaging
3. **Speciation**: Divergent neural architectures per colony
4. **Meta-learning**: Maw learns learning rate for soldiers
5. **GPU Acceleration**: Port neural forward passes to sandkings_gpu.py

### Research Questions
- Does folding create emergent strategies?
- How does mating rate affect diversity?
- Can pruning threshold be adaptive?
- Do colonies converge or diverge over time?

## Architecture Metaphor: "Noodley Appendages"

The system design mimics biological nervous systems:

- **Maw brain** = Central nervous system (brain/spinal cord)
  - Slow evolution
  - Strategic, long-term memory
  - Shared across colony

- **Soldier layers** = Peripheral nervous system (ganglia)
  - Fast evolution via mating
  - Tactical, short-term adaptations
  - Individual extensions

- **Folding** = Synaptic consolidation
  - Successful short-term memories → long-term storage
  - Lamarckian: experience modifies germline

- **Pruning** = Synaptic pruning
  - Remove unused neural pathways
  - Optimize for efficiency

This creates a **hierarchical, adaptive intelligence** that can respond to threats at multiple time scales while maintaining computational efficiency.

## Dependencies

**Required**:
- `torch` (PyTorch): Neural network operations
- `numpy`: Array operations

**Optional**:
- Falls back to rule-based AI if PyTorch unavailable

## Files Modified

1. **neural_hive.py** (NEW):
   - `ActivationStats`: Per-neuron firing-frequency EMA
   - `HiveMindBrain`: Maw's shared encoder
   - `SoldierLayer`: Individual soldier extensions (GRU memory + output head)
   - `encode_soldier_state()`: State → tensor
   - `decode_soldier_action()`: Tensor → action

2. **sandkings.py**:
   - Module header: torch import, neural imports
   - `ColonyGenome`: `brain` field, slow brain mutation in `mutate()`
   - `SandKing`: `brain_layer` field
   - `Maw.spawn_unit`: Spawn neural layers for new soldiers
   - `SandKingsSimulation.step()`: Periodic pruning
   - `_execute_unit_ai`: Neural AI execution path (soldier branch)
   - `_resolve_conflicts`: Combat mating + folding
   - `main()`: `--use-neural` CLI flag

## Conclusion

This implementation creates a **biologically-inspired hierarchical neuroevolution system** where colonies exhibit emergent intelligence through:

1. **Vertical inheritance**: Maw brain → soldiers
2. **Horizontal transfer**: Soldier mating during combat
3. **Lamarckian adaptation**: Successful soldiers → Maw brain
4. **Network pruning**: Efficiency optimization

The "noodley appendages" metaphor captures the essence: soldiers are extensions of the Maw's central intelligence, each with individual adaptations that can be incorporated back into the collective memory.

**The system is now ready for evolutionary experiments!** 🧠
