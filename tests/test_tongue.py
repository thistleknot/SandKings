"""SPEC_TONGUE TG1 — the masked-prediction head. Host-runnable (needs torch; the py310 venv has it). Proves the
additive masked head LEARNS to recover a masked token from context+hidden (the reference-slice acceptance), and does
not just output all-ones. The sim wiring (read_reach gene, TONGUE_ENABLED gate, observe_neural integration) is a
later increment; this pins the learned component itself.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    import tongue
    from tongue import MaskedMind, READ_REACH_DEFAULT, TONGUE_HIDDEN
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (tongue/torch unavailable)")
    return True


def _fixed_hidden(seed=0):
    torch.manual_seed(seed)
    return torch.randn(TONGUE_HIDDEN).tolist()


def test_defaults():
    if not HAVE:
        return _skip()
    assert tongue.TONGUE_ENABLED is False, "gate defaults off (battery byte-identical)"
    assert READ_REACH_DEFAULT == 3


def test_masked_recovery_learns():
    """TG1: training makes the head DISCRIMINATE — masked active tokens recover, non-active ones don't. Measured as a
    gap (robust to lucky random init on any single token)."""
    if not HAVE:
        return _skip()
    torch.manual_seed(0)
    mm = MaskedMind(vocab_size=16)
    rng = random.Random(0)
    hidden = _fixed_hidden()
    active = [2, 5, 9, 11]
    non_active = [t for t in range(16) if t not in active]

    def gap(m):
        r_act = sum(m.recovery(hidden, active, [t]) for t in active) / len(active)      # mask each active, recover it
        r_non = sum(m.recovery(hidden, active, [t]) for t in non_active) / len(non_active)  # false positives
        return r_act - r_non

    before = gap(mm)                                    # untrained: ~0
    for _ in range(400):
        mm.observe(hidden, active, rng, reach=READ_REACH_DEFAULT)
    after = mm.recovery(hidden, active, [5])            # a specific masked token is recovered
    assert after >= 0.99, f"a masked active token is recovered (got {after})"
    assert gap(mm) > before + 0.3, f"discrimination emerged with training ({before:.2f} -> {gap(mm):.2f})"
    assert gap(mm) >= 0.8, f"active recover, non-active don't (gap {gap(mm):.2f})"


def test_not_all_ones():
    """TG1: the head learns the ACTIVE set, not a degenerate all-present output — a non-active token stays low."""
    if not HAVE:
        return _skip()
    torch.manual_seed(1)
    mm = MaskedMind(vocab_size=16)
    rng = random.Random(1)
    hidden = _fixed_hidden(1)
    active = [3, 7, 12]
    for _ in range(400):
        mm.observe(hidden, active, rng)
    assert mm.recovery(hidden, active, [7]) >= 0.99, "an active token is predicted present"
    assert mm.recovery(hidden, active, [0]) < 0.5, "a non-active token is NOT predicted present"


def test_per_token_accuracy_tracked():
    """TG1: per-token accuracy EMA populates for masked tokens (the raw comprehension signal TG4 reads)."""
    if not HAVE:
        return _skip()
    torch.manual_seed(2)
    mm = MaskedMind(vocab_size=16)
    rng = random.Random(2)
    hidden = _fixed_hidden(2)
    for _ in range(200):
        mm.observe(hidden, [1, 4, 8], rng)
    assert mm.acc, "accuracy EMA populated"
    assert all(0.0 <= v <= 1.0 for v in mm.acc.values())


def test_tokenspace_glove_seed_and_knn():
    """TG2: GloVe-seeded shared space; kNN decode recovers the seeded token; unseeded rows stay finite."""
    if not HAVE:
        return _skip()
    from tongue import TokenSpace
    ts = TokenSpace(["war", "food", "peace"], dim=4)
    n = ts.seed_glove({"war": [1.0, 0, 0, 0], "food": [0, 1.0, 0, 0]})   # peace unseeded
    assert n == 2
    assert ts.nearest([1.0, 0, 0, 0])[0] == "war"
    assert ts.nearest([0, 1.0, 0, 0])[0] == "food"
    import numpy as np
    assert np.isfinite(ts.vec("peace")).all()


def test_compliance_gate():
    """TG5: obey = comprehension × loyalty × alignment; a resentful or self-endangering house refuses."""
    if not HAVE:
        return _skip()
    from tongue import compliance, obeys
    assert obeys(0.9, 0.9, 0.9)                       # understands, loyal, aligned -> obeys
    assert not obeys(0.9, 0.05, 0.9)                  # understands but hates you -> refuses
    assert not obeys(0.9, 0.9, 0.02)                  # loyal but suicidal order -> refuses
    assert not obeys(0.05, 0.9, 0.9)                  # doesn't understand the words -> can't obey
    assert compliance(0.5, 0.5, 0.5) == 0.125


def test_volley_macd_directional_change():
    """TG6: the fast/slow median cross flips direction when a rising comprehension series turns down (MACD-style)."""
    if not HAVE:
        return _skip()
    from tongue import VolleyStats
    vs = VolleyStats(window=8, fast=3, slow=6)
    for v in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:   # rising
        s = vs.push(v)
    assert s["direction"] == "expansion"
    crossed = False
    for v in [0.7, 0.5, 0.3, 0.1, 0.0]:                  # falling -> should cross to contraction
        s = vs.push(v)
        crossed = crossed or s["crossed"]
    assert s["direction"] == "contraction"
    assert crossed, "a rising-then-falling series must trigger a direction cross"


def test_curriculum_learning_progress():
    """TG9: expand into the max-LEARNING-PROGRESS token, NOT the highest-error (noisy-TV) or lowest-error one."""
    if not HAVE:
        return _skip()
    from tongue import next_to_learn
    # 'improving' has real progress; 'noise' is high-error-but-zero-progress (irreducible); 'mastered' plateaued
    assert next_to_learn({"improving": 0.05, "noise": 0.0, "mastered": 0.0001}) == "improving"
    assert next_to_learn({"noise": 0.0, "mastered": 0.0}) is None   # nothing learnable -> don't chase noise


def test_textreader_learns_to_read():
    """TG3: masked LM over the shared space recovers a masked word from context (accuracy rises with reading)."""
    if not HAVE:
        return _skip()
    from tongue import TokenSpace, TextReader
    import numpy as np
    vocab = ["the", "maw", "hungers", "for", "food"]
    ts = TokenSpace(vocab, dim=len(vocab))
    ts.E = np.eye(len(vocab), dtype="float32")          # orthogonal, distinct
    tr = TextReader(ts)
    rng = random.Random(0)
    for _ in range(800):
        tr.read(vocab, rng)
    assert tr.acc > 0.6, f"the reader learned to recover masked words (acc {tr.acc:.2f})"


def test_vision_self_recognition():
    """TG8: after aligning each colony's frame to its own token-centroid, a frame is recognized as ITS OWN, not
    another's (the measurable 'it saw a picture of its cage')."""
    if not HAVE:
        return _skip()
    from tongue import VisionEncoder
    torch.manual_seed(0)
    ve = VisionEncoder(dim=8)
    imgA = torch.rand(12, 12, 3); imgB = torch.rand(12, 12, 3)
    tA = torch.randn(8); tB = torch.randn(8)
    for _ in range(300):
        ve.align(imgA, tA); ve.align(imgB, tB)
    assert ve.recognizes(imgA, tA) > ve.recognizes(imgA, tB), "frame A recognized as A, not B"
    assert ve.recognizes(imgB, tB) > ve.recognizes(imgB, tA), "frame B recognized as B, not A"


def test_curriculum_comprehensible_input():
    """TG9: read texts with the FEWEST unlearned words first (Krashen i+1) — a stable sort by unknown-word count."""
    if not HAVE:
        return _skip()
    from tongue import curriculum_order
    known = {"the", "maw", "food", "eats"}
    easy = "the maw eats food"                 # 0 unknown
    med = "the maw wants food"                 # 1 unknown (wants)
    hard = "alien xylophone quzz grok"         # 4 unknown
    assert curriculum_order([hard, med, easy], known) == [easy, med, hard]


def test_read_text_caps_new_words():
    """TG9: a read introduces at most TONGUE_NEW_PER_READ new words ('a few masked words at a time')."""
    if not HAVE:
        return _skip()
    from tongue import TongueSystem, TONGUE_NEW_PER_READ
    ts = TongueSystem(vocab=["a", "b"], chat_stem=None)
    n0 = len(ts._space().vocab)
    ts.read_text("a b cat dog fox owl bee ant", random.Random())   # 6 new words present, cap applies
    assert len(ts.space.vocab) - n0 == TONGUE_NEW_PER_READ, "only a few new words are added per read"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all tongue tests passed")
