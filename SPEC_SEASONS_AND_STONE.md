# Spec: Seasons & Stone (scarcity, farming, oasis, ore, colony learning)

Layer: **Requirements** + **Behavioral** blocks. Governs: the season clock,
seasonal keeper dole, farming lifecycle, the oasis, ore generation/mining/
uses, worker AI v2, and the colony posture learner in `sandkings.py`
(+ `colony_learner.py`). T-numbers are shared with
SPEC_TERRARIUM_LIVENESS.md; this file owns **T16+**. Viewer surface:
SPEC_LIVE_VIEW.md R22–R24. Anchors: SPEC_HIVE_MONITOR.md M10.
Status: draft → implement → reconcile (log at bottom).

## 1. Defect being corrected

The terrarium is a world of abundance: the keeper's dole alone sustains
every colony forever, food requires no planning, nothing costs anything,
and the ground holds no secrets. Per the user's vision: "nothing without
cost"; long-term must beat short-term in the long term while short-term
always tempts; food should take seasons, requiring planning and safety;
the underground should hold DF-style discoveries.

## 2. Implementation Requirements (constants)

- `SEASON_LENGTH = 400`; seasons `("Flood", "Growth", "Dust", "Chill")`;
  `YEAR_LENGTH = 1600`. Season and year are DERIVED from `step_count`
  (never stored — old checkpoints resume seamlessly).
- `DOLE_FACTOR = {0: 1.0, 1: 0.75, 2: 0.5, 3: 0.25}`;
  `DOLE_RAMP = (1.0, 0.5, 0.0)` per-year floor (index `min(year, 2)`);
  CLI `--harsh` skips the ramp.
- `STORM_INTERVAL_DUST = 200` (Dust); storm rolls SKIPPED in Chill.
- `SPOIL_INTERVAL = 10`, `SPOIL_CHANCE = 0.02` (Dust only, exposed FOOD).
- Voxels: `TILLED = 7`, `CROP = 8`, `CROP_RIPE = 9`, `COPPER_ORE = 10`,
  `GOLD_ORE = 11`. TILLED/CROP/CROP_RIPE: not tunnelable, not solid.
  Ores: solid, not tunnelable.
- `SEED_COST = 5`, `CROP_TICK = 5`, `CROP_GROWDUR = 300` (60 ticks),
  `CROP_YIELD = 40`, `FARM_RADIUS = 6`, `FARM_MAX_PLOTS = 12`,
  `FARM_START_FOOD = 60`, `FARM_STOP_FOOD = 30`, `GROW_SEASONS = (0, 1)`.
- `OASIS_RADIUS = 6` (disc at (w//2, h//2), derived), `OASIS_GROWTH_MULT
  = 2`, `OASIS_FEED_BONUS = 2`.
- `COPPER_VEINS_PER_BAND = 2`, `VEIN_LENGTH ∈ [8, 16]`,
  `GOLD_CLUSTERS = 3` of 3–6 voxels, `MINE_TIME = 5`,
  `COPPER_ARMOR_HP = 10`.
- Learner (`colony_learner.py`): `LEARN_INTERVAL = 25`,
  `LEARN_RATE = 0.2`, `EPSILON_START = 0.8`, `EPSILON_FLOOR = 0.4`,
  `EPSILON_DECAY = 0.999` (per decision); `ColonyGenome.patience`
  init `uniform(0.3, 0.95)` = the TD discount γ, EVOLVABLE (MUST be in
  `mutate()`'s attr list).
- Unchanged: MAINTENANCE_COST, FEED_INTERVAL, TARGET_POP, HARVEST_YIELD,
  BOOTSTRAP_FLOOR, UNIT_CAP, WAR_CHEST, spawn costs.

## 3. Functional Requirements

- **T16 (season clock)** `season_index = (step_count // SEASON_LENGTH) % 4`,
  `year = step_count // YEAR_LENGTH`, both derived. The season tick runs
  FIRST in `step()`; on each boundary it MUST log
  `The {name} season begins (dole {pct}%)` with the ramped effective
  percentage. While Dust: storm rolls use STORM_INTERVAL_DUST and exposed
  surface FOOD voxels spoil to AIR at SPOIL_CHANCE per SPOIL_INTERVAL.
  While Chill: no storm rolls.
- **T17 (seasonal dole; amends T1)** Effective factor
  `f = max(DOLE_FACTOR[season], DOLE_RAMP[min(year, 2)])` (`--harsh`:
  ramp ignored). `_feed_terrarium` scales BOTH the base amount AND the
  lower clamp by f (dole voxels 48/36/24/12 at 4 colonies).
  BOOTSTRAP_FLOOR stays 10 and unscaled — the survival guarantee.
  OASIS_FEED_BONUS of the placed voxels land in random oasis columns.
- **T18 (worker AI v2; supersedes T3's ordering)** Priority: (1) radius-2
  grab (FOOD/CORPSE +15 → AIR; CROP_RIPE +CROP_YIELD → TILLED); (2) haul
  carried ore to maw (deposit at Chebyshev ≤ 2); (3) continue an adjacent
  valid mine (+1 progress/step; extract at MINE_TIME); (4) forage per T3
  (cached target → range scan → scout intel → step toward); (5) farm —
  only while `colony.farming` (hysteresis: on > FARM_START_FOOD, off <
  FARM_STOP_FOOD) AND (sow window open OR site in oasis): sow an adjacent
  unplanted TILLED when food ≥ SEED_COST (pay SEED_COST, voxel → CROP,
  crops[pos] = 0), else till toward the best site (surface SAND within
  FARM_RADIUS of own maw, oasis-first) while owned plots < FARM_MAX_PLOTS;
  (6) seek exposed ore within foraging_range; (7) random dig (unchanged).
  Wild food ALWAYS outranks farming (structural temptation).
- **T19 (crop lifecycle)** Single-voxel state machine on the column top:
  SAND → TILLED (till; ownership set) → CROP (sow) → CROP_RIPE (ripe) →
  TILLED (harvest, by anyone — plunder is emergent). Growth state lives
  in sparse `sim.crops: Dict[pos, ticks]`; every CROP_TICK steps each
  entry: (a) purge if voxel is no longer CROP; (b) die to SAND if the
  voxel directly above is non-AIR (burial by storm/gravity — detected
  crop-side; T12's sand conservation untouched); (c) season gate per T20;
  (d) progress += 1 (× OASIS_GROWTH_MULT in the oasis); at
  CROP_GROWDUR/CROP_TICK ticks → CROP_RIPE, entry removed.
- **T20 (season gating)** Non-oasis: crops progress only in GROW_SEASONS;
  Dust stalls them; Chill kills young crops to SAND (log once per Chill
  per colony: `The frost takes Colony {id}'s young crops`). Sowing
  (non-oasis) only when CROP_GROWDUR grow-steps remain in the current
  year's Flood+Growth window. Oasis plots are exempt from all gates.
- **T21 (farm warfare)** While at war (or on its aggression roll), a
  soldier adjacent (Chebyshev ≤ 1) to enemy-owned TILLED or CROP MUST
  raze it to SAND (one per step; consumes its action; event once per
  (war, pair): `Colony {a} razes Colony {b}'s fields!` + decision log).
  Ripe crops need no rule — the T18 mask makes them plunder.
- **T22 (oasis)** Pure positional disc, no new voxel. Effects: ×2 growth,
  all-season growth and sowing, OASIS_FEED_BONUS. `_spawn_colonies`
  places one random colony's maw on the ring at OASIS_RADIUS+1 (event:
  `Colony {id} wakes beside the oasis`) and initially keeps others ≥
  OASIS_RADIUS+4 from center; respawns respect only the normal
  min-distance — the oasis can change hands. Helper `oasis_holder()`
  (living maw within OASIS_RADIUS+2 of center, else None).
- **T23 (ore generation)** In `_generate_terrain` after strata+caverns,
  before glass: copper veins as jittered random walks inside each strata
  band converting STONE → COPPER_ORE; gold clusters at z ∈
  {substrate−2, substrate−1}. Every vein/cluster voxel MUST be hosted in
  STONE. When depth < 8: no ore (mirrors the cavern skip).
- **T24 (mining)** An ore voxel is minable iff ≥ 1 face-neighbor is AIR.
  A worker adjacent to one sets `mine_target` and spends MINE_TIME
  consecutive steps; on completion voxel → AIR, `carrying = kind`; haul
  to maw deposits `colony.ore[kind] += 1`. First successful mine of each
  kind per colony logs `Colony {id} strikes copper!/gold!` (feed +
  decision log, tracked in `colony.ore_struck`).
- **T25 (ore uses)** Copper: `Maw.spawn_unit` consumes 1 copper when
  spawning a SOLDIER if available → max_health/health = 20 +
  COPPER_ARMOR_HP (armored soldiers render copper-tinted). Gold: hoard
  sink only in this round — stored, displayed, spilled; its spend is
  RESERVED for Round 2 politics (tribute). On maw death the colony's
  stored ore scatters as re-minable ORE voxels within 3 of the maw.
- **T26 (learner)** `colony_learner.py`: per-colony tabular Q over state
  (season, food-band {0,1,2,3: <30, <200, <WAR_CHEST, ≥}, threat-band
  {0,1,2: no enemy in 15 / enemy / besieged}, farms>0, oasis-held) ×
  postures {FORAGE, FARM, RAID, FORTIFY}. Every LEARN_INTERVAL steps:
  TD(0) update with reward = Δ(food + 15·population)/interval and
  γ = genome.patience; ε-greedy (ε from EPSILON_START decaying by
  EPSILON_DECAY per decision to EPSILON_FLOOR). Posture BIASES gates,
  never overrides rules: FARM → FARM_START_FOOD × 0.75; RAID → war spawn
  mix while at war and +wealth bias reserved for Round 2 targeting;
  FORTIFY → soldiers keep within FARM_RADIUS+2 of the maw when no enemy
  in range (guard posture); FORAGE → neutral. Q-tables pickle with the
  sim; the manager screen MUST show the current posture and the learned
  best posture per current state.
  *S3/S4 amendment (SPEC_SENTIENCE): the effective learn rate is
  `LEARN_RATE * (0.5 + genome.plasticity)` and the exploration floor
  `EPSILON_FLOOR * (1.5 - plasticity)` (meta-learning); a replay memory
  (REPLAY_CAP 40) consolidates via offline TD updates during Chill
  dreams.*
- **T27 (acceptance)** The §5 unit tests plus the 3-year harsh soak
  (4800 steps, `--harsh`): population never 0 and every slot
  alive-or-pending; ≥ 1 sowing by step 800 and ≥ 1 harvest event by 1600;
  ≥ 1 colony fall in 3 years; ≥ 1 copper strike by year 1's end; every
  season boundary logged; throughput ≥ 19 steps/s.

### Compatibility (mirrors the T-spec conventions)
- Old checkpoints: `sim.crops`, `colony.farming/ore/ore_struck`, unit
  mine state, learner — ALL behind hasattr/getattr lazy guards; season/
  year/oasis are derived (zero migration). Voxel enum growth is
  append-only.
- `EnhancedSandKingsSimulation` overrides `step()` and
  `_execute_unit_ai`-equivalents: it gets NO seasons/dole/crops/mining/
  learner. Shared touchpoints are inert there: terrain ore behaves as
  STONE; the `Maw.spawn_unit` copper hook is guarded and never funded;
  the widened food mask is vacuous without crops. Tripwire test required.
- `sandkings_gpu.py` imports classes only; no crash path.

## 4. Behavioral Spec — crop growth phase (every CROP_TICK steps)

```
For (pos, ticks) in list(crops.items()):
    If voxel[pos] != CROP: del crops[pos]; continue          # purge first
    If voxel[above(pos)] != AIR: voxel[pos] ← SAND; del; continue  # buried
    If pos not in oasis:
        If season == Dust: continue                          # stall
        If season == Chill: voxel[pos] ← SAND; del; log once; continue
    ticks += OASIS_GROWTH_MULT if pos in oasis else 1
    If ticks ≥ CROP_GROWDUR / CROP_TICK: voxel[pos] ← CROP_RIPE; del
    Else: crops[pos] ← ticks
Invariant: every key of crops maps to a CROP voxel (checked by purge-first)
```

## 5. Acceptance (Given/When/Then — one per test)

- (T16) season/year derive purely from step_count; boundary logs exact
  catalog text; Dust storms roll at 200; Chill rolls none.
- (T17) placed dole ≈ 48/36/24/12 by season under --harsh; year-0 ramp
  keeps 48; the lower clamp scales.
- (T19) sow → ripe in exactly CROP_GROWDUR grow-steps; harvest pays
  CROP_YIELD and leaves TILLED; burial reverts to SAND.
- (T20) Dust stalls; Chill kills; oasis exempt (and ripens in ~150).
- (T18) worker prefers wild food over farming when both available; farms
  when range is empty and flag on; hysteresis holds at 45 food.
- (T21) at-war soldier razes adjacent enemy TILLED once, with event.
- (T22) lucky maw on the ring; others pushed out; oasis_holder() correct.
- (T23) seeded world: all copper z within band ranges, all gold at
  substrate−2/−1, counts in [20,80]/[6,18]; d=5 world has zero ore.
- (T24) mine takes MINE_TIME steps, hauls, deposits, strikes-event once.
- (T25) armored soldier 30 HP consumes 1 copper; ore spills on maw death.
- (T26) learner: rigged reward makes Q prefer FARM in a fixed state
  within 200 decisions; posture biases the farm gate; ε decays to floor;
  Q pickles.
- (T27) the 3-year harsh soak criteria.
- (compat) stripped-attrs sim steps 50× clean; Enhanced sim inert 200
  steps on ore terrain.

## 6. Reconciliation Log

- Shipped in 2.5.0 and verified by tests/test_seasons.py + the 3-year
  harsh soak (first sow @26, first harvest @180, copper strike year 1).
  Balance note from the soak: standing fields are rare (eaten/razed/
  frosted quickly) while populations pin at cap — farming works as
  pressure relief, not as visible agriculture; accepted drama.
- 2026-07-08: T26 amended by SPEC_SENTIENCE S3 (plasticity-scaled
  learning) and S4 (Chill dream replay) — see the T26 note above.
