# SPEC — Forageable flora: fishing + perennial shrubs (early food)

Status: IN PROGRESS (War & Survival arc, Phase 1). Baseline-ON, opt-out. Part of the food web
(SPEC_FOOD_WEB); the survival half of the arc whose planning test is SPEC_WINTER.

## Why

Early food today is essentially the keeper dole plus the `BOOTSTRAP_FLOOR=10` no-starve floor. The
guppy pond only auto-surfaces FOOD inside the oasis disc (so only the oasis-holder benefits), there is
**no deliberate fishing**, and **no edible wild flora** (trees are timber; only sown crops are food).
The arc needs a reliable, un-RL-gated early food source that any colony near water can work, plus a
foraged plant food — both of which **recede in Chill** so the Phase-2 winter test still bites.

## FL1 — Fishing (deliberate aquatic action)

- Gate `FISHING_ENABLED` (module default False → battery byte-identical; entrypoint flips on; opt-out
  `--no-fishing`; registered in `run_tests._GATE_NAMES`).
- `_fish_step(unit, colony) -> bool` (beside `_snare_tick`): a WORKER 6-adjacent to a `WATER` voxel
  (reuse the `_water_adjacent` neighbor scan) with the shared `guppy_pop > FISH_MIN_STOCK` surfaces one
  `FOOD` voxel in an adjacent AIR cell and draws `FISH_YIELD` guppies out of the **shared** pond (a
  commons — heavy fishing thins the shoal for everyone, and drought already throttles it). The worker
  eats the deposited FOOD next tick via the existing radius-2 grab loop — no new credit path.
- Keys off the `WATER` voxel, **not** the oasis disc, so a colony at any water body can fish (generalizes
  past the oasis-holder). WATER voxels exist wherever hydro pools (baseline-on); with hydro off there are
  no WATER voxels and the guppy pond's own oasis FOOD still serves the centre, so fishing adds reach
  without double-dipping.
- **Chill scarcity**: in Chill (`season_index()==3`) a fish only lands on an RNG roll `< FISH_CHILL_SCARCITY`
  — the shoal is under ice, so winter fishing is unreliable (the Phase-2 hook). All RNG is inside the gate.
- Worker AI: inserted as priority step **(4b) Fish**, between forage (4) and farm (5), so wild water food
  still outranks farming (matches "wild food always outranks farming").
- Gating: first line `if not FISHING_ENABLED: return False` → pure no-op, no RNG, no state when off.

Constants: `FISH_YIELD=3` (guppies removed per catch), `FISH_MIN_STOCK=20.0` (no fishing below this —
let the shoal rebuild, mirrors `GUPPY_YIELD_MIN`), `FISH_CHILL_SCARCITY=0.25`.

## FL2 — Perennial shrubs / berries (forageable flora)

- Gate `SHRUBS_ENABLED` (module default False; entrypoint flips on; opt-out `--no-shrubs`; in `_GATE_NAMES`).
- Voxel types appended: `SHRUB=19` (growing, inedible) and `SHRUB_RIPE=20` (edible berries). Appending
  changes no existing enum value or comparison; `is_solid`/`is_tunnelable` untouched (surface flora, like
  crops, blocks nothing).
- `self.shrubs: Dict[(x,y,z), int]` — a lazily-created ripeness registry (like `_rot`/`crops`), so a
  neutral run never allocates it and checkpoints stay byte-identical.
- `_shrub_tick` (beside `_cricket_tick`, called in `step()` beside the other guild ticks): early-returns
  when off or off-cadence. In **Growth** (`season_index()==1`) seeds up to `SHRUB_CAP` `SHRUB` voxels on
  random surface sand outside farm plots; advances ripeness; at `SHRUB_GROWDUR` sets the voxel `SHRUB_RIPE`.
  In **Chill** (`season_index()==3`) converts standing `SHRUB_RIPE`→`AIR` and marks the root dormant (kept
  in the registry, no regrow until Growth) — the die-back that keeps winter lean.
- Forage integration (reuse): add `SHRUB_RIPE` to the `_find_food_target` mask and the radius-2 grab
  tuple. On harvest, **do not delete the bush** — reset its registry ripeness to 0 so it **regrows in
  place** (perennial). Yields `SHRUB_YIELD` food.
- Gating: `_shrub_tick` early-returns when off → `self.shrubs` never created, no `SHRUB*` voxel ever
  placed → the added `_find_food_target` OR-term and grab-tuple entry match nothing (the crickets
  precedent) → `argwhere`/grab results identical → battery byte-identical.
- Display: `live_view` maps `SHRUB`/`SHRUB_RIPE` to glyphs/tiles so bushes are visible (display-only,
  not a battery concern).

Constants: `SHRUB_TICK=20`, `SHRUB_SEED_P` (per-tick seed probability in Growth), `SHRUB_CAP` (max
standing bushes), `SHRUB_GROWDUR` (ticks green→ripe), `SHRUB_YIELD`.

## Acceptance

- `tests/test_fishing.py`: a worker by a WATER voxel with a stocked pond surfaces FOOD and draws down
  `guppy_pop` by `FISH_YIELD`; a non-oasis colony gains food; Chill reduces the catch rate; gate-off is a
  no-op consuming no RNG.
- `tests/test_shrubs.py`: a bush grows green→ripe in Growth; a forager eats a ripe bush (+`SHRUB_YIELD`)
  and the bush **regrows** (stays registered); Chill clears the ripe voxels; gate-off places no voxels
  and is byte-identical.
- Full battery byte-identical with both gates off.
