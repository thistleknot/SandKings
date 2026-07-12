# Decision: Dynamic population & succession (bounded-pool model)

Date: 2026-07-11. Status: accepted (architecture); implementation phased, flag-gated.

## Problem / vision

The colony count should NOT always be 4. ~4 is a natural *equilibrium*, not a
constant: colonies can try to spawn more (crowding → war pressure over limited
resources), and when the board is sparse (~2) unused territory invites new colonies
to fill in. And a queen's death should be a *succession drama*, not an automatic
respawn — most spawn go mad when the psionic network collapses, but a rare **Spartan**
heir can resist, promote, and reclaim the line (Starks reclaiming Winterfell); only if
no heir survives does the house go truly extinct (disgraced gravestone).

## Architectural decision — BOUNDED POOL (not truly dynamic)

A fixed pool of `MAX_COLONIES = 8` slots, each carrying a lifecycle state
`ACTIVE | SUCCESSION | DORMANT`. Emergent population (breathing 2..8 around K≈4)
is delivered by activation transitions, NOT by a variable-length colony set.

Rationale: a truly-dynamic colony set would force an index-invalidation audit of every
`colony_id`-keyed structure — pheromone channels (ctor-fixed), the politics relation
matrix (a save/load shape contract), the modulo-indexed color palette (`Colony.COLORS`,
a 4-tuple), the dashboard, and dangling `laboring_for`/`gift_to` refs. Bounded-pool keeps
every structure shape-stable and localizes all churn into slot *state* plus one scrub
choke point. It delivers the emergent-population feel; the only thing given up is a truly
unbounded swarm (8 is the ceiling — an executive call, revisitable).

## Succession — the heir is unit state, not a new class

On queen death the colony enters SUCCESSION. Exactly one **Spartan** aspirant
(high loyalty ∧ high psionic gene) gets an ~800-step (half-year) window: debuffed,
confused, **pheromone-only**, **subjugation-immune** (never submits, fights to death),
with a rally radius for siblings and a **revolt surge** that can free subjugated siblings
in enemy territory. If it survives, the rise reuses the existing maw-construction/rebind
path — the **same house continues** ("Restored" lineage event, relations intact). The
rise is a **terminal molt** (SPEC_METAMORPHOSIS) with an **augmented neural net**
(SPEC_AUGMENTS, brain-ceiling growth, the neural hive) and boosted stats — the
half-year is *preparation for molting into a maw*. Non-aspirant spawn suffer unit-level
collapse-madness. Cadet-branching relocates from death-respawn to prosperity budding.
If no aspirant survives, the house goes extinct + disgraced (folds in the SPEC_MADNESS
draft's gravestone/epithet).

## Identity-at-neutral, phased, flag-gated

`dynamic_population = False` by default through phases 0–8: pool of `num_colonies` (4)
all-ACTIVE, the legacy `_check_maw_deaths → pending_respawns → _process_respawns →
_respawn_colony` spine untouched and **byte-identical**, the 45-suite battery green at
every phase. The flag flips on only in phase 9, when the legacy fork is deleted or
re-expressed as a degenerate succession config.

Load-bearing correctness: a total slot scrub (`_deactivate_slot`) must NOT be wired into
today's respawn — the current teardown intentionally keeps inbound trust as the P12
folk-memory shadow (dampened by `apply_respawn_shadow`). The scrub stays standalone and
is called only by the flag-gated DORMANT/founding paths where a full wipe is intended.

## Per-module spec build order

0. **SPEC_POPULATION** (pool, lifecycle states, the `dynamic_population` flag, the
   `_deactivate_slot` scrub choke point + inventory, save shim). Inert at flag-off.
1. SPEC_TERRARIUM_LIVENESS revision (T5/T6 → a population *floor*, liveness via founding).
2. SPEC_MADNESS repair (collapse-madness of non-aspirant spawn; resolves its open Qs).
3. SPEC_SUCCESSION (aspirant lifecycle; rise = molt + augment + brain growth).
4. SPEC_PSIONIC ext (psionic promotion) → 5. SPEC_SUBJUGATION ext (revolt surge, join-the-heir).
6. SPEC_FOUNDING (budding when crowded-and-prosperous; fill-in when sparse).
7. SPEC_DYNASTIES ext → 8. SPEC_POLITICS ext → 9. flag flip + test/dashboard reconciliation.

## Top risks
1. **Slot-reuse hygiene** (trickiest): a refounded slot must not inherit stale
   pheromones/relations/grudges/thralls — one `_deactivate_slot` choke point + a
   permutation battery. `house_grudges` is keyed by house *name* (lineage), not slot —
   scrub leaves it intact.
2. **Liveness via founding could heat-death** — a deterministic probability ramp to 1.0
   by a founding deadline + the retained injector.
3. **Succession tuning valley** (aspirants always/never rise) — an explicit ~30–60%
   rise-rate acceptance criterion.

## Implementation status (2026-07-11) — succession core landed, flag-gated & inert

Implemented directly, all behind `DYNAMIC_POPULATION=False` (byte-identical at flag-off,
battery unchanged):
- **Phase 0** (prior): pool constants (`MAX_COLONIES=8`, `POP_ACTIVE/SUCCESSION/DORMANT`,
  the flag), `_deactivate_slot` full-scrub choke point (14 surfaces, `house_grudges` left
  intact), `_colony_by_id`. Unwired.
- **Phase 1**: `MIN_ACTIVE_COLONIES=2` liveness floor + `_active_colony_count()`.
- **Phase 2** (disgrace): at the death-judgment in `_check_maw_deaths`, a flag-gated
  chronicle fork — a high-loyalty house "endures the collapse, an heir stirs"; a
  low-loyalty house "falls in disgrace, its spawn go mad" (gravestone via the existing
  `has fallen`/`will be remembered` salience).
- **Phase 3** (succession core — the narrative heart): in `_respawn_colony`, a flag-gated
  **Spartan-heir reclamation** fork. Model reconciliation: units share the colony genome
  (no per-unit genes), so "the Spartan spawn" = a **loyalty-gated lineage continuation**,
  not an individually-varied unit. When the dead slot's genome `loyalty >= SPARTAN_LOYALTY`
  (0.7), the SAME house continues (generation+1, inherits temperament/techs/stage/awakening
  from the dead line, `RESTORED` event) with the mind **augmented** (`loyalty`/`brain_hidden`
  ×`SPARTAN_BOOST`=1.3, `use_neural=True`, `memory_augment≥1`) — the "boosted stats +
  augmented neural net in preparation for molting into a maw." Below the gate → the normal
  cadet/fresh path (a rival seizes the vacant nest). Constants: `SPARTAN_LOYALTY`,
  `SPARTAN_BOOST`, `SUCCESSION_WINDOW=800` (reserved for the live-aspirant variant).

**All phases now implemented (2026-07-11, second pass).** Phases 4–9 landed directly:
- **Phase 6 (bounded pool + founding/budding)**: `__init__` sizes the pheromone axis and
  slot pool to `MAX_COLONIES` when dynamic; `_pad_dormant_slots` seats DORMANT placeholders
  (not-alive `Colony`, skipped by every `is_alive()` guard); `_population_tick` fills in when
  sparse (below the floor, urgently) and buds a daughter when crowded + a house is prosperous
  (`BUD_FOOD`), capped at 8. Politics is dict-keyed (lazy) so no matrix resize is needed —
  only the pheromone array is fixed-size.
- **Phase 3 live form**: on a Spartan queen's death `_check_maw_deaths` forks to
  `_begin_succession` (a live `POP_SUCCESSION` window, `SUCCESSION_WINDOW` steps; non-heir
  spawn suffer collapse-madness, a small honor guard endures). `_succession_tick` advances it;
  at the deadline `_molt_aspirant` rebuilds the maw from the aspirant with a Spartan-boosted,
  augmented genome (the SAME house, `RESTORED`); a fallen heir → `_fail_succession` (extinct +
  disgrace, slot rejoins the respawn spine). The committed reclaim-via-respawn is now the
  *fallback* when the house is wiped with no surviving heir.
- **Phase 4 (psionic promotion)**: the aspirant's `brain_hidden` ramps through the window.
- **Phase 5 (revolt surge)**: subjugated siblings in a succeeding house break free (defiance→1).
- **Phase 7 (dynasties)**: chronicle salience rows for RESTORED / extinguished / disgrace /
  aspirant-rises / buds-a-daughter / founding.
- **Phase 8 (politics)**: covered by name-keyed kinship — a bud inherits the parent's house,
  so grudges/kinship apply; `_fail_succession` routes through `clear_slot`.

**Load-bearing bug found & fixed at flag-flip:** a `POP_SUCCESSION` colony is not-alive
(queen dead), so `_check_maw_deaths` re-processed it as a fresh death every step and corpsed
its own aspirant one step in. Fix: skip `POP_SUCCESSION` (and `POP_DORMANT`) colonies at the
top of the death loop — the same treatment dormant slots get.

**Phase 9 status:** flag-off battery **46/0** (all new code inert at default). Flag-on smoke
(4000 steps, forced deaths) ran with no crash: population breathes 2↔6, dormant pool draws
down as founding/budding fire, and succession produces both `RESTORED` molts (multi-generation
dynasties — Maul-Den I→II→III) and `extinguished` failures. Shipped as **opt-in**: the module
default `DYNAMIC_POPULATION=False` stays (battery/identity green, no test reconciliation
needed); the runnable game turns it on with **`--dynamic`** (a `dynamic_population` ctor arg
threaded through `sandkings.py main()` and `dashboard.py`).

**Remaining (tuning, not implementation):** the aspirant is currently undefended during its
window (some heirs die within a few steps) — tune survivability + the `SPARTAN_LOYALTY` gate to
the ~30–60% rise-rate target, and add a dedicated SUCCESSION acceptance suite. These are
polish; the system is functional end-to-end.

## Corrections to the initial architect sketch (verified against code, 2026-07-11)
The initial scope was drafted without reading the code. Verified: the merge-debris
"duplicate `pending_respawns` init" and "duplicate `record_event`" claims are FALSE
(`record_event` does not exist; one `pending_respawns` init at `sandkings.py:1570`).
`COLOR_PAIRS` and `bound_to` do not exist (real: `Colony.COLORS`, `laboring_for`,
`gift_to`). This record supersedes that sketch.
