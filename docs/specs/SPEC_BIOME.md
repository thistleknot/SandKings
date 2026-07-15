# SPEC: The Closed Biome & the Panel (Phase 3) — BI1–BI7

The terrarium is a sealed system. Beyond the in-tank "hand", the keeper has a
PANEL behind the glass — an aquarium diffuser the creatures can never reach —
that sets a global WATER budget and the hours of SUNLIGHT. Weather EMERGES from
that budget instead of firing at random, and the panel keeps working even after
the terrarium turns on its god (the hand is bound; the sun is not).

Design invariant: all biome modulation is **default-neutral**. At the default
`water_level 0.6` / `sun_hours 12` nothing changes vs today (dole, crop growth,
weather), so every existing test stays green. The biome only bites at the
extremes the keeper (or the emergent cycle) drives it to.

## BI1 — Panel state
Getattr-guarded, pickled sim fields: `water_level` (0..1, default
`WATER_LEVEL_DEFAULT 0.6`) — the free water; `water_target` (0..1, default 0.6)
— the reservoir set point the keeper dials; `sun_hours` (default
`SUN_HOURS_DEFAULT 12`, clamped `SUN_MIN 4`..`SUN_MAX 20`) — day length.

## BI2 — The panel verbs (behind the glass; survive the turning)
`keeper_set_water(level)` sets `water_target = clip(level,0,1)`;
`keeper_set_sun(hours)` sets `sun_hours = clip(hours, SUN_MIN, SUN_MAX)`. These
are NOT `_hand_stayed`-gated — the diffuser is outside the tank, so even a
`keeper_bound` terrarium cannot stop the keeper from changing the water and sun
(thematic: they trapped the hand, not the sky).

## BI3 — The water cycle (`_biome_tick`, each step)
`water_level` eases toward an equilibrium set by the panel and the sun:
`equilibrium = clip(water_target - SUN_DRYING·(sun_hours-12)/12, 0, 1)`
`water_level += BIOME_EASE·(equilibrium - water_level)` (clamped 0..1).
More sun → lower equilibrium (evaporation); the keeper's `water_target` is the
baseline it settles around. Constants: `BIOME_EASE 0.03`, `SUN_DRYING 0.5`.

## BI4 — Emergent weather (`_biome_tick`, every `BIOME_TICK 20` steps)
Weather emerges from the budget, augmenting (not replacing) the seasonal rolls:
- `water_level > WET_THRESHOLD 0.78` and no active flood → chance `BIOME_FLOOD_
  CHANCE 0.3` to spill a flood ("the swollen reservoir overflows");
- dry (`_is_dry()`) and `sun_hours >= SUN_HOT 16` and no active arena heat →
  chance `BIOME_HEAT_CHANCE 0.4` of a heat wave ("the low water bakes the
  sands");
- `sun_hours <= SUN_COLD 8` and no active arena cold → chance `BIOME_COLD_
  CHANCE 0.3` of a chill ("the long night brings a creeping cold").
Reuses `flood_until` and the AR3 `arena_heat_until`/`arena_cold_until` tracks
(non-lethal). At default water/sun none of these fire.

## BI5 — Scarcity & crops read the budget (reconciled, not duplicated)
- `_is_dry()` = keeper `drought` OR `water_level < DRY_THRESHOLD 0.35`. This is
  the single dryness predicate; `_nature_mood` (AW2) reads it.
- `dole_factor()` multiplies the seasonal factor by
  `clip(water_level / DRY_THRESHOLD, 0.25, 1.0)` — 1.0 (no change) at/above the
  threshold, dropping only under real drought. Keeper drought still hard-zeros.
- `_grow_crops` non-oasis increment becomes `_biome_growth_units()`: 0 when
  `_is_dry()` or `sun_hours < SUN_COLD` (stall), else 1, and 2 when LUSH
  (`water_level > WET_THRESHOLD` and `SUN_COLD < sun_hours < SUN_HOT`). The
  oasis stays spring-fed (unchanged 2×). Default → 1 (unchanged).

## BI6 — Surfacing
- `build_state`: `water_level`, `water_target`, `sun_hours`.
- Dashboard: a **Panel** group (behind-the-glass styling) with Water −/+ and
  Sun −/+ via `POST /api/keeper/panel {water?, sun?}` (absolute values); a
  header readout "water NN% · sun NNh".
- Live view: HUD line "Water NN%  Sun NNh"; keys `x`/`c` water +/−, `a`/`z` sun
  +/− (each nudges the target/hours); help + legend updated.

## BI7 — Acceptance (tests/test_biome.py)
- Defaults are neutral: fresh sim has `water_level 0.6`, `dole_factor()`
  unchanged vs the seasonal value, non-oasis crop increment 1.
- `keeper_set_sun(SUN_MAX)` drives `water_level` DOWN over steps (evaporation);
  a high `water_target` with low sun drives it UP.
- Dry + hot emerges a heat wave; wet emerges a flood; short days emerge a chill
  (drive the panel to the extreme, step, assert the track lights).
- `_is_dry()` true below the threshold; `dole_factor` drops under low water and
  is unchanged at default; crops stall when dry.
- The panel verbs work while `keeper_bound` (survive the turning); the hand
  verbs do not (regression of PS5).
- state pickles; `EnhancedSandKingsSimulation.step` stays inert
  (`_biome_tick` not in its co_names).

## Status / Reconciliation
- Drafted 2026-07-10; implemented the same session (Phase 3, the closed-biome
  arc's engine). Reconciles with SPEC_WEATHER (weather now budget-driven, not
  purely stochastic), SPEC_SEASONS_AND_STONE T17 (dole reads water), SPEC_ARENA
  (emergent heat/cold reuse the arena tracks), and SPEC_AWARENESS (`_is_dry`
  feeds the nature mood).
