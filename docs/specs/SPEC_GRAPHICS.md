# SPEC — Terrarium graphics (legibility redesign)

Status: Phase 1 SHIPPED (2026-07-14). Live-view rendering only (`live_view.py` + `iso_sprites.py`);
no gameplay logic — the regression battery is unaffected.

## Why

The top-down glyph view was hard to parse: units were the letters `w/s/c`, wild beasts were
`r/q/v/n/t/S/A/z`, and glyphs collided (`x` = web AND spider; `s` soldier vs `S` snake). Letters were a
"good enough early decision"; the eye couldn't tell what was what. Goal: **storytelling-with-data /
Gestalt legibility** — distinctive glyphs, pre-attentive attributes (color, bold, underline, a reserved
blink) carrying the visual hierarchy, a toggleable sidebar legend, and procedural representational tiles.

## Phase 1 — Distinctive glyphs + Gestalt attributes (SHIPPED)

- **Font**: the map glyph fonts now load the real **DejaVu Sans Mono** (via matplotlib's bundled
  `DejaVuSansMono.ttf` — full unicode; `match_font` found only a partial fallback on Windows), with a
  Consolas fallback. `_load_fonts()` builds bold cell/maw fonts + an **underlined** cell variant.
- **Glyphs** (`UNIT_GLYPHS`/`BEAST_GLYPHS`/`GLYPHS`): units are solid shape-distinct silhouettes —
  worker `●`, soldier `◆`, scout `▲` (circle/diamond/triangle) — far clearer than `w/s/c`. Beasts each
  get a distinct glyph (spider `Ж`, scorpion `‡`, snake `§`, anteater `▼`, bird `⌃`, hornets `∴`, rabbit
  `∩`, squirrel `∪`, rodent `◦`); collisions resolved (web `╳`, castle `Π`). All confirmed rendered (no
  tofu) by a headless glyph-sheet.
- **Figure-ground**: terrain glyphs are muted (`TERRAIN_GLYPH_DIM`) to "ground" so bright, bold creatures
  read as "figure".
- **Pre-attentive attributes** (the storytelling): beasts colored by **danger class** (predator = warm
  red `PREDATOR_COLOR`, neutral = grey-green `NEUTRAL_BEAST_COLOR`); a maw **under siege** (`hp_frac<1`)
  **pulses red** (`_blink_on`, reserved for this rare urgent alert); **thralls** (`laboring_for>=0`) are
  **underlined**; existing color semantics kept (retreat magenta, envoy gold, armor copper, food green,
  water blue). The legend (`build_legend_entries`, auto-enumerated from the glyph dicts) is updated to
  read the new scheme.
- Verified: headless frame renders (SDL-dummy → PNG) show terrain receding and creatures popping; the
  `test_live_view` suite + full battery green (the hornets-glyph test updated to `∴`).

## Phase 2 — Toggleable sidebar legend (SHIPPED)

`L` no longer takes over the map. The legend is now an opaque **sidebar strip** (`LEGEND_SIDEBAR_W`,
`_draw_legend_sidebar`) drawn over the map's LEFT edge *after* the map, so the terrarium stays visible on
the right. It shows a **condensed** legend (`build_legend_compact`: creatures with danger colors, key
terrain, the reading key) in a single compact column (`legend_layout`, 11px font). The full
`build_legend_entries` is retained (tests + future use).

## Phase 3 — Procedural top-down sprite tiles (`RenderStyle.TILES`) — SHIPPED

A third render style (`R` now cycles GLYPH → BLOCKS → TILES) that draws **procedural creature sprites**
instead of glyphs: terrain is a clean full-color fill and each unit/maw/beast is a forged sprite (`_sprite`
→ `iso_sprites.forge_bug`/`forge_maw`/`forge_beast`, blitted centered, colony-tinted, internally cached).
The existing ISO forge already draws top-down-ish creatures (segmented body + legs, a maw-mound), so
TILES **reuses it directly** — a soldier looks like a mandibled bug, a spider like a spider. Gated on
`cell >= GLYPH_MIN_CELL` like glyphs. The maw-siege pulse carries through (the sprite tint is the pulse
color). Verified: a headless TILES frame shows creature sprites over color terrain; suite + battery green.

Note: the CryPixels 1-bit pack the user pointed at is abstract symmetric sigils (not creature icons), so
representational sprites are generated the way the ISO view already is, not loaded from that pack.

## All three phases shipped
Distinctive glyphs + Gestalt attributes (P1), toggleable sidebar legend (P2), procedural top-down sprite
tiles (P3). `R` cycles GLYPH/BLOCKS/TILES; `TAB` cycles TOPDOWN/SLICE/ISO; `L` toggles the sidebar legend.

## Phase 4 — Image-atlas TILESET (opt-in, mix-and-match, procedural fallback)

Revisits the P3 note ("representational sprites are generated ... not loaded from a pack"): P4 ADDS the ability
to load a real image tile pack (Dwarf Fortress / NetHack / Dungeon Crawl style — "rip and mix" from openly
licensed sets) as a fourth render style `RenderStyle.TILESET`, WITHOUT removing the procedural forge — the forge
(P3) becomes the **per-tile fallback**, so a partial/mixed pack always renders. The image path is **opt-in
(`--tileset[=PATH]`); with no flag the atlas is None and every existing view is byte-identical.**

### P4.1 — The atlas (pure, pygame-free core: `sim/tile_atlas.py`)
- `TileAtlas.load(pack_dir) -> TileAtlas | None`: reads `pack_dir/map.json` + the referenced sheet PNG (via
  **PIL**, not pygame — so the core loads/tests without a display). Returns None (→ caller keeps procedural) if
  the pack is absent or malformed (never raises into the render loop).
- `map.json` schema: `{ "tile_size": 16, "sheet": "atlas.png", "tiles": { "<key>": [col, row], ... },
  "tinted": ["unit/*", "maw", "beast/*"] }`. Keys are category-prefixed:
  `voxel/<NAME>` (the 22 `GLYPHS` voxels), `unit/<CASTE>` (WORKER/SOLDIER/SCOUT), `maw`, `beast/<species>`
  (the 18 `BEAST_GLYPHS`), and the hazard/pond/sign/carving keys — the full P-map enumeration.
- `tile(key) -> np.ndarray(H,W,4) | None`: the RGBA cell for a key, or None → **fallback** (caller uses the
  procedural forge, then the glyph). Missing keys are the mix-and-match seam.
- `tint(rgba, color) -> np.ndarray`: for `tinted` keys, treat the tile as a luminance/alpha **mask** and multiply
  by the entity color (colony `Colony.color`), preserving alpha — mirrors `forge_bug(caste, tint)`. Terrain
  tiles are used as-is (fixed color). Pure numpy; unit-tested on the host.

### P4.2 — The pygame adapter (`live_view.py`, additive + inert-by-default)
- `LiveViewer.__init__` gains a `tileset` path arg; `self.tile_atlas = TileAtlas.load(path)` (None if unset/failed).
  Stored beside the other view state (`:1273-1296`).
- `_sprite(kind, arg, tint, tw)` (`:1632`) checks the atlas FIRST — `voxel/`… no; for entities `unit/<caste>` /
  `maw` / `beast/<species>` → if `self.tile_atlas` and the key resolves, convert the tinted RGBA tile to a cached
  pygame Surface (scaled to `tw`) and return it; else the existing forge. One small `_atlas_surface()` helper is
  the only new pygame code path.
- Terrain: a `TILESET`-mode loop blits `voxel/<NAME>` atlas tiles per cell where present, OVER the flat P3 color
  fill (missing terrain tile → the flat color shows through — graceful).
- `RenderStyle` gains `TILESET`; the `R` cycle includes it ONLY when `self.tile_atlas is not None`
  (`GLYPH→BLOCKS→TILES→TILESET→GLYPH`), so a build with no pack behaves exactly as today.
- All atlas ops are guarded (a bad tile degrades to forge/glyph, never crashes the render loop).

### P4.3 — Assets + licensing
- A bundled **starter pack** `sim/tiles/starter/` (generated by `sim/tiles/make_starter.py` from the voxel
  palette + simple silhouettes) ships as a working, swappable template + proof of the load path.
- A bundled **cp437 pack** `sim/tiles/cp437/` (generated by `sim/tiles/make_cp437.py` from libtcod's CC0
  `terminal16x16_gs_ro.png`, a 16x16 row-order CP437 sheet, cell = codepoint): our GLYPHS/units/maw map to their
  CP437 codepoints; **luminance is converted to alpha** at build time (CP437 fonts have opaque black backgrounds)
  so glyphs sit transparent; **beasts are intentionally unmapped** and fall back to the procedural bug sprites —
  a live demonstration of mix-and-match. Renders as a crisp, colorized DF-style bitmap-glyph tileset.
- A bundled **phoebus pack** `sim/tiles/phoebus/` (composed by `sim/tiles/make_phoebus.py` from the Phoebus DF
  graphics set, github.com/DFgraphics/Phoebus): **representational drawn thumbnails** — terrain from
  `Phoebus_16x16.png` (greyscale CP437 tiles, palette-tinted) + beast sprites from `nwkohaku/{bugs,birds}.png`
  (colored, as-is, mapped via the `graphics_*.txt` manifests: spider/scorpion/cricket/fly/hornets/bird).
  **Units/maw and unmatched beasts fall back to the procedural forge** — the only renderer that colony-tints, so
  house identity survives (colored sprites can't be tinted). This is the "actual thumbnails, not glyphs" look.
- A bundled **mixed pack** `sim/tiles/mixed/` (composed by `sim/tiles/make_mixed.py`) — **borrows from BOTH
  traditions**: terrain from the Phoebus DF set + creature sprites from **rltiles** (github.com/statico/rltiles —
  the NetHack/Crawl 2D tile lineage, 32x32 resized to 16, matched by its JSON name index: spider/scorpion/snake/
  rat/cat/beetle/wasp/goldfish→guppy, 12 beasts). Units/maw → forge. This is the reference answer to "mix DF +
  NetHack."
- **`--tileset` starts in TILESET mode** (P4.2): when a pack loads, `LiveViewer.__init__` sets
  `render_style = RenderStyle.TILESET` so the tiles show immediately; `R` still cycles back to GLYPH/BLOCKS/TILES.
- **Mid-range cell size** (P4.6): the `mixed` pack ships at a **24px** native tile size (rltiles 32→24 LANCZOS,
  Phoebus 16→24 NEAREST) — the sweet spot between soft 16 and heavy 32. `--cell PX` sets the on-screen cell size
  (defaults to **24 when a `--tileset` is used**, else 12); `MAX_WINDOW` was raised to 1920×1080 so a wide world
  (≥64 cells) still fits at 24px. Verified: a 64×40 world renders at cell 24 in TILESET mode.
- **Terrain tinting (P4.2 refinement):** the terrain loop passes the per-cell palette color as the tint; the pack's
  `tinted` list decides whether it applies — a GREYSCALE font pack (cp437: `voxel/*` tinted) is colorized by
  terrain color, while a PRE-COLORED representational pack (starter: `voxel/*` not tinted) is used as-is.
- The repo is PUBLIC, so any pack must be openly licensed (DCSS tiles are public-domain-grade; Kenney is CC0;
  libtcod fonts are BSD-redistributable); each pack records its source + license in `pack_dir/LICENSE`.

### P4.4 — Awakening hook (stub, not wired)
- One documented seam for a later arc (SPEC_AFFORDANCES successor): force `RenderStyle.GLYPH` when a colony
  reaches the Shade stage — "the tiles glitch back to ASCII as the maw wakes." Documented here, not implemented.

**Acceptance P4** (`tests/test_tile_atlas.py`, host-runnable — no pygame/display):
- `TileAtlas.load` on a generated pack resolves every mapped key to an `(H,W,4)` array of `tile_size`; an
  unmapped key returns None (fallback); a missing/malformed pack dir returns None (no raise).
- `tint(mask, color)` scales a mask by the color and preserves alpha (a black-alpha pixel stays transparent; a
  white mask pixel becomes `color`).
- The bundled `sim/tiles/starter/` pack loads and covers the terrain + unit + maw keys.
- View-layer only: `run_tests.py` battery is unaffected (the sim never runs in the renderer).
- **Verified on-host** with the venv interpreter `C:\Users\user\py310\Scripts\python.exe` (pygame 2.6.1):
  headless SDL-dummy renders of GLYPH/TILES/TILESET all succeed for both the `starter` and `cp437` packs; the
  `cp437` pack renders as a colorized CP437 tileset with beasts falling back to the forge; full battery 74/0.
  Interactive `R`-toggle / on-screen check is the user's in a real window.

## Headless GIF frames (Phase H) — fixed views, no 3D

Governing intent (user): the matplotlib 3D frame is not useful ("I'm not sure a 3d frame is useful here") and
adaptive/averaged composites are noisy without a model to read them; keep it "simple like a top-level view,
and maybe a few views under ground." Fixed viewpoints keep frames comparable step-to-step, so change reads as
motion.

- The headless (GIF-mode) frame is a horizontal tile of FOUR fixed views, every step:
  1. **Top-down surface** — for each (x, y) column, the topmost non-AIR voxel's color (z scanned from
     depth-1 down); all units and maws overdrawn regardless of depth (the "where is everyone" view).
  2-4. **Underground slices** at fixed z = int(d*0.6) (shallow), int(d*0.4) (mid), substrate+1 (deep) —
     the existing `render_z_slice`, unchanged.
- The matplotlib 3D path (`generate_3d_frame`, `sandkings_3d.gif`) is REMOVED from the headless loop — it was
  ~all of the per-step wall clock and unreadable (occlusion). The single output is `sandkings_2d.gif`.
- Voxel color mapping is one shared table (`Visualizer._voxel_color`) used by both the slice and top-down
  renderers — no palette forks.

**Acceptance H.** A headless N-step run emits N tiled frames and saves only `sandkings_2d.gif`; wall-clock per
step is dominated by the sim, not the render; the frame width equals 4 view widths + separators.
