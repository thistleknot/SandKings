# SPEC: Fit Constants — a learned demonstrator for the four semi-permeable knobs (FC1–FC12)

A NEW **data-side tool** `fit_constants.py` that SEARCHES the four semi-permeable
knobs (`SUN_JITTER_SD`, `SUN_OSC_AMP`, `CAPTURE_TEMP`, `BARGAIN_TEMP`) against a
**healthy-ecology objective** and REPORTS the fitted vector versus the inert
default. It is the **Tier-2 demonstrator** of the grounding plan: today those four
knobs default to `0.0` (identity/inert per SPEC_SEMIPERMEABLE SP7/SP9/SP10/SP11),
and any non-zero value would otherwise be a hand-picked magic constant. This tool
makes the chosen value the **output of a search** — so a "`0.15`" becomes "the best
of a keep-if-improved search against a scalar objective," not another magic number.

> **What this tool DOES and does NOT do (read first).**
> - **DOES**: set the four knobs (as `sandkings` module globals) to candidate
>   vectors, run seeded headless episodes, score each against a 3-component
>   objective, hill-climb with keep-if-improved, checkpoint every `(vector, seed)`
>   evaluation to sqlite, and PRINT the inert-baseline vs fitted-incumbent scores.
> - **DOES NOT**: edit `sandkings.py`, mutate any constant durably, or decide
>   adoption. It is a **REPORTER/demonstrator**. Whether to adopt a fitted value is
>   a human decision made AFTER reading the report. It also does not touch the held
>   knobs `SUN_OSC_PERIOD`, `SUN_EMA_ALPHA`, `CAPTURE_CENTER` — those stay at their
>   `sandkings` defaults this pass (noted in FC2).
> - **REUSES** the `playtest_economy.py` eval-harness pattern verbatim: seed both
>   module streams (`random.seed(s); np.random.seed(s)`), enable the arc
>   (`sk.BARGAIN_ENABLED=True; sk.WAGE_ENABLED=True;
>   sk.CAPTURE_CHANCE=sk.BARGAIN_CAPTURE_CHANCE`), construct
>   `SandKingsSimulation(width=80,height=48,depth=16,num_colonies=4)` with
>   `sim.bargain_enabled=True; sim.keeper_auto=True`, step, and read telemetry via
>   `sim.colonies` / `c.is_alive()` / `sim._bargain_modes()` / `sim.sun_effective`.

Layer: **Requirements + Structural + Behavioral.** Observable search/report
behaviour (requirements), the module functions + sqlite schema + contracts
(structural), and the ordered search loop with state-save/restore (behavioral).

---

## FC1 — Requirements (observable behaviour + acceptance)

| # | Requirement | Acceptance criterion (mechanically checkable) |
|---|---|---|
| FC1.1 | **Deterministic objective** | For a fixed knob vector `v` and a fixed seed set `S`, `evaluate_candidate(v, S, conn)` returns the SAME averaged objective on repeat calls (no hidden entropy; proposal RNG is a separate instance from episode-seeding). See **FC-1**. |
| FC1.2 | **Bounded, finite components** | Each of the three components (LIVENESS, MODE_DIVERSITY, WEATHER_VARIANCE) is in `[0,1]`; the weighted OBJECTIVE is in `[0,1]`; the inert baseline `(0,0,0,0)` is evaluable and finite. See **FC-2**. |
| FC1.3 | **State hygiene (load-bearing)** | After ANY search run (or exception during one), the seven touched `sandkings` module globals equal their pre-run values — the tool leaves no global mutated. See **FC-3**. |
| FC1.4 | **Never regresses** | `run_search` starts its incumbent at the inert baseline and replaces it ONLY on a strictly-greater averaged objective; the returned incumbent's objective is `>=` the baseline's. See **FC-4**. |
| FC1.5 | **Idempotent checkpoint** | Evaluating the same `(vector, seed)` twice reads the cached row the second time and does NOT re-run the sim (sqlite load-if-exists). See **FC-5**. |
| FC1.6 | **Security** | Pure numeric, in-process only: sets numeric module globals, reads sim telemetry, writes ONE sqlite checkpoint file. NO `eval`/`exec`, no host codegen, no sockets, no network, no subprocess. See **FC9**. |
| FC1.7 | **Headless** | Runs without a display: `os.environ.setdefault('SDL_VIDEODRIVER','dummy')` at import top, BEFORE importing `sandkings`. See **FC10**. |
| FC1.8 | **Importable, cheap-testable** | The tool exposes `objective_components`, `objective_scalar`, `run_episode`, `evaluate_episode`, `evaluate_candidate`, `run_search` as importable functions with a budget argument, so `tests/test_fit_constants.py` drives them with tiny `N_ITERS/N_SEEDS/STEPS`. See **FC8**. |

---

## FC2 — Structural: the search space (the four knobs + their scale-matched bounds)

The search vector is an ordered 4-tuple of floats. Bounds reflect **each metric's
scale** (the SP9 lesson — a softmax/logistic `temp` must match the domain of the
metric it tempers; a metric-mismatched temp gives a near-inert membrane).

| Index | Knob (module global) | Bound `[lo, hi]` | Metric domain / rationale |
|---|---|---|---|
| 0 | `SUN_JITTER_SD` | `[0.0, 3.0]` | daylight-hours noise SD; sun domain `~4..20` (`SUN_MIN..SUN_MAX`). |
| 1 | `SUN_OSC_AMP` | `[0.0, 6.0]` | daylight-hours swing amplitude around the `sun_hours` setpoint. |
| 2 | `CAPTURE_TEMP` | `[0.0, 0.4]` | metric is `power_ratio ∈ [0,1]` → **SMALL** temp. Do NOT search up to `2.0` (that flattens `soft_gate` to `~0.44..0.56` across the whole domain — an inert membrane, SPA-10 temp-scale note). |
| 3 | `BARGAIN_TEMP` | `[0.0, 5.0]` | metric is EV *differences* (net-extraction values, larger scale) → larger temp span. |

**FC2.1 — Held fixed this pass.** `SUN_OSC_PERIOD`, `SUN_EMA_ALPHA`, and
`CAPTURE_CENTER` are NOT searched; they stay at their `sandkings` defaults
(`5*BIOME_TICK`, `0.25`, `0.5`). The tool never writes them.

**FC2.2 — The bounds constant table (rote, place at module top).**

```python
BOUNDS = {
    'SUN_JITTER_SD': (0.0, 3.0),   # daylight-hours noise SD; sun domain ~4..20
    'SUN_OSC_AMP':   (0.0, 6.0),   # daylight-hours swing amplitude
    'CAPTURE_TEMP':  (0.0, 0.4),   # metric power_ratio in [0,1] -> SMALL temp (SP9 lesson)
    'BARGAIN_TEMP':  (0.0, 5.0),   # metric EV differences, larger scale
}
KNOB_ORDER = ('SUN_JITTER_SD', 'SUN_OSC_AMP', 'CAPTURE_TEMP', 'BARGAIN_TEMP')
BASELINE_VECTOR = (0.0, 0.0, 0.0, 0.0)   # the inert default (all four identity)
```

`KNOB_ORDER` fixes the tuple index → global-name mapping for every read/write and
for the checkpoint hash; the vector is ALWAYS `(SUN_JITTER_SD, SUN_OSC_AMP,
CAPTURE_TEMP, BARGAIN_TEMP)` in that order.

---

## FC3 — Structural: the objective (three normalized components, equal-weighted)

OBJECTIVE is a scalar in `[0,1]` to **MAXIMIZE**, computed over one sim episode from
telemetry, as a weighted sum of three components each normalized to `[0,1]`.

**FC3.1 — Weights (named constants; default `1/3` each; sum to `1.0`).**

```python
W_LIVE = 1.0 / 3.0    # weight of LIVENESS
W_DIV  = 1.0 / 3.0    # weight of MODE_DIVERSITY
W_VAR  = 1.0 / 3.0    # weight of WEATHER_VARIANCE
# INVARIANT: W_LIVE + W_DIV + W_VAR == 1.0 (each component in [0,1] => OBJECTIVE in [0,1])
```

**FC3.2 — LIVENESS (surviving, non-collapsed ecology).**
```
liveness = len([c for c in sim.colonies if c.is_alive()]) / len(sim.colonies)
```
Already in `[0,1]` (final alive fraction). No further normalization.

**FC3.3 — MODE_DIVERSITY (variety of bargain modes, not a monoculture).**
Aggregate bargain-mode counts over the sampled snapshots (`sim._bargain_modes()`
returns `{frozenset({a_id,b_id}): mode_str}`; take `.values()`), then normalized
Shannon entropy over the **k = 4 feasible modes**:
```
FEASIBLE_MODES = (BARGAIN_MODE_NONE, BARGAIN_MODE_WAGE,
                  BARGAIN_MODE_SUBJUGATE, BARGAIN_MODE_ANNIHILATE)   # k = 4
total = sum(mode_counts[m] for m in mode_counts)
if total <= 0:                       # no pairs ever observed -> no diversity signal
    diversity = 0.0
else:
    H = -Σ_{c>0} (c/total) * ln(c/total)      # natural-log Shannon entropy
    diversity = H / ln(k)                      # normalized by ln(4); max entropy => 1.0
```
Normalizing by `ln(k)` keeps `diversity ∈ [0,1]` (max `H == ln(k)` under a uniform
mix over the 4 modes). A monoculture (all pairs one mode) → `H == 0` → `0.0`.

**FC3.4 — WEATHER_VARIANCE (oscillator+jitter actually varies the sky).**
Population variance of the sampled `sim.sun_effective` series, squashed into `[0,1]`
by a reference variance:
```
WEATHER_VAR_REF = 1.0    # hours^2; squash reference (v == ref -> 0.5); tunable
if len(sun_series) < 2:
    variance = 0.0
else:
    v = float(np.var(sun_series))          # population variance (ddof=0)
    variance = v / (v + WEATHER_VAR_REF)   # in [0,1); monotone increasing; 0 at v==0
```
A flatline (all `sun_effective` equal → `v == 0`) → `0.0`; more day-to-day swing →
closer to `1.0`.

**FC3.5 — The scalar.**
```
OBJECTIVE = W_LIVE*liveness + W_DIV*diversity + W_VAR*variance     # in [0,1]
```

**Provenance.** The FITTED values of the four knobs are `[prov:B
fit=fit_constants.py]` — that is the entire point: this tool is their provenance.
`WEATHER_VAR_REF`, `W_LIVE/W_DIV/W_VAR`, and the bounds are design choices of the
demonstrator, `[prov:C feel=demonstrator-scaling]`; do NOT fabricate literature
citations for them. `FEASIBLE_MODES` and the Shannon/`ln(k)` normalization are the
standard normalized-entropy diversity index, `[prov:A lit=Shannon entropy /
evenness index]`.

---

## FC4 — Structural: module functions (signatures + contracts)

All functions live in `fit_constants.py`. `import sandkings as sk` after the
headless env line (FC10). `random`, `numpy as np`, `math`, `sqlite3`, `hashlib`,
`os` at module top.

**FC4.1 — `objective_components(alive_frac, mode_counts, sun_series) -> (float, float, float)`**
Pure function of already-collected telemetry (no sim, no RNG), so it is unit-testable
in isolation.
- **Require** — `alive_frac ∈ [0,1]`; `mode_counts` a dict over `FEASIBLE_MODES`
  (counts `>= 0`); `sun_series` a list of floats.
- **Guarantee** — returns `(liveness, diversity, variance)`, each in `[0,1]`,
  finite; consumes NO RNG; mutates nothing. Empty/degenerate inputs map to the
  documented floors (`diversity=0.0` when `total<=0`, `variance=0.0` when
  `len(sun_series)<2`).
- **Assert** — `0.0 <= each <= 1.0`; a monoculture `mode_counts` → `diversity==0.0`;
  a constant `sun_series` → `variance==0.0`.

**FC4.2 — `objective_scalar(liveness, diversity, variance) -> float`**
- **Guarantee** — returns `W_LIVE*liveness + W_DIV*diversity + W_VAR*variance`,
  in `[0,1]` when the inputs are; pure.
- **Assert** — `objective_scalar(0,0,0)==0.0`; `objective_scalar(1,1,1)==1.0`.

**FC4.3 — `run_episode(vector, seed, steps=STEPS, sample=SAMPLE) -> (float, dict, list)`**
Constructs and steps ONE fresh seeded episode, returns raw telemetry
`(alive_frac, mode_counts, sun_series)`. This is the ONLY function that constructs a
sim. Sets the arc-enable globals and the four knobs from `vector` BEFORE construction.
- **Require** — `vector` a 4-tuple ordered per `KNOB_ORDER`; `seed` an int; the
  seven globals may be freely overwritten (caller restores them, FC7).
- **Guarantee** — seeds `random` AND `np.random` with `seed`; sets
  `sk.BARGAIN_ENABLED=True`, `sk.WAGE_ENABLED=True`,
  `sk.CAPTURE_CHANCE=sk.BARGAIN_CAPTURE_CHANCE`, and the four knobs to `vector`;
  constructs `SandKingsSimulation(width=80,height=48,depth=16,num_colonies=4)` with
  `bargain_enabled=True`, `keeper_auto=True`; steps `steps` times sampling every
  `sample` steps; returns telemetry. Deterministic given `(vector, seed)`.
- **Maintain** — SELF-restores the seven guarded globals in its OWN `finally`
  (leak-safe per episode): every entry point — a direct call, `evaluate_candidate`,
  `run_search`, or `fit` — is clean on its own, not only `fit`. This is load-bearing
  in the single-process battery, where a leaked knob would break sibling suites'
  identity tests. Reads `sim.sun_effective` getattr-guarded.

**FC4.4 — `evaluate_episode(vector, seed, conn) -> (float, float, float, float)`**
Checkpoint-guarded single-episode evaluation returning `(liveness, diversity,
variance, objective)`.
- **Require** — `conn` an open sqlite connection with the FC5 schema.
- **Guarantee** — on a checkpoint HIT (row for `(vector_hash(vector), seed)` exists)
  returns the cached tuple and does NOT call `run_episode` (increments no run
  counter). On a MISS, increments `_EPISODE_RUNS`, calls `run_episode`, computes the
  components + scalar, INSERTs the row, and returns them. Idempotent (FC-5).
- **Assert** — the returned `objective == objective_scalar(liveness, diversity,
  variance)` (float-equal within read/write round-trip tolerance).

**FC4.5 — `evaluate_candidate(vector, seeds, conn) -> (float, tuple)`**
Averages the objective (and components) over `N_SEEDS >= 3` distinct seeded
episodes — the stochastic-eval discipline (one episode is noise; the quality gate is
`>= 3` varied inputs).
- **Require** — `seeds` a list of `>= 1` distinct ints (production default `N_SEEDS>=3`).
- **Guarantee** — returns `(avg_objective, (avg_liveness, avg_diversity,
  avg_variance))`, each the arithmetic mean over `seeds` of `evaluate_episode`;
  deterministic given `(vector, seeds)` (FC-1).

**FC4.6 — `run_search(n_iters=N_ITERS, seeds=None, conn=None) -> (tuple, float, tuple, list)`**
Keep-if-improved hill-climb from the inert baseline.
- **Require** — `conn` open; `n_iters >= 0`.
- **Guarantee** — returns `(incumbent_vector, incumbent_objective,
  incumbent_components, trajectory)`; the incumbent starts at `BASELINE_VECTOR` and
  is replaced ONLY when a candidate's averaged objective is **strictly greater**, so
  `incumbent_objective >= baseline_objective` (FC-4). Persists the final incumbent to
  the `incumbent` table.
- **Maintain** — proposal RNG is a dedicated `random.Random(SEARCH_SEED)` instance,
  SEPARATE from the module `random` that episodes reseed — so proposed candidates are
  reproducible and unaffected by episode reseeding (FC-1 correctness).

**FC4.7 — `vector_hash(vector) -> str`** (checkpoint key helper)
- **Guarantee** — a stable hex digest of the vector rounded to fixed precision, so
  float noise does not fragment cache keys:
  `hashlib.sha1(('|'.join('%.6f' % x for x in vector)).encode()).hexdigest()`.
  Pure; identical vectors → identical hash.

---

## FC5 — Structural: the sqlite checkpoint (load-if-exists, idempotent)

A single sqlite file `fit_constants.db` (default; CLI-overridable path). Mirrors the
repo's load-if-exists checkpoint discipline: an evaluated `(vector, seed)` is never
recomputed.

```sql
CREATE TABLE IF NOT EXISTS episodes (
    param_hash TEXT NOT NULL,     -- vector_hash(vector)
    seed       INTEGER NOT NULL,
    liveness   REAL NOT NULL,
    diversity  REAL NOT NULL,
    variance   REAL NOT NULL,
    objective  REAL NOT NULL,
    PRIMARY KEY (param_hash, seed)
);
CREATE TABLE IF NOT EXISTS incumbent (
    id            INTEGER PRIMARY KEY CHECK (id = 1),   -- single row, upserted
    sun_jitter_sd REAL NOT NULL,
    sun_osc_amp   REAL NOT NULL,
    capture_temp  REAL NOT NULL,
    bargain_temp  REAL NOT NULL,
    objective     REAL NOT NULL
);
```

- **Read** (`evaluate_episode` HIT): `SELECT liveness, diversity, variance, objective
  FROM episodes WHERE param_hash=? AND seed=?`. A returned row short-circuits the sim.
- **Write** (`evaluate_episode` MISS): `INSERT OR REPLACE INTO episodes (...)`.
- **Incumbent write** (end of `run_search`): `INSERT OR REPLACE INTO incumbent
  (id, sun_jitter_sd, sun_osc_amp, capture_temp, bargain_temp, objective) VALUES
  (1, ?, ?, ?, ?, ?)`.
- **Idempotency (FC-5):** a module-level counter `_EPISODE_RUNS` is incremented ONLY
  on a cache miss (inside `evaluate_episode` before calling `run_episode`); tests
  assert it does not advance on a re-evaluation of the same `(vector, seed)`, and/or
  that `SELECT COUNT(*) FROM episodes` does not grow.

---

## FC6 — Behavioral: `run_episode` (rote pseudocode)

```python
_EPISODE_RUNS = 0    # module-level; number of sims actually stepped (cache-miss counter)

def run_episode(vector, seed, steps=None, sample=None):
    """Run ONE fresh seeded headless episode; return (alive_frac, mode_counts, sun_series).

    Preconditions: vector ordered per KNOB_ORDER.
    Budgets: steps/sample default to None and RESOLVE to the module STEPS/SAMPLE at
      CALL time (not def time), so a module-global override (fit_constants.STEPS=..)
      propagates through the whole eval/search chain -- this is how the cheap FC tests
      run without threading a budget through every caller.
    State hygiene: SELF-restores the seven guarded globals in a finally (leak-safe per
      episode; see the Maintain contract). Every entry point is clean on its own.
    Failure modes: none swallowed (fail-fast); a construction/step error propagates
      AND the finally still restores the globals.
    """
    import sandkings as sk
    if steps is None:  steps = STEPS
    if sample is None: sample = SAMPLE
    # (1) SEED both module streams FIRST (playtest_economy.py pattern) — determinism.
    random.seed(seed)
    np.random.seed(seed)
    saved = _save_globals(sk)              # capture BEFORE mutating (leak-safe per episode)
    try:
        # (2) ENABLE the arc exactly like playtest_economy.py.
        sk.BARGAIN_ENABLED = True
        sk.WAGE_ENABLED = True
        sk.CAPTURE_CHANCE = sk.BARGAIN_CAPTURE_CHANCE  # > 0 so CAPTURE_TEMP has effect
        # (3) SET the four searched knobs from the candidate vector (index per KNOB_ORDER).
        sk.SUN_JITTER_SD = float(vector[0])
        sk.SUN_OSC_AMP   = float(vector[1])
        sk.CAPTURE_TEMP  = float(vector[2])
        sk.BARGAIN_TEMP  = float(vector[3])
        # (4) CONSTRUCT the sim AFTER globals are set; ... step; collect telemetry; return.
        # (full body: step `steps`, sample every `sample`, return (alive_frac,counts,series))
    finally:
        _restore_globals(sk, saved)        # LOAD-BEARING: always restore, per episode
    sim = sk.SandKingsSimulation(width=80, height=48, depth=16, num_colonies=4)
    sim.bargain_enabled = True
    sim.keeper_auto = True
    # (5) STEP, sampling telemetry every `sample` steps.
    mode_counts = {m: 0 for m in sk_feasible_modes(sk)}     # {mode_str: 0} for the 4 modes
    sun_series = []
    for step in range(steps):
        sim.step()
        if step % sample == 0:
            for m in sim._bargain_modes().values():
                mode_counts[m] = mode_counts.get(m, 0) + 1
            sun_series.append(float(getattr(sim, 'sun_effective', sk.SUN_HOURS_DEFAULT)))
    # (6) FINAL liveness.
    total_colonies = len(sim.colonies)
    alive = len([c for c in sim.colonies if c.is_alive()])
    alive_frac = (alive / total_colonies) if total_colonies > 0 else 0.0
    return alive_frac, mode_counts, sun_series
```

Where `sk_feasible_modes(sk)` returns the tuple `(sk.BARGAIN_MODE_NONE,
sk.BARGAIN_MODE_WAGE, sk.BARGAIN_MODE_SUBJUGATE, sk.BARGAIN_MODE_ANNIHILATE)` — or
inline that tuple. `mode_counts.get(m, 0)+1` tolerates any unexpected mode string
(a mode not in the seeded dict simply becomes a new key; normalization divides by
the observed `total`, so out-of-set keys still contribute to entropy over whatever
`k` you normalize by — keep `k = len(FEASIBLE_MODES) = 4` fixed for a stable ceiling).

**Subtle spot flagged:** `sim.sun_effective` updates only once per `BIOME_TICK`
(20 steps). WEATHER_VARIANCE is only meaningful when `steps >> BIOME_TICK` (the
default `STEPS=800` spans ~40 biome-days). At the smoke-test `STEPS=60` the variance
signal is weak but the component is still well-defined and finite — the cheap test
(FC-2) asserts finiteness/range, not a specific variance magnitude.

---

## FC7 — Behavioral: `evaluate_episode`, `evaluate_candidate`, `run_search`, state hygiene

**FC7.1 — `evaluate_episode` (checkpoint-guarded).**
```python
def evaluate_episode(vector, seed, conn):
    global _EPISODE_RUNS
    h = vector_hash(vector)
    row = conn.execute(
        "SELECT liveness, diversity, variance, objective FROM episodes "
        "WHERE param_hash=? AND seed=?", (h, seed)).fetchone()
    if row is not None:
        return (row[0], row[1], row[2], row[3])          # CACHE HIT — no sim run
    _EPISODE_RUNS += 1                                    # CACHE MISS — sim will run
    alive_frac, mode_counts, sun_series = run_episode(vector, seed)
    l, d, v = objective_components(alive_frac, mode_counts, sun_series)
    obj = objective_scalar(l, d, v)
    conn.execute(
        "INSERT OR REPLACE INTO episodes "
        "(param_hash, seed, liveness, diversity, variance, objective) "
        "VALUES (?,?,?,?,?,?)", (h, seed, l, d, v, obj))
    conn.commit()
    return (l, d, v, obj)
```

**FC7.2 — `evaluate_candidate` (average over the seed set).**
```python
def evaluate_candidate(vector, seeds, conn):
    ls = ds = vs = objs = 0.0
    n = len(seeds)
    acc_l = acc_d = acc_v = acc_o = 0.0
    for s in seeds:
        l, d, v, o = evaluate_episode(vector, s, conn)
        acc_l += l; acc_d += d; acc_v += v; acc_o += o
    return (acc_o / n, (acc_l / n, acc_d / n, acc_v / n))
```

**FC7.3 — `run_search` (keep-if-improved hill-climb).**
```python
SEARCH_SEED = 12345    # proposal RNG seed — SEPARATE from episode seeds (determinism)

def _propose(proposer):
    """One random candidate uniformly within BOUNDS (proposer is a private Random)."""
    return tuple(proposer.uniform(*BOUNDS[name]) for name in KNOB_ORDER)

def run_search(n_iters=N_ITERS, seeds=None, conn=None):
    if seeds is None:
        seeds = list(range(N_SEEDS))            # e.g. [0,1,2]
    proposer = random.Random(SEARCH_SEED)       # PRIVATE instance — not module `random`
    incumbent = BASELINE_VECTOR                 # start at the inert default (0,0,0,0)
    inc_obj, inc_comps = evaluate_candidate(incumbent, seeds, conn)
    trajectory = [(incumbent, inc_obj)]
    for _ in range(n_iters):
        cand = _propose(proposer)
        cand_obj, cand_comps = evaluate_candidate(cand, seeds, conn)
        if cand_obj > inc_obj:                  # STRICTLY greater -> keep (never regress)
            incumbent, inc_obj, inc_comps = cand, cand_obj, cand_comps
        trajectory.append((incumbent, inc_obj))
    conn.execute(
        "INSERT OR REPLACE INTO incumbent "
        "(id, sun_jitter_sd, sun_osc_amp, capture_temp, bargain_temp, objective) "
        "VALUES (1,?,?,?,?,?)", (incumbent[0], incumbent[1], incumbent[2],
                                 incumbent[3], inc_obj))
    conn.commit()
    return incumbent, inc_obj, inc_comps, trajectory
```

**FC7.4 — State hygiene wrapper (the load-bearing Require/Guarantee, FC-3).**
The seven touched globals are SAVED before any search and RESTORED in a `finally` —
so the tool never leaves `sandkings`' module state mutated, even on exception.

```python
_GUARDED_GLOBALS = ('SUN_JITTER_SD', 'SUN_OSC_AMP', 'CAPTURE_TEMP', 'BARGAIN_TEMP',
                    'BARGAIN_ENABLED', 'WAGE_ENABLED', 'CAPTURE_CHANCE')

def _save_globals(sk):
    return {name: getattr(sk, name) for name in _GUARDED_GLOBALS}

def _restore_globals(sk, saved):
    for name, val in saved.items():
        setattr(sk, name, val)

def fit(n_iters=N_ITERS, n_seeds=N_SEEDS, db_path=DB_PATH):
    """Top-level entry: save globals, run the search, ALWAYS restore, report.

    Guarantee (FC-3): on return OR exception, every _GUARDED_GLOBALS entry equals
    its pre-call value. The ONLY durable side effect is the sqlite checkpoint file.
    """
    import sandkings as sk
    saved = _save_globals(sk)
    conn = _open_checkpoint(db_path)            # CREATE TABLE IF NOT EXISTS (FC5)
    try:
        base_obj, base_comps = evaluate_candidate(BASELINE_VECTOR, list(range(n_seeds)), conn)
        incumbent, inc_obj, inc_comps, trajectory = run_search(
            n_iters=n_iters, seeds=list(range(n_seeds)), conn=conn)
        _report(base_obj, base_comps, incumbent, inc_obj, inc_comps)   # FC8 table
        return incumbent, inc_obj, base_obj
    finally:
        _restore_globals(sk, saved)             # LOAD-BEARING: always restore
        conn.close()
```

**Subtle spot flagged (state restoration) — RECONCILED:** `run_episode` self-restores
the seven guarded globals in its OWN `finally`, so EVERY entry point is leak-safe — a
direct call to `run_episode`/`evaluate_candidate`/`run_search` cannot leak a fitted
knob into sibling code (critical because the single-process battery runs
`test_fit_constants` before other suites, and a leaked non-zero `SUN_OSC_AMP`/
`SUN_JITTER_SD` would break their identity tests). `fit`'s outer save/restore `finally`
is RETAINED as defense-in-depth. The FC-3 test asserts the seven globals are back to
pre-run values after both `fit(...)` and a direct `run_search(...)`.

---

## FC8 — Behavioral: the report (inert baseline vs fitted incumbent)

`_report(...)` prints a table comparing the inert baseline's objective (and its three
components) to the fitted incumbent's, plus the fitted vector. It writes NOTHING to
`sandkings.py` — adoption is a human decision, stated explicitly in the printed
footer.

```
==== fit_constants: learned vs inert (demonstrator; sandkings.py UNCHANGED) ====
                    OBJECTIVE   LIVENESS   MODE_DIV   WEATHER_VAR
  inert  (0,0,0,0)     <b>        <bl>       <bd>        <bv>
  fitted incumbent     <i>        <il>       <id>        <iv>
  fitted vector = SUN_JITTER_SD=<..>  SUN_OSC_AMP=<..>  CAPTURE_TEMP=<..>  BARGAIN_TEMP=<..>
  NOTE: this is a REPORT. Adopting these values into sandkings.py is a human decision.
================================================================================
```

The incumbent is also persisted to the `incumbent` table (FC5). `run_search`'s
`trajectory` (incumbent objective per iteration) may be printed as a one-line
progression for observability.

---

## FC9 — Security (Require)

- **Pure numeric, in-process only.** The tool sets numeric `sandkings` module
  globals, reads sim telemetry (`sim.colonies`, `c.is_alive()`,
  `sim._bargain_modes()`, `sim.sun_effective`), and computes an objective.
- **NO** `eval`/`exec`, **NO** host codegen, **NO** sockets, **NO** network, **NO**
  subprocess, **NO** dynamic import of untrusted names.
- **The ONLY filesystem write** is the sqlite checkpoint file (`DB_PATH`, default
  `fit_constants.db`). No other file is created or modified. `sandkings.py` is never
  written.
- Imports are limited to `os`, `random`, `math`, `hashlib`, `sqlite3`, `numpy`, and
  `sandkings` (plus stdlib `argparse` if a CLI is added).

---

## FC10 — Headless

Set the dummy video driver at the VERY TOP of the module, BEFORE importing
`sandkings` (which may transitively import pygame), so the tool runs without a
display (the repo's Docker run sets `SDL_VIDEODRIVER=dummy`; this makes the tool
safe standalone too):

```python
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')   # headless BEFORE importing sandkings
import random, math, hashlib, sqlite3
import numpy as np
import sandkings as sk
```

---

## FC11 — Constants & invocation defaults

```python
N_ITERS = 8      # search proposals per run (smoke default; scale up for a real fit)
N_SEEDS = 3      # distinct seeded episodes per candidate (>=3 = quality-gate minimum)
STEPS   = 800    # sim steps per episode (~40 biome-days; scale up for stronger signal)
SAMPLE  = 50     # telemetry sampling cadence (steps)
DB_PATH = 'fit_constants.db'
WEATHER_VAR_REF = 1.0
SEARCH_SEED = 12345
```

**FC11.1 — Cost note.** The defaults (`8 * (1 + N_SEEDS) ~= 32` episodes of 800
steps, minus cache hits on the repeated baseline) are tuned for a ~couple-minute
demonstrator. For a real fit, raise `N_ITERS` (more proposals), `N_SEEDS` (tighter
average), and `STEPS` (stronger weather/diversity signal); the checkpoint makes
re-runs cheap by skipping already-evaluated `(vector, seed)` pairs.

**FC11.2 — Invocation.**
- Host (use a Python 3.10 interpreter with the deps installed):
  `python fit_constants.py`
- Docker (sandking image, `SDL_VIDEODRIVER=dummy` already set): run the module the
  same way inside the container.
- Optional `argparse` CLI exposing `--n-iters`, `--n-seeds`, `--steps`, `--db`;
  `__main__` calls `fit(...)` with the parsed budgets. In a `SPAWNED_SESSION` the
  defaults are used with no prompt.

---

## FC12 — Acceptance (`tests/test_fit_constants.py`, kept CHEAP)

Tests import the functions directly and drive them with tiny budgets
(`N_ITERS=2, N_SEEDS=2, STEPS=60, SAMPLE=20`) so the file joins the battery cheaply.
Seed both streams like `playtest_economy.py` where a full episode runs. **Fail-fast:
no `try/except`-with-fallback in tests.** Each test opens its OWN temp checkpoint
(e.g. an in-memory or `tmp_path` sqlite) so cases are isolated.

1. **FC-1 — DETERMINISTIC OBJECTIVE.** For a FIXED vector (e.g. `(0.5, 1.0, 0.1, 1.0)`)
   and a FIXED seed set (e.g. `[0, 1]`), call `evaluate_candidate(v, seeds, conn)`
   TWICE (fresh conn each time so neither reads the other's cache) and assert the two
   averaged objectives are equal (float-equal). Proves reproducibility (separate
   proposal RNG, seeded episodes, no hidden entropy).
2. **FC-2 — BOUNDED & FINITE.** Run one episode at the inert baseline
   `(0,0,0,0)` (tiny STEPS), compute `objective_components(...)`; assert each of
   `(liveness, diversity, variance)` is `math.isfinite` and in `[0.0, 1.0]`, and
   `objective_scalar(...)` is in `[0.0, 1.0]`. Also assert the degenerate-input
   floors directly: `objective_components(1.0, {NONE:5}, [12,12,12])` gives
   `diversity==0.0` (monoculture) and `variance==0.0` (constant series); a uniform
   `mode_counts` over the 4 modes gives `diversity==1.0` (float tolerance).
3. **FC-3 — STATE HYGIENE (load-bearing).** Record the seven `_GUARDED_GLOBALS` from
   `sandkings` BEFORE the run. Call `fit(n_iters=2, n_seeds=2, db_path=<tmp>)` (or
   `run_search` wrapped in the same save/restore). AFTER it returns, assert
   `sandkings.SUN_JITTER_SD`, `SUN_OSC_AMP`, `CAPTURE_TEMP`, `BARGAIN_TEMP`,
   `BARGAIN_ENABLED`, `WAGE_ENABLED`, `CAPTURE_CHANCE` each equal their recorded
   pre-run values. (Optional: also assert restoration holds after an INDUCED
   exception mid-search — monkeypatch `run_episode` to raise on the 2nd call and
   assert the `finally` still restored all seven.)
4. **FC-4 — NEVER REGRESSES.** Call `run_search(n_iters=2, seeds=[0,1], conn=...)`;
   evaluate the inert baseline separately with the SAME seeds; assert the returned
   `incumbent_objective >= baseline_objective` (keep-if-improved never drops below
   the starting incumbent). Assert the first `trajectory` entry is the baseline vector.
5. **FC-5 — CHECKPOINT IDEMPOTENCY.** With a fresh conn, call
   `evaluate_episode(v, seed, conn)` once (records `_EPISODE_RUNS` before/after → +1,
   one row inserted), then call it AGAIN with the same `(v, seed, conn)`; assert
   `_EPISODE_RUNS` did NOT advance on the second call AND `SELECT COUNT(*) FROM
   episodes` is unchanged (cache hit, no recompute). Assert the second call's
   returned tuple equals the first's.

**Test design note.** The tool is built as importable functions
(`objective_components`, `objective_scalar`, `run_episode`, `evaluate_episode`,
`evaluate_candidate`, `run_search`, `fit`, `vector_hash`) so tests call them with
tiny budgets — never only via `__main__`. Budgets are passed as arguments
(`steps=`, `n_iters=`, `seeds=`) or via monkeypatching the module constants at the
top of each test and restoring them in a `finally`.

---

## Status / Reconciliation

- **Drafted 2026-07-11. Spec-first: implementation pending.** A NEW data-side tool
  `fit_constants.py` (+ `tests/test_fit_constants.py`) — a learned demonstrator that
  searches the four semi-permeable knobs against a healthy-ecology objective and
  REPORTS fitted-vs-inert. It does NOT edit `sandkings.py`.
- **Grounding plan Tier-2.** Turns "`0.15`" from a magic constant into "the best of a
  keep-if-improved search," giving the four knobs `[prov:B fit=fit_constants.py]`
  provenance. Adoption of any fitted value is a downstream human decision.
- **Reuses, does not duplicate:** the `playtest_economy.py` eval-harness pattern
  (seed both streams, enable the arc, construct at `80x48x16`/`num_colonies=4`, step,
  read `sim.colonies`/`is_alive`/`_bargain_modes`/`sun_effective`), the repo sqlite
  load-if-exists checkpoint discipline, and the SP7/SP9/SP10/SP11 identity-default
  contracts (the four knobs are inert at `0.0`).
- **Correctness subtleties flagged:** (a) proposal RNG is a SEPARATE
  `random.Random(SEARCH_SEED)` from the episode-seeding module `random`; (b)
  `CAPTURE_CHANCE` must be `> 0` for `CAPTURE_TEMP` to have any effect (set via the
  arc-enable); (c) `sun_effective` updates once per `BIOME_TICK` so WEATHER_VARIANCE
  needs `STEPS >> 20`; (d) state restoration is per-episode in
  `run_episode`'s own `finally` (leak-safe at EVERY entry point — the load-bearing
  FC-3 guarantee; `fit`'s outer `finally` is defense-in-depth); (e) `CAPTURE_TEMP` bound is SMALL (`[0,0.4]`)
  because its metric `power_ratio ∈ [0,1]` (the SP9 temp-scale lesson).
- **Anchors verified against `sandkings.py` (2026-07-11):** constructor
  `SandKingsSimulation.__init__:1511` (`width,height,depth,num_colonies,canon`);
  knobs `SUN_JITTER_SD:224`, `SUN_OSC_AMP:225`, `SUN_OSC_PERIOD:226`,
  `SUN_EMA_ALPHA:227`, `CAPTURE_CHANCE:328`, `CAPTURE_CENTER:330`, `CAPTURE_TEMP:331`,
  `WAGE_ENABLED:347`, `BARGAIN_ENABLED:382`, `BARGAIN_CAPTURE_CHANCE:383`,
  `BARGAIN_TEMP:396`; telemetry `sun_effective` init `:1532`, `_bargain_modes:4476`
  (returns `{frozenset: mode_str}`), `BARGAIN_MODE_*:377–380`,
  `SUN_HOURS_DEFAULT:221`; harness pattern `playtest_economy.py:11–28`.
```
