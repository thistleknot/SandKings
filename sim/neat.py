"""SPEC_NEAT — the NEAT core: evolve the TOPOLOGY of the maw's PEFT readout adapter while the maw-RL learns its
weights. Pure stdlib (no torch) so it unit-tests anywhere.

Increment 1 (this module): a CONNECTIVITY genome over the readout — input nodes = the M Kanerva prototypes, output
nodes = the E encoding units, connection genes = enabled (proto -> encoding) links carrying innovation numbers. The
phenotype is a boolean (E, M) MASK over the existing dense readout (built in neural_hive.MaskedReadout). NEAT evolves
which links are live; the maw-RL learns the weights on the live links. HIDDEN nodes (add_node -> a real bottleneck)
and novelty/speciation selection are Increment 2 (SPEC_NEAT NE1 add-node, NE4) — the genome API is shaped to admit
them without a rewrite.

Gated: NEAT_ENABLED default False => ColonyGenome carries no topology and the readout stays the dense nn.Linear
(battery byte-identical). The entrypoint flips it baseline-on.
"""
import random as _r
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

NEAT_ENABLED = False          # gate; entrypoint flips baseline-on (in run_tests._GATE_NAMES). Off => dense readout.

INPUT, HIDDEN, OUTPUT = 'input', 'hidden', 'output'


@dataclass(frozen=True)
class NodeGene:
    """SPEC_NEAT Structural: an immutable adapter node — its id and role (value object)."""
    id: int
    kind: str                 # INPUT | HIDDEN | OUTPUT


@dataclass(frozen=True)
class ConnGene:
    """SPEC_NEAT Structural: an immutable adapter connection; carries NO weight (RL owns weights). Toggling
    enabled produces a NEW gene (frozen)."""
    src: int
    dst: int
    innov: int
    enabled: bool = True


class NeatInnovationRegistry:
    """SPEC_NEAT Structural [service]: hands out innovation numbers, repeating the SAME number for a structurally
    identical (src, dst) so lineages across the live async population stay crossover-alignable without generations.
    Require: src != dst. Guarantee: identical (src, dst) always returns the same int."""

    def __init__(self) -> None:
        self._table: Dict[Tuple[int, int], int] = {}
        self._counter: int = 0

    def innovation(self, src: int, dst: int) -> int:
        if src == dst:
            raise ValueError("connection cannot be a self-loop (src == dst)")
        key = (src, dst)
        got = self._table.get(key)
        if got is None:
            got = self._counter
            self._table[key] = got
            self._counter += 1
        return got


class NeatGenome:
    """SPEC_NEAT Structural [entity]: one colony's adapter topology, mutated across reseeds. Input nodes are the M
    prototypes (ids 0..M-1), output nodes the E encoding units (ids M..M+E-1). Connections are (input -> output)
    links; `size()` (enabled conns) is the SPEC_BREATH quantity."""

    def __init__(self, n_in: int, n_out: int) -> None:
        self.n_in = int(n_in)
        self.n_out = int(n_out)
        self.nodes: Dict[int, NodeGene] = {}
        for i in range(self.n_in):
            self.nodes[i] = NodeGene(i, INPUT)
        for j in range(self.n_out):
            self.nodes[self.n_in + j] = NodeGene(self.n_in + j, OUTPUT)
        self.conns: List[ConnGene] = []

    # ---- read-only views -------------------------------------------------
    def size(self) -> int:
        """Enabled-connection count (+ hidden nodes, Increment 2) — the breathing quantity (SPEC_BREATH)."""
        return sum(1 for c in self.conns if c.enabled)

    def enabled_conns(self) -> List[ConnGene]:
        return [c for c in self.conns if c.enabled]

    def _live_pairs(self) -> set:
        return {(c.src, c.dst) for c in self.conns}

    # ---- structural mutation (evolution owns STRUCTURE) ------------------
    def add_connection(self, registry: NeatInnovationRegistry, rng=_r) -> bool:
        """SPEC_NEAT NE1: enable a fresh (input -> output) link not already present. Returns False if the graph is
        already complete (no room). The new link's WEIGHT warm-starts at 0 in the phenotype (RL grows it)."""
        live = self._live_pairs()
        if len(live) >= self.n_in * self.n_out:
            return False
        for _ in range(16):                                   # rejection-sample an unused pair
            src = rng.randrange(self.n_in)
            dst = self.n_in + rng.randrange(self.n_out)
            if (src, dst) not in live:
                self.conns.append(ConnGene(src, dst, registry.innovation(src, dst), True))
                return True
        return False

    def toggle_connection(self, rng=_r) -> bool:
        """SPEC_NEAT NE1: flip one connection's enabled bit (a frozen ConnGene -> a new one)."""
        if not self.conns:
            return False
        i = rng.randrange(len(self.conns))
        c = self.conns[i]
        self.conns[i] = replace(c, enabled=not c.enabled)
        return True


_REGISTRY = NeatInnovationRegistry()      # process-wide shared innovation registry (SPEC_NEAT Decision 3)


def registry() -> NeatInnovationRegistry:
    """The shared innovation registry — genome-level code (ColonyGenome.mutate) uses this so structurally-identical
    mutations across colonies align, without threading the sim through the genome."""
    return _REGISTRY


def reset_registry() -> None:
    """Clear the shared registry (test isolation only)."""
    global _REGISTRY
    _REGISTRY = NeatInnovationRegistry()


def sparse_init(n_in: int, n_out: int, registry: NeatInnovationRegistry,
                fanin: int = None, rng=_r) -> NeatGenome:
    """A fresh NEAT genome: each output wired to `fanin` random distinct inputs — sparse, functional, room to grow.
    Default fanin is round(sqrt(n_in)) — a DERIVED sparse width (for the 256-proto readout this is 16, the Kanerva
    sparsity), not an authored constant. (The dense all-links case is only the byte-identity anchor.)"""
    g = NeatGenome(n_in, n_out)
    if fanin is None:
        fanin = round(n_in ** 0.5)
    fan = max(1, min(int(fanin), n_in))
    for j in range(n_out):
        dst = n_in + j
        for src in rng.sample(range(n_in), fan):
            g.conns.append(ConnGene(src, dst, registry.innovation(src, dst), True))
    return g


def align(a: NeatGenome, b: NeatGenome) -> Tuple[List[Tuple[ConnGene, ConnGene]], List[ConnGene], List[ConnGene]]:
    """SPEC_NEAT: innovation-number alignment for crossover/compatibility. Returns (matching pairs, only-in-a,
    only-in-b). Pure — no state."""
    ma = {c.innov: c for c in a.conns}
    mb = {c.innov: c for c in b.conns}
    matching = [(ma[i], mb[i]) for i in ma.keys() & mb.keys()]
    only_a = [ma[i] for i in ma.keys() - mb.keys()]
    only_b = [mb[i] for i in mb.keys() - ma.keys()]
    return matching, only_a, only_b


def compatibility(a: NeatGenome, b: NeatGenome) -> float:
    """SPEC_NEAT: structural distance = (disjoint + excess) / max(genes) in [0, 1], for speciation. No weight term
    (weights aren't in genes). Pure — no state. Two empty genomes are identical (distance 0)."""
    matching, only_a, only_b = align(a, b)
    n = max(len(a.conns), len(b.conns))
    if n == 0:
        return 0.0
    return (len(only_a) + len(only_b)) / n


def crossover(a: NeatGenome, fit_a: float, b: NeatGenome, fit_b: float, rng=_r) -> NeatGenome:
    """SPEC_NEAT: innovation-aligned inheritance — matching genes picked at random from either parent, disjoint/
    excess taken from the FITTER parent. Builds a NEW genome, mutates neither parent. When the two share no
    innovation numbers, this reduces to a copy of the fitter parent."""
    child = NeatGenome(a.n_in, a.n_out)
    matching, only_a, only_b = align(a, b)
    for ca, cb in matching:
        child.conns.append(ca if rng.random() < 0.5 else cb)
    disjoint = only_a if fit_a >= fit_b else only_b
    child.conns.extend(disjoint)
    return child


def evolve_and_install(brain, parent_a: Optional[NeatGenome] = None, parent_b: Optional[NeatGenome] = None,
                       fit_a: float = 1.0, fit_b: float = 1.0, grow_to: Optional[int] = None, rng=_r) -> NeatGenome:
    """SPEC_NEAT NE1/NE4: produce a child adapter topology for `brain` and install it as the readout mask. No
    parents → sparse_init a fresh topology; one → copy it; two → innovation-aligned crossover. Then grow toward
    `grow_to` (the SPEC_BREATH-budgeted size) by add-connection. Returns the installed NeatGenome. Uses the shared
    process registry so lineages stay crossover-alignable. The maw-RL then learns the weights on the live links."""
    E, M = int(brain.readout.weight.shape[0]), int(brain.readout.weight.shape[1])
    reg = registry()
    if parent_a is None and parent_b is None:
        child = sparse_init(M, E, reg, rng=rng)
    elif parent_b is None:
        child = crossover(parent_a, fit_a, parent_a, fit_a, rng=rng)         # single parent → copy topology
    else:
        child = crossover(parent_a, fit_a, parent_b, fit_b, rng=rng)
    if grow_to is not None:
        mutate_topology(child, reg, max(0, int(grow_to) - child.size()), rng=rng)
    brain.apply_neat_genome(child)
    return child


def mutate_topology(genome: NeatGenome, registry: NeatInnovationRegistry, n_changes: int, rng=_r) -> None:
    """SPEC_NEAT NE1 (behavioral, in-place): apply `n_changes` structural mutations. `n_changes` is DERIVED from the
    SPEC_BREATH size delta (grow only as rivals shrink) — no authored mutation-rate constant. Each change is an
    add-connection when growing, else a toggle. Increment 2 adds add-node."""
    for _ in range(max(0, int(n_changes))):
        if not genome.add_connection(registry, rng):
            genome.toggle_connection(rng)
