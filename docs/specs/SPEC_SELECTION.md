# SPEC — Fitness-based live selection ("evolution proper", Phase 1)

Status: IN PROGRESS (Evolution Proper arc, Phase 1). Baseline-ON, no CLI flag (entrypoint-unconditional). Foundational:
makes the existing live GA actually select for fitness. Standalone: Phase 2 (the heritable behavioral repertoire —
`SPEC_AFFORDANCES`, the liability/affordance model that supersedes the old "caste phases" placeholder) reads and is
selected on by this Phase-1 fitness signal, but this phase has no dependency on it. Shared seam: `_respawn_colony` +
the genome.

## Why

The live GA's parent selection is **not fitness-based**. When a dead colony's slot is refilled, the parent is
`random.choice(survivors)` (`sandkings.py:7600`) — chosen *uniformly at random among the living*. The only
selection pressure is "be alive when a slot opens"; a thriving colony and a barely-surviving one are equally
likely to seed the next arrival. A real fitness-ranked GA exists but only in the orphaned offline
`sandkings_evolution.py`. This phase wires fitness into the *live* parent pick — the smallest edit that turns
survival-respawn into **survival of the fittest**.

Gate `FITNESS_SELECTION_ENABLED` (sandkings module default False → battery byte-identical; in `_GATE_NAMES`;
entrypoint flips it on unconditionally — no opt-out flag). Module global only (no cross-module reader). Deterministic given RNG.
Constants (sandkings.py, provisional/configurable): `FITNESS_TOURNAMENT_K=3` (contenders per tournament),
`FITNESS_TERRITORY_W=2.0`, `FITNESS_LONGEVITY_W=5.0` (fitness weights on territory size and lineage depth).

## SEL1 — Fitness signal (`_colony_fitness`, pure read)

`_colony_fitness(colony) = composite_power(colony) + FITNESS_TERRITORY_W·|territory| +
FITNESS_LONGEVITY_W·generation`. Reuses the existing `composite_power` (`sandkings.py:716` — military + wealth +
tech), plus a territory (expansion) term and a lineage-depth (longevity/survival) term. All getattr-guarded
(pre-feature pickles safe). Higher = a colony that is thriving, expansive, and long-surviving.

## SEL2 — Tournament parent selection (`_select_parent`, gated)

`_select_parent(survivors)`: sample `min(FITNESS_TOURNAMENT_K, len(survivors))` survivors without replacement and
return the one with the highest `_colony_fitness`. Tournament selection [standard GA] gives tunable, rank-based
pressure (K controls intensity) without needing normalized fitness. Called at `_respawn_colony` **only under the
gate**; off → the call site runs the original `random.choice(survivors)` verbatim (same single RNG draw → the
regression battery is byte-identical). The fitter initial parent then flows into BOTH downstream paths unchanged:
the asexual `parent.genome.mutate` path directly, and the sexual-path entry (which keys off the initial parent's
`use_neural`). `_choose_mates` is left as-is — it already biases the sexual path (conquest = strongest by `power`).

## Acceptance (`tests/test_selection.py`)

- **Gate default off:** `FITNESS_SELECTION_ENABLED` is False.
- **SEL1 ordering:** `_colony_fitness` ranks a rich/expansive/old colony above a poor/small/young one; equal-state
  colonies tie.
- **SEL2 selects the fittest:** with the gate on, over many tournaments on a fixed survivor set, the highest-fitness
  colony is chosen far above the uniform `1/n` rate; a dominant-fitness colony wins its tournaments deterministically
  when it is among the sampled contenders.
- **Gate-off byte-identity:** with the gate off, `_respawn_colony`'s parent pick is exactly `random.choice(survivors)`
  (same RNG draw). Full battery byte-identical with the gate off.
- **Soak:** over many respawns on a lean world, mean colony fitness trends upward with the gate on vs ~flat with it
  off (selection pressure is doing work).
