# SPEC — Online longevity fitness (eligibility traces) + two-tier survival objective + feature-lift measurement

Status: SPEC (design-before-build). Gated → battery byte-identical off when built. Formalizes the keeper's direction
(2026-07-19): measure whether features add value in terms of a spawn's SURVIVAL, track the longevity RL objective
ONLINE (no future-state prediction), and split the objective by whether a unit can propagate its genes.

## The load-bearing question (and its grounded answer)

**"Can we measure fitness / gene-propagation online, without predicting future states (MCTS/minimax need rollouts)?"**
Yes — **eligibility traces (TD(λ))** are exactly the online, model-free credit-assignment mechanism for a DELAYED
outcome. [empirical:cited — Sutton & Barto, `~/Documents/wiki/data science/` RL book] The trace
`e_t = γλ·e_{t-1} + x_t` (x_t = the features/genes active this step) decays credit backward over recent activity; when
the terminal signal arrives (death, or reproduction) a single update credits everything the trace still holds. No
lookahead, no future simulation — the online surrogate for MCTS-style credit assignment.

## Two-tier objective (the keeper's split) — TWO axes of decay

There are two DIFFERENT decays, on two different time axes — do not conflate them:

- **Common spawns → raw within-life survival count.** Fitness = `steps_alive` (undiscounted longevity of ONE life).
  The honest objective for a unit that will never propagate: live longer. Already tracked (`brain_layer.steps_alive`).
  Within-life credit assignment to the genes/features that kept it alive uses the eligibility trace (TD(λ), above).

- **Maw-propagators → a per-lineage DECAYING AGGREGATE OF LIFESPANS (across generations).** The keeper's refinement
  (2026-07-19): the decay is ACROSS successive lives, not within one. Each time a lineage member dies, fold its
  lifespan into a running lineage score carried on the maw/genome:
  ```
  V_lineage  <-  gamma * V_lineage  +  log(1 + lifespan)
  ```
  - **Discounted CUMULATIVE (not an average):** it SUMS across generations, so a persistent lineage scores HIGHER than
    any single lifespan (what the keeper wants) — an EMA/average could not exceed its max term.
  - **gamma < 1 discounts OLDER lifespans**, so recent generations matter more and the sum stays bounded
    (`<= log(1+L_max)/(1-gamma)`) — controls the exploding-gradient the keeper flagged.
  - **log-compression** of each lifespan further bounds any single runaway life's contribution.
  This is the "who's cumulative/EMA over lifespans is highest" measure — online (O(1) per death), cross-generational,
  no future-state prediction. It complements the existing neural-fold-of-top-performers path (which folds the best
  within-life brains up into the maw).

## What each mechanism reaches (the two axes, named)

- **Eligibility trace (within one life):** credits the genes/features that kept THIS unit alive — fast, online, cheap.
- **Per-lineage decaying aggregate (across lives):** the keeper's insight — the multi-generational "do they spread
  genes" signal IS reachable online, via a recursive decaying cumulative of lifespans carried on the lineage. Not a
  TD trace, but the same recursive/decaying/online spirit, one axis up. So the earlier "traces can't reach across
  generations" is TRUE of within-life traces but NOT of the lineage aggregate — the lineage score is the online
  cross-generational measure, and the GA's selection still rides on top of it.

## The baseline MUST be state-value V(s), not a scalar reward-mean (corpus-grounded, MEASURED 2026-07-19)

The RAG corpus (data-science-skills: actor-critic-method / gradient-bandit / reward-baseline) confirms a policy-gradient
update needs a **baseline** for variance reduction. This design's baseline is exactly the **critic's V(s)** — the
advantage `δ = r + γV(s') − V(s)` centers each update on the state's own value. That is the RIGHT baseline.
- **A scalar running-mean baseline is WRONG here** — proven by measurement: bolting an EWMA reward-mean onto the
  antenna's REINFORCE tripled friendly fire in-game (0.37→1.22/step) because the antenna's rewards are ASYMMETRIC
  (correct kin-restraint pays only +0.5, which sits below the running mean → restraint becomes negatively reinforced →
  more mis-fires). Reverted. The lesson: a per-STATE value baseline (the critic) subtracts the right reference for each
  situation; a single scalar mean mis-centers asymmetric per-action rewards. So the baseline lives in the critic, not
  as a scalar on any actor.

## Feature-lift measurement (does a feature ADD VALUE?)

Because survival is the online reward, every feature becomes falsifiable against it: **A/B the feature's gate and
compare survival curves** — does feature-ON (or calibrated-vs-defective) raise mean `steps_alive` / propagation rate?
- First target: the ANTENNA ([[skirmish-antenna-shipped]]). Claim to test: a well-calibrated antenna EXTENDS survival
  (fewer self/kin losses to friendly fire, better foe-detection) → measurable lift on `steps_alive`. Mouse first
  ([[mouse-model-testing]]): antenna-on vs antenna-off survival, and calibrated vs defective-band survival.
- This is the general contract going forward: a feature that cannot show survival lift is not earning its compute
  ([[balance-objective-computational-efficiency]], [[ml-increases-efficiency-dynamic-systems]]).

## Architecture: ACTOR-CRITIC, reuse not rebuild (keeper direction, 2026-07-19)

Do NOT build a new net. Recast the existing PEFT-style stack as online actor-critic with eligibility traces — the
keeper's insight that the trace idea and actor-critic are the SAME algorithm (AC(λ)).

- **Spawn = ACTOR.** The existing per-unit PEFT readout adapter (SoldierLayer over the frozen Kanerva/ZCA linear+binary
  features) becomes the policy π(a|s). **Shared PER SUBSPECIES** (soldier/worker/scout, or genetic sub-species), NOT
  per-unit: this (a) pools every member's steps into ONE net → hundreds of updates/step, escaping the H2 update-
  starvation that made per-unit maw-RL inert ([[frozen-fm-router-feudal-brain]]); (b) collapses 135 tiny per-unit
  forwards into ONE batched forward (solves the neural-forward batching cost); (c) "1 degree of dynamic RL locally,
  dispersed" — cheap.
- **Maw = CRITIC.** The maw brain estimates V(state) = expected longevity return. **Two-timescale:** the critic evolves
  SLOWLY (GA across generations — the frozen-within-life warm-start that already exists), the actor adapts FAST
  (within-life, local). Heavy value-learning is genetic; the cheap local update is the actor. This is the split H2
  demanded (within-life RL is only viable when cheap + aggregated).
  - **GUARD — a slow critic must be ACCURATE, not slow-LEARNING (corpus-grounded 2026-07-20).** The DS corpus
    (`actor-critic-method`, `two-timescale`, `Nonstationary Environment Problem`) is explicit: standard two-timescale
    actor-critic (Konda–Tsitsiklis) puts the **critic on the FASTER timescale**, because "a critic that learns much
    slower than the actor yields a stale, misleading baseline." That directly tensions the "critic evolves SLOWLY"
    framing above. Resolution: the maw-critic may be slow ONLY because it is a **pre-evolved, already-accurate** value
    function (the GA warm-start is a converged V, not a from-zero learner). If instead the critic must LEARN within a
    life, it MUST track at least as fast as the actor. **The population is multi-agent and therefore NONSTATIONARY**
    (`Nonstationary Environment Problem`: other colonies co-adapt, so V(s) drifts) — a from-zero slow critic is stale
    exactly when it matters most. **Ship L2/L3 with a critic-TD-error staleness monitor**; if `mean|δ|` trends up
    (not down) the baseline is stale and the critic rate must rise. This is the measured Finding-2 lesson, now named.
- **Shared-per-subspecies actor = A3C-style asynchronous shared updates (corpus, `Asynchronous Parameter Updates`).**
  Pooling every subspecies member's within-life steps into ONE shared actor that each unit updates asynchronously is
  the A3C pattern: many cheap workers → one shared policy → hundreds of updates/step, escaping the H2 update-starvation.
  The corpus treatment is the reference for the update/synchronization contract to follow during decomposition.
- **AC(λ) is the mechanism.** The critic's TD error `δ = r + γV(s') − V(s)` IS the advantage that trains the actor;
  both carry eligibility traces. The within-life longevity credit (above) and actor-critic are one algorithm, not two.
  The per-lineage decaying-cumulative-log-lifespan is the critic's CROSS-generational target / the maw's fitness.
- **Drop the fixed 85/15 blend.** It is a magic constant ([[no-authored-threshold-constants]]) AND unnecessary under
  actor-critic: the maw influences the actor via VALUE (the advantage signal), not a hardcoded 0.85 action mix.
  TRADE-OFF to own: top-down hive COORDINATION must then re-emerge from the shared critic + shared per-subspecies
  policy rather than an explicit queen-command blend. Accepted bet; verify coordination survives in the mouse/game.

## Design constraints

- **No authored constants** ([[no-authored-threshold-constants]]): the within-life λ (trace decay), the within-life γ,
  AND the cross-generational lineage γ must all be DERIVED, not hand-tuned. Candidates: the lineage γ from a real
  horizon such as the expected reproduction interval or a genome trait (e.g. `patience`); log-base from a structural
  quantity. Resolve during decomposition; never ship a magic 0.9. The `log(1+·)` compression is a shape, not a tuned
  number.
- **Gated + byte-identical off**; baseline-on at the entrypoint ([[features-are-baseline-not-flags]]).
- **Cheap/online**: one trace vector per unit, O(features) update per step — no rollouts, no replay buffer.

## Increments (each mouse-gated)

> **BUILD NEXT: L1.** Per the 2026-07-20 future-directions review, L1 is the immediate next build — it is pure
> measurement (no game change, no gate, byte-identical by construction), it is the cheapest rung, and it makes every
> later feature falsifiable against survival before any fitness rewrite is attempted. L2/L3 are scheduled behind it and
> must carry the two-timescale staleness guard above. This spec stays DESIGNED-NOT-BUILT until L1 lands.

- **L1 (BUILD NEXT):** the feature-lift **mouse** — measure antenna survival lift (on/off, calibrated/defective) in an
  ISOLATED accelerated harness, not the full game. Answers "does it add value" before any fitness rewrite.
  - **Mouse-first, per [[mouse-model-testing]].** The full game is NEVER the test loop. L1 is a standalone harness
    (sibling of `tools/mouse_antenna.py` / `tools/mouse_antenna_cull.py`) that instantiates ONLY the real antenna
    component (the same `_antenna_*` encode/prior/decide logic) and runs units through a controlled mix of true-foe and
    kin/ally lethal encounters. It does NOT construct `SandKingsSimulation`.
  - **Measure a scale-INVARIANT survival quantity**, so the result translates to macro without depending on game
    cadence: the **fraction of units still alive after a fixed number of lethal encounters**, and/or
    **encounters-to-death**, for antenna-ON vs OFF and calibrated vs defective band. NOT full-game `steps_alive`.
  - **Acceptance:** the mouse reports the lift's sign + magnitude across ≥3 varied conditions (seed / band-crowding /
    foe-mix — a permutation battery, not one case), question→curve in ≤10 min. Prior single-seed full-game reading was
    +45%; L1 replaces that with a cadence-independent mouse verdict. Zero `sandkings.py` change; byte-identical.
  - **The existing `tools/lift_antenna_survival.py` (full-game A/B) is DEMOTED to a later, single confirmatory check**
    — the final in-game validation AFTER the mouse verdict, never the debugging loop ([[mouse-model-testing]]).
- **L2:** per-spawn online survival trace (eligibility trace over `steps_alive`), replacing/augmenting the raw fitness
  score with a trace-credited longevity signal; derived γ/λ.
- **L3:** the two-tier split — the per-lineage decaying cumulative of log-lifespans `V ← γ·V + log(1+lifespan)` carried
  on the maw/genome for propagators, raw within-life count for common spawns; wire into selection/fold; derived γ.

## Provenance

Keeper's direction 2026-07-19: "measure features in terms of lift ... spawn's survival rate ... how long do they
actually survive, and do they spread their genes ... can we do this online ... eligibility traces that track the RL
objective of longevity ... only some propagate their genes ... maws have an additional (decaying) survival function."
Grounds in TD(λ)/eligibility traces (Sutton & Barto). Relates to [[frozen-fm-router-feudal-brain]] (survival is the maw
objective; within-life RL is update-starved — traces are the cheap online signal that fits that budget),
[[comprehension-drives-rl-cultural-evolution]], [[skirmish-antenna-shipped]].
