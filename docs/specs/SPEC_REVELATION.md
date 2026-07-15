# SPEC: Revelation & the Priesthood — R1…R4

Governing intent (user, verbatim, across messages): "worshipers (those who see 'signs beyond the glass')… a
priestly caste, small in number, just below managers, who intercede for the rest and guide policy… priests
'channel' the madness, they speak of a 'great mind beyond the glass'… let 'pages' fall from the sky with
'strange writings' the creatures 'learn' from… like Plato's allegory of the cave… we don't have to think of
HOW, it just happens, but the maws should have to LEARN to decode… always useful (novel utility)… think
ouroboros." Build order: this is item 3 of 3 (after Cortés + siege). Madness (SPEC_MADNESS) is the substrate —
the price of channeling.

Design decisions (from the user's fork answers):
- **The night sky is the projection surface** (currently dead real-estate). A "sign" appears there; we do NOT
  render a literal projector — the sign "just happens" (Plato's cave), the MECHANIC is the maw LEARNING to
  decode it.
- **Decode is a per-colony `literacy` curriculum** [0,1] that rises with exposure; priests (R2) accelerate it.
- **Payoff is POLYMORPHIC by sign TYPE** (user chose ALL): tech/recipe unlock (unearthed writing) · behavior/
  stat nudge · keeper favor/edict · portent/omen. (Word2vec-anchor shift is the richest future form; R1 uses
  the existing enlightenment/memory scalars.)
- Baseline-ON, opt-out `--no-revelation`, in `_GATE_NAMES`, byte-identical off.

Cross-references (not duplicated):
- **SPEC_MADNESS** — the channeling cost; R2 priests trade madness-risk for decode speed.
- keeper/awakening spine — `keeper_sentiment`, `breached`, `worshipped`, `enlightened`, `memory_augment`,
  `confidence`. R1 reads/writes these as the payoff surface (it does NOT add a parallel god system).

---

## R1 — Signs in the sky + the decode curriculum (FOUNDATION)

State: `sim.sky_sign` — the sign currently up, or None: a plain dict `{kind, since, decoded_by:set}`
(checkpoint-safe). Per-colony `literacy` float [0,1] (getattr-guarded).

`_revelation_tick()` — gated `REVELATION_ENABLED`:
- **Raise** (no sign up, `step % SIGN_INTERVAL == 0`): a new sign appears. Its `kind` is chosen by a
  DETERMINISTIC rotation over `SIGN_KINDS` keyed on a running sign counter (no RNG → gate-independent).
- **Study** (a sign is up): each living colony gains `literacy += LITERACY_GAIN` (accelerated ×
  `LITERACY_DEVOUT_MULT` when `worshipped` or `keeper_sentiment` is high — the devout read faster; R2 makes
  this the priest's edge). When a colony's `literacy >= DECODE_THRESHOLD` and it has not yet decoded THIS sign,
  it DECODES → `_apply_sign_payoff(colony, kind)`, add it to `decoded_by`, log a max-salience beat, and reset
  its `literacy` to 0 (ready for the next sign).
- **Retire** the sign after `SIGN_DURATION` steps (set `sky_sign=None`).

`_apply_sign_payoff(colony, kind)` — the polymorphic novel utility (each ALWAYS useful):
- `'writing'` (tech): grant one native tech the colony lacks (unearthed anthropological writing) — reuses the
  tech-grant path (`colony.techs.add`, xp seeded). If it knows them all, fall through to `'edict'`.
- `'omen_war'` (behavior/portent): raise `genome.aggression` and `confidence` (they foresee war) toward 1.
- `'omen_plenty'` (behavior/portent): raise `genome.expansion_rate` and `keeper_sentiment` (a sign of favor).
- `'edict'` (keeper favor): raise `keeper_sentiment` strongly + a `confidence` spike (a divine directive).
All nudges are clamped and use existing fields; `enlightened=True` is set on any decode (the mind that reads
the sky is enlightened, EN8).

**Contract.** Require: gate on. Guarantee: `literacy`,`keeper_sentiment`,`confidence` ∈ [0,1]; a colony decodes
a given sign at most once; `sky_sign` cycles raise→study→retire. Maintain: gate off → `_revelation_tick` never
runs, no `sky_sign`/`literacy` created → battery byte-identical.

**Render (live_view, pure).** When `sky_sign` is up, inscribe the sign's glyph across the top "sky" rows of the
board (a row of the sign glyph), tinted by kind — the maw's Plato's-cave projection. Pure read; legend gains a
`sky` category. (Ouroboros easter eggs — signs that reference the sim's own state — are future content.)

**Acceptance R1 (`tests/test_revelation.py`).**
- Gate default OFF; gate-off full battery byte-identical.
- A sign is raised on cadence; a colony studying it accrues `literacy` and, past `DECODE_THRESHOLD`, decodes
  once (in `decoded_by`) with the kind's payoff applied (tech added / stat raised / sentiment raised).
- The sign retires after `SIGN_DURATION`.

## R2 — The priest caste (channelers)

A small per-unit `is_priest` role (getattr-guarded, not a 4th UnitType) with `priest_kind ∈ {prophet,
soothsayer}` — below managers. TWO kinds (user's choice):
- **Mad prophets** — ordained when a colony's `madness >= PROPHET_MADNESS_MIN`. They channel the great mind:
  decode ×`PROPHET_DECODE_MULT` (fast), but each priest-tick raises colony `madness` by `PROPHET_MADNESS_RISK`
  per prophet, and at `PROPHET_BREAK_MADNESS` one prophet BREAKS (Cthulhu — dies raving, a pressure valve that
  fires below the MAD-2 house-death threshold).
- **Ordained soothsayers** — ordained when the colony is devout (`keeper_sentiment >= SOOTHSAYER_SENTIMENT_MIN`
  or `worshipped`) and not maddened. Stable: decode ×`SOOTHSAYER_DECODE_MULT`, no madness cost, and each gathers
  a `SOOTHSAYER_TITHE` to the maw (the political tax).

`_priest_tick` (gated `PRIESTHOOD_ENABLED`, cadence `PRIEST_TICK`): ordain one priest per colony up to
`PRIEST_MAX_FRAC` of its units (prophet if maddened else soothsayer if devout), then channel/break/tithe every
tick. `_colony_decode_mult` feeds the R1 study step (gated) so priests are literally THE decoders.
Deterministic (no RNG); ordination picks the first lay unit. Gate off → no priests, no decode bonus, no madness
cost → byte-identical. `live_view` tints prophets violet, soothsayers gold (pure read).

**Acceptance R2 (`tests/test_revelation.py`).**
- A maddened colony ordains a prophet; a devout colony ordains a soothsayer; the caste never exceeds the cap.
- A prophet raises the colony's decode multiplier and its madness; at `PROPHET_BREAK_MADNESS` a prophet breaks
  (unit removed). A soothsayer tithes food to the maw.
- Gate off → no ordination, full battery byte-identical.

## R3 — Aztec sacrifice

`_sacrifice_tick` (gated `PRIESTHOOD_ENABLED`, cadence `SACRIFICE_TICK`): a priest-led house that HOLDS a
captive (`_held_thrall` — a unit in another house's ranks whose `laboring_for` is our id) and is TROUBLED
(`madness >= SACRIFICE_MADNESS_MIN` or the keeper is `wrathful`) offers the thrall to the gods beyond the glass:
- the captive dies on the altar (removed from its owner, drops a `CORPSE`);
- colony `madness *= (1 - SACRIFICE_RELIEF)` (the rite eases the raving — a second pressure valve alongside the
  R2 prophet-break);
- `keeper_sentiment` and `confidence` rise by `SACRIFICE_FAVOR` (the gods appeased, the house steeled).
Deterministic (no RNG); ties the priesthood to the madness (SPEC_MADNESS) and the subjugation/suzerain thrall
systems. Gate off → no rite → byte-identical.

**Acceptance R3 (`tests/test_revelation.py`).** A priest-led, maddened house holding a thrall sacrifices it:
the thrall is removed, colony madness drops, keeper favor rises. No thrall / no priest / untroubled → no rite.

## R4 — Holy war

`_holy_war_tick` (gated `PRIESTHOOD_ENABLED`, cadence `HOLY_WAR_TICK`): a zealous, priest-led house
(`keeper_sentiment >= HOLY_WAR_SENTIMENT_MIN`) not already at war names the most divergent living INFIDEL — the
non-kin, non-allied house with the largest `keeper_sentiment` gap (plus a bump for an enlightenment schism,
`>= HOLY_WAR_DIVERGENCE`) — and launches a HOLY WAR: sets `war_target`, `at_war`, drives mutual trust down by
`HOLY_WAR_TRUST_HIT` (foreclosing truce/alliance), and marks `holy_war_until = step + HOLY_WAR_DURATION`. A
gated one-line guard in the war-footing stand-down (sandkings.py ~2349) clears `poor` while `holy_war_until`
holds, so ZEAL — not the hoard — sustains the crusade until the infidel falls. War is hostile-by-default, so
R4 DIRECTS aggression (not flips it): the priesthood chooses the enemy by faith. Deterministic (no RNG). Gate
off → no crusade, and the stand-down guard is inert → byte-identical.

**Acceptance R4 (`tests/test_revelation.py`).** A zealous, priest-led house with a divergent-faith neighbor
launches a holy war (`war_target` set to that neighbor, `holy_war_until` in the future, trust driven down).
A house with no priest / low zeal / no divergent neighbor does not.

## Constants (sandkings.py)

```
REVELATION_ENABLED = False   # gate (module default False -> byte-identical; entrypoint flips, --no-revelation)
SIGN_INTERVAL   = 200        # steps between a retired sign and the next appearing
SIGN_DURATION   = 120        # steps a sign stays up in the sky
SIGN_KINDS      = ('writing', 'omen_war', 'omen_plenty', 'edict')   # deterministic rotation
LITERACY_GAIN   = 0.02       # literacy gained per step a colony studies a sign
LITERACY_DEVOUT_MULT = 2.0   # the devout (worshipped / high sentiment) read faster
DECODE_THRESHOLD = 1.0       # literacy at which a colony decodes the sign
SIGN_NUDGE      = 0.15       # magnitude of a stat/sentiment nudge on decode
```
