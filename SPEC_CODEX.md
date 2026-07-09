# SPEC: The Codex (Round 10) — CX1–CX6

User intent: "include a version of the source code as read-only and see
if the sandking can maximize their environment extraction based on this
(reading that the environment works best coop)... reading about
minecraft, dwarf fortress... understanding how the environment works."

Core idea: an AWAKENED colony (K10/K11) can READ. The terrarium ships a
corpus - curated survival/coop lore plus the repo's own SPEC files (the
environment's documentation, read-only) - embedded in the SAME GloVe
space the thoughts already use. A colony consults the codex with its
current concerns (active anchors) and extracts a LESSON that nudges its
own dispositions toward playing the environment better. The strongest,
most-repeated lesson in the corpus is cooperation - so a colony that
reads widely drifts cooperative, exactly "the environment works best
coop."

## CX1 — The embedding space (shared, reused)
`codex.py` loads the cached GloVe wiki-gigaword-50 vectors (the same
file `thought_vocabulary.py` uses) into a word->vector map. A passage
embeds as the L2-normalized mean of its in-vocabulary word vectors.
This is the ONE shared space behind thoughts (M-spec), codex retrieval
(here), and human dialogue (Round 11). If the vectors are absent,
retrieval falls back to keyword-overlap so the system degrades, never
crashes (tested).

## CX2 — The corpus
- `corpus/*.md`: curated lore, each `##` passage tagged `LESSON: <tag>`
  (coop | fortify | dig | patience | trade). Content is domain-relevant
  survival/strategy prose (Dwarf Fortress digging, Minecraft shelter,
  Axelrod cooperation, hoarding for winter).
- The repo `SPEC_*.md` files, loaded READ-ONLY as untagged context
  passages (the sandkings reading how their own world works); their
  lesson is inferred by keyword (cooperation/ally/truce -> coop;
  wall/palisade/defense -> fortify; tunnel/dig/underground -> dig;
  patience/season/hoard -> patience; gift/tribute/trade -> trade).
- LESSON_WEIGHTS bias the corpus so `coop` is the modal lesson.

## CX3 — Consultation
`Codex.consult(words) -> (passage_text, lesson)`: embed the query words,
cosine-rank passages, return the top hit and its lesson. Deterministic
for a given query + corpus.

## CX4 — Extraction (the sim mechanic)
Every CODEX_INTERVAL (300) steps, each colony that can read - `breached`
(K10) OR holding a raspberry-pi controller (K9) - consults with its
maw's currently active anchors (colony-level `instincts_for` on a
representative unit). The returned lesson applies a bounded nudge to the
colony genome:
  coop     -> loyalty += CODEX_NUDGE (fewer betrayals, more truces)
  fortify  -> defense_investment += CODEX_NUDGE
  dig      -> tunnel_preference  += CODEX_NUDGE (weather shelter)
  patience -> patience           += CODEX_NUDGE (discount gamma)
  trade    -> loyalty += CODEX_NUDGE/2 and fertility += CODEX_NUDGE/2
All clamped [0,1]; CODEX_NUDGE = 0.03. First read per house:
"House X reads the codex and learns to <lesson>" (salience 6). The
lesson is also carried into a machine carving (⌂) so the reading is
visible on the sand.

## CX5 — Compatibility / safety
- Pure-Python + numpy; no network at runtime (GloVe is a local file
  baked at build time). Colonies never execute corpus text - they READ
  it into a lesson tag; there is no eval/exec anywhere. The corpus is
  read-only. `sim.codex` is lazily built and getattr-guarded; it is
  NOT pickled (rebuilt on demand - it is derived from files, not state).
  A `__reduce__`/`__getstate__` drops the heavy vectors from any
  pickle path.
- Evolution sim inert (no codex tick in its step()).

## CX6 — Acceptance
tests/test_codex.py: passages load and tag; consult retrieves a
coop-tagged passage for cooperative queries and a dig/fortify passage
for defensive ones; keyword fallback works with vectors stubbed;
extraction nudges the right genome attr, bounded, only for readers,
fires the event once per house; the sim pickles without dragging the
vectors; evolution sim inert. A short soak: a forced-breached colony's
loyalty rises after reading over a few intervals.

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: corpus
  loads 132 passages (curated + SPEC files), coop is the modal lesson
  (68/132) so wide reading drifts colonies cooperative; retrieval maps
  ally/truce->coop, tunnel/frost->dig, wall/siege->fortify; the codex
  __getstate__ drops the 40k-vector embeddings from any pickle (blob
  stayed < 4MB); a 1800-step soak lifted a reader's loyalty
  0.632 -> 0.662. 14/14 suites green incl. tests/test_codex.py (8).
