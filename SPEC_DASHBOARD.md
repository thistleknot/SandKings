# SPEC: The Keeper's Console (Round 9) — DB1–DB8

Intent: a human-facing web view of the terrarium — "the biodome
supported by proper technology" — that delivers real interaction
WITHOUT the safety hazards of Round 8's rejected code-exec/internet
path. The console READS the sim and INJECTS keeper verbs; the sim
never reaches the shell, a socket, or the internet.

## DB1 — Safety boundary (binding, tested)
- FastAPI app; served by uvicorn bound to `127.0.0.1` ONLY (never
  0.0.0.0) — a garage terminal, not a public server.
- The sim stays a pure function of its own state. The dashboard has
  exactly two effects on it: (a) READ a JSON/PNG snapshot, (b) call
  the EXISTING `keeper_*` sim methods. No endpoint executes arbitrary
  code, evaluates strings, touches the filesystem beyond the optional
  checkpoint, or makes any outbound request.
- No external frontend resources: all HTML/CSS/JS is inlined and
  served from the app; a strict `Content-Security-Policy: default-src
  'self'` header is set. No CDN, no fonts, no telemetry.

## DB2 — The runner (threading)
`TerrariumRunner` owns the sim and a background stepping thread. A
single `threading.Lock` guards every sim touch. The thread loops:
acquire lock -> `sim.step()` -> release -> sleep to hit target sps;
`paused` skips the step. Keeper endpoints acquire the same lock and
call sim methods directly (the calls are O(1)-ish; no queue needed).

## DB3 — State endpoint (`GET /api/state`)
Returns a JSON snapshot (pure function `build_state(sim)`):
- header: step, year, season name, dole %, drought flag, target sps,
  paused, active weather list.
- colonies[]: id, house label (D1), epithet, alive, keeper attitude
  (none/reverent/wrathful), population by caste, food, maw HP %,
  mood (colony_thought), at_war, generation, worshipped, breached,
  and utterance (compose_utterance of a representative unit, "" if
  not breached).
- saga[]: recent chronicle rows at salience >= 4 (house-substituted).
- events[]: the recent event feed lines.
- keeper: auto flag, gifts_given, whether a gift is on the ground.

## DB4 — Frame endpoint (`GET /api/frame.png`)
`render_frame_png(sim, scale)` — a top-down PNG built with numpy +
PIL (NO pygame dependency; the dashboard must import cleanly without
a display). First-non-air column scan -> palette LUT (mirrors the
glyph palette), owned surface tinted by colony color, then overlays:
units (colony color), maws (yellow, larger), beasts (violet),
carvings (gold), fire (orange), flood cells (blue). Nearest-neighbor
upscaled to ~`scale` px wide. Returned as `image/png`.

## DB5 — Keeper endpoints (inputs only)
POST, each acquiring the lock and calling the matching sim method,
returning the fresh state:
- `/api/keeper/food` {x,y} -> keeper_drop_food (clamped to bounds)
- `/api/keeper/release` {species in the garage set} -> keeper_release
- `/api/keeper/cat` -> keeper_release_cat
- `/api/keeper/gift` -> keeper_gift
- `/api/keeper/drought` {on: bool} -> keeper_drought
- `/api/keeper/speak` {colony_id} -> keeper_speak on a representative
  unit (404-safe: no-op if the colony has no units)
- `/api/control` {paused?, sps?} -> pacing
Any keeper POST sets `sim.keeper_auto = False` (the human has taken
the wand), mirroring the viewer.

## DB6 — The frontend (design-led)
One inlined single-page app, "THE KEEPER'S CONSOLE", polling
`/api/state` at ~2 Hz and refreshing the frame image. Design
principles are first-class here:
- IDENTITY: a garage-biodome control terminal. Dark, warm-sand and
  glass-green accents, one committed dark theme (a console in a dark
  garage is a deliberate single-theme choice).
- HIERARCHY: header (year/season/weather/drought) -> main split of
  [living terrarium image | House rail] -> the Saga ticker -> a
  sticky Keeper console bar grouped by intent (Bounty / Creatures /
  Wrath / Gifts).
- TYPE & RHYTHM: a monospace system stack (roguelike DNA), a small
  modular type scale, consistent 8px spacing rhythm, restrained
  color used only to encode meaning (attitude dot: gold reverent /
  red wrathful / grey none; breach badge; war mark).
- HOUSE CARDS: name + epithet, attitude dot, pop/food/mood, and for
  breached houses the utterance in quotes with a "speak" affordance.
  Selecting a card reveals a message box that POSTs to speak.
- LIVING MAP: clicking the terrarium image drops food at that world
  cell (pixel -> world via known dims). Fire/flood/drought read at a
  glance.
- RESPONSIVE, no horizontal body scroll; the rail wraps under the map
  on narrow viewports.
- FEEDBACK: the event feed streams; keeper actions flash a toast.

## DB7 — Launch
`python dashboard.py [--persist path] [--sps N] [--port P]` starts
the runner and uvicorn on 127.0.0.1. Per the server-start rule, the
CLI prints the URL and the process is meant to be launched detached /
in its own shell (never inline in an agent thread). Import of
`dashboard` MUST NOT start a server (guarded by `__main__`).

## DB8 — Acceptance
tests/test_dashboard.py (FastAPI TestClient, no real socket):
`/api/state` shape and safety (pure, no sim mutation on GET);
`/api/frame.png` returns a valid PNG without pygame; each keeper
endpoint invokes its sim method and disarms auto; speak is 404-safe;
the app sets the CSP header and binds localhost in the launch path;
no endpoint imports subprocess/socket/eval. build_state and
render_frame_png are pure and importable headless.

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Delta:
  - build_state coerces every numeric field to native Python
    (int/float/str) - numpy scalars creep into maw.food_stored etc.
    once the sim advances and FastAPI's JSONResponse cannot serialize
    np.float32. Caught at live-server probe, not by the step-0
    TestClient; the DB8 tests now step ~120 and json.dumps the state
    to lock it in.
  - DB8 soak/probe: PASSED - live uvicorn on 127.0.0.1 serves the
    console page (10KB), /api/state (house-named JSON), and
    /api/frame.png (valid PNG); keeper POSTs mutate + disarm auto.
    13/13 test suites green incl. tests/test_dashboard.py (9).
  - Deps: fastapi, uvicorn, pillow (numpy already present). No pygame.
