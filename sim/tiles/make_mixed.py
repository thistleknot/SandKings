"""SPEC_GRAPHICS P4 — compose the `mixed` pack: borrow from BOTH traditions. Terrain from the Phoebus DF set
(greyscale CP437 tiles, palette-tinted); creatures from rltiles (the NetHack/Crawl roguelike tile lineage,
32x32, resized to 16), colored as-is. Units/maw fall back to the procedural colony-tinted forge (house identity).

Sources:
  Phoebus_16x16.png  — github.com/DFgraphics/Phoebus (DF community set)
  rltiles-2d.png + rltiles-2d.json — github.com/statico/rltiles (RL Tiles; NetHack + Crawl 2D tiles, name index)

Run:  py310 sim/tiles/make_mixed.py --tiles PHOEBUS_16x16.png --rl rltiles-2d.png --rljson rltiles-2d.json
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

VOXEL_CP = {
    "voxel/SAND": 176, "voxel/STONE": 178, "voxel/GLASS": 35, "voxel/FOOD": 7, "voxel/CORPSE": 37,
    "voxel/TUNNEL_WALL": 240, "voxel/TILLED": 126, "voxel/CROP": 59, "voxel/CROP_RIPE": 42,
    "voxel/COPPER_ORE": 156, "voxel/GOLD_ORE": 36, "voxel/HULL": 21, "voxel/SALVAGE": 38, "voxel/WOOD": 20,
    "voxel/WOOD_WALL": 124, "voxel/WEB": 197, "voxel/CASTLE": 127, "voxel/WATER": 247, "voxel/SHRUB": 5,
    "voxel/SHRUB_RIPE": 6, "voxel/GRANARY": 254,
}
# our beast species -> rltiles tile NAME (resolved to an index via the JSON). NetHack/Crawl lineage art.
BEAST_RL = {
    "beast/spider": "giant_spider", "beast/small_spider": "cave_spider", "beast/scorpion": "scorpion",
    "beast/snake": "black_snake", "beast/rodent": "sewer_rat", "beast/mouse": "green_rat",
    "beast/cat": "housecat", "beast/beetle": "boring_beetle", "beast/bee": "red_wasp",
    "beast/hornets": "red_wasp", "beast/fly": "butterfly", "beast/guppy": "giant_goldfish",
}


def build(tiles_png, rl_png, rl_json, ts=16):
    phoebus = Image.open(tiles_png).convert("RGBA")          # 16px CP437 greyscale terrain
    rl_img = Image.open(rl_png).convert("RGBA")              # 32px rltiles creatures
    meta = json.load(open(rl_json, encoding="utf-8"))
    rts, rw, names = int(meta["tileSize"]), int(meta["width"]), meta["tiles"]
    idx = {n: i for i, n in enumerate(names)}

    def _extract(img, src_ts, col, row, resample):
        cell = img.crop((col * src_ts, row * src_ts, col * src_ts + src_ts, row * src_ts + src_ts))
        if src_ts != ts:
            cell = cell.resize((ts, ts), resample)          # terrain 16->ts NEAREST (crisp pixels); creatures 32->ts LANCZOS
        return np.ascontiguousarray(np.asarray(cell, dtype=np.uint8))

    cells = {}
    for key, code in VOXEL_CP.items():
        cells[key] = _extract(phoebus, 16, code % 16, code // 16, Image.NEAREST)  # greyscale terrain (tinted)
    for key, name in BEAST_RL.items():
        if name not in idx:
            continue
        i = idx[name]
        arr = _extract(rl_img, rts, i % rw, i // rw, Image.LANCZOS)
        if int(arr[:, :, 3].max()) > 0:
            cells[key] = arr

    keys = list(cells.keys())
    cols = 8
    rows = (len(keys) + cols - 1) // cols
    atlas = np.zeros((rows * ts, cols * ts, 4), dtype=np.uint8)
    tiles = {}
    for i, key in enumerate(keys):
        c, r = i % cols, i // cols
        atlas[r * ts:(r + 1) * ts, c * ts:(c + 1) * ts, :] = cells[key]
        tiles[key] = [c, r]

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mixed")
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(atlas, "RGBA").save(os.path.join(out_dir, "atlas.png"))
    spec = {"tile_size": ts, "sheet": "atlas.png", "tiles": tiles, "tinted": ["voxel/*"]}
    with open(os.path.join(out_dir, "map.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    with open(os.path.join(out_dir, "LICENSE"), "w", encoding="utf-8") as f:
        f.write("mixed tile pack — borrows from BOTH traditions:\n"
                "  terrain: Phoebus DF set, data/art/Phoebus_16x16.png (github.com/DFgraphics/Phoebus)\n"
                "  creatures: rltiles, rltiles-2d.png (github.com/statico/rltiles — RL Tiles, NetHack + Crawl 2D\n"
                "    tiles), resized 32->16, colored as-is. See each source repo for terms.\n"
                "Units/maw and unmatched beasts fall back to the game's procedural colony-tinted sprites.\n")
    beasts = [k for k in tiles if k.startswith("beast/")]
    print(f"wrote {out_dir}: {len(tiles)} tiles ({len(beasts)} NetHack beasts: {[b.split('/')[1] for b in beasts]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", required=True)
    ap.add_argument("--rl", required=True)
    ap.add_argument("--rljson", required=True)
    ap.add_argument("--ts", type=int, default=16, help="output tile size (e.g. 24 for mid-range)")
    a = ap.parse_args()
    build(a.tiles, a.rl, a.rljson, a.ts)
