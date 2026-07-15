# SPEC — Wage vs Whip: diffuse resistance and the durable soft order

Status: IN PROGRESS (Repression & Resistance arc, Phase 6). Baseline-ON, opt-out `--no-diffuse-resistance`.
Extends SPEC_REPRESSION (modulates the two-sided tribute loop). Depends on Phase 5 (the repression dynamics it
shapes).

## Why

Phase 5 made the tribute order two-sided, but every overlord runs it the same way, and in short soaks the order
tends to end by *dissolution* (the overlord bled below its power threshold) rather than by the *revolt* event —
the Spartacus/Helot drama the arc is about. Phase 6 makes the **extraction style** set the **shape of
resistance**, encoding the codex doctrine already in the game ("the wage outlasts the whip",
`SPEC_SUBJUGATION.md:434`) and the Minoan-vs-Mycenaean influence (the mercantile thalassocracy vs the fortress
citadel):

- A **whip** order (an aggressive, militarized overlord — Sparta / Mycenae the fortress) extracts overtly and
  represses hard; its krypteia memory compounds fast, so it ends in **revolt** (the yoke is thrown off).
- A **wage** order (a peaceable, mercantile overlord — Minoan trade) extracts softly; grudge accrues slowly so
  it rarely revolts — a **durable** order — but the subjugated foot-drag a small, permanent, non-escalating
  amount (the diffuse "anarchist" resistance of fiat wage-slavery). The wage outlasts the whip.

Extraction hardness is **continuous**, not a binary caste: `hardness = clamp(overlord.genome.aggression, 0, 1)`
(default 0.5; colonies init in ~[0.5,1.0]). This is robust to the aggression distribution and ties order style
to the overlord's evolved disposition — an aggressive house rules by the fist, a peaceable one by the purse.

Gate `DIFFUSE_RESISTANCE_ENABLED` (sandkings module default False → battery byte-identical; in `_GATE_NAMES`;
baseline-on `--no-diffuse-resistance`). Module global only. The modulation lives inside `_tribute_tick` and only
applies when **both** `DIFFUSE_RESISTANCE_ENABLED` and `REPRESSION_ENABLED` are on (it shapes the Phase-5
dynamics); with the diffuse gate off, the multipliers are neutral and Phase-5 behavior is exact. Deterministic
(no new RNG). Constants (politics.py, beside the repression block; provisional, soak-tuned):
`WHIP_MEMORY_K=4.0` (hard-order krypteia acceleration), `WAGE_GRUDGE_FLOOR=0.5` (soft-order grudge-accrual
floor), `DIFFUSE_DRAG=0.10` (max permanent foot-drag withholding for the softest order).

## WW1 — Whip: hard orders revolt (krypteia acceleration)

When both gates are on, the krypteia memory bred per repression scales with the overlord's hardness:
`memory_gain = REPRESSION_RESENTMENT · (1 + WHIP_MEMORY_K · hardness)`. An aggressive overlord's memory compounds
fast, so the memory-accelerated accrual reaches `REVOLT_RESENTMENT` before dissolution — the order ends in
`_revolt` (war resumes). A soft overlord (low hardness) breeds little memory.

## WW2 — Wage: soft orders endure (grudge softening)

Grudge accrual is scaled by `grudge_mult = WAGE_GRUDGE_FLOOR + (1 − WAGE_GRUDGE_FLOOR) · hardness` (∈
[WAGE_GRUDGE_FLOOR, 1]). A soft (low-hardness) overlord's vassals accrue grudge slowly, so the revolt line is
rarely reached — the order is durable. A hard overlord gets ~full accrual (`grudge_mult → 1`).

## WW3 — Diffuse drag (the anarchist foot-drag)

Independent of grudge, the subjugated always foot-drag a soft order: the vassal withholds an extra
`DIFFUSE_DRAG · (1 − hardness)` of its tribute (added on top of the RR1 grudge-scaled withholding, total capped
below 1.0). This is the permanent, non-escalating diffuse resistance of wage-slavery — small, never revolts,
always present. The softer the order, the more the diffuse drag (a soft order buys peace but never full
compliance); a pure whip order (hardness=1) has zero diffuse drag — its resistance is concentrated into revolt
instead.

## Net effect (measurable: "the wage outlasts the whip")

Across seeds, high-hardness (whip) orders end sooner and by revolt; low-hardness (wage) orders persist longer,
revolt less, and carry a standing diffuse drag. Order longevity rises as overlord aggression falls.

## Optional (deferred, not in this phase)

The same `DIFFUSE_DRAG` applied to exploited **wage-market** laborers in `_credit_labor` (continuous kinds only)
when `WAGE_ENABLED` — the literal fiat wage-slavery. Deferred because the wage market is opt-in (`--wages`), so
it does not affect baseline play; the colony-tier mechanic above carries the theme in the baseline game.

## Acceptance (`tests/test_diffuse_resistance.py`)

- **Gate default off:** `DIFFUSE_RESISTANCE_ENABLED` is False.
- **WW1 whip revolts sooner:** a high-aggression overlord breeds more `subjugation_memory` per repression than a
  low-aggression one (memory_gain scales with hardness); a maxed-hardness order reaches revolt in fewer
  intervals than the Phase-5 baseline.
- **WW2 wage endures:** a low-aggression overlord's vassal accrues less grudge per interval than a high-aggression
  one (grudge_mult < 1 for soft), so it survives more intervals before the revolt line.
- **WW3 diffuse drag:** a soft-order vassal renders strictly less tribute than the Phase-5 (no-diffuse) amount at
  the same grudge (extra foot-drag), and a pure-whip (hardness=1) order adds zero diffuse drag.
- **Gate-off:** with `DIFFUSE_RESISTANCE_ENABLED` False, `_tribute_tick` reproduces Phase 5 exactly (multipliers
  neutral). Full battery byte-identical with the gate off.
