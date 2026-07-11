# SPEC: Technology & Civilization (Phase T1) — TE1–TE6

The maws become a CIVILIZATION. Two classes of technology: FOREIGN (the keeper's
gift ladder — an accelerant the maws could never invent alone, "Aristotle with a
calculator") and NATIVE (fire, farming, metallurgy… earned by the maws). T1 lays
the data model, revises the foreign ladder, and recognises fire. Native
acquisition, bonuses, skills (T2) and diffusion (T3) build on this.

Architecture lens: the maw is a MASTERMIND (a private mind, blind to other maws'
minds); the spawn are its remote underlings. A maw cannot READ a rival's tech —
it must earn, observe, barter, or conquer for it (T2/T3).

## TE1 — Per-colony tech state
Two getattr-guarded, pickled fields on `Colony` (mutable → initialised per
colony, NOT via the shared-default normalization tuple):
- `techs: set[str]` — the technologies this house KNOWS (default empty).
- `tech_xp: dict[str,float]` — proficiency 0..1 per tech (the DF "skill level";
  default empty). Written in T2; carried here so old checkpoints resume.
Both are added in `Colony.__init__` and guarded in the two normalization sites
(`sandkings.py` ~1484 and ~4201) with explicit `if not hasattr(...)` lines.

## TE2 — The tech registry
`TECH_REGISTRY: dict[id -> {kind: 'foreign'|'native', desc: str}]` (module-level
in sandkings.py). Foreign: `abacus, watch, calculator, pi`. Native: `fire,
farming, metallurgy, plow, masonry`. `TECH_FOREIGN`/`TECH_NATIVE` tuples name the
members. Extensible — adding a row is the only step to introduce a tech.

## TE3 — The foreign ladder (revised)
`GIFT_LADDER = ('abacus', 'watch', 'calculator', 'pi')` — the confirmed order.
`_claim_gift` grants the claimed tech (`_grant_tech(colony, kind)`) and its
capability:
- **abacus** — counting/quantity; `machine_arc` none→known (a first numeracy).
- **watch** — time/periodicity; `machine_arc` none→known.
- **calculator** — a plain VM `Controller` (VM_FUEL); arc known→claimed.
- **pi** — the hot `Controller` (PI_FUEL) — the ONLY rung whose controller can
  reach the terminal (`fuel_cap > VM_FUEL`) and thus `_escape`. **The pi is the
  sole escape key** (TE-invariant): no abacus/watch/calculator path reaches the
  breakout.
`_grant_tech(colony, tech)` adds to `colony.techs` (idempotent) and logs the
first acquisition once.

## TE4 — Fire as a native technology (recognition only)
Fire already exists (torches T45, wildfire, dry-lightning). T1 adds NO new fire
behavior — it RECOGNISES it: a colony that fields a torch-bearing unit (the
`unit.torch = True` path in `Colony.spawn_unit`) gains the `fire` tech. This is
the first native tech and the template for T2's practice-based acquisition.

## TE5 — Surfacing
- `build_state` per-colony gains `"techs": sorted(list(colony.techs))`.
- Dashboard house card shows a house's techs ("tech: fire, farming"); the
  live-view inspect panel lists them.
- Inheritance: cadet branches inherit the bloodline's techs (respawn — crossover
  = union of both parents' `techs`; single-parent = a copy), and `tech_xp`
  likewise. Extends the existing `breached`/`memory_augment` inheritance block.
- The inspiration doc gains a Civilization section (Civ tech tree, Dwarf-Fortress
  skills, historical progression fire→farming→metallurgy; foreign vs native;
  diffusion by observe/barter/conquer).

## TE6 — Acceptance (tests/test_tech.py)
- `techs`/`tech_xp` default empty, pickle, and inherit on respawn (crossover
  unions, single-parent copies).
- `GIFT_LADDER == ('abacus','watch','calculator','pi')`; claiming each foreign
  gift grants the matching tech; ONLY the pi yields a terminal-capable controller
  (pi-only-escape invariant).
- Fielding a torch grants the `fire` tech.
- `build_state` exposes a colony's techs.
- `TECH_REGISTRY` covers every foreign + native id with a kind.
- State is DEFAULT-NEUTRAL (no behavior change at empty techs); `Enhanced
  SandKingsSimulation.step` stays inert.

## Status / Reconciliation
- Drafted 2026-07-10; implemented the same session (T1 of the Tech &
  Civilization arc). T2 (acquisition/bonuses/skills) and T3 (diffusion) extend
  this spec.
