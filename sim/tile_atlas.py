"""SPEC_GRAPHICS Phase 4 — the image-atlas TILESET core (pure, pygame-free).

Loads a mix-and-match image tile pack (Dwarf Fortress / NetHack / Dungeon Crawl style) as a keyed set of RGBA
tiles, with per-key resolution so any tile the pack omits falls back to the procedural forge (P3) then the glyph
(P1). Deliberately depends only on PIL + numpy (NOT pygame) so it loads and unit-tests without a display; the
pygame Surface conversion lives in live_view.py. The load path never raises into the render loop — a missing or
malformed pack returns None and the caller keeps the procedural view.

Pack layout (a directory):
    map.json   {"tile_size": 16, "sheet": "atlas.png",
                "tiles": {"<key>": [col, row], ...},
                "tinted": ["unit/*", "maw", "beast/*"]}
    atlas.png  the spritesheet (tile_size x tile_size cells)
    LICENSE    source + license of the pack (the repo is public: openly-licensed packs only)

Keys are category-prefixed: voxel/<NAME> (the GLYPHS voxels), unit/<CASTE>, maw, beast/<species>, and the
hazard/pond/sign/carving keys. `tinted` keys are luminance/alpha masks multiplied by the entity color.
"""
import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from PIL import Image
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False


def _matches(key: str, patterns: List[str]) -> bool:
    """True if key matches any pattern; a trailing '*' is a prefix wildcard, else exact match."""
    for p in patterns:
        if p.endswith("*"):
            if key.startswith(p[:-1]):
                return True
        elif key == p:
            return True
    return False


class TileAtlas:
    """A loaded image tile pack: key -> RGBA tile (np.uint8 (ts, ts, 4)), plus the tinted-key patterns.

    Require:  constructed via TileAtlas.load(pack_dir) — do not build directly.
    Guarantee: .tile(key) returns an (ts, ts, 4) uint8 array or None (fallback); never raises. .is_tinted(key)
               reports whether the key is a color mask. Immutable after load.
    """

    def __init__(self, tile_size: int, tiles: Dict[str, np.ndarray], tinted: List[str]):
        self.tile_size = int(tile_size)
        self._tiles = tiles
        self._tinted = list(tinted)

    @classmethod
    def load(cls, pack_dir: Optional[str]) -> Optional["TileAtlas"]:
        """Load a pack directory into a TileAtlas, or return None (keep the procedural view) if the pack is
        absent, PIL is unavailable, or map.json/the sheet is malformed. NEVER raises — a bad pack must not break
        the renderer; it just means no image tiles.

        Failure modes (all -> None, not an exception): pack_dir None/missing; PIL missing; map.json missing or
        unparseable; sheet missing; a tile rect out of the sheet's bounds.
        """
        if not pack_dir or not _HAVE_PIL:
            return None
        map_path = os.path.join(pack_dir, "map.json")
        if not os.path.isfile(map_path):
            return None
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                spec = json.load(f)
            ts = int(spec["tile_size"])
            sheet_path = os.path.join(pack_dir, spec.get("sheet", "atlas.png"))
            sheet = np.asarray(Image.open(sheet_path).convert("RGBA"), dtype=np.uint8)  # (H, W, 4)
            sh, sw = sheet.shape[0], sheet.shape[1]
            tiles: Dict[str, np.ndarray] = {}
            for key, (col, row) in spec.get("tiles", {}).items():
                y0, x0 = int(row) * ts, int(col) * ts
                if y0 + ts > sh or x0 + ts > sw:
                    continue  # skip an out-of-bounds cell rather than fail the whole pack
                tiles[key] = np.ascontiguousarray(sheet[y0:y0 + ts, x0:x0 + ts, :])
            if not tiles:
                return None
            return cls(ts, tiles, list(spec.get("tinted", [])))
        except Exception:
            return None  # malformed pack -> keep the procedural view

    def tile(self, key: str) -> Optional[np.ndarray]:
        """The RGBA tile for a key, or None if the pack does not define it (the mix-and-match fallback seam)."""
        return self._tiles.get(key)

    def has(self, key: str) -> bool:
        return key in self._tiles

    def is_tinted(self, key: str) -> bool:
        """Whether this key is a color MASK (entity, colored by colony) vs a fixed-color terrain tile."""
        return _matches(key, self._tinted)

    @staticmethod
    def tint(rgba: np.ndarray, color: Tuple[int, int, int]) -> np.ndarray:
        """Multiply a luminance/alpha MASK tile by an entity color, preserving alpha. Mirrors forge_bug(caste,
        tint): a white mask pixel becomes `color`, a black/transparent pixel stays dark/transparent.

        Require:  rgba is (H, W, 4) uint8; color is an (r, g, b) triple in 0..255.
        Guarantee: returns (H, W, 4) uint8; alpha channel is unchanged; RGB = (luminance/255) * color. Pure.
        """
        rgb = rgba[:, :, :3].astype(np.float32)
        lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) / 255.0
        col = np.asarray(color, dtype=np.float32)
        out = np.empty_like(rgba)
        out[:, :, :3] = np.clip(lum[:, :, None] * col[None, None, :], 0, 255).astype(np.uint8)
        out[:, :, 3] = rgba[:, :, 3]
        return out
