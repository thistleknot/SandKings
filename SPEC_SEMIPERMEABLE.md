# SPEC: Semi-Permeable Parameters — learnable soft params + the daylight tracer (SP1–SP9)

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
> - **REUSES** the existing seeded module RNG streams (`random` + `np.random`,
>   seeded by tests / `play_kit` at construction), the `_clamp01` module-helper
>   convention (`sandkings.py:526`), and the whole `BIOME_TICK` weather cadence
>   (`:222`) as the day boundary — no new cadence constant.
> - **CHANGES nothing at neutral.** `SUN_JITTER_SD == 0.0` and `temp <= 0` make
>   every effect the identity transform; the primitive consumes **zero RNG** at
>   neutral, so the shared draw stream is byte-identical and `--canon` reruns
>   match today exactly. SP9 keeps this: `CAPTURE_TEMP == 0.0` is the byte-for-byte
>   flat-gate identity path.

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
- **Reuses, does not duplicate:** the seeded module RNG streams, the `_clamp01`
  module-helper convention (`:526`), and the `BIOME_TICK` cadence (`:222`) as the
  day boundary. Adds `jitter`/`soft_gate`/`power_ratio`, `DistParam`/`GateParam`,
  one `sun_effective` field, `SUN_JITTER_SD`/`CAPTURE_CENTER`/`CAPTURE_TEMP`
  constants, one day-boundary draw, three reader redirections, one count-sibling
  refactor, and one capture mode-switch.
- **Default-neutral strategy:** `SUN_JITTER_SD == 0.0`, `temp <= 0`, and
  `CAPTURE_TEMP == 0.0` make every effect the identity transform; `jitter`
  consumes ZERO RNG at `sd == 0` and the capture mode-switch takes the exact
  pre-SP9 branch, so the shared draw stream is unperturbed and the 41-suite
  battery + the subjugation suite + `--canon` stay byte-identical. Dynamism
  appears only when variance/softness is dialed in (evolution/fitting, future).
- **Next-tracer seam REALIZED:** SP4's `CAPTURE_CHANCE → soft_gate` binding is now
  implemented by SP9 (was: deferred, signature-validation only).
- **Real anchors verified against `sandkings.py` (2026-07-11):** `_clamp01:526`,
  sun setpoint init `:1459`, `step()` order (`_biome_tick:1645` before
  `CROP_TICK:1668`), `keeper_set_sun:2665`, `_biome_growth_units:2676` (reads
  `:2678/2682`), `_biome_tick:2687` (read `:2692`), biome constants `:222–230`,
  capture constants `:324–334`, `_units_near:4575`, `_chebyshev:4571`,
  `_subjugate_stance:4603`, `_local_dominance:4617`, `_try_capture:4640` (flat
  gate `:4665`), test-seeding precedent `tests/test_weather.py:24–25`,
  `test_subjugation.py` fixture pattern (module-constant override + `RandomSpy`).
</content>
</invoke>
