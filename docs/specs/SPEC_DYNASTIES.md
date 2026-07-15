# SPEC: Dynasties & Chronicle (Round 5) — D1–D12

Governing intent (user, verbatim): "Game of Thrones but with sandkings —
no humans; the creatures and technology crashes are the only outside
influences; the maws are sentient creatures. [Quasi] sentient life
operating inside my computer within the terrarium."

Gap analysis: the sim has politics (P1–P15), economy (T16–T27), machines
(T28–T40), and monsters (T41–T48) — but no IDENTITY (maws are numbers),
no NARRATIVE MEMORY (events scroll off a deque), and no INTERIORITY at
the colony level (thoughts are per-unit). GoT = named houses + carried
grudges + a history someone wrote down. This round adds exactly those
three organs and nothing else.

## D1 — Names and Houses
Every maw gets a generated name (syllable grammar, deterministic from a
per-lineage rng) and every lineage a house name + epithet ("House
Vex-Karn, the Oath-Broken"). Names are STATE (pickled), not derived.
Respawn lineage (mutated survivor genome, existing red-queen mechanic)
inherits the house; a truly fresh genome founds a new house. The
HUD/manager/events say "Vex-Karn" where they now say "Colony 2".

## D2 — Epithets are earned, not rolled
A house's epithet re-derives from its chronicle at succession: the
dominant weighted deed class of the dead maw's reign. Full set (per
chronicle.py EPITHET_RULES, weight in parentheses): the Oath-Broken
(betrayal, 5), the Machine-Waker (4), the Beast-Slayer (3), the Burned
(3), the Wall-Breaker (3), the Oath-Keeper (truces, 2), the Open-Handed
(tribute, 2), the Farmer-King (2), the Delver (ore strikes, 2), the
Stone-Hearted (palisades, 2), the Warlord (war declarations/sieges, 1),
and the Founder (a reign with no notable deeds). Epithet judgments are
themselves chronicle events ("will be remembered as").

## D3 — Blood grudges (amends P12)
A betrayal by a house is remembered against the HOUSE
(`sim.house_grudges`, keyed by house names), never decaying — blood
remembers what trust forgets. An outstanding grudge adds +0.3 to P5
target scoring, and selecting the grudged house fires "The blood feud
between House X and House Y flares again!" (throttled). The P12 trust
shadow multiplier (0.25x) is unchanged — the drafted 0.5x within-house
scaling was rejected as double-counting once eternal grudges shipped
(see reconciliation).

## D4 — The Chronicle
A new `chronicle.py`: an append-only saga log that pickles with the
sim (so it survives --persist restarts; the drafted sqlite table was
unnecessary). Appending past 900 rows triggers a prune down to
ROW_CAP 800, dropping lowest-salience oldest rows first; rows at
salience >= PRUNE_KEEP_SALIENCE (7) are never pruned. Every
`_log_event` gains a salience score (constants table: maw deaths 10,
betrayals 9, machine claims 8, speciation 8, war declarations 7,
incursions 5 ... keeper feedings 1). The chronicle is the long-term
memory the events deque never was.

## D5 — The Saga screen (R30)
New viewer key (H): renders the chronicle as readable history — reign
by reign, "In the 3rd year of Vex-Karn the Oath-Broken: the frost took
the fields; the ram broke House Mirel's walls; the ancient machine
fell silent." Generated from chronicle rows by a template grammar
(deterministic, no LLM). This is the "make it POP" surface: the
terrarium can tell you its own story.

## D6 — Colony self-model (M13)
The thought layer gains colony-level anchors evaluated on the COLONY
context, not per-unit: "pride" (house epithet is positive + hegemon or
oasis holder), "vengeance" (active blood grudge), "legacy" (maw HP low
+ house is >= 3 generations old). Colony mood line on the manager
screen quotes them: "House Vex-Karn broods on vengeance."

## D7 — Succession drama
Maw death while units survive: the colony fights on leaderless for
RESPAWN_DELAY (existing), but now those units carry the "vengeance"
context bonus (+aggression bias vs the killer house) — last stands of
a fallen house are dramatic by construction.

## D8–D11 (backlog and shipped extras)
D8 house relics (an heirloom item — the ancient controller already
behaves like one — formally owned by a house, its loss/capture
chronicled) and D10 chronicle-driven epithet vocabulary via the GloVe
pipeline remain BACKLOG. D9 (oaths) was closed by reconciliation:
betrayal already requires an active truce (P6), so every betrayal is
oathbreaking and its price includes the eternal D3 grudge. D11 (saga
export) SHIPPED: E on the saga screen writes the full chronicle to
terrarium_saga.txt with a houses-as-history-judged-them preface (R30).

## D12 — Acceptance (executed)
tests/test_dynasties.py (8 tests): founding houses named and labeled;
chronicle capture with write-time house substitution and salience;
prune keeps high-salience rows; epithets judged per-reign with weighted
precedence; succession earns the epithet and respawn inherits as a
cadet branch; kin never targeted and the blood feud flares once; the
saga builder reads history in houses; dynasty state pickles and
pre-dynasty checkpoints lazily re-found houses. Soak: a 5-harsh-year
run must yield a readable saga with earned epithets and a
generation >= 2 cadet house (PASSED — see reconciliation).

## Compatibility
Same contract as every round: lazy accessors + getattr guards for old
checkpoints; EnhancedSandKingsSimulation stays inert; chronicle sqlite
lives beside the --persist checkpoint db; all new state pickles.

## Status / Reconciliation Log
- Drafted 2026-07-08 immediately after Round 4 (commit 2b50ec9).
- 2026-07-08 (same day): D1–D7 IMPLEMENTED. Deltas, all deliberate:
  - D1: names live in `chronicle.py` (syllable grammar); houses found
    lazily via `sim._house_name()` so pre-dynasty checkpoints earn
    names on first use. Respawn = CADET BRANCH of the genome parent
    (same house, generation+1, roman-numeral label) - the respawn
    already inherits a survivor's mutated genome, so the house follows
    the blood. KIN AMENDMENT: same-house colonies are never hostile()
    (single-gate change in politics.py) and never targeted (P5 filter).
  - D2: epithets are weighted deed scores (betrayal 5 > machine 4 >
    beast/fire/wall 3 > truce/tribute/harvest/delve/palisade 2 >
    warlord 1) so one betrayal brands harder than two harvests;
    judged at death, scoped to the reign via founded_step.
  - D3: delivered as `sim.house_grudges` (victim_house, traitor_house)
    -> step, set at betrayal, NEVER decaying, +0.3 target-score feud
    bonus and a throttled "blood feud flares" event. The P12 trust
    shadow multiplier was left untouched (simpler, same drama).
  - D4: the chronicle is a plain pickled list on the sim (whole-sim
    pickling already persists across --persist restarts; the spec's
    sqlite table was unnecessary). Rows are house-substituted AT WRITE
    TIME so history stays attributed after slots change hands, and
    deduplicated within a season (war-declaration flapping is one
    fact, not eleven rows). Salience prune at 900 -> ROW_CAP 800,
    rows >= salience 7 never pruned.
  - D5: H key toggles the saga screen (build_saga_entries: year/season
    framing over saga_rows(min_salience=4)); HUD events and the
    colony roster also speak in houses; manager header is
    "== HOUSE Vex-Karn II, the Oath-Broken (Colony 2) ==".
  - D6: pride/vengeance/legacy are colony-level DIRECT predicates on
    the manager screen ("House X broods on vengeance"), not GRU
    probes - they are colony facts, not hidden-state decodes; the
    35-anchor probe lexicon is unchanged.
  - D7: delivered as the D3 feud bonus. The spec'd leaderless last
    stand conflicts with T5 (maw death = immediate corpse feast);
    T5 wins - recorded as a rejected sub-feature.
  - D9 CLOSED BY RECONCILIATION: betrayal is only possible under an
    active truce (P6), so every betrayal is already oathbreaking; its
    price is the -60/-20 trust hit, the grudge lock, AND the eternal
    D3 house grudge. A separate oath object would double-count.
  - D11 SHIPPED: E key on the saga screen exports the full chronicle
    (all salience) to terrarium_saga.txt via chronicle.write_saga(),
    with the houses-as-history-judged-them preface.
  - D8 (relic ownership formalization) and D10 (epithet vocabulary
    via GloVe) remain backlog. D12 soak: PASSED - 5 harsh years, 23.8 sps, 423
    chronicle rows, 3 epithets earned, a generation-2 cadet house,
    saga readable (truces, tributes, coalitions, the ancient machine
    passing between houses). All 9 test suites green incl. new
    tests/test_dynasties.py (8 tests).
