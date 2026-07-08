# Sand Kings v2.0 - Quick Decisive Battles

## Changes Implemented (2025-01-XX)

### 1. Variable Colony Count (3-5)
**Location:** `sandkings.py:625-631`
```python
def _spawn_colonies(self, num_colonies: int = None):
    # Variable colony count (3-5) if not specified or 0
    if num_colonies is None or num_colonies == 0:
        num_colonies = random.randint(3, 5)
```

**Result:** Each battle randomly spawns 3, 4, or 5 colonies (not fixed at 4)

**Test:** `python -c "from sandkings import SandKingsSimulation; results = [len(SandKingsSimulation(num_colonies=0).colonies) for _ in range(10)]; print(results)"`
```
Colony counts: [5, 3, 4, 4, 4, 4, 4, 5, 5, 4]
```

---

### 2. Randomized Spawn Positions
**Location:** `sandkings.py:633-648`
```python
# Minimum distance = 10% of map diagonal
min_distance = int(0.1 * ((w**2 + h**2)**0.5))

# Generate positions ensuring min distance
positions = []
for i in range(num_colonies):
    for attempt in range(max_attempts):
        x = random.randint(w//8, 7*w//8)
        y = random.randint(h//8, 7*h//8)
        z = d//2  # Mid-depth
        
        if all(((pos[0]-p[0])**2 + (pos[1]-p[1])**2)**0.5 >= min_distance 
               for p in positions):
            positions.append((x, y, z))
            break
```

**Before:** Fixed 4 corners `(w//4, h//4)`, `(3*w//4, h//4)`, etc.
**After:** Random positions with 10% diagonal minimum separation

---

### 3. Morale System (10% HP Retreat)
**Location:** `sandkings.py:218-221` (SandKing class)
```python
@dataclass
class SandKing:
    health: int = 10
    max_health: int = 10  # Track original health
    retreating: bool = False  # Morale flag
```

**Location:** `sandkings.py:244-250` (take_damage method)
```python
def take_damage(self, damage: int, resilience: float = 0.0) -> bool:
    actual_damage = damage * (1.0 - resilience * 0.5)
    self.health -= actual_damage
    
    # Morale check: retreat at 10% HP (ancient Greek tactics)
    if self.health < self.max_health * 0.1 and not self.retreating:
        self.retreating = True
    
    return self.health <= 0
```

**Behavior:** When unit drops below 10% max HP, `retreating` flag set → unit flees instead of attacking

**Ancient Warfare Model:** Greek/Roman armies historically broke and fled at ~10% casualties, creating decisive victories without total annihilation.

---

### 4. Retreat AI Behavior
**Location:** `sandkings.py:714-733` (Soldier AI)
```python
elif unit.unit_type == UnitType.SOLDIER:
    # MORALE CHECK: Retreat if wounded (<10% HP)
    if unit.retreating:
        # Flee away from enemy
        if closest_enemy:
            dx = -np.sign(closest_enemy.position[0] - x)  # Run opposite direction
            dy = -np.sign(closest_enemy.position[1] - y)
            dz = 0  # Stay at same depth when fleeing
            new_pos = (int(x + dx), int(y + dy), int(z + dz))
            if self.world.in_bounds(*new_pos):
                unit.move(new_pos)
    else:
        # If healthy and enemy within range, ATTACK
        if closest_enemy and min_dist < colony.genome.foraging_range:
            # Move toward enemy...
```

**Before:** Soldiers always aggressive
**After:** Wounded soldiers (<10% HP) actively flee, cannot attack while retreating

---

### 5. Aggression > Defense Balance
**Increased Soldier Damage:**
```python
# sandkings.py:231-235
elif self.unit_type == UnitType.SOLDIER:
    self.health = 20  # Reduced from 25
    self.max_health = 20
    self.attack = 12  # Increased from 8 (50% damage boost)
```

**Weakened Defense:**
```python
# sandkings.py:245
actual_damage = damage * (1.0 - resilience * 0.5)  # Resilience capped at 50%

# sandkings.py:651
genome.resilience = random.uniform(0.0, 0.3)  # Defense weaker (was 0-1.0)
```

**Aggression Bias in Genome:**
```python
# sandkings.py:650
genome.aggression = random.uniform(0.5, 1.0)  # Favor aggression (50-100%)
```

**Result:** Offensive strategies are more effective → battles resolve faster

---

### 6. GPU Version Updates
**Location:** `sandkings_gpu.py`

Same changes applied:
- Lines 203-267: Morale retreat AI
- Lines 269-296: Increased damage (12 base), weakened resilience (30% cap)

```python
# sandkings_gpu.py:278
# COMBAT! Increased damage (12 base), resilience capped at 30%
if unit.take_damage(enemy.attack, colony.genome.resilience * 0.6):  # Weaker defense
```

---

## Design Philosophy

**Core War Adaptation:**
- Core War: Shared memory = 100% combat probability
- Sand Kings: 3D space = sparse encounters → Need morale collapse for decisive outcomes

**Ancient Warfare Model:**
- Historical armies broke at ~10% casualties
- Morale collapse creates clear winners without requiring physical proximity
- Psychological routing creates cascading retreats

**Aggression > Defense:**
- More weapon upgrades than defensive traits
- Quick decisive battles (like Conway's Game of Life)
- Clear victors emerge through morale collapse

---

## Testing Commands

**Variable Colony Count:**
```bash
python sandkings.py --steps 200 --num-colonies 0  # Random 3-5 colonies
```

**Morale Testing (Long Run):**
```bash
python sandkings.py --steps 500 --num-colonies 3  # See if battles end decisively
```

**GPU Version:**
```bash
python sandkings_evolution.py --mode demo --sim-steps 500 --gpu --num-colonies 0
```

---

## Expected Outcomes

1. ✅ **Variable battles:** 3-5 colonies per run (not always 4)
2. ✅ **Spatial diversity:** Colonies spawn at random positions
3. ✅ **Decisive outcomes:** Maw sieges (SPEC_TERRARIUM_LIVENESS.md T4) make
   colony elimination real — war soak: 4 falls in 3000 steps
4. ✅ **Quick resolution:** war parties + sieges resolve conflicts in bursts;
   sieges last ~10-40 steps of adjacency (Maw 500 HP vs squad attack)
5. ✅ **Emergent routing:** observed in soaks — besieged colonies lose units,
   retreat, and collapse into corpse feasts

---

## Next Steps

1. ✅ **Test long runs (500-1000 steps)** - Done via 2500-3000-step soaks
   (SPEC_TERRARIUM_LIVENESS.md reconciliation log): populations oscillate,
   colonies fall and are replaced
2. ✅ **Check battle duration** - War soak: 12 sieges / 4 falls in 3000 steps;
   elimination happens through sieges rather than pure morale collapse
3. ✅ **Visualize retreats** - Done: the live viewer (`python sandkings.py --live`) renders retreating units at 40% brightness with a magenta border (`live_view.py`, SPEC_LIVE_VIEW.md R5)
4. ✅ **Fix fitness function** - Done: outcome-based scoring
   (enemies_eliminated 500 / survived 200 dominate; time is a 0.05
   tie-breaker) — `SandKingsMapElites.get_fitness`, SPEC T14
5. **Reduce max steps** - Optional now that outcomes are decisive: pass
   `--sim-steps 200` to evolution runs; default left unchanged

---

## Key Metrics to Monitor

- **Time to first elimination:** How long until a colony is wiped out?
- **Retreat cascades:** Do wounded units trigger panic?
- **Battle resolution rate:** % of battles with clear victor vs time-out
- **Population dynamics:** Do populations still grow infinitely, or do battles create losers?
