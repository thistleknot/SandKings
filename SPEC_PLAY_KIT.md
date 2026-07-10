# SPEC: Play Kit — a headless client to drive & test the terrarium (PK1–PK6)

A scriptable client so an agent (or any Python) can PLAY and TEST the game
through the same API the browser uses — no pixels, no manual curl. Borrows
the FastAPI backend (`create_app`) as the interaction layer and a
streamlit-style stateful loop for hands-on play.

## PK1 — Transport (`play_kit.Terrarium`)
`Terrarium` wraps the API behind a plain method surface. Two backends, one
interface:
- **in-process (default)** — builds a `TerrariumRunner` that is NOT started
  (no background thread) and a FastAPI `TestClient` over `create_app(runner)`.
  Stepping is explicit and deterministic; no socket or server needed. This is
  the play/test sandbox.
- **remote** — `Terrarium.connect(url)` uses `httpx` against a live console
  (e.g. `http://127.0.0.1:8010`) to observe/act on an autonomously-stepping
  sim. Same methods (except deterministic stepping, which a live sim owns).

Constructor: `Terrarium(canon=True, colonies=4, width=64, height=40, depth=14,
seed=None)`. `seed` seeds `random`/`np.random` for reproducible sessions.

## PK2 — `/api/step` endpoint (deterministic advance)
`POST /api/step {n:int}` steps `n` (clamped 1..STEP_CAP=500) via
`runner.step_owed(n)` under `runner.lock`, returns the fresh `build_state`.
This is what makes headless deterministic play/testing possible (the browser
never needs it; it's localhost + it only advances the sim it already owns).

## PK3 — Actions (thin wrappers over existing endpoints)
`feed(x=None, y=None)` (defaults to world center), `gift()`,
`release(species)` (any of the AR1 roster), `cat()`, `drought(on=True)`,
`temp(direction)` (arena heat/cold, AR3), `water(big, x, y)` /
`seed(x, y)` (HH1/HH3), `speak(colony_id)`,
`say(colony_id, text) -> {understood, heard, reply}` (converse),
`pause()/resume()`, `sps(v)`, `mirror(on=True)`, `step(n=1)`. Each mutating
call returns the new state dict (or the converse reply for `say`).
`aim(cid)` returns a colony's maw (x,y) for targeted feeding (in-process).

## PK4 — Reads
`state()` (raw `/api/state`), `colonies()` (list), `colony(cid)` (one, or
None), `events(n=10)`, `summary() -> str` one readable line:
`"t=<step> <season> | House <name> pop<p> food<f> stage<s> sent<σ> <flags>"`
per living house. Pure reads; never mutate.

## PK5 — Scenarios (scripted playthroughs that assert + narrate)
`play_kit.SCENARIOS` maps name -> function `(Terrarium) -> ScenarioResult`
(`ok: bool`, `name`, `transcript: list[str]`). Each drives the API, asserts a
mechanic, and narrates every beat:
- **worship** — feed a house repeatedly + step; it becomes `worshipped`.
- **cruelty** — worship then drought + step; `keeper_sentiment` falls and the
  carving band sours (devout→wary→hateful).
- **metamorphosis** — grow a house (food/pop) + step; `stage` reaches 2.
- **dialogue** — breach a house, `say(cid, "peace")` → heard `ally`, a reply.
- **turning** — a hateful Shade (stage 3) binds the keeper; feed is then
  stayed (`keeper_bound`).
Scenarios use `seed` for reproducibility and short step budgets.

## PK6 — CLI / REPL
`python play_kit.py`:
- `--scenario NAME` runs one scenario (or `all`), prints the transcript, exits
  non-zero on failure.
- `--do "cmd; cmd; ..."` runs a `;`-separated command script then exits (how
  an agent plays headlessly from a shell).
- `--repl` a terminal loop with the same `dispatch()` commands: `step [n]`,
  `feed [x y]`, `gift`, a bare species name (`cricket`/`ant`/`spider`/
  `scorpion`/`snake`/`squirrel`/`rabbit`/`small_spider`) or `release <sp>`,
  `cat`, `drought on|off`, `heat`, `cold`, `rain`, `deluge`, `seeds`,
  `say <cid> <text>`, `speak <cid>`,
  `state`/`summary`, `events [n]`, `quit`; prints `summary()` after each.
- `--url URL` targets a live console (remote transport) instead of in-process.
- `--seed N`, `--no-canon` options.

## Acceptance — tests/test_play_kit.py
In-process `Terrarium`: `/api/step` advances the count deterministically and
is clamped; `feed`/`drought`/`gift` mutate state and disarm auto; `say` on a
breached house returns a reply; `summary()` is a nonempty string naming a
house; at least the `worship` and `dialogue` scenarios return `ok`. No socket
is opened (TestClient only). The `Terrarium` never steps except via
`/api/step` (the single deterministic advance path).

## Status / Reconciliation
- Drafted + implemented 2026-07-10 (`play_kit.py`, `/api/step` in
  dashboard). Reconciled with Arena mode: `temp` action + the AR1 roster in
  `release`/REPL. Verified: all 5 scenarios PASS in-container and a `--do`
  session drives feed→growth→metamorphosis→worship→heat+drought mayhem;
  `tests/test_play_kit.py` green.
