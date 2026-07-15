# SPEC: Madness & Extinction (Round 6) — MAD-1…MAD-6

Governing intent (user, verbatim): "a house can go extinct — disappear from
the board, its name a disgraced gravestone — by two vectors, GoT-style."

Scope: a house may now END (extinct: replaced by a *fresh unrelated* house at
respawn, its name kept forever as a gravestone in `house_epithets`) rather than
continue as a cadet of a surviving bloodline. Two vectors reach extinction:
**MADNESS** (natural, rare, shameful — "the Mad") and **CONFLICT** (dog-eat-dog,
honorable — an earned `derive_epithet`). This round adds the madness accumulator,
the crack trigger, the shameful override, the survivor warning, and the
identity fork at respawn — and nothing else.

Cross-references (this spec does NOT duplicate them):
- **SPEC_DISPOSITION.md** (DP1–DP12) — owns `agitation`, `favoritism`,
  `confidence`, `_disposition_tick`, `_disposition_wrath`. Madness reads
  `agitation` and adds a NEW accumulator alongside them.
- **SPEC_FACES.md** (F1–F3) — owns `keeper_sentiment`, the `hateful` band
  (<0.33), and the `_sentiment_wrath` "cracked once" latch. Madness reads
  these as its neglect signal; it does NOT move `keeper_sentiment` on the
  mad maw (only on survivors, MAD-3).
- **SPEC_DYNASTIES.md** (D1–D2) — owns house names, `derive_epithet`,
  `EPITHET_RULES`, the chronicle `SALIENCE` table, and the cadet-respawn
  identity rules. Madness OVERRIDES the earned epithet with "the Mad" and
  FORKS the respawn identity to a fresh house.
- **SPEC_TERRARIUM_LIVENESS.md** (T5/T6) — owns the death→corpse→
  `pending_respawns`→`_process_respawns`→`_respawn_colony` slot-refill spine.
  **The liveness invariant below is load-bearing: extinction changes only the
  IDENTITY minted at respawn; it never empties a slot.**
- **SPEC_POLITICS.md** (P12) — `apply_respawn_shadow` runs unchanged for the
  fresh house (folk memory of the banner/colony_id).

---

## THE LIVENESS INVARIANT (load-bearing — hard Require)

**Require (correctness, non-negotiable):** every madness/extinction death MUST
route through the EXISTING spine, unchanged in shape:

```
maw.alive = False
  → _check_maw_deaths()  (corpse feast, epithet, pending_respawns[cid] = step + RESPAWN_DELAY)
    → _process_respawns() (when due)
      → _respawn_colony(cid)  (SAME colony_id, slot refilled in place)
```

Extinction changes ONLY the *house identity* assigned inside `_respawn_colony`
(a fresh unrelated house instead of a cadet of a survivor's line). It MUST NOT:
- drop or reassign the `colony_id`,
- skip or reschedule `pending_respawns`,
- return early from / bypass `_check_maw_deaths` or `_respawn_colony`,
- leave the slot empty or reduce `len(self.colonies)`.

**Guarantee:** after a full death→respawn cycle the board has the same number
of colonies, the mad colony's `colony_id` is present and `is_alive()` is True,
and only its `house`/`generation`/`genome` differ from a normal (cadet) respawn.
This is the T5/T6 no-heat-death property. MAD-4 verifies it mechanically.

---

## MAD-1 — The madness accumulator (natural vector; RARE)

Agitation decays too fast to represent *sustained* neglect (verified:
`AGIT_RETAIN=0.7`, half-life ~2 steps). Madness needs a slow accumulator.

Add a per-colony float `colony.madness` ∈ [0,1] (getattr-guarded, pickled),
updated inside `_disposition_tick` (sandkings.py:2519–2534, which already
iterates living colonies, is pure, consumes no RNG, and runs at step section
4a — line 1827 — BEFORE `_check_maw_deaths` at line 2042 in the same step).

The maw is "raving" when it is BOTH highly agitated AND keeper-hated:
- highly agitated: `agitation >= MADNESS_AGIT_MIN`
- keeper-hated: `keeper_sentiment < 0.33` (the F1 hateful band) OR the
  `_sentiment_wrath` latch is set ("cracked once").

Ratchet up while raving (asymptotic toward 1, so a single wrath spike barely
moves it — RARE by construction); multiplicative decay otherwise.

**Contract.** Require: colony alive. Guarantee: `madness` ∈ [0,1], pure (no
RNG), identity at `MADNESS_RISE=0.0` (never rises → never cracks → today's
behavior exactly). Maintain: `madness` is monotone non-decreasing only while
raving; otherwise strictly decays toward 0.

**Acceptance MAD-1.**
- Drive `_disposition_tick` with `agitation >= MADNESS_AGIT_MIN` and
  `keeper_sentiment < 0.33` for N steps (re-spiking agitation each step, since
  it decays fast) → `colony.madness` rises monotonically to
  `>= MADNESS_THRESHOLD`.
- With `agitation = 0` (or `keeper_sentiment` high) → `madness` decays strictly
  toward 0 each tick.
- Identity: set `MADNESS_RISE = 0.0`; after any number of raving steps
  `madness` stays 0.0 (never cracks).

## MAD-2 — Madness death is EXTINCTION + DISGRACE

When `colony.madness >= MADNESS_THRESHOLD` (checked in `_disposition_tick`
right after the accumulator update, once, guarded on a live un-cracked maw):
- set `colony.maw.alive = False` and `colony.mad = True` (the flag rides the
  dead colony object — `pending_respawns` is a bare `Dict[int,int]` with no
  payload, so the flag-on-the-object is the ONLY channel that survives from
  death to respawn; no signature changes),
- log a max-salience beat: `"House {name} goes mad and dies raving"`.

In `_check_maw_deaths` (madness branch, at the epithet step 6284–6290):
- OVERRIDE the epithet — `self._house_epithets()[house] = "the Mad"` (do NOT
  call `derive_epithet` for a mad death; the disgrace is FIXED, not judged),
- emit the disgrace line: `"House {house} will be remembered as the Mad"`
  (retains the "will be remembered" salience-8 row that D2 already scores),
- run the SURVIVOR WARNING loop (MAD-3), then fall through to the UNCHANGED
  `pending_respawns[...] = step + RESPAWN_DELAY` scheduling (liveness spine).

In `_respawn_colony` (THE FORK, at index resolution 6360 → before overwrite at
6422): read the still-resident `old = self.colonies[index]` and if
`getattr(old, 'mad', False)` is True, FORCE the fresh-house outcome regardless
of survivors — `colony.house = make_house_name()`, `colony.generation = 1`,
genome from a survivor-mutate if any else a fresh `ColonyGenome` — instead of
`parent.house` / `parent.generation + 1`. The dead disgraced name stays in
`house_epithets` permanently as the gravestone (names are never pooled/reused).

**Acceptance MAD-2.**
- Force `colony.madness` past threshold (or directly set `colony.mad = True`
  and `colony.maw.alive = False`), run `_check_maw_deaths` →
  `sim._house_epithets()[house] == "the Mad"`, and a max-salience
  "goes mad"/"remembered as the Mad" row is logged.
- Then `_respawn_colony(cid)` → the new house's BASE name is NOT the dead
  house's base AND `generation == 1` (fresh, extinct bloodline).
- Contrast (regression guard): a NORMAL non-mad fall still respawns as a cadet
  of a survivor — `generation >= 2` — so `test_dynasties` stays green.

## MAD-3 — Survivor warning (keeper-directed wariness)

The keeper (not a rival) rotted the mad house, so survivors turn WARY of the
KEEPER, not into a political grudge. In the madness branch of
`_check_maw_deaths`, loop the LIVING survivors (mirror the hegemon-quarrel loop
6274–6281 / the `_betray` observer template 5376–5399) and nudge each:
- `keeper_sentiment -= MADNESS_WARNING` (clamped [0,1]),
- a dread spike via `self._disposition_wrath(survivor, 0.0, MADNESS_WARNING)`
  (agitation up, favoritism untouched — pass `dfav=0.0`).

**Acceptance MAD-3.** After a madness death, each living survivor's
`keeper_sentiment` is lower than before by `MADNESS_WARNING` (and/or
`agitation` higher), for every survivor.

## MAD-4 — Liveness preserved (T5/T6)

The madness death still schedules `pending_respawns` and refills the slot.
**Acceptance MAD-4.** After a madness death + `_process_respawns`:
- `cid in [c.colony_id for c in sim.colonies]` (slot present),
- the colony at that slot `is_alive()` is True,
- `len(sim.colonies)` is unchanged from before the death.
The extinction does NOT empty the board.

## MAD-5 — Conflict vector (DEFERRED trigger; documented counterpart)

**Decision (chosen — do not re-open): DEFER the new decisive-extinction
trigger; document + assert the existing conflict-respawn as the honorable
counterpart.**

Root cause of the defer: there is NO clean, readily-available, correctly-scoped
signal for "decisive conflict extinction" AT the death/respawn site. The two
candidate signals both fail the minimality/identity test:
- **ANNIHILATE bargain mode** (`BARGAIN_MODE_ANNIHILATE`, sandkings.py:386;
  read via `_bargain_mode_ids(a_id, b_id)`): requires the KILLER's id, which
  `_check_maw_deaths` does not track. Threading a killer-id (and its bargain
  mode) into the death site is a behavioral change of larger scope than this
  arc — hand to `opus_architect` if wanted later.
- **"no surviving colony shares this dead house's base name"**: readily
  available in `_respawn_colony`, but respawn already picks a RANDOM survivor
  as the cadet parent, so this predicate is true for nearly EVERY death →
  using it as the extinction trigger would make almost all conflict deaths
  extinctions and BREAK the D1 cadet-continuation (`test_dynasties`).

What ships for MAD-5 instead:
- DOCUMENT that a conflict fall keeps the EXISTING behavior — cadet-continuation
  of a survivor (`generation >= 2`, D1) with the earned `derive_epithet` epithet
  (D2) — as the honorable counterpart to the shameful madness death.
- ASSERT that the fresh-house conflict paths that ALREADY exist (the CS hybrid
  path 6365–6371, the no-survivor path 6335) mint their epithet via
  `derive_epithet` (earned, non-shameful) — this is already true; the test
  pins it so a future change cannot silently make a conflict death shameful.

**Acceptance MAD-5 (deferred-doc variant).** A non-mad (conflict) fall:
`sim._house_epithets()[house]` equals `derive_epithet(...)` for that reign
(NOT "the Mad"), and the respawn is a cadet (`generation >= 2`) when a survivor
exists. Assert `colony.mad` is falsy on that path. A one-line note records the
ANNIHILATE-triggered decisive extinction as BACKLOG (needs killer-id threading).

## MAD-6 — Rarity / identity / re-baseline

**Acceptance MAD-6.** At the shipped defaults, a colony under NORMAL treatment
does NOT go mad over a long run (madness is uncommon): run a seeded sim for a
long horizon with default/kind keeper treatment → no colony reaches
`MADNESS_THRESHOLD`, and the full existing battery stays green (no seeded suite
spuriously loses a house to madness). Any test that DOES change baseline under
the non-zero `MADNESS_RISE` default is flagged for re-baseline in the
reconciliation log (see Determinism note).

---

## Structural

New per-colony STATE (in `Colony.__init__`, beside the DP fields at
sandkings.py:1159–1164; getattr-guarded everywhere for old checkpoints, both
pickle automatically with the sim):
```
self.madness = 0.0    # MAD-1 sustained-neglect accumulator 0..1 (0 = sane)
self.mad     = False  # MAD-2 crack flag; rides the dead object to the fork
```

Methods TOUCHED (no new methods, no signature changes):
- `_disposition_tick(self)` — sandkings.py:2519 — accumulate `madness`; crack
  trigger (set `maw.alive=False`, `mad=True`, log) at threshold.
- `_check_maw_deaths(self)` — sandkings.py:6196 — madness branch at the epithet
  step: "the Mad" override, disgrace line, survivor-warning loop.
- `_respawn_colony(self, colony_id)` — sandkings.py:6304 — read `old` before
  overwrite; `mad` → force fresh-house identity.

Data TOUCHED in chronicle.py:
- `SALIENCE` (28–99) — add `("goes mad", 10)`.
- `EPITHET_RULES` (105–120) — add a shameful row for robustness (see Constants).

Nothing else changes. `apply_respawn_shadow` (politics.py:134), the corpse
feast, thrall conversion, ore spill, `pending_respawns`, and `_process_respawns`
are all UNTOUCHED.

---

## Constants + Provenance

All new constants live beside the Disposition block (sandkings.py:263–288).
Tag `[prov:C feel=madness-pacing]` = chosen by the spec author for pacing;
tune against the MAD-6 rarity gate.

| Constant | Default | Meaning / provenance |
|---|---|---|
| `MADNESS_AGIT_MIN` | `0.5` | agitation gate for "raving" (matches `AGIT_FREEZE=0.5`, the existing "high agitation" line). [prov:C] |
| `MADNESS_RISE` | `0.01` | ratchet step while raving: `madness += RISE*(1-madness)`. SMALL — reaching a `0.6` threshold needs ~90 sustained raving steps → RARE. `0.0` = identity (madness off). [prov:C feel=madness-pacing] |
| `MADNESS_DECAY` | `0.95` | multiplicative retention while NOT raving (half-life ~13 steps) — kind treatment recovers a near-crack. [prov:C] |
| `MADNESS_THRESHOLD` | `0.6` | crack point: `madness >= THRESHOLD` → the maw dies raving. [prov:C] |
| `MADNESS_WARNING` | `0.05` | survivor keeper_sentiment decrement + agitation dread spike after a madness death. [prov:C] |
| `"the Mad"` | literal | the fixed shameful epithet (NOT from `derive_epithet`). |

**Identity / off default (state the trade-off explicitly).** `MADNESS_RISE=0.0`
reproduces today exactly (madness never accumulates, no colony ever cracks, no
new behavior, byte-identical RNG since the accumulator is pure). The SHIPPED
default `MADNESS_RISE=0.01` is a **live behavior change**: a colony kept both
highly agitated AND keeper-hated for a sustained stretch now dies of madness.
Because it is non-zero, the MAD-6 rarity battery MUST be re-checked and any
seeded suite that now loses a house to madness re-baselined. Recommended:
ship `0.01` (madness CAN happen, but rarely) over `0.0` (never), because
"a house that can never break" is the poorer story; the rarity is enforced by
the RISE×THRESHOLD×AND-gate product, tuned to MAD-6.

---

## Behavioral — rote pseudocode

### B1. `_disposition_tick` — accumulator + crack (append inside the per-colony loop, after the agitation-decay line at 2534)

```
# --- MADNESS (MAD-1/MAD-2): sustained-neglect accumulator, pure, no RNG ---
mad_now = getattr(colony, 'madness', 0.0)
hated   = (getattr(colony, 'keeper_sentiment', 0.5) < 0.33
           or getattr(colony, '_sentiment_wrath', False))
raving  = (getattr(colony, 'agitation', 0.0) >= MADNESS_AGIT_MIN) and hated
if raving:
    mad_now = mad_now + MADNESS_RISE * (1.0 - mad_now)   # asymptotic ratchet
else:
    mad_now = mad_now * MADNESS_DECAY                    # decay toward 0
colony.madness = float(np.clip(mad_now, 0.0, 1.0))
# crack once: a live, un-cracked maw that reaches the threshold dies raving.
if (colony.madness >= MADNESS_THRESHOLD
        and colony.maw.alive
        and not getattr(colony, 'mad', False)):
    colony.mad = True
    colony.maw.alive = False        # picked up by _check_maw_deaths THIS step
    self._log_event(f"House {self._house_name(colony)} goes mad and dies raving")
```
Note: `_disposition_tick` runs at step section 4a (line 1827), BEFORE
`_check_maw_deaths` at line 2042 — the cascade fires the SAME step.

### B2. `_check_maw_deaths` — shameful override + survivor warning (replace the epithet block at 6284–6290)

```
from chronicle import derive_epithet
house = self._house_name(colony)
if getattr(colony, 'mad', False):
    # MAD-2: disgrace is FIXED, not judged — do NOT call derive_epithet.
    self._house_epithets()[house] = "the Mad"
    self._log_event(f"House {house} will be remembered as the Mad")
    # MAD-3: survivors turn WARY OF THE KEEPER (not a grudge — the keeper rotted them)
    for other in self.colonies:
        if other is colony or not other.is_alive():
            continue
        other.keeper_sentiment = float(np.clip(
            getattr(other, 'keeper_sentiment', 0.5) - MADNESS_WARNING, 0.0, 1.0))
        self._disposition_wrath(other, 0.0, MADNESS_WARNING)  # dread spike only
else:
    # UNCHANGED conflict/normal path (D2): earned epithet
    epithet = derive_epithet(self._chronicle(), house,
                             getattr(colony, 'founded_step', 0))
    self._house_epithets()[house] = epithet
    self._log_event(f"House {house} will be remembered as {epithet}")
# ... fall through UNCHANGED to pending_respawns[...] = step + RESPAWN_DELAY ...
```

### B3. `_respawn_colony` — the identity fork (at index resolution 6360, before overwrite 6422)

```
index = next(i for i, c in enumerate(self.colonies) if c.colony_id == colony_id)
old   = self.colonies[index]                 # still the DEAD object (pre-overwrite)
extinct = getattr(old, 'mad', False)         # MAD-2 fork signal (Vector-2 deferred)
colony = Colony(colony_id, pos, genome)
colony.maw.food_stored = RESPAWN_FOOD
if extinct:
    # EXTINCTION: a fresh unrelated house takes the slot; bloodline ends.
    from chronicle import make_house_name
    colony.house = make_house_name()
    colony.generation = 1
    # genome already came from a survivor-mutate (or fresh ColonyGenome) above;
    # do NOT copy parent.house / breached / techs — this is NOT a cadet.
    colony.founded_step = self.step_count
elif crossed is not None:
    ... UNCHANGED CS hybrid path (make_house_name, generation=1, inherit both) ...
elif survivors:
    ... UNCHANGED cadet path (parent.house, generation+1, inherit) ...
# (no-survivor fresh path at 6335 also UNCHANGED)
colony.founded_step = self.step_count
self.colonies[index] = colony                # slot refilled — liveness intact
```
`old` is discarded after the overwrite, so its `mad` flag naturally dies with
it. `apply_respawn_shadow(colony_id)` and all downstream steps run UNCHANGED.

### B4. chronicle.py data rows

```
# SALIENCE (28–99): add near the other salience-10 lines
("goes mad", 10),

# EPITHET_RULES (105–120): a shameful row for robustness (the live override in
# _check_maw_deaths is authoritative; this makes derive_epithet safe if a
# "goes mad" row ever reaches it). Precedence: place ABOVE "betrays".
("goes mad", "the Mad", 6),
```

---

## Determinism / re-baseline note (flag)

- The accumulator and crack trigger consume NO RNG (pure clip/compare), so at
  `MADNESS_RISE=0.0` the RNG stream is byte-identical to today.
- At the shipped `MADNESS_RISE=0.01`, madness CAN fire: a colony that cracks
  dies one step earlier than it otherwise would and respawns as a fresh house,
  which perturbs the RNG stream from that point. **MAD-6 must confirm no seeded
  suite loses a house to madness under normal treatment**; flag and re-baseline
  any that does. The DP-arc "zero-RNG at neutral" invariant is preserved (the
  new code draws no RNG at any madness value).

## Compatibility

Same contract as every round: `getattr`-guarded reads for old checkpoints
(`madness`/`mad` default to `0.0`/`False`), all new state pickles with the sim,
`EnhancedSandKingsSimulation` stays inert, no signature changes anywhere.

## Status / Reconciliation Log

- Drafted 2026-07-11. Vector 1 (madness) fully specified; Vector 2 (conflict
  extinction) DEFERRED to backlog — see MAD-5 root cause (no clean killer-id
  signal at the death site without a scope-expanding thread; hand to
  `opus_architect` if pursued). MAD-1…MAD-6 acceptance in
  `tests/test_madness.py` (new), mirroring `tests/test_disposition.py`
  agitation-drive and `tests/test_dynasties.py:72–93` death/epithet/respawn
  idioms.
