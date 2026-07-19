"""SPEC_ENSEMBLE_EMBED — offline builder for `ensemble_embed.npz`.

Fetches the Tongue vocabulary's vectors from up to 6 embedding models (BERT/DistilBERT, GloVe, word2vec, Jina v2
small, Nomic, MiniLM), aligns each into ONE comparable frame via relative representations (cosine-sims to shared
anchors — Moschella et al. 2023), stacks the frozen members, and writes the npz the runtime loads. The heavy models
run HERE, once — the game only ever loads the frozen table.

Graceful degradation: a member whose deps/model are unavailable is skipped (logged). The build ABORTS if fewer than
ENSEMBLE_FLOOR (3) members resolve — the multi-view floor. Run:  python tools/build_ensemble_embeddings.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sim"))

import ensemble_embed as ee            # relative_representation, EnsembleBundle, save_ensemble, constants
from hive_mind_monitor import ANCHOR_SEEDS   # the 42-token vocab


def _vocab():
    # SPEC_VOCAB_EXTEND: build the ensemble for the EXTENDED vocab (the anchors' concept cloud) so a VOCAB_EXTEND-on
    # game loads a matching mixture. Falls back to the 42 anchors if GloVe is absent.
    import tongue
    import codex
    return tongue.extended_vocab(list(ANCHOR_SEEDS), codex._load_glove())


# ---- per-member fetchers: word list -> (V, d) float32 raw vectors, or raise on unavailable -------------------
def fetch_glove(words):
    import codex
    g = codex._load_glove()
    if not g:
        raise RuntimeError("glove file absent")
    dim = len(next(iter(g.values())))
    return np.stack([np.asarray(g.get(w, np.zeros(dim)), dtype=np.float32) for w in words])


def fetch_word2vec(words):
    import gensim.downloader as api            # missing gensim -> ImportError -> skipped
    kv = api.load("word2vec-google-news-300")
    dim = kv.vector_size
    return np.stack([kv[w].astype(np.float32) if w in kv else np.zeros(dim, np.float32) for w in words])


def _fetch_hf_contextual(words, model_name):
    """BERT/DistilBERT via transformers — the mask/CLS angle: mean-pool the word's contextual token states."""
    import torch
    from transformers import AutoModel, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModel.from_pretrained(model_name).eval()
    out = []
    with torch.no_grad():
        for w in words:
            enc = tok(w, return_tensors="pt")
            h = mdl(**enc).last_hidden_state[0]           # (T, d)
            out.append(h.mean(0).numpy().astype(np.float32))
    return np.stack(out)


def fetch_bert(words):
    return _fetch_hf_contextual(words, "distilbert-base-uncased")


def _fetch_sbert(words, model_name, trust_remote_code=False):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(model_name, trust_remote_code=trust_remote_code)
    return np.asarray(m.encode(list(words), show_progress_bar=False), dtype=np.float32)


def fetch_jina(words):
    """jina v2 small via ONNX (model-w-mean-pooling.onnx from https://huggingface.co/jinaai/jina-embeddings-v2-
    small-en) — bypasses the remote torch modeling code that broke on transformers 5.3 / torch 2.11 (missing
    transformers.onnx, find_pruneable_heads_and_indices, dropped config defaults, and a meta-device forward).
    Pooled 512-d sentence embeddings via onnxruntime."""
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer
    import onnxruntime as ort
    name = "jinaai/jina-embeddings-v2-small-en"
    tok = AutoTokenizer.from_pretrained(name)
    sess = ort.InferenceSession(hf_hub_download(name, "model-w-mean-pooling.onnx"),
                                providers=["CPUExecutionProvider"])
    input_names = {i.name for i in sess.get_inputs()}
    out = []
    for w in words:
        enc = tok(w, return_tensors="np")
        feeds = {k: enc[k].astype(np.int64) for k in input_names if k in enc}
        out.append(np.asarray(sess.run(None, feeds)[0]).reshape(-1).astype(np.float32))
    return np.stack(out)


def fetch_nomic(words):
    return _fetch_sbert(words, "nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)


def fetch_minilm(words):
    return _fetch_sbert(words, "sentence-transformers/all-MiniLM-L6-v2")


def fetch_wordnet(words, anchors):
    """The SYMBOLIC member: each word's WordNet path-similarity to the anchor words — the fixed IS-A/synonym
    taxonomy (a labeled scaffold the distributional members lack). Already lives in the anchor frame (a
    similarity-to-anchors matrix), so it does NOT go through relative_representation. Missing synsets → zero row."""
    from nltk.corpus import wordnet as wn

    def syn(w):
        ss = wn.synsets(w.replace(" ", "_"))
        return ss[0] if ss else None

    anchor_syn = [syn(a) for a in anchors]
    out = np.zeros((len(words), len(anchors)), dtype=np.float32)
    for i, w in enumerate(words):
        s = syn(w)
        if s is None:
            continue
        for j, a in enumerate(anchor_syn):
            if a is None:
                continue
            sim = s.path_similarity(a)
            if sim is not None:
                out[i, j] = sim
    return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-8)   # L2 rows (same frame as the other members)


FETCHERS = {
    "bert": fetch_bert, "glove": fetch_glove, "word2vec": fetch_word2vec,
    "jina": fetch_jina, "nomic": fetch_nomic, "minilm": fetch_minilm,
}


def build():
    words = _vocab()
    anchor_ids = list(range(min(ee.ENSEMBLE_ANCHORS, len(words))))    # first D vocab tokens as shared anchors
    if len(anchor_ids) != ee.ENSEMBLE_ANCHORS:
        print(f"[warn] vocab ({len(words)}) < ENSEMBLE_ANCHORS ({ee.ENSEMBLE_ANCHORS}); frame width = {len(anchor_ids)}")
    anchor_words = [words[i] for i in anchor_ids]
    members, names = [], []
    for name in ee.ENSEMBLE_ROSTER:
        try:
            if name == "wordnet":
                aligned = fetch_wordnet(words, anchor_words)          # symbolic — already in the anchor frame
                note = f"path-sim -> {aligned.shape}"
            else:
                raw = FETCHERS[name](words)
                aligned = ee.relative_representation(raw, anchor_ids) # (V, D) comparable frame
                note = f"raw {raw.shape} -> aligned {aligned.shape}"
            members.append(aligned); names.append(name)
            print(f"[ok]   {name:9s} {note}")
        except Exception as exc:
            print(f"[skip] {name:9s} ({type(exc).__name__}: {exc})")
    if len(members) < ee.ENSEMBLE_FLOOR:
        raise SystemExit(f"[abort] only {len(members)} member(s) resolved; need >= {ee.ENSEMBLE_FLOOR} "
                         f"(the multi-view floor). No npz written.")
    bundle = ee.EnsembleBundle(members=np.stack(members).astype(np.float32), tokens=words, names=names)
    ee.save_ensemble(bundle)
    print(f"[done] wrote {ee.ENSEMBLE_PATH} — {bundle.members.shape} ({len(names)} angles: {', '.join(names)})")


if __name__ == "__main__":
    build()
