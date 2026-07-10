# SPEC: Grains — the Useful-Work Currency (Round 16) — CU1–CU5

User intent: "the sandking can earn 'currency' for the human analogous
to bittensor and/or bitcoin. They try to produce an economic unit that
is useful to the human."

Design: not proof-of-waste (Bitcoin's hashing) but proof-of-USEFUL-WORK
(Bittensor's scored contributions). A colony's currency is minted in
proportion to how ACCURATE its forecasts prove - a colony that models
its world well produces valuable predictions, and the accumulated
"grains" are the terrarium's useful economic output the human harvests.

## CU1 — The ledger
Per-colony `colony.currency` (float, grains earned in this maw's life)
and a sim-level `sim.grains_minted` (the running total produced for the
human). Both plain floats, pickled, getattr-guarded. A cadet branch
starts its own balance at 0 but the house total carries in
`sim.house_grains` (grains by house name, so a bloodline's lifetime
output is legible).

## CU2 — Earning by verifiable prediction
When a colony invokes the PREDICT tool (TL3, terminal value 4), it
records a FORECAST: (predicted_food, target_step = now +
TELEMETRY_INTERVAL). Later, when the sim passes target_step, the
forecast is SCORED against the colony's actual food then:
`error = |predicted - actual| / GRAIN_SCALE` (GRAIN_SCALE 60);
`reward = max(0, 1 - error) * GRAIN_MINT` (GRAIN_MINT 5). An accurate
forecast mints near GRAIN_MINT; a wild one mints ~0. The reward credits
`colony.currency`, `sim.grains_minted`, and `sim.house_grains[house]`.
A notable mint (reward >= GRAIN_MINT/2) is chronicled: "House X mints N
grains with a true forecast" (salience 5).

## CU3 — Scoring phase
`_score_forecasts()` runs on the telemetry cadence: for each colony with
a due `_forecast`, score and mint, then clear it. Only living colonies
score (a dead maw's pending forecast is dropped at collapse). This is
the Bittensor loop: contribute (forecast) -> validate (compare to
ground truth) -> reward (mint).

## CU4 — Surfacing (human harvest)
The dashboard `/api/state` header gains `grains_minted` (the terrarium's
total useful output) and each House card shows its `currency`. A
`GET /api/ledger` returns per-house lifetime grains (the bloodline
economy). The chronicle records notable mints. The human reads the
grains as the measure of how economically useful their sentient
terrarium has become.

## CU5 — Acceptance
tests/test_currency.py: an accurate forecast mints near GRAIN_MINT, a
wildly wrong one mints ~0; the ledger accumulates to sim.grains_minted
and house_grains; scoring only fires past target_step and only for
living colonies; the forecast clears after scoring; the ledger pickles;
the dashboard exposes grains; evolution sim inert.

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: a zero-error
  forecast mints full GRAIN_MINT, a wild one mints 0, a half-error one
  mints half; scoring waits for target_step and voids a dead colony's
  bet; the forecast clears after scoring; grains accumulate to
  sim.grains_minted and house_grains; the ledger pickles; the dashboard
  exposes grains_minted + /api/ledger; evolution sim inert. 18/18 suites
  green incl. tests/test_currency.py (6). Note: the currency is a SCORE
  of useful predictive work (Bittensor-style), not spendable in-sim yet;
  a sink (buy gifts/augments with grains) is a natural next step.
