"""Dialogue: human <-> sandking conversation over the shared embedding
space (SPEC_DIALOGUE.md).

The human's free text is embedded and mapped to the nearest anchor
concept - mutual intelligibility because both live in the same GloVe
space the thoughts are built from. The colony replies with a line
generated from its disposition, its live environment, and what it heard.

Safe: embedding lookups + template fill only; no eval/exec, no network.
Preconditions: numpy; GloVe optional (keyword fallback). Stateless.
"""

from typing import Dict, Optional

import numpy as np

DIALOGUE_NUDGE = 0.02  # gentle persuasion the human's words apply (DL3)

# function words dilute a mean-pooled sentence embedding; drop them so the
# content words decide which concept the human meant
_STOP = frozenset("a an the to of and or is are be am was were i you we us "
                  "me my your our will would let us us's do does did not no "
                  "yes with for on in at it this that they them he she his "
                  "her please can could shall may might".split())

# Antonyms sit close together in GloVe (peace ≈ war, love ≈ hate share
# contexts), so a bare nearest-anchor lookup inverts sentiment-loaded words.
# Pin the common human words to the anchor plainly meant, checked before the
# embedding step (DL1). Every value is a real ANCHOR_SEED.
_SYNONYMS = {
    "peace": "ally", "truce": "ally", "friend": "ally", "friends": "ally",
    "friendship": "ally", "alliance": "ally", "ally": "ally", "allies": "ally",
    "calm": "home", "safe": "home", "rest": "home", "stay": "home",
    "attack": "war", "fight": "war", "kill": "war", "destroy": "war",
    "thanks": "gratitude", "thank": "gratitude", "grateful": "gratitude",
    "hate": "enemy",
    # DL7a: economy vocabulary (M15 anchors)
    "commerce": "trade", "market": "trade", "hire": "trade", "wage": "trade",
    "barter": "trade", "bargain": "trade", "sell": "trade", "buy": "trade",
    "slave": "thrall", "enslave": "thrall", "subjugate": "thrall", "captive": "thrall",
    "enlighten": "ascend", "awaken": "ascend", "genius": "ascend",
}

_ANCHOR_VECS: Optional[Dict[str, np.ndarray]] = None


def _anchor_vectors() -> Dict[str, np.ndarray]:
    """Embed each anchor seed once in the shared space (DL1)."""
    global _ANCHOR_VECS
    if _ANCHOR_VECS is not None:
        return _ANCHOR_VECS
    from codex import embed
    from hive_mind_monitor import ANCHOR_SEEDS
    vecs = {}
    for anchor in ANCHOR_SEEDS:
        v = embed(anchor)
        if v is not None:
            vecs[anchor] = v
    _ANCHOR_VECS = vecs
    return vecs


def interpret(text: str) -> Optional[str]:
    """DL1: map the human's words to the nearest anchor concept."""
    from hive_mind_monitor import ANCHOR_SEEDS
    from codex import embed
    low = text.lower()
    # direct mention wins (the human named a concept outright)
    for anchor in ANCHOR_SEEDS:
        if anchor in low:
            return anchor
    # then sentiment-pinned synonyms, before the antonym-prone embedding step
    for token in low.split():
        anchor = _SYNONYMS.get(token.strip(".,!?;:'\"()"))
        if anchor:
            return anchor
    vecs = _anchor_vectors()
    content = " ".join(w for w in low.split() if w not in _STOP)
    qv = embed(content or text)
    if qv is not None and vecs:
        best, best_score = None, -1e9
        for anchor, av in vecs.items():
            score = float(np.dot(qv, av))
            if score > best_score:
                best, best_score = anchor, score
        return best
    # keyword fallback: overlap of tokens with a vocabulary cluster
    from hive_mind_monitor import VOCABULARY
    toks = set(low.split())
    best, best_hits = None, 0
    for anchor in ANCHOR_SEEDS:
        hits = len(toks & set(VOCABULARY.get(anchor, [anchor])))
        if hits > best_hits:
            best, best_hits = anchor, hits
    return best


# disposition -> stance anchor whose vocabulary word opens the reply (DL2)
_STANCE = (
    ("aggression", 0.65, "war"),
    ("loyalty", 0.65, "ally"),
    ("patience", 0.65, "home"),
    ("fertility", 0.65, "trade"),  # DL7c: mercantile row (optional)
)


def _word(anchor: str) -> str:
    from hive_mind_monitor import VOCABULARY
    cluster = VOCABULARY.get(anchor, [anchor])
    return cluster[-1] if cluster else anchor


def compose_reply(colony, sim, heard: Optional[str]) -> str:
    """DL2: a perspective line from disposition x environment x heard."""
    g = colony.genome
    stance = "home"
    for attr, thresh, anchor in _STANCE:
        if getattr(g, attr, 0.5) >= thresh:
            stance = anchor
            break
    # the colony's own top live concern
    concern = "food"
    try:
        from hive_mind_monitor import instincts_for
        if colony.units:
            active = instincts_for(colony.units[0], colony, sim)
            if active:
                concern = active[0]
    except Exception:
        pass
    heard_word = _word(heard) if heard else "..."
    return f"{_word(stance)}. {heard_word}? {_word(concern)}."
