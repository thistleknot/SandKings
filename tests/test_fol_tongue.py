"""SPEC_FOL_TONGUE acceptance — decode, role-typed masked-slot training, store roundtrip, rendering, byte-identity.

Run under run_tests.py (sim/ on path; the gate is reset off before each suite, so the bag-of-words Tongue stays
byte-identical — that invariant is enforced by the whole battery, not re-asserted here)."""
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import fol_tongue
from fol_tongue import FOL_ROLE_TOKENS

# A small vocab with the sentences' content words present (exact-identity canon — WordNet quality is not under test
# here; the injected canon isolates the decode LOGIC from WordNet flakiness).
VOCAB = ["colony", "raids", "granary", "winter", "ants", "fear", "flood", "flee", "valley",
         "queen", "commands", "soldiers", "defend", "hive"] + list(FOL_ROLE_TOKENS)
_VID = {w: i for i, w in enumerate(VOCAB)}
_STOP = {"the", "a", "an", "her", "his", "its", "their", "to", "of", "in", "on", "and", "or"}


def _canon(span):
    for w in str(span).lower().replace("_", " ").split():
        if w in _STOP:
            continue
        if w in _VID:
            return _VID[w]
    return -1


def test_decode_battery():
    """A fixed battery of 3 varied sentences (raid, fear+flee conjunction, command+defend implication) each yields
    >=1 triplet with pred resolved and >=2 resolvable slots."""
    sents = [
        "The colony raids the granary in winter.",
        "Ants fear the flood and flee the valley.",
        "The queen commands her soldiers to defend the hive.",
    ]
    for s in sents:
        trips = fol_tongue.decode_to_triplets(s, _canon)
        assert trips, f"no triplet decoded from {s!r}"
        for t in trips:
            assert t.pred_id >= 0, f"pred unresolved in {t} from {s!r}"
            resolvable = (t.subj_id >= 0) + 1 + (t.obj_id >= 0)
            assert resolvable >= 2, f"<2 resolvable slots in {t} from {s!r}"
    # the raid sentence must recover the raid relation and both arguments
    raid = fol_tongue.decode_to_triplets(sents[0], _canon)
    assert any(t.subj_id == _VID["colony"] and t.pred_id == _VID["raids"] and t.obj_id == _VID["granary"]
               for t in raid), f"raids(colony, granary) not among {raid}"


def test_observe_triplet_trains():
    """Role-typed masked-slot training raises masked-slot recovery above chance on a fixed triplet, across >=3 seeds
    (dense path — NEG reset off by the runner). Better than random: mean(last window) > mean(first window)."""
    from tongue import _HAVE_TORCH, MaskedMind
    if not _HAVE_TORCH:
        return
    import torch
    roles = tuple(range(len(VOCAB) - 3, len(VOCAB)))            # ⟨SUBJ⟩ ⟨PRED⟩ ⟨OBJ⟩ ids
    slots = [(roles[0], _VID["colony"]), (roles[1], _VID["raids"]), (roles[2], _VID["granary"])]
    wins = 0
    for seed in (0, 1, 2, 3, 4):
        torch.manual_seed(seed)
        rng = random.Random(seed)
        mm = MaskedMind(len(VOCAB))
        hidden = torch.randn(mm.head.in_features // 2)
        accs = [mm.observe_triplet(hidden, slots, rng) or 0.0 for _ in range(240)]
        first = float(np.mean(accs[:40])); last = float(np.mean(accs[-40:]))
        wins += 1 if last > first else 0
    assert wins >= 3, f"masked-slot recovery did not climb in >=3/5 seeds (wins={wins})"


def test_observe_triplet_needs_two_slots():
    """<2 resolvable slots -> None (nothing to mask+context)."""
    from tongue import _HAVE_TORCH, MaskedMind
    if not _HAVE_TORCH:
        return
    import torch
    mm = MaskedMind(len(VOCAB))
    hidden = torch.randn(mm.head.in_features // 2)
    assert mm.observe_triplet(hidden, [(len(VOCAB) - 3, _VID["colony"])], random.Random(0)) is None


def test_build_and_load_store_roundtrip(tmp_path=None):
    """build_store over a tiny corpus, save/load, rows survive; empty corpus raises (fail loud)."""
    corpus = ["The colony raids the granary in winter.", "The queen commands her soldiers to defend the hive."]
    store = fol_tongue.build_store(corpus, _canon)
    assert store.rows.shape[1] == 3 and store.rows.shape[0] >= 2
    assert (store.rows[:, 1] >= 0).all(), "every kept row must have a resolved predicate"
    path = os.path.join(os.environ.get("TEMP", "."), "fol_triplets_test.npz")
    fol_tongue.save_store(store, path)
    back = fol_tongue.load_store(path)
    assert back is not None and np.array_equal(back.rows, store.rows) and np.allclose(back.conf, store.conf)
    os.remove(path)
    try:
        fol_tongue.build_store(["x"], _canon)                  # nothing decodes -> raise
        raise AssertionError("empty decode should raise")
    except RuntimeError:
        pass


def test_load_store_absent_is_none():
    assert fol_tongue.load_store(os.path.join(os.environ.get("TEMP", "."), "no_such_fol.npz")) is None


def test_format_triplet_tag():
    """Rendering: predicate(subject, object) with the observed/inferred tag from confidence; -1 slot -> '?'."""
    row = (_VID["colony"], _VID["raids"], _VID["granary"])
    assert fol_tongue.format_triplet(VOCAB, row, 1.0) == "raids(colony, granary) [observed]"
    assert fol_tongue.format_triplet(VOCAB, row, 0.5) == "raids(colony, granary) [inferred]"
    assert fol_tongue.format_triplet(VOCAB, (-1, _VID["raids"], _VID["granary"]), 1.0) == "raids(?, granary) [observed]"


def test_wordnet_canonicalizer_exact_path():
    """The canonicalizer's exact-identity fast path resolves a span whose content word is directly in vocab."""
    canon = fol_tongue.wordnet_canonicalizer(VOCAB)
    assert canon("the colony") == _VID["colony"]
    assert canon("the granary") == _VID["granary"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
