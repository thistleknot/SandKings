# SPEC: Semi-Permeable Parameters — learnable soft params + the daylight tracer (SP1–SP11)

A reusable **semi-permeable parameter** primitive plus ONE tracer application
(daylight). The terrarium today is mostly frozen constants and hard `if metric >
C` gates; this makes selected parameters **semi-permeable** — a scalar becomes a
distribution the sim draws from, a hard gate becomes a soft (logistic)
probability — so the world reacts and responds with RL-like give instead of
brittle rules. The primitive is designed so its **neutral defaults reproduce
today's behaviour byte-for-byte** (the 41-suite battery stays green), and so the
soft params can later be **evolved / fit** exactly like `ColonyGenome.brain_hidden`.

> **What this ADDS vs what it REUSES (read first).**
> - **ADDS** two module-level pure functions (`jitter`, `soft_gate`) and two
>   tiny learnable-holder dataclasses (`DistParam`, `GateParam`); one new
>   per-sim field `sun_effective`; one constant `SUN_JITTER_SD` (defaults `0.0`);
>   a once-per-biome-day daylight draw inside `_biome_tick`.
> - **ADDS (SP9)** a third pure module-level function (`power_ratio`), a pure
>   count helper method (`_dominance_counts`), a mode-switch in `_try_capture`,
>   and two constants (`CAPTURE_CENTER`, `CAPTURE_TEMP`, both default identity) —
>   migrating the frozen capture coin-flip to the `soft_gate` membrane.
> - **ADDS (SP10)** an OSCILLATOR-driven, self-normalizing daylight signal that
>   GROWS the SP5 flat per-day Gaussian draw: the per-day mean swings around the
>   keeper setpoint (`SUN_OSC_AMP`, `SUN_OSC_PERIOD`), and a pure EMA observer
>   (`sun_ema_mean`, `sun_ema_sd`, smoothed by `SUN_EMA_ALPHA`) tracks a rolling
>   mean/sigma for a NEW normalized read `z`. Two new observer fields, three new
>   constants, one pure read helper. `SUN_OSC_AMP == 0.0` (default) is identity —
>   the oscillator term is `0.0` and the EMA consumes ZERO RNG, so the battery
>   stays byte-identical. The one-way `sun → water` (`SUN_DRYING`) edge is
>   preserved and NO `water → sun` edge is added (the graph stays ACYCLIC).
> - **ADDS (SP11)** a temperature-controlled Boltzmann softmax over the three
>   bargain-mode EVs: one constant `BARGAIN_TEMP` (default `0.0` = identity / hard
>   argmax) and a mode switch in `_bargain_pair_mode` — the semi-permeable
>   membrane applied to a discrete CHOICE (softmax) rather than a scalar (`jitter`)
>   or a binary gate (`soft_gate`). Default routes to the EXACT pre-SP11 argmax
>   (ZERO RNG, byte-identical battery); `> 0` samples the mode with
>   `P(mode) ∝ exp(EV_mode / BARGAIN_TEMP)`.
> - **REUSES** the existing seeded module RNG streams (`random` + `np.random`,
>   seeded by tests / `play_kit` at construction), the `_clamp01` module-helper
>   convention (`sandkings.py:526`), and the whole `BIOME_TICK` weather cadence
>   (`:222`) as the day boundary — no new cadence constant. SP10 additionally
>   REUSES the existing `EPS_POWER = 1e-9` divisor guard (`:365`) — no new EPS.
> - **CHANGES nothing at neutral.** `SUN_JITTER_SD == 0.0` and `temp <= 0` make
>   every effect the identity transform; the primitive consumes **zero RNG** at
>   neutral, so the shared draw stream is byte-identical and `--canon` reruns
>   match today exactly. SP9 keeps this: `CAPTURE_TEMP == 0.0` is the byte-for-byte
>   flat-gate identity path. SP10 keeps this: `SUN_OSC_AMP == 0.0` makes the swing
>   term `0.0` and the EMA is pure arithmetic (no RNG), so the stream is unmoved.
>   SP11 keeps this: `BARGAIN_TEMP == 0.0` routes to the exact hard argmax and
>   draws NO RNG, so the bargain-mode selection is byte-identical.

Layer: **Requirements + Structural + Behavioral.** Observable soft-param
behaviour (requirements), two pure primitives + holders + contracts
(structural), and the ordered once-per-day daylight draw wired into `_biome_tick`
with its readers (behavioral).

---

## SP1 — Requirements (the two forms + the four hard contracts)

The primitive comes in exactly **two forms**:

- **Form 1 — DISTRIBUTIONAL SCALAR.** A frozen constant `C` becomes a draw
  `X ~ N(mean, sd)` clipped to `[lo, hi]`. Implemented by `jitter(...)`.
- **Form 2 — SOFT GATE.** A hard `if metric > C` becomes
  `P(act) = logistic((metric − center) / temp)`; the caller then draws
  `rng.random() < P`. Implemented by `soft_gate(...)`.

| # | Requirement | Acceptance criterion (mechanically checkable) |
|---|---|---|
| SP1.1 | **Determinism / canon** | Both forms draw ONLY from the caller-supplied `rng` (default: module `random`, which tests/`play_kit` seed at construction). No `default_rng()`, no fresh unseeded Generator, no time/OS entropy. Two runs with the same seed + same `sd>0` produce identical draw sequences (SPA-6). |
| SP1.2 | **Identity at neutral** | `jitter` with `sd <= 0` returns `float(mean)` and consumes **zero** RNG draws; `soft_gate` with `temp <= 0` is a hard step (`1.0` iff `metric > center`, else `0.0`). At the neutral defaults every existing test stays byte-identical (SPA-1). |
| SP1.3 | **Learnable hook** | `mean/sd` (Form 1) and `center/temp` (Form 2) are carried by a per-param holder (`DistParam` / `GateParam`) that can be swapped for an evolved/fit instance without touching call-sites — the seam, not the genome integration, is in scope. |
| SP1.4 | **Security** | Pure numeric, in-process only. No host codegen, no `eval`/`exec`, no sockets, no filesystem, no network, no subprocess. The two functions import only `math`/`random` and read their arguments. |

**Tracer scope (SP1.5).** Exactly ONE application lands in this spec: **daylight**.
Today `sun_hours` is a fixed setpoint (`keeper_set_sun` clips to `[SUN_MIN=4,
SUN_MAX=20]`, default `SUN_HOURS_DEFAULT=12`) read directly by the crop-growth
and water-equilibrium code. This spec makes the *effective* per-day daylight a
Form-1 draw around that setpoint, drawn ONCE per biome-day so every reader in a
day sees the same sky. `SUN_JITTER_SD` defaults `0.0`, so the setpoint behaviour
is unchanged until someone (or evolution) dials variance in.

---

## SP2 — Structural: the two primitives (module-level, pure)

Placement: a new module-level block **immediately after `_clamp01`
(`sandkings.py:526`)** — the established home for pure numeric helpers. Both
functions are free functions (like `_clamp01`), callable unqualified from methods.

```python
def jitter(mean: float, sd: float = 0.0,
           lo: float = float('-inf'), hi: float = float('inf'),
           rng=random) -> float:
    """FORM 1 — distributional scalar: draw X ~ N(mean, sd), clipped to [lo, hi].

    Precondition:  rng provides .gauss(mu, sigma) (module `random` or a
                   random.Random instance — the SEEDED stream, never default_rng).
    Failure modes: none raised; sd<=0 short-circuits, lo>hi would clamp to hi.
    IDENTITY:      sd <= 0.0 returns float(mean) and DRAWS NOTHING (no rng call),
                   so the shared RNG stream is unperturbed (canon stays in sync).
    """
    if sd <= 0.0:
        return float(mean)                      # identity — NO draw consumed
    x = rng.gauss(mean, sd)                      # single draw from the seeded stream
    return float(min(max(x, lo), hi))            # clip to [lo, hi]


def soft_gate(metric: float, center: float, temp: float) -> float:
    """FORM 2 — soft gate: P(act) = logistic((metric - center) / temp), in [0,1].

    The CALLER draws rng.random() < P(act); this function is pure (no RNG here).
    Failure modes: none raised; overflow-safe logistic (branch on sign of z).
    IDENTITY:      temp <= 0.0 collapses to the hard step 1.0 if metric > center
                   else 0.0 — byte-for-byte the pre-existing `if metric > C` gate.
    """
    if temp <= 0.0:
        return 1.0 if metric > center else 0.0   # identity — hard threshold at center
    z = (metric - center) / temp
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)
```

**Contract (`jitter`):**
- **Require** — `rng` exposes `.gauss`; `rng` is a seeded stream (module `random`
  in this repo). Callers must NOT pass a fresh unseeded generator.
- **Guarantee** — `sd <= 0` ⇒ returns `float(mean)` and makes **no** RNG call
  (zero draws consumed); `sd > 0` ⇒ exactly ONE `rng.gauss` draw, result in
  `[lo, hi]`; pure w.r.t. all other state.
- **Maintain** — the number of RNG draws is `0` at `sd == 0` and `1` at `sd > 0`,
  deterministically — so draw-count is a pure function of `sd == 0` vs not.
- **Assert** — `sd == 0.0 ⇒ jitter(...) == float(mean)` (float-equal); `sd > 0 ⇒
  lo <= result <= hi`.

**Contract (`soft_gate`):**
- **Require** — `metric`, `center`, `temp` finite floats.
- **Guarantee** — returns a value in `[0.0, 1.0]`; `temp <= 0` ⇒ hard step
  (`1.0` iff `metric > center`); `temp > 0` ⇒ strictly monotone increasing in
  `metric`, crossing `0.5` exactly at `metric == center`; consumes NO RNG.
- **Maintain** — monotonicity: `metric_a < metric_b ⇒ soft_gate(a,..) <=
  soft_gate(b,..)` for any fixed `center, temp > 0`.
- **Assert** — `soft_gate(center, center, t>0) == 0.5`; `soft_gate(m, c, 0) ==
  (1.0 if m > c else 0.0)`.

**Import note (SP2.1).** Ensure `import math` and `import random` are present at
module top (both already imported in `sandkings.py`; no new dependency).

---

## SP3 — Structural: the learnable holders (the evolve/fit seam)

Two frozen-by-default dataclasses that carry a soft param's tunable numbers in ONE
place, so a call-site reads `param.draw(rng)` / `param.prob(metric)` and an
evolved instance can be substituted without touching the call-site. This is the
**seam** SP1.3 requires — NOT a genome integration (deferred).

```python
from dataclasses import dataclass

@dataclass
class DistParam:
    """Learnable holder for a FORM-1 distributional scalar. Swap for an evolved
    instance to make the scalar adaptive; default (sd=0) is identity."""
    mean: float
    sd: float = 0.0
    lo: float = float('-inf')
    hi: float = float('inf')
    def draw(self, rng=random) -> float:
        return jitter(self.mean, self.sd, self.lo, self.hi, rng)

@dataclass
class GateParam:
    """Learnable holder for a FORM-2 soft gate. Swap for an evolved instance to
    make the threshold adaptive; default (temp=0) is a hard step at center."""
    center: float
    temp: float = 0.0
    def prob(self, metric: float) -> float:
        return soft_gate(metric, self.center, self.temp)
```

Placement: directly beneath `jitter`/`soft_gate` (same module-level block).

**Seam convention (SP3.1 — where a param's `(mean, sd)` lives).** A semi-permeable
param's tunable pair lives at exactly one of two scopes, by intent:
- **per-sim** (this tracer): a module constant for the neutral value +
  a sim field for the *setpoint* (here `SUN_JITTER_SD` + `self.sun_hours`); the
  learnable seam is "construct a `DistParam(mean=self.sun_hours, sd=SUN_JITTER_SD,
  lo=SUN_MIN, hi=SUN_MAX)` at the draw site." Evolution later replaces the `sd`
  source with a fit/evolved value **without changing the draw call**.
- **per-colony** (future): store a `DistParam`/`GateParam` on the colony (the
  `ColonyGenome.brain_hidden` precedent) and read `colony.<param>.draw(rng)`.

Only the per-sim seam is exercised by this tracer; the per-colony path is
documented for the next application, not implemented.

**Contract (holders):**
- **Require** — constructed with finite `mean`/`center`; `sd >= 0`, `temp >= 0`.
- **Guarantee** — `DistParam(sd=0).draw()` returns `mean` (no RNG); `GateParam(
  temp=0).prob(m)` is the hard step — identity holders reproduce the constant.
- **Maintain** — a holder is the SINGLE source of a param's numbers; call-sites
  never inline `mean/sd/center/temp`.

---

## SP4 — Structural: the NEXT tracer seam (CAPTURE_CHANCE → soft_gate) — REALIZED BY SP9

> **STATUS: REALIZED by SP9 (drafted 2026-07-11).** This seam is no longer
> deferred. The `CAPTURE_CHANCE → soft_gate` migration is fully specified for
> rote implementation in **SP9 — Behavioral: the capture membrane** (below),
> which adds the `power_ratio` metric, the `CAPTURE_CENTER` / `CAPTURE_TEMP`
> constants, the `_try_capture` mode-switch, and acceptance criteria SPA-7…SPA-11.
> The original signature-validation prose below is **retained verbatim** as the
> design record that first bound the Form-2 signature to this second caller — it
> is marked realized, not deleted. Where SP4 says "DEFERRED / do not implement,"
> read "**superseded by SP9**"; where it cites line anchors `:4601` / `:4598`,
> read the corrected anchors in SP9 (the file has since drifted).

Originally specified so the **Form-2 signature is validated against a
real second caller** (proving `soft_gate(metric, center, temp)` binds to a live
metric, not just to daylight).

Today the capture gate (`sandkings.py:4601`) is a flat probability past three hard
gates:

```python
        if random.random() >= CAPTURE_CHANCE:      # (4) RNG reached ONLY past 1-3
            return False
```

The soft-gate migration replaces the flat probability with one that **rises with
the captor's local dominance**:

```python
        # DEFERRED (SP4): power_ratio surfaced from _local_dominance (SJ2).
        p_capture = soft_gate(power_ratio, CAPTURE_CENTER, CAPTURE_TEMP)
        if random.random() >= p_capture:
            return False
```

- **Metric binding:** `power_ratio` = the captor-vs-victim local strength ratio
  that `_local_dominance` (`:4598`) already computes internally; the seam requires
  **surfacing that ratio** (return it or a sibling accessor) so `soft_gate` can
  read it. That surfacing is the deferred work item. *(Realized in SP9 via the
  pure `_dominance_counts` sibling + the `power_ratio(enforcers, defenders)`
  module helper.)*
- **New constants (deferred, NOT added now):** `CAPTURE_CENTER` (the dominance
  ratio at which capture is a coin-flip) and `CAPTURE_TEMP` (softness; `<= 0`
  recovers a hard `power_ratio > CAPTURE_CENTER` step). Note: `temp <= 0` recovers
  a hard *threshold on dominance*, which is a deliberate MODEL change from today's
  flat `CAPTURE_CHANCE`, so this migration is behaviour-changing and gated behind
  its own spec/tests — it is listed here ONLY to validate the Form-2 signature.
  *(SP9 REVISES this design point: rather than let `temp <= 0` become a hard
  threshold on `power_ratio` — which would silently change the default flat
  behaviour — SP9 makes `CAPTURE_TEMP <= 0.0` a MODE SWITCH back to the exact flat
  coin-flip, preserving byte-for-byte identity at the default. See SP9.2.)*
- **Do not implement in this pass.** No edit to `:4601` lands with this spec.
  *(SUPERSEDED by SP9 — the edit now lands; anchors updated in SP9.1.)*

---

## SP5 — Behavioral: the daylight tracer state + draw point

**New state (SP5.1).** One per-sim field, initialised beside the sun setpoint at
`sandkings.py:1459` (right after `self.sun_hours = SUN_HOURS_DEFAULT`):

```python
        self.sun_effective = SUN_HOURS_DEFAULT   # SP5: the drawn sky for the current biome-day
```

- getattr-guarded on read (`getattr(self, 'sun_effective', ...)`), so a pre-SP
  pickle / the evolution engine reads a neutral value.

**The once-per-day draw (SP5.2).** At the **very top of `_biome_tick`
(`sandkings.py:2687`)**, before `target = ...` (`:2691`), insert the day-boundary
draw. The day boundary IS the existing `BIOME_TICK` weather cadence (plus the
first tick, so day one has a sky):

```python
    def _biome_tick(self):
        # SP5: draw the EFFECTIVE daylight ONCE per biome-day so every reader in
        # this day sees the same sky. Identity at SUN_JITTER_SD==0 (no RNG draw).
        if self.step_count == 1 or self.step_count % BIOME_TICK == 0:
            self.sun_effective = jitter(
                mean=getattr(self, 'sun_hours', SUN_HOURS_DEFAULT),
                sd=SUN_JITTER_SD, lo=SUN_MIN, hi=SUN_MAX)   # rng defaults to module `random`
        # ... existing body follows (target/equilibrium/weather rolls) ...
```

- **Draw stream:** `jitter`'s `rng` defaults to module `random` — the SAME stream
  `_biome_tick`'s own `random.random()` weather rolls use, and the stream tests
  seed with `random.seed(...)`. So `--canon` reruns are identical (SPA-6).
- **Ordering:** `_biome_tick` runs at `step()`'s `:1645`, BEFORE the crop-growth
  block (`:1668`, `CROP_TICK`) — so `sun_effective` is refreshed before any
  reader consumes it in the same step.
- **Identity:** with `SUN_JITTER_SD == 0.0`, `jitter` returns `sun_hours` exactly
  and consumes NO RNG, so the assignment is a no-op relative to today's reads and
  the weather-roll draws keep their exact stream position — byte-identical.

---

## SP6 — Behavioral: the readers consume `sun_effective`

Redirect the three sun reads from the setpoint to the drawn per-day value. Each
read becomes `getattr(self, 'sun_effective', getattr(self, 'sun_hours',
SUN_HOURS_DEFAULT))` (double getattr-guard: drawn value, else setpoint, else
default).

| # | Site (anchor) | Before | After |
|---|---|---|---|
| SP6.1 | `_biome_growth_units` dark gate `:2678–2679` | `getattr(self,'sun_hours',SUN_HOURS_DEFAULT) < SUN_COLD` | `getattr(self,'sun_effective',getattr(self,'sun_hours',SUN_HOURS_DEFAULT)) < SUN_COLD` |
| SP6.2 | `_biome_growth_units` lush read `:2682` | `sun = getattr(self,'sun_hours',SUN_HOURS_DEFAULT)` | `sun = getattr(self,'sun_effective',getattr(self,'sun_hours',SUN_HOURS_DEFAULT))` |
| SP6.3 | `_biome_tick` water-equilibrium read `:2692` | `sun = getattr(self,'sun_hours',SUN_HOURS_DEFAULT)` | `sun = getattr(self,'sun_effective',getattr(self,'sun_hours',SUN_HOURS_DEFAULT))` |

- `keeper_set_sun` (`:2665`) is UNCHANGED — it still writes the setpoint
  `self.sun_hours`; the draw reads that setpoint as its mean each day.
- Downstream locals (`:2708/2713` use the `sun` bound at `:2692`) inherit the
  drawn value automatically — no further edits.

**Contract (tracer):**
- **Require** — `_biome_tick` called once per `step()` (already true, `:1645`).
- **Guarantee** — within any biome-day all three readers see the SAME
  `sun_effective`; at `SUN_JITTER_SD == 0` `sun_effective == sun_hours` every step
  and no RNG is consumed by the draw; at `SUN_JITTER_SD > 0`, `sun_effective ∈
  [SUN_MIN, SUN_MAX]`.
- **Maintain** — `keeper_set_sun`'s clip domain `[SUN_MIN, SUN_MAX]` is preserved
  by the draw's `lo/hi`; the mean tracks the setpoint.
- **Assert** — `SUN_JITTER_SD == 0.0 ⇒ sun_effective == sun_hours` after every
  `_biome_tick`.

**Inertness (SP6.4).** No `sun_effective` field is required in
`EnhancedSandKingsSimulation`; its readers fall back through getattr to
`sun_hours`. Regardless, `SUN_JITTER_SD == 0.0` makes the whole tracer identity,
so the evolution engine is byte-identical to today.

---

## SP7 — Constants

| Constant | Value | Provenance | Meaning |
|---|---|---|---|
| `SUN_JITTER_SD` | `0.0` | `[prov:B fit=liveness+weather-variance]` | std-dev of the per-biome-day daylight draw around `sun_hours`; **defaults 0 (identity)**; learnable — evolution/fitting dials it up so the sky varies day to day |
| logistic form (`soft_gate`) | — | `[prov:A lit=logistic choice / softmax action selection, Sutton&Barto]` | the `P = 1/(1+e^{-z})` soft-gate shape is the standard logistic / softmax action-selection response; used structurally, not tuned here |
| `DAY_LENGTH` (concept) | `BIOME_TICK` (`20`) | `[prov:— reuse]` | the day boundary reuses the existing `BIOME_TICK` weather cadence; **no new constant is added** |

Place `SUN_JITTER_SD` in the biome constants block beside `BIOME_TICK`
(`sandkings.py:222–230`):

```python
SUN_JITTER_SD = 0.0          # SP7: std-dev of per-day daylight draw (0 = identity; learnable)
```

**Load-bearing identity constant:** `SUN_JITTER_SD == 0.0` is the single value
that keeps the 41-suite battery byte-identical (via `jitter`'s `sd<=0` no-draw
short-circuit). Any tune to a positive value is an intentional dynamism change and
requires re-running the invariant suites (it shifts the shared RNG trajectory once
a draw is consumed). Do NOT fabricate citations for `SUN_JITTER_SD`'s value — `0.0`
is chosen for identity; a positive default would be `[prov:B]` fit work.

---

## SP8 — Acceptance (`tests/test_semipermeable.py`)

Clause **SPA-1 is FIRST and gating (neutral ⇒ identity).** Tests seed both module
streams (`random.seed(s); np.random.seed(s)`) like `tests/test_weather.py:24–25`.

1. **SPA-1 — NEUTRAL ⇒ IDENTITY (mechanical, no long run).**
   - `jitter(mean=12, sd=0.0, lo=4, hi=20)` returns `12.0` exactly (float-equal),
     for several `mean` values (e.g. `4, 12, 20, 7.5`).
   - Under a `random.*` counting spy, `jitter(..., sd=0.0)` consumes **zero**
     draws; `jitter(..., sd=0.5)` consumes **exactly one**.
   - `soft_gate(metric, center, temp=0.0)` equals `1.0 if metric > center else
     0.0` across a battery (metric on both sides of + equal to center).
   - A `SandKingsSimulation` stepped N steps with `SUN_JITTER_SD == 0.0` has
     `sun_effective == sun_hours` on **every** step (byte-identical daylight).
2. **SPA-2 — daylight identity across a run.** With `SUN_JITTER_SD == 0.0`, for a
   canon sim run ≥ `3·BIOME_TICK` steps, `sun_effective` equals `sun_hours` at
   every step and after any `keeper_set_sun(h)` the effective daylight equals `h`
   from the next day boundary (mean tracks the setpoint).
3. **SPA-3 — distribution shape (sd>0).** With `SUN_JITTER_SD` monkey-patched to a
   positive value (e.g. `2.0`) and `sun_hours == 12`, collecting one
   `sun_effective` per biome-day over many days yields: sample mean ≈ `12` (within
   a tolerance, e.g. `±1.0` over ≥ 200 days), **nonzero** sample variance, and
   **every** sample within `[SUN_MIN, SUN_MAX]` (clip holds; test near a boundary
   like `sun_hours == 19` to exercise `hi`).
4. **SPA-4 — soft_gate is a monotone probability crossing 0.5 at center.** For
   `temp > 0`: `soft_gate(center, center, temp) == 0.5`; the function is strictly
   increasing across a swept `metric` battery; `soft_gate(center-Δ) < 0.5 <
   soft_gate(center+Δ)`; values stay within `[0,1]` and saturate toward `0`/`1` at
   large `|metric-center|`. (Validates the Form-2 signature SP4/SP9 reuse.)
5. **SPA-5 — one sky per day.** Within a single biome-day (steps between two
   `BIOME_TICK` boundaries), `sun_effective` does not change even with
   `SUN_JITTER_SD > 0` — all readers in the day see the same value; it only
   changes at a day boundary.
6. **SPA-6 — canon reproducibility (sd>0).** Two `SandKingsSimulation(canon=True)`
   runs, each preceded by the SAME `random.seed(s); np.random.seed(s)` and the
   same positive `SUN_JITTER_SD`, produce **identical** `sun_effective` sequences
   over ≥ `10·BIOME_TICK` steps (the draw rides the seeded module stream, not a
   fresh generator).

---

## SP9 — Behavioral: the capture membrane (CAPTURE_CHANCE → soft_gate, REALIZES SP4)

Migrates the FIRST frozen `if/else` capture gate to the semi-permeable primitive:
the flat coin-flip `if random.random() >= CAPTURE_CHANCE` becomes, under an opt-in
temperature, a `soft_gate` probability shaped by the captor's **local superiority**
(`power_ratio`). The default (`CAPTURE_TEMP == 0.0`) is a **mode switch back to the
exact pre-SP9 flat gate** — byte-for-byte identical, zero new RNG draws — so the
full 41-suite battery and the existing subjugation suite stay green. This is the
concrete realization of the SP4 seam, and it validates `soft_gate(metric, center,
temp)` against its live second caller.

### SP9.1 — Current anchors (verified against `sandkings.py`, 2026-07-11)

The file has drifted since SP4 was written; these are the true anchors:

| Symbol | Line | Note |
|---|---|---|
| Capture constants block | `:324–334` | `CAPTURE_CHANCE = 0.0` at `:325`, `CAPTURE_HEALTH = 3` at `:326` |
| `_chebyshev` | `:4571` | Chebyshev distance helper (pure) |
| `_units_near(position, radius=1)` | `:4575` | returns `List[SandKing]` near a voxel (pure read) |
| `_subjugate_stance` | `:4603` | gate (2), no RNG |
| `_local_dominance` | `:4617` | gate (3) bool, no RNG — REFACTORED by SP9.3 to delegate |
| `_try_capture` (def) | `:4640` | the 4-gate chain; gate (4) flat coin-flip at `:4665` |

### SP9.2 — Requirements (observable behaviour + contracts)

| # | Requirement | Acceptance criterion (mechanically checkable) |
|---|---|---|
| SP9.2a | **Identity mode-switch** | `CAPTURE_TEMP <= 0.0` (DEFAULT) executes the EXACT pre-SP9 lines: gate (3) hard bool `_local_dominance` (require `enforcers>=1 AND defenders==0`) then gate (4) `if random.random() >= CAPTURE_CHANCE: return False`. Same return value AND same RNG-draw count as pre-SP9 for every `(CAPTURE_CHANCE, enforcers, defenders)` state (SPA-7). |
| SP9.2b | **RNG conservation preserved** | The `_try_capture` docstring's guarantees are kept verbatim: `CAPTURE_CHANCE <= 0` ⇒ zero RNG (gate 1); on `False`, zero RNG consumed unless capture was **genuinely possible**. In flat mode "genuinely possible" = past gates 1–3 (enforcers≥1 AND defenders==0). In soft mode it = past gates 1, 2, and 3′ (enforcers≥1). EXACTLY ONE `random.random()` draw on any path where capture is genuinely possible (SPA-7, SPA-10). |
| SP9.2c | **Boolean dominance unchanged** | `_local_dominance(...)` returns `True` iff `enforcers>=1 and defenders==0` — identical truth table and signature to pre-SP9, for its existing callers (SPA-8). |
| SP9.2d | **power_ratio metric** | `power_ratio(enforcers, defenders) = enforcers/(enforcers+defenders)` when `enforcers+defenders>0`, else `0.0`; range `[0,1]`; `1.0`=uncontested, `0.5`=even (SPA-9). |
| SP9.2e | **Soft membrane** | `CAPTURE_TEMP > 0.0` relaxes the hard wall: capture is possible whenever `enforcers>=1` (defenders no longer forced to 0). Probability `p = CAPTURE_CHANCE * soft_gate(power_ratio, CAPTURE_CENTER, CAPTURE_TEMP)`; a contested case flat-mode rejects with prob 1 now has `p ∈ (0,1)` rising monotonically with `power_ratio` (SPA-10). |
| SP9.2f | **Canon under softness** | Two same-seed runs with `CAPTURE_TEMP>0` produce identical capture outcomes (SPA-11). |
| SP9.2g | **Security** | Pure numeric + spatial read. `power_ratio` and `_dominance_counts` consume no RNG, do no I/O, no mutation. |

### SP9.3 — Structural additions

**(a) Module-level pure helper** — placed beside `soft_gate` in the SP2 block
(same pure-numeric home). Makes `power_ratio` independently unit-testable (SPA-9)
and gives the future per-colony seam a clean function to hold.

```python
def power_ratio(enforcers: int, defenders: int) -> float:
    """SP9: bounded local-superiority scalar for the soft capture gate, in [0,1].

    power_ratio = enforcers / (enforcers + defenders), or 0.0 when no units are
    present. 1.0 = uncontested (no defenders adjacent), 0.5 = even numbers,
    approaches 0.0 as defenders dominate. Pure: no RNG, no I/O, no mutation.

    Failure modes: none raised; enforcers+defenders <= 0 short-circuits to 0.0
                   (avoids ZeroDivisionError and matches "no captor present").
    """
    total = enforcers + defenders
    if total <= 0:
        return 0.0
    return enforcers / total
```

**Contract (`power_ratio`):**
- **Require** — `enforcers`, `defenders` non-negative ints (counts).
- **Guarantee** — result in `[0.0, 1.0]`; `defenders==0 and enforcers>0 ⇒ 1.0`;
  `enforcers==0 ⇒ 0.0`; monotone non-decreasing in `enforcers`, non-increasing in
  `defenders`; consumes NO RNG.
- **Assert** — `power_ratio(1,0)==1.0`; `power_ratio(0,0)==0.0`;
  `power_ratio(1,1)==0.5`.

**(b) Pure count sibling** — refactor `_local_dominance`'s counting loop into a
sibling method so the bool gate and the ratio metric share ONE source of truth for
the enforcer/defender counts (they can never disagree). This method is the
"sibling accessor" the SP4 seam asked for.

```python
    def _dominance_counts(self, captor_colony: Colony, captor_unit: SandKing,
                          victim: SandKing, victim_colony: Colony) -> Tuple[int, int]:
        """SP9: count captor enforcers and victim defenders within Chebyshev radius 1
        of the victim. Single source of truth for both _local_dominance (bool) and
        the power_ratio metric.

        Enforcer = a captor-colony SOLDIER adjacent to victim.
        Defender = a victim-colony FREE birth-house unit (laboring_for < 0) adjacent.

        Require: victim has a valid position.
        Guarantee: returns (enforcers, defenders), both >= 0. Pure read: no
                   mutation, no RNG. Counting logic is byte-identical to the loop
                   that previously lived inline in _local_dominance.
        """
        vx, vy, vz = victim.position
        enforcers = 0      # captor soldiers within radius 1 of victim
        defenders = 0      # victim's birth free units within radius 1 (rescuers)
        for other in self._units_near(victim.position, radius=1):
            if other is victim:
                continue
            if (other.colony_id == captor_colony.colony_id
                    and other.unit_type == UnitType.SOLDIER):
                enforcers += 1
            elif (other.colony_id == victim_colony.colony_id
                    and getattr(other, 'laboring_for', -1) < 0):  # free birth-house unit
                defenders += 1
        return enforcers, defenders
```

**(c) `_local_dominance` now delegates** — signature, docstring intent, and truth
table UNCHANGED; only the body is replaced so the count loop is not duplicated.

```python
    def _local_dominance(self, captor_colony: Colony, captor_unit: SandKing,
                        victim: SandKing, victim_colony: Colony) -> bool:
        """Check local dominance: at least one captor enforcer (soldier) adjacent to victim
        and zero free (unextraced) defenders of victim's birth house adjacent.

        Require: victim and captor_unit have valid positions.
        Guarantee: True only when enforcers >= 1 and defenders == 0 within Chebyshev radius 1.
        Maintain: pure read, no mutation, no RNG.
        """
        enforcers, defenders = self._dominance_counts(
            captor_colony, captor_unit, victim, victim_colony)
        return enforcers >= 1 and defenders == 0
```

> **Refactor is RNG-neutral.** `_dominance_counts` performs the identical
> iteration and counting the old inline loop did, and neither touches `random`.
> So `_local_dominance` returns the identical bool and the shared RNG stream is
> untouched by the move — the identity path (SP9.4, `CAPTURE_TEMP<=0`) is
> byte-for-byte. SPA-8 pins the truth table; Sonnet additionally verifies the
> extracted loop is a faithful character-for-character move of the original
> (cite `:4626–4638`).

### SP9.4 — Behavioral: the `_try_capture` mode switch

Replace gates (3) and (4) (`sandkings.py:4661–4666`) with a mode switch on
`CAPTURE_TEMP`. Gates (1) and (2) are UNCHANGED. The capture body (`:4667–4674`)
is UNCHANGED. Rote pseudocode for the new gate block:

```python
        # (1) HARD GATE — no RNG, default-neutral   [UNCHANGED]
        if CAPTURE_CHANCE <= 0.0:
            return False
        # (2) stance gate (default False) — no RNG   [UNCHANGED]
        if not self._subjugate_stance(captor_colony, victim_colony):
            return False

        # (3)+(4) SP9 MODE SWITCH on CAPTURE_TEMP.
        if CAPTURE_TEMP <= 0.0:
            # IDENTITY PATH — byte-for-byte the pre-SP9 flat gate.
            # (3) SJ2 dominance — hard wall (enforcers>=1 AND defenders==0), no RNG
            if not self._local_dominance(captor_colony, captor_unit, victim, victim_colony):
                return False
            # (4) flat coin-flip — the ONLY draw, reached ONLY past gates 1-3
            if random.random() >= CAPTURE_CHANCE:
                return False
        else:
            # SOFT MEMBRANE PATH — opt-in, behaviour-changing (CAPTURE_TEMP > 0).
            # (3') relaxed wall: a captor must be present (enforcers>=1), but
            #      adjacent defenders no longer veto — they only lower power_ratio.
            enforcers, defenders = self._dominance_counts(
                captor_colony, captor_unit, victim, victim_colony)
            if enforcers < 1:
                return False                      # no captor adjacent — no draw (RNG conserved)
            # (4') soft probability shaped by local superiority; CAPTURE_CHANCE is
            #      the ceiling/enable, soft_gate scales it by power_ratio.
            pr = power_ratio(enforcers, defenders)
            p = CAPTURE_CHANCE * soft_gate(pr, CAPTURE_CENTER, CAPTURE_TEMP)
            if random.random() >= p:              # the ONLY draw, reached only past 1,2,3'
                return False

        # CAPTURE (shared, UNCHANGED from pre-SP9)
        victim.laboring_for = captor_colony.colony_id
        victim.health = CAPTURE_HEALTH
        victim.defiance = 0.0
        self._log_event(...)                       # existing M2 capture log
        return True
```

**Reading the constants as module globals (SP9.4a).** `_try_capture` references
`CAPTURE_CHANCE`, `CAPTURE_TEMP`, and `CAPTURE_CENTER` as **bare names** (module
globals resolved at call time), exactly as it already reads `CAPTURE_CHANCE`. This
matches the launcher pattern (`globals()['CAPTURE_CHANCE'] = ...` at `:6963/6983`)
and lets tests monkeypatch `sandkings.CAPTURE_TEMP` / `sandkings.CAPTURE_CENTER`.
Do NOT read them off `self`.

**Docstring update (SP9.4b).** KEEP the existing `_try_capture` docstring
Require/Guarantee/Maintain/Assert lines **verbatim** (the RNG-conservation
guarantee "On False, ZERO RNG consumed unless a capture was genuinely possible"
and "RNG stream untouched whenever CAPTURE_CHANCE <= 0" still hold). APPEND one
paragraph documenting the mode switch:

```
        SP9: gate (4) is a mode switch on the module constant CAPTURE_TEMP.
          CAPTURE_TEMP <= 0.0 (default): the exact pre-SP9 flat gate — hard
            dominance wall (enforcers>=1 AND defenders==0) then a flat
            random.random() >= CAPTURE_CHANCE coin-flip. Byte-identical.
          CAPTURE_TEMP > 0.0 (opt-in): the soft membrane — the hard wall relaxes
            to enforcers>=1, and capture probability is
            CAPTURE_CHANCE * soft_gate(power_ratio, CAPTURE_CENTER, CAPTURE_TEMP).
          "Genuinely possible" (the RNG-conservation predicate above) means past
          gates 1-3 in flat mode, and past gates 1,2,3' (enforcers>=1) in soft
          mode: exactly one random.random() draw on that path, else zero.
```

**Contract (`_try_capture`, SP9 additions):**
- **Require** — unchanged; plus `CAPTURE_TEMP`, `CAPTURE_CENTER` are finite floats
  (module globals; defaults `0.0`, `0.5`).
- **Guarantee** — `CAPTURE_TEMP <= 0.0` ⇒ identical return value and identical
  RNG-draw count to pre-SP9 for every input state. `CAPTURE_TEMP > 0.0` ⇒ at most
  one `random.random()` draw, taken iff `enforcers>=1` past gates 1–2; capture
  probability equals `CAPTURE_CHANCE * soft_gate(power_ratio, CAPTURE_CENTER,
  CAPTURE_TEMP)`.
- **Maintain** — colony_id unchanged on capture; no unit migration; RNG stream
  untouched whenever `CAPTURE_CHANCE <= 0` (both modes).
- **Assert** — after capture, `victim.health == CAPTURE_HEALTH > 0` and victim not
  in `units_to_remove` (unchanged).

### SP9.5 — Constants

| Constant | Value | Provenance | Meaning |
|---|---|---|---|
| `CAPTURE_CENTER` | `0.5` | `[prov:B fit=capture-liveness]` | the `power_ratio` at which the soft capture gate is a coin-flip; `0.5` = "even numbers → 50%". Only consulted when `CAPTURE_TEMP > 0`. |
| `CAPTURE_TEMP` | `0.0` | `[prov:B fit=capture-liveness]` | softness of the capture membrane; **defaults `0.0` = identity / mode-switch to the exact flat coin-flip**; `> 0` opts into the logistic soft gate. Learnable. |
| logistic form (`soft_gate`) | — | `[prov:A lit=logistic / softmax action selection, Sutton&Barto]` | reuses the SP2 soft-gate shape; not re-tuned here. |
| `power_ratio` form | `enforcers/(enforcers+defenders)` | `[prov:B fit=capture-liveness]` | bounded local-superiority scalar; the `[0,1]` normalization is a modelling choice, not a cited result. |

Place both constants in the capture block immediately after `CAPTURE_HEALTH = 3`
(`sandkings.py:326`), grouped with `CAPTURE_CHANCE`:

```python
CAPTURE_CENTER = 0.5          # SP9: power_ratio at which the soft capture gate is a coin-flip (even numbers -> 50%)
CAPTURE_TEMP = 0.0            # SP9: softness of the capture membrane (0 = identity/flat coin-flip; >0 = logistic on local superiority)
```

**Load-bearing identity constant:** `CAPTURE_TEMP == 0.0` is the single value that
keeps the capture path byte-identical (the mode switch takes the exact pre-SP9
branch). A positive value is an intentional behaviour change: it BOTH relaxes the
hard defender-wall AND shifts the shared RNG trajectory (soft mode draws in
contested cases where the flat wall previously returned before drawing), so
enabling it requires re-running the invariant suites. Do NOT fabricate citations
for the numeric values — `0.0`/`0.5` are chosen for identity and even-odds
centering; tuning them is `[prov:B]` fit work.

**The evolve/fit seam (SP9.6, documented not implemented).** `(CAPTURE_CENTER,
CAPTURE_TEMP)` are the natural contents of a per-colony `GateParam` (SP3): a colony
could carry `colony.capture_gate = GateParam(center=CAPTURE_CENTER,
temp=CAPTURE_TEMP)` and `_try_capture` would read `captor_colony.capture_gate.prob(
power_ratio)` instead of the module constants — letting each house evolve its own
capture aggression (temp) and superiority threshold (center). This is the SP3.1
per-colony seam; NOT implemented in this pass (module constants only).

### SP9.7 — Acceptance (`tests/test_semipermeable.py`, EXTEND)

**Decision: extend `tests/test_semipermeable.py`** (not `test_subjugation.py`).
Rationale: SP9 is the SP-primitive migration, its `power_ratio`/`soft_gate`
assertions belong with the other SP acceptance clauses, and the file already
imports the SP surface. Add `CAPTURE_CENTER`, `CAPTURE_TEMP`, `power_ratio` to the
`from sandkings import (...)` line. Seed both streams like `test_subjugation.py`
(`random.seed(s); np.random.seed(s)`).

**Shared fixture (rote).** Drive `_try_capture` directly against a real seeded sim
with the dominance counts and stance stubbed, so a contested/uncontested state is
forced deterministically without waiting for an emergent adjacency:

```python
class RandomSpy:
    """Count random.random() draws; optionally force the returned roll."""
    def __init__(self, forced=None):
        self.count = 0
        self.forced = forced
        self.original = random.random
    def __call__(self):
        self.count += 1
        return self.original() if self.forced is None else self.forced

def _capture_probe(enforcers, defenders, capture_chance, capture_temp,
                   capture_center=0.5, forced_roll=None, seed=50):
    """Force one _try_capture call with controlled dominance counts + stance.

    Returns (result: bool, draw_count: int). Stubs _subjugate_stance -> True and
    _dominance_counts -> (enforcers, defenders); both the flat gate (via the
    delegating _local_dominance) and the soft gate then read those counts.
    """
    import sandkings
    random.seed(seed); np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sandkings.CAPTURE_CHANCE = capture_chance
    sandkings.CAPTURE_TEMP = capture_temp
    sandkings.CAPTURE_CENTER = capture_center
    # pick two distinct alive colonies + a unit from each
    alive = [c for c in sim.colonies if c.is_alive() and c.units]
    captor_colony, victim_colony = alive[0], alive[1]
    captor_unit = captor_colony.units[0]
    victim = victim_colony.units[0]
    sim._subjugate_stance = lambda cc, vc: True
    sim._dominance_counts = lambda cc, cu, v, vc: (enforcers, defenders)
    spy = RandomSpy(forced=forced_roll)
    old = random.random; random.random = spy
    try:
        result = sim._try_capture(captor_colony, captor_unit, victim, victim_colony)
    finally:
        random.random = old
        sandkings.CAPTURE_CHANCE = 0.0
        sandkings.CAPTURE_TEMP = 0.0
        sandkings.CAPTURE_CENTER = 0.5
    return result, spy.count
```

1. **SPA-7 — IDENTITY + RNG-count (gating; keeps the 42-suite battery green).**
   With `CAPTURE_TEMP == 0.0`, `_try_capture`'s return AND draw count match the
   pre-SP9 flat path across this battery (assert exact `draw_count`):
   | CAPTURE_CHANCE | (E, D) | forced_roll | expect result | expect draws |
   |---|---|---|---|---|
   | `0.0` | any | — | `False` | `0` (gate 1) |
   | `1.0` | `(0,0)` | — | `False` | `0` (hard wall, enforcers<1) |
   | `1.0` | `(1,1)` | — | `False` | `0` (hard wall, defenders>0) |
   | `1.0` | `(1,0)` | `0.0` | `True` | `1` (past wall, roll<1.0) |
   | `0.5` | `(1,0)` | `0.99` | `False` | `1` (past wall, roll>=0.5) |
   Assert `draw_count` equals the "expect draws" column for each row. The `(1,1)`
   and `(0,0)` rows are the pre-SP9 hard-wall zero-draw cases; the `(1,0)` rows are
   the only draws — byte-identical to today.
2. **SPA-8 — `_local_dominance` truth table UNCHANGED.** For a matrix of `(E, D)`
   in `{0,1,2} × {0,1,2}`, stub `sim._dominance_counts` to return `(E, D)` and
   assert `sim._local_dominance(cc, cu, v, vc) == (E >= 1 and D == 0)`. (Signature
   and callers unchanged; Sonnet additionally verifies the extracted count loop is
   a faithful move of `:4626–4638`.)
3. **SPA-9 — `power_ratio` formula.** `power_ratio(1,0)==1.0`;
   `power_ratio(0,0)==0.0`; `power_ratio(1,1)==0.5`; `power_ratio(3,1)==0.75`;
   `power_ratio(0,5)==0.0`; every result in `[0,1]`; monotone non-decreasing as
   `enforcers` rises with `defenders` fixed.
4. **SPA-10 — SOFT MEMBRANE.** With `CAPTURE_TEMP > 0` (`0.15`, scale-matched to
   `power_ratio`'s `[0,1]` domain — see the scale note below),
   `CAPTURE_CENTER == 0.5`, `CAPTURE_CHANCE == 1.0`:
   - **Probability shape (pure, deterministic):** define
     `p(E, D) = CAPTURE_CHANCE * soft_gate(power_ratio(E, D), 0.5, 0.15)`. Assert a
     CONTESTED case `(1, 1)` (flat mode rejects with prob 1) has `p ∈ (0, 1)` (it is
     `0.5`); `(1, 0)` uncontested is near-certain, `p > 0.9` (it is
     `soft_gate(1.0, 0.5, 0.15) ≈ 0.966`); and `p` rises monotonically across
     `power_ratio` values from a swept `(E, D)` battery (e.g.
     `(1,3),(1,1),(3,1),(1,0)` → `power_ratio` `0.25<0.5<0.75<1.0` →
     `p` `0.16<0.5<0.84<0.97`).
   - **Draw actually taken on the contested case:** `_capture_probe(enforcers=1,
     defenders=1, capture_chance=1.0, capture_temp=0.15, forced_roll=0.0)` returns
     `True` with `draw_count == 1` — proving the hard wall is relaxed (flat mode
     would have returned `False`, `0` draws). And `_capture_probe(enforcers=0,
     defenders=0, capture_temp=0.15, ...)` returns `False`, `0` draws (no captor).

   **Temp-scale note (load-bearing for a MEANINGFUL membrane).** `soft_gate`'s
   `temp` must be scaled to the *domain of its metric*. `power_ratio ∈ [0,1]`, so a
   temp near `0.15` puts the logistic argument `(1.0−0.5)/0.15 ≈ 3.3` at the extreme
   — the gate saturates to ~0.03 / ~0.97 and the S-curve actually discriminates. A
   sun-domain temp like `2.0` (fine for `sun_hours ≈ 4..20`) would flatten the gate
   to the range `0.44..0.56` across all of `[0,1]` — technically valid, but a nearly
   inert membrane. Because `CAPTURE_TEMP` is `[prov:B fit=capture-liveness]`, the fit
   process is expected to find this scale; the note keeps a hand-tuner from picking a
   metric-mismatched value.
5. **SPA-11 — canon under softness.** Two same-seed sims with `CAPTURE_TEMP == 2.0`,
   `CAPTURE_CENTER == 0.5`, `CAPTURE_CHANCE` bumped (e.g. `0.4`), subjugation stance
   on colony 0, run ≥ `50` steps each: collect the per-step sequence of thrall
   records `(unit_id, laboring_for)` and assert the two sequences are IDENTICAL
   (mirror `test_subjugation.py`'s override pattern; restore module constants in a
   `finally`). Same seed + same temp ⇒ identical trajectory.

---

## SP10 — Behavioral: the oscillator-driven, self-normalizing daylight signal

Grows the SP5 daylight tracer from a **flat per-day Gaussian draw** into an
**oscillator-driven, self-normalizing signal**. Two independent drivers — daylight
(this block) and water (the existing `_biome_tick` equilibrium) — **combine at the
existing weather rolls**; the dependency graph stays **ACYCLIC** (the one-way
`sun → water` `SUN_DRYING` edge is preserved; NO `water → sun` edge is added).

SP10 has three parts, all gated to identity at the neutral defaults:

- **(A) OSCILLATOR (mean-only swing).** The per-day daylight *mean* swings around
  the keeper setpoint `sun_hours` by a sinusoid in the biome-day index. `sigma`
  (`SUN_JITTER_SD`) is **not** modulated.
- **(B) EMA OBSERVER (rolling mean + rolling sigma).** After each per-day draw, two
  new per-sim fields track an exponential-moving mean and mean-absolute-deviation
  (≈ rolling sigma). **Observer-only:** nothing that affects existing behaviour
  reads them. Pure arithmetic — **zero RNG**.
- **(C) NORMALIZED READ (`z`).** A pure read helper exposes the standardized signal
  `z = (sun_effective − sun_ema_mean) / max(EPS_POWER, sun_ema_sd)` for future
  regime logic and display. **Nothing existing consumes it this pass.**

This is the signal-modulation non-stationary-normalization pattern: an oscillating
non-stationary source, standardized on-line by its own rolling statistics.

### SP10.1 — Requirements (observable behaviour + acceptance)

| # | Requirement | Acceptance criterion (mechanically checkable) |
|---|---|---|
| SP10.1a | **Identity at neutral** | `SUN_OSC_AMP == 0.0` (DEFAULT) ⇒ the swing term is exactly `0.0`, `mean(day) == sun_hours`, and `sun_effective` is byte-identical to SP5 for every day. The EMA update is pure arithmetic (consumes ZERO RNG) regardless of `SUN_EMA_ALPHA`, so the shared RNG stream is unperturbed and the whole battery + `--canon` stay byte-identical (SPA-12). |
| SP10.1b | **Oscillator (mean-only)** | With `SUN_OSC_AMP > 0` and `SUN_JITTER_SD == 0`, `sun_effective(day) == sun_hours + SUN_OSC_AMP * sin(2π · day / SUN_OSC_PERIOD)` within float tolerance; peak-to-peak span ≈ `2·SUN_OSC_AMP`; `sigma` is not modulated (SPA-13). |
| SP10.1c | **EMA observer tracks the signal** | After a keeper setpoint step, `sun_ema_mean` moves monotonically toward the new setpoint (approaches, does not overshoot) with the EMA time-constant; `sun_ema_sd` is larger under `SUN_JITTER_SD > 0` than under `== 0` (SPA-14). |
| SP10.1d | **Normalized read** | `z = (sun_effective − sun_ema_mean) / max(EPS_POWER, sun_ema_sd)` is computable and finite for all states; with `SUN_JITTER_SD > 0` its long-run mean ≈ `0` (SPA-15). |
| SP10.1e | **ACYCLIC (daylight ⊥ water)** | `mean(day)` and `sun_effective` are computed from `sun_hours` and `step_count` ONLY — never from `water_level`, `water_target`, or any weather state. Two runs identical except for a very different starting `water_level` produce the IDENTICAL `sun_effective` sequence (SPA-16). |
| SP10.1f | **Canon under dynamism** | With `SUN_OSC_AMP > 0` AND `SUN_JITTER_SD > 0`, two same-seed runs produce identical `sun_effective` sequences (SPA-17). |
| SP10.1g | **Security** | Pure numeric, in-process. The oscillator uses `math.sin`/`math.pi` (already imported); the EMA and `z` helper are arithmetic reads. No RNG beyond the existing SP5 `jitter` draw, no I/O, no mutation of anything but the two new observer fields. |

### SP10.2 — Structural: new state (two observer fields)

Initialise **beside `sun_effective`** at `sandkings.py:1528` (right after
`self.sun_effective = SUN_HOURS_DEFAULT`):

```python
        self.sun_ema_mean = SUN_HOURS_DEFAULT    # SP10: rolling-mean daylight observer (observer-only)
        self.sun_ema_sd = 0.0                    # SP10: rolling abs-deviation ~ rolling sigma (observer-only)
```

- Both getattr-guarded on read (`getattr(self, 'sun_ema_mean', SUN_HOURS_DEFAULT)`,
  `getattr(self, 'sun_ema_sd', 0.0)`) so a pre-SP10 pickle / the evolution engine
  reads a neutral value.
- **Observer-only invariant:** these two fields are WRITTEN by the SP10.4 update
  and READ only by the SP10.3 `z` helper (a new read consumed by nobody existing).
  No existing behaviour (`_biome_growth_units`, the water equilibrium, the weather
  rolls) may read them — that would create a new coupling.

### SP10.3 — Structural: the normalized-signal read helper (`_sun_z`)

A pure read method on `SandKingsSimulation` (placement: beside the other sun
readers, e.g. directly after `_biome_growth_units` at `:2745`, or after
`keeper_set_sun` — any pure-read home). REUSES the existing `EPS_POWER = 1e-9`
divisor guard (`sandkings.py:365`); **no new EPS constant is added.**

```python
    def _sun_z(self) -> float:
        """SP10: normalized daylight signal (standardized on-line by the EMA observer).

        z = (sun_effective - sun_ema_mean) / max(EPS_POWER, sun_ema_sd)

        A NEW read exposed for future regime logic and display; NOTHING existing
        consumes it this pass. Pure: no RNG, no I/O, no mutation. All fields are
        getattr-guarded so a pre-SP10 sim reads neutral (z == 0.0 at init, since
        sun_effective == sun_ema_mean == SUN_HOURS_DEFAULT and the guard floors
        the divisor at EPS_POWER).
        """
        se = getattr(self, 'sun_effective', getattr(self, 'sun_hours', SUN_HOURS_DEFAULT))
        m = getattr(self, 'sun_ema_mean', SUN_HOURS_DEFAULT)
        s = getattr(self, 'sun_ema_sd', 0.0)
        return (se - m) / max(EPS_POWER, s)
```

**Contract (`_sun_z`):**
- **Require** — none beyond a constructed sim (all reads getattr-guarded).
- **Guarantee** — returns a finite float for every state (the `max(EPS_POWER, s)`
  guard prevents division by zero); consumes NO RNG; mutates nothing.
- **Maintain** — the observer-only invariant: `_sun_z` is a read; it does not write
  `sun_ema_mean`/`sun_ema_sd`.
- **Assert** — at init (`sun_effective == sun_ema_mean`), `_sun_z() == 0.0`.

### SP10.4 — Behavioral: the oscillator draw + EMA update in `_biome_tick`

Modify the SP5.2 once-per-day draw block at the top of `_biome_tick`
(`sandkings.py:2762–2765`). The day-boundary predicate is UNCHANGED
(`self.step_count == 1 or self.step_count % BIOME_TICK == 0`). The rest of
`_biome_tick` (target/equilibrium/water/weather rolls at `:2766+`) is UNCHANGED.

**Before (SP5.2, current `:2762–2765`):**

```python
        if self.step_count == 1 or self.step_count % BIOME_TICK == 0:
            self.sun_effective = jitter(
                mean=getattr(self, 'sun_hours', SUN_HOURS_DEFAULT),
                sd=SUN_JITTER_SD, lo=SUN_MIN, hi=SUN_MAX)
```

**After (SP10.4):**

```python
        if self.step_count == 1 or self.step_count % BIOME_TICK == 0:
            # SP10: biome-day index — REUSES the SP5 BIOME_TICK cadence, NO new
            # time source. day advances by 1 each biome-day (step 1 -> 0, step
            # BIOME_TICK -> 1, 2*BIOME_TICK -> 2, ...).
            day = self.step_count // BIOME_TICK
            # SP10 OSCILLATOR (mean-only swing). At SUN_OSC_AMP == 0.0 the swing
            # term is exactly 0.0 (0.0 * finite sin == 0.0) so mean_day == sun_hours
            # EXACTLY -> byte-identical to SP5. sigma is NOT modulated.
            mean_day = (getattr(self, 'sun_hours', SUN_HOURS_DEFAULT)
                        + SUN_OSC_AMP * math.sin(2.0 * math.pi * day / SUN_OSC_PERIOD))
            self.sun_effective = jitter(
                mean=mean_day,
                sd=SUN_JITTER_SD, lo=SUN_MIN, hi=SUN_MAX)   # jitter sd<=0 draws NO rng
            # SP10 EMA OBSERVER (observer-only, ZERO RNG, pure arithmetic). Mean
            # first, then sd referencing the JUST-updated mean (EMA of |deviation|
            # ~ rolling sigma). Read by nobody existing.
            self.sun_ema_mean = (SUN_EMA_ALPHA * self.sun_effective
                                 + (1.0 - SUN_EMA_ALPHA)
                                 * getattr(self, 'sun_ema_mean', SUN_HOURS_DEFAULT))
            self.sun_ema_sd = (SUN_EMA_ALPHA * abs(self.sun_effective - self.sun_ema_mean)
                               + (1.0 - SUN_EMA_ALPHA)
                               * getattr(self, 'sun_ema_sd', 0.0))
```

**Byte-identity at `SUN_OSC_AMP == 0.0` (load-bearing — read carefully):**
- `math.sin(2.0 * math.pi * day / SUN_OSC_PERIOD)` returns a finite value in
  `[-1, 1]` for every finite `day` (never `nan`/`inf`, since the argument is finite
  and `SUN_OSC_PERIOD > 0`). Therefore `SUN_OSC_AMP * sin(...)` at `AMP == 0.0` is
  `0.0 * finite == 0.0` **exactly**.
- `mean_day = sun_hours + 0.0`. For every finite `sun_hours` (int `12` or the float
  `keeper_set_sun` writes via `np.clip`), `x + 0.0 == x` numerically, and
  `jitter(mean=x, sd<=0)` returns `float(x)` — identical to SP5's `float(sun_hours)`
  (`float(12) == float(12.0) == 12.0`). So `sun_effective` is byte-identical.
- **Do NOT reorder** the expression to `SUN_OSC_AMP * sin(...) + sun_hours` or
  factor it; keep `sun_hours + SUN_OSC_AMP * math.sin(...)` so the `+ 0.0` is the
  final operation and exactness holds.
- The EMA update calls no RNG (no `gauss`, no `random`), so it cannot move the
  shared stream — `--canon` and the battery stay byte-identical at `AMP == 0.0`
  regardless of `SUN_EMA_ALPHA` and `SUN_OSC_PERIOD`.
- With `SUN_JITTER_SD == 0.0` AND `SUN_OSC_AMP == 0.0` the whole block is a no-op
  versus SP5 today: `jitter` short-circuits (no draw) and the EMA is inert
  arithmetic on constants.

**Contract (SP10 daylight signal):**
- **Require** — `_biome_tick` called once per `step()` (already true); `math`
  imported (already true); `SUN_OSC_PERIOD > 0`.
- **Guarantee** — at `SUN_OSC_AMP == 0.0`: `sun_effective` byte-identical to SP5
  and zero extra RNG. At `SUN_OSC_AMP > 0`, `SUN_JITTER_SD == 0`:
  `sun_effective(day) == sun_hours + SUN_OSC_AMP·sin(2π·day/SUN_OSC_PERIOD)`
  exactly (jitter `sd<=0` returns `float(mean_day)` unclipped). The EMA fields are
  updated once per biome-day by pure arithmetic and are read only by `_sun_z`.
- **Maintain (ACYCLIC)** — `mean_day`, `sun_effective`, `sun_ema_mean`,
  `sun_ema_sd`, and `z` are functions of `sun_hours` and `step_count` ONLY. They
  NEVER read `water_level`, `water_target`, `drought`, or any weather/flood/heat
  state. The existing one-way `sun → water` edge (`SUN_DRYING` in the equilibrium)
  is preserved; NO `water → sun` edge is introduced. Daylight is provably
  independent of water (SPA-16).
- **Assert** — `SUN_OSC_AMP == 0.0 ⇒ mean_day == sun_hours` (float-equal) and
  `sun_effective == sun_hours` at `SUN_JITTER_SD == 0`; `_sun_z()` finite always.

### SP10.5 — Constants

Place in the biome constants block beside `SUN_JITTER_SD` (`sandkings.py:224`,
after it, within the `BIOME_TICK` group; `BIOME_TICK` is defined just above at
`:223`, so `5 * BIOME_TICK` resolves):

```python
SUN_OSC_AMP = 0.0                 # SP10: daylight oscillator amplitude in hours (0 = identity; learnable)
SUN_OSC_PERIOD = 5 * BIOME_TICK   # SP10: period of the daylight swing (steps; season-length pacing)
SUN_EMA_ALPHA = 0.25              # SP10: smoothing for the rolling mean/sdev daylight observer
```

| Constant | Value | Provenance | Meaning |
|---|---|---|---|
| `SUN_OSC_AMP` | `0.0` | `[prov:B fit=weather-variance]` | amplitude of the per-day daylight mean-swing, in daylight-hours; **defaults `0.0` = identity** (swing term is exactly `0.0`); learnable — evolution/fitting dials it up so the sky oscillates seasonally. |
| `SUN_OSC_PERIOD` | `5 * BIOME_TICK` (`100`) | `[prov:C feel=season-length]` | period of the daylight swing; a design pacing choice (a "season"), honest feel-tag — **no literature claim**. |
| `SUN_EMA_ALPHA` | `0.25` | `[prov:A lit=EMA / exponential moving average; Bollinger-band z-score normalization]` | smoothing factor for the rolling mean/sdev observer; the on-line standardization is the standard EMA + Bollinger-style z-score pattern. |
| `EPS` divisor guard | `EPS_POWER` (`1e-9`) | `[prov:— reuse]` | REUSES the existing `EPS_POWER = 1e-9` at `:365` for the `z` divide-guard; **no new EPS constant added.** |

**Load-bearing identity constant:** `SUN_OSC_AMP == 0.0` is the single value that
keeps the battery byte-identical (the swing term collapses to `0.0` and the EMA
consumes zero RNG). Any positive `SUN_OSC_AMP` is an intentional dynamism change
(and, combined with `SUN_JITTER_SD > 0`, shifts the shared RNG trajectory once a
`jitter` draw is consumed), so enabling it requires re-running the invariant
suites. Do NOT fabricate citations for `SUN_OSC_AMP` / `SUN_OSC_PERIOD` — `0.0` is
chosen for identity and `5 * BIOME_TICK` is a feel-tagged pacing choice.

> **Units note (for the tuner, non-blocking).** `day = step_count // BIOME_TICK` is
> in **biome-days**, while `SUN_OSC_PERIOD = 5 * BIOME_TICK` is a **step count**;
> the ratio `day / SUN_OSC_PERIOD` therefore gives a swing whose period is
> `SUN_OSC_PERIOD` **biome-days**. The implementation and every acceptance clause
> (SPA-13) use the SAME expression `sin(2π · day / SUN_OSC_PERIOD)`, so they agree
> and the tests pass by construction; this note only flags that the effective
> period is measured in days, not steps, for whoever later tunes the pacing. At the
> `SUN_OSC_AMP == 0.0` default this is irrelevant (the term is `0.0`).

**The evolve/fit seam (SP10.6, documented not implemented).** `SUN_OSC_AMP` is the
natural learnable of a `DistParam`-adjacent oscillator holder (amplitude of a
mean-swing), and `SUN_EMA_ALPHA` a fixed observer hyperparameter. A future pass can
fold `(sun_hours, SUN_OSC_AMP, SUN_OSC_PERIOD)` into a per-sim oscillator param and
let evolution fit the amplitude against a weather-variance / liveness objective —
the same SP3 seam pattern. NOT implemented in this pass (module constants only).

### SP10.7 — Acceptance (`tests/test_semipermeable.py`, EXTEND)

Add `SUN_OSC_AMP`, `SUN_OSC_PERIOD`, `SUN_EMA_ALPHA`, `EPS_POWER` to the
`from sandkings import (...)` line. Construct/seed sims exactly like the SP5 tests
in this file: `random.seed(s); np.random.seed(s)` then
`sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)`.
Monkeypatch module globals (`sandkings.SUN_OSC_AMP = ...`, etc.) and **restore the
originals in a `finally`**. Drive day boundaries the way `test_distribution_shape`
does (increment `sim.step_count` and call `sim._biome_tick()`), or set
`sim.step_count` directly to boundary values (`1`, `BIOME_TICK`, `2*BIOME_TICK`, …)
and call `_biome_tick()` to sample one day at a time.

12. **SPA-12 — IDENTITY (gating; keeps the battery byte-identical).** With
    `SUN_OSC_AMP == 0.0` and `SUN_JITTER_SD == 0.0`, over a run ≥ `3·BIOME_TICK`
    steps: `sun_effective == sun_hours` on every day (byte-identical to SP5).
    Under a `random.gauss` counting spy, the SP10 draw+EMA block adds **zero**
    `gauss` draws (the EMA is pure arithmetic; `jitter` at `sd==0` short-circuits).
    And `sun_ema_mean` converges to `sun_hours` (with `sun_hours == SUN_HOURS_DEFAULT`
    it stays exactly `SUN_HOURS_DEFAULT` — EMA of a constant seeded at that constant).
    Rote: seed, set `sandkings.SUN_OSC_AMP = 0.0`, `sandkings.SUN_JITTER_SD = 0.0`;
    wrap `random.gauss` with a counter; step the boundaries; assert
    `sim.sun_effective == sim.sun_hours` each day, `gauss_count == 0`, and
    `abs(sim.sun_ema_mean - sim.sun_hours) < 1e-9`; restore in `finally`.
13. **SPA-13 — OSCILLATOR (mean-only).** With `SUN_OSC_AMP = 3.0`,
    `SUN_JITTER_SD = 0.0`, `SUN_OSC_PERIOD = 5 * BIOME_TICK` (default),
    `sun_hours = 12`: sample one `sun_effective` per biome-day for `day` values
    covering ≥ one full period (e.g. set `sim.step_count` to `1` then
    `k*BIOME_TICK` for `k = 1 .. SUN_OSC_PERIOD`, call `_biome_tick()`, record
    `(day, sim.sun_effective)` with `day = sim.step_count // BIOME_TICK`). Assert
    for every sample `abs(sun_effective - (12 + 3.0*math.sin(2*math.pi*day/SUN_OSC_PERIOD))) < 1e-9`
    (direct index check — the primary, no-run-length-dependent assertion). Assert
    the peak-to-peak span `max(samples) - min(samples)` is `≈ 2*3.0 == 6.0`
    (tolerance `±0.2`), confirming the swing amplitude, and that the sample nearest
    `day == SUN_OSC_PERIOD/4` is near the crest `12 + 3.0`.
14. **SPA-14 — EMA tracks a keeper step.** `SUN_OSC_AMP = 0.0`. Start
    `sun_hours = 12`, `SUN_JITTER_SD = 0.0`; step to steady state (many days) so
    `sun_ema_mean ≈ 12`. Then `sim.keeper_set_sun(18)` (or `sim.sun_hours = 18.0`)
    and sample `sun_ema_mean` once per day for the following days. Assert the
    sequence is **monotonically increasing**, each value `> 12` and `<= 18` (never
    overshoots), and converges toward `18` (`abs(last - 18) < 0.5` after enough
    days). Separately: run to steady state with `SUN_JITTER_SD = 0.0` (record
    `sun_ema_sd ≈ 0`) versus `SUN_JITTER_SD = 2.0` (record `sun_ema_sd`) and assert
    the positive-SD `sun_ema_sd` is strictly greater. Restore all globals in
    `finally`.
15. **SPA-15 — z / normalization.** `SUN_OSC_AMP = 0.0`, `SUN_JITTER_SD = 2.0`,
    `sun_hours = 12`. Step many days; each day collect `sim._sun_z()`. Assert every
    value is **finite** (`math.isfinite`), and the long-run **mean of z ≈ 0**
    (tolerance `±0.3` over ≥ 200 days). Also assert `_sun_z()` is computable at init
    without error and equals `0.0` there (`sun_effective == sun_ema_mean`).
16. **SPA-16 — ACYCLIC (daylight ⊥ water).** `SUN_OSC_AMP = 3.0`,
    `SUN_JITTER_SD = 0.0` (so `sun_effective` is a PURE function of `step_count`
    and `sun_hours` — **no RNG is consumed by the daylight path**, sidestepping any
    shared-stream coupling). Build two sims with the SAME seed but very different
    starting water: `sim_a.water_level = 0.05; sim_a.water_target = 0.05` and
    `sim_b.water_level = 0.95; sim_b.water_target = 0.95`. Step both the same number
    of days, collecting the per-day `sun_effective` sequence from each. Assert the
    two sequences are **byte-identical** — proving `sun_effective` does not depend on
    `water_level`. (Rationale for `SUN_JITTER_SD = 0`: with a positive SD the two
    runs' *water-driven* weather rolls would consume different counts of the shared
    `random.random()` stream and desync the subsequent `jitter` draws — that is RNG
    coupling, not a daylight→water read; setting `SD = 0` isolates the acyclic
    computation-input claim the invariant actually makes.)
17. **SPA-17 — CANON under dynamism.** `SUN_OSC_AMP = 3.0`, `SUN_JITTER_SD = 1.0`,
    `SUN_OSC_PERIOD` default. Two runs, each preceded by the SAME
    `random.seed(s); np.random.seed(s)`, sample one `sun_effective` per biome-day
    over ≥ `10·BIOME_TICK` steps. Assert the two sequences are **identical** (the
    oscillator is deterministic in `step_count`; the `jitter` draw rides the seeded
    module stream). Restore globals in `finally`.

---

## SP11 — Behavioral: the bargain-mode membrane (hard argmax → Boltzmann softmax, BARGAIN_TEMP)

Migrates the frozen **bargain-mode SELECTION** from a hard deterministic `argmax`
over the three net-extraction EVs into a **temperature-controlled Boltzmann softmax
sample** — a semi-permeable choice instead of a discrete cliff. Same pattern as SP9
(capture): a temperature constant whose default (`0.0`) routes to the EXACT existing
code (identity, byte-identical battery, ZERO RNG), and whose positive values opt
into a tempered stochastic choice. The three EV computations (`_bargain_ev_wage` /
`_bargain_ev_brute` / `_bargain_ev_destroy`) and the strong/weak assignment are
UNCHANGED — only the selection AMONG the three EVs changes. This applies the
semi-permeable membrane to a discrete CHOICE (softmax over 3 modes), where SP5
applied it to a scalar (`jitter`) and SP9 to a binary gate (`soft_gate`).

### SP11.1 — Current anchors (verified against `sandkings.py`, 2026-07-11)

| Symbol | Line | Note |
|---|---|---|
| `BARGAIN_MODE_*` string enum | `:377–380` | `NONE` / `WAGE` / `SUBJUGATE` / `ANNIHILATE` |
| Bargain constants block | `:382–395` | `BARGAIN_ENABLED = False :382` … `BARGAIN_GRUDGE_SENS = 1.2 :395` (last line of block; `BARGAIN_TEMP` appends here) |
| `_bargain_ev_wage/brute/destroy` (defs) | `:4475 / :4486 / :4500` | pure EV functions — **NOT touched** by SP11 |
| `_bargain_pair_mode` (def) | `:4546` | the frozen argmax gate; body `:4547–4562` (the ONLY code SP11 rewrites) |
| SOLE call site | `:4579` | inside `_bargain_tick`'s pair double-loop; result stored into `modes[key]`, then `self.bargain_modes = modes` wholesale |

**Sample-once finding (SP11 load-bearing — VERIFIED, no risk).**
`_bargain_pair_mode` is invoked **exactly once per unordered living-colony pair per
`_bargain_tick` recompute** — the single call at `:4579`, inside the
`for i, a in enumerate(living): for b in living[i+1:]:` loop — and the returned mode
is written into the local `modes[key]` dict which replaces `self.bargain_modes`
wholesale at the end of the tick. Every downstream reader hits that CACHE, never
`_bargain_pair_mode`: `_bargain_mode` (def `:4482`; read at `:3616` and `:4643`) and
`_bargain_mode_ids` (def `:4487`; read at `:1909`) both `.get(...)` off
`_bargain_modes()`. Therefore `_bargain_pair_mode` is **NOT on any read-hot path**;
under sampling a pair's mode is drawn once and stays stable for the whole tick — no
resample / no flicker. **No caching change is required** — the existing
recompute-then-cache structure already satisfies SP11's sample-once guarantee.

### SP11.2 — Requirements (observable behaviour + contracts)

| # | Requirement | Acceptance criterion (mechanically checkable) |
|---|---|---|
| SP11.2a | **Identity mode-switch** | `BARGAIN_TEMP <= 0.0` (DEFAULT) executes the EXACT pre-SP11 lines — `best<=0 → NONE`; `e_wage>=e_brute and e_wage>=e_destroy → WAGE`; `e_brute>=e_destroy → SUBJUGATE`; else `ANNIHILATE` — INCLUDING the exact tie-break order, and consumes ZERO RNG. Same return value AND same draw count as pre-SP11 for every EV triple (SPA-18). |
| SP11.2b | **NONE guard precedes any draw** | The `best <= 0.0 → BARGAIN_MODE_NONE` guard is FIRST in BOTH modes: when nothing is worth doing there is NO draw on either path (SPA-18, SPA-20). |
| SP11.2c | **Tempered soft choice** | `BARGAIN_TEMP > 0.0` (opt-in) Boltzmann-samples among {WAGE, SUBJUGATE, ANNIHILATE} with `P(mode) ∝ exp(EV_mode / BARGAIN_TEMP)`; empirical frequencies over many draws approximate `softmax(EV/temp)`; close EVs → near-uniform, a dominant EV → near-deterministic (SPA-19). |
| SP11.2d | **Exactly one draw on the soft path** | With `best > 0` and `BARGAIN_TEMP > 0`, a single `_bargain_pair_mode` call consumes EXACTLY ONE `random.random()` draw; with `best <= 0`, ZERO (SPA-20). |
| SP11.2e | **Numerically stable softmax** | Weights use `exp((EV_i − best)/temp)` (max-subtracted before `exp`), then a single inverse-CDF pick over the ordered (WAGE, SUBJUGATE, ANNIHILATE) list — no overflow (SPA-19). |
| SP11.2f | **Canon under softness** | Two same-seed runs with `BARGAIN_TEMP > 0` produce identical mode selections (SPA-21). |
| SP11.2g | **Sample-once stability** | A pair's sampled mode is computed once per recompute and cached in `bargain_modes`; downstream reads never resample within a tick (SP11.1 finding; no code change needed). |
| SP11.2h | **Security** | Pure numeric + one seeded-stream draw. No I/O, no host codegen, no `eval`/`exec`, no sockets, no subprocess; reads `BARGAIN_TEMP` as a bare module global and draws only from module `random`. |

### SP11.3 — Behavioral: the `_bargain_pair_mode` mode switch

Replace the BODY of `_bargain_pair_mode` (`sandkings.py:4547–4562`) with a mode
switch on `BARGAIN_TEMP`. The strong/weak assignment (`:4548–4551`) and the three
`_bargain_ev_*` calls (`:4552–4554`) are UNCHANGED; only the selection among the
three EVs changes. Rote, drop-in pseudocode for the WHOLE method:

```python
    def _bargain_pair_mode(self, a: Colony, b: Colony) -> str:
        """Choose the enforcement mode for the unordered pair (a, b).

        SP11: selection is a mode switch on the module constant BARGAIN_TEMP.
          BARGAIN_TEMP <= 0.0 (default): the exact pre-SP11 hard argmax over the
            three EVs (byte-identical, ZERO RNG, same tie-break order).
          BARGAIN_TEMP > 0.0 (opt-in): a Boltzmann softmax sample among the three
            feasible modes {WAGE, SUBJUGATE, ANNIHILATE} with
            P(mode) proportional to exp(EV_mode / BARGAIN_TEMP), drawn ONCE.
        The best<=0 -> NONE guard is FIRST in BOTH modes (no draw when nothing is
        worth doing). Reads BARGAIN_TEMP as a bare module global; the soft draw
        rides the seeded module `random` stream. Called once per pair per
        _bargain_tick recompute (result cached in bargain_modes) -> a pair's mode
        is stable within a tick even under sampling.
        """
        # strong/weak assignment + the three EVs — UNCHANGED from pre-SP11
        if composite_power(a) >= composite_power(b):
            strong, weak = a, b
        else:
            strong, weak = b, a
        e_wage    = self._bargain_ev_wage(strong, weak)
        e_brute   = self._bargain_ev_brute(strong, weak)
        e_destroy = self._bargain_ev_destroy(strong, weak)
        best = max(e_wage, e_brute, e_destroy)
        # (G) NONE guard FIRST — both modes; NO draw when nothing is worth doing
        if best <= 0.0:
            return BARGAIN_MODE_NONE                     # nothing worth doing -> plain peace
        if BARGAIN_TEMP <= 0.0:
            # IDENTITY PATH — byte-for-byte the pre-SP11 hard argmax. ZERO RNG.
            if e_wage >= e_brute and e_wage >= e_destroy:
                return BARGAIN_MODE_WAGE
            if e_brute >= e_destroy:
                return BARGAIN_MODE_SUBJUGATE
            return BARGAIN_MODE_ANNIHILATE
        # SOFT PATH — opt-in tempered choice (BARGAIN_TEMP > 0). EXACTLY ONE draw.
        modes   = (BARGAIN_MODE_WAGE, BARGAIN_MODE_SUBJUGATE, BARGAIN_MODE_ANNIHILATE)
        evs     = (e_wage, e_brute, e_destroy)
        # numerically stable softmax: subtract best (the max EV) before exp
        weights = [math.exp((ev - best) / BARGAIN_TEMP) for ev in evs]
        total   = weights[0] + weights[1] + weights[2]   # > 0 (the best term is exp(0)=1.0)
        # single inverse-CDF pick over the ordered (WAGE, SUBJUGATE, ANNIHILATE) list
        r   = random.random() * total                    # the ONLY draw, taken past the NONE guard
        acc = 0.0
        for mode, w in zip(modes, weights):
            acc += w
            if r < acc:
                return mode
        return BARGAIN_MODE_ANNIHILATE                    # float-guard fallthrough (last ordered mode)
```

**Reading BARGAIN_TEMP as a module global (SP11.3a).** `_bargain_pair_mode`
references `BARGAIN_TEMP` as a **bare name** (module global resolved at call time),
exactly as it already reads the `BARGAIN_MODE_*` constants and as `_try_capture`
reads `CAPTURE_TEMP` (SP9.4a). Do NOT read it off `self`; tests monkeypatch
`sandkings.BARGAIN_TEMP`. `math` and `random` are already imported at module top
(SP2.1); no new import.

**Why route to the literal old code at temp<=0 (SP11.3b — the SP9 lesson).** Do
NOT reproduce the identity path as a `tau→0` softmax limit. Floating-point `exp`
and the argmax tie-break order would drift — the pre-SP11 `>=`-chain resolves a
three-way tie to WAGE deterministically, whereas a softmax with equal weights
samples uniformly — breaking the byte-identical battery AND consuming a draw where
today there is none. Route to the EXACT pre-SP11 `>=`-chain (same lesson as SP9's
`CAPTURE_TEMP<=0` mode switch: the neutral path is the literal old code, never a
limiting case of the soft path).

**Feasible-set note (SP11.3c).** The soft path samples over ALL THREE modes
{WAGE, SUBJUGATE, ANNIHILATE}; a mode whose EV is `<= 0` (but where `best > 0`)
still receives a small positive weight `exp((EV−best)/temp) ∈ (0,1]` and remains
sampleable. This is intentional — the `best <= 0` guard already removes the
"nothing worth doing" case (→ NONE); past it, at least one EV is positive and the
tempered choice may still occasionally pick a weaker mode, which is the whole point
of a semi-permeable (not hard) selection.

**Contract (`_bargain_pair_mode`, SP11):**
- **Require** — `a`, `b` are colonies with `composite_power` defined; `BARGAIN_TEMP`
  a finite float (module global; default `0.0`).
- **Guarantee** — `BARGAIN_TEMP <= 0.0` ⇒ identical return value and identical
  RNG-draw count (ZERO) to pre-SP11 for every EV triple, including tie-break order.
  `BARGAIN_TEMP > 0.0` ⇒ returns NONE with ZERO draws when `best <= 0`; else takes
  EXACTLY ONE `random.random()` draw and returns a mode in {WAGE, SUBJUGATE,
  ANNIHILATE} sampled with
  `P(mode) = exp((EV_mode−best)/temp) / Σ_i exp((EV_i−best)/temp)`.
- **Maintain** — the three `_bargain_ev_*` values and the strong/weak assignment are
  unchanged; the returned mode is cached once per pair per recompute at the `:4579`
  call site (no resample within a tick).
- **Assert** — at `BARGAIN_TEMP == 0.0`, output equals the pre-SP11 argmax for the
  battery `{(10,1,1)→WAGE, (1,10,1)→SUBJUGATE, (1,1,10)→ANNIHILATE, (0,-1,-2)→NONE,
  (5,5,5)→WAGE, (1,5,5)→SUBJUGATE}` with zero draws; at `BARGAIN_TEMP > 0` with
  `best > 0`, exactly one draw is consumed.

### SP11.4 — Constants

Place in the bargain constants block, appended immediately after
`BARGAIN_GRUDGE_SENS = 1.2` (`sandkings.py:395`), grouped with the other `BARGAIN_*`
constants:

```python
BARGAIN_TEMP = 0.0                    # SP11: softmax temperature over the three bargain EVs (0 = identity/hard argmax; >0 = tempered stochastic choice; learnable)
```

| Constant | Value | Provenance | Meaning |
|---|---|---|---|
| `BARGAIN_TEMP` | `0.0` | `[prov:B fit=mode-diversity]` | Boltzmann temperature over the three bargain EVs; **defaults `0.0` = identity / hard argmax** (routes to the exact pre-SP11 selection, ZERO RNG); `> 0` opts into a tempered stochastic choice (close EVs → near-uniform, a dominant EV → near-deterministic). Learnable — fitting dials it up for mode diversity. |
| softmax form | `exp(EV/temp)` normalized | `[prov:A lit=Boltzmann / softmax action selection, Sutton&Barto]` | the tempered-choice shape is the standard Boltzmann / softmax action-selection response; used structurally, not tuned here. |

**Load-bearing identity constant:** `BARGAIN_TEMP == 0.0` is the single value that
keeps the bargain-mode path byte-identical (the mode switch takes the exact
pre-SP11 argmax branch and draws NO RNG). A positive value is an intentional
behaviour change: it turns each pair's mode into a per-recompute draw and thereby
shifts the shared RNG trajectory for everything downstream in that tick — so
`BARGAIN_TEMP > 0` is only canon-comparable to same-temp runs (mirror the SP9
`CAPTURE_TEMP` and SP7 `SUN_JITTER_SD` notes). The battery stays byte-identical
ONLY at the `0.0` default. Do NOT fabricate a citation for the value — `0.0` is
chosen for identity; the softmax FORM itself is the cited Sutton&Barto pattern, not
the numeric.

**The evolve/fit seam (SP11.5, documented not implemented).** `BARGAIN_TEMP` is the
natural learnable of a per-colony (or per-house) choice-temperature: a house could
carry its own `bargain_temp` and `_bargain_pair_mode` would read it instead of the
module constant — letting sharp houses sample decisively (low temp) and erratic
houses diffusely (high temp), the SP3.1 per-colony seam. NOT implemented in this
pass (module constant only).

### SP11.6 — Acceptance (`tests/test_semipermeable.py`, EXTEND)

Add `BARGAIN_TEMP` and the four `BARGAIN_MODE_*` constants to the `from sandkings
import (...)` line. Seed both streams like the other clauses
(`random.seed(s); np.random.seed(s)`). REUSE the `RandomSpy` from the SP9 section.

**Shared fixture (rote).** Force one `_bargain_pair_mode` call against a real seeded
sim with the three EVs stubbed to fixed values, so the selection logic is exercised
deterministically without constructing power / endowment states:

```python
def _bargain_probe(ev_wage, ev_brute, ev_destroy, temp, seed=50, forced_roll=None):
    """Force one _bargain_pair_mode call with controlled EVs + temperature.

    Returns (mode: str, draw_count: int). Stubs the three _bargain_ev_* methods to
    return fixed EVs; strong/weak still resolves via composite_power on two real
    alive colonies (their actual power is irrelevant — the EVs are stubbed).
    Sets/restores sandkings.BARGAIN_TEMP in a finally.
    """
    import sandkings
    random.seed(seed); np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sandkings.BARGAIN_TEMP = temp
    alive = [c for c in sim.colonies if c.is_alive() and c.units]
    a, b = alive[0], alive[1]
    sim._bargain_ev_wage    = lambda s, w: ev_wage
    sim._bargain_ev_brute   = lambda s, w: ev_brute
    sim._bargain_ev_destroy = lambda s, w: ev_destroy
    spy = RandomSpy(forced=forced_roll)
    old = random.random; random.random = spy
    try:
        mode = sim._bargain_pair_mode(a, b)
    finally:
        random.random = old
        sandkings.BARGAIN_TEMP = 0.0
    return mode, spy.count
```

18. **SPA-18 — IDENTITY + ZERO RNG (gating; keeps the battery byte-identical).**
    With `BARGAIN_TEMP == 0.0`, `_bargain_pair_mode`'s return AND draw count match
    the pre-SP11 hard argmax across this battery. Compare against a LOCAL reference
    `_argmax_mode(ew, eb, ed)` in the test that reproduces the exact pre-SP11
    `>=`-chain, and assert both `mode == _argmax_mode(...)` AND `draw_count == 0`
    for every row:
    | (e_wage, e_brute, e_destroy) | expect mode | branch exercised |
    |---|---|---|
    | `(10, 1, 1)` | `WAGE` | clear WAGE |
    | `(1, 10, 1)` | `SUBJUGATE` | clear SUBJUGATE |
    | `(1, 1, 10)` | `ANNIHILATE` | clear ANNIHILATE |
    | `(0.0, -1.0, -2.0)` | `NONE` | best<=0 guard |
    | `(-1.0, -2.0, -3.0)` | `NONE` | best<=0 guard |
    | `(5, 5, 5)` | `WAGE` | three-way tie → WAGE branch (`e_wage>=both`) |
    | `(1, 5, 5)` | `SUBJUGATE` | tie e_brute==e_destroy → SUBJUGATE |
    | `(5, 5, 1)` | `WAGE` | tie e_wage==e_brute → WAGE |
    | `(1, 5, 3)` | `SUBJUGATE` | e_brute strict max |
    Use `_bargain_probe(..., temp=0.0)`; the zero-draw assertion pins that the
    identity path is byte-identical to today.
19. **SPA-19 — SOFTMAX SHAPE (temp>0).** Construct ONE seeded sim, stub the three
    EVs, set `BARGAIN_TEMP > 0`, and sample many times in a loop calling
    `sim._bargain_pair_mode(a, b)` (each call advances the same seeded stream);
    tally mode frequencies. Assert:
    - **Equal EVs → ~uniform:** with `(5, 5, 5)` and any `temp > 0`, each of the
      three modes occurs ≈ `1/3` (tolerance e.g. `±0.05` over ≥ `3000` samples).
    - **Approximates softmax:** with `(2.0, 1.0, 0.0)` and `temp = 1.0`, empirical
      frequencies approximate `softmax([2,1,0]) ≈ (0.665, 0.245, 0.090)` within
      tolerance (`±0.05`).
    - **Dominant EV → near-deterministic:** with a large gap `(10, 0, 0)` and a
      small `temp` (e.g. `0.5`), WAGE occurs with probability `> 0.95`.
20. **SPA-20 — ONE DRAW / ZERO ON NONE.** With `BARGAIN_TEMP > 0` (e.g. `1.0`):
    `_bargain_probe(5, 5, 5, temp=1.0)` consumes EXACTLY ONE draw
    (`draw_count == 1`); `_bargain_probe(0.0, -1.0, -2.0, temp=1.0)` returns `NONE`
    and consumes ZERO draws (the `best<=0` guard precedes the draw). Also assert the
    identity path draws zero: `_bargain_probe(10, 1, 1, temp=0.0)` → `draw_count == 0`.
21. **SPA-21 — CANON under softness.** Two probe loops, each preceded by the SAME
    `random.seed(s); np.random.seed(s)`, `sandkings.BARGAIN_TEMP` set to the same
    `> 0` value, stubbed EVs near-uniform (e.g. `(3, 2, 1)`), collect the sequence
    of sampled modes over `N ≥ 200` calls; assert the two sequences are IDENTICAL.
    (Optional full-sim mirror of SPA-11: two `BARGAIN_ENABLED=True`, same-seed sims
    with `BARGAIN_TEMP > 0` run ≥ `50` steps produce identical per-step
    `bargain_modes` maps.) Restore `sandkings.BARGAIN_TEMP` in a `finally`.

---

## Status / Reconciliation

- **Drafted 2026-07-11. Spec-first: implementation pending.** Introduces a
  reusable semi-permeable-parameter primitive (Form 1 distributional scalar,
  Form 2 soft gate) plus one tracer (daylight) that makes the effective sky a
  per-day draw around the keeper's setpoint.
- **SP9 added 2026-07-11 (this revision).** Realizes the SP4 seam: migrates the
  frozen capture coin-flip to the `soft_gate` membrane behind `CAPTURE_TEMP`
  (default `0.0` = byte-for-byte flat identity). Adds the pure `power_ratio`
  helper, the pure `_dominance_counts` count sibling (refactor of
  `_local_dominance`, truth table unchanged), the `_try_capture` mode switch, two
  constants (`CAPTURE_CENTER=0.5`, `CAPTURE_TEMP=0.0`), and acceptance clauses
  SPA-7…SPA-11 (extend `tests/test_semipermeable.py`).
- **SP10 added 2026-07-11 (this revision).** Grows the SP5 daylight tracer into an
  oscillator-driven, self-normalizing signal: a mean-only sinusoidal swing
  (`SUN_OSC_AMP`, `SUN_OSC_PERIOD`) around the keeper setpoint, plus a pure EMA
  observer (`sun_ema_mean`, `sun_ema_sd`, `SUN_EMA_ALPHA`) feeding a new normalized
  read `_sun_z()` consumed by nobody existing. Adds two observer fields, three
  constants, one read helper; REUSES `EPS_POWER` and the SP5 `BIOME_TICK` day
  index. `SUN_OSC_AMP == 0.0` (default) is identity: the swing term is exactly
  `0.0` and the EMA consumes zero RNG, so the battery + `--canon` stay
  byte-identical. Keeps the graph ACYCLIC (one-way `sun → water` preserved; no
  `water → sun` edge). Acceptance clauses SPA-12…SPA-17 (extend
  `tests/test_semipermeable.py`).
- **SP11 added 2026-07-11 (this revision).** Converts the bargain-mode SELECTION
  from a hard `argmax` over the three net-extraction EVs into a temperature-
  controlled Boltzmann softmax sample behind `BARGAIN_TEMP` (default `0.0` =
  byte-for-byte hard-argmax identity, ZERO RNG). Changes ONLY the selection body of
  `_bargain_pair_mode` — the three `_bargain_ev_*` computations and the strong/weak
  assignment are untouched. Adds one constant (`BARGAIN_TEMP = 0.0`) and acceptance
  clauses SPA-18…SPA-21 (extend `tests/test_semipermeable.py`). VERIFIED
  `_bargain_pair_mode` is called once per pair per `_bargain_tick` recompute (sole
  call site `:4579`, result cached in `bargain_modes`, all reads hit the cache) —
  NOT a read-hot path, so a pair's sampled mode is stable within a tick and NO
  caching change is needed.
- **Reuses, does not duplicate:** the seeded module RNG streams, the `_clamp01`
  module-helper convention (`:526`), the `BIOME_TICK` cadence (`:222`) as the
  day boundary, and (SP10) the `EPS_POWER` divisor guard (`:365`). Adds
  `jitter`/`soft_gate`/`power_ratio`, `DistParam`/`GateParam`, one `sun_effective`
  field (+ SP10's `sun_ema_mean`/`sun_ema_sd`), `SUN_JITTER_SD`/`CAPTURE_CENTER`/
  `CAPTURE_TEMP`/`SUN_OSC_AMP`/`SUN_OSC_PERIOD`/`SUN_EMA_ALPHA`/`BARGAIN_TEMP`
  constants, one day-boundary draw (now oscillator+EMA), three reader redirections,
  the `_sun_z` read helper, one count-sibling refactor, one capture mode-switch,
  and (SP11) one bargain-mode selection mode-switch.
- **Default-neutral strategy:** `SUN_JITTER_SD == 0.0`, `temp <= 0`,
  `CAPTURE_TEMP == 0.0`, `SUN_OSC_AMP == 0.0`, and `BARGAIN_TEMP == 0.0` make every
  effect the identity transform; `jitter` consumes ZERO RNG at `sd == 0`, the
  capture mode-switch takes the exact pre-SP9 branch, the SP10 swing term is exactly
  `0.0` with a pure-arithmetic (zero-RNG) EMA, and the SP11 mode-switch routes to
  the exact pre-SP11 argmax with zero draws — so the shared draw stream is
  unperturbed and the battery + the subjugation suite + `--canon` stay
  byte-identical. Dynamism appears only when variance/softness/amplitude/temperature
  is dialed in (evolution/fitting, future).
- **Next-tracer seam REALIZED:** SP4's `CAPTURE_CHANCE → soft_gate` binding is now
  implemented by SP9 (was: deferred, signature-validation only).
- **Real anchors verified against `sandkings.py` (2026-07-11):** `_clamp01:530`,
  `jitter:535`, `soft_gate:552`, `power_ratio:569`, `DistParam:578`/`GateParam:589`,
  `EPS_POWER:365`, biome constants `:218–232` (`SUN_HOURS_DEFAULT:221`,
  `SUN_MIN/SUN_MAX:222`, `BIOME_TICK:223`, `SUN_JITTER_SD:224`, `SUN_DRYING:226`),
  sun setpoint + `sun_effective` init `:1527–1528`, `keeper_set_sun:2734`,
  `_biome_growth_units:2745` (reads `:2747/2751`), `_biome_tick:2756` (SP5 draw
  `:2762–2765`, water-equilibrium read `:2767`), bargain constants block `:382–395`
  (`BARGAIN_GRUDGE_SENS:395`), `BARGAIN_MODE_*:377–380`, `_bargain_pair_mode:4546`
  (body `:4547–4562`), sole call site `:4579` in `_bargain_tick:4564`, cache reads
  `_bargain_mode:4482`/`_bargain_mode_ids:4487` (consumers `:1909/:3616/:4643`),
  test-seeding precedent `tests/test_semipermeable.py:23–28`. NOTE: the SP5/SP6/SP9
  line anchors quoted verbatim in those older blocks (`:1459`, `:2687`, `:4640`, …)
  predate later drift; SP10's and SP11's anchors above are the current truth.
