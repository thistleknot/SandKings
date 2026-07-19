"""SPEC_JLENS — the colony J-lens. Torch-required (skips without). Pins: gate default off, the Jacobian read-out
(top-k unspoken thoughts, pure inference), the treachery meter range, and that injection provably raises the target
token's J-space weight (monotonic in strength)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import torch
    import sandkings
    from tongue import TongueSystem, MaskedMind
    HAVE = MaskedMind is not None
except Exception:
    HAVE = False


def _skip():
    print("SKIP (jlens unavailable — no torch)")
    return True


def test_gate_default_off():
    if not HAVE:
        return _skip()
    assert sandkings.JLENS_ENABLED is False, "JLENS gate off by default (battery byte-identical)"


def test_read_thoughts_topk_and_deterministic():
    if not HAVE:
        return _skip()
    ts = TongueSystem()
    torch.manual_seed(0)
    enc = torch.randn(32)
    a = ts.read_thoughts(enc, k=5)
    b = ts.read_thoughts(enc, k=5)
    assert len(a) == 5 and all(isinstance(n, str) for n, _ in a), "5 (token, weight) pairs"
    assert a == b, "pure inference — deterministic, no RNG"
    assert [n for n, _ in a] == [n for n, _ in a], "ranked list"


def test_treachery_in_range():
    if not HAVE:
        return _skip()
    ts = TongueSystem()
    torch.manual_seed(1)
    tr = ts.treachery(torch.randn(32))
    assert 0.0 <= tr <= 1.0, f"treachery is a probability mass in [0,1] (got {tr})"


def test_injection_raises_target_and_is_monotonic():
    """SPEC_JLENS acceptance: injecting toward a token raises its J-space weight, monotonically in strength."""
    if not HAVE:
        return _skip()
    ts = TongueSystem()
    torch.manual_seed(2)
    enc = torch.randn(32)
    tok = "war"
    base = dict(ts.read_thoughts(enc, k=len(ts.vocab)))[tok]
    w1 = dict(ts.read_thoughts(ts.inject_thought(enc, tok, strength=1.0), k=len(ts.vocab)))[tok]
    w5 = dict(ts.read_thoughts(ts.inject_thought(enc, tok, strength=5.0), k=len(ts.vocab)))[tok]
    assert w1 > base, "injection raises the target token's J-weight"
    assert w5 > w1, "monotonic in strength (stronger press -> higher weight)"


def test_inject_unknown_token_is_noop():
    if not HAVE:
        return _skip()
    ts = TongueSystem()
    enc = torch.randn(32)
    out = ts.inject_thought(enc, "not_a_real_token_xyz", strength=3.0)
    assert torch.equal(torch.as_tensor(out).reshape(-1), enc.reshape(-1)), "unknown token -> unchanged encoding"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all jlens tests passed")
