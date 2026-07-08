# Spec: Terrarium Liveness (feeding, foraging, maw combat, respawn, strata terrain)

Layer: **Requirements** + **Behavioral** blocks (feeding phase, colony death cascade).
Governs: `sandkings.py` — terrain generation, the economy phases of
`SandKingsSimulation.step()`, worker/soldier AI additions, Maw combat, and
colony respawn. Status: draft → implement → reconcile (log at bottom).

## 1. Defect being corrected

Observed: by step ~1200 every colony is frozen at 0 units / ~1 food / maw
100 HP, permanently. Causes (verified): the food system is closed (~6 food
voxels ever, no regeneration) and workers only harvest by random radius-2
encounter; `Maw.take_damage` has no call sites so colonies can never be
eliminated; and the 0-unit low-food state has no exit. The terrarium needs
throughput (food in, corpses recycled, colonies falling and being replaced)
to stay alive indefinitely.

## 2. Implementation Requirements

- Constant: `MAINTENANCE_COST = 0.1` food/unit/step (was 1.0) — one 15-food
  harvest sustains a unit 150 steps.
- Constant: `FEED_INTERVAL = 100` steps — feeding pulse cadence.
- Feed amount: `N = round(TARGET_POP · num_colonies · MAINTENANCE_COST ·
  FEED_INTERVAL / HARVEST_YIELD)` clamped to `[4 · num_colonies, (w·h)//40]`,
  with `Constant: TARGET_POP = 18`, `Constant: HARVEST_YIELD = 15`.
  Equilibrium: at 4 colonies × 18 units × 0.1 = 7.2 food/step consumption vs
  48 × 15 / 100 = 7.2 food/step inflow; pulsed delivery makes population
  oscillate rather than sit at a fixed point.
- Constant: `BOOTSTRAP_FLOOR = 10` — minimum food each living colony is
  topped up to at every feeding (the keeper's dole).
- Constant: `STARVATION_MAX_KILLS = 2` per colony per step (was unbounded).
- `Maw.food_stored` initial: 120 (was 200).
- `expansion_rate` init: `uniform(0.3, 1.0)` (was `random()`), bounding the
  spawn threshold `30/rate` to [30, 100].
- Constant: `MAW_MAX_HEALTH = 500` (was 100); `Constant: MAW_REGEN = 0.5`
  HP/step when no enemy unit is adjacent.
- Constant: `RESPAWN_DELAY = 300` steps; `Constant: RESPAWN_FOOD = 50`;
  respawn genome mutation rate 0.15.
- Terrain noise: numpy only (`np.random.default_rng`); `VoxelWorld` gains an
  optional `seed` parameter (None → nondeterministic, unchanged default).
- Compatibility: `EnhancedSandKingsSimulation` (sandkings_evolution.py)
  overrides `step()` entirely and is unaffected by new step phases; it does
  inherit the new terrain and constants (fitness scale shifts — accepted).
  `sandkings_gpu.py` imports classes without subclassing `step()`; no crash
  path. Existing tests build 20×10×5 worlds — terrain gen MUST work there.

## 3. Functional Requirements (EARS)

- **T1** When `step_count % FEED_INTERVAL == 0`, the sim MUST place the feed
  amount N of FOOD voxels, each at the first AIR voxel directly above
  terrain in a random interior column, and MUST raise every living colony's
  `food_stored` to at least BOOTSTRAP_FLOOR.
- **T2** While a colony is alive with 0 units and `food_stored` ≥ the worker
  spawn cost (3), the step MUST spawn one WORKER, bypassing the spawn
  threshold and fertility roll.
- **T3** Worker AI order MUST be: (1) radius-2 food/corpse grab (existing,
  unchanged, clears any cached target); (2) step toward a cached
  `forage_target` that still holds FOOD or CORPSE; (3) scan the
  `foraging_range` box for FOOD or CORPSE and cache the nearest by Manhattan
  distance; (4) existing tunnel-dig fallback.
- **T4** When a soldier finds no enemy unit within `foraging_range`, it MUST
  chase the nearest living enemy Maw within `foraging_range` (same
  aggression roll and movement rules). `_resolve_conflicts` MUST apply each
  unit's attack to enemy Maws at Chebyshev distance ≤ 1 via
  `Maw.take_damage`. A Maw with no adjacent enemy unit MUST regain
  MAW_REGEN HP per step, capped at MAW_MAX_HEALTH.
- **T5** When a Maw's health reaches 0: every unit of that colony MUST become
  a CORPSE voxel at its position; the 3×3 area at the maw's z MUST become
  CORPSE where not GLASS/STONE; all `ownership == colony_id` MUST clear to
  −1; the colony's pheromone channel MUST zero; and a respawn MUST be
  scheduled for `step_count + RESPAWN_DELAY`.
- **T6** When a scheduled respawn is due: the dead colony's slot MUST be
  replaced in place with a fresh `Colony` using the same `colony_id` (color
  and pheromone slot follow from the id); genome = a random living
  survivor's `genome.mutate(0.15)` (a fresh randomized genome when none
  survive); position MUST respect the existing 10%-diagonal minimum distance
  from living maws; maw z = surface; `food_stored = RESPAWN_FOOD`; 3 starter
  workers.
- **T7** Starvation MUST kill at most STARVATION_MAX_KILLS units per colony
  per step.
- **T8** Terrain generation MUST produce: a 3-octave value-noise heightmap
  with per-column surface height in `[substrate+2, 0.85·depth]`; two stone
  strata bands (thickness 2) where band noise exceeds its threshold; cavern
  air pockets from thresholded 3D noise, confined between substrate+1 and
  surface−3, with SAND directly above a cavern converted to STONE (roof
  cementing, else gravity collapses them); surface food patches plus buried
  food pockets; glass walls and z=0 floor preserved; maws placed at the
  surface (`surface_z`); and post-generation `apply_gravity()` MUST be a
  no-op (settled at gen). When depth < 8, caverns MUST be skipped and bands
  clamped so generation still succeeds (20×10×5 worlds).

## 4. Behavioral Spec — feeding phase (inside `step()`)

```
When step_count % FEED_INTERVAL == 0:
    n ← feed amount (Implementation Requirements)
    Loop n times:
        (x, y) ← random interior column
        z_surface ← world.surface_z(x, y)
        If z_surface + 1 < depth and voxel[x, y, z_surface + 1] is AIR:
            set voxel[x, y, z_surface + 1] ← FOOD
    For each living colony:
        food_stored ← max(food_stored, BOOTSTRAP_FLOOR)
```

## 5. Behavioral Spec — colony death cascade

```
After combat resolution, for each colony whose maw.alive turned False:
    For each unit: set voxel[unit.position] ← CORPSE; clear units
    For (dx, dy) in 3×3 around maw at maw z:
        If in bounds and voxel not GLASS/STONE: set ← CORPSE
    ownership[ownership == colony_id] ← −1
    pheromones channel[colony_id] ← 0
    pending_respawns[colony_id] ← step_count + RESPAWN_DELAY
Then, for each due entry in pending_respawns:
    replace colonies[slot] in place per T6; delete the entry
Assert: len(colonies) is constant; every colony_id occurs exactly once
```

## 6. Acceptance (Given/When/Then)

- Given a fresh sim stepped to a feeding step, Then the world gains ~N FOOD
  voxels, each previously AIR with non-AIR directly below, and a living
  0-unit colony's food is ≥ BOOTSTRAP_FLOOR.
- Given an alive colony with 0 units and food 5, When one step runs, Then it
  has 1 WORKER.
- Given an enemy soldier adjacent to a Maw, When conflicts resolve, Then
  maw.health decreases; Given no adjacent enemy, Then it regens toward max.
- Given a Maw driven to 0 HP, Then the colony's units are corpse voxels, its
  ownership is cleared, and `pending_respawns[colony_id]` is scheduled.
- Given a due respawn with survivors, Then the slot holds a new alive Colony
  with the same id, a genome differing from the dead one, and a maw ≥ min
  distance from living maws.
- Given a worker and a lone FOOD voxel 6 away in open air, Then the food is
  harvested within 20 steps and the maw gains HARVEST_YIELD.
- Given a seeded 80×40×20 world: surface-height std > 1.5; all heights in
  bounds; ≥ 1 cavern AIR voxel strictly between substrate and surface;
  STONE present above the substrate line (strata); glass shell intact;
  `apply_gravity()` changes nothing. Given 20×10×5: generation succeeds.

## 7. Reconciliation Log

- (fill in after implementation)
