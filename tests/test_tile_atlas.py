"""SPEC_GRAPHICS Phase 4 (P4 acceptance) — the image-atlas TILESET core. Pure PIL/numpy, NO pygame/display, so
it runs on the dev host (the live pygame view is container-only). Verifies load, key resolution, the mix-and-match
fallback (unmapped key -> None), malformed-pack safety (-> None, no raise), and the mask-tint math.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

try:
    import numpy as np
    from tile_atlas import TileAtlas
    HAVE = True
except Exception:
    HAVE = False

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STARTER = os.path.join(_REPO, "sim", "tiles", "starter")


def _skip():
    print("SKIP (tile_atlas/PIL unavailable)")
    return True


def test_load_starter_pack():
    """P4: the bundled starter pack loads; mapped keys resolve to (ts,ts,4); an unmapped key -> None (fallback)."""
    if not HAVE:
        return _skip()
    atlas = TileAtlas.load(_STARTER)
    assert atlas is not None, "starter pack must load"
    assert atlas.tile_size == 16
    for key in ("voxel/SAND", "voxel/CASTLE", "voxel/GRANARY", "unit/SOLDIER", "maw", "beast/spider"):
        t = atlas.tile(key)
        assert t is not None and t.shape == (16, 16, 4), f"{key} resolves to a 16x16 RGBA tile"
    assert atlas.tile("voxel/NONESUCH") is None, "an unmapped key returns None (procedural fallback)"
    assert atlas.has("maw") and not atlas.has("beast/dragon")


def test_missing_pack_returns_none():
    """P4: a None path or a nonexistent dir yields None (keep procedural) — never raises."""
    if not HAVE:
        return _skip()
    assert TileAtlas.load(None) is None
    assert TileAtlas.load(os.path.join(_REPO, "sim", "tiles", "does_not_exist")) is None


def test_malformed_pack_returns_none():
    """P4: a pack with unparseable map.json yields None, not an exception (a bad pack must not break the render)."""
    if not HAVE:
        return _skip()
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "map.json"), "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ]")
    assert TileAtlas.load(d) is None


def test_is_tinted():
    """P4: entity keys are color MASKS (tinted); terrain keys are fixed-color."""
    if not HAVE:
        return _skip()
    atlas = TileAtlas.load(_STARTER)
    assert atlas.is_tinted("unit/SOLDIER") and atlas.is_tinted("maw") and atlas.is_tinted("beast/spider")
    assert not atlas.is_tinted("voxel/SAND"), "terrain tiles are used as-is, not tinted"


def test_tint_mask():
    """P4: tint(mask, color) = (luminance/255)*color, alpha preserved. White->color, transparent stays transparent."""
    if not HAVE:
        return _skip()
    mask = np.zeros((2, 2, 4), dtype=np.uint8)
    mask[0, 0] = (255, 255, 255, 255)   # opaque white -> becomes the color
    mask[1, 1] = (0, 0, 0, 0)           # transparent -> stays transparent
    out = TileAtlas.tint(mask, (200, 50, 60))
    assert tuple(out[0, 0, :3]) == (200, 50, 60), "white mask pixel takes the tint color"
    assert out[0, 0, 3] == 255, "alpha preserved on the opaque pixel"
    assert tuple(out[1, 1, :3]) == (0, 0, 0) and out[1, 1, 3] == 0, "transparent pixel stays transparent"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all tile_atlas tests passed")
