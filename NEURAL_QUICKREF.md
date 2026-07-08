# Neural Hive Mind Quick Reference

## 🧠 Architecture

```
Input State (40 features)
         ↓
    Maw Brain (Encoder)
    [40 → 64 → 32]
    Slow Evolution
    (records firing stats)
         ↓
    ┌────┴────┐
    ↓         ↓
Soldier₁      Soldier₂ ...
GRU(32→32)    GRU(32→32)
[32 → 7]      [32 → 7]
softmax       softmax
Fast Evolution
    ↓         ↓
  Actions   Actions
```

Maw forward records per-neuron activation stats; each soldier routes the encoding through its own `GRUCell(32,32)` memory (hidden state persists across the soldier's life, detached each step, blank for fresh/cloned/mated layers) before the `Linear(32→7)` + softmax head.

## ⚡ Evolution Rates

| Component | Rate | Trigger | Purpose |
|-----------|------|---------|---------|
| **Maw Brain** | Slow (0.5×) | Survives battle | Strategic memory |
| **Soldier Layer** | Fast (1.0×) | Combat mating | Tactical adaptation |

## 🔄 Key Mechanisms

### 1. Combat Mating (5% chance)
```python
# When soldiers meet in battle:
offspring = soldier1.mate(soldier2)
# Uniform crossover + Gaussian mutation (std=0.15)
# over ALL parameters (GRU memory + output head);
# offspring memory starts blank; parents must be
# structurally identical (asserted)
```

### 2. Lamarckian Folding (score ≥ 0.7)
```python
# Successful soldier → Maw brain: blend only the
# overlapping submatrix (soldier 7×32 vs encoder 32×64)
alpha = 0.1 * performance_score
rows, cols = min(7, 32), min(32, 64)
maw.weight[:rows, :cols] = (1-α)*maw.weight[:rows, :cols] + α*soldier.weight[:rows, :cols]
maw.bias[:rows]          = (1-α)*maw.bias[:rows] + α*soldier.bias[:rows]
```
(The old full-tensor blend was dimensionally impossible and crashed whenever a dying soldier scored ≥ 0.7.)

### 3. Network Pruning (every 50 steps)
```python
# Per-neuron post-ReLU firing frequency, EMA decay 0.99
# Skipped until 100 forward passes recorded (warm-up)
if firing_ema <= 0.01:
    weight_row = 0
    bias = 0
```

## 📊 Performance Score

```python
if steps_alive == 0:
    return 0.0
score = clip(
    kills * 0.4 +                                # Combat
    (steps_alive / 100) * 0.3 +                  # Longevity
    (damage_dealt / max(1, damage_taken)) * 0.2 +  # Damage ratio
    (food_gathered / 10) * 0.1,                  # Resources
    0.0, 1.0
)
```

## 🎮 Usage

```bash
# Enable neural mode
python sandkings.py --steps 300 --use-neural

# Compare with rule-based
python sandkings.py --steps 300  # No flag = rules
```

## 📁 Files

- `neural_hive.py`: Neural architecture
- `sandkings.py`: Integration
- `NEURAL_HIVE_IMPLEMENTATION.md`: Full docs

## 🔬 Biological Inspiration

**Central Nervous System**
- Maw brain = brain/spinal cord
- Strategic, long-term memory

**Peripheral Nervous System**
- Soldier layers = ganglia
- Tactical, short-term adaptations

**Evolutionary Mechanisms**
- Vertical inheritance: Maw → soldiers
- Horizontal transfer: Soldier mating
- Lamarckian: Acquired traits → germline
- Pruning: Synaptic optimization

## 🎯 Design Goals

1. ✅ Hierarchical time scales (slow Maw, fast soldiers)
2. ✅ Bidirectional learning (vertical + horizontal)
3. ✅ Lamarckian dynamics (experience → germline)
4. ✅ Efficiency optimization (pruning)
5. ✅ Emergent intelligence (collective + individual)

## 🧪 Testing

```bash
# Quick test (50 steps, 3 colonies)
python sandkings.py --steps 50 --num-colonies 3 --use-neural

# Full evolution (300 steps)
python sandkings.py --steps 300 --num-colonies 5 --use-neural
```

**Expected output:**
```
🧠 NEURAL HIVE MINDS ENABLED
   Maw brain + soldier layers with mating/folding/pruning
✓ Neural hive minds initialized for all colonies
```

## 🚀 Future Work

- [x] Memory for temporal patterns — shipped as per-soldier GRU (one gate fewer than LSTM, same temporal reach at this scale; spec N10)
- [ ] Soldier-to-soldier communication
- [ ] Meta-learning (Maw learns learning rate)
- [ ] GPU acceleration
- [ ] Speciation (divergent architectures)
- [ ] Co-evolution (neural workers)

---

**"Noodley appendages"** - soldiers as extensions of Maw's central intelligence 🐙
