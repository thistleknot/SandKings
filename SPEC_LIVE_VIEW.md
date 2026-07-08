# Spec: Live Terrarium Viewer (`live_view.py`)

Layer: **Structural** (a new module) hosting one **Behavioral** block (the event loop).
Governs: `live_view.py` (new), the `--live` branch of `sandkings.main()`.
Status: draft → implement → reconcile (see Reconciliation Log at bottom).

## 1. Definitions

- :LiveViewer: — entity. Owns the pygame window, render surfaces, and loop state
  (running, paused, z_level, capture flag). One instance per live run.
- :StepPacer: — entity (mutable counters). Fixed-timestep accumulator converting
  wall-clock frame deltas into an integer number of owed `sim.step()` calls.
- :SliceRenderer: — concept, realized as pure module-level functions
  (`build_voxel_palette`, `slice_color_array`, `unit_draw_color`). No pygame
  dependency in the pure parts (numpy in, numpy/tuples out).
- :HUD: — concept, realized as pure `build_hud_lines` (sim state in, list[str] out)
  plus a pygame text-blit step inside :LiveViewer:.

## 2. Implementation Requirements

- Dependency: `pygame` (already pinned). pygame MUST be imported only inside
  `live_view.py`; `sandkings.py` imports `live_view` lazily inside its `--live`
  branch so GIF mode, `sandkings_gpu`, and `sandkings_evolution` never load pygame.
- Config: `steps_per_second` — initial sim rate, float ∈ [SPS_MIN, SPS_MAX],
  varies by CLI (`--sps`, default 5.0).
- Config: `cell_size` — pixels per voxel, int, default `DEFAULT_CELL_SIZE`;
  MUST shrink automatically so `(w*cell_size + HUD_WIDTH, h*cell_size)` fits
  1600×900 for nonstandard `--width/--height`.
- Constant: `HUD_WIDTH = 320` (right-side panel px).
- Constant: `DEFAULT_CELL_SIZE = 12`.
- Constant: `SPS_MIN = 0.5`, `SPS_MAX = 60.0`.
- Constant: `MAX_STEPS_PER_FRAME = 10` — UI-freeze guard.
- Constant: `RETREAT_BORDER_COLOR = (255, 0, 255)`, `RETREAT_FILL_FACTOR = 0.4`.
- Palette MUST equal `Visualizer.render_z_slice` colors exactly
  (`sandkings.py:501-524`): GLASS (100,100,100), STONE (50,50,50),
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
- **R5** While a unit's `retreating` flag is set, it MUST render with fill =
  colony color × RETREAT_FILL_FACTOR and border = RETREAT_BORDER_COLOR;
  non-retreating units use full colony color with a contrast border (black
  border if the colony color is light, white if dark; luminance threshold 128).
- **R6** If the owed step debt in one frame exceeds MAX_STEPS_PER_FRAME, the
  pacer MUST clamp to MAX_STEPS_PER_FRAME and discard the residual accumulator
  (the UI never freezes; effective SPS degrades honestly).
- **R7** The HUD MUST show: step counter, paused state, target SPS, current
  z-slice, capture state, and per living colony: unit counts by caste, food
  stored, maw health, retreating count.
- **R8** Key bindings: SPACE pause/resume; `+`/`=`/`.` speed ×1.5 (clamp
  SPS_MAX); `-`/`,` speed ÷1.5 (clamp SPS_MIN); UP/DOWN z-slice ±1 (clamp
  [0, depth-1], initial depth//2); `S` single step (paused only); `G` toggle
  frame capture; ESC or window close quits.
- **R9** (MAY — stretch) `P` cycles a pheromone overlay off → FOOD_TRAIL →
  DANGER; alpha-blended heatmap. Not required for acceptance.
- **R10** (MAY — stretch) While capture is on, each rendered frame is stored;
  on quit, frames save to `sandkings_live.gif`.
- **R11** The Maw MUST render as a yellow (255,255,0) square with black border,
  larger than a unit, when its z matches the current slice.

## 4. Structural Spec

```
live_view.py
  build_voxel_palette() -> np.ndarray            # (256,3) uint8 LUT
  slice_color_array(world, colonies, z) -> np.ndarray   # (w,h,3) uint8; voxel LUT + territory tint
  unit_draw_color(colony_color, retreating) -> (fill, border)   # pure
  build_hud_lines(sim, sps, paused, z_level, capturing) -> list[str]  # pure

  class StepPacer:            # role: value-ish entity, no I/O
      __init__(steps_per_second)
      update(dt_ms, paused) -> int    # 0..MAX_STEPS_PER_FRAME owed steps
      faster() / slower()             # ×1.5 / ÷1.5 with clamps
      request_single_step()           # honored only while paused

  class LiveViewer:           # role: service/controller, owns pygame lifecycle
      __init__(sim, cell_size=DEFAULT_CELL_SIZE,
               steps_per_second=DEFAULT_STEPS_PER_SECOND, max_steps=None)
      run() -> None                   # blocks; pygame.init/quit bracketed
      _handle_event(event) / _render()   # internal

  run_live(sim, max_steps=None, steps_per_second=5.0) -> None   # entry point
```

`sandkings.main()` delta (only place touched): `--live` flag, `--sps` float,
`--steps` default 20 → None with GIF fallback `None → 20`.

## 5. Behavioral Spec — event loop

```
Input: sim (SandKingsSimulation), max_steps (int | None)
Initialize: steps_done ← 0; paused ← False; z ← depth // 2; running ← True
Loop while running:
    dt ← clock.tick(60)
    drain pygame events → _handle_event  (may flip paused/running/z/sps/capture,
                                          may request single step)
    owed ← pacer.update(dt, paused)      # 0 if paused unless single-step pending
    Loop owed times:
        sim.step(); steps_done += 1
        If max_steps is not None and steps_done >= max_steps: running ← False; break
    _render()                            # slice + units + maw + HUD (+ capture)
Terminate: pygame.quit(); print(sim.get_status())
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

## 7. Reconciliation Log

- (fill in after implementation)
