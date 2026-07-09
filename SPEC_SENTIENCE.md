# SPEC: The Sentience Arc (Round 6) — S1–S6

Governing intent (user): "[quasi] sentient life operating inside my
computer within the terrarium." Rounds 1–5 built the world and its
history; this round works on the MINDS. The three research items parked
since the liveness rounds — unit communication, speciation, and
meta-learning — become mechanics, each with a measurable claim.

Design law (chess-deep-q findings, carried forward): small, inspectable
learned components riding on the existing substrate. No architecture
changes to pickled networks — every mechanic below composes with the
GRU/brain shapes already in checkpoints.

## S1 — Resonance: thought contagion (communication)
Soldiers of the same colony within RESONANCE_RANGE blend GRU hidden
states each resonance tick: h_i <- (1-a)h_i + a*mean(h_neighbors),
a = RESONANCE_ALPHA. The hidden state IS the soldier's decoded mind
(N1–N10, concept probes), so blending it is literal thought
transmission: a soldier that has seen the enemy raises its neighbors'
p(danger) BEFORE they have line of sight.
- Allied colonies cross-resonate at a * ALLY_RESONANCE_FACTOR — culture
  crosses alliances — but ONLY while their genomes remain conspecific
  (S2 gate). Hostile/neutral colonies never resonate.
- MEASURABLE CLAIM (test): plant a distinctive hidden vector in one
  soldier; after k resonance ticks its squadmates' hidden states move
  measurably toward it; a hostile colony's soldiers do not.
- Constants: RESONANCE_RANGE 6 (Chebyshev), RESONANCE_ALPHA 0.15,
  RESONANCE_TICK 2, ALLY_RESONANCE_FACTOR 0.3.

## S2 — Speciation: the lines grow strange
genome_distance(a, b) = mean |trait difference| over the 8 scalar
traits. Above SPECIATION_DIST 0.35, two colonies are no longer
conspecific: combat mating (the 5% neural crossover) produces NO
offspring, and cross-colony resonance is blocked even for allies.
First crossing per house pair logs "House X and House Y have grown too
strange to mingle" (salience 8 — speciation is history).
- MEASURABLE CLAIM: lineage divergence is observable in soaks via the
  event; kin houses (same house) are by construction conspecific.

## S3 — Plasticity: learning to learn (meta-learning)
New evolvable `ColonyGenome.plasticity` in [0,1] (mutates, inherits by
lineage like patience/loyalty). It scales the colony learner:
learn rate = LEARN_RATE * (0.5 + plasticity); exploration floor =
EPSILON_FLOOR * (1.5 - plasticity). High-plasticity minds learn fast
and keep exploring; low-plasticity minds are set in their ways.
Selection now acts on HOW FAST minds adapt, not just what bodies do —
the Baldwin-effect experiment made explicit.

## S4 — Dreams: Chill-season consolidation
The learner keeps a replay memory (last 40 transitions). During Chill
— the quiet season — each decision tick also replays DREAM_REPLAYS
random remembered transitions (offline TD updates: experience replay,
Lin 1992/DQN lineage). Once per year the chronicle notes "The maws
dream through the long frost" (salience 3). Dreaming colonies enter
spring with consolidated Q-tables at zero food cost.

## S5 — Surfacing (viewer surface R31, see SPEC_LIVE_VIEW ledger)
- Manager (neural colonies): "resonance: 0.NN across K soldiers" —
  mean pairwise cosine similarity of live hidden states; the number
  literally reports how much the hive is of one mind.
- EVENT_TINTS: "too strange" (violet), "dream" (pale blue).
- SALIENCE: speciation 8, dreams 3.

## S6 — Acceptance
- tests/test_sentience.py: resonance moves squadmate hidden states
  (and not hostile ones); speciation gates mating + fires the event
  once; plasticity mutates within [0,1] and scales the learner's
  update; dreams replay only in Chill and only with memory; all new
  state pickles; EnhancedSandKingsSimulation remains inert.
- Soak: 3 years with --use-neural genomes forced: no crash, sps >= 4
  (full-neural baselines ~5.5 sps; forward passes are the budget, see
  reconciliation), resonance measurably > 0.2 in at least one sample,
  a winter dream logged, no liveness regression.

## Compatibility
ColonyLearner gains fields lazily (getattr) so pickled learners
resume; genome.plasticity defaults to 0.5 via dataclass field for old
checkpoints (dataclass default applies only to new instances — old
pickled genomes hit the getattr guard at the call site). SoldierLayer
is untouched: resonance mutates `hidden` (runtime state, never a
Parameter), so folding/mating/probes all compose unchanged.

## Status / Reconciliation
- Drafted + implemented 2026-07-08 (same session as Rounds 4–5).
- Implementation deltas, all deliberate:
  - S1 resonance is fully vectorized: one row-normalized weight matrix
    (kin 1.0 / conspecific-ally 0.3 / else 0, Chebyshev-masked, zero
    diagonal) and a single (1-a)H + a(W @ H) blend - no order bias by
    construction. The first per-pair implementation cost ~20% of
    neural throughput; the matrix form costs ~7%.
  - S6 soak throughput floor corrected from the drafted 12 sps to
    4 sps: full-neural mode (4 colonies, per-soldier forward passes)
    baselines at ~5.5 sps with resonance disabled - the floor was
    mis-specced against rule-based throughput. GPU offload remains
    the sanctioned path for faster neural runs (sandkings_gpu).
  - Dream cadence rides the existing 25-step learner tick during
    Chill rather than a separate phase; one chronicle event per year.
  - Speciation observability: soaks may legitimately log zero
    speciations when lineages stay within SPECIATION_DIST (respawn
    inherits a mutated survivor genome, which keeps distances small
    for many generations) - the unit test proves the gate; the event
    is the long-run observable, not a per-soak guarantee.
- S6 soak: PASSED - 3 harsh neural years, 5.1 sps, 167 resonance
  samples (peaks > 0.2), 3 winter dreams chronicled, plasticity spread
  0.27-0.82 across lineages, no crash, liveness held. All 10 suites
  green including tests/test_sentience.py (8 tests).
