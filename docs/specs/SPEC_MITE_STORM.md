# SPEC — The Mite Storm: a contagious infestation (locust plague → disease under the skin)

Status: INCREMENT 1 + 2 IMPLEMENTED, baseline-ON. Inc 1 gate `MITE_STORM_ENABLED`; **Inc 2 gate `MITE_HERBAL_ENABLED`**
(both default False → battery byte-identical; entrypoint flips on). Increment 2 (2026-07-20): **herbal cure** — an
infested host adjacent to crops is cured at a DERIVED rate = local crop density (the remedy grows among cultivation);
**quarantine** — the colony isolates a host with probability = its DERIVED healthy fraction (an overwhelmed house
cannot contain → the outbreak runs), and a quarantined host cannot spread the contagion. Validated
`tests/test_mite_inc2.py`. Extends
SPEC_WEATHER (the storm trigger) and reuses the poison-DoT / water / corpse patterns. The one weather event that
INFESTS the living, not just the land.

## Why (the keeper's design)

A mite swarm follows the green flush, but the danger isn't the eaten crops — it's that the mites get **under the
skin**: an infested unit is a diseased host that **spreads to others**. The colony must **quarantine** or **clean**
the infested (drown the mites in water, or apply herbal knowledge), and when a host can't be cured it faces the hard
triage — **cull the afflicted** before they infect the rest, or let the contagion run. This makes the mite storm a
famine source AND an emergent disease-management crisis, feeding SPEC_SCARCITY_WAR / SPEC_WINTER.

## Increments

- **Increment 1 (this build):** the storm INFESTS exposed hosts; infestation is a contagious DoT that spreads to
  adjacent hosts (kin AND enemy — biological spillover) and kills the unchecked; **water cures it** (an infested
  unit adjacent to WATER drowns the mites). Gated, byte-identical off.
- **Increment 2 (queued):** herbal-knowledge cure (a codex/tech remedy a colony can learn), deliberate QUARANTINE
  (isolate the infested), and the emergent CULL decision (the maw/genome triages — kill the afflicted to save the
  brood — driven by temperament + curability, not an authored threshold).

## Decisions (resolved; no authored magic constants)

- **Emergent storm trigger:** Growth/Dust seasons, on the existing storm cadence, chance = the surface's standing-
  vegetation coverage (boom-bust). Non-overlapping with sandstorm/hail (mirror `mite_until`).
- **Infestation is a boolean host state** `unit.infested` (like `poisoned_until`), not an authored "load" number.
- **Reused rates:** DoT while infested = `POISON_DAMAGE` (mites drain the host like a toxin); storm window duration
  = `STORM_DURATION`. **Water cure is binary** — adjacent to `WATER` ⇒ cured (no rate constant). **Contagion is
  bounded** — an infested host infects at most ONE adjacent uninfested host per tick (no authored probability).

## MS1 — Storm trigger + seeding (`_mite_tick`, near the sandstorm block)

Gated. In Growth/Dust, on the storm cadence, non-overlapping, `random.random() < vegetation_coverage()` ⇒
`mite_until = step + STORM_DURATION`, log "A mite storm descends — the swarm blackens the sky!". While
`mite_until > step`, exposed (surface) units become `infested = True` (the swarm settles on them).

## MS2 — Infestation processing (`_mite_infest_tick`, every step — the disease persists AFTER the storm)

Early-return if no unit is infested (cheap / byte-identical-safe). For each infested host:
- **Cure (drowning):** adjacent to a `WATER` voxel ⇒ `infested = False` (the mites wash off).
- **Else the mites feed:** `take_damage(POISON_DAMAGE)`; on death → remove unit + `CORPSE` voxel.
  - **Contagion:** if it survives, infect ONE random adjacent UNINFESTED host (any colony) — the disease jumps hosts.

## Constants

| Constant | Value | Meaning |
|---|---|---|
| `MITE_STORM_ENABLED` | `False` | gate; module default off (battery byte-identical); entrypoint flips baseline-on |

(No other constants — duration = `STORM_DURATION`, DoT = `POISON_DAMAGE`, cure = binary water adjacency, contagion =
one-host-per-tick. All reused/derived.)

## Acceptance

- Gate off ⇒ `MITE_STORM_ENABLED` False, both ticks early-return with ZERO RNG, weather determinism byte-identical.
- Gate on, vegetated board ⇒ a mite storm eventually fires (chance rises with coverage); barren board never triggers.
- An infested host next to water is cured; away from water it takes `POISON_DAMAGE` and, surviving, infects one
  adjacent host; unchecked infestation kills the host (corpse), and the contagion spreads across colonies.

## Gating

`MITE_STORM_ENABLED` module default False → `run_tests._GATE_NAMES` → entrypoint baseline-on. Off ⇒ no storm, no
infestation, byte-identical.
