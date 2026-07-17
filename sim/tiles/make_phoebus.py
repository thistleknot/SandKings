"""SPEC_GRAPHICS P4 — compose the `phoebus` pack: Phoebus terrain tiles (greyscale, tinted by palette) + Phoebus
creature sprites for beasts (colored, as-is). Units/maw and unmatched beasts are omitted -> they fall back to the
procedural forge (which draws colony-tinted bugs, the only renderer that preserves house identity).

Sources (github.com/DFgraphics/Phoebus, a DF community graphics set — see that repo's README for terms):
  data/art/Phoebus_16x16.png            — 16x16 CP437 terrain tiles (greyscale+alpha)
  raw/graphics/nwkohaku/bugs.png+birds.png — creature sprites (nwkohaku), mapped by their graphics_*.txt

Run:  py310 sim/tiles/make_phoebus.py --tiles PHOEBUS_16x16.png --bugs bugs.png --birds birds.png
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

TS = 16
# terrain glyph -> CP437 codepoint (cell = codepoint in the 16-wide grid)
VOXEL_CP = {
    "voxel/SAND": 176, "voxel/STONE": 178, "voxel/GLASS": 35, "voxel/FOOD": 7, "voxel/CORPSE": 37,
    "voxel/TUNNEL_WALL": 240, "voxel/TILLED": 126, "voxel/CROP": 59, "voxel/CROP_RIPE": 42,
    "voxel/COPPER_ORE": 156, "voxel/GOLD_ORE": 36, "voxel/HULL": 21, "voxel/SALVAGE": 38, "voxel/WOOD": 20,
    "voxel/WOOD_WALL": 124, "voxel/WEB": 197, "voxel/CASTLE": 127, "voxel/WATER": 247, "voxel/SHRUB": 5,
    "voxel/SHRUB_RIPE": 6, "voxel/GRANARY": 254,
}
# our beast species -> (source sheet, col, row) in the Phoebus creature sheets. Unmatched species -> forge.
BEAST_SRC = {
    "beast/spider": ("bugs", 12, 0),        # giant jumping spider
    "beast/small_spider": ("bugs", 12, 0),
    "beast/scorpion": ("bugs", 4, 1),       # bark scorpion
    "beast/cricket": ("bugs", 3, 1),        # grasshopper
    "beast/fly": ("bugs", 0, 1),            # mosquito
    "beast/hornets": ("bugs", 1, 1),        # damselfly (flying)
    "beast/bird": ("birds", 0, 4),          # sparrow
}


def _cell(sheet, col, row):
    """Extract a TSxTS RGBA cell (col,row) from a sheet array, or None if out of bounds."""
    y0, x0 = row * TS, col * TS
    if y0 + TS > sheet.shape[0] or x0 + TS > sheet.shape[1]:
        return None
    return np.ascontiguousarray(sheet[y0:y0 + TS, x0:x0 + TS, :])


def build(tiles_png, bugs_png, birds_png):
    phoebus = np.asarray(Image.open(tiles_png).convert("RGBA"), dtype=np.uint8)   # greyscale+alpha terrain
    srcs = {"bugs": np.asarray(Image.open(bugs_png).convert("RGBA"), dtype=np.uint8),
            "birds": np.asarray(Image.open(birds_png).convert("RGBA"), dtype=np.uint8)}

    cells = {}   # key -> RGBA (TS,TS,4)
    for key, code in VOXEL_CP.items():
        cells[key] = _cell(phoebus, code % 16, code // 16)   # greyscale terrain glyph (tinted at render)
    for key, (sheet, col, row) in BEAST_SRC.items():
        c = _cell(srcs[sheet], col, row)
        if c is not None and int(c[:, :, 3].max()) > 0:      # skip empty cells
            cells[key] = c

    keys = [k for k, v in cells.items() if v is not None]
    cols = 8
    rows = (len(keys) + cols - 1) // cols
    atlas = np.zeros((rows * TS, cols * TS, 4), dtype=np.uint8)
    tiles = {}
    for i, key in enumerate(keys):
        c, r = i % cols, i // cols
        atlas[r * TS:(r + 1) * TS, c * TS:(c + 1) * TS, :] = cells[key]
        tiles[key] = [c, r]

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phoebus")
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(atlas, "RGBA").save(os.path.join(out_dir, "atlas.png"))
    spec = {"tile_size": TS, "sheet": "atlas.png", "tiles": tiles,
            "tinted": ["voxel/*"]}   # terrain greyscale -> palette-tinted; beasts are colored as-is
    with open(os.path.join(out_dir, "map.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    with open(os.path.join(out_dir, "LICENSE"), "w", encoding="utf-8") as f:
        f.write("phoebus tile pack — composed from the Phoebus DF graphics set (github.com/DFgraphics/Phoebus):\n"
                "terrain = data/art/Phoebus_16x16.png (greyscale CP437 tiles, palette-tinted at render); beast\n"
                "sprites = raw/graphics/nwkohaku/{bugs,birds}.png (colored, as-is). See the Phoebus repo README for\n"
                "terms. Units/maw and unmatched beasts fall back to the game's procedural colony-tinted sprites.\n")
    beasts = [k for k in tiles if k.startswith('beast/')]
    print(f"wrote {out_dir}: {len(tiles)} tiles ({len(beasts)} beast sprites: {beasts}); units/maw -> forge")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", required=True)
    ap.add_argument("--bugs", required=True)
    ap.add_argument("--birds", required=True)
    a = ap.parse_args()
    build(a.tiles, a.bugs, a.birds)
