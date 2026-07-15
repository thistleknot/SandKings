"""Fit the LEARNED shared encoder basis (SPEC_REPR / Bundle 5) and save it to learned_basis.npz.

The random Kanerva codebook covers the whitened state manifold ~28x worse than a learned one (half its
256 prototypes are dead). This fits, ONCE and offline, a shared frozen basis every colony loads:
  - a ZCA whitener (mean, W) from representative soldier states, and
  - k-means prototype centroids in that whitened space.
The readout stays evolvable (GA untouched); the codebook stays SHARED (grafting semantics preserved).

Run from the repo root with the py310 interpreter:
    C:/Users/user/py310/Scripts/python.exe tools/fit_learned_basis.py
Writes learned_basis.npz next to sandkings.py.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import sandkings
from sandkings import SandKingsSimulation, UnitType
from neural_hive import (HiveMindBrain, SoldierLayer, KANERVA_PROTOS, ZCA_EPS)

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "learned_basis.npz")


def collect_states(steps):
    random.seed(11); np.random.seed(11); torch.manual_seed(11)
    sim = SandKingsSimulation(width=56, height=40, depth=12, num_colonies=4)
    for c in sim.colonies:
        c.genome.use_neural = True
        if c.genome.brain is None:
            c.genome.brain = HiveMindBrain()
        for u in c.units:
            if u.unit_type == UnitType.SOLDIER and getattr(u, 'brain_layer', None) is None:
                u.brain_layer = SoldierLayer(); u.brain_layer.steps_alive = 0
    raw, hooked = [], set()

    def hook(m, inp):
        raw.append(inp[0].detach().reshape(-1, inp[0].shape[-1]).clone())

    def ensure():
        for c in sim.colonies:
            b = getattr(c.genome, 'brain', None)
            if b is not None and id(b) not in hooked:
                b.register_forward_pre_hook(hook); hooked.add(id(b))

    for _ in range(steps):
        ensure(); sim.step()
    return torch.cat(raw, dim=0).numpy().astype(np.float64)


def fit_zca(X):
    """Match ZCAWhitener: W = evecs @ diag(1/sqrt(clamp(evals))) @ evecs.T on the state covariance."""
    mean = X.mean(0)
    cov = np.cov((X - mean).T)
    cov = 0.5 * (cov + cov.T) + ZCA_EPS * np.eye(X.shape[1])
    evals, evecs = np.linalg.eigh(cov)
    W = evecs @ np.diag(1.0 / np.sqrt(np.clip(evals, ZCA_EPS, None))) @ evecs.T
    return mean, W


def main():
    X = collect_states(STEPS)
    print(f"collected {len(X)} states, dim {X.shape[1]}")
    mean, W = fit_zca(X)
    Xw = (X - mean) @ W
    # DEDUPLICATE (idle soldier states are massively duplicated and collapse k-means onto a few modes);
    # fit on DISTINCT states so rare situations (combat, low health) each earn a prototype.
    uniq = np.unique(np.round(Xw, 2), axis=0)
    print(f"distinct states (rounded): {len(uniq)}")
    from sklearn.cluster import KMeans
    if len(uniq) >= KANERVA_PROTOS:
        km = KMeans(n_clusters=KANERVA_PROTOS, n_init=4, max_iter=150, random_state=0).fit(uniq)
        protos = km.cluster_centers_.astype(np.float32)
    else:  # fewer distinct states than cells: use them all, pad with jittered copies
        pad = KANERVA_PROTOS - len(uniq)
        rng = np.random.RandomState(0)
        extra = uniq[rng.randint(0, len(uniq), pad)] + rng.normal(0, 0.05, (pad, X.shape[1]))
        protos = np.vstack([uniq, extra]).astype(np.float32)
    # report coverage on a held-out tail of the FULL (duplicated) distribution — real usage
    te = Xw[int(len(Xw) * 0.8):]
    d2 = ((te[:, None, :] - protos[None, :, :].astype(np.float64)) ** 2).sum(-1)
    print(f"codebook: quant-err {float(d2.min(1).mean()):.4f}, protos used "
          f"{len(np.unique(d2.argmin(1)))}/{KANERVA_PROTOS}")
    np.savez(OUT, mean=mean.astype(np.float32), W=W.astype(np.float32), protos=protos)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
