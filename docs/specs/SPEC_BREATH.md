# SPEC — The Breathing Net: evolvable capacity as a floating, semi-permeable, log-scaled, annealed quantity

Status: DRAFT (new arc, "the Breath"). Baseline-ON when built (opt-out `--no-breath`); gate default off → battery
byte-identical. Refines the EV1 evolvable-architecture genes (`brain_hidden`, `brain_depth`) and the SPEC_TONGUE
`read_reach` gene. Obeys the design law: it reshapes only how the *evolvable* genes MUTATE — it never edits the
frozen Kanerva SDM / GRU (the readout Linear is already rebuilt/grafted on a width change, EV4).

## Why

Today capacity drifts by a **hard clamp**: `brain_hidden` jumps ±8 and is `np.clip`ed to
`[BRAIN_HIDDEN_MIN, min(BRAIN_HIDDEN_MAX, brain_ceiling)]`; `read_reach` ±1 hard-clamped. The user wants the net to
**breathe** ("extend the net as it learns"): the neuron count per layer is a **floating (mean, sdev)** quantity held
inside a **semi-permeable** range (soft membrane, not a wall), growing/shrinking in **log proportions** so it can't
run away, over a **sparse** substrate (the Kanerva top-k of 256 already gives gaps), and **annealed** (the unfit
prune out via the existing GA). Capacity becomes an evolved, breathing quantity selected by survivability, not an
authored cap. This is the general brain-wide version of the read-reach evolution SPEC_TONGUE flagged.

Gate `BREATH_ENABLED` (module default False → battery byte-identical; in `_GATE_NAMES`; entrypoint flips it on
baseline-on, opt-out `--no-breath`). Off ⇒ mutation is the exact pre-Breath hard-clamp drift (byte-identical).

## BR1 — The `breathe` kernel (pure, identity-safe)

`breathe(current, mean, sdev, soft_lo, soft_hi, rng) -> int`: propose a new capacity value that
1. **floats toward the population mean** (mean-reversion): `drift = MEAN_PULL·(mean − current) + rng.gauss(0, sdev)`;
2. is **log-damped** so big values move slowly and cannot blow up: `step = drift / log2(max(current, 2))`;
3. is **semi-permeably bounded** (a soft membrane, NOT a hard clamp): beyond `[soft_lo, soft_hi]` the value is
   *softly compressed* back with a tanh squash of the overshoot (it may sit a little past the band, never far).

**Contract:** Require — finite args, `soft_lo ≤ soft_hi`, positive `current`. Guarantee — returns an int in a
bounded neighborhood of `[soft_lo, soft_hi]` (soft overshoot ≤ a log-scaled margin); mean-reverting; deterministic
given `rng`; consumes exactly one `rng.gauss` draw. Maintain — never returns a runaway value (log damping + soft
squash). Assert — `sdev==0 and current==mean ⇒ breathe == mean` (a settled population is stable).

## BR2 — `PopulationBreath` (the floating mean/sdev)

A tiny rolling tracker: `observe(values)` updates an EMA `(mean, sdev)` of a trait across the living colonies;
`sample(current, soft_lo, soft_hi, rng)` = `breathe(current, mean, sdev, …)`. This is the "quasi-static mean and
sdev" the population maintains; the band floats with the colonies that survive (annealing does the culling).

## BR3 — Wiring (gated; the only mutation change)

In `ColonyGenome.mutate`, under `BREATH_ENABLED`, replace the hard-clamp drift of `brain_hidden` (and `read_reach`,
SPEC_TONGUE) with `PopulationBreath.sample(...)` using log-scaled soft bounds
(`soft_hi = min(BRAIN_HIDDEN_MAX, brain_ceiling)`, `soft_lo = BRAIN_HIDDEN_MIN`). Off ⇒ the exact prior lines run
(byte-identical). Annealing = the existing `_respawn_colony` fitness cull (poor capacities die with their colony);
sparsity = the existing Kanerva top-k activation; the readout width change is absorbed by EV4 `graft_into`.

## Constants

| Constant | Value | Meaning |
|---|---|---|
| `BREATH_ENABLED` | `False` | module default off (battery byte-identical); entrypoint flips baseline-on |
| `BREATH_MEAN_PULL` | `0.2` | mean-reversion rate toward the population mean (a dynamics rate, like a learning rate) |
| `BREATH_SOFT_MARGIN` | `0.5` | log-scaled coefficient of the semi-permeable overshoot past the per-colony band |

**No magic budget constant.** The shared compute budget is **DERIVED**, not authored: `budget = N · geometric_mean(
soft_lo, soft_hi)` — the log-center of the trait's OWN existing band (`[BRAIN_HIDDEN_MIN, min(BRAIN_HIDDEN_MAX,
brain_ceiling)]` for width; `[1, TONGUE_READ_REACH_MAX]` for reach), so the fair share is the natural midpoint of
the bounds already in the code, per-trait. Only `MEAN_PULL` and `SOFT_MARGIN` are free dynamics rates.

## Status / Reconciliation (implemented 2026-07-17)

`sim/breath.py` (`breathe` kernel BR1, `PopulationBreath` BR2, derived-budget `sample_trait` BR3, all pure/torch-free).
Wiring: `sim/sandkings.py` (`BREATH_ENABLED` gate + entrypoint baseline-on flip + `--no-breath`; gated
`PopulationBreath.sample` override of `brain_hidden` and `read_reach` in `ColonyGenome.mutate`; population observed
every 100 steps in `step`), `run_tests._GATE_NAMES`. Budget is derived per-trait from the geometric mean of that
trait's bounds — no `BREATH_TOTAL`/`BREATH_PER` constant. Growth above the fair share is an ABSOLUTE log-law of the
headroom the others leave (nets are a floating ratio of a fixed pool; annealing = the existing GA cull frees room).
Verified: `tests/test_breath.py` (8, green) — no-runaway, mean-reversion, semi-permeable-bounded, settled-stability,
over-budget-pulled-to-fair-share, no-population-only-band; gate-off byte-identity via the `evolution` suite; live
sim runs clean with the tracker firing and the budget deriving correctly. A homogeneous population is correctly
stable (breathing moves capacity only under variance/pressure).

## Acceptance (`tests/test_breath.py`)

- **Gate default off:** `BREATH_ENABLED` is False; `ColonyGenome.mutate` runs the exact hard-clamp drift; a
  determinism suite (evolution/selection) stays byte-identical.
- **BR1 no-runaway:** iterating `breathe` thousands of times from any start stays in a bounded neighborhood of the
  band (log damping + soft squash hold) — never diverges.
- **BR1 mean-reversion:** starting far from `mean`, the series drifts toward `mean`; a settled population
  (`sdev==0, current==mean`) is stable.
- **BR1 semi-permeable:** the value MAY sit slightly past `soft_hi` (not hard-clamped) but the overshoot is bounded
  by the log-scaled margin — a soft membrane, not a wall.
- **BR3 evolved capacity:** with the gate on, over respawns the population `brain_hidden`/`read_reach` distribution
  floats toward what fitness rewards, without any value exceeding the soft band by more than the margin.
