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

## Open (Phase 3)

- **Phase 3 — Procedural top-down sprite tiles** (`RenderStyle.TILES`): extend the `iso_sprites.py` forge
  to bake representational 16×16 top-down sprites (bug/beast/maw/food/water), colony-tinted and cached —
  a soldier LOOKS like a mandibled bug, a guppy like a fish.

Note: the CryPixels 1-bit pack the user pointed at is abstract symmetric sigils (not creature icons), so
representational sprites are generated the way the ISO view already is, not loaded from that pack.
