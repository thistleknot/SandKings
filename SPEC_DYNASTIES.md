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
dominant deed class of the dead maw's reign (Betrayer / Farmer-King /
Machine-Waker / Beast-Slayer / Oath-Keeper / Burned / ...). Mapping
table in the spec; epithet changes are themselves chronicle events.

## D3 — Blood grudges (amends P12)
The respawn reputation shadow becomes lineage-aware: inbound trust
memory persists at 0.5x (up from 0.25x) WITHIN a house line, and a
betrayal by a house is remembered against the HOUSE (new
`Diplomacy.house_grudges`), decaying only across generations, not steps.
Wars between the same two houses across 2+ generations get the event
"The blood feud between X and Y flares again."

## D4 — The Chronicle
A new `chronicle.py`: an append-only, sqlite-backed saga log (survives
--persist restarts; capped by pruning LOW-salience entries, never
high). Every existing `_log_event`/`_milestone`/decision-log call gains
a salience score (constants table: maw deaths 10, betrayals 9, machine
claims 8, incursions 7 ... keeper feedings 1). The chronicle is the
long-term memory the events deque never was.

## D5 — The Saga screen (R28)
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

## D8–D12 (reserved)
Sized during design: D8 house relics (an heirloom item — the ancient
controller already behaves like one — formally owned by a house, its
loss/capture chronicled), D9 oaths (public truce promises whose
breaking doubles betrayal penalties — GoT oathbreaker mechanics on top
of P6), D10 chronicle-driven epithet vocabulary via the GloVe pipeline,
D11 saga export (write the full saga to a text file on demand), D12
acceptance soak (a 5-year run must produce a saga a human finds
readable; blood feud + epithet change + relic capture each observed).

## Compatibility
Same contract as every round: lazy accessors + getattr guards for old
checkpoints; EnhancedSandKingsSimulation stays inert; chronicle sqlite
lives beside the --persist checkpoint db; all new state pickles.

## Status
- Drafted 2026-07-08 immediately after Round 4 (commit 2b50ec9).
- Next: validate D1–D7 against the spec skill, then implement in
  order D1 -> D4 -> D3 -> D2 -> D5 -> D6 -> D7 (identity before
  memory before drama; the saga screen needs chronicle rows to read).
