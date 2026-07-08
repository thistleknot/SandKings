# Spec: Live Terrarium Viewer (`live_view.py`)

Layer: **Structural** (a new module) hosting one **Behavioral** block (the event loop).
Governs: `live_view.py` (new), the `--live` branch of `sandkings.main()`.
Status: draft → implement → reconcile (see Reconciliation Log at bottom).

## 1. Definitions

- :LiveViewer: — entity. Owns the pygame window, render surfaces, and loop state
  (running, paused, z_level, view_mode, overlay_index, render_style, capture
  flag, captured_frames, save_path). One instance per live run.
- :StepPacer: — entity (mutable counters). Fixed-timestep accumulator converting
  wall-clock frame deltas into an integer number of owed `sim.step()` calls.
- :SliceRenderer: — concept, realized as a family of pure module-level functions
  (`build_voxel_palette`, `slice_color_array`, `topdown_cells`,
  `topdown_color_array`, `depth_shade`, `unit_visible_depth`,
  `pheromone_overlay_array`, `storm_haze_array`, `unit_draw_color`). No pygame
  dependency in the pure parts (numpy in, numpy/tuples out).
- :HUD: — concept, realized as a pure-function family: `build_hud_entries`
  (sim state in, list of (text, color) pairs out) is the primary HUD source;
  `build_hud_lines` is its text-only projection; `hud_text_color`,
  `event_tint`, and `hp_bar` are its helpers. A pygame text-blit step inside
  :LiveViewer: consumes the entries.

## 2. Implementation Requirements

- Dependency: `pygame` (already pinned). pygame MUST be imported only inside
  `live_view.py`; `sandkings.py` imports `live_view` lazily inside its `--live`
  branch so GIF mode, `sandkings_gpu`, and `sandkings_evolution` never load pygame.
- Config: `steps_per_second` — initial sim rate, float ∈ [SPS_MIN, SPS_MAX],
  varies by CLI (`--sps`, default 5.0).
- Config: `cell_size` — pixels per voxel, int, default `DEFAULT_CELL_SIZE`;
  MUST shrink automatically so `(w*cell_size + HUD_WIDTH, h*cell_size)` fits
  MAX_WINDOW for nonstandard `--width/--height`, with a floor of 2 px per cell.
- Constant: `HUD_WIDTH = 320` (right-side panel px).
- Constant: `DEFAULT_CELL_SIZE = 12`.
- Constant: `DEFAULT_STEPS_PER_SECOND = 5.0`.
- Constant: `SPS_MIN = 0.5`, `SPS_MAX = 60.0`.
- Constant: `MAX_STEPS_PER_FRAME = 10` — UI-freeze guard.
- Constant: `MAX_WINDOW = (1600, 900)` — window size ceiling; window height
  additionally has a 400 px floor so the HUD stays readable on short worlds.
- Constant: `RETREAT_BORDER_COLOR = (255, 0, 255)`, `RETREAT_FILL_FACTOR = 0.4`.
- Constant: `TERRITORY_TINT = 0.3` — territory blend weight, matching the
  owned-air factor of the GIF renderer.
- Constant: `DEPTH_SHADE_FACTOR = 0.85`, `DEPTH_SHADE_MIN = 0.3` — R12 top-down
  shading: brightness per z-level of depth, floor so deep terrain stays legible.
- Constant: `VOID_COLOR = (10, 10, 12)` — column with no terrain down to z=0.
- Constant: `GLYPH_BG_DIM = 0.45` — background dimming under glyphs (R18b).
- Constant: `GLYPH_MIN_CELL = 8` — px; below this glyphs are illegible and
  BLOCKS is forced (R18a).
- Constant: `PHEROMONE_BRIGHTNESS = 140` — overlay additive-glow ceiling per
  channel (R17).
- Constant: `MAW_COLOR = (255, 255, 0)`.
- Constant: `HUD_BG = (12, 12, 16)`, `HUD_FG = (220, 220, 220)`.
- Constant: `EVENT_LINES = 4` — drama-feed entries shown in the HUD (R15).
- Config: `EVENT_TINTS` — event-line tint mapping for R19b, keyed on message
  substrings: "Keeper" → green, "besieges" → orange, "fallen" → red,
  "arrives" → cyan; messages matching no substring use HUD_FG.
- Palette MUST equal `Visualizer.render_z_slice` colors exactly
  (the color mapping inside `Visualizer.render_z_slice` — cited by name;
  line numbers rot): GLASS (100,100,100), STONE (50,50,50),
  SAND (194,178,128), TUNNEL_WALL (139,90,43), FOOD (0,255,0),
  CORPSE (128,0,0), AIR unowned (20,20,20), AIR owned = colony color × 0.3.
- Headless: the viewer MUST run to completion under `SDL_VIDEODRIVER=dummy`.

## 3. Functional Requirements (EARS)

- **R1** When `--live` is passed, the program MUST open a pygame window rendering
  the simulation and MUST NOT write GIF files unless frame capture is toggled on.
- **R2** When `--live` is absent, behavior MUST be the existing GIF pipeline
  unchanged; `--steps` omitted MUST default to 20 steps in GIF mode.
- **R3** When `--live` is passed with `--steps N`, the viewer MUST auto-exit
  (exit code 0) after N sim steps have executed and print `sim.get_status()`.
  When `--live` is passed without `--steps`, the viewer MUST run until the user
  quits.
- **R4** While paused, when `S` is pressed, exactly one `sim.step()` MUST execute.
- **R5** While render style is BLOCKS, while a unit's `retreating` flag is set,
  it MUST render with fill = colony color × RETREAT_FILL_FACTOR and border =
  RETREAT_BORDER_COLOR; non-retreating units use full colony color with a
  contrast border (black border if the colony color is light, white if dark;
  luminance threshold 128). See R18 for the default GLYPH rendering of units,
  where unit fills pass through `hud_text_color` for legibility on dark terrain.
- **R6** If the owed step debt in one frame exceeds MAX_STEPS_PER_FRAME, the
  pacer MUST clamp to MAX_STEPS_PER_FRAME and discard the residual accumulator
  (the UI never freezes; effective SPS degrades honestly).
- **R7** The HUD MUST show: step counter, paused state, target SPS, current
  z-slice, capture state, and per living colony: unit counts by caste, food
  stored, maw health, retreating count.
- **R8** Key bindings (one EARS clause per binding):
  - When SPACE is pressed, the viewer MUST toggle paused/resumed.
  - When `+`, `=`, `.`, or keypad-plus is pressed (unmodified), the viewer
    MUST multiply speed by 1.5, clamped to SPS_MAX.
  - When `-`, `,`, or keypad-minus is pressed (unmodified), the viewer MUST
    divide speed by 1.5, clamped to SPS_MIN.
  - When UP or DOWN is pressed, the viewer MUST change z_level by ±1,
    clamped to [0, depth−1].
  - When TAB is pressed, the viewer MUST toggle the view mode (R12).
  - While paused, when `S` is pressed, the viewer MUST execute a single
    sim step (R4).
  - When `P` is pressed, the viewer MUST cycle the pheromone overlay (R17).
  - When `R` is pressed, the viewer MUST toggle the render style (R18).
  - While `save_path` is set, when `K` is pressed, the viewer MUST save the
    terrarium (R20).
  - When `G` is pressed, the viewer MUST toggle frame capture.
  - When ESC is pressed or the window is closed, the viewer MUST quit.
- **R8a** DF-style z-navigation: comma/period WITH Shift or Ctrl held —
  i.e. `<` = z+1 (up toward surface, matching DF's `<`) and `>` = z−1 —
  MUST change z_level (clamped) and MUST NOT change speed. The modifier
  check runs before the speed branch; `event.unicode` `'<'`/`'>'` MUST also
  be honored for layouts with dedicated keys. Unmodified comma/period keep
  their R8 speed roles; UP/DOWN keep working.
- **R7a** A dead colony whose respawn is scheduled MUST show
  `DEAD (respawn in N)` in the HUD, where N is the steps remaining, read via
  a guarded `getattr(sim, 'pending_respawns', {})` so sims without the
  liveness feature still render.
- **R9** Superseded by R17.
- **R12** The viewer MUST offer two view modes toggled by TAB:
  - `TOPDOWN` (default) — Dwarf-Fortress-style: looking down the z axis
    (z is vertical: gravity moves sand z→z−1). For each (x, y) column,
    render the first non-AIR voxel at or below the current z_level, with
    brightness multiplied by `depth_shade(delta) = max(DEPTH_SHADE_MIN,
    DEPTH_SHADE_FACTOR ** delta)` where delta = z_level − found_z; columns
    with no terrain down to z=0 render VOID_COLOR. Territory: where the
    found voxel is owned, blend TERRITORY_TINT of the colony color into the
    shaded terrain color.
  - `SLICE` — the existing single-z cross-section (R5/R11 semantics).
- **R13** In TOPDOWN mode a unit (or Maw) MUST render iff its z ≤ z_level
  and every voxel strictly above it up to z_level in its column is AIR;
  its fill is depth-shaded like terrain, its border is not shaded (so
  retreat magenta and contrast borders stay readable at depth).
- **R14** UP/DOWN changes z_level in both modes (shared state, clamped to
  [0, depth−1]). Initial z_level is depth−1 in TOPDOWN (surface view),
  which also serves SLICE after a TAB switch. The HUD MUST name the
  active view mode.
- **R15** (Round B) The HUD MUST show the last EVENT_LINES (4) entries of
  `sim.events` (guarded `getattr` — sims without the feed render without it)
  as `[step] message`, most recent last.
- **R16** (Round B) A living Maw whose health < MAW_MAX_HEALTH MUST render a
  health bar directly above its marker: background dark red, foreground
  green→red proportional fill, the maw marker's width (two cells) × 3 px.
  Full-health maws show no bar (ambient calm reads clean).
- **R17** (Round B, upgrades R9 from MAY to MUST) `P` cycles a pheromone
  overlay: off → FOOD_TRAIL → TERRITORY → DANGER → off. The overlay
  alpha-blends per-cell colony-colored intensity: per cell, the maximum
  across colonies of the selected type's intensity, sampled at the current
  z-level in both view modes. HUD names the active overlay.
- **R18** (Round C — dazzle) DF-style glyph rendering:
  - **R18a** The default render style MUST be GLYPH, a DF-style character
    grid. `R` toggles GLYPH ↔ BLOCKS (the rect renderer, unchanged
    semantics). While cell_size < GLYPH_MIN_CELL, BLOCKS MUST be used
    regardless of the toggle.
  - **R18b** Each GLYPH cell draws its terrain color dimmed by GLYPH_BG_DIM
    as background and a foreground glyph from the GLYPH map (SAND `░`,
    STONE `▓`, GLASS `#`, FOOD `•`, CORPSE `%`, TUNNEL_WALL `≡`, AIR blank)
    in the full depth-shaded terrain color.
  - **R18c** Units render as letters (`w` worker, `s` soldier, `c` scout) in
    colony color, lightened via `hud_text_color` when dark; retreating units
    render their letter in RETREAT_BORDER_COLOR.
  - **R18d** The Maw renders as `Ω` in MAW_COLOR at double glyph size (the
    R16 health bar is unchanged).
  - **R18e** Glyph surfaces MUST be cached per (char, color) — the grid
    blits from cache, never re-rendering text per frame.
- **R19** (Round C) The HUD MUST be color-coded:
  - **R19a** Colony stat lines render in the colony's color, passed through
    `hud_text_color` (lightened when too dark for the panel background).
  - **R19b** Event lines are tinted per the EVENT_TINTS mapping in section 2.
  - **R19c** A damaged maw's line MUST include an ASCII text bar of its HP
    fraction, like `[====....]` — full-height block glyphs were dropped
    because they overflow the 18 px HUD line box.
  - **R19d** Pure HUD content MUST come from `build_hud_entries(...) ->
    list[(text, color)]`; `build_hud_lines` remains as its text-only
    projection (existing tests and callers stay valid).
- **R10** While capture is on, each render in which at least one sim step
  executed MUST be stored; on quit, frames save to `sandkings_live.gif`.
- **R11** While render style is BLOCKS, the Maw MUST render as a yellow
  (255,255,0) square with black border, larger than a unit, when its z matches
  the current slice. See R18 for the default GLYPH rendering of the Maw.
- **R20** While `save_path` is set: when `K` is pressed the viewer MUST
  checkpoint the sim and log "The keeper preserves the terrarium"; when the
  loop exits the viewer MUST autosave. Persistence semantics are owned by
  SPEC_TERRARIUM_LIVENESS.md T13.
- **R21** While `sim.storm_until > sim.step_count` (guarded getattr), the
  viewer MUST render a flickering sand-haze overlay (`storm_haze_array`,
  additive blend). Storm mechanics are owned by SPEC_TERRARIUM_LIVENESS.md T12.

## 4. Structural Spec

```
live_view.py
  ViewMode (enum): TOPDOWN | SLICE               # R12 view modes
  RenderStyle (enum): GLYPH | BLOCKS             # R18 render styles

  build_voxel_palette() -> np.ndarray            # (256,3) uint8 LUT
  slice_color_array(world, colonies, z) -> np.ndarray   # (w,h,3) uint8; voxel LUT + territory tint
  topdown_cells(world, z) -> (found_voxels, depth_below, has_terrain, ownership)  # pure, R12 column scan
  topdown_color_array(world, colonies, z) -> np.ndarray # (w,h,3) uint8; DF view (R12), pure
  depth_shade(delta) -> float                    # pure, R12 shading curve
  unit_visible_depth(world, position, z) -> int | None  # pure, R13 visibility
  pheromone_overlay_array(pheromones, colonies, z, ptype) -> np.ndarray  # (w,h,3) uint8 glow, R17
  storm_haze_array(shape_wh) -> np.ndarray       # (w,h,3) uint8 flicker speckle, R21
  unit_draw_color(colony_color, retreating) -> (fill, border)   # pure
  hud_text_color(color) -> color                 # pure, R19a legibility floor
  event_tint(message) -> color                   # pure, R19b substring tint
  hp_bar(fraction, width=8) -> str               # pure, R19c ASCII bar
  build_hud_entries(sim, sps, paused, z_level, capturing, view_mode, overlay)
      -> list[(text, color)]                     # pure, R19d primary HUD source
  build_hud_lines(sim, sps, paused, z_level, capturing, view_mode, overlay)
      -> list[str]                               # pure, text projection of entries

  class StepPacer:            # role: value-ish entity, no I/O
      __init__(steps_per_second)
      update(dt_ms, paused) -> int    # 0..MAX_STEPS_PER_FRAME owed steps
      faster() / slower()             # ×1.5 / ÷1.5 with clamps
      request_single_step()           # honored only while paused

  class LiveViewer:           # role: service/controller, owns pygame lifecycle
      __init__(sim, cell_size=DEFAULT_CELL_SIZE,
               steps_per_second=DEFAULT_STEPS_PER_SECOND, max_steps=None,
               save_path=None)
      run() -> None                   # blocks; pygame.init/quit bracketed
      _handle_event(event) / _render()   # internal

  run_live(sim, max_steps=None, steps_per_second=DEFAULT_STEPS_PER_SECOND,
           save_path=None) -> None   # entry point
```

`sandkings.main()` delta (only place touched): `--live` flag, `--sps` float,
`--persist [DB]` (resume from / autosave to a sqlite terrarium; enables the
K-save binding, R20), `--steps` default 20 → None with GIF fallback `None → 20`.

## 5. Behavioral Spec — event loop

```
Input: sim (SandKingsSimulation), max_steps (int | None)
Initialize: steps_done ← 0; paused ← False; z ← depth − 1; running ← True
Loop while running:
    dt ← clock.tick(60)
    drain pygame events → _handle_event  (may flip paused/running/z/sps/capture,
                                          may request single step)
    owed ← pacer.update(dt, paused)      # 0 if paused unless single-step pending
    Loop owed times:
        sim.step(); steps_done += 1
        If max_steps is not None and steps_done >= max_steps: running ← False; break
    _render()                            # slice + units + maw + HUD (+ capture)
Terminate: save capture GIF if frames were captured; autosave terrarium if
           save_path set (R20); pygame.quit()
           (sandkings.main() prints sim.get_status() after run_live returns)
Assert: max_steps is None or steps_done <= max_steps
```

Termination conditions: user quit (ESC/close) OR steps_done reaching max_steps.

## 6. Test Requirements

- Headless fixture: `os.environ.setdefault("SDL_VIDEODRIVER", "dummy")` before
  pygame import; seeded deterministic world 20×10×5.
- Acceptance (Given/When/Then):
  - Given the palette LUT, Then LUT[v] equals the `render_z_slice` color for
    every VoxelType v.
  - Given a fixture world with one owned AIR voxel, When `slice_color_array`
    runs, Then that cell equals colony color × 0.3 and shape is (w,h,3).
  - Given a retreating unit, Then `unit_draw_color` differs from the
    non-retreating result in both fill and border.
  - Given a paused pacer with one requested single step, When update runs,
    Then it returns exactly 1, and 0 on the following frame.
  - Given dt implying 50 owed steps, Then update returns MAX_STEPS_PER_FRAME.
  - Given `LiveViewer(sim, max_steps=5)` under the dummy driver, When run()
    completes, Then sim.step_count == 5 and the process did not hang.
  - Given buried and surface terrain plus one owned voxel, When the top-down
    view renders, Then buried terrain is depth-shaded, owned terrain blends
    the colony color, and bottomless columns render VOID_COLOR
    (test_topdown_first_nonair_and_depth_shading, test_topdown_territory_blend,
    test_topdown_cells_consistency).
  - Given deltas 0, 1, and 100, Then `depth_shade` returns 1.0,
    DEPTH_SHADE_FACTOR, and DEPTH_SHADE_MIN respectively (test_depth_shade_curve).
  - Given a unit below z_level, Then it is visible through an open column, and
    hidden when occluded or above the view level (test_unit_visible_depth).
  - Given Shift/Ctrl-modified comma/period keydowns, Then z_level changes
    (clamped) and speed does not, While unmodified comma/period still change
    speed only (test_df_z_keys).
  - Given a dead colony with a scheduled respawn, Then the HUD shows
    `DEAD (respawn in N)` (test_hud_respawn_countdown).
  - Given more events than EVENT_LINES, Then the HUD shows only the last
    EVENT_LINES entries, most recent last (test_hud_event_feed).
  - Given one deposited pheromone cell, Then the overlay glows there and stays
    dark elsewhere, and When `P` is pressed through the whole cycle, Then the
    overlay wraps back to off (test_pheromone_overlay_array,
    test_p_key_cycles_overlay).
  - Given the glyph maps, Then every VoxelType and every UnitType has a glyph
    and a maw glyph exists (test_glyph_map_covers_all_voxel_types).
  - Given a near-black color, Then `hud_text_color` lightens it while leaving
    already-legible colors unchanged (test_hud_text_color_lightens_dark).
  - Given a half-health maw and tagged events, Then HUD entries carry colony
    colors, event tints, and an ASCII hp bar
    (test_hud_entries_colors_and_hp_bar).
  - Given a fresh viewer, Then the render style defaults to GLYPH and `R`
    toggles to BLOCKS and back (test_r_key_toggles_render_style).

## 7. Reconciliation Log

- 2026-07-07 — Implemented as specced with three deviations/discoveries:
  1. **Module aliasing requirement (new)**: when `sandkings.py` runs as a
     script it is `__main__`; `live_view`'s `from sandkings import ...` would
     re-import a duplicate module with distinct enum classes (KeyError on
     `UnitType`). The `--live` branch MUST alias
     `sys.modules.setdefault('sandkings', sys.modules[__name__])` before
     importing `live_view`. Implemented in `sandkings.main()`.
  2. **Capture cadence**: frames are captured only on renders where at least
     one sim step executed (not every 60 FPS frame), keeping
     `sandkings_live.gif` aligned with sim time. R10 refined accordingly.
  3. **Pre-existing sim defect fixed during verification**: with
     `--num-colonies 0` (default), `SandKingsSimulation.__init__` sized the
     pheromone colony axis at 0 before `_spawn_colonies` resolved the random
     3-5 count, crashing on first deposit. Count is now resolved in
     `__init__` before `PheromoneLayer` construction (out of this spec's
     module scope, recorded here as the discovering spec).
- Acceptance verified: GIF regression (`--steps 5`), headless live 30 steps
  exit 0, neural live 120 steps exit 0, windowed 100-step auto-exit, both
  test suites green (8 + 6 tests).
- 2026-07-07 (dazzle rounds) — R15-R19 implemented: drama-feed ticker, maw
  health bars, pheromone overlay (P), DF glyph renderer as default (R
  toggles BLOCKS), color-coded HUD via `build_hud_entries` with
  `build_hud_lines` retained as its text projection. Deviation: unit glyph
  colors pass through `hud_text_color` so black-colony units stay legible
  on dark terrain (extends the R18 "black units lightened" clause to all
  dark fills). Verified by 22 viewer tests + captured frames
  (sandkings_live.gif).
- 2026-07-07 (later) — R12-R14 (Dwarf-Fortress-style TOPDOWN view) added per
  user request and implemented: `topdown_color_array` / `depth_shade` /
  `unit_visible_depth` pure functions, `ViewMode` enum, TAB toggle, entity
  depth shading with unshaded borders, initial z_level moved to depth−1
  (surface). `build_hud_lines` gained a `view_mode` parameter (defaulted, so
  prior callers remain valid). Verified: 12 viewer tests green, headless and
  windowed runs exit 0, real-terrain render shows 10 distinct brightness
  levels at surface view and visible tunnel pits at mid-level.
- 2026-07-08 — Spec one-over repair: R5/R9/R10/R11/R16/R17 corrected, R18/R19
  split into sub-clauses, R20/R21 added for the persistence and storm-haze
  surfaces, sections 1/2/4/5/6 reconciled with the implemented module;
  historical test counts in older entries are per-round snapshots.
