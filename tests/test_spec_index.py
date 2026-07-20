"""Guard test — SPEC_INDEX.md must catalog every spec on disk.

Purpose: the spec catalog rotted once (2026-07-20: 22 of 73 specs were absent from
the index, including most of the recent ML arc). This test makes that failure mode
loud: it fails the battery the moment a `docs/specs/SPEC_*.md` is added without a
matching reference in `SPEC_INDEX.md`. Pure filesystem — no sandkings import, no RNG.

Precondition: run from anywhere; paths resolve relative to this file.
Failure mode surfaced: a new spec file that no one added to the index (silent
under-cataloguing), which is exactly what made the index untrustworthy.
"""

import os

_SPECS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "specs"
)
_INDEX = os.path.join(_SPECS_DIR, "SPEC_INDEX.md")


def _spec_names():
    """Every SPEC_*.md basename (sans extension) except the index itself."""
    return sorted(
        f[:-3]
        for f in os.listdir(_SPECS_DIR)
        if f.startswith("SPEC_") and f.endswith(".md") and f != "SPEC_INDEX.md"
    )


def test_index_exists():
    """The catalog file is present."""
    assert os.path.isfile(_INDEX), f"missing spec catalog: {_INDEX}"


def test_every_spec_is_catalogued():
    """Each on-disk spec name appears somewhere in SPEC_INDEX.md."""
    with open(_INDEX, encoding="utf-8") as fh:
        index_text = fh.read()
    missing = [n for n in _spec_names() if n not in index_text]
    assert not missing, (
        "specs on disk but absent from SPEC_INDEX.md: "
        + ", ".join(missing)
        + " — add a one-line entry under the appropriate arc."
    )


def test_index_has_no_dangling_entries():
    """Every SPEC_*.md referenced in the index still exists on disk (no stale rows)."""
    import re

    with open(_INDEX, encoding="utf-8") as fh:
        index_text = fh.read()
    referenced = set(re.findall(r"SPEC_[A-Z0-9_]+", index_text))
    referenced.discard("SPEC_INDEX")
    on_disk = set(_spec_names())
    dangling = sorted(r for r in referenced if r not in on_disk)
    assert not dangling, (
        "SPEC_INDEX.md references specs that no longer exist on disk: "
        + ", ".join(dangling)
    )


if __name__ == "__main__":
    test_index_exists()
    test_every_spec_is_catalogued()
    test_index_has_no_dangling_entries()
    print("test_spec_index: OK")
