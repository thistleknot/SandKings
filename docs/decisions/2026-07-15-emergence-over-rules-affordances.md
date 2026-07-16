# Decision: Emergence over Rules — Affordances + Genome-Expressed Decisions

Date: 2026-07-15
Status: DIRECTION ACCEPTED; the genome-shape sub-decision (D1 below) is OPEN — user deferred ("discuss more
before I commit"). No code yet; this records the principle and the first worked example (granaries + scorched
earth) so future dynamics are built in this style rather than as more threshold rules.

## The principle (user, verbatim)

> "I would hope these dynamics are LIGHTLY prescribed by fixed rules (or rules the maw can modify) and more so
> on neural net decisions. Because I don't want to have to create a lot of 'rules', I really just want to
> create 'baseline' genetics as a starting point and those genetics are 'binary features' in rl."

## The distinction that resolves most of the tension

A mechanic has two separable parts, and only one of them has to be a rule:

- **The mechanic itself** (what a granary IS, what fire DOES, what scorched earth COSTS) — *unavoidably* a
  fixed rule. You cannot neural-net a granary into existence. Keep these thin and physical.
- **The decision** (does THIS house build a granary now? does it torch the enemy's grain?) — this is where the
  project has been over-prescribing (hand-tuned `if cold and food>X` thresholds). This SHOULD come from the
  genome + the neural policy, not a threshold the author picked.

So the target pattern for every new dynamic is an **affordance**, not a rule:

```
1. MECHANIC        — the effect (a fixed, thin rule): build barn / bring livestock in / ignite grain store.
2. PRECONDITION    — a cheap physical gate (also fixed): it is cold AND the house holds livestock; or the
                     marauder is adjacent to an enemy grain store. This only says the action is POSSIBLE.
3. DECISION        — NOT a threshold. A genome trait the maw-RL expresses: the policy (warm-started from the
                     baseline genome) chooses whether to take the affordance, conditioned on state.
```

The author writes (1) and (2) — small, legible. The author does NOT write (3) as a threshold; (3) is
`trait AND policy-wants-it`. Baseline genetics seed it; evolution + RL tune it. This is exactly what the maw-RL
directive layer already does for aggression/mobility/verticality/forage-mode (`apply_directive`, identity at
neutral, warm-started from genome) — the direction is to route NEW affordances through that same layer instead
of through fresh thresholds.

## What already supports this (so we're building WITH the grain, not against it)

- `maw_brain.py` — a real RL policy emits a colony **directive** (continuous, neutral 0.5, warm-started from
  the genome's instincts). This is the "neural decisions" layer; new affordances become new directive channels.
- `ColonyGenome` (sandkings.py:1222) — the baseline genetics; already has ONE binary gene (`use_neural`).
- The GA (`neuroevolution.py`) evolves the baseline across generations; RL tunes within a life. Two timescales
  already in place.

## What is in tension (named honestly)

- Genes today are **continuous**, not the "binary features" the user wants. (D1 below.)
- Everything shipped this session (poison, siege, priests, madness, holy war) is a **threshold rule**, not a
  policy-selected affordance. Retrofitting those is a large refactor and is NOT promised here; the direction
  applies to NEW dynamics first, and existing ones opportunistically.
- "No rules" is not achievable and the user did not ask for it ("LIGHTLY prescribed"). The win is moving the
  DECISION out of thresholds, not deleting mechanics.

## D1 (OPEN) — the shape of "binary features"

The reframing that likely dissolves the either/or: **binary vs continuous is a per-trait choice, not a global
one.**
- **Magnitudes/temperament** (how aggressive, how patient, how loyal) are naturally **continuous** — and they
  feed the maw-RL warm-start as graded starting points. Forcing these binary is lossy.
- **Capabilities/dispositions** (does this house scorch earth? keep livestock? build granaries?) are naturally
  **binary** — a bit the GA flips, a feature the RL reads, an affordance it unlocks. These ARE the "binary
  features" the user wants, and they are new (the behavioral repertoire), not the existing temperament genes.

**Superseded first idea** (flat binary trait-vector): rejected by the user in favor of *interactions between
potentials* — a bit is too flat; traits should emerge from interacting continuous genes.

**Now-preferred model (user, 2026-07-15; still OPEN):** *"I prefer interactions between potentials. Instead of
binary traits, maybe Tukey's and between two or more interacting terms (also reduced to some non-nominal
quantization), a threshold determines if the feature is present."*

Read as the **quantitative-genetics threshold/liability model with epistasis** (soft-gated, per the
SEMIPERMEABLE direction):
- The genome stays **continuous "potentials"** (latent genes) — no bits stored.
- Each affordance/trait has a **liability** = an **interaction of two+ potentials** — a *non-additive* term
  (`p_i · p_j`, the Tukey one-degree-of-freedom non-additivity sense — a product, not a sum), optionally more
  terms. Epistasis is the point: the trait is not any single gene.
- That liability is **quantized to a non-nominal (ordinal) scale** — binned into ordered levels (matches the
  project's median-cut / statistical-partitioning habit), not a nominal on/off.
- A **threshold** on the quantized liability decides **presence** (and the level grades **strength**). The cut
  should be a **soft/learnable gate** (`soft_gate`, identity at neutral — SEMIPERMEABLE), not a hard `if`.

Why it fits the "don't author rules" goal: the author defines only the **potentials**, the **interaction map**
(which potentials multiply for which affordance), and a soft cut — the GA evolves the potentials and expression
*emerges*; one potential feeds many affordances (pleiotropy) through different interactions. The maw-RL reads
the **potentials and/or the liability levels** as features and expresses the affordance situationally.

**Sub-questions — proposed resolutions (orchestrator's lean, PENDING user sign-off; D1 stays OPEN):**

- **(a) What the RL reads as features** → the **quantized liability *levels*** (the expressed affordance
  strength — "how available is scorch-earth to me"), NOT the raw potentials. The interaction+threshold already
  did the epistasis; the policy decides off what the organism can do, and the input stays small + legible. Raw
  potentials remain in the genome as the evolvable substrate only.
- **(b) Cut** → **soft/learnable** (`soft_gate`, identity at neutral — SEMIPERMEABLE). Near the cut a trait
  expresses partially/probabilistically, not on/off; differentiable if we ever learn the cut.
- **(c) Potentials** → **reuse the existing continuous temperament genes** (aggression, loyalty, expansion,
  patience, resilience, tunnel_preference, plasticity) as the potentials to start — already evolved, already
  warm-start the RL. Add a NEW latent potential only when an affordance needs a dimension temperament can't
  express. Keeps the genome from ballooning.
- **(d) Interaction map — concrete first cut** (2-term non-additive products of existing genes, quantized,
  soft-cut; epistasis visible — a trait needs BOTH terms; pleiotropy visible — `patience` feeds two):

  | affordance        | liability (interaction)   | reading                                   |
  |-------------------|---------------------------|-------------------------------------------|
  | **scorched earth**| `aggression · (1 − loyalty)` | cruel AND faithless → burns what it can't hold |
  | **builds granaries** | `patience · expansion`  | patient growth → stockpiles + builds      |
  | **keeps livestock** | `patience · resilience`  | a husbandry temperament                   |

**Proposed reference implementation (pending sign-off):** prototype ONE affordance — **scorched earth** —
end-to-end as the pattern's reference: liability `aggression·(1−loyalty)` → soft-cut → level fed to the maw-RL
→ the policy chooses to ignite an adjacent enemy grain store (reusing T45 fire). Small, testable, proves the
architecture before generalizing the map. **Not started.**

## First worked example (spec target once D1 lands): livestock, granaries & scorched earth

Framed as affordances, minimal fixed rules:
- **Livestock** — mice are "cattle" (low-danger → tameable, DM domestication); a `keeps_livestock` house tames
  and pastures them for a periodic food (dairy/stock-feed) yield. Squirrels are "fast mammoths" — above the
  taming ceiling, resist. (See [[world-alive-fauna-arc]] mouse-as-cattle note.)
- **Granaries / barns** — a `builds_granaries` house, when it is cold (precondition) and holds stored food /
  livestock, builds a granary/barn structure and brings livestock inside (shelter from the Chill; a
  concentrated, defensible food store). MECHANIC = the structure + shelter; DECISION = trait + policy.
- **Scorched earth** — a `scorches_earth` marauder adjacent to an enemy grain store / field (precondition) may
  IGNITE it (reuses the existing fire spread) to starve the rival out and take the land. MECHANIC = ignite +
  starve; DECISION = trait + policy, NOT "if at_war and adjacent then burn."

Each is one thin precondition + a directive channel — no new threshold ladder. Build order pends D1.

## Cross-references
- `maw_brain.py` (the directive/warm-start layer), `neuroevolution.py` (the GA), SPEC_DOMESTICATION (livestock),
  SPEC_TIMBER_AND_FLAME / T45 fire (scorched earth reuses fire spread), SPEC_WINTER (the cold that drives
  barns), SPEC_STORY_LOG (legible bit-flip evolution feeds the saga).
