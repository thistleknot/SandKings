"""The evolving engine: sexual maw reproduction + heritable brain
topology (SPEC_EVOLUTION.md).

Two surviving maws recombine into a new one - dispositions AND neural
architecture (n_nodes = brain_hidden, n_layers = brain_depth) are drawn
from both parents, then mutated. Brains of DIFFERENT topology reproduce
by weight-grafting the overlapping top-left submatrix per layer, so no
shape ever needs to match. Selection (the survival/victory league
already running) does the rest: smarter, larger brains that win
propagate.

Preconditions: torch (guarded - build_brain returns None without it).
Failure modes: none fatal; mismatched shapes graft their overlap only.
"""

import random
from typing import Optional

import numpy as np

BRAIN_HIDDEN_MIN = 24
BRAIN_HIDDEN_MAX = 160
BRAIN_DEPTH_MAX = 4

try:
    import torch
    from neural_hive import HiveMindBrain
    _TORCH = True
except Exception:  # pragma: no cover - torch optional
    _TORCH = False


def build_brain(genome) -> Optional["HiveMindBrain"]:
    """EV2: a brain sized by the genome's architecture genes."""
    if not _TORCH:
        return None
    return HiveMindBrain(hidden_dim=int(getattr(genome, 'brain_hidden', 64)),
                         depth=int(getattr(genome, 'brain_depth', 1)))


def graft_into(child: "HiveMindBrain", parent: "HiveMindBrain") -> None:
    """EV4: copy each parent Linear's overlapping top-left block into the
    child's same-index Linear. Shapes may differ; only the overlap moves."""
    if not _TORCH or parent is None:
        return
    import torch.nn as nn
    c_lin = [m for m in child.encoder if isinstance(m, nn.Linear)]
    p_lin = [m for m in parent.encoder if isinstance(m, nn.Linear)]
    with torch.no_grad():
        for i, cl in enumerate(c_lin):
            if i >= len(p_lin):
                break
            pl = p_lin[i]
            ro = min(cl.weight.shape[0], pl.weight.shape[0])
            co = min(cl.weight.shape[1], pl.weight.shape[1])
            cl.weight.data[:ro, :co] = pl.weight.data[:ro, :co]
            if cl.bias is not None and pl.bias is not None:
                cl.bias.data[:ro] = pl.bias.data[:ro]


def crossover_genome(a, b, mutation_rate: float = 0.15):
    """EV3: a fresh child genome - each gene drawn from a or b, then
    mutated. The sexual step: recombination of two bloodlines."""
    from sandkings import ColonyGenome
    child = ColonyGenome()
    child.use_neural = a.use_neural or b.use_neural
    scalars = ['aggression', 'tunnel_preference', 'expansion_rate',
               'defense_investment', 'fertility', 'resilience', 'patience',
               'loyalty', 'plasticity']
    for attr in scalars:
        src = a if random.random() < 0.5 else b
        setattr(child, attr, getattr(src, attr, 0.5))
    for attr in ('foraging_range', 'swarm_threshold', 'brain_hidden',
                 'brain_depth'):
        src = a if random.random() < 0.5 else b
        setattr(child, attr, getattr(src, attr, getattr(child, attr)))
    # mutate() applies gene jitter AND builds/grafts the brain per its genes
    mutated = child.mutate(mutation_rate)
    if mutated.use_neural and _TORCH:
        # graft from BOTH parents: parent per layer, so the child's brain
        # is a mosaic of its two ancestors (EV4)
        _mosaic_graft(mutated.brain, a.brain, b.brain)
    return mutated


def _mosaic_graft(child_brain, brain_a, brain_b) -> None:
    if not _TORCH or child_brain is None:
        return
    import torch.nn as nn
    c_lin = [m for m in child_brain.encoder if isinstance(m, nn.Linear)]
    with torch.no_grad():
        for i, cl in enumerate(c_lin):
            donor = brain_a if random.random() < 0.5 else brain_b
            if donor is None:
                donor = brain_a or brain_b
            if donor is None:
                continue
            d_lin = [m for m in donor.encoder if isinstance(m, nn.Linear)]
            if i >= len(d_lin):
                continue
            dl = d_lin[i]
            ro = min(cl.weight.shape[0], dl.weight.shape[0])
            co = min(cl.weight.shape[1], dl.weight.shape[1])
            cl.weight.data[:ro, :co] = dl.weight.data[:ro, :co]
            if cl.bias is not None and dl.bias is not None:
                cl.bias.data[:ro] = dl.bias.data[:ro]


def architecture_of(genome) -> str:
    return (f"{int(getattr(genome, 'brain_hidden', 64))}x"
            f"{int(getattr(genome, 'brain_depth', 1))}")
