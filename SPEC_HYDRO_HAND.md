# SPEC: The Hand's Water & Seeds (Phase 2 / Hydro-Hand) — HH1–HH5

Two new keeper "hand" verbs that reuse the existing flood + crop systems.
Water rewards terraforming for free (the flood fill already parts around any
column raised above the water line — dams shelter, dug channels drain).

## HH1 — `keeper_water(x, y, big=False)`
A keeper water source on its own track (getattr-guarded, pickled):
`kw_center=(x,y)`, `kw_big`, `kw_until = step + (WATER_FLOOD_DUR if big else
WATER_RAIN_DUR)`. `_hand_stayed`-gated (PS5). Logs a rain vs deluge line.
`_water_cells(cx, cy, radius, rise)` is a 4-connected fill from the center to
`radius`, inundating a column only if `surface_z <= surface_z(center) + rise`
(the same dam rule as `_compute_flood_cells`) — raised banks block it, dug/low
ground conducts it. Constants: `WATER_RAIN_RADIUS 5`, `WATER_FLOOD_RADIUS 12`,
rain `rise 0` / deluge `rise FLOOD_RISE`.

## HH2 — `_keeper_water_tick()` (each step, non-fatal both ways)
While `kw_until > step`, compute `kw_cells = _water_cells(...)` and:
- **irrigation (both intensities)** — per cell: surface `SAND` → `TILLED`
  (prob `WATER_TILL_P 0.15`); a surface `CROP`/`CROP_RIPE` gets `WATER_CROP_BOOST`
  (2) extra growth ticks via `_crops()`; occasional fertile `FOOD` in the AIR
  above (prob `WATER_FOOD_P 0.02`).
- **deluge only (`big`)** — each exposed unit whose (x,y) is in `kw_cells` takes
  `FLOOD_DAMAGE` via `_weather_kill` (sheltered/underground units and those
  behind a dam are simply not in the cells → safe). Rain never drowns.
Store `kw_cells` on the sim for rendering. Called from `step()` at the weather
phase.

## HH3 — `keeper_seed(x, y)`
Sow up to `SEED_COUNT` (12) crops in a small radius: a surface `SAND` or
`TILLED` voxel becomes `CROP` and joins `_crops()` at growth 0. `_hand_stayed`-
gated. Logs "The keeper scatters seeds across the sand". A Gift — the colonies
then tend and harvest via the existing crop lifecycle (T19).

## HH4 — Surfaces
- Endpoints `POST /api/keeper/water {x, y, big}` and `POST /api/keeper/seed
  {x, y}` (default x/y to world center).
- Dashboard: Gifts group gains **Seeds** + **Rain**; Wrath gains **Deluge**.
- Live view: keys `w` rain / `d` deluge / `j` seeds (at the look cursor); legend
  + HUD help updated; the weather line shows "rain"/"deluge" while `kw_until`
  runs; the `kw_cells` overlay reuses the flood-cell render (blue wash).
- `build_state` weather list gains "rain"/"deluge" from `kw_until`+`kw_big`.

## HH5 — Acceptance (tests/test_hydro_hand.py)
- Rain over a flat maw tills sand and boosts a crop's growth, and drowns NO
  unit; a deluge over an EXPOSED unit on open ground drowns it, but an
  identical unit sheltered behind a raised bank (a column above the water line)
  is spared (terraforming rewarded).
- `keeper_seed` turns sand/tilled into tended crops.
- A bound keeper (`keeper_bound`) can do neither (PS5).
- state pickles; `EnhancedSandKingsSimulation.step` stays inert
  (`_keeper_water_tick` not in its co_names).

## Status / Reconciliation
- Drafted 2026-07-10; implemented the same session (Phase 2 of the closed-biome
  arc). Reuses `_compute_flood_cells`' dam rule, `_weather_kill`, `FLOOD_RISE`/
  `FLOOD_DAMAGE`, and the `_crops()` lifecycle.
