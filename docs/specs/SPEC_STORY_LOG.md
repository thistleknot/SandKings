# SPEC: Story Log — per-turn JSONL chronicle + optional local-LLM saga — SL1…SL4

Governing intent (user): "track a jsonl log of the game each turn… so an LLM can review and tell a story by
summarizing the state every ~100 lines (settable)… leverage a local Ollama qwen model to generate summaries
every 64 lines… idk, but a log at the very least."

The JSONL log is the **source of truth**; the LLM saga rides on top and is strictly optional and fail-soft.
Opt-in (a telemetry/output tool that writes a file — NOT a sim feature): default off, enabled by `--log`. When
off, `sim.story_log is None` and the `step()` hook is a no-op → byte-identical.

## SL1 — The per-turn JSONL log

`sim.story_log` (default `None`; a `StoryLog` when `--log` is passed). At the END of `sim.step()`:
`if sim.story_log: sim.story_log.record(sim)`. `record` writes one compact JSON object per logged step (cadence
`--log-every N`, default 1) to the log file, then flushes. Pure read of sim state; consumes NO RNG.

**One line = one snapshot** (`story_log.snapshot(sim)`):
```
{ step, year, season, hegemon, weather:[...active...], pond:{guppies,algae}, sign:<sky_sign kind|null>,
  colonies:[ { id, house, epithet, alive, gen, units, food, maw_hp, at_war, war_target,
               keeper, madness, confidence, breached, enlightened, priests, techs:[...] } ],
  events:[ <this step's drama messages> ] }
```
Events for the turn = `[m for (s,m) in sim.events if s == sim.step_count]` (the SPEC-T9 drama deque).

**Acceptance SL1.** With `--log run.jsonl`, a headless N-step run writes N (or N/every) lines; each parses as
JSON, carries `step`/`colonies`/`events`, and the step numbers are monotonic. No `--log` → no file, and the
`step()` hook is inert (battery byte-identical).

## SL2 — The optional local-LLM saga (fail-soft)

When `--summarize-every M` (>0) is set, `record` buffers each logged row; every M rows it calls a local Ollama
model (`--summary-model`, default `qwen3:2b`; `--summary-host`, default `http://localhost:11434`) with a bounded
prompt (season arc + surviving houses' end-state + the chronicle of events) and appends the returned saga to a
companion `<log>.story.md`, headed by the step range. The final partial buffer is summarized on `close()`.

**Fail-soft is REQUIRED:** the summary path is wrapped so that a missing/unreachable Ollama, an unknown model,
or any HTTP error NEVER raises into the game — it prints one `[STORY] … summary skipped` line and the JSONL log
keeps writing. The game must run identically whether or not Ollama is installed. Safe: one `localhost` POST, no
`eval`/`exec`, no third-party host.

**Acceptance SL2.** With `--summarize-every 2` and Ollama absent, a 4-step run still writes 4 JSONL lines and
prints the skip notice without crashing. (With Ollama present, `<log>.story.md` gains a saga per M lines — a
manual/live check, not a unit test, since it depends on an external model.)

## SL3 — CLI

`--log [PATH]` (bare → default `sandkings.jsonl`), `--log-every N` (default 1), `--summarize-every M`
(default 0 = off), `--summary-model NAME`, `--summary-host URL`. Built after sim creation, attached as
`sim.story_log`, closed at run end (both the `--live` and headless paths, via `sim.step()`-driven logging).

## SL4 — Spatial hotspots (where the action is)

Governing intent (user): the chronicle should carry WHERE the action happened, "frame by frame (a delta)" —
but symbolically, not as imagery: "we probably have to intelligently summarize sets of the state." Averaged or
3D renders are not LLM-interpretable; a named-region delta count is.

Each logged line gains `hotspots`: up to 3 `{"where": "<region> <band>", "changes": N}` entries ranked by the
count of cells whose voxel type OR ownership changed since the PREVIOUS logged line. Regions: 3x3 compass grid
over (x, y) — `NW N NE W C E SW S SE`. Bands: depth thirds — z in the top third is `surface`, middle `mid`,
bottom `deep` (z=0 is bedrock). The first logged line has `hotspots: []` (no baseline yet). Pure numpy diff of
`world.voxels` + `world.ownership` against copies kept by `StoryLog` — no RNG, no sim mutation, O(w·h·d)
compare per logged line. Zero-change regions are never listed.

The saga prompt (SL2) aggregates the batch's hotspots into one "where the action was" line (top 3 regions by
summed changes), so the chronicler can place the drama.

**Acceptance SL4.** With `--log`, every line parses with a `hotspots` list; line 1 has `[]`; after steps in
which colonies dig/build/fight, some line has a nonempty `hotspots` whose entries match the
`"<compass> <band>"` vocabulary with positive integer `changes`.

## Constants / files
- `story_log.py` — `StoryLog`, `snapshot(sim)`, `hotspots` region diff (SL4), the Ollama call. No new sim
  constants; no `_GATE_NAMES` entry (opt-in, None-by-default, not a sim gate).
