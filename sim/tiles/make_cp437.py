"""SPEC_GRAPHICS P4 — build the `cp437` tile pack from a 16x16 row-order (CP437) greyscale font sheet.

Source: libtcod `terminal16x16_gs_ro.png` (python-tcod repo) — a 256x256 sheet, cell index = CP437 codepoint. CP437
font sheets have OPAQUE BLACK backgrounds, so we convert luminance -> alpha (glyph pixels opaque, background
transparent) at build time; then the atlas's standard tint() colors each glyph (terrain by palette, entities by
colony). Beasts are intentionally left UNMAPPED so they fall back to the procedural bug sprites — mix-and-match.

Run:  py310 sim/tiles/make_cp437.py --src <path-to-terminal16x16_gs_ro.png>
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

# Our glyph keys -> CP437 codepoint (cell index in the 16x16 row-order grid; col = code%16, row = code//16).
CP437 = {
    "voxel/SAND": 176, "voxel/STONE": 178, "voxel/GLASS": 35, "voxel/FOOD": 7, "voxel/CORPSE": 37,
    "voxel/TUNNEL_WALL": 240, "voxel/TILLED": 126, "voxel/CROP": 59, "voxel/CROP_RIPE": 42,
    "voxel/COPPER_ORE": 156, "voxel/GOLD_ORE": 36, "voxel/HULL": 21, "voxel/SALVAGE": 38, "voxel/WOOD": 20,
    "voxel/WOOD_WALL": 124, "voxel/WEB": 197, "voxel/CASTLE": 127, "voxel/WATER": 247, "voxel/SHRUB": 5,
    "voxel/SHRUB_RIPE": 6, "voxel/GRANARY": 254,
    "unit/WORKER": 9, "unit/SOLDIER": 4, "unit/SCOUT": 30,
    "maw": 234,
    # beasts: intentionally omitted -> fall back to the procedural forge (real bug sprites)
}
TS = 16


def build(src, out_name="cp437"):
    src_rgba = np.asarray(Image.open(src).convert("RGBA"), dtype=np.float32)  # (256,256,4)
    lum = (0.299 * src_rgba[:, :, 0] + 0.587 * src_rgba[:, :, 1] + 0.114 * src_rgba[:, :, 2])  # glyph shape
    rgba = np.zeros(src_rgba.shape, dtype=np.uint8)
    rgba[:, :, 0] = rgba[:, :, 1] = rgba[:, :, 2] = np.clip(lum, 0, 255).astype(np.uint8)  # greyscale (tint() reads it)
    # Keep the source alpha when the sheet already carries transparency (Phoebus); else derive it from luminance so an
    # opaque-black-background font (libtcod) becomes glyph-on-transparent.
    if float(src_rgba[:, :, 3].std()) > 8.0:
        rgba[:, :, 3] = src_rgba[:, :, 3].astype(np.uint8)
    else:
        rgba[:, :, 3] = np.clip(lum, 0, 255).astype(np.uint8)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_name)
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, "atlas.png"))
    tiles = {k: [code % 16, code // 16] for k, code in CP437.items()}
    spec = {"tile_size": TS, "sheet": "atlas.png", "tiles": tiles,
            "tinted": ["voxel/*", "unit/*", "maw", "beast/*"]}   # greyscale -> tint everything we map
    with open(os.path.join(out_dir, "map.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    with open(os.path.join(out_dir, "LICENSE"), "w", encoding="utf-8") as f:
        f.write(f"{out_name} tile pack — a 16x16 row-order (CP437) sheet, cell = codepoint. Our GLYPHS map to CP437\n"
                "codepoints; greyscale is kept so the atlas tint() colorizes each glyph (terrain by palette, entities\n"
                "by colony). Beasts are unmapped and fall back to the game's procedural sprites.\n"
                "Sources: libtcod 'terminal16x16_gs_ro.png' (python-tcod, BSD-3-Clause, redistributable) or\n"
                "Phoebus 'Phoebus_16x16.png' (github.com/DFgraphics/Phoebus — DF community graphics set; see that\n"
                "repo's README for terms). Record the exact source you built from here.\n")
    print(f"wrote {out_dir}: {len(tiles)} tiles mapped (beasts fall back to forge)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="path to a 16x16 row-order CP437 sheet PNG (256x256)")
    ap.add_argument("--out", default="cp437", help="pack name (subdir of sim/tiles/)")
    a = ap.parse_args()
    build(a.src, a.out)
