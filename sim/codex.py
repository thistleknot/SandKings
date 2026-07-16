"""The Codex: the awakened colonies read, and learn (SPEC_CODEX.md).

A corpus - curated survival/coop lore plus the repo's own SPEC files,
loaded read-only - embedded in the SAME GloVe space the thoughts use.
A colony consults with its active concerns and extracts a LESSON that
nudges its dispositions toward playing the environment better; the
modal lesson is cooperation.

SAFETY: the corpus is READ into lesson tags - never executed. No
eval/exec, no network at runtime (GloVe is a local file). Preconditions:
numpy; the GloVe cache is optional (keyword fallback without it).
Failure modes: an empty corpus consults to (\"\", None) - a safe no-op.
"""

import glob
import gzip
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
GLOVE_PATH = os.path.join(_ROOT, "glove-wiki-gigaword-50.gz")
CORPUS_DIR = os.path.join(_ROOT, "corpus")
GLOVE_TOP = 40_000        # frequency-ordered words loaded for embedding
CORPUS_MAX_PASSAGES = 400  # cap per plain-text file (a WikiText dump is huge)

LESSONS = ("coop", "fortify", "dig", "patience", "trade", "commerce", "enlightenment")
# keyword -> lesson, for untagged spec passages (CX2)
LESSON_KEYWORDS = {
    "coop": ("cooperat", "ally", "allies", "truce", "coalition", "tribute",
             "trust", "gift"),
    "fortify": ("wall", "palisade", "defense", "defence", "castle", "gate",
                "fortif", "siege"),
    "dig": ("tunnel", "dig", "dug", "underground", "shelter", "dam",
            "channel", "burrow"),
    "patience": ("patience", "hoard", "season", "harvest", "store",
                 "long-term", "winter"),
    "trade": ("trade", "envoy", "fertility", "grow", "economy", "surplus"),
    "commerce": ("commerce", "wage", "contract", "market", "factor", "grain",
                 "license", "settle"),  # CX7a: economy doctrine
    "enlightenment": ("enlighten", "ascend", "ascension", "plasticity", "ceiling",
                      "escape", "breach"),  # CX7a: post-escape intelligence
}
# the sim reads these as bounded genome nudges (CX4)
LESSON_EFFECT = {
    "coop": [("loyalty", 1.0)],
    "fortify": [("defense_investment", 1.0)],
    "dig": [("tunnel_preference", 1.0)],
    "patience": [("patience", 1.0)],
    "trade": [("loyalty", 0.5), ("fertility", 0.5)],
    "commerce": [("loyalty", 1.0), ("fertility", 1.0)],  # CX7a: market doctrine
    "enlightenment": [("plasticity", 1.0)],  # CX7a: learning-to-learn leap
}
CODEX_NUDGE = 0.03
CODEX_INTERVAL = 300

_GLOVE: Optional[Dict[str, np.ndarray]] = None


def _load_glove() -> Dict[str, np.ndarray]:
    """Load (once) the top-N GloVe word vectors; {} if the cache absent."""
    global _GLOVE
    if _GLOVE is not None:
        return _GLOVE
    vecs: Dict[str, np.ndarray] = {}
    if os.path.exists(GLOVE_PATH):
        with gzip.open(GLOVE_PATH, "rt", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= GLOVE_TOP:
                    break
                parts = line.rstrip().split(" ")
                if len(parts) > 10:
                    vecs[parts[0]] = np.asarray(parts[1:], dtype=np.float32)
    _GLOVE = vecs
    return vecs


_TOKEN = re.compile(r"[a-z]+")


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


def embed(text: str) -> Optional[np.ndarray]:
    """L2-normalized mean of in-vocab word vectors; None if none hit."""
    glove = _load_glove()
    if not glove:
        return None
    vs = [glove[t] for t in _tokens(text) if t in glove]
    if not vs:
        return None
    v = np.mean(vs, axis=0)
    n = np.linalg.norm(v)
    return v / n if n else None


def infer_lesson(text: str) -> str:
    """Keyword-vote a lesson for an untagged passage (CX2)."""
    low = text.lower()
    best, best_hits = "coop", 0
    for lesson, keys in LESSON_KEYWORDS.items():
        hits = sum(low.count(k) for k in keys)
        if hits > best_hits:
            best, best_hits = lesson, hits
    return best


class Codex:
    """The read-only library. Built from files; never pickled (CX5)."""

    def __init__(self, corpus_dir: str = CORPUS_DIR,
                 spec_dir: Optional[str] = os.path.join(_ROOT, "docs", "specs")):
        self.passages: List[Tuple[str, str, Optional[np.ndarray],
                                  List[str]]] = []
        self._ingest_corpus(corpus_dir)
        if spec_dir:
            self._ingest_specs(spec_dir)

    def _add(self, text: str, lesson: str):
        text = text.strip()
        if len(_tokens(text)) < 4:
            return
        self.passages.append((text, lesson, embed(text), _tokens(text)))

    def _ingest_corpus(self, corpus_dir: str):
        # recursive: curated lore in corpus/ AND baked material in
        # subdirs like corpus/wikitext/ (SPEC_SANDBOX SB4)
        for path in sorted(glob.glob(os.path.join(corpus_dir, "**", "*.md"),
                                     recursive=True)):
            with open(path, encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
            if "LESSON:" in body:  # curated: split on ## passages
                for chunk in re.split(r"\n##\s", body):
                    m = re.search(r"LESSON:\s*(\w+)", chunk)
                    lesson = m.group(1).strip() if m else infer_lesson(chunk)
                    if lesson not in LESSONS:
                        lesson = "coop"
                    clean = re.sub(r"LESSON:\s*\w+", "", chunk)
                    clean = re.sub(r"^#+\s.*", "", clean).strip()
                    self._add(clean, lesson)
            else:  # plain text (e.g. WikiText): paragraph chunks, capped
                added = 0
                for para in re.split(r"\n\s*\n", body):
                    para = para.strip()
                    if len(para) < 40 or para.startswith("="):
                        continue  # skip headers and stubs
                    self._add(para[:600], infer_lesson(para))
                    added += 1
                    if added >= CORPUS_MAX_PASSAGES:
                        break  # a 6MB dump must not explode the index

    def _ingest_specs(self, spec_dir: str):
        for path in sorted(glob.glob(os.path.join(spec_dir, "SPEC_*.md"))):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            for chunk in re.split(r"\n##+\s", body)[1:]:
                self._add(chunk[:600], infer_lesson(chunk))

    def consult(self, words: List[str]) -> Tuple[str, Optional[str]]:
        """CX3: retrieve the best passage for the query words + its lesson."""
        if not self.passages:
            return "", None
        query = " ".join(words) or "survival"
        qv = embed(query)
        best, best_score = None, -1e9
        if qv is not None:
            for text, lesson, pv, _toks in self.passages:
                if pv is None:
                    continue
                score = float(np.dot(qv, pv))
                if score > best_score:
                    best, best_score = (text, lesson), score
        if best is None:  # keyword-overlap fallback (no vectors)
            qset = set(words) or {"survival"}
            for text, lesson, _pv, toks in self.passages:
                score = len(qset & set(toks))
                if score > best_score:
                    best, best_score = (text, lesson), score
        return best if best is not None else ("", None)

    # CX5: derived from files - never drag the vectors through a pickle
    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        self.__init__()


def apply_lesson(genome, lesson: str, scale: float = 1.0) -> List[str]:
    """CX4: bounded genome nudge; returns the attrs it moved."""
    moved = []
    for attr, weight in LESSON_EFFECT.get(lesson, ()):
        current = getattr(genome, attr, 0.5)
        setattr(genome, attr,
                float(np.clip(current + CODEX_NUDGE * weight * scale, 0.0, 1.0)))
        moved.append(attr)
    return moved
