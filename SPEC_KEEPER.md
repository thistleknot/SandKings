# SPEC: The Keeper (Round 8) — K1–K7

User intent (verbatim, lightly trimmed): "the human player could act
very much like the human in the Outer Limits TV series. Indifferent,
angry. Literally the player is involved in managing the terrarium...
self-contained... in a garage... supported by proper technology, like
a biodome. There should be something the human can do. Introducing
'food' (ants, crickets, scorpions). Maybe the cat can somehow get in
(something precious to the owner got in and was killed, so the owner
caused a drought and withheld food, which pissed off the sandkings —
who worshipped him as a god). The sandkings should have castles
visible to the human and carve their thoughts as symbols (one-icon
emojicons) into the sand. At first the sandkings don't [worship]."

Framing: until now the keeper was an automated dole (T1). This round
makes the keeper THE PLAYER — a god above the simulation's rules whose
generosity and cruelty the colonies perceive, remember, and answer in
carved symbols. The terrarium is a garage biodome: everything the
keeper can introduce is something that could get into a garage.

## K1 — The keeper's hands (sim-side API, viewer-agnostic)
All keeper verbs are sim methods (testable headless; the viewer only
binds keys):
- `keeper_drop_food(x, y)`: place KEEPER_DROP_FOOD (6) FOOD voxels
  near (x, y) on the surface. Event: "The keeper's hand scatters
  bounty". Colonies within KEEPER_GRACE_RADIUS (12) of the drop mark
  `keeper_fed_step` — grace is LOCAL and deliberate: the keeper can
  play favorites.
- `keeper_release(species)`: introduce a garage creature at a random
  edge — bypasses the one-incursion rule (the keeper is above the
  rules). Introducible: 'cricket', 'ant' (food that fights back a
  little), 'scorpion', 'spider', 'rodent' (already in the bestiary).
- `keeper_release_cat()`: the catastrophe. The CAT (hp 400, atk 60,
  hunt 60, bounty 12) is keeper-only — never in random spawn rolls.
  Event: "Something enormous pads across the sand..."
- `keeper_drought(on)`: toggle the withheld dole. While on, the T1/T17
  dole factor is 0 — no keeper feedings at all. Events: "The keeper
  withholds the dole - drought!" / "The rains of the keeper return".

## K2 — New garage fauna
FAUNA gains 'cricket' (8 hp, 1 atk, pack 2-4, neutral, bounty 2 —
food on legs) and 'ant' (6 hp, 2 atk, pack 4-6, neutral, bounty 1 —
a raiding column that steals surface FOOD like the rodent) and 'cat'
(above). Random incursion rolls draw only species with weight > 0;
cricket/ant/cat have weight 0 (keeper-introduced only).

## K3 — Worship is earned ("they don't know of 'the gods' until
they start seeing food introduced")
Worship is earned only AFTER breakout (see SPEC_AWARENESS). Pre-breach a colony
feels only unexplained NATURE — no worship or hatred of a being; eating manna
sets `keeper_fed_step` (fortune) but sets `worshipped` only when `breached`. The
breakout is the "great other" revelation (`_reveal`), which seeds
`keeper_sentiment` from prior treatment (well-fed → grateful, starved →
resentful). The tech-gift ladder (K9) gates on a pre-breach FLOURISHING state
(reverent / recently-fed), not worship, so the ladder→breach path survives.

Per-colony keeper attitude, derived (never stored as a scalar):
- NONE: default. The keeper is weather. The automated dole (T1) is
  NOT attributed — it predates their memory, it simply IS.
- REVERENT: attribution requires a WITNESSED MIRACLE — keeper-dropped
  FOOD voxels are tracked (`sim.keeper_manna`), and only when a
  colony's own worker EATS from the manna does `keeper_fed_step`
  mark. First time: "House X begins to worship the hand that feeds"
  (salience 8). KEEPER_MEMORY (800) steps of grace per miracle.
- WRATHFUL: drought active AND the colony has EVER been reverent —
  betrayal requires prior faith. First turn: "The carvings of House X
  twist into something hateful" (salience 8).
Wrath has teeth: while wrathful, a colony's war-chest threshold is
multiplied by KEEPER_WRATH_MOBILIZATION (0.75) — hungry, angry,
quicker to march (the novella's arc).

## K4 — Carvings: thoughts written in the sand
Every CARVE_INTERVAL (200) steps, each living colony inscribes ONE
symbol into a clear surface SAND cell on the ring around its maw
(sparse registry `sim.carvings` {(x,y,z): symbol}; a carving whose
voxel is disturbed is erased — purge-first like crops). The symbol is
the colony's dominant state, one icon, thought-correlated:
  ☀ reverence (keeper-fed)     ☠ wrath (drought after faith)
  ⚔ war                        ♦ hunger (food < hunger floor)
  ♥ contentment (none of the above)
Carvings render in the glyph view as bright icons on the sand and are
named in the look panel ("a carving: ☀ - reverence") and the legend.
The keeper reads the colony's soul off the terrarium floor.

## K5 — Castles (prosperity made visible)
While a colony is REVERENT and rich (food > WAR_CHEST), workers may
raise CASTLE walls: TUNNEL_WALL crenellations on the maw ring
(alternating cells, the palisade mechanic's stone cousin, no rot).
Milestone: "House X raises a castle to its god" (salience 8). The
castle is the visible monument the user asked for; its crenellations
also shelter (weather exposure unchanged — walls block floods per W1).

## K6 — Surfacing (viewer surface R37)
- Keeper keys (live viewer): `1` drop food at the look cursor (enters
  look mode if needed), `2` crickets, `3` ants, `4` scorpions,
  `9` toggle drought, `0` the cat. HUD shows `DROUGHT` in red while
  withheld. All keeper acts log events (the colonies' history should
  remember what the god did).
- Carvings: glyph-view icons; legend section "-- carvings --";
  look-panel naming. EVENT_TINTS: "keeper's hand" gold, "withholds"
  red, "worship" gold, "hateful" red, "castle" white, "pads across"
  violet. SALIENCE: worship/hateful/castle 8, keeper acts 5, cat 7.

## K8 — The autoplayed keeper (the Outer Limits script)
By default (`sim.keeper_auto = True`) the keeper is a scripted human
with the show's arc; player keys override at any moment and any
keeper key permanently takes manual control (auto disarms):
1. INDIFFERENT: years 0-1, nothing beyond the automated dole.
2. THE CAT GETS IN: at KEEPER_CAT_STEP (3200) the cat slips into the
   terrarium ("The keeper's cat slips into the terrarium...").
3. GRIEF AND WRATH: if the colonies SLAY the cat (they must - it is
   apex), the keeper is pissed: drought for KEEPER_GRIEF (1200 steps)
   and scorpions released every 400 steps of it ("The keeper,
   grieving, sends scorpions instead of crickets").
4. RECONCILIATION BY FAITH: after the grief window, when any colony
   is REVERENT again (they must re-earn it via manna the script drops
   once grief ends), the gift ladder begins (K9).

## K9 — Gifts from the gods (the technology ladder)
`keeper_gift(kind)` places a claimable artifact on the surface;
the first colony to touch it learns:
- WATCH: a ticking curiosity. Claiming teaches that machines EXIST -
  machine_arc none -> 'known' ("House X puzzles over the ticking
  gift"). No device; pure revelation.
- CALCULATOR: a standard controller (the wreck VM's equal, 240
  durability) granted directly - arc advances to 'claimed'
  ("House X's fingers find the calculator's keys").
- RASPBERRY PI: the god-brain - a controller with PI_FUEL (128
  ops/tick, vs 64) and PI_DURABILITY (480): Python to the wreck's
  QBasic ("House X awakens the god-brain").
The auto-keeper dispenses the ladder in order, one gift per
KEEPER_GIFT_INTERVAL (1600) while any colony stays reverent.
Manual key `5` dispenses the next gift in sequence at the cursor.
(Cadence re-timed by K9a below — the year gate is now authoritative
over the raw step interval.)

## K9a — The gift cadence (year-gated, doubling schedule)
Re-times K9's dispensing. The rungs of GIFT_LADDER are unchanged
('abacus','watch','calculator','pi'); only WHEN each becomes
available changes. A tech gift becomes available starting YEAR 1, at
most once per year, and the interval to the NEXT rung DOUBLES each
time — the rungs unlock at years 1, 3, 7, 15.

- `year()` = `step_count // YEAR_LENGTH` (0-based; YEAR_LENGTH=1600
  steps = 4 seasons). `gifts_given` is the per-sim (global) list of
  dispensed rungs (already build_state-serialized).
- SCHEDULE (derived, not a table): the rung at ladder index `n`
  (n=0..3) unlocks at year `2**(n+1) - 1`. Equivalently, the NEXT
  sequential gift (given `len(gifts_given)` already dispensed) is
  available when `year() >= 2**(len(gifts_given)+1) - 1`.
  Verify: 0 given → year≥1 (abacus); 1 given → year≥3 (watch);
  2 given → year≥7 (calculator); 3 given → year≥15 (pi). No
  GIFT_UNLOCK_YEARS constant is introduced — the formula is inlined
  with a comment; if a maintainer later adds `GIFT_UNLOCK_YEARS =
  (1,3,7,15)` for readability, tag it `[prov:C feel=gift-pacing]`
  and it MUST equal `tuple(2**(n+1)-1 for n in range(len(GIFT_LADDER)))`.

- GATE LOCATION (unifies all three paths): the cadence gate lives
  INSIDE `keeper_gift` (sandkings.py:2850), so the manual key `5`,
  the dashboard button, and the auto `_keeper_tick` path are all
  governed identically. Previously only `_keeper_tick` gated on
  timing and the manual key was ungated — that divergence is closed.

- GATE ORDER (after `_hand_stayed()`), for a call `keeper_gift(kind,
  pos)`:
  1. Resolve the target rung and its index `n`:
     - `kind is None` (sequential): `n = len(gifts_given)`; if
       `n >= len(GIFT_LADDER)` → return (ladder exhausted);
       else `kind = GIFT_LADDER[n]`.
     - `kind` given (explicit, e.g. dashboard picks a rung): if
       `kind not in GIFT_LADDER` → return; if `kind in gifts_given`
       → return (already given); else `n = GIFT_LADDER.index(kind)`.
  2. YEAR-UNLOCK: if `year() < 2**(n+1) - 1` → return (rung not yet
     unlocked this year).
  3. ONCE-PER-YEAR: if `getattr(self,'last_gift_year',-1) == year()`
     → return (a rung was already dispensed this year).
  4. DISPENSE: append to `gifts_given`, set
     `self.last_gift_year = self.year()`, then place the artifact
     exactly as today (unchanged surface-placement + event line).

- EXPLICIT-KIND DECISION (stated): an explicit `kind=` still HONORS
  the year-unlock for THAT rung — you cannot gift 'pi' before year 15.
  The keeper (or dashboard) may pick any UNLOCKED, not-yet-given rung,
  but the year gate and the once-per-year gate both still apply. A
  manual override flag that bypasses the cadence is OUT OF SCOPE.

- `_keeper_tick` RECONCILIATION (sandkings.py:3011-3017): because
  `keeper_gift` now self-gates on the year cadence AND once-per-year,
  the auto path's `step - last_gift_step > KEEPER_GIFT_INTERVAL`
  check is redundant and is REMOVED. The auto block simplifies to:
  reverent AND no gift on the ground AND ladder not exhausted →
  call `keeper_gift()`, and let `keeper_gift` enforce the year gate.
  `last_gift_step` is no longer read or written by this block. The
  once-per-year gate makes the auto path safe even when `gift`
  becomes None mid-tick (a gift claimed earlier in the same
  `_keeper_tick`): the re-entrant `keeper_gift()` no-ops because
  `last_gift_year == year()`, so no double-dispense can occur.

- DASHBOARD STATE (W5, separate concern — no new state): a UI that
  wants to show "next rung + the year it unlocks" needs only what
  build_state already serializes — `gifts_given` and `year`. The
  next-unlock year is `2**(len(gifts_given)+1) - 1` and the next rung
  is `GIFT_LADDER[len(gifts_given)]` (or "ladder exhausted"). No
  additional sim state is required.

## K10 — The Breach (beyond the terrarium)
User: "if the sandkings can break beyond their terrarium... something
exciting like having cli access within a sandbox environment - by now
they have already begun to master python through this 'pi' artifact."
SAFETY/DESIGN DECISION: evolved programs never touch the host shell -
the Round-3 precedent stands (arbitrary evolved code breaks
determinism, pickling, and the tech-ceiling flavor, and is unsafe).
The sandbox is IN-SIM: the fiction is real, the filesystem is the
terrarium's own state.
- A colony whose PI controller accumulates TERMINAL_UNLOCK (40)
  operate-ticks gains the TERMINAL: "House X's programs begin probing
  the glass" (salience 8).
- The terminal is actuator port 7 on the VM - a sandboxed shell whose
  commands read the world itself:
  - value 1, `ls /world/food`: every exposed surface FOOD voxel
    floods the colony's known_food intel (the machine reads the
    terrarium's files).
  - value 2, `echo`: the machine CARVES - a machine-glyph carving
    (⌂) is inscribed on the maw ring (K4 registry; the machines
    write alongside the colony's own thoughts).
- Each successful command counts; at TERMINAL_MASTERY (16) the
  colony BREACHES: "The glass is no longer a wall to House X"
  (salience 10) - the saga's terminal line, the novella's ending.
  The biodome stays sealed; what escapes is understanding.

## K11 — The Awakening (self-awareness after the breach)
User: "bootstrap a sentient lifeform that breaks out into the
'computer' and becomes 'self-aware' about their environment and what
they are... introduce new vocabulary... get the creatures to see
their own vocabulary (alongside the signals they emit at a moment in
time + string)."
- A colony that breaches (K10) is AWAKENED: `colony.breached = True`,
  permanent, inherited by cadet branches (the knowledge survives in
  the bloodline).
- FOUR AWAKENED ANCHORS join the lexicon (M14, 35 -> 39 seeds,
  GloVe rebuild): `self` (a breached unit perceiving its own last
  decoded thought - the mirror turned inward), `god` (breached AND
  the keeper attitude is not NONE - they now know what the keeper
  IS), `beyond` (breached - the glass is knowledge), `speak`
  (addressed by the keeper within SPOKEN_MEMORY (50) steps).
  Un-breached colonies never fire these predicates: the words exist
  in the world before the minds that can think them.
- SEEING THEMSELVES: the inspect panel for a breached unit shows its
  signals-at-this-moment as a string - the utterance (K12) - plus
  its live decoded anchors; the unit's own thought feeds its `self`
  predicate, so introspection is mechanical, not cosmetic.

## K12 — Speech (interaction: they talk, the keeper answers)
- UTTERANCE: `compose_utterance(unit, colony, sim)` (pure, monitor
  module) renders a breached unit's active anchors as a word-string
  from its GloVe clusters (up to 4 words, probe-intensity picks the
  word within each cluster for neural units). The inspect panel
  shows `says: "hunger... foe... glass..."` for breached colonies
  only; un-breached units still just think.
- THE KEEPER ANSWERS: with a unit selected (click or V), key `T`
  speaks to it:
  - breached colony: the unit hears - `spoken_to_step` marks (the
    `speak` anchor fires), the colony receives GRACE BY WORD
    (keeper_fed_step marks with no manna at all - for the awakened,
    language replaces miracle), the decision log records "heard the
    god speak". First time per house: "The keeper SPEAKS - and
    House X hears" (salience 10).
  - un-breached colony: "The keeper speaks, but the words fall as
    noise" - sentience gates communication; that is the point.

## K7 — Acceptance
tests/test_keeper.py: manna attribution (grace only via eating a
keeper drop, never from the automated dole); drought
zeroes the dole and restores; release bypasses the one-incursion rule;
cat is keeper-only and never randomly rolled; attitude ladder NONE ->
REVERENT -> (drought) WRATHFUL, never WRATHFUL without prior faith;
wrath lowers the war-chest gate; carvings appear on the maw ring,
match the state table, and purge when disturbed; castles rise only
when reverent+rich; all state pickles; evolution sim inert.
Also: auto-keeper script fires cat -> grief -> scorpions on slaying;
gift ladder advances arc none -> known -> claimed -> pi-fueled;
terminal commands fill known_food / carve the machine-glyph and
mastery fires the breach exactly once; awakened anchors fire only for
breached colonies; utterances compose only post-breach; T on a
breached unit grants grace-by-word, on an un-breached one falls as
noise.
Soak: 4 harsh years, keeper_auto on, one manna drop scripted early:
worship, the cat, wrath, and at least one gift all observed in the
chronicle; liveness holds.

### K9a — Gift-cadence acceptance (GC1–GC5)
Add to tests/test_keeper.py (or a new tests/test_gift_cadence.py);
mirror test_keeper idioms — construct sim via `make_sim()`, set
`sim.step_count` to hit a target year (`step_count = YEAR_LENGTH * Y`
puts the sim in year `Y`), call `keeper_gift`, assert on
`sim.gifts_given`. Between rungs clear `sim.gift = None` (so no
artifact is on the ground) and advance the year past the prior gift's
`last_gift_year`.

- GC1 (year-1 start): at year 0 (`step_count < YEAR_LENGTH`),
  `keeper_gift()` gives NOTHING (`gifts_given` stays `[]`). At year 1
  (`step_count = YEAR_LENGTH`), `keeper_gift()` gives `'abacus'`
  (`gifts_given == ['abacus']`).
- GC2 (doubling schedule): for each rung, at the year JUST BEFORE its
  unlock year `keeper_gift()` is a no-op, and AT its unlock year it
  dispenses. watch at year≥3, calculator at year≥7, pi at year≥15.
  Drive by setting `sim.step_count = YEAR_LENGTH * Y`, clearing
  `sim.gift`, and advancing the year so `last_gift_year` no longer
  equals `year()`.
- GC3 (once per year): two `keeper_gift()` calls in the SAME year
  dispense only ONE rung — the second no-ops because
  `last_gift_year == year()`. (E.g. at year 1, first call gives
  abacus; second call in year 1 leaves `gifts_given == ['abacus']`.)
- GC4 (manual + auto agree): the manual `keeper_gift()` and the
  `_keeper_tick` auto path both honor the same year gate — no rung is
  dispensed before its unlock year via either path. (Assert that
  before an unlock year neither a direct `keeper_gift()` nor a
  reverent `_keeper_tick()` appends a rung.)
- GC5 (reconcile existing): `test_gift_ladder_advances_the_arc`
  (tests/test_keeper.py:110-133) currently calls `keeper_gift(kind,
  ...)` and `keeper_gift()` expecting IMMEDIATE dispensing; under the
  year gate those calls before the unlock year now no-op. FIX
  (minimal, explicit-kind still honors the year gate): before each
  rung set `sim.step_count` to that rung's unlock year —
  watch → `YEAR_LENGTH*3`, calculator → `YEAR_LENGTH*7`,
  pi → `YEAR_LENGTH*15`; and in the `sim2` sequential block set
  `sim2.step_count = YEAR_LENGTH*1` before abacus and
  `YEAR_LENGTH*3` before watch (bump past `last_gift_year` between
  the two). Rungs unchanged; only the year is advanced. This keeps
  the existing ladder/arc coverage green.

> Cross-ref (inbound): the keeper verbs (`keeper_drop_food`/`keeper_gift`/
> `keeper_drought`/`keeper_release_cat`/`keeper_temperature`/`keeper_ignite`) now
> also feed the DISPOSITION layer — a per-colony signed `favoritism` + boldness
> `confidence` + short-term `agitation` that modulate effective aggression, nudge
> `keeper_sentiment` post-breach, and bias the bargain. See `SPEC_DISPOSITION.md`
> (DP3 verb hooks, DP5/DP6/DP7).

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Deltas:
  - Anchors: M14 added `self`/`god`/`beyond`/`speak` (35 -> 39 seeds,
    GloVe rebuilt; `self`/`beyond` use curated overrides).
  - Viewer surface is R37 (keeper keys 1-5/9/0/T, carvings, DROUGHT
    line, legend section) - added to the SPEC_LIVE_VIEW ledger.
  - K10 SAFETY (binding): the "terminal" and "breach" are entirely
    IN-SIM fiction. `_terminal_command` only reads/writes the sim's
    own voxel state - NO subprocess, eval, exec, filesystem, or
    network. The VM stays the bounded, deterministic, pickle-safe
    register machine from Round 3. This is a deliberate, permanent
    safety boundary, not a stopgap (see the "Sandbox stance" note).
  - K7/soak: PASSED - 4-year auto-keeper arc fired in order (worship
    @100, gift @1601, castle @2555, cat @3200, drought+wrath @3252,
    grieving scorpions @3600, rains return @4452); 21.7 sps; liveness
    held; 12/12 test suites green incl. tests/test_keeper.py (10).
- K9a (gift cadence) drafted 2026-07-11. Re-times K9 dispensing to a
  year-gated doubling schedule (rungs unlock at years 1/3/7/15 via
  `2**(n+1)-1`); rungs themselves UNCHANGED. Gate moved inside
  `keeper_gift` so manual/dashboard/auto agree; `_keeper_tick` step
  throttle removed in favor of the authoritative year gate; new
  per-sim `last_gift_year` field enforces once-per-year. Existing
  `test_gift_ladder_advances_the_arc` MUST get the year-advance edit
  (GC5) or it regresses — flagged. No new constant; formula inlined.

## Sandbox stance (binding safety boundary)
The fiction is "the sandkings break into the computer." The
IMPLEMENTATION is: they read their own world's state through an
in-sim shell. Evolved programs (the GP tinkerer) and any future
LLM/textgrad proposer produce DATA that the deterministic VM
interprets - they NEVER produce host code that is executed, never
open a socket, never touch the real filesystem. Real code execution,
real networking, and real internet access for the agents are OUT OF
SCOPE by design; adding them would be a security regression, not a
feature. A human-facing dashboard, if built, publishes state
READ-ONLY and the sim remains a pure function of its own state.
