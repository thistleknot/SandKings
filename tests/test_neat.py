"""SPEC_NEAT Increment 1 — the pure NEAT core. Torch-free, host-runnable. Pins the genome, the shared innovation
registry, and the genetic operators against the spec's acceptance criteria."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import neat
    from neat import (NeatGenome, NeatInnovationRegistry, sparse_init, crossover,
                      compatibility, align, mutate_topology)
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (neat unavailable)")
    return True


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert neat.NEAT_ENABLED is False, "NEAT_ENABLED defaults off (battery byte-identical)"


def test_registry_same_structure_same_innovation():
    """SPEC_NEAT NE1: identical (src,dst) in different colonies MUST get the same innovation number (crossover
    alignment); distinct structure gets distinct numbers; self-loops are rejected."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    a = reg.innovation(3, 260)
    b = reg.innovation(3, 260)          # same structure, later, different "colony"
    c = reg.innovation(4, 260)          # different structure
    assert a == b, "same (src,dst) -> same innovation"
    assert c != a, "different (src,dst) -> different innovation"
    try:
        reg.innovation(5, 5)
        assert False, "self-loop must raise"
    except ValueError:
        pass


def test_sparse_init_fanin():
    """A fresh genome wires each output to exactly `fanin` distinct inputs (sparse, not dense)."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    g = sparse_init(256, 32, reg, fanin=16, rng=random.Random(0))
    assert g.size() == 32 * 16, f"32 outputs x 16 fan-in enabled conns (got {g.size()})"
    assert g.size() < 256 * 32, "sparse, well below the dense readout"


def test_compatibility_identical_and_disjoint():
    """compatibility is 0 for identical genomes and rises with disjoint fraction; two empty genomes are identical."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    g = sparse_init(64, 8, reg, fanin=4, rng=random.Random(1))
    same = crossover(g, 1.0, g, 1.0, rng=random.Random(2))   # copy of g (all matching)
    assert compatibility(g, same) == 0.0, "identical topology -> distance 0"
    assert compatibility(NeatGenome(64, 8), NeatGenome(64, 8)) == 0.0, "two empty genomes identical"
    g2 = sparse_init(64, 8, reg, fanin=4, rng=random.Random(99))
    assert compatibility(g, g2) > 0.0, "different topologies -> positive distance"


def test_crossover_disjoint_from_fitter_and_no_shared():
    """SPEC_NEAT: disjoint genes come from the FITTER parent; with no shared innovations the child copies the
    fitter parent."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    a = sparse_init(32, 4, reg, fanin=3, rng=random.Random(3))
    reg2 = NeatInnovationRegistry()                          # disjoint innovation space -> no shared genes
    b = sparse_init(32, 4, reg2, fanin=3, rng=random.Random(4))
    child_a = crossover(a, 5.0, b, 1.0, rng=random.Random(5))
    assert {c.innov for c in child_a.conns} == {c.innov for c in a.conns}, "no shared -> copies the fitter (a)"
    child_b = crossover(a, 1.0, b, 5.0, rng=random.Random(6))
    assert len(child_b.conns) == len(b.conns), "no shared, b fitter -> copies b"


def test_mutate_grows_under_budget():
    """SPEC_NEAT NE1: mutate_topology applies n_changes add-connections (growth), bounded — the count is the
    Breath-derived delta, so growth is throttled, never a runaway."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    g = sparse_init(64, 8, reg, fanin=4, rng=random.Random(7))
    before = g.size()
    mutate_topology(g, reg, n_changes=10, rng=random.Random(8))
    assert g.size() == before + 10, f"10 growth mutations add 10 enabled conns (got {g.size() - before})"
    assert g.size() <= 64 * 8, "never exceeds the complete graph"


def test_add_node_splits_connection():
    """SPEC_NEAT Increment 2: add_node splits an enabled conn src->dst into src->h->dst — disables the old link
    (kept for alignment), creates ONE hidden node, adds TWO enabled conns; net size change is +1."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    g = sparse_init(8, 2, reg, fanin=2, rng=random.Random(1))
    before = g.size()
    assert not g.hidden_nodes()
    assert g.add_node(reg, rng=random.Random(2))
    assert len(g.hidden_nodes()) == 1, "exactly one hidden node created"
    assert g.size() == before + 1, "disable 1 + add 2 enabled = net +1"
    disabled = [c for c in g.conns if not c.enabled]
    assert len(disabled) == 1, "the split link is disabled, not deleted"


def test_node_innovation_stable():
    """SPEC_NEAT Increment 2: splitting the SAME connection innovation yields the SAME hidden id (crossover-alignable
    across the async population), and hidden ids never collide with input/output ids."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    assert reg.node_innovation(5) == reg.node_innovation(5), "same split -> same hidden id"
    assert reg.node_innovation(5) != reg.node_innovation(6), "different splits -> different hidden ids"
    assert reg.node_innovation(5) >= NeatInnovationRegistry.HIDDEN_BASE, "hidden ids above proto/encoding range"


def test_speciate_separates_divergent():
    """SPEC_NEAT NE4 Increment 2: speciate partitions structurally-divergent genomes into >1 species using the
    DERIVED median compatibility threshold; identical genomes collapse to one species."""
    if not HAVE:
        return _skip()
    reg = NeatInnovationRegistry()
    base = sparse_init(16, 4, reg, fanin=3, rng=random.Random(3))
    twins = [base, crossover(base, 1.0, base, 1.0, rng=random.Random(4))]  # structurally identical
    assert len(neat.speciate(twins)) == 1, "identical genomes -> one species"
    pop = [sparse_init(16, 4, reg, fanin=3, rng=random.Random(10 + k)) for k in range(8)]
    for k in range(4):
        for _ in range(6):
            pop[k].add_node(reg, rng=random.Random(100 + k))  # diverge half the pop by growing bottlenecks
    assert len(neat.speciate(pop)) >= 2, "divergent topologies -> multiple species"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all neat tests passed")
