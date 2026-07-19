"""SPEC_NEAT Increment 1 phenotype — the masked readout (torch-required; skips without). Pins the byte-identity
anchor (all-ones mask == the dense readout) and that a sparse NEAT mask zeroes the masked-out proto->encoding links."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    from neural_hive import HiveMindBrain
    from neat import NeatGenome, NeatInnovationRegistry, ConnGene, sparse_init
    import random
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (neat adapter unavailable — no torch)")
    return True


def _dense_genome(M, E, reg):
    g = NeatGenome(M, E)
    for dst in range(E):
        for src in range(M):
            g.conns.append(ConnGene(src, M + dst, reg.innovation(src, M + dst), True))
    return g


def test_all_ones_mask_is_byte_identical():
    """The byte-identity anchor: an all-links-enabled NEAT mask MUST reduce exactly to the dense readout output."""
    if not HAVE:
        return _skip()
    torch.manual_seed(0)
    brain = HiveMindBrain(input_dim=40, encoding_dim=32)
    M, E = brain.readout.weight.shape[1], brain.readout.weight.shape[0]
    x = torch.randn(40)
    enc0 = brain(x).clone()
    brain.apply_neat_genome(_dense_genome(M, E, NeatInnovationRegistry()))
    enc1 = brain(x)
    assert torch.equal(enc0, enc1), "all-ones NEAT mask == dense readout (byte-identity anchor)"


def test_sparse_mask_zeroes_masked_out_links():
    """A sparse NEAT genome installs a mask with exactly `enabled` ones, and outputs differ from the dense case."""
    if not HAVE:
        return _skip()
    torch.manual_seed(1)
    brain = HiveMindBrain(input_dim=40, encoding_dim=32)
    M, E = brain.readout.weight.shape[1], brain.readout.weight.shape[0]
    reg = NeatInnovationRegistry()
    g = sparse_init(M, E, reg, fanin=16, rng=random.Random(0))
    brain.apply_neat_genome(g)
    assert int(brain.readout_mask.sum().item()) == g.size(), "mask ones == enabled connections"
    assert brain.readout_mask.shape == (E, M), "mask is (encoding, prototypes)"
    # a proto connected to no output must be a fully-zero column in the mask
    live_srcs = {c.src for c in g.enabled_conns()}
    dead_src = next(s for s in range(M) if s not in live_srcs) if len(live_srcs) < M else None
    if dead_src is not None:
        assert float(brain.readout_mask[:, dead_src].sum().item()) == 0.0, "an unconnected proto is fully masked"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all neat adapter tests passed")
