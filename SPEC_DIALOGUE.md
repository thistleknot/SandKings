# SPEC: Dialogue (Round 17) — DL1–DL6

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
