# SPEC — Incursions: invaders manifest inside the sealed terrarium, and never leave

Status: IMPLEMENTED 2026-07-18. Refines the T48 fauna incursion lifecycle. Baseline (core fauna, no gate) —
this is a behavior change to existing invaders, not an opt-in feature. Reconciles the sealed-box invariant the
keeper asked about: the glass is a closed firmament; nothing physical crosses it.

## Why

The keeper asked whether the terrarium has any opening besides the hand. It shouldn't. Today wild beasts
*enter through* a random map edge (`_spawn_incursion` placed the pack 2 cells in from one wall) and *leave* by
walking to the nearest edge and vanishing (`_beast_leaves`) — which implicitly treats the glass as porous. The
keeper's correction: invaders arrive by "a mechanism beyond the firmament" — from the inhabitants' perspective
they simply **manifest** inside; there is no door and no breach of the glass — and they **never leave** (a sealed
box has no way out; unslain, they perish inside).

## IN1 — Manifestation (not edge-entry)

`_spawn_incursion` manifests the pack at a site chosen from a MIX of modes (the keeper's "all of the above"),
never framed as passing through the wall:
- `wall`   — a margin just inside a random one of the four walls,
- `corner` — one of the four corners,
- `overhead` — an interior patch (as if lowered from beyond the firmament above).
The pack jitters ±2 around the site, every cell clamped to `[1, w-2] x [1, h-2]` (off the glass). Surface `z`.

## IN2 — Never leave; perish in place

The exit path is removed. In `_fauna_tick`:
- a beast older than `FAUNA_RAMPAGE` steps that is still unslain **perishes in place** — it is removed and a
  `CORPSE` voxel is stamped at its cell (this also keeps the one-incursion-at-a-time gate from deadlocking on an
  immortal straggler);
- a `fleeing` beast (a squirrel slipping a lone attacker, a bird wheeling off a strike) **evades toward open
  interior ground** (`_beast_retreat`), clamped inside — it no longer walks to the edge and disappears.
`_beast_leaves` is deleted (dead once nothing leaves).

## Invariant

The glass boundary is a closed firmament: `get_voxel` out-of-bounds is `GLASS`, movement is `in_bounds`-gated,
projectiles are distance-capped, water drains only at the numeric edge sink, and now fauna neither enter through
nor exit across the wall. The only intentional crossing is the keeper's hand from above (food/water/seeds/crickets).

## Acceptance

- A manifested incursion's beasts all sit strictly inside the glass (no cell on row/col 0 or w-1/h-1).
- Over `> FAUNA_RAMPAGE` steps an unslain incursion clears by perishing (corpse left), not by reaching an edge;
  a fresh incursion can then roll.
- A lone-attacked squirrel still sets `fleeing` (existing test) but stays in the tank; two adjacent pins still slay it.
- Bounty on slaying is unchanged; the single-incursion rule is unchanged.
