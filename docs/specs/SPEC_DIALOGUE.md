# SPEC: Dialogue (Round 17) — DL1–DL7

User intent: "a console dialogue option with a human using their
'thoughts'... thoughts they can send back by clicking on them... add
dialogue contextually relevant perspective thoughts - take into
consideration the dialectic between two minds and their dispositions and
what they might want to say based on their environment, but have a
shared vocabulary because we are using an embedding space."

Design: the human and an AWAKENED colony converse in the ONE shared
GloVe space. The human types free text; it is EMBEDDED and mapped to the
nearest anchor concept (the shared vocabulary is what makes them
mutually intelligible). The colony REPLIES with a perspective line
generated from its disposition + its live environment concerns + what it
just heard - a genuine dialectic, not a canned response.

## DL1 — Understanding the human (embedding -> anchor)
`dialogue.interpret(text) -> anchor`: embed the human's words in the
GloVe space, cosine-rank against the anchor seed vectors, return the
nearest anchor (keyword fallback if vectors absent). This is the
mutual-intelligibility step: arbitrary human words become one of the
sandkings' concepts because both live in the same embedding space.
Order of resolution: (1) a direct anchor mention wins; (2) a small
sentiment-pinned SYNONYM map (`_SYNONYMS`) then fixes the words GloVe
misplaces — antonyms share contexts, so a bare nearest-neighbor maps
"peace"→"war" and "hate"→"love"; the map pins peace/truce/friend→ally,
attack/fight/kill→war, thanks→gratitude, etc.; (3) only then the
embedding nearest-anchor; (4) keyword fallback. This keeps the
mutual-intelligibility promise from inverting on sentiment-loaded words.

## DL2 — The colony's reply (disposition x environment x heard)
`dialogue.compose_reply(colony, sim, heard) -> str`: a perspective line
built from three parts, each a word drawn from the shared VOCABULARY:
- STANCE from the dominant disposition gene (aggression -> a war word;
  loyalty -> an ally word; patience -> a wait/hoard word; else a home
  word);
- the HEARD concept, acknowledged (the human's mapped anchor);
- the colony's own top live concern (its first active instinct anchor).
Template: "<stance>. <heard>? <concern>." - terse, insectoid, but
grounded in who this colony is and what it faces. Two different colonies
answer the same human word differently: the dialectic of dispositions.

## DL3 — The exchange (sim.converse)
`sim.converse(colony_id, text) -> {heard, reply, understood}`:
- UN-AWAKENED colony: understood=False, reply="" - it cannot hold a
  conversation (the K12 "words fall as noise" gate; sentience gates
  language).
- AWAKENED colony: interpret the text -> heard anchor; mark it spoken-to
  (K12 `speak` anchor lights) and apply a GENTLE persuasion nudge (the
  heard concept moves one disposition by DIALOGUE_NUDGE, like a codex
  lesson but from the human - the human can teach through talk); then
  compose_reply. Logs a decision "answered the god: <reply>".

## DL4 — The console (two-way)
The Keeper's Console House card's speak box (K12) becomes a chat: typing
POSTs `/api/converse {colony_id, text}`; the reply renders under the
card as `House X: "<reply>"`. Un-awakened houses show the noise line.
The card also surfaces the colony's own unprompted utterance (already
present). Clicking a House selects it; the human can also click the
suggested anchor chips to "send a thought" without typing.

## DL5 — Safety / compatibility
Pure embedding lookups + template fill; no eval/exec, no network. The
persuasion nudge is bounded [0,1] like every other. Un-awakened gating
preserved. `dialogue` is stateless (derives from the shared vocab);
nothing new to pickle beyond the K12 spoken_to_step already present.
Evolution sim untouched.

## DL6 — Acceptance
tests/test_dialogue.py: interpret maps "peace/ally" -> a cooperative
anchor and "attack/kill" -> a hostile one; compose_reply differs by
disposition for the same heard concept; converse gates on breach
(noise vs reply), lights the speak anchor, applies a bounded nudge, and
returns a non-empty reply for the awakened; the dashboard /api/converse
endpoint works; keyword fallback works without vectors.

## DL7 — Economy vocabulary (the labor political-economy arc)
The economy arc (SPEC_LABOR/SUBJUGATION/WAGES/BARGAIN + SPEC_ENLIGHTENMENT)
adds three anchors — `trade`, `thrall`, `ascend` (SPEC_HIVE_MONITOR M15).
So a human can now converse ABOUT the shipped economy in plain words that
map onto those concepts, and can nudge a colony's disposition toward
commerce, cruelty, or ascension by talk. Every synonym VALUE below is a
REAL anchor (the M15 anchors must exist first).

**DL7a — `_SYNONYMS` pins (commerce, bondage, enlightenment).** Extend the
`_SYNONYMS` map (`dialogue.py:30`), checked before the antonym-prone
embedding step, so mercantile / slaving / awakening words the human is
likely to use resolve to the right anchor rather than a GloVe near-miss:
- commerce / market / hire / wage / barter / bargain / sell / buy → `trade`
- slave / enslave / subjugate / captive → `thrall`
- enlighten / awaken / genius → `ascend`

Rationale: like peace≈war, these are sentiment/context-loaded — "barter"
and "wage" sit near generic economics words in GloVe, "captive" near
war/enemy, "genius"/"awaken" near unrelated common terms — so a bare
nearest-anchor lookup misroutes them. Pinning keeps the shared-vocabulary
promise intact for the economy the same way DL1 does for peace/hate.

**DL7b — `converse` `nudge_map` additions (the human teaches through talk).**
The DL3 persuasion nudge lives in `sim.converse` (`sandkings.py:2594`) as a
`nudge_map` from the heard anchor to a genome disposition. Add three entries
so talking economy shifts disposition, mirroring the codex `commerce` /
`enlightenment` lessons (SPEC_CODEX CX7):
- `trade` → fertility AND loyalty (the commerce lesson's two attrs)
- `thrall` → aggression
- `ascend` → plasticity

Code note (real structure differs from a flat map): the shipped `nudge_map`
values are single attribute strings (`{'ally':'loyalty', ...}`) and apply
ONE `DIALOGUE_NUDGE`. `trade` needs TWO attrs. Canonised resolution: allow a
`nudge_map` value to be a string OR a tuple of attrs, and apply the bounded
`DIALOGUE_NUDGE` to each — `trade`: `('fertility','loyalty')`,
`thrall`: `'aggression'`, `ascend`: `'plasticity'`. Existing single-string
entries are unchanged (normalise a bare string to a one-tuple at read).
Each nudge stays `np.clip(..., 0.0, 1.0)` bounded (DL5), so nothing escapes
`[0,1]`.

**DL7c — optional mercantile `_STANCE` row.** `compose_reply`'s `_STANCE`
table (`dialogue.py:94`) opens the reply with a disposition-driven stance
word (aggression→war, loyalty→ally, patience→home). OPTIONAL, additive: add
a mercantile row `("fertility", 0.65, "trade")` so a high-fertility (growth /
commerce) colony opens with a trade word — a merchant-nation voice distinct
from the warlike and loyal ones. It slots into the same first-match-wins
scan; if omitted, stance falls through to the existing rows unchanged. Keep
it AFTER the aggression/loyalty rows so a warlike merchant still reads
warlike.

**DL7d — gating unchanged.** All three additions ride the existing DL3
breach gate: an un-awakened colony still hears only noise, so the economy
vocabulary is speakable only to a colony that has escaped. No new state; the
map/table edits are pure and consume no RNG (DL5 holds).

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: interpret
  maps direct mentions and embeds unnamed words ("friends and comrades"
  -> love, "destroy and kill" -> enemy) after stopword filtering;
  compose_reply answers the same heard concept differently by
  disposition; converse gates on breach (noise vs reply), lights the K12
  speak anchor, applies a bounded persuasion nudge, and returns a
  non-empty reply for the awakened; the /api/converse endpoint works;
  keyword fallback holds without vectors. 19/19 suites green incl.
  tests/test_dialogue.py (7). The console speak box is now a two-way
  chat showing the colony's reply.
- 2026-07-11 — DL7 added (economy-arc alignment): `_SYNONYMS` pins for
  commerce/bondage/enlightenment, `converse` `nudge_map` gains
  trade/thrall/ascend, optional mercantile `_STANCE` row. Depends on the
  M15 anchors (`trade`/`thrall`/`ascend`) existing in `ANCHOR_SEEDS`.
  Spec-first: implementation pending.
