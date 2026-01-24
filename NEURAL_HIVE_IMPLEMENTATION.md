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
[Soldier₁ Layer] [Soldier₂ Layer] [Soldier₃ Layer]
  (32 → 7)         (32 → 7)         (32 → 7)
    ↓                 ↓                 ↓
  Actions          Actions          Actions
```

### Components

#### 1. HiveMindBrain (Maw's Brain)
**Location**: `neural_hive.py` lines 48-159

**Structure**:
- Input: 40 features (soldier state encoding)
- Hidden: 64 neurons
- Output: 32-dimensional encoding (shared representation)

**Evolution Rate**: SLOW (mutation_rate * 0.5)
- Only mutates when Maw survives battles
- Represents long-term strategic memory

**Key Features**:
- **Activation Tracking**: Records which weights are used during forward passes
- **Pruning**: Removes weights used < 1% of time (every 50 steps)
- **Folding**: Incorporates high-performing soldier layers (>0.7 score) via weighted blending
- **Performance Metrics**: Tracks battles_survived, total_kills, folded_layer_count

#### 2. SoldierLayer (Individual Soldier Extensions)
**Location**: `neural_hive.py` lines 162-254

**Structure**:
- Input: 32 (from Maw encoding)
- Output: 7 actions (6 movement directions + attack)

**Evolution Rate**: FAST
- Mates during combat (5% chance when encountering enemies)
- Uniform crossover + Gaussian mutation (std=0.1)

**Performance Tracking**:
- `kills`: Number of enemies killed
- `damage_dealt`: Total damage output
- `damage_taken`: Damage absorbed
- `food_gathered`: Food collected
- `steps_alive`: Survival time

**Performance Score**:
```python
score = (
    kills * 0.4 +           # Combat effectiveness
    survival * 0.3 +        # Longevity
    efficiency * 0.2 +      # Damage dealt vs taken
    gathering * 0.1         # Resource collection
)
```

#### 3. State Encoding
**Location**: `neural_hive.py` lines 257-314

**40 Features**:
- Position (x, y, z): 3 features
- Health fraction: 1 feature
- Retreat flag: 1 feature
- Closest enemy direction (unit vector): 3 features
- Closest enemy distance (normalized): 1 feature
- 3×3×3 voxel neighborhood: 27 features (one-hot for each voxel type)
- Colony food (normalized): 1 feature

#### 4. Action Decoding
**Location**: `neural_hive.py` lines 317-327

**7 Actions**:
- 0-5: Movement (±x, ±y, ±z)
- 6: Attack (handled by combat system)

## Integration Points

### Colony Spawning
**Location**: `sandkings.py` lines 302-316

When `use_neural=True`, new soldiers get assigned a `SoldierLayer`:
```python
if NEURAL_AVAILABLE and hasattr(self, 'genome') and self.genome.use_neural:
    unit.brain_layer = SoldierLayer()
    unit.brain_layer.steps_alive = 0
```

### Combat Resolution
**Location**: `sandkings.py` lines 882-942

**Three neural events during combat**:

1. **Mating** (5% chance):
   - Soldiers exchange genetic material during combat
   - Creates offspring layer via uniform crossover
   - Spawns new soldier with hybrid brain in stronger colony

2. **Kill Tracking**:
   - Increments `brain_layer.kills` for killer
   - Updates performance metrics

3. **Folding on Death**:
   - When soldier dies, check performance score
   - If score > 0.7, blend layer into Maw encoder (10% weighted)
   - Implements Lamarckian inheritance (acquired traits → germline)

### AI Execution
**Location**: `sandkings.py` lines 767-846

**Two AI paths**:
1. **Neural**: Forward pass through Maw → Soldier → Action
2. **Rule-based**: Fallback enemy-seeking behavior

**Neural execution**:
```python
state_tensor = encode_soldier_state(unit, colony, world, enemy_positions)
encoding = colony.genome.brain(state_tensor)
action_probs = unit.brain_layer(encoding)
action_type, direction = decode_soldier_action(action_probs)
```

### Pruning
**Location**: `sandkings.py` lines 728-733

Every 50 steps:
```python
pruned = colony.genome.brain.prune_weights(threshold=0.01)
# Zeros weights used < 1% of time
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

When soldier performs well (score > 0.7):
```python
# Blend soldier's output layer into Maw's encoder
alpha = 0.1 * performance_score
maw_weights = (1 - alpha) * maw_weights + alpha * soldier_weights
```

This creates **vertical inheritance** where acquired traits can influence the germline (Maw brain).

### Horizontal Gene Transfer
**Mating during combat** creates horizontal gene flow:
- Soldiers from different colonies exchange genetic material
- Creates hybrid offspring with traits from both parents
- Mimics bacterial conjugation or viral lateral transfer

### Network Pruning
**Efficiency optimization**:
- Track which neurons fire during forward passes
- Remove weights used < 1% of time
- Prevents bloat, maintains computational efficiency
- Analogous to synaptic pruning in biological brains

## Performance Metrics

### Individual Soldier Fitness
```python
def get_performance_score(self) -> float:
    survival = min(1.0, self.steps_alive / 100.0)
    efficiency = self.damage_dealt / max(1.0, self.damage_taken)
    efficiency_norm = min(1.0, efficiency / 10.0)
    gathering = min(1.0, self.food_gathered / 50.0)
    
    return (
        self.kills * 0.4 +
        survival * 0.3 +
        efficiency_norm * 0.2 +
        gathering * 0.1
    )
```

### Colony-Level Intelligence
- **battles_survived**: Maw longevity
- **total_kills**: Aggregate combat success
- **folded_layer_count**: Number of successful soldiers incorporated

## Comparison: Neural vs Rule-Based

| Feature | Rule-Based | Neural Hive Mind |
|---------|-----------|-----------------|
| Decision Making | Hardcoded if/else | Learned weights |
| Evolution | Scalar parameters (aggression, etc.) | Neural network weights |
| Adaptation | Random mutation | Mating + folding + pruning |
| Memory | None | Maw brain encodes experience |
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

### Potential Improvements
1. **Co-evolution**: Neural food-finding for workers
2. **Memory**: Add LSTM layers for temporal patterns
3. **Communication**: Soldier-to-soldier neural messaging
4. **Speciation**: Divergent neural architectures per colony
5. **Meta-learning**: Maw learns learning rate for soldiers
6. **GPU Acceleration**: Port neural forward passes to sandkings_gpu.py

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

1. **neural_hive.py** (NEW, 376 lines):
   - `ActivationStats`: Tracks neuron usage
   - `HiveMindBrain`: Maw's shared encoder
   - `SoldierLayer`: Individual soldier extensions
   - `encode_soldier_state()`: State → tensor
   - `decode_soldier_action()`: Tensor → action

2. **sandkings.py** (1066 lines):
   - Lines 1-31: Added torch import, neural imports
   - Lines 193-232: `ColonyGenome.brain` field
   - Lines 244-263: `SandKing.brain_layer` field
   - Lines 302-316: Spawn neural layers for new soldiers
   - Lines 728-733: Periodic pruning
   - Lines 767-846: Neural AI execution path
   - Lines 882-942: Combat mating + folding
   - Lines 985-1047: `--use-neural` CLI flag

## Conclusion

This implementation creates a **biologically-inspired hierarchical neuroevolution system** where colonies exhibit emergent intelligence through:

1. **Vertical inheritance**: Maw brain → soldiers
2. **Horizontal transfer**: Soldier mating during combat
3. **Lamarckian adaptation**: Successful soldiers → Maw brain
4. **Network pruning**: Efficiency optimization

The "noodley appendages" metaphor captures the essence: soldiers are extensions of the Maw's central intelligence, each with individual adaptations that can be incorporated back into the collective memory.

**The system is now ready for evolutionary experiments!** 🧠
