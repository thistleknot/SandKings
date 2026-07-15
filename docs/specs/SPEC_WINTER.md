# SPEC — Seasonal planning: winter bites, the maw learns to hoard

Status: IN PROGRESS (War & Survival arc, Phase 2). Baseline-ON, opt-out. The intelligence test that
sits on top of the Phase-1 food sources (SPEC_FLORA): store an annual harvest or starve in the Chill.

## Why

Today a colony cannot really starve: `_feed_terrarium` floors every living colony to `BOOTSTRAP_FLOOR=10`
each feeding (sandkings.py:5911-5913), and hoarded `food_stored` never decays. So "prepare for winter" has
no teeth and no reward. The arc needs winter to genuinely kill the unprepared while the prepared ride
their hoard — and it needs the maw to be able to *learn* the moon/season cycle and stock up ahead of the
Chill, not merely react. Two independent gates so we can A/B whether the harsher net alone drives emergent
hoarding or whether the learner needs a shaping nudge.

## WI1 — Winter bites (weaken the safety net in Chill)

- Gate `WINTER_BITE_ENABLED` (module default False → battery byte-identical; entrypoint flips on; opt-out
  `--no-winter-bite`; in `_GATE_NAMES`).
- In `_feed_terrarium`, guard the bootstrap floor:
  `if not (WINTER_BITE_ENABLED and season_index()==3): food_stored = max(food_stored, BOOTSTRAP_FLOOR)`.
  In Chill the floor is skipped, so an **unprepared** colony's `food_stored` falls past 0 and the existing
  starvation cull (2111-2120) kills its units — real extinction pressure. A **prepared** colony rides its
  non-decaying hoard untouched (the reserve is honoured — the whole test is "did you save enough").
- The hoard stays non-decaying (no winter spoilage added): saving is the intended winning move, so a
  reserve must survive to spend. The `DOLE_RAMP` years-0-1 grace is left intact (early-game onramp); the
  floor removal bites independently of the ramp.
- Gating: when `WINTER_BITE_ENABLED` is False the guard is `not (False and ...) == True`, so the floor
  applies exactly as today. No RNG touched → byte-identical.

## WI2 — The maw learns to plan (hoard shaping, gated)

The learner (`colony_learner.py`) is un-gated and RNG-active every 25 steps — the sharpest byte-identity
trap. All changes are threaded behind a default-False flag so the OFF path is bit-for-bit today's learner.

- Gate `HOARD_PLANNING_ENABLED` (sandkings global; module default False; entrypoint flips on; opt-out
  `--no-hoard-planning`; in `_GATE_NAMES`). Passed to `learner.decide(..., hoard_shaping=...)`.
- `observe_state(sim, colony, hoard_shaping=False)`: when on, append a `winter_coming` bool (True in Dust,
  `season==2`, the last prep window) → a 6-tuple; when off, the 5-tuple exactly as today. The policy can
  then condition prep on winter's approach, not only its arrival (season is already dim 0).
- `decide(..., hoard_shaping=False)`: passes the flag to `observe_state`, and at the **Dust→Chill
  crossing** (last season 2, current 3) adds `HOARD_BONUS * min(food/HOARD_TARGET, 1)` to the TD reward —
  crediting a stockpile built earlier, which the short-horizon Δ-reward otherwise under-credits (patience-γ
  alone discounts but never manufactures the long-horizon signal). No new posture — changing `POSTURES`
  length would reorder the whole battery RNG stream; reward shaping + one bool state dim consume **no** RNG.
- `dream` is unchanged: it replays stored `(s,a,r,s2)` transitions (whose reward already carries the
  shaping) and never calls `observe_state`, so it needs no flag.
- Gating: when off, the reward, the state-tuple length, and `POSTURES` are all unchanged → identical Q
  updates → identical `argmax` postures → identical downstream gate/worker RNG → battery byte-identical.
- Tuning (`colony_learner.py`): `HOARD_BONUS=5.0` (a strong one-per-year winter-crossing credit, well
  above the O(1) per-interval reward), `HOARD_TARGET=200.0` (food reserve counted as "fully prepared").

## Two flags on purpose

`WINTER_BITE_ENABLED` (the net) and `HOARD_PLANNING_ENABLED` (the shaping) are separate so a run can test
whether the harsher net *alone* yields emergent stockpiling (most emergent, ideal) or whether the shaping
is actually needed — answered by experiment, not assertion. Both baseline-on (`--no-winter-bite` /
`--no-hoard-planning`).

## Acceptance

- `tests/test_winter.py`: with `WINTER_BITE_ENABLED` and `season_index()==3`, `_feed_terrarium` leaves a
  low colony below the floor (it can starve) while a stocked colony keeps its reserve; gate-off floors both
  to `BOOTSTRAP_FLOOR` exactly as today.
- `tests/test_hoard_planning.py`: with `HOARD_PLANNING_ENABLED`, `observe_state` returns a 6-tuple with the
  `winter_coming` bit (True only in Dust); a Dust→Chill decision with a full hoard raises the Q of the
  reserve-building transition above the un-shaped baseline; gate-off yields the 5-tuple and an identical Q
  trajectory.
- Full battery byte-identical with both gates off.

Amends: SPEC_SEASONS_AND_STONE.md (the Chill floor removal), SPEC_SENTIENCE.md S3/S4 + the
`colony_learner.py` docstring (the gated shaping + winter-coming feature; "learning refines, never
overrides" preserved).
