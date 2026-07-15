# Spec: Water Engineering — persistent flow simulation + hydro tech tree (SPEC_HYDRO)

Layers: **Structural** (a WATER voxel + a water-depth field + constants + a tech tree),
**Behavioral** (the flow tick, the dig behaviors, boats, irrigation, flood relief),
**Requirements** (the identity-at-neutral guarantee). Governs `sandkings.py` (the flow
sim, `_grow_crops`, the flood tick, `_try_build`, `_step_toward`), `tech.py` (the tree +
constants), and the renderers (`live_view.py`, `dashboard.py`). Distinct from
`SPEC_HYDRO_HAND.md` (the KEEPER's transient water hand); this is the COLONY-learned,
persistent water world.

## Motivation (HY0)
The terrarium had no persistent spatial water — only a global `water_level` scalar and a
transient per-flood cell set. Dug basins held nothing. Colonies should LEARN water
engineering as a tech tree and build man-made rivers, reservoirs/lakes that HOLD water,
and farming dikes — for irrigation and flood alleviation — and spawn should cross the
water by boat. The user chose a full per-cell flow simulation and a small hydro tree.

## Requirements
- **HY1 — persistent water.** `VoxelType.WATER` (18): non-solid, non-tunnelable (so it
  blocks gravity, `tunnel()`, and walking). Backed by a **lazily-allocated numpy float32
  depth field** `sim.water` (shape = `world.voxels.shape`), the single source of truth;
  `None` until water first appears. `VoxelWorld.terrain_z()` = ground height excluding WATER.
- **HY2 — conservative flow.** `_hydro_tick()` (every `HYDRO_TICK`): gravity (fall into a
  passable cell below, cap `HYDRO_CAP`) → lateral equalization (move `HYDRO_FLOW_RATE·Δhead/2`
  from higher to lower hydraulic head `z+depth` into passable ±x/±y neighbours, symmetric
  via `np.roll` so total volume is conserved exactly) → oasis SOURCE + EVAPORATION (gated,
  HY7) → edge sinks → mirror AIR↔WATER by `HYDRO_SETTLE_MIN`. **Pure numpy, ZERO RNG.**
- **HY3 — the hydro tech tree** (`tech.py`): `irrigation → aqueduct → reservoir` (prereqs
  `farming → irrigation → aqueduct`). Learned by DOING (`_practice` inside each dig
  behavior) on top of prereq-research diffusion (`_tech_tick`). Proficiency (`_prof`)
  scales size/rate. All acquisition RNG-free.
- **HY4 — dig behaviors** (in `_try_build`, before the castle branch): `_reservoir_step`
  (basin, filled by the flow sim), `_channel_step` (SAND→AIR trench from the oasis so water
  routes toward the nest), `_dike_step` (raised SAND dike ring to pond irrigation water).
  Each gated on the water system being on AND the relevant tech; `_practice`s it.
- **HY5 — irrigation.** In `_grow_crops`, a CROP 6-adjacent to standing WATER gains
  `HYDRO_IRRIG_GROWTH` extra growth (`_water_adjacent`). A crop under water is irrigated,
  not buried.
- **HY6 — flood alleviation.** Tech dikes part the flood via the existing dam rule
  (`surface_z > water_line`). A house that has learned `reservoir` takes reduced flood
  damage (`_flood_damage`, its basins soak the surge by `HYDRO_RESERVOIR_ABSORB`).
- **HY7 — boats.** In `_step_toward`, a step blocked by WATER: an already-rafted unit
  passes; else it boards a raft if the house has timber (one wood); it dismounts on dry
  solid ground in CALM conditions. Distinct from the reactive flood-raft (which persists
  while a flood is active anywhere, cleared on recede) via the flood-active check.
- **HY8 — render.** WATER glyph `≈` + blue in `live_view.GLYPHS`/`build_voxel_palette`
  and `dashboard._palette_lut`. Underground is occluded in top-down; the owned-air X-ray
  reveals tunnels, and WATER (non-AIR) is never mistaken for a tunnel.

## Identity / gating (HY9 — load-bearing)
Default-neutral: the field is lazily allocated and `HYDRO_SOURCES_ENABLED` gates the
oasis SOURCE + EVAPORATION + the dig behaviors, so a sim with no water and no tech is
byte-identical (the 48-suite regression battery stays green). The flow sim is pure numpy
with **no new RNG in any neutral-reachable path** — never resize an existing
`random.choice` list, never draw a gated feature's RNG at neutral (the determinism
guardrail from the structures wave). `HYDRO_SOURCES_ENABLED` is registered in
`run_tests.py._GATE_NAMES` so suites reset it.

## Baseline (HY10)
Water engineering is a BASELINE feature of the runnable game: `sandkings.py --live` and
`dashboard.py` turn `HYDRO_SOURCES_ENABLED` on by default (opt-out `--no-hydro`). The
module constant stays False ONLY as a test-harness isolation switch, never as a
user-facing gate.

## Constants (`tech.py`)
`HYDRO_TICK`, `HYDRO_CAP`, `HYDRO_FLOW_RATE`, `HYDRO_SETTLE_MIN`, `HYDRO_SOURCE_LEVEL`,
`HYDRO_EVAP_RATE`, `HYDRO_IRRIG_GROWTH`, `HYDRO_CHANNEL_LEN`, `HYDRO_RESERVOIR_RADIUS`,
`HYDRO_RESERVOIR_DEPTH`, `HYDRO_RESERVOIR_ABSORB`, `HYDRO_SOURCES_ENABLED`. All
default-neutral / first-pass; a tuning pass balances flow vs evaporation vs basin size.

## Acceptance (`tests/test_hydro.py`)
Lazy/neutral identity; volume conservation; gravity; lateral settle; voxel mirror;
non-solid/non-tunnelable; oasis spring fills when enabled; reservoir dig gated + practices;
irrigation out-grows a dry crop; reservoir flood-damage reduction; boat board/cross/dismount;
render. Plus the full 48-suite battery byte-identical at neutral.

## Known open (tuning, not defects)
Balance constants are first-pass. Tunnelling (the idle dig that feeds the underground
warren the X-ray reveals) is still a low-priority idle behaviour — a busy economy rarely
reaches it, so warrens are sparse; promoting it to a proactive designated-digger (as
castles were promoted) is the next step for visible tunnel networks.
