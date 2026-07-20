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

# --- Increment 2: FOL quantifiers + connectives -------------------------------------------------------------------
# A triplet's logical FORM, packed into one small int carried alongside the (subj,pred,obj) row. The subject's
# determiner sets the QUANTIFIER (∀/∃); a negation word on the predicate sets the ¬ flag. Clause-split (Inc 1, the
# extractor's enable_clause_split) already realises ∧ by emitting conjoined clauses as SEPARATE triplets, so ∧ needs
# no per-row code. Alphabet is STRUCTURAL (fixed 4 forms), not a tunable.
QUANT_NONE, QUANT_FORALL, QUANT_EXISTS = 0, 1, 2   # subject quantifier (low 2 bits)
QUANT_MASK = 3
NEG_FLAG = 4                                        # bit 2: predicate negated (¬)
_FORALL_DET = {"all", "every", "each", "any"}       # ∀ surface determiners
_EXISTS_DET = {"some", "a", "an", "one"}            # ∃ surface determiners
_NEG_WORDS = {"not", "no", "never", "none", "n't"}  # ¬ markers on the predicate


def quantifier_code(subj_span: str, pred_span: str) -> int:
    """Pure NL->FOL form detection: read the SUBJECT's determiner for the quantifier and the PREDICATE for negation,
    from the RAW spans (before stopword stripping, which would eat 'all'/'some'/'not'). ∀ wins over ∃ when both
    appear (universal is the stronger claim). Returns a packed int (low 2 bits = quantifier, bit 2 = ¬). No state."""
    sw = str(subj_span).lower().replace("_", " ").split()
    pw = str(pred_span).lower().replace("_", " ").split()
    q = QUANT_FORALL if any(w in _FORALL_DET for w in sw) else (QUANT_EXISTS if any(w in _EXISTS_DET for w in sw) else QUANT_NONE)
    if any(w in _NEG_WORDS for w in pw):
        q |= NEG_FLAG
    return q


# One decoded, vocab-mapped triplet. -1 in any slot = that span did not resolve to the vocab (dropped downstream if
# fewer than 2 slots resolve). confidence in [0,1]: 1.0 = direct (observed), <1.0 = entailed (inferred). quant =
# packed FOL form (Increment 2; defaults to QUANT_NONE so Inc-1 call sites and stores stay valid).
FolTriplet = namedtuple("FolTriplet", ("subj_id", "pred_id", "obj_id", "confidence", "quant"))
FolTriplet.__new__.__defaults__ = (QUANT_NONE,)     # quant optional -> back-compatible with Inc-1 4-arg construction

# The offline-decoded corpus the runtime loads (what fol_triplets.npz holds). quants optional (Inc 2).
FolTripletStore = namedtuple("FolTripletStore", ("rows", "conf", "quants"))   # rows (N,3) i32; conf (N,) f32; quants (N,) i8
FolTripletStore.__new__.__defaults__ = (None,)      # quants optional -> old 2-field stores still construct


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
        subj_raw, pred_raw = getattr(t, "subject", ""), getattr(t, "relation", "")
        s = canon(subj_raw)
        p = canon(pred_raw)
        o = canon(getattr(t, "object", ""))
        if p < 0:
            continue
        if (1 if s >= 0 else 0) + 1 + (1 if o >= 0 else 0) < 2:   # pred always counts; need >=2 resolvable slots
            continue
        q = quantifier_code(subj_raw, pred_raw)                   # Increment 2: ∀/∃ + ¬ from the raw spans
        out.append(FolTriplet(s, p, o, float(getattr(t, "confidence", 1.0)), q))
    return out


def build_store(corpus, canon: Callable[[str], int], extractor=None) -> FolTripletStore:
    """Offline: decode a wikitext corpus (iterable of passage strings) into the frozen triplet store. Reuses ONE
    entailment-off extractor across the whole corpus (fast + clean). Logs kept vs dropped (never silently truncates).
    Raises if nothing decodes (the extractor or vocab is wrong — fail loud)."""
    ex = extractor if extractor is not None else default_extractor()
    rows, conf, quants, dropped = [], [], [], 0
    for passage in corpus:
        trips = decode_to_triplets(passage, canon, ex)
        if not trips:
            dropped += 1
            continue
        for t in trips:
            rows.append((t.subj_id, t.pred_id, t.obj_id))
            conf.append(t.confidence)
            quants.append(t.quant)
    if not rows:
        raise RuntimeError("SPEC_FOL_TONGUE: no triplets decoded from the corpus — extractor or vocab mismatch")
    n_quant = sum(1 for q in quants if q)
    print(f"[FOL] decoded {len(rows)} triplets from the corpus ({dropped} passages yielded none; {n_quant} quantified/negated)")
    return FolTripletStore(np.asarray(rows, dtype=np.int32), np.asarray(conf, dtype=np.float32),
                           np.asarray(quants, dtype=np.int8))


def save_store(store: FolTripletStore, path: str = FOL_TRIPLET_PATH) -> None:
    quants = store.quants if store.quants is not None else np.zeros(len(store.rows), dtype=np.int8)
    np.savez(path, rows=store.rows, conf=store.conf, quants=quants)


def load_store(path: str = FOL_TRIPLET_PATH) -> Optional[FolTripletStore]:
    """Load fol_triplets.npz, or None if absent/unreadable (the gate then stays off — byte-identical). Pure I/O
    boundary mirroring ensemble_embed.load_ensemble. Back-compatible: an Inc-1 store without a `quants` array loads
    as all-QUANT_NONE (so an old npz renders exactly as before — byte-identical on the ON path too)."""
    try:
        if not os.path.exists(path):
            return None
        d = np.load(path)
        rows = d["rows"].astype(np.int32)
        quants = d["quants"].astype(np.int8) if "quants" in d.files else np.zeros(len(rows), dtype=np.int8)
        return FolTripletStore(rows, d["conf"].astype(np.float32), quants)
    except Exception:
        return None


def format_triplet(vocab: List[str], row, conf: float, quant: int = QUANT_NONE) -> str:
    """Render one decoded triplet as the keeper's FOL line, now with Increment-2 QUANTIFIERS and NEGATION:
    `∀x. predicate(x, object)` / `∃x. predicate(...)` for a quantified subject, `¬predicate(...)` when negated,
    and the plain `predicate(subject, object)` otherwise — then `[observed|inferred]`. Missing (-1) slots render as
    `?`. The tag is [observed] iff a DIRECT parse (confidence == 1.0), else [inferred]. quant defaults to QUANT_NONE
    so an Inc-1 call renders exactly as before. No authored thresholds."""
    def w(i):
        return vocab[i] if 0 <= int(i) < len(vocab) else "?"
    s, p, o = int(row[0]), int(row[1]), int(row[2])
    tag = "observed" if float(conf) >= 1.0 else "inferred"
    q = int(quant)
    pred = w(p)
    if q & NEG_FLAG:
        pred = "¬" + pred
    quantifier = q & QUANT_MASK
    if quantifier == QUANT_FORALL:
        body = f"{pred}(∀x:{w(s)}, {w(o)})"
    elif quantifier == QUANT_EXISTS:
        body = f"{pred}(∃x:{w(s)}, {w(o)})"
    else:
        body = f"{pred}({w(s)}, {w(o)})"
    return f"{body} [{tag}]"


def action_triplet(subj_id: int, pred_id: int, obj_id: int, quant: int = QUANT_NONE) -> FolTriplet:
    """Increment 2 (colony action cross-train): wrap a colony's OWN executed action as a first-class FolTriplet
    (subject=actor, predicate=action, object=target), so the same masked-slot objective that learns from wikitext
    can also learn from what colonies actually DO — grounding the shared word-space in lived events, not just text.
    confidence=1.0 (a directly observed act). The training loop feeds these alongside the corpus rows."""
    return FolTriplet(int(subj_id), int(pred_id), int(obj_id), 1.0, int(quant))
