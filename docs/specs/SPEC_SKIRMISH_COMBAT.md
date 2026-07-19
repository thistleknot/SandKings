# SPEC — Skirmish combat: learned antenna-frequency kin-recognition + pheromone-tracked engagement

Status: **I1 + I2 IMPLEMENTED** (2026-07-19), baseline-ON (gate `SKIRMISH_ANTENNA_ENABLED` default False → battery
byte-identical off; entrypoint flips on). I2b (heritable acuity + within-life combat-outcome calibration) and I3
(limited sight + pheromone-gradient approach) remain SPEC. **Replaces the
omniscient O(26·U²) proximity scan in `_resolve_conflicts` (`sim/sandkings.py:9786`) with a biomimetic,
LEARNED, LOCAL sensing model** built on the existing `PheromoneLayer` (`:1673`) and the units' neural weights.
Companion to SPEC_CHEMICAL_WAR (the chemical medium) and the pheromone/stigmergy substrate.

## THE LOAD-BEARING CONTRACT (the keeper's first principle, 2026-07-19)

> **Use ML to INCREASE efficiency through dynamic systems.** The learned sensing MUST profile CHEAPER than the
> brute-force scan it replaces — dynamic/learned systems are the SHORTCUT, not an add-on. If the new combat is not
> measurably less compute than today's `_resolve_conflicts`, it does NOT ship. This inverts the usual "ML costs
> more" assumption: a small per-unit *learned discrimination* replaces a global *all-pairs scan*.

This is the escalation of [[balance-objective-computational-efficiency]]: not just "better AND cheaper," but "the
learned/dynamic system is HOW we get cheaper."

## Why (the keeper's design)

Today every unit, every step, auto-detects any enemy in all 26 surrounding cells — *omniscient adjacency*, un-
insectlike, and O(26·U²). Real insects have **short sight + kin-recognition by chemical signature + pheromone
trail-following**, and none of it is a global scan. The vision: units *sense* friend vs foe through their **dynamic
neural weights**, not a hardcoded `hostile()` rule — an **antenna** that reads pheromone signatures as **banded
frequencies**, learns its nest's band, and flags an **out-of-band** frequency as an enemy. It is a DYNAMIC SYSTEM
WITH ROOM FOR ERROR that each unit must CALIBRATE TO LEARN — misidentification is a feature (attacking kin, missing
foes) that creates emergent drama and evolutionary pressure to sharpen the antenna.

## The model (cheaper AND more authentic)

- **Signature as frequency band — a "sixth sense" from the RL weights down through linear features.** Each colony
  emits a pheromone signature encoded as a band, and the band is a **fixed N of quantile-pegged discrete floats**
  (bins pinned at specific values — a discretized frequency comb, not a continuous scalar). Those N pegs ARE the
  unit's linear input features; the antenna reads the local pheromone field (already computed by the pheromone tick
  — no new global pass), snaps the sensed signature onto the pegs, and the **RL weights over those linear features**
  produce the discrimination — an emergent "spidey sense" flowing top-down from the learned weights through the
  binary/linear feature layer, not a hardcoded compare. The quantile pegging keeps it a small fixed-width feature
  vector (cheap) while giving the weights a sharp, learnable basis to separate in-band (kin) from out-of-band (foe).
- **RL-TUNED band + BOLTZMANN selection (the dynamic weights — the keeper's correction, 2026-07-19).** Ally/enemy is
  a LEARNED soft boundary, and CRITICALLY the band is **tuned by RL**, not a hand-set geometric constant, and the
  error is **not a uniform random miss (epsilon-greedy is explicitly rejected)**. The mechanism:
  - **The antenna is learned weights `w`** over the fixed N-peg frequency comb → a scalar logit `z` = foe-ness.
  - **Strike/hold is a Boltzmann policy:** `P(strike) = sigmoid(z / T)`, temperature `T` annealed hot→cold
    (explore→exploit). This is softmax-over-actions, NOT epsilon-greedy — the softness IS the room for error, and it
    sharpens as T cools.
  - **The band is tuned by REINFORCE from combat outcomes:** `w` starts at ZERO (no innate band); the reward is the
    engagement result (struck a true foe = +; struck kin = − friendly-fire cost; held vs a foe = − missed threat;
    held vs kin = + restraint), and `w += lr · reward · (a − P(strike))/T · x`. The discrimination EMERGES from
    feedback — "must calibrate to learn." Per-colony weights + temperature (heritable acuity/temperature = drift +
    selection). Reuses [[semipermeable-params-direction]] (identity-at-neutral, learnable), NOT authored thresholds
    ([[no-authored-threshold-constants]]).
  - **Update budget is NOT the maw's problem:** combat is frequent (many engagements/game), so unlike the
    update-starved within-life maw-RL ([[frozen-fm-router-feudal-brain]], ~4 updates/game → inert), the antenna gets
    the hundreds of updates it needs. Mouse-validated (`tools/mouse_antenna.py`): band self-organizes from zero to
    0.98 strike-correctness in a **median 278 updates**; crowded bands stay confusable (0.69) — room for error
    emerges from the tuning, not from a hand-injected coin flip.
- **Layered limited perception (pheromone-trail + frequency + line-of-sight).** A unit responds to environmental
  stimuli in three bands, cheapest-first:
  - **Frequency / pheromone signature (the long band, O(1)):** the primary sense — a unit READS its local pheromone
    field value (already computed by the pheromone tick) and snaps the sensed signature onto its frequency pegs. This
    is a per-unit O(1) field read (NOT a cell scan), and it reaches a little FARTHER than eyesight — it senses an
    enemy's presence/direction before it can see them. This is what makes the model cheaper than the old scan: the
    FIELD does the spatial aggregation, units just read it.
  - **Line of sight (the short band, ≤ ~6 steps):** WITHIN vision, the SAME detection formula as today, just a much
    smaller range (a unit cannot see more than ~6 steps out). Kept bounded and ideally frequency-triggered (only
    look when the pheromone sense flags something), so it is not an always-on radius-6 scan (which would be ~85× the
    cells — the opposite of the goal). Constant reuses the semi-permeable/soft-gate pattern, not an authored magic
    number.
  - **Engagement (melee):** combat resolves on adjacency/co-location (the current radius-1), via the position index.
  Net: combat EMERGES from movement + chemistry (units follow gradients toward foes and clash when close), and
  pheromones are first-class double-duty — communication AND enemy detection — with the field read replacing the scan.
- **Co-location resolution (the compute shortcut).** Combat resolves where hostile units actually share a cell — a
  **position-index group-by, O(U)** — instead of the 26-cell all-pairs scan. The position→unit index (already being
  added to `_resolve_conflicts` as the interim optimization) is the substrate; the learned antenna decides WHO is a
  foe at that cell, replacing the `hostile()` call.

## Compute placement (the keeper's GPU-cooperative rule, 2026-07-19)

The antenna is **CPU-light by design** — a tiny per-unit frequency-peg discriminator (a handful of params over a
fixed-N feature vector), never a GPU job. That is the whole point: ML that *reduces* cost runs where it's cheapest.
The keeper often uses the GPU for LLM work, so the standing rule for ANY heavy neural job in this repo:
- **If the GPU is uncontended:** submit as a LAZY / low-priority job (cooperative-yield, `ewma-eta-watchdog`'s
  idle-priority gating pattern).
- **If contended (job not picked up in an almost-immediate window):** move it to the CPU via the **`rust-wrapper`**
  skill (Rust call wrapped in Python) — a fast native fallback, so the sim never blocks on a busy GPU and never
  steals it from the LLMs.
- **If the GPU is CLOCK-THROTTLED (~300 MHz):** go straight to CPU — a throttled GPU runs this work ~**5× SLOWER
  than the CPU**, so the GPU path is a net loss regardless of contention. Gate on the observed core clock, not just
  the queue: throttled → Rust-CPU path unconditionally.
Antenna I2/I3 do not trip this (CPU-only), but the rule governs any future GPU-bound learner here.

## Compute budget (the gate)

Profiled per-step cost of the new combat MUST be `<` the current `_resolve_conflicts` at the same scale (7 colonies,
~145 units, where it is ~320 ms/step / 26% of the step). Verify the SAME way as the perf work: headless ms/step +
cProfile before/after, and mouse-test the discriminator's learning in isolation before touching the game
([[mouse-model-testing]]). If it isn't cheaper, iterate or don't ship.

## Room for error + calibration (the dynamic system)

The antenna is stochastic/soft: a false-negative lets a foe pass; a false-positive attacks an ally (real cost — lost
food, grievance, a broken truce). Those outcomes are the calibration signal (the unit/colony updates its band). Over
generations, well-calibrated antennae win → the discrimination sharpens by selection, and confused lineages
misfire — emergent kin-recognition error, exactly like real ant colonies mixing signatures.

## I2b — LETHAL friendly fire + self-culling of defectives (the keeper's point, 2026-07-19)

The room for error is not cosmetic — **the mis-fire must bite**, or there is no selective pressure and it isn't a
dynamic system. So:
- **Friendly fire is REAL and lethal.** The antenna is the strike decision at EVERY co-located pair — kin, ally, and
  foe alike, not just diplomacy-confirmed foes. A strike deals real damage regardless of diplomacy. A mis-tuned band
  that reads an ally or a sibling as out-of-band **actually strikes them** (lost units, spilled kin).
- **Innocent prior (so the defect is LEARNED, not initial noise).** The antenna is warm-started to HOLD (a negative
  strike bias): a naive unit does not strike until RL raises foe-band strike-probability. Friendly fire is therefore
  a symptom of a *mis-learned / mis-inherited* band — a genuine defect — not startup randomness that would just
  slaughter every young colony.
- **The stakes: a mis-fire on an ally risks a ruinous war.** Striking an allied house can turn the truce hostile —
  the single most expensive outcome in the game. That is what makes culling rational.
- **Self-culling (Spartan / insect — "a defective member").** A unit that commits friendly fire (strikes a non-foe)
  is culled by its own maw: removed and barred from mating, pruning the defective antenna lineage from the gene pool.
  The colony purges its own mis-firer to avoid the costly war — exactly how a hive ejects a mite-infested member or
  Sparta exposed the unfit. This is the colony's **own genetic culling**, an active mechanism, not merely fewer
  offspring. Rhymes with the existing madness-cull and Spartan-heir succession.
- **Selection loop.** Colonies that breed mis-firers bleed members and risk wars → lower fitness → the GA prunes the
  predisposition; heritable antenna priors (the genetic warm-start) sharpen by selection while confused lineages are
  culled — nature (inherited band prior) and nurture (within-life RL) both in play.
- **Stability is the load-bearing risk → mouse-gate it.** Self-culling could either converge (friendly-fire rate
  declines, population survives) or collapse (colonies cull themselves to extinction before the band tunes). MUST be
  mouse-tested as an evolutionary sim BEFORE game integration ([[mouse-model-testing]]): does mean friendly-fire rate
  fall across generations while population persists? Only integrate if it converges; otherwise rebalance
  (prior strength, cull severity, learning rate) first.

## Increments (staged; each mouse-gated + compute-gated)

- **I1:** position-index co-location resolution (the O(U) substrate) — the interim optimization already in flight;
  byte-identical, ships now.
- **I2:** RL-TUNED antenna replaces `hostile()`'s certainty at the co-located cell — per-colony learned weights over
  the frequency comb, BOLTZMANN strike policy `P(strike)=sigmoid(z/T)` (temperature-annealed, NOT epsilon-greedy),
  band tuned by REINFORCE from combat outcomes (w starts at zero → discrimination emerges). Gated, mouse-tested for
  "does the band self-organize from reward, cheaply, within the in-game combat update budget." (An interim fixed-band
  RBF version shipped first, then was replaced by this RL-tuned model per the keeper's correction.)
- **I2b:** LETHAL friendly fire + self-culling of defectives (above) — antenna decides at ALL co-located pairs
  (kin/ally/foe), a strike is real regardless of diplomacy, mis-firers are culled by their own maw (genetic pruning),
  heritable antenna prior warm-started from the genome. Mouse-gated on evolutionary STABILITY (converge, don't
  collapse) before integration.
- **I3:** limited sight + pheromone-gradient approach (combat emerges from movement, not adjacency scan) — the full
  skirmish model.

## Gating / Provenance

New gate (module default False → battery byte-identical; entrypoint baseline-on). Provenance: real ant nestmate
recognition via cuticular-hydrocarbon signatures; stigmergy (Grassé) — the pheromone medium as shared memory; the
keeper's antenna-frequency-band metaphor and the "ML increases efficiency through dynamic systems" directive.
Relates to [[balance-objective-computational-efficiency]], [[comprehension-drives-rl-cultural-evolution]],
[[semipermeable-params-direction]], [[mouse-model-testing]]. Medium: `PheromoneLayer` (`sim/sandkings.py:1673`).
