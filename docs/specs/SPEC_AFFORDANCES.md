# SPEC — Affordances: heritable behavioral repertoire ("evolution proper", Phase 2)

Status: IN PROGRESS (Evolution Proper arc, Phase 2 — the heritable behavioral repertoire). Baseline-ON, no CLI flag
(entrypoint-unconditional). Depends on the SEMIPERMEABLE `soft_gate` primitive (`sandkings.py:897`); realizes decision
D1 (`docs/decisions/2026-07-15-emergence-over-rules-affordances.md`, 2026-07-15). Reads and is selected on by the
Phase-1 fitness signal (SPEC_SELECTION) — both hook the same `_respawn_colony` / genome seam.

## Why

Every dynamic shipped this session (poison, siege, priests, madness, holy war, scorched earth) is a **threshold rule** —
a hand-tuned `if cold and food>X` the author picked. The maw-RL directive layer already proves the alternative:
`apply_directive` (`maw_brain.py:146`) warm-starts a colony's aggression/mobility/verticality from its genome and lets
the policy tune the DECISION, identity at neutral. New capabilities keep being bolted on as fresh thresholds instead of
routed through that layer. D1 resolves the tension: a mechanic has two separable parts, and only one must be a rule.

- **The mechanic** (what fire DOES, what a granary IS) — unavoidably a thin, physical rule. Keep these small.
- **The decision** (does THIS house torch the enemy's grain? build a granary now?) — this SHOULD come from the genome +
  the neural policy, NOT an authored threshold.

The target for every new dynamic is an **affordance**: a thin MECHANIC + a cheap PRECONDITION + a DECISION that is
`trait AND policy-wants-it`. The genome carries no new bits: each affordance's presence is a **liability** — a
non-additive product of two existing continuous genes (Tukey one-degree-of-freedom sense, `p_i·p_j`), quantized to an
ordinal level, passed through a **soft/learnable cut** (`soft_gate`, identity at `temp<=0`). Epistasis is the point (a
trait needs BOTH terms); pleiotropy is free (`patience` feeds two affordances). The author writes ONLY the potentials
(reused genes), the interaction map, and the cut — expression emerges and evolves. This phase makes the model concrete
and ships **scorched earth end-to-end** as its reference implementation.

Gate `AFFORDANCES_ENABLED` (sandkings module default False → battery byte-identical; in `_GATE_NAMES`; entrypoint flips
it on unconditionally — no opt-out flag, matching the SELECTION precedent). Module global only. Liability and level are
**pure genome reads** (no RNG); expression draws ride the seeded module `random` stream (deterministic given seed).
Constants (sandkings.py, provisional/configurable): `AFF_LEVELS=4` (ordinal strength buckets), `AFF_CENTER=0.25`
(neutral genome liability → coin-flip-ish presence), `AFF_TEMP=0.0` (soft-cut softness; **0 = identity/hard step**;
learnable). All values `[prov:B fit=affordance-liveness]`; `AFF_TEMP=0.0` is the load-bearing identity constant.

## AF1 — The liability primitive (`_affordance_liability`, `_affordance_level`, `_affordance_p`; pure reads)

The reusable core. **No new genome fields** — potentials are the existing continuous temperament genes
(`ColonyGenome`, `sandkings.py:1222`). The single authored rule is the interaction map:

```
AFFORDANCE_MAP = {
    'scorched_earth':   ('aggression',  ('inv', 'loyalty')),   # aggression * (1 - loyalty)
    'builds_granaries': ('patience',    'expansion_rate'),      # patience   * expansion_rate
    'keeps_livestock':  ('patience',    'resilience'),          # patience   * resilience
}
```

| affordance key      | liability (interaction)      | reading                                        |
|---------------------|------------------------------|------------------------------------------------|
| `scorched_earth`    | `aggression · (1 − loyalty)` | cruel AND faithless → burns what it can't hold |
| `builds_granaries`  | `patience · expansion_rate`  | patient growth → stockpiles and builds         |
| `keeps_livestock`   | `patience · resilience`      | a husbandry temperament                        |

> Gene-name note: the expansion gene is `expansion_rate` (`sandkings.py:1226`), not `expansion` — D1's table used the
> short form. Each map term is either a gene name (read `getattr(genome, name, 0.5)`) or `('inv', name)` (read
> `1 − getattr(genome, name, 0.5)`), so a term can invert a potential.

- `_affordance_liability(genome, key) -> float` in `[0,1]`: the product of the two mapped terms, getattr-guarded (pre-
  feature pickles safe). Pure — no RNG, no mutation.
- `_affordance_level(liability) -> int` in `0..AFF_LEVELS-1`: ordinal quantization by even bucketing,
  `int(np.clip(liability * AFF_LEVELS, 0, AFF_LEVELS-1))` — reuses the pervasive `int(np.clip(...))` tiering idiom
  (`season_index` precedent, `sandkings.py:2657`). This is the "how available is it" strength grade the RL reads.
- `_affordance_p(liability) -> float` in `[0,1]`: `soft_gate(liability, AFF_CENTER, AFF_TEMP)` — the presence
  probability; the CALLER draws `rng.random() < p`. At `AFF_TEMP == 0.0` (default) this is the exact hard step
  `1.0 if liability > AFF_CENTER else 0.0` — byte-identical to an authored threshold, so combined with
  `AFFORDANCES_ENABLED == False` the battery is unmoved.

**Contract (AF1):**
- **Require** — `genome` exposes the mapped gene attrs (else getattr default 0.5); `key` in `AFFORDANCE_MAP`.
- **Guarantee** — `_affordance_liability` in `[0,1]`, deterministic, consumes NO RNG; neutral genome (all 0.5) gives
  `scorched_earth` liability `0.25`; `_affordance_level` is monotone non-decreasing in liability and in `[0, AFF_LEVELS)`;
  `_affordance_p` in `[0,1]`, `AFF_TEMP==0` ⇒ hard step at `AFF_CENTER`, no RNG.
- **Maintain** — a single source of truth for each affordance's genes (the map); call-sites never inline gene products.
- **Assert** — `_affordance_liability(neutral, 'scorched_earth') == 0.25`; `_affordance_p(l) ∈ {0.0,1.0}` when
  `AFF_TEMP==0`.

## AF2 — The maw-RL wiring (levels in as features, one directive channel out per affordance)

Realizes D1(a) ("the RL reads the quantized liability *levels*, not the raw potentials") and the decision record's "new
affordances become new directive channels." Gated by `MAW_RL_ENABLED` exactly as today; non-neural sims are unaffected.

- **Feature in.** Append the three `_affordance_level` values (normalized `/ (AFF_LEVELS-1)`) to the obs `stats` tensor
  in `_maw_rl_tick` (`sandkings.py:2531–2540`), extending obs 39 → 42. Small, legible — the interaction+threshold already
  did the epistasis; the policy decides off what the organism *can* do.
- **Channel out.** Extend `MAW_DIRECTIVE_DIM` 4 → 7 (`maw_brain.py:44`); the three new channels
  (d4 scorched_earth, d5 granaries, d6 livestock) are warm-started from each affordance's normalized level in the warm
  tensor (`sandkings.py:2546–2554`, appended after d3). `apply_directive` (`maw_brain.py:146`) is **NOT** touched — it
  tilts only the 7-action move/attack space off d0–d2; the new channels are read by the affordance sites (AF3–AF5), so
  movement/attack stays identity-at-0.5 (SPA regression).
- **Decision rule** (every affordance): `take = (rng.random() < _affordance_p(liability)) AND (directive_dK > 0.5)`.
  Non-neural sims (no `colony.maw_directive`) fall back to the trait-only soft-cut (`directive_dK` treated as neutral
  0.5 → the `> 0.5` term is skipped). This is D1's `trait AND policy-wants-it` — no new threshold ladder.

**Contract (AF2):**
- **Require** — obs rebuild path (`sandkings.py:2542`) reconstructs the policy when `obs_dim` changes; `MAW_DIRECTIVE_DIM`
  read consistently by `MawPolicy`/`ColonyMawRL`.
- **Guarantee** — with `MAW_RL_ENABLED == False`, zero change (the tick returns early); with it on, obs dim is 42 and the
  directive is 7-d; the three new channels initialize to the genome affordance levels; `apply_directive`'s move/attack
  output is unchanged at neutral.
- **Maintain** — the directive is emitted once per RL cycle (`colony.maw_directive`), read by AF3–AF5.

## AF3 — Scorched earth (the reference implementation, `_scorched_earth_step`, gated)

**Build this FIRST** — D1 names it the pattern's end-to-end reference. Proves liability → soft-cut → RL channel →
mechanic before the map generalizes.

- **Mechanic** — reuse `_ignite(pos)` (`sandkings.py:3165`); fire spread (`_fire_tick`, `:3170`) already damages units
  and razes crop/food to SAND. No new fire code.
- **Precondition** (cheap physical gate) — an at-war soldier adjacent (Chebyshev 1, `get_neighbors_3d(..., radius=1)`) to
  an **enemy-owned** flammable food voxel: `world.voxels[n] in (CROP, CROP_RIPE)` with
  `world.ownership[n] != colony.colony_id`. This mirrors the existing torch-ignition surface (`:9225–9236`) and the T21
  field-raze surface (`:9237–9241`), reusing `world.ownership` for the enemy check.
- **Decision** — AF2's rule on channel d4 + liability `aggression·(1−loyalty)`. NOT "if at_war and adjacent then burn."
- **Wiring** — call `_scorched_earth_step` in the soldier AI beside the torch site (`:9225`), under
  `AFFORDANCES_ENABLED`; on success `_ignite` the cell and emit a salient event ("House X torches the fields of House Y
  to starve them out"). Consumes the action like the adjacent torch/raze branches.

**Contract (AF3):**
- **Require** — `AFFORDANCES_ENABLED`; a soldier with a valid position; an adjacent enemy-owned CROP/CROP_RIPE voxel.
- **Guarantee** — ignites at most one adjacent enemy food voxel per call; only when the trait+policy decision passes;
  gate off ⇒ no call, no `_ignite`, RNG stream unmoved.
- **Maintain** — reuses the fire registry; no new voxel damage path.

## AF4 — Builds granaries (`_granary_step`, gated, reuses the castle build pattern)

- **Mechanic** — a new never-rot `VoxelType.GRANARY` raised by the `_castle_step` ring-scan (`_granary_step`): scan the
  `PALISADE_RING+1` Chebyshev ring around `colony.maw.position` on the ODD cells (the crenellations the castle's even
  cells leave free), walk the builder there (`_step_toward`, same as castle), set `world.voxels[best] =
  VoxelType.GRANARY.value` + `world.ownership[best] = colony.colony_id`, cost `colony.maw.food_stored -= 2` (labor fed,
  mirroring `_castle_step`), NO rot registration; increment `colony.granaries` (getattr-guarded). While ≥1 granary the
  colony owns stands, it **keeps the `BOOTSTRAP_FLOOR`** even when the Chill lifts it for everyone else (the shelter
  reuses the existing survival-floor constant — no new magic number).
- **Precondition** — physical: `season_index() == 3` (the Chill) AND `colony.maw.food_stored > BOOTSTRAP_FLOOR` (a
  surplus above bare survival worth sheltering — the existing floor constant, not an authored threshold).
- **Decision** — AF2's rule on channel d5 + liability `patience·expansion_rate`.

**Contract (AF4):** gate off ⇒ no build, no shelter, byte-identical; on build, one GRANARY voxel per successful step,
never rots; `food_stored` never goes negative from the build cost (guard `>= 2`).

## AF5 — Keeps livestock (`_livestock_gate`, gated, reuses domestication)

- **Mechanic** — the existing `_taming_tick` (`sandkings.py:6084`) / `_tamed_work` (`:6128`) machinery. NO new mechanic.
- **Change** — gate WHICH houses tame on the `keeps_livestock` trait (level `patience·resilience`) + AF2's channel d6,
  rather than the global `DOMESTICATION_ENABLED` flag deciding for all. When `AFFORDANCES_ENABLED`, a beast is tameable by
  a colony only if that colony passes the livestock affordance decision; mice-as-cattle (`hunt_range 0`, under
  `TAME_DANGER_CEIL=65`) already qualify. `DOMESTICATION_ENABLED` off ⇒ the affordance is inert (no taming machinery to
  gate).
- **Decision** — AF2's rule on channel d6 + liability `patience·resilience`.

**Contract (AF5):** gate off ⇒ taming behaves exactly as today (global flag only); on, a colony that fails the livestock
decision does not tame; the taming/upkeep/yield math (`TAME_FORAGE_YIELD=8`, etc.) is unchanged.

## AF6 — Constants

| Constant | Value | Provenance | Meaning |
|---|---|---|---|
| `AFFORDANCES_ENABLED` | `False` | `[prov:— gate]` | module default off → battery byte-identical; in `_GATE_NAMES`; entrypoint flips True unconditionally |
| `AFF_LEVELS` | `4` | `[prov:B fit=affordance-liveness]` | ordinal strength buckets for `_affordance_level` |
| `AFF_CENTER` | `0.25` | `[prov:B fit=affordance-liveness]` | the liability at which the soft cut is a coin-flip; `0.25` = neutral genome (all 0.5) sits at the cut |
| `AFF_TEMP` | `0.0` | `[prov:B fit=affordance-liveness]` | soft-cut softness; **`0.0` = identity/hard step at `AFF_CENTER`**; `>0` = logistic; learnable |
| `VoxelType.GRANARY` | `21` | `[prov:— reuse]` | never-rot food-shelter structure; built like CASTLE |

**No new granary magic constants.** AF4 deliberately reuses the existing `BOOTSTRAP_FLOOR` for BOTH the build
precondition ("a surplus above bare survival") AND the winter shelter level — an authored `GRANARY_FOOD_FLOOR`/
`GRANARY_SHELTER` threshold would be exactly the `if metric > C` anti-pattern this arc exists to remove. The only
affordance parameters are the model's own `AFF_*` (the liability quantization and soft cut, per D1) plus the build cost
`-= 2` inherited from `_castle_step`.

Place the scalar constants in a new `# Affordances (SPEC_AFFORDANCES, Evolution Proper Phase 2)` block; add
`AFFORDANCES_ENABLED` to `run_tests._GATE_NAMES` (and thus the reset tuple). Do NOT fabricate citations for the numeric
values — they are chosen for identity (`AFF_TEMP=0.0`) and neutral-genome centering (`AFF_CENTER=0.25`); tuning them is
`[prov:B]` fit work that shifts the shared RNG trajectory once a soft draw is consumed.

**The evolve/fit seam (documented, not implemented).** `(AFF_CENTER, AFF_TEMP)` are the natural contents of a per-colony
`GateParam` (SEMIPERMEABLE SP3): a colony could carry `colony.affordance_gate[key] = GateParam(center=AFF_CENTER,
temp=AFF_TEMP)` and each site would read `.prob(liability)` instead of the module constants — letting each house evolve
its own expression threshold. This is the SP3.1 per-colony seam; module constants only in this pass.

## Acceptance (`tests/test_affordances.py`)

- **Gate default off:** `AFFORDANCES_ENABLED` is `False`.
- **AF1 liability/level (pure):** `_affordance_liability` equals the mapped product over a battery of ≥3 varied genomes
  (incl. neutral → `scorched_earth == 0.25`); the `('inv', gene)` term inverts; `_affordance_level` buckets monotonically
  into `[0, AFF_LEVELS)`; equal-liability genomes tie.
- **AF1 soft-cut identity:** with `AFF_TEMP == 0.0`, `_affordance_p(l)` equals `1.0 if l > AFF_CENTER else 0.0` across a
  battery straddling `AFF_CENTER`, and consumes **zero** RNG draws (counting spy).
- **AF2 wiring (neural):** with `MAW_RL_ENABLED` on, obs dim is 42; the three new directive channels initialize to the
  genome's normalized affordance levels; `apply_directive`'s move/attack output is byte-identical at neutral d0–d2
  (regression — the new channels do not tilt the 7-action space).
- **AF3 scorched earth:** with the gate on, a cruel-faithless colony's at-war soldier adjacent to an enemy-owned crop
  ignites it (cell enters the fire registry); a loyal/gentle colony in the same state does not; the ignite reuses
  `_ignite` (no new fire path). Forced-roll probe makes the decision deterministic.
- **AF4 granaries:** a patient-expansive colony in the Chill (`season_index()==3`) with stored food raises exactly one
  never-rot GRANARY voxel and its `food_stored` is sheltered from the winter floor-lift; a low-trait colony does not
  build; `food_stored` never goes negative.
- **AF5 livestock:** with `DOMESTICATION_ENABLED` on, a patient-resilient colony tames an adjacent mouse; a low-trait
  colony does not; the taming/yield math is unchanged.
- **Gate-off byte-identity:** with `AFFORDANCES_ENABLED` off, every AF3–AF5 site runs the exact pre-feature path (no
  ignite, no build, global-flag-only taming); the full battery is byte-identical.
- **Soak:** over many respawns on a lean world, the population's expressed affordance mix tracks the evolving genome —
  as Phase-1 fitness selection shifts the gene distribution, `_affordance_level` histograms shift with it (the
  liability model is heritable and selected on, not static).

## Status / Reconciliation

- Drafted + implemented + verified 2026-07-16 (Evolution Proper Phase 2). All five phases shipped baseline-on
  (`AFFORDANCES_ENABLED` flips True at the entrypoint; module default False keeps the battery byte-identical).
- Code (`sim/sandkings.py`): AF constants + `AFFORDANCE_MAP`/`AFFORDANCE_CHANNEL`; the pure `_affordance_liability`/
  `_affordance_level`/`_affordance_p` helpers (beside `soft_gate`); the shared `_affordance_take` decision; AF3
  `_scorched_earth_step` + soldier-branch call site; AF4 `VoxelType.GRANARY=21` (+ `is_solid`), `_granary_step`,
  `_try_build` branch, `_feed_terrarium` shelter; AF5 `_taming_tick` gate. AF2 in `sim/maw_brain.py`
  (`MAW_DIRECTIVE_DIM 4→7`) + the obs(39→42)/warm(7) build in `_maw_rl_tick`. Glyph in `sim/live_view.py`.
- **No new magic constants** (per user direction): AF4's build precondition and winter shelter both reuse the existing
  `BOOTSTRAP_FLOOR`; the granary build cost reuses `_castle_step`'s `-= 2`. The `GRANARY_FOOD_FLOOR`/`GRANARY_SHELTER`
  thresholds sketched in an earlier draft were removed as the exact `if metric > C` anti-pattern this arc replaces.
- Acceptance: `tests/test_affordances.py` (14 tests) green; `tests/test_maw_rl.py` two toy-learning tests pinned to the
  core directive dim (4) since they predate the affordance channels. Full battery 62 passed / 11 failed **on the py310
  host** — all 11 failures are `pygame`/`fastapi` import gaps (those libs live only in the Docker image), none touch
  affordances; byte-identical to the pre-feature baseline. A definitive full-green battery needs the container.
- Live-verified: a headless run with `MAW_RL_ENABLED` on builds obs dim 42 / directive dim 7 and runs 600 steps
  clean; a patient-expansive population raises granaries in the Chill (37 GRANARY voxels at season 3).
- Regression caught + fixed during delivery: the AF4 insert initially severed `_castle_step`'s trailing
  `_step_toward` walk (the worker never reached the ring) — restored, and `_granary_step` given the same walk.
</content>
