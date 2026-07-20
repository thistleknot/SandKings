# Sand Kings — Goals (Eisenhower roadmap)

Derived from the 2026-07-20 future-directions review (specs bounced off the code, RL directions
grounded in the data-science corpus). Importance = advances the learning/measurement north star or
protects the spec-integrity contract. Urgency = actively misleading or blocking today.

The DO-NOW (spec-rot reconciliation) and DELEGATE (index guard, README alignment) quadrants are
DONE and pushed. What remains is the SCHEDULE quadrant (items 3–5) and the SOMEDAY quadrant (8–11).

---

## SCHEDULE — Important, not urgent (the frontier bets)

### 3. LONGEVITY_FITNESS — the online survival/fitness core (L1 → L2 → L3)
- **Goal:** make survival the measurable objective, so every feature is falsifiable against it. Online
  eligibility-trace credit assignment (TD(λ)) + a two-tier objective (common spawns = within-life
  survival count; maw-propagators = a per-lineage decaying cumulative of log-lifespans), recast as
  online actor-critic (spawn=actor per-subspecies, maw=critic). Spec: `SPEC_LONGEVITY_FITNESS`.
- **Status:** `SPEC_LONGEVITY_FITNESS` = DESIGNED-NOT-BUILT (no gate, no code). **L1 measurement is
  now DONE** (see item 5 — it is the L1 rung). L2/L3 are the actual fitness rewrite, unbuilt.
- **Corpus grounding (verified):** AC(λ) trace + advantage update + Boltzmann policy + discounted
  return all confirmed correct. Two live guards folded into the spec:
  - **Baseline must be the critic's V(s), not a scalar reward-mean** (measured: a scalar mean
    mis-centers the antenna's asymmetric rewards → tripled friendly fire; reverted).
  - **Two-timescale: a slow critic is safe ONLY if pre-evolved-accurate**, else it must track the
    actor — the population is multi-agent/nonstationary, so a from-zero slow critic goes stale.
    Ship L2/L3 with a critic-TD-error staleness monitor. (`Nonstationary Environment Problem`, A3C.)
- **Next action:** build **L2** — a per-spawn online survival eligibility trace over `steps_alive`,
  with DERIVED γ/λ (no authored constants). Mouse-first, gated, byte-identical off.
- **Acceptance (L2):** a mouse shows the trace credits the genes/features that kept a unit alive
  (credit concentrates on survival-correlated features vs a shuffled control), ≥3 varied conditions.

### 4. Hive-attention refactor (the high-risk sibling)
- **Goal:** the attention-mediated hive-mind redesign — multi-head attention / relational model as the
  maw→swarm mediator, eusocial reproduction inversion, only two heavy models to track. Spec:
  `SPEC_HIVE_ATTENTION` (in the `hive-mind-attention` worktree).
- **Status:** DESIGNED, unbuilt. High collapse risk (acknowledged). Worktree exists, unpushed.
- **Next action:** do NOT integrate yet. Build an **H1 mouse** first — an isolated attention-mediator
  that must beat the current pheromone-blend baseline on a toy coordination task before any game wiring.
- **Acceptance (H1):** the attention mediator matches or beats the deterministic MAW→MANAGER→SWARM
  pheromone pipeline on a controlled coordination metric, in isolation, ≤10 min. If it can't, the
  refactor stays parked.

### 5. Antenna survival-lift hardening  (= LONGEVITY_FITNESS L1)  — DONE
- **Goal:** prove the antenna earns its compute — does a calibrated band actually EXTEND survival vs a
  defective band, and how far below the omniscient (pre-antenna) ceiling? Multi-seed, not one run.
- **Status:** **DONE.** `tools/mouse_antenna_lift.py` — isolates the real `_antenna_*` logic (no game),
  measures a scale-invariant quantity (mean **encounters-to-death**, after a non-lethal calibrate-then-
  deploy warm-up), across 3 conditions (2 spread-foe seeds + 1 crowded-foe stress).
- **Measured result (honest):**
  - Spread foes: calibrated survives ~0.23–0.27 of the horizon vs defective ~0.01 → **lift +0.22/+0.26**.
  - Crowded (near-band) foes: calibrated ≈ defective ≈ 0.04 → **lift +0.01** — the antenna cannot
    separate band-adjacent foes (the documented room-for-error; refined genetically across generations
    by culling, not within-life).
  - Mean lift **+0.16** (>0 in all 3) → **L1 PASSES**: calibration adds real survival value when bands
    are separable. Realism cost vs omniscient is large (~0.82) because 24 lethal draws compound even
    small near-band error — expected, not a defect.
- **Lesson captured:** `fraction-alive-after-N` SATURATES to ~0 for any realistic accuracy over a long
  lethal horizon; **encounters-to-death** is the non-saturating survival metric. Calibration-phase
  exploration must be non-lethal or it swamps the settled-discrimination signal (calibrate-then-deploy).
- **Next action:** none for L1. Feeds L2 (item 3) as the first survival-instrumented feature.

---

## SOMEDAY — Not important, not urgent (content increments; real, low-leverage)

These are genuinely unbuilt named next-increments. They are deferred, not dropped: each is a
one-increment extension of an already-shipped, baseline-on system, so none is on the critical path
to the learning/measurement north star. Promote any of them if a concrete need surfaces.

### 8. NEAT Increment 2 — `add_node` + speciation
- **Goal:** grow NEAT from connectivity-mask evolution (Inc 1, shipped) to structural growth:
  `add_node` (hidden bottleneck), novelty/speciation selection, a diversity curve. Spec: `SPEC_NEAT`.
- **Status:** Inc 1 shipped baseline-on (`sim/neat.py`); Inc 2 = comment stubs only, no `add_node`.
- **Next action (when promoted):** mouse an `add_node` mutation + speciation on the readout adapter;
  show topological diversity rises without collapsing fitness, before any game wiring.

### 9. FOL Tongue Increment 2 — quantifiers + action-triplet cross-train
- **Goal:** extend the FOL Tongue (Inc 1 triplets, shipped) with logic quantifiers/connectives
  (∀ / ∃ / ∧ / ∨) and colony action-triplet cross-training. Spec: `SPEC_FOL_TONGUE`.
- **Status:** Inc 1 shipped baseline-on (`sim/fol_tongue.py`); Inc 2 = no quantifier code.
- **Next action (when promoted):** spec the quantifier slot encoding first (it is a representation
  change, not a tuning knob); mouse the masked-slot prediction over quantified triplets.

### 10. FLOOD_REFUGEE (FR1–FR4)
- **Goal:** water's double edge — irrigated-crop heat immunity (FR1), the flood-refugee surface-forage
  state (FR2), overthrow of the devastated (FR3), and ICE turning a moat into a winter-assault bridge
  (FR4). Spec: `SPEC_FLOOD_REFUGEE` (DRAFT).
- **Status:** DRAFT, zero code. Correctly unbuilt.
- **Next action (when promoted):** it is a content/mechanics arc, not a learning feature — build
  spec-first (FR1→FR4), each gated + byte-identical off. Lowest learning-leverage of the set.

### 11. MITE_STORM Increment 2 — herbal cure / quarantine
- **Goal:** extend the mite storm (Inc 1 infest/cull, shipped) with an herbal-knowledge cure and an
  active quarantine mechanic. Spec: `SPEC_MITE_STORM`.
- **Status:** Inc 1 shipped baseline-on (`MITE_STORM_ENABLED`, `sandkings.py:10492`); Inc 2 unbuilt.
- **Next action (when promoted):** ties to the tech/knowledge tree (herbal cure as earned tech); spec
  the cure→quarantine interaction, then a small in-isolation contagion-containment check.

---

## Sequencing

Cleared: DO-NOW + DELEGATE. Done: item 5 (L1). **Live front: item 3 (build L2).** Item 4 stays parked
behind its H1 mouse. Items 8–11 promote on demand only. No SOMEDAY item precedes L2/L3 — the fitness
core is the leverage point that makes everything else measurable.
