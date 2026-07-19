"""SPEC_ENSEMBLE_EMBED — a learned, universal-geometry mixture of frozen embedding members feeding the Tongue's
MaskedMind head. The heavy models run OFFLINE once (tools/build_ensemble_embeddings.py) → a frozen
`ensemble_embed.npz`; at runtime the MaskedMind's embedding table is a tiny LEARNED mixture over those frozen
members, trained by the masked-prediction loss ("weights learned between what helps reduce loss between guesses").

Members are aligned into ONE comparable frame by RELATIVE REPRESENTATIONS (each token = its cosine-sims to shared
anchors; Moschella et al. 2023) so heterogeneous spaces (GloVe 50-d, MiniLM 384-d, …) become averageable. Gated:
ENSEMBLE_EMBED_ENABLED default False (or npz absent) ⇒ MaskedMind.emb is the current random table (byte-identical).

Alignment + I/O are pure numpy (torch-free); only MixtureEmbedding needs torch (built only in the MaskedMind path).
"""
import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

ENSEMBLE_EMBED_ENABLED = False        # gate; entrypoint flips baseline-on IFF the npz is present. Off = byte-identical.
ENSEMBLE_ANCHORS = 32                 # relative-representation frame width; == TONGUE_HIDDEN so no projection is needed
ENSEMBLE_FLOOR = 3                    # the multi-view floor: the builder aborts below this many resolvable members
ENSEMBLE_ROSTER = ("bert", "glove", "word2vec", "jina", "nomic", "minilm", "wordnet")   # 6 distributional + 1
#   SYMBOLIC (WordNet IS-A/synonym path-similarity — a fixed labeled taxonomy the mixture learns to weight)

ENSEMBLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ensemble_embed.npz")


@dataclass
class EnsembleBundle:
    """SPEC_ENSEMBLE_EMBED Structural [value]: the stacked frozen members the npz holds — what the runtime loads."""
    members: np.ndarray               # (K, vocab, D) float32, frozen
    tokens: List[str]                 # the vocab index
    names: List[str]                  # the K member names


def relative_representation(raw: np.ndarray, anchor_ids: List[int]) -> np.ndarray:
    """SPEC_ENSEMBLE_EMBED: the alignment primitive (pure) — each token row → its cosine similarities to the anchor
    tokens, an L2-normalized (vocab, len(anchor_ids)) space-invariant table. This is what makes heterogeneous member
    spaces comparable/averageable. Free function: no state."""
    x = raw.astype(np.float32)
    x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)      # L2 rows
    sims = x @ x[anchor_ids].T                                     # (vocab, D) cosine-to-anchors
    sims = sims / (np.linalg.norm(sims, axis=1, keepdims=True) + 1e-8)
    return sims.astype(np.float32)


def load_ensemble(path: Optional[str] = None) -> Optional[EnsembleBundle]:
    """Load ensemble_embed.npz, or None if absent/unreadable (the caller falls back to the GloVe seed). Mirrors
    neural_hive._load_learned_basis — a pure I/O boundary, no state. Resolves ENSEMBLE_PATH at CALL time (not a
    frozen default) so a monkeypatch/relocation of the module path is honored."""
    if path is None:
        path = ENSEMBLE_PATH
    if not os.path.exists(path):
        return None
    try:
        d = np.load(path, allow_pickle=True)
        return EnsembleBundle(members=d["members"].astype(np.float32),
                              tokens=list(d["tokens"]), names=list(d["names"]))
    except Exception:
        return None


def save_ensemble(bundle: EnsembleBundle, path: Optional[str] = None) -> None:
    """Persist a bundle to npz (offline builder). Resolves ENSEMBLE_PATH at call time."""
    if path is None:
        path = ENSEMBLE_PATH
    np.savez(path, members=bundle.members.astype(np.float32),
             tokens=np.array(bundle.tokens, dtype=object), names=np.array(bundle.names, dtype=object))


# ---- runtime learned mixture (torch) -------------------------------------------------------------------------
# torch is imported at module level (guarded) so MixtureEmbedding is a MODULE-LEVEL class — a nested/<locals> class
# is unpicklable, which would break checkpoint save/load of a sim whose MaskedMind holds a mixture. ensemble_embed
# is only ever imported in a torch context (MaskedMind, run_tests, the offline tool), so the top-level import is safe.
try:
    import torch
    import torch.nn as nn
    _TORCH = True
except Exception:
    _TORCH = False


if _TORCH:
    class MixtureEmbedding(nn.Module):
        """SPEC_ENSEMBLE_EMBED Structural [entity]: the runtime learned mixture replacing MaskedMind.emb — a drop-in
        for nn.Embedding(vocab, D). The member tables are a FROZEN buffer; only `mix` (per-member logits) and a
        zero-init `residual` learn, via the MaskedMind's existing SGD. Module-level so it pickles with a checkpoint.
        emb(tok) = Σ_m softmax(mix)_m · members[m, tok] + residual(tok)."""

        def __init__(self, members_np: np.ndarray):
            super().__init__()
            m = torch.as_tensor(np.asarray(members_np, dtype=np.float32))   # (K, vocab, D)
            self.register_buffer("members", m)                              # frozen (no grad)
            K, V, D = m.shape
            self.mix = nn.Parameter(torch.zeros(K))                         # uniform start (softmax of zeros)
            self.residual = nn.Embedding(V, D)                              # learned deviation beyond the substrate
            with torch.no_grad():
                self.residual.weight.zero_()                                # start == pure mixture

        def forward(self, ids):
            # INDEX-THEN-MIX (lean synergy): weight only the NEEDED member rows, not the full (vocab, D) consensus
            # table — O(|ids|) not O(vocab) per forward. Identical result (indexing commutes with the weighted sum).
            w = torch.softmax(self.mix, dim=0)                              # (K,)
            sel = self.members[:, ids]                                     # (K, …ids…, D)
            return torch.tensordot(w, sel, dims=([0], [0])) + self.residual(ids)


def build_mixture(members: np.ndarray):
    """SPEC_ENSEMBLE_EMBED Structural: construct the runtime MixtureEmbedding from stacked frozen members."""
    if not _TORCH:
        raise RuntimeError("build_mixture requires torch")
    return MixtureEmbedding(members)
