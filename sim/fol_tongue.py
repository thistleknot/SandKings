"""SPEC_FOL_TONGUE — communication as subject-predicate-object triplets + FOL qualifiers.

The Tongue (SPEC_TONGUE) learns an order-free BAG of world-tokens. This module reframes the learning signal to
RELATIONAL structure: who did what to whom. Wikitext is decoded OFFLINE into (subject, predicate, object) triplets
via `triplet-extract` (dependency-parse OpenIE), each span canonicalized to a vocab id through WordNet's IS-A/synonym
taxonomy (the same symbolic member SPEC_ENSEMBLE_EMBED already builds). The colony then learns by masking ONE role
SLOT of a triplet and reconstructing it — a stronger, sparser objective than bag-of-words masking, and cheap
(3 slots, negative-sampling-friendly). This is the keeper's FOL normalization: predicate = intent/feeling, the
[observed]/[inferred] tag rides `Triplet.confidence`.

Design law (inherited): member tables FROZEN; the offline decode is a one-time build (never a parser in the hot
loop); gate off ⇒ the bag-of-words Tongue, byte-identical.
"""
import os
from collections import namedtuple
from typing import Callable, List, Optional

import numpy as np

# --- Gate + role alphabet (structural, not tunables) --------------------------------------------------------------
FOL_TONGUE_ENABLED = False          # gate; entrypoint flips baseline-on IFF fol_triplets.npz present. Off ⇒ byte-identical.
FOL_ROLE_TOKENS = ("⟨SUBJ⟩", "⟨PRED⟩", "⟨OBJ⟩")   # ⟨SUBJ⟩ ⟨PRED⟩ ⟨OBJ⟩ — the 3 role markers
FOL_TRIPLET_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fol_triplets.npz")

# One decoded, vocab-mapped triplet. -1 in any slot = that span did not resolve to the vocab (dropped downstream if
# fewer than 2 slots resolve). confidence in [0,1]: 1.0 = direct (observed), <1.0 = entailed (inferred).
FolTriplet = namedtuple("FolTriplet", ("subj_id", "pred_id", "obj_id", "confidence"))

# The offline-decoded corpus the runtime loads (what fol_triplets.npz holds).
FolTripletStore = namedtuple("FolTripletStore", ("rows", "conf"))   # rows: (N,3) int32 ; conf: (N,) float32


_STOP = {"the", "a", "an", "her", "his", "its", "their", "to", "of", "in", "on", "and", "or",
         "this", "that", "these", "those", "some", "all", "any", "no", "not", "is", "are", "was", "were"}


def wordnet_canonicalizer(vocab: List[str]) -> Callable[[str], int]:
    """Return a pure span->vocab-id canonicalizer backed by a PRECOMPUTED WordNet reverse index — the fixed
    IS-A/synonym topology the keeper asked for, resolved in O(1) per span (not O(vocab) path-similarity per query).

    Build once: every vocab word claims, as surface forms mapping to its id, its own lemma plus the lemmas of its
    WordNet SYNONYMS and its DIRECT (1-hop) hypernyms and hyponyms. Lower vocab ids win ties (lower id = the more
    canonical/frequent anchor). Exact vocab words always map to themselves (override any synonym capture). At query
    time a span's content words (WordNet-lemmatized via morphy) are looked up in this index; first hit wins, else -1.
    Surface spans are evidence, not ontology (kg_ontology): one canonical id per span.

    Precondition: `vocab` is the Tongue's token list. Failure mode: no nltk/WordNet ⇒ index holds only the exact
    vocab words (synonym/hypernym expansion is skipped, exact identity still resolves)."""
    vid = {w.lower(): i for i, w in enumerate(vocab)}
    lemma_to_id = {}                                             # surface lemma -> canonical vocab id
    try:
        from nltk.corpus import wordnet as wn
        for i in range(len(vocab) - 1, -1, -1):                  # reverse: lower ids overwrite, so they win ties
            w = vocab[i]
            for ss in wn.synsets(w.replace(" ", "_")):
                for r in [ss] + ss.hypernyms() + ss.hyponyms():  # synonyms + 1-hop IS-A neighborhood (bounded)
                    for lm in r.lemma_names():
                        lemma_to_id[lm.replace("_", " ").lower()] = i
    except Exception:
        wn = None
    for w, i in vid.items():                                     # exact vocab words always resolve to themselves
        lemma_to_id[w] = i

    def _lemmatize(word: str):
        if wn is None:
            return [word]
        m = wn.morphy(word)                                      # "raids"->"raid", "fled"->"flee" (base form)
        return [word, m] if m and m != word else [word]

    def canon(span: str) -> int:
        words = [w for w in str(span).lower().replace("_", " ").split() if w and w not in _STOP]
        for w in words:
            for c in _lemmatize(w):
                if c in lemma_to_id:
                    return lemma_to_id[c]
        return -1

    return canon


def default_extractor():
    """One reusable OpenIEExtractor with ENTAILMENT OFF — the natural-logic paraphrase explosion is the slow step and
    it only yields low-confidence redundant variants (noise for training). Clause-split stays ON so conjunctions
    still split into separate triplets (the FOL ∧ the keeper wants). Direct triplets are confidence≈1.0 = [observed].
    Reused across a whole corpus build (the library's documented fast path). None if triplet-extract is unavailable."""
    try:
        import triplet_extract as te
        return te.OpenIEExtractor(enable_entailment=False, enable_clause_split=True)
    except Exception:
        return None


def decode_to_triplets(text: str, canon: Callable[[str], int], extractor=None) -> List[FolTriplet]:
    """Pure NL->FOL boundary: run triplet-extract over `text`, canonicalize each span to a vocab id, keep triplets
    whose PREDICATE resolves and at least one argument resolves (>=2 slots). Returns [] if the extractor is
    unavailable (fails closed) or nothing parses. `extractor` = a reused OpenIEExtractor instance (build path); None
    falls back to the module singleton (te.extract). No state.

    Guarantee: every returned FolTriplet has pred_id >= 0 and at least 2 of {subj,pred,obj} >= 0."""
    try:
        import triplet_extract as te
    except Exception:
        return []
    out: List[FolTriplet] = []
    try:
        extracted = (extractor.extract_triplet_objects(text) if extractor is not None else te.extract(text))
    except Exception:
        return []
    for t in extracted:
        s = canon(getattr(t, "subject", ""))
        p = canon(getattr(t, "relation", ""))
        o = canon(getattr(t, "object", ""))
        if p < 0:
            continue
        if (1 if s >= 0 else 0) + 1 + (1 if o >= 0 else 0) < 2:   # pred always counts; need >=2 resolvable slots
            continue
        out.append(FolTriplet(s, p, o, float(getattr(t, "confidence", 1.0))))
    return out


def build_store(corpus, canon: Callable[[str], int], extractor=None) -> FolTripletStore:
    """Offline: decode a wikitext corpus (iterable of passage strings) into the frozen triplet store. Reuses ONE
    entailment-off extractor across the whole corpus (fast + clean). Logs kept vs dropped (never silently truncates).
    Raises if nothing decodes (the extractor or vocab is wrong — fail loud)."""
    ex = extractor if extractor is not None else default_extractor()
    rows, conf, dropped = [], [], 0
    for passage in corpus:
        trips = decode_to_triplets(passage, canon, ex)
        if not trips:
            dropped += 1
            continue
        for t in trips:
            rows.append((t.subj_id, t.pred_id, t.obj_id))
            conf.append(t.confidence)
    if not rows:
        raise RuntimeError("SPEC_FOL_TONGUE: no triplets decoded from the corpus — extractor or vocab mismatch")
    print(f"[FOL] decoded {len(rows)} triplets from the corpus ({dropped} passages yielded none)")
    return FolTripletStore(np.asarray(rows, dtype=np.int32), np.asarray(conf, dtype=np.float32))


def save_store(store: FolTripletStore, path: str = FOL_TRIPLET_PATH) -> None:
    np.savez(path, rows=store.rows, conf=store.conf)


def load_store(path: str = FOL_TRIPLET_PATH) -> Optional[FolTripletStore]:
    """Load fol_triplets.npz, or None if absent/unreadable (the gate then stays off — byte-identical). Pure I/O
    boundary mirroring ensemble_embed.load_ensemble."""
    try:
        if not os.path.exists(path):
            return None
        d = np.load(path)
        return FolTripletStore(d["rows"].astype(np.int32), d["conf"].astype(np.float32))
    except Exception:
        return None


def format_triplet(vocab: List[str], row, conf: float) -> str:
    """Render one decoded triplet as the keeper's FOL line: `predicate(subject, object)  [observed|inferred]`.
    Missing (-1) slots render as `?`. The tag is [observed] iff the triplet was a DIRECT parse (confidence == 1.0),
    else [inferred] (an entailed reading) — the operating-contract epistemic split, no authored float threshold."""
    def w(i):
        return vocab[i] if 0 <= int(i) < len(vocab) else "?"
    s, p, o = int(row[0]), int(row[1]), int(row[2])
    tag = "observed" if float(conf) >= 1.0 else "inferred"
    return f"{w(p)}({w(s)}, {w(o)}) [{tag}]"
