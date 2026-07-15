# SPEC: Disposition — favoritism, confidence & agitation (DP1–DP12)

A keeper-treatment → **DISPOSITION** layer ported from the external browser
"Sandkings" game and reconciled with our existing keeper / faces / awareness /
bargain systems. The external model gives each colony three live scalars —
a signed **favoritism** (how the god has treated *this* colony lately), a
**confidence / boldness** meter (how dominant the colony feels from its material
condition), and a short-term **agitation** startle spike. This spec ports all
three, **adapted** so they layer onto — never duplicate — what the terrarium
already has.

> **What this ADDS vs what it REUSES (read first).**
> - **ADDS** three getattr-guarded, pickled per-colony scalars (`favoritism`,
>   `confidence`, `agitation`) plus `last_victory_step`; one pure per-step
>   `_disposition_tick`; an effective-aggression read `_aggression_eff`; a
>   confidence-boldness factor on the (already-gated) bargain force EVs; an
>   agitation mill on unit AI; and keeper-verb hooks that write favoritism /
>   agitation.
> - **REUSES** the mood/face surface entirely — `keeper_sentiment`
>   (`sandkings.py:2224 _update_sentiment`), the carved face band
>   (`CARVE_SYMBOLS`), `face_favor`, and `NATURE_SYMBOLS`/`_nature_mood`
>   (`:2259`). This spec adds **no parallel face or mood system**; favoritism
>   *nudges* the existing `keeper_sentiment` post-breach and the faces mirror the
>   result as they already do (SPEC_FACES F1/F2).
> - **RECONCILES** with the awareness gate (SPEC_AWARENESS AW1): `confidence` is
>   NATURE-level / always-on (material condition, not keeper-knowledge, so it does
>   **not** gate on `breached`); `favoritism` accumulates pre-breach as bookkeeping
>   and only *modulates* `keeper_sentiment` **post-breach** (where
>   `_update_sentiment` already runs).

Layer: **Structural + Behavioral.** New per-colony state + contracts (structural)
and an ordered per-step tick with stateful decay (behavioral).

---

## DP1 — The three scalars (state)

Three new per-colony fields, each getattr-guarded, pickled, with a **NEUTRAL
default that is behaviourally identity** (a fresh sim behaves byte-identically to
today at these defaults):

| Field | Type / range | Neutral default | Meaning |
|---|---|---|---|
| `favoritism` | float `[-1.0, 1.0]` | `0.0` | signed record of the god's recent treatment of THIS colony; decays to neutral |
| `confidence` | float `[0.0, 1.0]` | `0.5` | boldness meter; `0.5` = neutral boldness; drives effective aggression |
| `agitation` | float `[0.0, 1.0]` | `0.0` | short-term startle from keeper disturbance; decays fast |

Plus one bookkeeping field for the "recent victory" confidence input:

| Field | Type | Neutral default | Meaning |
|---|---|---|---|
| `last_victory_step` | int | `-10**9` | step at which this colony last won a war (a rival it warred fell) |

**Placement (real anchors):**
- Init in `Colony.__init__` beside the keeper block at `sandkings.py:1015–1018`
  (right after `self.keeper_sentiment = 0.5`).
- Pickle-restore in the getattr-guard tuple at `sandkings.py:1695–1705` — append
  `('favoritism', 0.0), ('confidence', 0.5), ('agitation', 0.0),
  ('last_victory_step', -10**9)` to the existing `(attr, default)` loop.

**Contract (state):**
- **Require** — every read is `getattr(colony, name, default)` with the DP1
  default, so a pre-DP pickle reads the neutral value.
- **Guarantee** — `favoritism ∈ [-1,1]`, `confidence ∈ [0,1]`, `agitation ∈ [0,1]`
  after every write (all writers clamp).
- **Maintain** — at the neutral defaults, every DP effect (DP4/DP5/DP6/DP7) is
  the identity transform.
- **Assert** — `-1.0 <= favoritism <= 1.0 and 0.0 <= confidence <= 1.0 and
  0.0 <= agitation <= 1.0`.

---

## DP2 — `_disposition_tick`: confidence from material condition (NATURE-level, always-on)

Confidence is a colony's read of its **own material condition** — it grows bold
when thriving and cowed when starved/threatened, **regardless of awareness** (a
thriving pre-breach colony still grows dominant; it responds to plenty, not to
knowing the keeper). Therefore `_disposition_tick` does **NOT** gate on
`breached`. It also decays favoritism (medium) and agitation (fast). It is a
**pure** read of colony state — **consumes ZERO RNG** — so it never perturbs the
draw stream.

### Confidence target (the neutral-band model — the load-bearing identity choice)

The target is `0.5` plus prosperity signals minus distress signals, where **every
signal is exactly 0 for a colony in ordinary condition**, so an ordinary colony's
target is EXACTLY `0.5` and, starting from the `0.5` default, `confidence` never
moves (identity). Divergence emerges only as a colony becomes genuinely
rich/populous/victorious (target > 0.5) or starved/threatened/disfavoured
(target < 0.5).

```
def _disposition_confidence_target(self, colony) -> float:
    """Pure target for the boldness meter from material condition. 0.5 for an
    ordinary colony (every term 0); >0.5 thriving, <0.5 distressed. No RNG."""
    step = self.step_count
    food = colony.maw.food_stored
    n    = len(colony.units)
    fav  = getattr(colony, 'favoritism', 0.0)
    # prosperity signals — zero in ordinary condition, saturate at extremes
    surplus_frac = _clamp01((food - CONF_RICH_FOOD) / CONF_RICH_FOOD)   # 0 until rich
    pop_frac     = _clamp01((n   - CONF_POP_REF)   / CONF_POP_REF)      # 0 until populous
    won_recent   = 1.0 if (step - getattr(colony, 'last_victory_step', -10**9)
                           < CONF_WIN_WINDOW) else 0.0
    # distress signals — zero in ordinary condition
    starving   = 1.0 if food < 2 * BOOTSTRAP_FLOOR else 0.0
    acute = any(getattr(self, a, 0) > step for a in (
        'cold_until', 'arena_cold_until', 'arena_heat_until',
        'flood_until', 'hail_until', 'storm_until'))                    # reuse _nature_mood's set
    threatened = 1.0 if (getattr(colony, 'at_war', False) or acute) else 0.0
    target = (0.5
              + CONF_W_SURPLUS * surplus_frac
              + CONF_W_POP     * pop_frac
              + CONF_W_WIN     * won_recent
              + CONF_W_FAV     * fav            # SIGNED: negative favoritism pulls down
              - CONF_W_STARVE  * starving
              - CONF_W_THREAT  * threatened)
    return float(np.clip(target, 0.0, 1.0))

def _disposition_tick(self):
    """DP2/DP4: move each living colony's confidence toward its material target
    with inertia; decay favoritism (medium) and agitation (fast) toward neutral.
    Pure — consumes NO RNG, always-on (no breached gate)."""
    for colony in self.colonies:
        if not colony.is_alive():
            continue
        c   = getattr(colony, 'confidence', 0.5)
        tgt = self._disposition_confidence_target(colony)
        colony.confidence = float(np.clip(c + CONF_RATE * (tgt - c), 0.0, 1.0))
        # favoritism decays toward 0 (multiplicative — never overshoots)
        colony.favoritism = float(np.clip(
            getattr(colony, 'favoritism', 0.0) * FAV_RETAIN, -1.0, 1.0))
        # agitation decays fast toward 0
        colony.agitation = float(np.clip(
            getattr(colony, 'agitation', 0.0) * AGIT_RETAIN, 0.0, 1.0))
```

**Note on `_clamp01`:** reuse the existing M3 helper `_clamp01`
(`sandkings.py`, used by SPEC_WAGES / SPEC_BARGAIN). If it is a module function
not a method, call it unqualified as those specs do.

**Tick placement (real anchor).** `_disposition_tick` must run **before** the
stage-5 per-colony loop (`# 5. Food consumption and starvation`, `for colony in
self.colonies:` at `sandkings.py:1678–1679`) because that loop contains the
aggression reads (`_execute_unit_ai` at `:1838`) that consume the confidence, and
because SPEC_BARGAIN's `_bargain_tick` (its stage 4b) — which reads confidence
for the force-EV bias (DP7) — also runs there. Insert immediately after the
neural-pruning block (`:1666–1677`) and **before** `_bargain_tick()`, so the
bargain EVs read THIS step's confidence:

```
        # 4a. THE DISPOSITION (SPEC_DISPOSITION DP2): update confidence from
        #     material condition; decay favoritism/agitation. Pure, no RNG.
        self._disposition_tick()
        # 4b. THE BARGAIN (SPEC_BARGAIN BG7): _bargain_tick() — reads confidence
        #     (DP7) for the force-EV bias.  [added by SPEC_BARGAIN, if enabled]

        # 5. Food consumption and starvation (DARWINIAN PRESSURE)
        for colony in self.colonies:
            ...
```

> **Inertness (SPEC-wide convention).** `_disposition_tick` is added ONLY to
> `SandKingsSimulation.step`. `EnhancedSandKingsSimulation.step`
> (`sandkings_evolution.py:301`) is a fully independent step that does NOT call it
> and uses `_execute_enhanced_ai` (not `_execute_unit_ai`), so in the evolution
> engine `confidence` stays frozen at its `0.5` default and every DP effect is the
> identity transform — the evolution sim is byte-identical to today. This is the
> DP1-default guarantee doing the inertness work: the READS are identity at the
> defaults; only the TICK (added in one place) animates the state.

**Contract (`_disposition_tick`):**
- **Require** — called once per `SandKingsSimulation.step`, before the stage-5
  loop at `:1679`.
- **Guarantee** — consumes ZERO RNG; mutates only `confidence`/`favoritism`/
  `agitation` on living colonies; each stays in range.
- **Maintain** — an ordinary colony (`food ≤ CONF_RICH_FOOD`, `n ≤ CONF_POP_REF`,
  not starving, not threatened, `favoritism == 0`) has `target == 0.5` exactly, so
  from the `0.5` default `confidence` stays exactly `0.5`.
- **Assert** — after the tick, for every living colony the three ranges hold and
  no `random.*` was called (a counting spy sees no draws from this method).

---

## DP3 — Favoritism: the keeper-treatment ledger (verb hooks)

`favoritism` tracks keeper **treatment events** — it is pure event bookkeeping and
so accumulates **pre- and post-breach alike** (DP-reconciliation with AW1: it does
not require awareness because it is a record OF the treatment, not a feeling about
a known being). Its downstream uses split by awareness:
- **always** feeds `confidence` (DP2, the `CONF_W_FAV` term) and the nature-level
  response;
- **post-breach only** nudges `keeper_sentiment` (DP5), where `_update_sentiment`
  already runs (AW3) — and the carved faces mirror that result (SPEC_FACES F2), so
  there is no parallel sentiment.

### DP3 helpers

```
def _disposition_grace(self, colony, dfav: float):
    """Kind treatment raises favoritism. Clamped. No RNG."""
    if colony is None or not colony.is_alive():
        return
    colony.favoritism = float(np.clip(
        getattr(colony, 'favoritism', 0.0) + dfav, -1.0, 1.0))

def _disposition_wrath(self, colony, dfav: float, dagit: float):
    """Cruel/startling treatment lowers favoritism and spikes agitation.
    dfav is subtracted (pass the positive magnitude). Clamped. No RNG."""
    if colony is None or not colony.is_alive():
        return
    colony.favoritism = float(np.clip(
        getattr(colony, 'favoritism', 0.0) - dfav, -1.0, 1.0))
    colony.agitation = float(np.clip(
        getattr(colony, 'agitation', 0.0) + dagit, 0.0, 1.0))

def _disposition_nearest(self, x: int, y: int):
    """Nearest LIVING colony to (x,y) by maw manhattan distance; None if none."""
    best, best_d = None, float('inf')
    for c in self.colonies:
        if not c.is_alive():
            continue
        mx, my, _ = c.maw.position
        d = abs(mx - x) + abs(my - y)
        if d < best_d:
            best_d, best = d, c
    return best
```

### DP3 — the verb hooks (real anchors; each is one added line/branch, RNG-free)

| Verb (anchor) | Treatment | Hook (append at end of the verb, after its `_log_event`) |
|---|---|---|
| `keeper_drop_food(x,y)` `:2306` | manna → grace, targeted | `self._disposition_grace(self._disposition_nearest(x, y), FAV_MANNA)` |
| `keeper_gift` claim `_claim_gift(colony,…)` `:2880` | gift → grace, to the claimant | `self._disposition_grace(colony, FAV_GIFT)` |
| `keeper_drought(on)` `:2351` | slow cruelty, all colonies, NO startle | on the `on and not was` branch: `for c in self.colonies: self._disposition_wrath(c, FAV_DROUGHT, 0.0)` |
| `keeper_release_cat()` `:2348` / threat species in `keeper_release` `:2325` | terror/threat, startle | for cat & threat species (`scorpion`/`spider`/`rodent`): `for c in self.colonies: self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)` |
| `keeper_temperature(direction)` `:2364` | harsh air, startle, all | `for c in self.colonies: self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)` |
| `keeper_ignite(x,y)` `:2377` | blast/poke, startle, LOCAL | for colonies with a unit within `FIRECRACKER_RADIUS` of (x,y): `self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)` |

- **Food species** (`cricket`/`ant`) introduced via `keeper_release` are food, not
  threat → **no** favoritism/agitation change (skip the hook for those).
- All hooks are gated by the verb being CALLED (keeper acts), consume no RNG, and
  write only DP1 fields, so they do not perturb the draw stream. `keeper_drought`
  writes only on the `on and not was` edge (matching the existing event log), so a
  no-op toggle changes nothing.

**Contract (verb hooks):**
- **Require** — the hook runs only inside the keeper verb it is attached to, after
  the verb's own effect and `_log_event`.
- **Guarantee** — writes only `favoritism`/`agitation` (clamped); consumes no RNG;
  a nearest-target hook is a no-op when there is no living colony.
- **Maintain** — grace and wrath are opposite-signed on `favoritism`; only the
  startling verbs (cat/threat-release/temperature/ignite) add `agitation`; drought
  does not (it is slow cruelty, not a startle).
- **Assert** — after any hook, the DP1 ranges hold.

---

## DP4 — Agitation: startle → dispersed/slower mobiles (identity at 0)

A high-agitation colony's mobiles are briefly **dispersed / slower**: on each unit
AI tick a unit may forfeit its purposeful action (it mills / freezes), with
probability proportional to agitation. This is **identity at agitation 0** and, to
keep the RNG stream byte-identical at neutral, the RNG draw is **guarded behind
`agitation > 0`** (short-circuit → no draw at agitation 0).

**Hook (real anchor).** At the top of `_execute_unit_ai` (`sandkings.py:6012`),
immediately after `x, y, z = unit.position` (`:6014`) and before the monitor
observe block:

```
        # DP4: a startled (agitated) colony's mobiles disperse / hesitate.
        # Guarded so agitation==0 draws NO RNG (byte-identical at neutral).
        ag = getattr(colony, 'agitation', 0.0)
        if ag > 0.0 and random.random() < AGIT_FREEZE * ag:
            return   # this unit mills this step (slower); resumes next step
```

Agitation ALSO makes a colony *slightly more hostile* — that term lives in
`_aggression_eff` (DP5), not here, so a startled colony both hesitates to
coordinate (this mill) and lashes out locally (the `AGIT_HOSTILITY` term).

- **Require** — reached at the entry of every `_execute_unit_ai` call.
- **Guarantee** — at `agitation == 0` the branch short-circuits before `random.*`,
  so no draw occurs and unit behaviour is byte-identical; at `agitation > 0` the
  unit forfeits its action with probability `AGIT_FREEZE·agitation`.
- **Assert** — the `random.random()` call is unreachable when `agitation == 0.0`.

---

## DP5 — Confidence → effective aggression (`_aggression_eff`, identity at neutral)

The single read every raid/combat propensity site uses. `f(confidence)` is exactly
`1.0` at `confidence == 0.5`; `agitation` adds a small hostility term that is `0`
at `agitation == 0`. So `_aggression_eff` equals the base genome aggression
**exactly** at neutral values.

```
def _aggression_eff(self, colony) -> float:
    """DP5: effective aggression = base * f(confidence) + hostility(agitation).
    f(0.5) == 1.0 and hostility(0) == 0.0, so this equals genome.aggression
    EXACTLY at neutral. Pure; no RNG. May exceed 1.0 (a bold colony 'grown
    dominant') — the probability read-sites saturate naturally, and tests may
    assert the modulation > 1.0."""
    base = getattr(colony.genome, 'aggression', 0.5)
    conf = getattr(colony, 'confidence', 0.5)
    ag   = getattr(colony, 'agitation', 0.0)
    return base * (1.0 + CONF_AGG_K * (conf - 0.5)) + AGIT_HOSTILITY * ag
```

**Hook sites (real anchors).** Replace the direct `colony.genome.aggression` read
at the three **raid / combat propensity** probability reads with
`self._aggression_eff(colony)`:

| Site (anchor) | Before | After |
|---|---|---|
| raze enemy field `:6304` | `random.random() < colony.genome.aggression * 0.1` | `random.random() < self._aggression_eff(colony) * 0.1` |
| attack-move to enemy `:6352` | `random.random() < colony.genome.aggression` | `random.random() < self._aggression_eff(colony)` |
| siege enemy maw `:6382` | `random.random() < colony.genome.aggression` | `random.random() < self._aggression_eff(colony)` |

- At neutral (`confidence 0.5`, `agitation 0`), `_aggression_eff == genome.aggression`
  exactly → the `random.random() < threshold` OUTCOME is identical → byte-identical.
- The number of RNG draws is unchanged at every site (the helper is pure); only the
  threshold value changes, and only once confidence/agitation diverge from neutral.
- **NOT hooked (flagged):** the R1 BETRAY threshold in `_run_policy_cascade`
  (`:5078`, `aggression > 0.75 …`) and the war-entry FOOD gate (`:1793`,
  `food_stored > enter_at`). Betrayal is an explicit treachery declaration (the
  same surface SPEC_BARGAIN BG6 deliberately leaves ungated), and war entry is a
  hoard threshold, not an aggression read. Folding either in broadens the
  behaviour-change surface. **Fork #A — flagged for reviewer** (a one-line analogous
  swap at `:5078` if a bold colony should also betray more readily).

**Contract (`_aggression_eff`):**
- **Require** — `colony.genome` present; called only at the three propensity reads.
- **Guarantee** — returns `genome.aggression` EXACTLY when `confidence == 0.5 and
  agitation == 0.0`; pure, no RNG, no mutation; may exceed `1.0`.
- **Maintain** — the three read-sites keep their existing draw count and RNG order.
- **Assert** — at neutral values `abs(_aggression_eff(colony) -
  genome.aggression) == 0.0`.

---

## DP6 — Favoritism does NOT touch keeper_sentiment (RECONCILED: coupling removed)

**Reversed during implementation.** The original design had favoritism *nudge*
`keeper_sentiment` post-breach. In practice that (a) DOUBLE-COUNTS keeper treatment —
the SPEC_FACES arc already moves `keeper_sentiment` from the SAME feed/drought events
that move favoritism (DP3) — and (b) the per-call additive term ACCUMULATES a
persistent favoritism into sentiment every `_update_sentiment` call, saturating the
band and desyncing the faces calibration (it broke `tests/test_faces.py`).

**Resolution:** favoritism does NOT feed `keeper_sentiment`. `_update_sentiment` is
left exactly as SPEC_FACES defines it. A favoured colony still shows a devout face —
via the NORMAL sentiment path (feeding raises `keeper_sentiment` → devout band), not
via a second favoritism term. Favoritism's job is confined to driving **confidence**
(DP2, the `CONF_W_FAV` term) and display (DP9). `SENTIMENT_FAV_W` is removed. This
keeps the SPEC_FACES / SPEC_AWARENESS suites byte-identical and avoids a redundant
parallel push on the same signal.

**Nature-level pre-breach response (optional/deferred).** DP3 requires favoritism
to feed "the nature response" pre-breach. It does so **through confidence** (the
`CONF_W_FAV` term in DP2 — the nature-level meter). A direct tilt of
`_nature_mood` (`:2259`) at the favoritism extremes (|favoritism| ≥ `CONF_FAV_BAND`
→ lean toward bounty/dread) is **deferred as OPTIONAL** to keep the pre-breach
carving glyph byte-identical at neutral; feeding confidence satisfies DP3 without a
second `_nature_mood` behaviour surface. **Fork #B — flagged** (implement the
`_nature_mood` tilt only if the reviewer wants favoritism to change the pre-breach
NATURE glyph directly, not just via confidence).

- **Require** — reached only from `_update_sentiment` (post-breach, AW3).
- **Guarantee** — adds `SENTIMENT_FAV_W · favoritism` to the drift; identity at
  `favoritism == 0`; result clamped `[0,1]`.
- **Maintain** — no parallel sentiment field; the faces read `keeper_sentiment` as
  before.
- **Assert** — with `favoritism == 0`, `keeper_sentiment` after `_update_sentiment`
  equals its pre-DP value.

---

## DP7 — Confidence → bargain force-EV bias (gated by BARGAIN_ENABLED, neutral at 0.5)

A bold colony tilts its per-pair bargain toward FORCE (subjugate/annihilate); a
meek one toward WAGE. This is a bias term that is **exactly zero (factor 1.0) at
`confidence == 0.5`** and lives only inside the SPEC_BARGAIN EV helpers, which run
only when `BARGAIN_ENABLED` — so it touches **only the already-gated economy** and
is doubly inert by default (disabled arc AND identity at neutral confidence).

```
def _disposition_boldness(self, colony) -> float:
    """DP7: force-EV multiplier from the extractor's boldness. 1.0 at
    confidence 0.5; >1 bold (force nets more), <1 meek (wage preferred). Pure."""
    conf = getattr(colony, 'confidence', 0.5)
    return 1.0 + BARGAIN_CONF_K * (conf - 0.5)
```

**Hook (SPEC_BARGAIN anchors).** Multiply the FORCE EVs — and only those — by the
**extractor's** boldness. In `_bargain_ev_brute` (SPEC_BARGAIN BG2b) the extractor
is `captor`; in `_bargain_ev_destroy` (BG2c) it is `aggressor`. `E_wage`
(BG2a) is left unmodified, so the tilt is a single force-side bias:

```
# BG2b _bargain_ev_brute, on the return:
    return (leaked - enforce - war_loss) * self._disposition_boldness(captor)

# BG2c _bargain_ev_destroy, on the return:
    return (BARGAIN_DESTROY_WEIGHT * composite_power(rival) * grudge - war_loss) \
           * self._disposition_boldness(aggressor)
```

- **Identity at `confidence 0.5`:** boldness `== 1.0`, so both force EVs are
  unchanged → `_bargain_pair_mode` is unchanged → SPEC_BARGAIN's BGA-1
  (byte-identical war entry) and BGA-4 (wages win at neutral) hold. BGA-4 constructs
  FRESH colonies (default `confidence 0.5`), so the pure-constants inequality
  `(1−W_FAIR)·WAGE_RELIABILITY > (1−W_BRUTE)·BRUTE_RELIABILITY` is untouched.
- When `confidence ≠ 0.5` in a `--bargain` run this is the intended tilt: a bold
  colony's `E_brute`/`E_destroy` rise → mode moves toward SUBJUGATE/ANNIHILATE; a
  meek colony's fall → toward WAGE.

**Contract (`_disposition_boldness` + hook):**
- **Require** — the multiply is applied only inside the SPEC_BARGAIN force-EV
  helpers, which run only when `BARGAIN_ENABLED`.
- **Guarantee** — factor `== 1.0` at `confidence == 0.5` (identity); pure, no RNG;
  applied to force EVs only (E_wage untouched).
- **Maintain** — the arc's default-neutral guarantee: with `BARGAIN_ENABLED False`
  the helpers never run; with it True and confidence neutral, the EVs are unchanged.
- **Assert** — `_disposition_boldness(colony) == 1.0` iff `confidence == 0.5`.

---

## DP8 — Persistence, inheritance & inertness

- **Pickle:** all four DP1 fields getattr-guard to their neutral defaults on a
  pre-DP pickle (DP1 restore tuple at `:1695–1705`).
- **Respawn inheritance (real anchors — the crossed branch `:5945–5969`, the
  survivor branch `:5970–5986`):** follow the `keeper_sentiment` precedent, but
  split by kind:
  - `confidence` **INHERITS** like a temperament (a bloodline's boldness carries):
    crossed → `max(pa.confidence, pb.confidence)`; survivor → `parent.confidence`.
  - `favoritism` **RESETS to `0.0`** — it is a ledger of how the god treated the
    *dead* colony; a cadet starts with a clean treatment slate.
  - `agitation` **RESETS to `0.0`** — it is a transient startle, not heritable.
  - `last_victory_step` **RESETS to `-10**9`** — the new colony has won nothing yet.
  This is **Fork #C (flagged but RESOLVED as recommended):** confidence inherits,
  favoritism/agitation/last_victory reset. A reviewer preferring confidence to also
  reset to `0.5` (temperament reborn neutral) should say so — it is a one-line
  change in both respawn branches.
- **Inertness:** `_disposition_tick` is NOT added to
  `EnhancedSandKingsSimulation.step` (`sandkings_evolution.py:301`); confidence
  stays `0.5` there and every DP effect is identity → the evolution sim is
  byte-identical to today.

---

## DP9 — Surfacing (display-only)

- **Dashboard House card (SPEC_DASHBOARD):** add display-only `confidence`,
  `favoritism`, `agitation` (rounded) beside the existing `face` field. Read-only;
  no control flow keys off a surfaced value.
- **Live-view inspect (SPEC_LIVE_VIEW):** the unit/colony inspect panel shows the
  three scalars (e.g. `bold 0.72 · favor +0.30 · agit 0.00`). Purely informational
  — the keeper reads a colony's boldness/mood at a glance.
- **OPTIONAL / deferred vocabulary tie-in:** a `bold` / `cowed` disposition could
  map onto the `trade` / `thrall` economy anchors (SPEC_HIVE_MONITOR M15) or a new
  anchor. **Noted and deferred** — not in scope here; flagged so a later vocab pass
  can pick it up.

---

## DP10 — Constants (DP8 table)

| Constant | Value | Meaning |
|---|---|---|
| `CONF_RATE` | `0.02` | inertia: fraction of (target − confidence) applied per tick |
| `CONF_W_SURPLUS` | `0.25` | weight of food surplus (above `CONF_RICH_FOOD`) on the confidence target |
| `CONF_W_POP` | `0.15` | weight of population surplus (above `CONF_POP_REF`) |
| `CONF_W_WIN` | `0.15` | weight of a recent war victory |
| `CONF_W_FAV` | `0.25` | weight of (signed) favoritism on the confidence target |
| `CONF_W_STARVE` | `0.35` | penalty when `food < 2·BOOTSTRAP_FLOOR` |
| `CONF_W_THREAT` | `0.15` | penalty when at war or under acute weather |
| `CONF_RICH_FOOD` | `WAR_CHEST` (`400`) | food above which surplus registers (reuses `WAR_CHEST`) |
| `CONF_POP_REF` | `20` | population above which pop-surplus registers |
| `CONF_WIN_WINDOW` | `400` | steps a victory counts as "recent" |
| `CONF_AGG_K` | `0.8` | confidence→aggression gain: `f(conf)=1+K·(conf−0.5)` (conf 1.0 → ×1.4; conf 0 → ×0.6) |
| `AGIT_HOSTILITY` | `0.3` | additive hostility term on `_aggression_eff` per unit agitation |
| `AGIT_FREEZE` | `0.5` | max mill probability at agitation 1.0 (DP4) |
| `AGIT_SPIKE` | `0.5` | agitation added per startling wrath verb (DP3) |
| `AGIT_RETAIN` | `0.7` | agitation multiplicative retention per tick (fast decay) |
| `FAV_RETAIN` | `0.995` | favoritism multiplicative retention per tick (slow decay toward 0) |
| `FAV_MANNA` | `+0.15` | favoritism gained when the nearest colony is manna-fed |
| `FAV_GIFT` | `+0.25` | favoritism gained by the colony that claims a gift |
| `FAV_DROUGHT` | `0.10` | favoritism lost (magnitude) by all colonies when drought is switched on |
| `FAV_WRATH` | `0.20` | favoritism lost (magnitude) per wrath verb (cat/threat-release/temperature/ignite) |
| `SENTIMENT_FAV_W` | `0.10` | favoritism nudge to `keeper_sentiment` per `_update_sentiment` (post-breach, DP6) |
| `BARGAIN_CONF_K` | `0.5` | boldness gain on force EVs: `1+K·(conf−0.5)` (conf 1.0 → ×1.25; conf 0 → ×0.75) |
| `CONF_FAV_BAND` | `0.3` | (Fork #B, deferred) `|favoritism|` threshold for a direct `_nature_mood` tilt |

Place the block beside the keeper/faces constants (`sandkings.py:234–248`). The
**load-bearing identity constants** are the ones that make each effect identity at
neutral: `f(0.5)=1.0` (from the `(conf−0.5)` form, independent of `CONF_AGG_K`),
`AGIT_HOSTILITY·0=0`, `SENTIMENT_FAV_W·0=0`, `_disposition_boldness(0.5)=1.0`, and
the neutral-band target (`0.5` when every signal is 0). Any retune MUST preserve
those zero-points.

---

## DP11 — Reconciliation (explicit ADD vs REUSE)

| Existing system | Anchor | This spec REUSES | This spec ADDS |
|---|---|---|---|
| `keeper_sentiment` / `_update_sentiment` | `:2224` | the scalar + its drift + clip; post-breach-only run (AW3) | a `SENTIMENT_FAV_W·favoritism` nudge term (DP6), identity at fav 0 |
| carved faces (`face_favor`, `CARVE_SYMBOLS`) | SPEC_FACES F1/F2 | the whole face band — it mirrors `keeper_sentiment` unchanged | nothing (no parallel face/mood) |
| `_nature_mood` / `NATURE_SYMBOLS` | `:2259` | the pre-breach mood glyph, unchanged at neutral | (deferred) an optional favoritism tilt (Fork #B) |
| awareness gate `breached` | SPEC_AWARENESS AW1 | the gate for keeper-directed feeling | confidence is NATURE-level (does NOT gate on breached); favoritism accrues pre-breach, nudges sentiment post-breach |
| `keeper_attitude` (none/reverent/wrathful) | `:2296` | the derived attitude driving F1/AW | favoritism is an independent, finer-grained treatment ledger (not derived) |
| genome `aggression` | `:775` | the base trait at the three propensity reads | `_aggression_eff` = base·f(conf)+hostility(agit), identity at neutral (DP5) |
| SPEC_BARGAIN force EVs | BG2b/BG2c | the EV model + `BARGAIN_ENABLED` gate | a boldness multiplier on E_brute/E_destroy, identity at conf 0.5 (DP7) |
| `_plunder_techs` (victor) | `:2832` | the existing victor-identified choke point | one line: `victor.last_victory_step = self.step_count` (after `:2847`), read-only elsewhere |

The victory hook (real anchor): in `_plunder_techs`, immediately after the
`if victor is None: return` at `:2846–2847`, add
`victor.last_victory_step = self.step_count`. It writes a new field only the
disposition tick reads; no RNG, no behaviour change.

---

## DP12 — Acceptance (`tests/test_disposition.py`)

Clause **DPA-1 is FIRST and gating (neutral ⇒ identity).**

1. **DPA-1 — NEUTRAL ⇒ IDENTITY (mechanical, no long run).**
   - `_aggression_eff(colony)` with `confidence == 0.5`, `agitation == 0.0` equals
     `colony.genome.aggression` **exactly** (float-equal).
   - `_disposition_boldness(colony)` with `confidence == 0.5` equals `1.0` exactly;
     `_bargain_ev_brute`/`_bargain_ev_destroy` on a neutral-confidence extractor
     equal their un-multiplied values.
   - `_update_sentiment` with `favoritism == 0.0` leaves `keeper_sentiment` at its
     pre-DP value.
   - `_disposition_tick` on an ordinary colony (`food ≤ CONF_RICH_FOOD`,
     `n ≤ CONF_POP_REF`, not starving/threatened, `favoritism 0`) leaves
     `confidence == 0.5` and, under a `random.*` counting spy, consumes **zero
     draws**. The DP4 mill draws no RNG at `agitation == 0`.
2. **DPA-2 — bold rise.** A well-fed, favoured colony (`food > CONF_RICH_FOOD`,
   populous, `favoritism > 0`) run through several `_disposition_tick`s has rising
   `confidence` and `_aggression_eff(colony) > genome.aggression` (the modulation
   **exceeds 1.0×**).
3. **DPA-3 — cowed fall.** A starved / abused colony (`food < 2·BOOTSTRAP_FLOOR`
   and/or `favoritism < 0`) has falling `confidence` and
   `_aggression_eff(colony) < genome.aggression`.
4. **DPA-4 — agitation spikes & decays fast.** A wrath verb (cat / temperature /
   ignite) spikes `agitation` by ~`AGIT_SPIKE`; repeated `_disposition_tick`s decay
   it toward `0` markedly faster than favoritism decays (`AGIT_RETAIN < FAV_RETAIN`).
5. **DPA-5 — favoritism → keeper_sentiment POST-breach only.** For a `breached`
   colony, positive favoritism lifts `keeper_sentiment` across `_update_sentiment`
   and negative lowers it; for an UN-breached colony `_update_sentiment` is not
   called (AW3) so sentiment does not move.
6. **DPA-6 — favoritism ledger.** `keeper_drop_food`/`keeper_gift`(claim) raise the
   targeted/claiming colony's `favoritism`; `keeper_drought(True)`/`release_cat`/
   `keeper_temperature`/`keeper_ignite` lower it; it decays toward `0` under
   `_disposition_tick`. Food-species release (`cricket`/`ant`) does NOT change it.
7. **DPA-7 — pickle & inheritance.** All four fields pickle and getattr-guard on a
   pre-DP pickle. On respawn: `confidence` inherits (crossed → max of parents;
   survivor → parent), `favoritism`/`agitation` reset to `0.0`,
   `last_victory_step` resets to `-10**9` (DP8 / Fork #C).
8. **DPA-8 — bargain tilt (gated).** With `BARGAIN_ENABLED` and a both-feasible
   pair: a bold extractor (`confidence` high) tilts `_bargain_pair_mode` toward
   SUBJUGATE/ANNIHILATE vs the same pair at neutral confidence; a meek extractor
   tilts toward WAGE; at `confidence 0.5` the mode equals the pre-DP bargain choice
   (BGA-4 preserved).
9. **DPA-9 — evolution inert.** `EnhancedSandKingsSimulation.step` never calls
   `_disposition_tick`; a run leaves every colony's `confidence == 0.5` and is
   byte-identical to a pre-DP evolution run.
10. **DPA-10 — at-risk suites (the always-on caveat, must be documented).** Because
    confidence is **always-on**, once a colony's material condition diverges its
    `_aggression_eff` changes a `random.random() < threshold` OUTCOME, which shifts
    the whole downstream RNG trajectory. This is the **intended** DP6 behaviour
    change, not a regression, but it means:
    - **Invariant-asserting suites are SAFE** (assert alive / event-present /
      monotonic, not exact frozen trajectories): the soak / liveness suites,
      and the behavioural assertions in `test_keeper.py` / `test_faces.py` /
      `test_awareness.py`. These should still be re-run; timing may shift but the
      asserted invariants hold.
    - **Any suite holding a committed EXACT-trajectory golden** (frozen RNG-draw
      count, exact per-step `war_target` sequence, exact combat outcome over many
      steps) that was baked **before** disposition landed must be **re-captured
      once**. Note SPEC_BARGAIN is spec-first / unimplemented, so its BGA-1 /
      BGA-4 goldens will be captured **with** disposition already present and are
      therefore internally consistent (both baseline and test run disposition-on) —
      no conflict, provided BGA-4 uses fresh (`confidence 0.5`) colonies.
    - The acceptance test MUST pin **neutral ⇒ identity** (DPA-1) as the guarantee;
      it does NOT claim a byte-identical full battery (unlike a gated arc), because
      the layer is deliberately always-on.

---

## Ambiguities / forks flagged (not silently resolved)

- **Fork #A — R1 BETRAY not modulated (DP5).** `_aggression_eff` hooks the three
  raid/combat propensity reads only; the betrayal threshold at `:5078` and the
  war-entry food gate at `:1793` are left as-is (matching SPEC_BARGAIN BG6's
  discipline of a minimal behaviour-change surface). Flagged if a reviewer wants a
  bold colony to also betray more readily.
- **Fork #B — favoritism → `_nature_mood` direct tilt deferred (DP6).** Pre-breach,
  favoritism feeds the nature-level response THROUGH confidence (DP2). A direct
  glyph tilt of `_nature_mood` at the favoritism extremes is deferred as OPTIONAL
  (`CONF_FAV_BAND`) to keep the pre-breach carving byte-identical at neutral.
- **Fork #C — confidence inherits, favoritism/agitation reset (DP8).** Recommended
  and baked in (confidence = temperament, carries; favoritism = a ledger of the
  dead colony's treatment, resets; agitation = transient, resets). Flagged in case
  the reviewer prefers confidence reborn at neutral `0.5`.
- **Confidence target formula (the flagged design fork).** DP2's neutral-band
  formula (each signal 0 in ordinary condition → target exactly 0.5) is a concrete
  proposal chosen specifically to make neutral ⇒ identity mechanical. The exact
  weights (`CONF_W_*`) and references (`CONF_RICH_FOOD`, `CONF_POP_REF`) are
  tunable; the **load-bearing invariant** is the zero-point: an ordinary colony's
  target must be exactly `0.5`. A reviewer wanting a different curve (e.g. smooth
  sigmoid on food/pop rather than the clamped-hinge band) may retune as long as the
  ordinary-condition target stays exactly `0.5`.

---

## Status / Reconciliation

- **Drafted 2026-07-11. Spec-first: implementation pending.** Ports the external
  Sandkings keeper-treatment → disposition layer (favoritism / confidence /
  agitation), adapted and reconciled with the terrarium's existing keeper (K),
  faces (F), awareness (AW), and bargain (BG) systems.
- **Reuses, does not duplicate:** `keeper_sentiment`/`_update_sentiment`,
  `face_favor`/`CARVE_SYMBOLS`, `_nature_mood`/`NATURE_SYMBOLS`, genome
  `aggression`, `composite_power`, and the SPEC_BARGAIN force EVs. Adds three
  pickled scalars + `last_victory_step`, one pure `_disposition_tick`,
  `_aggression_eff`, `_disposition_boldness`, the agitation mill, six keeper-verb
  hooks, and one victory-choke-point line.
- **Default-neutral strategy:** every effect is the identity transform at the DP1
  neutral defaults (`confidence 0.5`, `favoritism 0`, `agitation 0`); the reads are
  pure and identity-at-default, and only `_disposition_tick` (added in ONE place,
  not in the evolution step) animates the state — so a fresh sim and the evolution
  sim are byte-identical to today. Unlike a gated arc, the layer is **always-on**:
  divergence is intended once a colony's condition diverges (DPA-10).
- **Real anchors verified against `sandkings.py`:** keeper verbs `:2306/2325/2348/
  2351/2364/2377/2561`, `_claim_gift:2880`, `_update_sentiment:2224`,
  `_nature_mood:2259`, `keeper_attitude:2296`, carve tick `_keeper_tick:2638`
  (called `:1848`), aggression reads `:6304/6352/6382`, `_execute_unit_ai:6012`,
  `_plunder_techs:2832`, `composite_power:456`, `ColonyGenome.aggression:775`,
  respawn `:5945/5970`, init defaults `:1015`, pickle restore `:1695`, stage-5 loop
  `:1678`.
</content>
</invoke>
