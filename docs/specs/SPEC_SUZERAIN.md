# SPEC — Aztec/Cortés new order: suzerainty, Pax, tribute, revolt

Status: IN PROGRESS (War & Survival arc, Phase 4). Baseline-ON, opt-out `--no-suzerain`. Amends
SPEC_POLITICS §P7 (hegemon). Closes the loop: endemic war → a dominant power imposes a tribute order →
the order decays → revolt → war resumes. Depends on Phase 3 (endemic war must exist for a conqueror to
end it).

## Why

Today the strongest colony is the Waltz-inverted *coalition target* (`d.hegemon`) that everyone gangs up
on and that enforces nothing; subjugation is per-*unit* thralls; there is no empire/tribute/vassal
structure. The user's arc needs "someone stronger comes by and enforces a new order." Phase 4 adds the
missing **colony-over-colony binding**: a power strong enough past a higher threshold *imposes* vassalage
(recurring coerced tribute) instead of being ganged up on, a **Pax** suppresses war among its vassals, and
resentment + overlord-weakness eventually break the order so war resumes.

Gate `SUZERAIN_ENABLED` (sandkings module default False → battery byte-identical; in `_GATE_NAMES`;
baseline-on `--no-suzerain`). `politics.hostile()` reads the flag as `getattr(sim, 'suzerain_enabled',
False)` (mirroring `sim.wage_enabled`) so politics.py needs no cross-module global; the entrypoint sets
BOTH the module gate and `sim.suzerain_enabled`. Constants (politics.py): `SUZERAIN_ENTER=2.4` /
`SUZERAIN_EXIT=1.8` (× equal share, above `HEGEMON_ENTER=1.6`, hysteresis), `TRIBUTE_INTERVAL=200`,
`TRIBUTE_RATE=0.10`, `TRIBUTE_RESENTMENT=10.0`, `REVOLT_RESENTMENT=50.0` (revolt after ~5 tributes),
`TRIBUTE_TRUST_HIT=-3.0`.

Colony status via the getattr-guarded `laboring_for` convention (no `__init__` change → old checkpoints
load): `tributary_to` (overlord id, default -1), `overlord_of` (set of vassal ids, default `set()`),
`overlord_grudge` (resentment accumulator, default 0.0).

## SZ1 — Impose / maintain / dissolve the order (`_update_hegemon`, guarded)

`_update_hegemon` first calls `_update_suzerain(d)` when `SUZERAIN_ENABLED`; if a suzerain reigns it
returns and the coalition track is skipped (**suzerainty supersedes the coalition** — the same power-share
can't drive both; §P7 amendment). `_update_suzerain`:
- If a living colony already holds vassals (`overlord_of`): it stays suzerain while its power share
  `≥ SUZERAIN_EXIT/n`; below that, `_dissolve_order` frees every vassal (the order crumbles). Returns
  whether an order still reigns.
- Else the strongest living colony with share `> SUZERAIN_ENTER/n` imposes: `_impose_order` sets
  `tributary_to` on every weaker **non-kin** living colony, fills `overlord_of`, clears their `war_target`
  (Pax), suppresses the coalition (`d.hegemon=None`), zeroes their `overlord_grudge`, and bumps
  `_suzerain_epoch`. Between `HEGEMON_ENTER/n` and `SUZERAIN_ENTER/n` → fall through to today's coalition.

## SZ2 — Pax (`politics.hostile()`, gated)

After the kin check, when `getattr(sim,'suzerain_enabled',False)`, consult an epoch-cached
`_suzerain_map` (`{vassal: overlord}`, rebuilt when `_suzerain_epoch` changes — mirrors `_kin_map`):
overlord↔vassal and co-vassals of one overlord are **not hostile** (the Pax). Off → the block is skipped
and `hostile()` is byte-identical (it gates all combat RNG).

## SZ3 — Recurring coerced tribute (`_tribute_tick`, after `_labor_market_tick`)

Gated early-return when off (byte-identical, the `_maw_rl_tick` pattern). Every `TRIBUTE_INTERVAL`
(staggered per vassal by `colony_id`), each vassal renders `TRIBUTE_RATE * food_stored` to its overlord by
a **direct transfer** (subtract from vassal, `maw.eat` on overlord — robust; the voluntary courier
`_dispatch_gift` can fail to a dead envoy and is cooldown/min-gated, so a coerced flow uses a direct move
like `_plunder`). Each tribute adds `TRIBUTE_RESENTMENT` to the vassal's `overlord_grudge` and nudges
`d.rel(vassal,overlord)` by `TRIBUTE_TRUST_HIT`. A dead/absent overlord frees the vassal.

**Decay-math note (resolves the plan's flagged risk):** `TRUST_DECAY=0.999/step` over `TRIBUTE_INTERVAL`
decays a trust-ledger grudge to a fixed point (~−16 for −3/tribute) that never reaches a −50 revolt line —
so revolt keys off the **non-decaying** `overlord_grudge` accumulator, not the trust ledger. The trust
nudge is flavor for other readers.

## SZ4 — Decay → revolt → war resumes (`_revolt`, loop closure)

Two decay paths: (1) when `overlord_grudge ≥ REVOLT_RESENTMENT`, `_revolt` frees the vassal
(`tributary_to=-1`, drop from `overlord_of`, bump `_suzerain_epoch`), sets `war_target=overlord`, and
`at_war=True` — Pax lifts (`hostile` true again) and war resumes; (2) `SUZERAIN_EXIT` dissolves the whole
order when the overlord is bled down. The order is thus never permanent.

*Amendment (SPEC_REPRESSION, Phase 5, gated `REPRESSION_ENABLED`):* revolt is no longer reached by a lone
tribute counter. The two-sided loop drives it — the vassal withholds and spoils tribute (RR1, which bleeds the
overlord toward decay-path 2), the overlord pays to suppress the grudge (RR2 iron fist), and repression breeds a
persistent `subjugation_memory` that accelerates accrual toward decay-path 1 (RR3 krypteia). Both decay paths
stay exactly as above; Phase 5 only changes *how fast* each is reached. Gate off → this amendment is inert.

## Acceptance (`tests/test_suzerain.py`)

- Imposition + Pax: inflate one colony's power past `SUZERAIN_ENTER/n`; after `_update_hegemon`,
  `overlord_of == {others}`, each `tributary_to == suzerain`, `d.hegemon is None`, and `hostile(vassalA,
  vassalB) is False`.
- Tribute flow: after one `TRIBUTE_INTERVAL`, a vassal's food dropped and the overlord's rose (conserved);
  `overlord_grudge` increased.
- Revolt closes the loop: force `overlord_grudge ≥ REVOLT_RESENTMENT`; after `_tribute_tick`,
  `tributary_to == -1`, `war_target == overlord`, and `hostile(vassal, overlord) is True` (war resumes —
  the sim did not freeze).
- Gate-off: `_update_hegemon` produces the coalition/hegemon exactly as today; `_tribute_tick`
  early-returns; `hostile()` byte-identical.
- Full battery byte-identical with the gate off.
