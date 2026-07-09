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
- Constant: `UNIT_CAP = 30` — per-colony population cap on the normal spawn
  gate (the bootstrap spawn T2 is exempt by construction: it fires at 0
  units). The Enhanced evolution sim keeps its own separate cap of 50.
- `Maw.food_stored` initial: 120 (was 200).
- `expansion_rate` init: `uniform(0.3, 1.0)` (was `random()`), bounding the
  spawn threshold `30/rate` to [30, 100].
- Constant: `MAW_MAX_HEALTH = 500` (was 100); `Constant: MAW_REGEN = 0.5`
  HP/step when no enemy unit is adjacent.
- Constant: `RESPAWN_DELAY = 300` steps; `Constant: RESPAWN_FOOD = 50`;
  respawn genome mutation rate 0.15.
- Terrain noise: numpy only (`np.random.default_rng`); `VoxelWorld` gains an
  optional `seed` parameter. When `seed=None`, the generator is derived from
  the global NumPy stream so `np.random.seed()` in tests makes terrain
  reproducible; unseeded production runs stay random.
- Compatibility: `EnhancedSandKingsSimulation` (sandkings_evolution.py)
  overrides `step()` entirely and is unaffected by new step phases; it does
  inherit the new terrain and constants (fitness scale shifts — accepted).
  `sandkings_gpu.py` imports classes without subclassing `step()`; no crash
  path. Existing tests build 20×10×5 worlds — terrain gen MUST work there.

## 3. Functional Requirements (EARS)

Requirement IDs are stable (they are cited from commits and logs); the list
is in numeric order.

- **T1** When `step_count % FEED_INTERVAL == 0`, the sim MUST place the feed
  amount N of FOOD voxels, each at the first AIR voxel directly above
  terrain in a random interior column, MUST raise every living colony's
  `food_stored` to at least BOOTSTRAP_FLOOR, and MUST log the feeding to
  the event feed (see the T9 event catalog). *(Amended by T17: N and its
  lower clamp scale by the seasonal dole factor —
  SPEC_SEASONS_AND_STONE.md.)*
- **T2** While a colony is alive with 0 units and `food_stored` ≥ the worker
  spawn cost (3), the step MUST spawn one WORKER, bypassing the spawn
  threshold and fertility roll.
- **T3** Worker AI order MUST be: (1) radius-2 food/corpse grab (existing,
  unchanged, clears any cached target); (2) step toward a cached
  `forage_target` that still holds FOOD or CORPSE; (3) scan the
  `foraging_range` box for FOOD or CORPSE and cache the nearest by Manhattan
  distance; (4) existing tunnel-dig fallback. Directed movement steps
  toward the target through AIR (walk) or SAND (tunnel); when the diagonal
  is blocked it falls back to single-axis steps. *(Ordering superseded by
  T18 worker AI v2 — SPEC_SEASONS_AND_STONE.md — which inserts hauling,
  mining, and farming branches around this forage core.)*
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
  from living maws; the maw sits on the surface at `surface_z + 1` (clamped
  to depth−1); `food_stored = RESPAWN_FOOD`; 3 starter workers.
- **T7** Starvation MUST kill at most STARVATION_MAX_KILLS distinct units
  per colony per step.
- **T8** Terrain generation MUST produce: a 3-octave value-noise heightmap
  with per-column surface height in `[substrate+2, 0.85·depth]`; two stone
  strata bands (thickness 2) where band noise exceeds its threshold; cavern
  air pockets from thresholded 3D noise, confined between substrate+1 and
  surface−3, with SAND directly above a cavern converted to STONE (roof
  cementing, else gravity collapses them); surface food patches plus buried
  food pockets; glass walls and z=0 floor preserved; maws placed on the
  surface at `surface_z + 1` (clamped to depth−1); and post-generation
  `apply_gravity()` MUST be a no-op (settled at gen). When depth < 8,
  caverns MUST be skipped and bands clamped so generation still succeeds
  (20×10×5 worlds).
- **T9** (Round B) The sim MUST keep an event feed `self.events` (deque of
  `(step, message)`, maxlen 50). A Maw siege is announced when a Maw is
  damaged while at full health (one announcement per healed-and-re-besieged
  spell). Console prints may phrase things differently; the feed text below
  is authoritative for the HUD. `get_status()` remains the plain console
  summary (alive colonies only); WAR/DEAD/respawn presentation is the live
  HUD's job (SPEC_LIVE_VIEW.md R7a/R15).

  **Event catalog** (emitter → exact feed text):
  | Emitter | Feed text |
  |---|---|
  | `_feed_terrarium` | `Keeper scatters {placed} food` |
  | `_apply_maw_siege_damage` | `Colony {a} besieges Colony {b}!` |
  | `_check_maw_deaths` | `Colony {id} has fallen!` |
  | `_respawn_colony` | `A new colony {id} arrives` |
  | war-footing transition | `Colony {id} marches to war!` |
  | storm start / end | `A sandstorm rises!` / `The sandstorm passes` |
  | maw flight start | `Colony {id}'s Maw flees!` |
  | live viewer K key | `The keeper preserves the terrarium` |
- **T10** (Round D — war parties) `Constant: WAR_CHEST = 400`. While a
  colony's `food_stored` > WAR_CHEST it is **at war**: its spawn mix flips
  soldier-heavy (the T11 mix: 0.30 worker / 0.60 soldier / 0.10 scout,
  vs peacetime 0.60 / 0.25 / 0.15), and its soldiers' maw-siege targeting
  ignores `foraging_range` (they march across the map). The transition into
  war MUST log to the event feed (once per transition). Hysteresis: war
  ends only when food falls below WAR_CHEST/2. Maw health is clamped at 0.
  *Rationale:* soaks showed rich colonies hoarding unboundedly with zero
  sieges, and threshold flapping without hysteresis; wealth must convert
  into drama.
- **T11** (Round F — scouts) Scouts join the spawn mix per the shares in
  T10. Scout AI: (a) if an enemy unit is within SCOUT_ALARM_RANGE (5,
  Manhattan), the scout MUST deposit a DANGER pheromone (strength 2.0)
  at its position and flee (up to 2 AIR moves away); (b) otherwise it
  surveys — scanning 2 × foraging_range and caching the nearest
  food/corpse find of the step into `colony.known_food` (deduped, cap
  KNOWN_FOOD_CAP = 8; intel accumulates across steps) — and wanders fast
  (up to 2 random AIR moves per step; scouts do not tunnel). Workers whose
  own scan fails MUST pull the nearest still-valid entry from
  `colony.known_food` (stale entries dropped on read).
  *Rationale:* closes the v1.0 known limitation "Scout units defined but
  not spawned" and feeds the DANGER overlay.
- **T12** (Round G — sandstorms) `Constant: STORM_INTERVAL = 600`,
  `Constant: STORM_CHANCE = 0.5`, `Constant: STORM_DURATION = 25`,
  `Constant: STORM_COLUMNS_FRACTION = 1/50` (surface columns disturbed per
  storm step). Every STORM_INTERVAL steps, with probability STORM_CHANCE
  and only while no storm is active, a storm begins: `sim.storm_until =
  step + STORM_DURATION` and a per-storm prevailing wind direction (unit
  x/y vector) is chosen. While a storm is active, each step MUST transport
  sand: for ~`w·h·fraction` random interior columns whose surface voxel is
  SAND above the substrate, the top sand voxel moves to the top of the
  downwind neighbor column (±1 jitter on the axis perpendicular to the
  wind), and gravity runs each storm step so drifts settle. Sand is moved,
  never created or destroyed; whatever a drift covers stays in place,
  buried but diggable. Start and end MUST be logged (T9 catalog). The
  viewer renders the storm haze (SPEC_LIVE_VIEW.md R21). *(Amended by
  T16: the roll interval is seasonal — 200 in Dust, no rolls in Chill —
  SPEC_SEASONS_AND_STONE.md.)*
- **T13** (Round H — persistence) `save_checkpoint(sim, path) -> int` MUST
  pickle the entire simulation into a sqlite table
  `checkpoints(id, step, saved_at, state BLOB)`; `load_checkpoint(path)`
  MUST return the latest checkpoint's sim, or None when the file or table
  has none. CLI: `--persist [DB]` (default path `terrarium.db`) resumes
  from the db when it exists (else starts fresh) and autosaves on exit in
  both live and GIF modes; in live mode the `K` key saves a snapshot on
  demand and logs to the event feed (T9 catalog). Neural init
  (`--use-neural`) applies only to fresh sims — resumed sims keep their
  evolved brains. Round-trip MUST preserve step_count, voxels, ownership,
  colonies (units, food, maw HP), pending respawns, and the event feed.
- **T14** (Round J — outcome fitness) The maw-siege damage pass MUST live in
  `SandKingsSimulation._apply_maw_siege_damage()` so both the base
  `_resolve_conflicts` and `EnhancedSandKingsSimulation.step` share it.
  The Enhanced (evolution) step MUST run siege damage, maw regen, and the
  death cascade — but never `_process_respawns`, so elimination is terminal
  during evaluation. `SandKingsMapElites.get_fitness` MUST be
  outcome-based: enemies_eliminated (500) and survived (200) dominate;
  enemy_kills (2.0) next; population/territory/survival_time are
  tie-breakers (0.1 / 0.01 / 0.05).
  *Rationale:* closes BATTLE_SYSTEM_V2 Next Step 4 (time-based →
  outcome-based scoring).
- **T15** (Round K — maw migration) `Constant: MAW_MIGRATE_HEALTH = 0.4`
  (fraction of max HP), `Constant: MAW_MIGRATE_COST = 2.0` (food per step
  of flight). While a living Maw's health < MAW_MIGRATE_HEALTH ×
  MAW_MAX_HEALTH, food ≥ cost, and an enemy unit is within
  `foraging_range`: the Maw MUST crawl one voxel per step directly away
  from the nearest enemy (through AIR, or tunneling SAND; z unchanged;
  never into walls; a blocked diagonal falls back to single-axis steps;
  an attacker sharing the Maw's cell yields a random escape direction),
  paying MAW_MIGRATE_COST food per move; its new cell is carved AIR with
  colony ownership. The first move of a flight MUST log to the event feed
  (T9 catalog); the flight flag clears once health recovers to
  ≥ MAW_MIGRATE_HEALTH or no threat remains in range.
  *Rationale:* closes the v1.2 roadmap item "Maw migration".

### Amendments by SPEC_POLITICS.md (Round 2)

- **T4/T15/T11**: soldier targeting, maw-migration threat scans, and scout
  alarms iterate HOSTILE colonies only (`politics.hostile`, P9) — allied
  and truced units pass safely.
- **T5/T6**: the death cascade also clears the fallen colony's treaties,
  war targets, and grudges (P12); respawns receive the asymmetric
  reputation shadow.
- **T9**: the event catalog gains the P13 political rows (truce strike/
  lapse, betrayal, targeted war declaration — which REPLACES "marches to
  war" — tribute dispatch/accept/perish/spurn, coalition rise/dissolve,
  restless peace, field raids).
- **T10**: war footing now selects a single target (P5); coalition members
  mobilize at half the chest; cross-map sieges reach only the target.

### Scope note — neural systems

Neural mating (5% roll between adjacent enemy soldiers, offspring joining
the larger colony when its food > 10), dead-soldier folding, and weight
pruning also run inside `step()`/`_resolve_conflicts` but are governed by
SPEC_NEURAL_ACTIVATION_TRACKING.md, not re-specified here.

## 4. Behavioral Spec — feeding phase (inside `step()`)

```
When step_count % FEED_INTERVAL == 0:
    n ← feed amount (Implementation Requirements); placed ← 0
    Loop n times:
        (x, y) ← random interior column
        z_surface ← world.surface_z(x, y)
        If z_surface + 1 < depth and voxel[x, y, z_surface + 1] is AIR:
            set voxel[x, y, z_surface + 1] ← FOOD; placed += 1
    For each living colony:
        food_stored ← max(food_stored, BOOTSTRAP_FLOOR)
    log event "Keeper scatters {placed} food"; return placed
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
Invariant (by construction, not a runtime assert): len(colonies) is
constant and every colony_id occurs exactly once
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
- (T7) Given negative food and many units, at most STARVATION_MAX_KILLS die
  in one step — implicit in every soak's gradual declines.
- (T9) Given a feeding step, the feed contains a `Keeper scatters` entry
  (`test_hud_event_feed` asserts HUD projection; feed assertions run inline
  in soaks).
- (T10) Given food > WAR_CHEST, When a step runs, Then the colony is at war
  and the declaration is logged once per transition; Given food dropping to
  10, war ends (`test_war_footing_triggers_and_logs`). Given an at-war
  soldier and a distant enemy maw, it marches beyond foraging_range
  (`test_war_soldier_marches_beyond_foraging_range`).
- (T11) Given a scout and lone food beyond worker range, the find enters
  `known_food` and a worker adopts it (`test_scout_surveys_food_into_colony_intel`);
  Given an enemy within 5, the scout deposits DANGER and flees
  (`test_scout_alarm_deposits_danger_and_flees`); stale intel purges on read
  (`test_stale_known_food_dropped`).
- (T12) Given an active storm, terrain changes, total sand count is
  conserved, and the world stays gravity-settled
  (`test_storm_transports_sand_and_stays_settled`); rise/pass events fire
  and the storm ends (`test_storm_lifecycle_events`).
- (T13) Given a saved sim, load returns the latest checkpoint preserving
  voxels/ownership/colonies/respawns/events and it keeps stepping
  (`test_checkpoint_roundtrip`, `test_checkpoint_roundtrip_neural`).
- (T14) Given a conqueror phenotype vs a slow survivor, the conqueror
  scores higher (`test_outcome_fitness_dominates_time`); Given a maw at
  1-hit HP in an Enhanced sim, elimination is terminal — no respawn
  (`test_enhanced_sim_maw_sieges_are_terminal`).
- (T15) Given a wounded maw with an adjacent attacker, it crawls away,
  pays MAW_MIGRATE_COST, and logs once per flight
  (`test_wounded_maw_flees_attacker`); healthy maws hold ground
  (`test_healthy_maw_stays_put`).

## 7. Reconciliation Log

- 2026-07-08 (spec one-over) — Audit repair: T10's stale "70% soldier" mix
  corrected to the implemented T11 shares (0.30/0.60/0.10 at war); T6/T8
  now state `surface_z + 1` placement; T9 gained the authoritative event
  catalog and the simplified siege-announce rule (the regen/besieger-death
  re-announce variant was never implemented and is dropped); T12 records
  storm non-overlap, sand conservation, and perpendicular-axis jitter; T15
  records the single-axis fallback and same-cell escape (added when the
  flaky randomized-diagonal movement was fixed); UNIT_CAP = 30 specced and
  named in code; rationale prose separated from normative clauses;
  acceptance scenarios added for T7 and T9-T15 citing their tests; scope
  note added deferring neural systems to SPEC_NEURAL_ACTIVATION_TRACKING.md.
  Also: `VoxelWorld(seed=None)` now derives from the global NumPy stream so
  seeded tests get reproducible terrain (a 1-in-5 suite flake).

- 2026-07-07 (night rounds G-K) — T12 (sandstorms; non-overlap made explicit
  in code, sand conservation tested), T13 (pet-mode persistence; verified
  save-at-25 / resume / save-at-50 across real processes), T14 (outcome
  fitness; siege pass extracted to `_apply_maw_siege_damage`, Enhanced sims
  cascade deaths but never respawn), and T15 (maw migration) all implemented
  as specced. Grand soak, 4000 steps with every system live: recent-50 event
  mix 12 sieges / 14 feedings / 2 wars / 17 maw flights / 4 storms / falls
  and arrivals; all slots alive-or-pending. N10 (soldier GRU memory) lives
  in SPEC_NEURAL_ACTIVATION_TRACKING.md. Remaining roadmap items across the
  docs were either shipped or closed with rationale (README_SANDKINGS.md
  Roadmap: Done / Out of scope / Open research).

- 2026-07-07 (drama rounds) — T9 (event feed), T10 (war parties with
  WAR_CHEST/2 hysteresis and 0-clamped maw HP), and T11 (scouts) implemented
  and soak-verified: war soak 12 sieges / 4 falls / 6 declarations in 3000
  steps; scout soak 2500 steps with active surveying, shared intel, and 7
  falls — all slots alive-or-pending throughout. Note: at-war raids apply to
  rule-based soldiers; neural-mode soldiers keep their learned policy
  (accepted — war pressure still arrives via the enemy's rule-based raids).
- 2026-07-07 — Implemented as specced, with notes:
  - Maws sit ON the surface (`surface_z + 1`, clamped to depth−1) rather than
    buried at mid-depth; visible in TOPDOWN immediately.
  - Terrain noise uses one generic `value_noise(shape, cells, rng)` for both
    2D and 3D instead of separate helpers; `box_blur` wraps at edges (fine
    for noise).
  - Starvation now samples distinct units (fixes a pre-existing bug where
    `random.choice` in a loop could pick the same unit twice, double-crediting
    the +2 salvage).
  - The worker's directed-forage move counts as its action for the step (no
    random dig on top of it).
  - Soldier maw-siege movement reuses `_step_toward` (walks air, tunnels
    sand), so sieges can dig to a buried maw.
  - Acceptance: 9/9 terrarium tests, 14/14 viewer tests, 6/6 neural tests,
    3000-step soak (colonies alive-or-pending throughout, populations
    oscillating, falls + arrivals observed).
