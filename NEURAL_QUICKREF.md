# Neural Hive Mind Quick Reference

## 🧠 Architecture

```
Input State (40 features)
         ↓
    Maw Brain (Encoder)
    [40 → 64 → 32]
    Slow Evolution
         ↓
    ┌────┴────┐
    ↓         ↓
Soldier₁   Soldier₂ ...
[32 → 7]   [32 → 7]
Fast Evolution
    ↓         ↓
  Actions   Actions
```

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
# Uniform crossover + Gaussian mutation
```

### 2. Lamarckian Folding (score > 0.7)
```python
# Successful soldier → Maw brain
alpha = 0.1 * performance_score
maw_weights = (1-α)*maw + α*soldier
```

### 3. Network Pruning (every 50 steps)
```python
# Remove weights used < 1%
if usage < 0.01:
    weight = 0
```

## 📊 Performance Score

```python
score = (
    kills * 0.4 +        # Combat
    survival * 0.3 +     # Longevity
    efficiency * 0.2 +   # Damage ratio
    gathering * 0.1      # Resources
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

- `neural_hive.py` (376 lines): Neural architecture
- `sandkings.py` (1066 lines): Integration
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

- [ ] LSTM for temporal patterns
- [ ] Soldier-to-soldier communication
- [ ] Meta-learning (Maw learns learning rate)
- [ ] GPU acceleration
- [ ] Speciation (divergent architectures)
- [ ] Co-evolution (neural workers)

---

**"Noodley appendages"** - soldiers as extensions of Maw's central intelligence 🐙
