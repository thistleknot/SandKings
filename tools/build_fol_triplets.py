"""Offline: decode the Codex wikitext/lore corpus into subject-predicate-object triplets (SPEC_FOL_TONGUE).

Each sentence is parsed by triplet-extract (dependency-parse OpenIE); each span is canonicalized to the Tongue's
EXTENDED vocab via WordNet's IS-A/synonym taxonomy (so the ids align with a VOCAB_EXTEND-on game). The frozen store
is written to fol_triplets.npz — the runtime loads a table, never a parser in the hot loop (balance objective with
computational efficiency). Run once whenever the corpus or vocab changes.

Usage:  py310 tools/build_fol_triplets.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "sim"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # for build_ensemble_embeddings._vocab

import fol_tongue


def main():
    from build_ensemble_embeddings import _vocab
    vocab = _vocab()                                            # the Tongue's extended token list (ids align)
    canon = fol_tongue.wordnet_canonicalizer(vocab)
    from codex import Codex
    cx = Codex()
    corpus = [p[0] for p in cx.passages]                        # the ingested passage texts
    print(f"[FOL] decoding {len(corpus)} passages over vocab={len(vocab)} ...")
    store = fol_tongue.build_store(corpus, canon)
    fol_tongue.save_store(store)
    print(f"[FOL] wrote {store.rows.shape[0]} triplets -> {fol_tongue.FOL_TRIPLET_PATH}")
    for i in range(min(10, len(store.rows))):                   # sanity: a few rendered FOL lines
        print("   ", fol_tongue.format_triplet(vocab, store.rows[i], float(store.conf[i])))


if __name__ == "__main__":
    main()
