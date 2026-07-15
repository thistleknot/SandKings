# SPEC — Repression & Resistance: the two-sided tribute order

Status: IN PROGRESS (Repression & Resistance arc, Phase 5). Baseline-ON, opt-out `--no-repression`. Amends
SPEC_SUZERAIN §SZ4 (revolt is now the tail of a two-sided loop, not a lone grudge counter). Depends on Phase 4
(the suzerain order must exist for repression/resistance to act on it).

## Why

The Phase-4 suzerain order is **one-sided**: a vassal only accrues `overlord_grudge` and revolts at
`REVOLT_RESENTMENT`; the overlord does nothing active — no cost to holding, no way to suppress unrest, and the
vassal has no recourse short of open revolt. So a dominant overlord that never weakens rules **forever, for
free** — a 2400-step probe showed one house holding all four rivals 82% of the run with zero revolts.

The same two-sided dynamic already exists one tier down, at the unit-thrall level (SPEC_SUBJUGATION SJ3–SJ5): a
captor soldier within `GUARD_RADIUS` calms a thrall's `defiance` (the iron fist), coercion flows captor→thrall,
the thrall strikes back at `STRIKE_CHANCE`, and it breaks free at threshold. Phase 5 **ports that pattern up to
the colony/suzerain tier**: the overlord pays to repress (iron fist), the vassal sabotages back (retaliation on
both sides), and repression breeds a simmering long-memory that shortens each next fuse (the krypteia paradox).
Turnover becomes emergent — it arises from the repression↔sabotage balance, not a fixed timer.

Gate `REPRESSION_ENABLED` (sandkings module default False → battery byte-identical; in `_GATE_NAMES`; baseline-on
`--no-repression`). Module global only — no cross-module politics reader is needed (repression touches no combat
gate; `politics.hostile()` is untouched), so this is the simpler single-flip pattern (mirrors
`SCARCITY_WAR_ENABLED`, not the dual-flip suzerain). All logic lives inside `_tribute_tick` under
`if REPRESSION_ENABLED:` and is **deterministic** (no new `random.*` draw → draw-order unshiftable even under the
gate; the Phase-3 plunder precedent).

Constants (politics.py, beside `TRIBUTE_*`; provisional, soak-tuned):
`REPRESSION_COST_FOOD=12.0` (food the fist costs per repressed vassal per interval), `REPRESSION_CALM=8.0`
(grudge suppressed per repression; `< TRIBUTE_RESENTMENT=10` so a repressed-and-tributed vassal still climbs
slowly), `REPRESSION_RESENTMENT=1.0` (krypteia memory bred per repression), `MEMORY_ACCEL_K=0.5` (memory's
contribution to per-tribute accrual), `SABOTAGE_WITHHOLD_K=0.6` / `SABOTAGE_WITHHOLD_CAP=0.5` (tribute a
resentful vassal withholds), `SABOTAGE_DAMAGE_K=0.06` (overlord food a resentful vassal spoils per interval),
`SABOTAGE_MIN_GRUDGE=20.0` (grudge below which no sabotage).

New colony field via the getattr-guarded convention (no `__init__` change → old checkpoints load):
`subjugation_memory` (float, default 0.0). **Unlike `overlord_grudge`, it is NOT reset** by `_impose_order` /
`_dissolve_order` / `_revolt` — it is the long memory of having been crushed, so each cycle shortens the next
fuse.

## RR1 — Sabotage (the resistance half, `_tribute_tick`, deterministic)

At a vassal's staggered tribute interval, let `grudge_norm = min(1.0, overlord_grudge / REVOLT_RESENTMENT)`.
- **Withhold:** the vassal renders `TRIBUTE_RATE · food · (1 − withhold)` instead of the full amount, where
  `withhold = min(SABOTAGE_WITHHOLD_CAP, SABOTAGE_WITHHOLD_K · grudge_norm)`. The withheld food **stays with the
  vassal** (conserved — the transfer just shrinks).
- **Covert damage:** when `overlord_grudge ≥ SABOTAGE_MIN_GRUDGE`, the vassal spoils
  `SABOTAGE_DAMAGE_K · grudge_norm · overlord.food_stored` of the overlord's stores. This food is **destroyed**,
  not transferred (arson/pillage — no minting). Throttled event: "House X sabotages the overlord's stores".

## RR2 — Repression (the iron-fist half, `_tribute_tick`)

After the (reduced) tribute is rendered, the overlord may repress this vassal iff it can afford the fist:
`overlord.maw.food_stored ≥ REPRESSION_COST_FOOD`. If so:
- Deduct `REPRESSION_COST_FOOD` from the overlord (the cost of holding).
- `overlord_grudge = max(0.0, overlord_grudge − REPRESSION_CALM)` (the fist stills unrest now).
- Throttled event: "House Y's iron fist stills House X".
If the overlord **cannot** afford it (bled down / starving), repression **lapses** — grudge is not suppressed
this interval, so it climbs unchecked toward revolt. "Costly but possible": a rich, well-fed overlord holds; a
bled one loses the order.

## RR3 — Krypteia memory (the paradox, `_tribute_tick`)

Every interval a vassal is tributed, its grudge accrues an **effective** resentment that rises with past
repression: `effective_resentment = TRIBUTE_RESENTMENT + MEMORY_ACCEL_K · subjugation_memory`. Each time the
overlord actually represses (RR2 fires), `subjugation_memory += REPRESSION_RESENTMENT`. So repression calms the
*current* grudge but deepens the *standing* memory, and memory accelerates future accrual — the fist buys time
at a compounding cost, and the fuse shortens each cycle. `subjugation_memory` survives revolt/dissolution
(persisted, not reset), so a house crushed before resents faster the next time.

## RR4 — Revolt (loop closure, unchanged endpoint)

The existing SZ4 path stands: when `overlord_grudge ≥ REVOLT_RESENTMENT`, `_revolt(vassal, overlord)` frees the
vassal, sets `war_target=overlord`, lifts the Pax, and war resumes. Phase 5 only changes *how fast* that line is
reached (via the RR1–RR3 balance); it does not change the revolt mechanism. `subjugation_memory` is deliberately
untouched by `_revolt` so it carries into the next order.

## Order of operations within one vassal's interval (RR1 → RR2 → RR3 → RR4)

1. Compute `grudge_norm` from the pre-tick grudge.
2. RR1 withhold: render the reduced tribute (conserved). RR1 covert-damage: spoil overlord food (destroyed) if
   `grudge ≥ SABOTAGE_MIN_GRUDGE`.
3. RR3 accrual: `overlord_grudge += TRIBUTE_RESENTMENT + MEMORY_ACCEL_K · subjugation_memory`.
4. RR2 repression: if affordable, pay cost, `grudge −= REPRESSION_CALM` (floored at 0), and
   `subjugation_memory += REPRESSION_RESENTMENT`.
5. RR4: if `overlord_grudge ≥ REVOLT_RESENTMENT`, revolt.

(The existing `TRIBUTE_TRUST_HIT` diplomatic nudge and the "renders tribute" event remain.)

## Acceptance (`tests/test_repression.py`)

- **Sabotage withholds + damages (RR1):** a high-grudge vassal renders strictly less than `TRIBUTE_RATE·food`
  (withheld part stays with the vassal — conserved), and spoils overlord food when `grudge ≥ SABOTAGE_MIN_GRUDGE`
  (overlord's post-tick food is below `pre + tribute_received` — net destruction). A zero-grudge vassal renders
  the full amount and spoils nothing.
- **Repression suppresses + costs (RR2):** an affordable overlord's food drops by `REPRESSION_COST_FOOD` beyond
  the tribute it received, and the vassal's grudge is lower than the un-repressed accrual. An overlord below
  `REPRESSION_COST_FOOD` does not repress and the vassal's grudge climbs by the full effective resentment.
- **Krypteia memory (RR3):** after a repression, `subjugation_memory` increased by `REPRESSION_RESENTMENT`;
  `subjugation_memory` is unchanged by `_revolt` (persists across a revolt); a vassal with higher
  `subjugation_memory` accrues more grudge per interval than one with zero.
- **Loop still closes (RR4):** driving grudge past `REVOLT_RESENTMENT` still triggers `_revolt` (war resumes).
- **Gate-off:** with `REPRESSION_ENABLED` False, `_tribute_tick` is byte-identical to Phase 4 (full tribute, no
  sabotage, no repression, `subjugation_memory` never created). Full battery byte-identical with the gate off.
