"""SPEC_GRAPHICS Phase 4 — generate the bundled `starter` tile pack (PIL only, no pygame/no game import).

The starter pack is a working, swappable TEMPLATE + proof of the atlas load path — NOT the final look. Terrain
tiles are flat palette colors with a border; entity tiles are white luminance/alpha MASKS (tinted by colony
color at render time). Drop a real openly-licensed pack (DCSS/NetHack/Kenney) over these keys to make it pop.

Run:  py310 sim/tiles/make_starter.py   ->  writes sim/tiles/starter/{atlas.png, map.json, LICENSE}
"""
import json
import os

from PIL import Image, ImageDraw

TS = 16  # tile size (px)

# Approximate voxel colors (self-contained — live_view.build_voxel_palette imports pygame, unavailable off-host).
VOXELS = {
    "SAND": (194, 178, 128), "STONE": (110, 110, 120), "GLASS": (180, 200, 210), "FOOD": (90, 200, 90),
    "CORPSE": (150, 90, 90), "TUNNEL_WALL": (90, 80, 70), "TILLED": (120, 90, 60), "CROP": (80, 160, 70),
    "CROP_RIPE": (200, 190, 70), "COPPER_ORE": (184, 115, 51), "GOLD_ORE": (220, 190, 60),
    "HULL": (120, 120, 140), "SALVAGE": (150, 150, 160), "WOOD": (110, 80, 50), "WOOD_WALL": (140, 100, 60),
    "WEB": (210, 210, 220), "CASTLE": (150, 150, 160), "WATER": (60, 110, 200), "SHRUB": (60, 130, 60),
    "SHRUB_RIPE": (170, 60, 120), "GRANARY": (170, 140, 90),
}
CASTES = ["WORKER", "SOLDIER", "SCOUT"]
BEASTS = ["spider", "scorpion", "snake", "anteater", "bird", "hornets", "rabbit", "squirrel", "rodent",
          "cricket", "ant", "fly", "small_spider", "mouse", "cat", "beetle", "bee", "guppy"]

WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)


def _terrain_tile(color):
    """Flat palette fill + a 1px darker border so cells read as discrete tiles."""
    img = Image.new("RGBA", (TS, TS), color + (255,))
    d = ImageDraw.Draw(img)
    dark = tuple(int(c * 0.6) for c in color) + (255,)
    d.rectangle([0, 0, TS - 1, TS - 1], outline=dark)
    return img


def _mask(shape):
    """A white silhouette MASK on a transparent field (tinted by colony color at render time)."""
    img = Image.new("RGBA", (TS, TS), CLEAR)
    d = ImageDraw.Draw(img)
    c, r = TS // 2, TS // 2
    if shape == "circle":       # worker
        d.ellipse([c - 5, c - 5, c + 4, c + 4], fill=WHITE)
    elif shape == "diamond":    # soldier
        d.polygon([(c, 2), (TS - 3, c), (c, TS - 3), (2, c)], fill=WHITE)
    elif shape == "triangle":   # scout
        d.polygon([(c, 2), (TS - 3, TS - 3), (2, TS - 3)], fill=WHITE)
    elif shape == "blob":       # maw (fills most of the cell)
        d.ellipse([1, 2, TS - 2, TS - 1], fill=WHITE)
    else:                        # beast: a generic critter body + two legs
        d.ellipse([c - 4, c - 3, c + 4, c + 3], fill=WHITE)
        d.line([(c - 4, c + 2), (c - 6, c + 5)], fill=WHITE, width=1)
        d.line([(c + 4, c + 2), (c + 6, c + 5)], fill=WHITE, width=1)
    return img


def build():
    keys = ([f"voxel/{n}" for n in VOXELS] + [f"unit/{c}" for c in CASTES] + ["maw"]
            + [f"beast/{s}" for s in BEASTS])
    cols = 8
    rows = (len(keys) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * TS, rows * TS), CLEAR)
    tiles = {}
    for i, key in enumerate(keys):
        col, row = i % cols, i // cols
        if key.startswith("voxel/"):
            img = _terrain_tile(VOXELS[key.split("/", 1)[1]])
        elif key.startswith("unit/"):
            img = _mask({"WORKER": "circle", "SOLDIER": "diamond", "SCOUT": "triangle"}[key.split("/", 1)[1]])
        elif key == "maw":
            img = _mask("blob")
        else:
            img = _mask("beast")
        sheet.paste(img, (col * TS, row * TS))
        tiles[key] = [col, row]

    out_dir = os.path.dirname(os.path.abspath(__file__))
    pack_dir = os.path.join(out_dir, "starter")
    os.makedirs(pack_dir, exist_ok=True)
    sheet.save(os.path.join(pack_dir, "atlas.png"))
    spec = {"tile_size": TS, "sheet": "atlas.png", "tiles": tiles,
            "tinted": ["unit/*", "maw", "beast/*"]}
    with open(os.path.join(pack_dir, "map.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    with open(os.path.join(pack_dir, "LICENSE"), "w", encoding="utf-8") as f:
        f.write("Starter tile pack — procedurally generated placeholder (public domain / CC0).\n"
                "Terrain = flat palette tiles; entities = white masks tinted by colony color.\n"
                "Replace with an openly-licensed pack (Dungeon Crawl Stone Soup tiles: public-domain-grade;\n"
                "Kenney: CC0) by overwriting atlas.png and map.json with matching keys. The repo is PUBLIC —\n"
                "bundle only openly-licensed art and keep this LICENSE current.\n")
    print(f"wrote {pack_dir}: {len(tiles)} tiles, sheet {sheet.size}")


if __name__ == "__main__":
    build()
