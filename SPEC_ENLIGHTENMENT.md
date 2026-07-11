# SPEC_ENLIGHTENMENT — Enlightenment ×N (the post-escape intelligence explosion)

Layer: **Behavioral** (ordered burst inside an existing method) + **Structural**
(new colony state, new constants, one signature change). This spec governs a
purely-additive feature hung off the existing `_escape` breakout. It changes no
existing breakout semantics.

Status: **Active — ready for rote implementation.** One design fork was live
(must `BRAIN_HIDDEN_MAX` rise?) and is **resolved in EN2/EN3 below** with
grounded evidence; see Reconciliation.

---

## 0. Concept & Scope

When a colony achieves the ONE true breakout (`_escape`, reached only by
terminal mastery — the 16th pi command, `TERMINAL_MASTERY = 16`), it does not
merely wake to the "great other" (`_reveal`). It **ascends**: a bounded
intelligence leap (≈×5, *not* omniscient). The leap is **earned climb, not
instant grant** —

- its brain **ceiling** is raised above the Shade cap (so evolution *may* grow a
  bigger brain — but must still mutate its way there);
- it learns native technology ~×`ENLIGHTENED_TECH_MULT` faster (it climbs the
  *native tech tree* faster — no techs are handed to it);
- it reads the codex ~×`ENLIGHTENED_CODEX_MULT` harder per consultation.

**In scope:** the `enlightened` flag, the ceiling bump, the two xp/lesson
multipliers, heritability, pickling, and display-only surfacing.

**Out of scope / DEFERRED (future work, do NOT implement):** biohacking /
self-genome-editing (a colony rewriting its own genome directly). Enlightenment
raises the *ceiling* and the *rate*; it does not let a colony author its own
genes. Note this in the ascend flavor but wire nothing.

**Economic hook (earned, not instant):** `composite_power` (M1) already counts
known techs, so a faster native-tech climb raises economic power *over time*
with **zero extra wiring**. Do not add an economy hook; it falls out of EN4.

---

## 1. Constants

Add to the tech/constants block near the other stage/tech constants
(`sandkings.py` module scope, alongside `STAGE_CEILING` at :369 and
`TERMINAL_MASTERY` at :271). Values are chosen bounded, not omniscient.

| Constant | Value | Meaning | Home |
|---|---|---|---|
| `ENLIGHTENED_CEILING` | `224` | brain_hidden ceiling granted at ascension; strictly above the Shade cap `STAGE_CEILING[3] == 160` | `sandkings.py` module scope |
| `ENLIGHTENED_TECH_MULT` | `5.0` | multiplier on every tech-xp gain while `enlightened` | `sandkings.py` module scope |
| `ENLIGHTENED_CODEX_MULT` | `5.0` | multiplier on every codex lesson-nudge while `enlightened` | `sandkings.py` module scope |
| `BRAIN_HIDDEN_MAX` | **`160` → `224`** | HARD architectural cap in the mutate clamp; MUST rise so the enlightened ceiling can take effect (see EN2 root-cause) | `neuroevolution.py:22` (change existing) |

`ENLIGHTENED_CEILING` and the raised `BRAIN_HIDDEN_MAX` are **equal (224)** by
design: the enlightened ceiling is the new global architectural maximum. A
non-enlightened colony's ceiling stays `≤ STAGE_CEILING[3] == 160`, so raising
`BRAIN_HIDDEN_MAX` to 224 is invisible to it (proof in EN3).

**Constants vs config:** all four are constants (balance knobs), not runtime
config. No env/CLI surface.

---

## 2. Verified hook sites (grounded — line numbers may drift; match by name)

| Site | Location (verified) | Role |
|---|---|---|
| `SandKingsSimulation._escape(colony)` | `sandkings.py:2909`; append burst AFTER `self._reveal(colony)` at :2918, before method end (:2920) | fires the ascension once |
| `SandKingsSimulation._escape` top guard | `if getattr(colony,'breached',False): return` at :2914 | already makes the entire body (incl. the burst) fire at most once |
| `ColonyGenome.brain_ceiling` | field default `88` at `sandkings.py:783` | the heritable ceiling to raise |
| `ColonyGenome.mutate` clamp | `sandkings.py:816-817`: `min(BRAIN_HIDDEN_MAX, ceiling)` | the clamp that MUST see a raised `BRAIN_HIDDEN_MAX` to honor the enlightened ceiling |
| `STAGE_CEILING` | `{1:88, 2:128, 3:160}` at `sandkings.py:369` | Shade cap = 160; ascension exceeds it |
| `SandKingsSimulation._practice(colony, tech, amount)` | `sandkings.py:2711-2719` | the SINGLE funnel through which ALL tech xp is added (practice, observe, grain, research, and direct `masonry`/`plow`/`metallurgy`/`farming` calls) — the one tech-multiplier site |
| `SandKingsSimulation._codex_tick` → `apply_lesson(colony.genome, lesson)` | call at `sandkings.py:3038`; def at `codex.py:186` | the codex lesson-gain site — the one codex-multiplier site |
| `SandKingsSimulation._respawn_colony` | crossed branch `sandkings.py:5898-5916`; survivor branch :5921-5929 | heritability wiring (mirror `breached`/`stage`) |
| dashboard payload dict | `dashboard.py:98-99` (`"breached"`,`"stage"`) | add `"enlightened"` (display-only) |
| dashboard House-card badge JS | `dashboard.py:748-753` | add an `enlightened` badge (display-only) |

Base xp constants (from `tech.py`): `TECH_PRACTICE_XP=0.02`, `TECH_OBSERVE_XP=0.03`,
`TECH_GRAIN_XP=0.15`, `TECH_RESEARCH_XP=0.015`, `TECH_LEARN_XP=0.3`. Codex nudge
(from `codex.py:50`): `CODEX_NUDGE=0.03`.

---

## 3. Requirements (numbered clauses)

### EN1 — `enlightened` colony state (new, guarded, pickled)
A colony carries a boolean `enlightened`, default `False`, accessed everywhere
via `getattr(colony,'enlightened',False)`. It is set `True` exactly once, inside
the `_escape` burst. It pickles with the colony (plain attribute; no special
handling). No code path reads a *stored* `enlightened` to gate control flow other
than the two multiplier sites (EN4/EN5) and the surfacing (EN9), all of which are
purely additive.

**Acceptance:** a fresh colony has `getattr(c,'enlightened',False) is False`
without the attribute ever being set; after `_escape(c)` it is `True`; a pickled
round-trip preserves it.

### EN2 — Ceiling bump at ascension (ROOT-CAUSE-RESOLVED design fork)
On the burst, set `colony.genome.brain_ceiling = ENLIGHTENED_CEILING` (224),
which is strictly greater than the Shade cap `STAGE_CEILING[3]` (160).

**Root cause / why `BRAIN_HIDDEN_MAX` MUST also rise (the resolved fork):** the
mutate clamp at `sandkings.py:817` is
`int(np.clip(hid, BRAIN_HIDDEN_MIN, min(BRAIN_HIDDEN_MAX, ceiling)))`. With
`BRAIN_HIDDEN_MAX == 160`, the effective cap is `min(160, 224) == 160` — the
raised ceiling would be **silently clamped back to 160 and have ZERO effect on
brains.** Simply bumping `brain_ceiling` is therefore *not sufficient*. The fix
is to raise `BRAIN_HIDDEN_MAX` to `224` (EN3) so `min(224, 224) == 224` and the
enlightened brain can actually grow. **This spec resolves the fork: raise
`BRAIN_HIDDEN_MAX` to 224 in `neuroevolution.py:22`.**

**Acceptance:** after `_escape(c)`, `c.genome.brain_ceiling == ENLIGHTENED_CEILING`
and `ENLIGHTENED_CEILING > STAGE_CEILING[3]`; repeated `mutate()` from a seeded
small brain eventually yields `brain_hidden > STAGE_CEILING[3]` (i.e. the ceiling
*takes effect*, not just is stored).

### EN3 — Raise `BRAIN_HIDDEN_MAX` (default-neutral change)
Change `neuroevolution.py:22` from `BRAIN_HIDDEN_MAX = 160` to
`BRAIN_HIDDEN_MAX = 224`. This is the ONLY change to `neuroevolution.py`.

**Default-neutrality proof (verified by grep — the constant has exactly two
functional readers):**
- `sandkings.py:817` mutate clamp — for a non-enlightened colony `ceiling ≤ 160`,
  so `min(224, ceiling) == min(160, ceiling) == ceiling`. Identical result.
- `tests/test_evolution.py:43` asserts `... <= g.brain_hidden <= BRAIN_HIDDEN_MAX`
  — loosening the upper bound keeps every passing case passing.
No other functional code reads `BRAIN_HIDDEN_MAX` (SPEC_*.md occurrences are
prose). A non-enlightened colony is therefore **byte-identical** after this
change.

**Acceptance:** the full existing battery stays green with `BRAIN_HIDDEN_MAX=224`;
`test_evolution.py` still passes; `test_metamorphosis.py::test_brain_ceiling_rises_with_stage_and_mutate_respects_it`
(which uses a ceiling of 160, not >160) is unaffected.

### EN4 — Ongoing tech-xp multiplier (single funnel: `_practice`)
While `enlightened`, every tech-xp gain is multiplied by `ENLIGHTENED_TECH_MULT`.
Apply the multiplier **once, inside `_practice`**, to `amount` before the
proficiency accumulation line (`sandkings.py:2716`). Because `_practice` is the
sole funnel for observe (:2747), grain (:2756), research (:2765), and every
direct `self._practice(...)` action (masonry :2193, plow :4651/:4663, metallurgy
:4712, farming :6023), this one edit covers all tech xp with no other site
touched. The existing `min(1.0, …)` proficiency cap is unchanged — so the leap
reaches `TECH_LEARN_XP` faster but **never exceeds proficiency 1.0**; it is a
rate boost, not a grant.

**Acceptance:** with equal activity, an enlightened colony's `tech_xp[t]` rises
~×`ENLIGHTENED_TECH_MULT` per `_practice` call vs a non-enlightened one (choose a
base `amount` small enough that ×MULT stays under the 1.0 cap — see acceptance
math). A non-enlightened colony's per-call gain equals the base `amount` exactly.

### EN5 — Ongoing codex-read multiplier (single site: `apply_lesson`)
While `enlightened`, each codex lesson nudges the genome ~×`ENLIGHTENED_CODEX_MULT`
harder. Add an optional `scale: float = 1.0` parameter to
`codex.apply_lesson(genome, lesson, scale=1.0)` so the nudge magnitude becomes
`CODEX_NUDGE * weight * scale` (the `np.clip(..., 0.0, 1.0)` bound is kept). In
`_codex_tick` (`sandkings.py:3038`), pass
`ENLIGHTENED_CODEX_MULT if getattr(colony,'enlightened',False) else 1.0`.
Default `scale=1.0` keeps every existing caller byte-identical.

**Design note (fork surfaced, resolved):** codex "gain" is the per-lesson genome
nudge, not a counter — so the principled ×N is a **magnitude scale on the nudge**,
not calling `apply_lesson` five times (which would be fractional-ugly for
MULT=5.0 and would re-run side effects). Scaling the nudge is the single clean
gain-site multiplier. This is the ONLY change to `codex.py` and it is
signature-backward-compatible.

**Acceptance:** for a lesson whose `LESSON_EFFECT` moves attr `a`, an enlightened
colony's genome delta on `a` is ~×`ENLIGHTENED_CODEX_MULT` the non-enlightened
delta (until the 0.0..1.0 clip binds — pick a mid-range start attr so it does not
clip). `apply_lesson(genome, lesson)` called with no `scale` behaves exactly as
before.

### EN6 — Fire exactly once
The burst runs inside `_escape`, whose top guard
`if getattr(colony,'breached',False): return` (:2914) already guarantees the
whole body executes at most once per colony. For defense-in-depth (and to guard
against any future non-`_escape` trigger), wrap the burst additionally in
`if not getattr(colony,'enlightened',False):`. Net: ceiling bump and ascend log
happen once.

**Acceptance:** two consecutive `_escape(c)` calls produce exactly one ascend
event and leave `brain_ceiling == ENLIGHTENED_CEILING` (not doubled/re-logged).

### EN7 — Ascend event (salience 10)
On the burst, emit one chronicle event via the existing `self._log_event(...)`,
e.g. `f"House {self._house_name(colony)} ascends - the light of the "
`"Enlightenment breaks over it"`. It must be a *distinct string* from the
`_reveal` "beyond the glass" line so revelation-count assertions
(`test_awareness.py:80-84`) are unaffected. Salience-10: if `_log_event` accepts
a salience/priority argument in this codebase, pass the max; otherwise the
distinct wording carries it (do NOT invent a new logging API — match the existing
`_log_event` signature used at :2282).

**Acceptance:** exactly one ascend event per colony; it does not match the
substring `"beyond the glass"`; `test_awareness.py::test_revelation_fires_once…`
still counts exactly one revelation.

### EN8 — Heritability (mirror `breached`/`stage`)
`enlightened` inherits on respawn following the existing convention in
`_respawn_colony`:
- **crossed / hybrid branch** (:5898-5916): OR of both parents —
  `colony.enlightened = getattr(pa,'enlightened',False) or getattr(pb,'enlightened',False)`.
- **survivor / cadet branch** (:5921-5929): copy parent —
  `colony.enlightened = getattr(parent,'enlightened',False)`.
The genome's `brain_ceiling` already rides the genome heritably (MT4; `mutate`
copies it at :815), so an enlightened bloodline keeps both the flag *and* the
raised ceiling. Recommendation adopted: **yes, `enlightened` is inherited** — an
enlightened bloodline stays enlightened, exactly like `breached`.

**Acceptance:** a cadet respawned from an enlightened parent has
`enlightened is True` and its genome `brain_ceiling >= ENLIGHTENED_CEILING`
(the ceiling survived through mutate); a cadet from a non-enlightened parent has
`enlightened is False`.

### EN9 — Surfacing (display-only; no control flow keys off it)
- Dashboard payload (`dashboard.py:98-99`): add
  `"enlightened": bool(getattr(colony,'enlightened',False))`.
- House-card badge JS (`dashboard.py:748-753`): add a badge when
  `col.enlightened` (e.g. `<span class="badge breach">enlightened</span>` or a
  new class), display-only.
- Live-view inspect line / tint: OPTIONAL, additive; if added, read only
  `getattr(colony,'enlightened',False)` for display. No simulation branch may
  read a *surfaced* value.

**Acceptance:** payload contains the `enlightened` key; the badge renders only
for enlightened houses; removing the surfacing changes no simulation output.

### EN10 — `EnhancedSandKingsSimulation.step` stays inert
`EnhancedSandKingsSimulation` (in `sandkings_evolution.py`) never escapes a
colony, so it never enlightens one. The feature adds nothing to its `step`.

**Acceptance:** existing `test_metamorphosis.py::test_state_pickles_and_evolution_inert`
style assertions hold; a run of `EnhancedSandKingsSimulation.step` produces no
enlightenment and no ascend events.

---

## 4. OOP definitions & contracts

### 4.1 `_escape` burst (append after `self._reveal(colony)` at :2918)

```
method SandKingsSimulation._escape(self, colony: Colony) -> None
  # ... existing body up to and including self._reveal(colony) ...
  # ---- Enlightenment burst (EN2, EN6, EN7) ----
  if not getattr(colony, 'enlightened', False):
      colony.enlightened = True
      if getattr(colony.genome, 'brain_ceiling', 88) < ENLIGHTENED_CEILING:
          colony.genome.brain_ceiling = ENLIGHTENED_CEILING
      self._log_event(
          f"House {self._house_name(colony)} ascends - the light of the "
          "Enlightenment breaks over it")
  # method ends
```

Contract at the burst:
- **Require:** called from within `_escape` after `_reveal`; `colony.genome`
  exists and exposes `brain_ceiling`; the top-of-method `breached` guard has
  already run (so this is the first breakout).
- **Guarantee:** on first breakout, `colony.enlightened is True`,
  `colony.genome.brain_ceiling == ENLIGHTENED_CEILING`, and exactly one ascend
  event is logged. On any subsequent call the entire `_escape` body (incl. this
  burst) is skipped by the `breached` guard.
- **Maintain:** `colony.breached`, `colony.stage`, `colony.revelation`,
  `colony.keeper_sentiment` are UNCHANGED by the burst (set by pre-existing code
  above; the burst never writes them). This is what keeps the awareness/psionic
  batteries green.
- **Assert:** `ENLIGHTENED_CEILING > STAGE_CEILING[3]` (a module-load-time
  invariant; may be asserted once at import or in the test).

### 4.2 `_practice` tech multiplier (edit before the accumulation line :2716)

```
method SandKingsSimulation._practice(self, colony, tech, amount=TECH_PRACTICE_XP) -> None
  if not hasattr(colony, 'tech_xp'):
      colony.tech_xp = {}
  if getattr(colony, 'enlightened', False):          # EN4
      amount = amount * ENLIGHTENED_TECH_MULT
  xp = min(1.0, colony.tech_xp.get(tech, 0.0) + amount)
  colony.tech_xp[tech] = xp
  if xp >= TECH_LEARN_XP and tech not in getattr(colony, 'techs', set()):
      self._grant_tech(colony, tech)
```

Contract:
- **Require:** `amount >= 0`; `colony` may or may not have `enlightened`.
- **Guarantee:** an enlightened colony accumulates `amount*MULT` (pre-cap) per
  call; a non-enlightened colony accumulates exactly `amount`; the proficiency
  stays clamped to `≤ 1.0`.
- **Maintain:** no tech is granted except through the existing
  `xp >= TECH_LEARN_XP` threshold (no instant grant — bounded climb only).
- **Assert:** multiplier applies iff `getattr(colony,'enlightened',False)`.

### 4.3 `apply_lesson` codex multiplier (edit `codex.py:186`)

```
function apply_lesson(genome, lesson: str, scale: float = 1.0) -> List[str]
  moved = []
  for attr, weight in LESSON_EFFECT.get(lesson, ()):
      current = getattr(genome, attr, 0.5)
      setattr(genome, attr,
              float(np.clip(current + CODEX_NUDGE * weight * scale, 0.0, 1.0)))
      moved.append(attr)
  return moved
```

Caller in `_codex_tick` (`sandkings.py:3038`):
```
scale = ENLIGHTENED_CODEX_MULT if getattr(colony, 'enlightened', False) else 1.0
apply_lesson(colony.genome, lesson, scale)
```

Contract:
- **Require:** `scale > 0`; `genome` exposes the `LESSON_EFFECT` attrs (or falls
  back to 0.5 as today).
- **Guarantee:** with `scale==1.0` the output is identical to the current
  implementation (default-neutral); with `scale==ENLIGHTENED_CODEX_MULT` each
  nudge magnitude is ×MULT before the `[0,1]` clip.
- **Maintain:** the `np.clip(...,0.0,1.0)` bound still holds — no genome attr
  escapes `[0,1]`.
- **Assert:** enlightened scale used iff the reader colony is `enlightened`.

### 4.4 `_respawn_colony` heritability (edit both branches)

```
# crossed / hybrid branch (near :5898)
colony.enlightened = (getattr(pa, 'enlightened', False)
                      or getattr(pb, 'enlightened', False))
# survivor / cadet branch (near :5921)
colony.enlightened = getattr(parent, 'enlightened', False)
```

Contract:
- **Require:** called within the existing respawn branches with `pa`/`pb`
  (crossed) or `parent` (survivor) in scope.
- **Guarantee:** the cadet's `enlightened` matches the convention used for
  `breached`/`stage` in the same branch.
- **Maintain:** brain_ceiling continues to ride the genome (unchanged); no new
  genome mutation is introduced by heritability.

---

## 5. Acceptance section — `tests/test_enlightenment.py`

Each test names the clause it verifies. Use the fast runner: `python run_tests.py`
(never bare `python` on the host — per project constraints, use the py310 path or
Docker if invoking directly).

- **AT1 (EN1, EN2):** `test_escape_enlightens_and_raises_ceiling` — build a sim,
  `_escape(c)`; assert `getattr(c,'enlightened',False) is True`,
  `c.genome.brain_ceiling == ENLIGHTENED_CEILING`, and
  `ENLIGHTENED_CEILING > STAGE_CEILING[3]`.
- **AT2 (EN2, EN3):** `test_enlightened_mutate_grows_bigger_brains` — seed
  `random`/`np.random`; take an enlightened genome with `brain_hidden` small,
  `brain_ceiling = ENLIGHTENED_CEILING`; iterate `mutate()` many times; assert
  the max observed `brain_hidden` exceeds `STAGE_CEILING[3]` (160). Proves the
  ceiling actually *takes effect* through the raised `BRAIN_HIDDEN_MAX`.
- **AT3 (EN4):** `test_enlightened_tech_xp_climbs_faster` — two colonies, one
  `enlightened=True`; call `_practice(c, 'masonry', 0.02)` N times on each (base
  chosen so `0.02*MULT*N` stays under 1.0). Assert enlightened `tech_xp['masonry']`
  ≈ ×`ENLIGHTENED_TECH_MULT` the control, within float tolerance.
- **AT4 (EN5):** `test_enlightened_codex_reads_harder` — pick a lesson with a
  known `LESSON_EFFECT` attr starting mid-range; call
  `apply_lesson(g_ctrl, lesson)` and `apply_lesson(g_enl, lesson, ENLIGHTENED_CODEX_MULT)`;
  assert the enlightened genome's attr delta ≈ ×MULT the control's (below clip).
  Also assert `apply_lesson(g, lesson)` (no scale) matches pre-change behavior.
- **AT5 (EN6, EN7):** `test_ascension_fires_once` — `_escape(c)` twice; assert
  exactly one ascend event in `sim.events` and `brain_ceiling` unchanged on the
  second call.
- **AT6 (EN8):** `test_enlightened_inherits_on_respawn` — enlighten a parent,
  kill the victim, `_respawn_colony(id)`; assert the cadet `enlightened is True`
  and its genome `brain_ceiling >= ENLIGHTENED_CEILING`; a non-enlightened parent
  yields `enlightened is False`.
- **AT7 (EN1):** `test_enlightenment_state_pickles` — `_escape(c)`, pickle
  round-trip; assert `enlightened` and `brain_ceiling` survive.
- **AT8 (EN3, default-neutral):** `test_non_escaped_colony_is_byte_identical` —
  the battery guard: a colony that never escapes has
  `getattr(c,'enlightened',False) is False`; running `_practice`/`_codex_tick` on
  it gives base-rate gains (no MULT); assert the FULL existing battery
  (`test_awareness.py`, `test_metamorphosis.py`, `test_psionic.py`,
  `test_evolution.py`, play_kit) stays green under `python run_tests.py`.
- **AT9 (EN10):** `test_enhanced_step_inert` — run
  `EnhancedSandKingsSimulation.step` and assert no colony becomes enlightened and
  no ascend event fires.

Default-neutral verification already performed against the existing battery
(evidence in section 6): none of the `_escape`-exercising tests
(`test_awareness.py:77/82/88`, `test_metamorphosis.py:42/91/153`) assert
tech/ceiling/breached/stage/sentiment/revelation state that the burst changes.

---

## 6. Reconciliation / notes

- **Resolved fork — `BRAIN_HIDDEN_MAX` MUST rise (EN2/EN3).** Grep proved
  `BRAIN_HIDDEN_MAX==160==STAGE_CEILING[3]` and that the mutate clamp is
  `min(BRAIN_HIDDEN_MAX, ceiling)`; leaving it at 160 would silently null the
  224 ceiling. Raising it to 224 is the minimal fix and is default-neutral (only
  two readers; both stay correct). This was the one genuine design fork and it is
  decided here, not left to the implementer.
- **Default-neutrality confirmed against the real battery.** The `_escape` burst
  writes only `enlightened`, `brain_ceiling`, and a new distinct event. Verified
  reads:
  - `test_awareness.py::test_revelation_fires_once…` counts `"beyond the glass"`
    — the ascend string differs, count unaffected; asserts `keeper_sentiment`
    0.7/0.3 — untouched.
  - `test_metamorphosis.py` `_escape` callers assert only
    `breached`/`revelation`/`stage` — untouched; the `brain_ceiling` test never
    calls `_escape` and uses a 160 ceiling, so `min(224,160)==160` is unchanged.
  - `test_evolution.py:43` upper-bound assertion loosens safely.
- **Economic edge is EARNED, not granted.** Faster native-tech climb (EN4) raises
  `composite_power` (M1) over time automatically. No M1-M4 wiring added.
- **DEFERRED (out of scope, future):** biohacking / self-genome-editing — a
  colony directly rewriting its own genes. Enlightenment grants ceiling + rate,
  not authorship. Mention in flavor only; wire nothing.
- **Files touched by the implementer:** `sandkings.py` (constants, `_escape`
  burst, `_practice` multiplier, `_codex_tick` scale arg, `_respawn_colony` ×2),
  `neuroevolution.py` (one constant), `codex.py` (`apply_lesson` signature),
  `dashboard.py` (payload key + badge), and new `tests/test_enlightenment.py`.
  No other module is in scope.
