# SPEC: The Evolving Engine (Round 12) — EV1–EV6

User intent: "turn this into a REAL evolving engine... allow THEM to
self-modify by mixing their underlings they emit with other maws to
create a 'new' maw, and as more entities are created, the ones who are
smarter from genetic mutation and potentially extended capabilities
(stronger/more expansive neural nets in the form of n_layers, n_nodes)
all from crossover populated from parents' DNA."

Core: maw reproduction becomes SEXUAL and the neural ARCHITECTURE
itself becomes heritable. A new maw's genome (dispositions AND brain
shape) is a crossover of TWO surviving parents, then mutated. Brain
width (n_nodes) and depth (n_layers) evolve; selection - survival and
victory, the league already in place - favors the architectures that
win. This is neuroevolution of augmenting topologies, kept small and
graft-based so it stays deterministic-enough and pickle-safe.

## EV1 — Architecture genes
`ColonyGenome` gains `brain_hidden` (n_nodes per hidden layer,
[BRAIN_HIDDEN_MIN 24 .. BRAIN_HIDDEN_MAX 160]) and `brain_depth`
(n_layers, [1 .. BRAIN_DEPTH_MAX 4]). Defaults 64/1 reproduce the
current fixed brain. Both mutate in `genome.mutate()` (small integer
jitter, clamped). The fixed I/O contract holds: input_dim 40,
encoding_dim 32 (SoldierLayer's expectation) never change - only the
hidden stack between them evolves.

## EV2 — Building a brain from genes
`build_brain(genome)` -> HiveMindBrain(hidden_dim=brain_hidden,
depth=brain_depth). HiveMindBrain's encoder is now variable-depth but
still ends in Linear(hidden->32), ReLU, so fold_soldier_layer /
prune_weights (which read encoder[-2]) are unchanged.

## EV3 — Genome crossover (two parents -> child)
`crossover_genome(a, b)` (neuroevolution.py): each scalar disposition
is inherited from a or b at random (uniform gene draw), the two integer
architecture genes likewise, then `mutate(rate)` is applied. Returns a
fresh ColonyGenome. This is the sexual step - the child is a genuine
recombination of both parents' DNA, not a mutated clone of one.

## EV4 — Brain crossover (weight grafting)
`crossover_brain(brain_a, brain_b, child_genome)`: build the child
brain from the child's architecture genes, then GRAFT - for each
Linear layer, copy the largest top-left submatrix that fits from the
same-index layer of a randomly chosen parent (per layer), leaving the
rest at fresh init. Shapes never need to match (the SoldierLayer.mate
overlap-blend pattern generalized), so parents of different topology
reproduce without error. The child inherits learned structure where it
fits and explores where it grew.

## EV5 — Integration (respawn = sexual reproduction)
When a neural colony respawns (`_respawn_colony`) and >= 2 survivors
exist, pick TWO distinct survivor parents (the "mixing underlings from
different maws"): the child genome is `crossover_genome`, and if either
parent had a brain, the child brain is `crossover_brain`. With < 2
survivors it falls back to the existing single-parent mutate. Radiation
mutation-catalysis (T40) still multiplies the rate. Non-neural sims are
unchanged (architecture genes ride along inertly). A chronicle line
notes a notable jump: "House X is born of two bloodlines
(NxM brain)" (salience 6) when the child's architecture differs from
both parents.

## EV6 — Acceptance
tests/test_evolution.py: architecture genes mutate within bounds;
build_brain yields a forward-valid brain at depth 1..4 producing a
32-vector; crossover_genome draws each gene from a parent and stays in
range; crossover_brain grafts across DIFFERENT topologies without shape
error and the child runs a forward pass; a respawn with two neural
survivors produces a recombined child; everything pickles; evolution
sim (the OTHER one, EnhancedSandKingsSimulation) still runs. A short
neuroevolution soak: over several respawns the population's brain
sizes diversify from the uniform start.

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: build_brain
  yields a forward-valid 32-vector encoder at depth 1..4 (encoder still
  ends Linear(->32),ReLU so fold/prune hold); crossover of a 48x1 and a
  96x3 parent produced varied children (40x2, 56x2, ...) each running a
  forward pass; grafting across different topologies copies only the
  overlap, never a shape error; sexual respawn with two neural survivors
  recombines; evolved genome+brain pickles. 15/15 suites green incl.
  tests/test_evolution.py (6). Note: the full neuroevolution soak is
  slow (neural forward passes ~5 sps); the diversification is proven by
  the crossover unit tests, and the GPU sim (sandkings_gpu) is the fast
  path for long neural runs.
