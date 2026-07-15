# SPEC: The Keeper's Console (Round 9) — DB1–DB9

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

## DB9 — Economy runtime toggle (`POST /api/keeper/economy`) — EC1–EC3
Intent: the bargain/wage economy ships OFF (byte-identical regression
battery). Before this section the ONLY way to enable it was the
`--bargain` launch flag, so the console renders "Economy — off —" with
no control. DB9 adds a runtime toggle that flips the SAME gates
`--bargain` flips, at runtime, in both directions.

### DB9.1 — What `--bargain` sets (ground truth, sandkings.py:7136-7140)
The `--bargain` handler sets EXACTLY these four, no more:
```
sandkings.BARGAIN_ENABLED = True                    # module global (default False, :387)
sandkings.WAGE_ENABLED    = True                    # module global (default False, :352)
sandkings.CAPTURE_CHANCE  = BARGAIN_CAPTURE_CHANCE  # = 0.4 (default 0.0, :333/:388)
sim.bargain_enabled       = True                    # sim instance flag
```
OFF is the module-default triple plus the cleared sim flag:
`BARGAIN_ENABLED=False`, `WAGE_ENABLED=False`, `CAPTURE_CHANCE=0.0`,
`sim.bargain_enabled=False`.
- Require: toggle-ON sets the ON list verbatim; toggle-OFF restores the
  OFF triple and clears the sim flag.
- Maintain: module globals are mutated via attribute assignment on the
  imported module object (`import sandkings; sandkings.X = ...`) — NOT a
  local `from sandkings import X` rebind, which leaves the real module
  global untouched and would silently no-op the gate.
- Assert (OFF): restore `CAPTURE_CHANCE = 0.0` and `WAGE_ENABLED = False`
  by VALUE, not by deleting the attribute — other systems read these
  live globals; a missing attribute is a different failure than the OFF
  value.

### DB9.2 — Why the toggle alone lights the panel (no new state key)
`build_state` computes
`economy_on = bool(getattr(sim,'bargain_enabled',False)) or WAGE_ENABLED`
(dashboard.py:160) and re-imports `from sandkings import WAGE_ENABLED`
FRESH on every call (dashboard.py:65). Therefore:
- Setting `sim.bargain_enabled=True` alone flips `economy_on` True on the
  next state (short-circuit left operand).
- Setting `sandkings.WAGE_ENABLED=True` is also picked up (no stale
  binding), keeping `economy_on` parity with the `--bargain` launch.
The existing `economy_on` key already gates the client Economy panel
(dashboard.py:839) between "— off —" and the bargains/contracts render.
Guarantee: no change to `build_state`, no new state key.

### DB9.3 — The endpoint (mirror DB5 keeper POSTs, dashboard.py:448-494)
- Body model, beside the other `*Body` classes (dashboard.py:356-403):
  ```
  class EconomyBody(BaseModel):
      on: bool
  ```
  Explicit idempotent SET (`{on: true|false}`), NOT a blind server-side
  flip — the client sends the intended state, so double-clicks and
  reconnects converge instead of racing to the opposite state.
- Handler, beside gift/opendoor/drought:
  ```
  @app.post("/api/keeper/economy")
  def economy(body: EconomyBody):
      import sandkings
      with runner.lock:
          if body.on:
              sandkings.BARGAIN_ENABLED = True
              sandkings.WAGE_ENABLED    = True
              sandkings.CAPTURE_CHANCE  = sandkings.BARGAIN_CAPTURE_CHANCE
              runner.sim.bargain_enabled = True
          else:
              sandkings.BARGAIN_ENABLED = False
              sandkings.WAGE_ENABLED    = False
              sandkings.CAPTURE_CHANCE  = 0.0
              runner.sim.bargain_enabled = False
          return build_state(runner.sim)
  ```
- `_disarm_auto()`: DO NOT call it here — deliberate divergence from the
  other keeper POSTs. Rationale: `_disarm_auto` encodes "the human took
  the wand" over keeper WELFARE automation (food/gift/door/drought are
  direct hand interventions on colony fate). The economy toggle is a
  world-RULE mode switch orthogonal to welfare; its launch-flag
  equivalent (`--bargain`, sandkings.py:7136-7143) never touches
  `keeper_auto`. Silently disarming auto-keeper because the operator
  enabled wages would be a surprising side effect. The parent asked this
  be stated explicitly: choice = no disarm.

### DB9.4 — The button + JS (mirror droughtBtn, dashboard.py:718/754/786)
- Action-bar button near the Panel group (dashboard.py:726-730),
  state-driven label, initial text "Economy: Off":
  ```
  <button class="act" id="econBtn" onclick="toggleEconomy()">Economy: Off</button>
  ```
- JS helper beside `toggleDrought` (dashboard.py:754); sends the OPPOSITE
  of the server's current truth, guarding a null first-render state:
  ```
  function toggleEconomy(){post('/api/keeper/economy',{on:!(state&&state.economy_on)});}
  ```
- In `render()` beside the droughtBtn line (dashboard.py:786), reflect
  server state (NOT a client latch), so a reconnecting client shows the
  real economy state:
  ```
  document.getElementById('econBtn').textContent=
    (state.economy_on?'Economy: On':'Economy: Off');
  ```

## DB9 Acceptance — EC1–EC3 (tests/test_dashboard.py, TestClient)
Mirror the existing keeper-endpoint TestClient idioms (POST JSON, assert
200 + returned-state shape). `import sandkings` in the test to read/write
the module gates directly.

- EC1 — set/clear round-trip.
  `POST /api/keeper/economy {"on": true}` -> 200; returned state
  `economy_on is True`; `runner.sim.bargain_enabled is True`;
  `sandkings.BARGAIN_ENABLED is True`; `sandkings.WAGE_ENABLED is True`;
  `sandkings.CAPTURE_CHANCE == sandkings.BARGAIN_CAPTURE_CHANCE` (0.4).
  Then `{"on": false}` -> 200; `economy_on is False`;
  `sim.bargain_enabled is False`; `BARGAIN_ENABLED` and `WAGE_ENABLED`
  both `False`; `CAPTURE_CHANCE == 0.0`.
- EC2 — idempotent set. `{"on": true}` twice -> both 200, no error,
  final `economy_on is True` (explicit set, not a flip, so a repeat
  converges rather than toggling back off).
- EC3 — state hygiene (MANDATORY, single-process battery). These are
  MODULE globals; a test that flips them ON and leaks the ON values
  poisons every sibling suite that assumes the OFF default (same class of
  bug as the SPEC_FIT_CONSTANTS state-hygiene lesson). The test MUST
  snapshot `sandkings.BARGAIN_ENABLED`, `sandkings.WAGE_ENABLED`,
  `sandkings.CAPTURE_CHANCE`, and `sim.bargain_enabled` at entry and
  restore all four in a `finally` (or a fixture teardown) regardless of
  assertion outcome. Assert the OFF path restores the exact OFF triple
  (`0.0`, `False`, `False`) so no leak survives even on the happy path.

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
- DB9 drafted 2026-07-11. Economy runtime toggle mirrors the exact
  `--bargain` set-list (sandkings.py:7136-7140). NOT yet implemented —
  awaiting haiku_worker. Notable design calls: (a) `{on: bool}` idempotent
  set over blind flip; (b) NO `_disarm_auto` (economy is a world-rule
  switch, not a welfare wand); (c) OFF restores CAPTURE_CHANCE=0.0 by
  value; (d) EC3 finally-restore is mandatory to protect the shared
  single-process test battery.
