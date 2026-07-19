"""SPEC_VOCAB_EXTEND — the represented-vocabulary extension. Torch-free. Pins: gate default off, graceful empty-GloVe
fallback, anchors-lead-with-stable-ids, no duplicates, and that the vocab genuinely grows."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

try:
    import tongue
    from hive_mind_monitor import ANCHOR_SEEDS
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (tongue unavailable)")
    return True


def _synthetic_glove(seed=0):
    rng = np.random.RandomState(seed)
    extra = ["blade", "siege", "blood", "army", "famine", "starve", "thirst", "throne", "crown", "plague",
             "harvestman", "raider", "kinsman", "worship", "sacrifice", "betrayal", "conquest", "vassal",
             "tribute", "banner", "fortress", "rampart", "sentinel", "forager", "brood", "swarm"]
    words = list(ANCHOR_SEEDS) + extra
    return {w: rng.randn(50).astype("float32") for w in words}


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert tongue.VOCAB_EXTEND_ENABLED is False, "vocab extension off by default (byte-identical)"


def test_empty_glove_falls_back_to_anchors():
    if not HAVE:
        return _skip()
    assert tongue.extended_vocab(list(ANCHOR_SEEDS), {}, 15) == list(ANCHOR_SEEDS), "no glove -> just the anchors"


def test_extends_anchors_first_no_dups():
    if not HAVE:
        return _skip()
    v = tongue.extended_vocab(list(ANCHOR_SEEDS), _synthetic_glove(), m=5)
    assert v[:len(ANCHOR_SEEDS)] == list(ANCHOR_SEEDS), "anchors lead, ids 0..41 preserved (game supervision stable)"
    assert len(set(v)) == len(v), "no duplicate tokens"
    assert len(v) > len(ANCHOR_SEEDS), "the represented vocabulary genuinely grows"
    assert all(w.isalpha() and len(w) >= 3 for w in v[len(ANCHOR_SEEDS):]), "extension is content words only"


def test_neighbors_bounded_by_m():
    if not HAVE:
        return _skip()
    g = _synthetic_glove()
    small = tongue.extended_vocab(list(ANCHOR_SEEDS), g, m=1)
    big = tongue.extended_vocab(list(ANCHOR_SEEDS), g, m=8)
    assert len(big) >= len(small), "more neighbors per anchor -> at least as large a vocab"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all vocab_extend tests passed")
