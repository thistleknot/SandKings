# SPEC — NEAT on the PEFT adapter: evolved topology, RL-learned weights

Status: **INCREMENT 1 IMPLEMENTED** (2026-07-18) — the NEAT core (`sim/neat.py`), the masked-readout phenotype
(`neural_hive.HiveMindBrain.apply_neat_genome`), and the GA wiring (topology inherits + grows under the Breath
budget on mutation, crosses both bloodlines on sexual reproduction, sparse-seeds fresh colonies) are built, gated
`NEAT_ENABLED` baseline-on (with neural), byte-identical off; battery 78/0 (`tests/test_neat.py` 7,
`tests/test_neat_adapter.py` 2). **INCREMENT 2 pending:** `add_node` (real hidden-bottleneck topology, not just
connection selection), novelty/niching *selection* + speciation (NE4), and the diversity/complexity curve.
Extends EV1/EV4 (evolvable readout), SPEC_BREATH (the compute budget), the maw-RL (85:15 weight learning), and
docs/HARVEST_ALIFE.md. Design law: the frozen Kanerva SDM / GRU are never mutated — only the adapter.

## The thread (the keeper's design)

- **NEAT provides the substrate RL thrives on** — evolution searches network **structure**; the maw-RL learns the
  **weights** on that structure within a lifetime (Baldwinian split).
- **NEAT can exist in our PEFT layer that sits on top of the Kanerva substrate** — the frozen ZCA+Kanerva SDM is a
  pretrained backbone; the evolvable readout becomes a parameter-efficient adapter.
- **The PEFT layer is what we do RL on, and keeps computation tight** — NEAT evolves the adapter topology, maw-RL
  learns the adapter weights, and PEFT (small/sparse) keeps per-colony compute bounded by the Breath budget.

## Decisions (the four open questions, now settled)

1. **Where the graph sits.** A **masked bottleneck adapter**: proto sparse-code (M inputs) → a small hidden layer
   `h` → encoding (E outputs), with allowed direct skip connections proto→E. NEAT evolves which connections are
   live; `h` is the Breath-budgeted hidden width. `h == 0` with all skips on == today's dense readout.
2. **Weight handoff on topology change.** New connections/nodes warm-start at weight **0** (identity-preserving —
   a fresh connection contributes nothing until RL grows it); surviving connections keep their trained weight via
   innovation-aligned graft. No RL policy discontinuity.
3. **Innovation bookkeeping.** One monotonic **shared registry on the sim**: structurally-identical mutations
   (same src,dst) in different colonies receive the **same** innovation number, so live async lineages stay
   crossover-alignable without generations.
4. **torch representation.** A **binary connectivity MASK over Linear weights**, not a dynamic graph object — the
   mask is the NEAT phenotype. Reuses the existing Linear + `graft_into` + checkpoint machinery; an all-ones mask
   with `h==0` is byte-identical to the current dense readout, so gating is trivial.

**No new magic constants** (per project rule): the number of structural mutations per reseed is the SPEC_BREATH
`breathe()` delta on topology size (grows only as rivals shrink), and the speciation threshold is derived from the
population's compatibility distribution (harvest niching's max/mean normalize), not an authored cutoff.

## Expansion axis (expansive options considered, bounded on compute)

Leaning expansive, balanced against compute — the more ambitious variants and why each is in or deferred:
- **IN — real hidden-node topology** (not just skip-mask pruning): add-node grows a genuine bottleneck, so the
  adapter can learn nonlinear feature compositions, not only feature selection. Cheap under the Breath budget.
- **IN — shared innovation registry across the live async population** (not per-colony ids): the more expansive
  choice, it makes cross-lineage crossover truly alignable. Cost is one small dict on the sim — negligible.
- **DEFER — recurrent adapter connections** (canonical NEAT allows cycles): the frozen backbone's GRU already
  supplies temporal memory, so an additionally-recurrent adapter doubles training cost for redundant capacity.
  Revisit only if the diversity/complexity curve says feed-forward adapters have plateaued.
- **DEFER — NEAT on the SoldierLayer too** (not just the maw readout): expansive but multiplies the evolving
  surface by the soldier count — heavy. The maw directive is the highest-leverage single adapter per colony; prove
  it there first.
- **OUT — HyperNEAT / CPPN indirect encoding**: maximally expansive, but it *generates* weights from geometry,
  which collides with the RL-learns-weights split — the whole point of this spec. Not compatible, not deferred.

---

## Structural

### NEAT-PEFT adapter, for evolving the maw readout's topology while RL learns its weights

Constant: NEAT_ENABLED — master feature gate; off ⇒ the readout is the current dense `nn.Linear` path (battery
byte-identical). In `run_tests._GATE_NAMES`; entrypoint flips baseline-on.

class NodeGene [value]: an immutable adapter node — its id and role
    state: id — int, immutable
    state: kind — enum{input, hidden, output}, immutable

class ConnGene [value]: an immutable adapter connection; carries NO weight (RL owns weights)
    state: src — int node id, immutable
    state: dst — int node id, immutable
    state: innov — int innovation number, immutable
    state: enabled — bool, immutable (toggling produces a new gene)

class NeatGenome [entity]: one colony's adapter topology, mutated across reseeds
    state: nodes — dict[int, NodeGene], mutated by mutate_topology/crossover
    state: conns — list[ConnGene], mutated by mutate_topology/crossover
    size() -> int: count of enabled conns + hidden nodes (the Breath quantity); no failure mode (pure read)
    hidden_width() -> int: number of hidden NodeGenes; used to size the bottleneck

class NeatInnovationRegistry [service]: hands out innovation numbers, repeating for identical structure
    state: table — dict[(int,int), int], src/dst → innov, mutated by innovation()
    state: counter — int, monotonic, mutated by innovation()
    innovation(src: int, dst: int) -> int: return the shared number for (src,dst), minting one if new
        (Require: src != dst; Guarantee: identical (src,dst) always returns the same int)

class MaskedAdapter [entity]: the torch phenotype realizing a NeatGenome; replaces HiveMindBrain.readout when NEAT on
    state: w_in — Tensor(h, M), RL-trained; state: w_out — Tensor(E, h), RL-trained
    state: w_skip — Tensor(E, M), RL-trained direct proto→encoding
    state: in_mask, out_mask, skip_mask — Tensor bool, frozen for the colony's life (the genome phenotype)
    forward(sparse_code: Tensor) -> Tensor: masked bottleneck + skip; fails closed to skip-only if h==0
        (Maintain: masked-off weights never contribute to the output)

class NeatEvolver [service]: coordinates topology mutation, crossover, speciation, and reseed selection
    reseed_adapter(dead: ColonyGenome, living: list[ColonyGenome]) -> NeatGenome: build a child topology for a
        fallen house; fails closed to the parent topology if no valid mutation fits the budget

def crossover(a: NeatGenome, b: NeatGenome) -> NeatGenome: pure innovation-aligned inheritance — matching genes
    picked at random, disjoint/excess taken from the fitter parent; free function — builds a new genome, mutates
    neither parent; fails to an exact copy of the fitter parent when the two share no innovation numbers
def express(genome: NeatGenome, hidden_cap: int) -> (Tensor, Tensor, Tensor): pure genome→mask projection;
    free function because it mutates no genome state — it only reads the genome to emit boolean masks
def compatibility(a: NeatGenome, b: NeatGenome) -> float: pure structural distance = (excess+disjoint)/max_genes,
    for speciation; free function — no state, no weight term (weights aren't in genes)
def align(a: NeatGenome, b: NeatGenome) -> (list, list, list): pure innovation-number alignment
    (matching, disjoint, excess) for crossover; free function — no state

`ColonyGenome`, `HiveMindBrain`, `Tensor`, `PopulationBreath`, the maw-RL trainer, and the fitness/novelty selector
are external — referenced bare, never classified here.

---

## Behavioral — NeatEvolver.reseed_adapter (topology owns structure; RL owns weights)

Input: dead — the fallen colony whose nest is reseeded, ColonyGenome
Input: living — the surviving colonies, list[ColonyGenome]
Uses: fitness_novelty_select — living → two parent genomes, weights rawfitness × topological novelty (harvest #1)
Uses: registry.innovation — (src,dst) → int, the shared innovation registry
Uses: breathe — SPEC_BREATH kernel, current_size → budgeted new_size int
Uses: graft_weights — copy overlapping trained weights by innovation alignment (EV4 generalized), Tensor→Tensor
Initialize: parent_a, parent_b ← fitness_novelty_select(living)   # global to this reseed
Initialize: child ← crossover(parent_a, parent_b)                 # inherit matching genes, disjoint/excess from fitter
Initialize: target ← breathe(child.size(), population mean, sdev, size_lo, size_hi)   # Breath-governed size

Loop while child.size() < target:
    Initialize choice ← a random structural mutation kind          # transient, re-picked each pass
    When choice is add-connection:
        pick an unconnected (src, dst); innov ← registry.innovation(src, dst); append enabled ConnGene
    Otherwise When choice is add-node:
        split an enabled conn: disable it, add a hidden NodeGene, add two conns via registry.innovation
    (Maintain: child remains a valid feed-forward topology — no cycle, every hidden node on some in→out path)

Express child → masks; build MaskedAdapter sized to child.hidden_width()
graft_weights: surviving connections keep their trained weight; new connections warm-start ← 0
Assert: on normal completion, with NEAT_ENABLED off the built adapter reduces to the dense Linear (masks all-ones,
        h==0) and produces byte-identical output; the maw-RL then trains w_in/w_out/w_skip over the fixed masks.

Given NEAT_ENABLED off, When any colony brain runs, Then the readout output MUST equal the prior dense Linear.
Given two colonies each apply the same add-connection (src,dst), When each calls registry.innovation, Then both
  MUST receive the same innovation number.
Given a mutation adds a connection mid-lineage, When the adapter is expressed, Then the new connection's weight
  MUST be 0 (RL grows it; no policy jump).
Given the shared compute budget is saturated, When reseed_adapter runs, Then child.size() MUST NOT exceed the
  breathe()-derived target (topology grows only as rivals shrink or die).
Given a population converging on one topology, When fitness_novelty_select runs, Then a structurally-novel
  topology MUST receive a higher selection weight than a common one of equal rawfitness (speciation protects it).

## Gating

`NEAT_ENABLED` module default False → `_GATE_NAMES` → entrypoint baseline-on. Off ⇒ `HiveMindBrain.readout` stays
the dense `nn.Linear(KANERVA_PROTOS, encoding_dim)` (`neural_hive.py:185`); on ⇒ it is a `MaskedAdapter` whose masks
are the current colony's `NeatGenome` phenotype and whose weights the maw-RL trains.

## Provenance

NEAT (Stanley & Miikkulainen 2002 — the keeper's first white paper), the frozen-backbone + PEFT/LoRA adapter
pattern, and the Framsticks `evolalg` diversity toolkit (`framspy/evolalg`: novelty/niching/speciation). See
docs/HARVEST_ALIFE.md and the [[neat-peft-adapter-direction]] memory.

Local grounding (skills_master): evolving the topology is gradient-FREE optimization (`misc/gradient-free-algorithm`
— evolution searches structure without backprop); speciation/compatibility is a dissimilarity measure
(`misc/dissimilarity-measure`); the frozen Kanerva substrate the adapter sits on is a whitened prototype code
(`clustering-dimred/principal-component-analysis`, `.../singular-value-decomposition-svd`, `.../self-organizing-map`).
