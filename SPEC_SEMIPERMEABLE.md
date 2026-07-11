# SPEC: Semi-Permeable Parameters — learnable soft params + the daylight tracer (SP1–SP8)

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
> - **REUSES** the existing seeded module RNG streams (`random` + `np.random`,
>   seeded by tests / `play_kit` at construction), the `_clamp01` module-helper
>   convention (`sandkings.py:526`), and the whole `BIOME_TICK` weather cadence
>   (`:222`) as the day boundary — no new cadence constant.
> - **CHANGES nothing at neutral.** `SUN_JITTER_SD == 0.0` and `temp <= 0` make
>   every effect the identity transform; the primitive consumes **zero RNG** at
>   neutral, so the shared draw stream is byte-identical and `--canon` reruns
>   match today exactly.

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

## SP4 — Structural: the NEXT tracer seam (CAPTURE_CHANCE → soft_gate, DEFERRED)

Not implemented here — specified so the **Form-2 signature is validated against a
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
  read it. That surfacing is the deferred work item.
- **New constants (deferred, NOT added now):** `CAPTURE_CENTER` (the dominance
  ratio at which capture is a coin-flip) and `CAPTURE_TEMP` (softness; `<= 0`
  recovers a hard `power_ratio > CAPTURE_CENTER` step). Note: `temp <= 0` recovers
  a hard *threshold on dominance*, which is a deliberate MODEL change from today's
  flat `CAPTURE_CHANCE`, so this migration is behaviour-changing and gated behind
  its own spec/tests — it is listed here ONLY to validate the Form-2 signature.
- **Do not implement in this pass.** No edit to `:4601` lands with this spec.

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
   large `|metric-center|`. (Validates the Form-2 signature SP4 will reuse.)
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

## Status / Reconciliation

- **Drafted 2026-07-11. Spec-first: implementation pending.** Introduces a
  reusable semi-permeable-parameter primitive (Form 1 distributional scalar,
  Form 2 soft gate) plus one tracer (daylight) that makes the effective sky a
  per-day draw around the keeper's setpoint.
- **Reuses, does not duplicate:** the seeded module RNG streams, the `_clamp01`
  module-helper convention (`:526`), and the `BIOME_TICK` cadence (`:222`) as the
  day boundary. Adds `jitter`/`soft_gate`, `DistParam`/`GateParam`, one
  `sun_effective` field, one `SUN_JITTER_SD` constant, one day-boundary draw, and
  three reader redirections.
- **Default-neutral strategy:** `SUN_JITTER_SD == 0.0` and `temp <= 0` make every
  effect the identity transform; `jitter` consumes ZERO RNG at `sd == 0`, so the
  shared draw stream is unperturbed and the 41-suite battery + `--canon` stay
  byte-identical. Dynamism appears only when variance/softness is dialed in
  (evolution/fitting, future).
- **Next-tracer seam validated:** SP4 binds the Form-2 `soft_gate(metric, center,
  temp)` signature to a real second caller (`CAPTURE_CHANCE` → dominance-driven
  capture probability), deferred and behaviour-gated — not implemented here.
- **Real anchors verified against `sandkings.py`:** `_clamp01:526`, sun setpoint
  init `:1459`, `step()` order (`_biome_tick:1645` before `CROP_TICK:1668`),
  `keeper_set_sun:2665`, `_biome_growth_units:2676` (reads `:2678/2682`),
  `_biome_tick:2687` (read `:2692`), biome constants `:222–230`, capture gate
  `:4601`, test-seeding precedent `tests/test_weather.py:24–25`.
