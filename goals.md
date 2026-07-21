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

## SOMEDAY → DONE (2026-07-20: completed on request "complete 8-11")

All four deferred increments were built — gated, byte-identical off, baseline-on, validated. Each was a
one-increment extension of an already-shipped system; constants DERIVED (no authored magic numbers).

### 8. NEAT Increment 2 — `add_node` + speciation  ✅ DONE
- **Delivered:** `add_node` (split a conn into a real hidden node, stable per-split hidden ids), `speciate()`
  (DERIVED median compatibility threshold), wired into `mutate_topology` at a DERIVED rate `1/(1+size)`;
  phenotype composes hidden nodes into the readout mask by reachability (byte-identical with no hidden nodes).
  Validated `tests/test_neat.py` (11 total) + `tools/mouse_neat_speciation.py`. **Tails now wired:** weighted
  bottleneck (evolvable per-hidden `node_gain`, composed as a real-valued mask) + speciation-protected selection
  (fitness-sharing in `_select_parent`). Increment 2 complete.

### 9. FOL Tongue Increment 2 — quantifiers + action-triplet cross-train  ✅ DONE
- **Delivered:** per-triplet packed `quant` code — subject ∀/∃ + predicate ¬ (∧ already via Inc-1 clause-split);
  back-compatible store (`quants` array; legacy npz loads as QUANT_NONE → byte-identical); `format_triplet` renders
  `∀x:`/`∃x:`/`¬`; `action_triplet()` wraps a colony's own act as an observed triplet for cross-training. Validated
  `tests/test_fol_tongue.py` (12 total). **Tail now wired:** `observe_action` cross-trains a colony's own act
  (self-war-enemy) each turn from `_tongue_observe`. Increment 2 complete.

### 10. FLOOD_REFUGEE (FR1–FR4)  ✅ DONE
- **Delivered:** FR1 irrigated crops immune to heat wilt; FR2 the `refugee_until`/`is_refugee` state (maw
  inundated → refugee, enters no new war footing); FR3 refugees weighted up as war targets; FR4 the `frozen`
  surface-ice overlay + walkable-crossing bypass (moat → road in the freeze, adrift on thaw). Constants DERIVED
  (`REFUGEE_DURATION = RESPAWN_DELAY//2`, `REFUGEE_TARGET_MULT = 2.0` from the binary can't-retaliate state).
  Validated `tests/test_flood_refugee.py` (FR1-FR4 + gate-off). **Tail now wired:** FR2 surface-forage — a refugee
  cannot descend below the surface (`_step_toward` rejects descent while `is_refugee`). FR1-FR4 complete.

### 11. MITE_STORM Increment 2 — herbal cure / quarantine  ✅ DONE
- **Delivered:** gate `MITE_HERBAL_ENABLED`. HERBAL CURE — an infested host adjacent to crops is cured at a DERIVED
  rate = local crop density; QUARANTINE — the colony isolates a host with prob = its DERIVED healthy fraction, and a
  quarantined host cannot spread the contagion (an overwhelmed house fails to contain). Validated
  `tests/test_mite_inc2.py`. Commit `feat(MITE_STORM Inc2 / goal 11)`.

---

## Sequencing

Cleared: DO-NOW + DELEGATE. Done: item 5 (L1). **Live front: item 3 (build L2).** Item 4 stays parked
behind its H1 mouse. Items 8–11 promote on demand only. No SOMEDAY item precedes L2/L3 — the fitness
core is the leverage point that makes everything else measurable.
