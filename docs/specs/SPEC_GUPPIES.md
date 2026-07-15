# SPEC — Guppies (the oasis pond ecosystem)

Status: ACCEPTED + IMPLEMENTED (2026-07-14). Baseline-ON (opt-out `--no-guppies`).

## What & why

A small, self-sustaining **consumer-resource ecosystem** seeded into the oasis water **from
world-gen** — a living starting prior. Algae grows (sunlight/water), guppies eat algae and
**breed** (replication), and the pond's surplus becomes **harvestable food** the colonies forage.
A renewable food spring whose flow tracks its ecological health — and a **commons** (whoever's
nearest harvests it; INSPIRATIONS: Ostrom, *Governing the Commons*). Fits the terrarium fiction
(the kid's tank has guppies) and the closed-budget ethos (Oxygen Not Included / the water budget).

## Model (requirements)

- **State** (lazy, on the sim; plain floats → checkpoint-safe): `guppy_pop`, `algae`. Seeded on
  first tick when the gate is on (`GUPPY_SEED`, `ALGAE_SEED`) so a fresh OR resumed world gains a
  pond. Absent ⇒ the tick seeds them; gate off ⇒ never touched.
- **Cadence:** every `GUPPY_TICK` steps (cheap; O(1) dynamics + a few voxel writes).
- **Dynamics** (pure fn `guppy_dynamics(guppy, algae, water) -> (guppy, algae, catch)`):
  - `water = clamp(water_level, 0.2, 1.0)` — drought/season throttles algae (ties to the water budget).
  - `algae += ALGAE_REGROW·(ALGAE_CAP−algae)·water − GUPPY_GRAZE·guppy·(algae/ALGAE_CAP)`; clamp [0,CAP].
  - `guppy += GUPPY_BREED·guppy·(algae/ALGAE_CAP)·(1 − guppy/GUPPY_CAP) − GUPPY_DEATH·guppy`; clamp [0,CAP].
    Logistic birth, **modulated by food (algae) and density** — guppies mate when fed and there's room.
  - `catch = int(GUPPY_YIELD_FRAC·guppy)` when `guppy > GUPPY_YIELD_MIN`, else 0 — the harvestable surplus.
- **Harvest = FOOD voxels in the oasis** (reuse the existing forage path; no new unit AI): the sim
  deposits `min(catch, free oasis food slots)` FOOD voxels at oasis surface-AIR cells (mirrors the
  keeper dole), capped at `GUPPY_FOOD_CAP` standing guppy-food voxels; `guppy_pop` drops by what was
  actually deposited (fish removed from the pond → the commons pressure). Colonies forage them normally.

## Contracts

- **Require:** gate on; `water_level` in [0,1]; oasis disc from `in_oasis`.
- **Guarantee:** `guppy_pop, algae ∈ [0, cap]` every tick (clamped, never NaN); standing guppy-food
  voxels ≤ `GUPPY_FOOD_CAP`; the pond persists (positive equilibrium) at healthy water and RECOVERS
  after a crash; declines (not necessarily to 0) under drought.
- **Maintain:** dynamics are deterministic given (guppy, algae, water); voxel placement draws the
  python RNG only when the gate is on (battery byte-identical with gate off).
- **Assert:** pinned by `tests/test_guppies.py` — a permutation battery over starting stocks
  (boundedness, persistence, post-crash recovery, drought decline) + a gate-off no-op/no-RNG guard.

## Gating (baseline-ON, opt-out)

`GUPPIES_ENABLED` module-default **False** (battery byte-identical; `_guppy_tick` returns immediately,
draws no RNG, seeds nothing). The game entrypoint flips it **True unless `--no-guppies`**. Registered
in `run_tests._GATE_NAMES`.

## Observability

- **Drama feed** on pond state transitions (throttled): booming → "the oasis shoals silver with
  guppies"; collapse → "the guppy shoal thins to nothing"; recovery → "guppies return to the shallows".
  Tinted in the HUD (`live_view.EVENT_TINTS`: shoal/guppies → watery blue).
- **HUD readout** (`live_view.build_hud_entries`): a "Pond: N guppies, algae M" line under the Oasis
  line (blue when healthy ≥20, amber when thin), shown only when the pond exists. Verified headlessly.

## Files

- `sandkings.py` — `GUPPY_*` constants, `guppy_dynamics` (pure), `_guppy_tick` (dynamics + deposit +
  drama), the `step()` call, entrypoint gate-flip + `--no-guppies`.
- `run_tests.py` — `GUPPIES_ENABLED` in `_GATE_NAMES`.
- `tests/test_guppies.py` — the dynamics battery + gate-off guard.

## Open / future

- **Spatial spread** to HYDRO water (rivers/lakes) when `--hydro` is on (today: oasis pond only).
- **Predators** (a fish that eats guppies) for a 3-tier chain; **over-harvest collapse** as an explicit
  commons-tragedy signal the player can see.
