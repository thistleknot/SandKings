# SPEC: Tools & Telemetry (Round 15) — TL1–TL6

User intent: "they can learn from the code and how it enables their
ability, and try to work through new problems to create their own code
to do things for them (calculate their environment, make predictions,
use the tabfm model to do regression). Data should be made freely
available to them, such as environment stats, similar to Dwarf
Therapist stats."

Design (safe): DATA is free - a Dwarf-Therapist-style telemetry feed of
environment stats, available to the human (dashboard) and to the
sandkings. The ABILITY to exploit it is a PRE-WRAPPED tool: a pi colony
invokes a regression call (sklearn, tabfm-pluggable) over its own
history to predict its fortunes and act. No free-form codegen - a
whitelisted analysis call, run inside the sandbox.

## TL1 — Telemetry feed (freely available)
`telemetry.py` `Telemetry` collects, every TELEMETRY_INTERVAL (50)
steps, a per-colony row: (step, food, pop, maw_hp, at_war, season,
oasis_held, attitude). Bounded ring (TELEMETRY_HISTORY 64 rows per
colony) so it pickles cheaply. `sim._telemetry()` is lazy + guarded.
This is the Dwarf-Therapist analogue: the stats are just THERE, for
anyone.

## TL2 — The regression tool (pre-wrapped)
`predict_food(rows) -> (predicted_next, slope)`: fit food vs step over a
colony's recent rows and extrapolate one TELEMETRY_INTERVAL ahead.
Backend order: sklearn LinearRegression if present, else numpy polyfit
(always available) - a clean `REGRESSION_BACKENDS` seam so a TabPFM
regressor can drop in without touching callers. Pure, deterministic for
given rows.

## TL3 — Invoking it (terminal value 4)
Terminal command value 4 (K10 shell, pi-only): the colony runs
`predict_food` on its own telemetry. A downward slope -> it prepares
(patience += TOOL_NUDGE: hoard against the lean times it foresees); an
upward slope -> it grows (fertility += TOOL_NUDGE). Bounded [0,1]. First
use: "House X computes its fortunes" (salience 6); the outcome logs
"...and hoards against lean times" / "...and grows toward plenty".

## TL4 — Human access (dashboard)
`GET /api/telemetry` returns the per-colony recent rows (the free data
feed). The Keeper's Console House card gains a tiny food sparkline drawn
from it - the human reads the same stats the sandkings do.

## TL5 — Safety / compatibility
sklearn/numpy only; the tool is a fixed analysis call, never evaluated
text - no eval/exec, no network. Telemetry is a small bounded structure
that pickles with the sim (getattr-guarded). Evolution sim inert.

## TL6 — Acceptance
tests/test_tools.py: telemetry records bounded per-colony rows;
predict_food recovers a planted slope (rising and falling) via both
backends; the terminal tool nudges the right disposition by trend,
pi-only, once-logged; the feed pickles; evolution sim inert; the
dashboard /api/telemetry endpoint returns rows. Skips sklearn assertions
if sklearn is absent (numpy backend still tested).

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: telemetry
  records bounded per-colony rows; predict_food recovers planted rising
  and falling slopes via both sklearn and numpy backends (>=3 rows);
  the terminal PREDICT tool nudges patience on a falling trend and
  fertility on a rising one, pi-only, once-logged; the feed pickles
  (module-level ring factory, not a lambda); /api/telemetry serves it;
  evolution sim inert. 17/17 suites green incl. tests/test_tools.py (6).
  The dashboard sparkline (TL4) endpoint ships; the inline SVG sparkline
  on the card is deferred (the /api/telemetry feed is live).
