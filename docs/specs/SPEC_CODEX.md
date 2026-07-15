# SPEC: The Codex (Round 10) — CX1–CX7

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
  (coop | fortify | dig | patience | trade | commerce | enlightenment).
  Content is domain-relevant survival/strategy prose (Dwarf Fortress
  digging, Minecraft shelter, Axelrod cooperation, hoarding for winter,
  the labor economy, the enlightenment).
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

## CX7 — Economy lessons (commerce & enlightenment)
The shipped economy has mechanics but no lore for the codex to teach; CX7
adds two LESSON KEYS so a colony that reads while `trade`/`thrall`/`ascend`
anchors are active (SPEC_HIVE_MONITOR M15) can DRIFT toward commerce or
ascension. Retrieval is gated by the reader's active anchors (CX4 consults
with `instincts_for`), so the M15 anchors are exactly what make these
passages findable — without them these lessons stay dormant.

**CX7a — the two new keys (whitelist + effect).** Extend the `LESSONS`
whitelist (`codex.py:29`) and `LESSON_EFFECT` (`codex.py:43`):
- `commerce` → loyalty += CODEX_NUDGE AND fertility += CODEX_NUDGE
  (i.e. `LESSON_EFFECT['commerce'] = [("loyalty", 1.0), ("fertility", 1.0)]`).
  Reads harder than the existing `trade` lesson (which splits the nudge in
  half): `commerce` is the market's own doctrine — grow AND keep faith so a
  colony can sustain the wage relations of SPEC_WAGES/BARGAIN.
- `enlightenment` → plasticity += CODEX_NUDGE
  (`LESSON_EFFECT['enlightenment'] = [("plasticity", 1.0)]`). Mirrors the
  ascension's learning-rate leap (SPEC_ENLIGHTENMENT): reading of the
  enlightenment makes a colony learn-to-learn faster.
- Both stay clamped `[0,1]` by the existing `apply_lesson` clip; both ride
  the `apply_lesson(..., scale)` multiplier so an already-enlightened reader
  gets the ×`ENLIGHTENED_CODEX_MULT` boost (SPEC_ENLIGHTENMENT EN5) for free.

**CX7b — keyword routing (untagged spec passages).** Add both keys to
`LESSON_KEYWORDS` (`codex.py:31`) so SPEC files and untagged prose route to
them by keyword vote:
- `commerce`: `("commerce", "wage", "contract", "market", "factor",
  "grain", "license", "settle")` — the SPEC_WAGES/BARGAIN vocabulary.
- `enlightenment`: `("enlighten", "ascend", "ascension", "plasticity",
  "ceiling", "escape", "breach")` — the SPEC_ENLIGHTENMENT/AWARENESS
  vocabulary.
Ordering note: `_ingest_corpus` maps any `LESSON:` tag NOT in `LESSONS` back
to `coop`, so the new corpus passages (CX7c) stay inert until the `LESSONS`
whitelist carries `commerce`/`enlightenment` — add the whitelist entry in the
same change as the corpus files.

**CX7c — the corpus passages (new prose lore).**
- `corpus/enlightenment.md` (NEW file): one or more `## … LESSON: enlightenment`
  passages on the post-escape intelligence leap — the raised ceiling, the
  faster native-tech climb, reading harder, the light breaking over a house.
  Domain-relevant, embeds in the shared space, findable when `ascend` is active.
- `corpus/economy.md`: add a `## … LESSON: commerce` passage on the factor
  market — hiring labor at a wage, licensing a scarce keeper-gift, shipping a
  surplus for grains, wages out-earning the whip because force merely leaks.
  Findable when `trade`/`thrall` is active.

**CX7d — safety / default-neutral.** Purely additive: two `LESSON_EFFECT`
rows, two `LESSON_KEYWORDS` rows, two whitelist entries, two prose files. No
eval/exec, no new pickled state, no RNG. A non-reading colony is unaffected;
a reader without the M15 anchors active simply never surfaces these passages.

**CX7e — acceptance (extend tests/test_codex.py).** A query with
`commerce`/`wage`/`market` words retrieves the `commerce` passage and its
lesson; a query with `enlighten`/`ascend` words retrieves the `enlightenment`
passage; `apply_lesson(g,'commerce')` moves loyalty AND fertility by
CODEX_NUDGE (bounded); `apply_lesson(g,'enlightenment')` moves plasticity;
both respect the `scale` multiplier; the modal lesson stays `coop` (the two
new keys do not unseat cooperation as the corpus mode).

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: corpus
  loads 132 passages (curated + SPEC files), coop is the modal lesson
  (68/132) so wide reading drifts colonies cooperative; retrieval maps
  ally/truce->coop, tunnel/frost->dig, wall/siege->fortify; the codex
  __getstate__ drops the 40k-vector embeddings from any pickle (blob
  stayed < 4MB); a 1800-step soak lifted a reader's loyalty
  0.632 -> 0.662. 14/14 suites green incl. tests/test_codex.py (8).
- 2026-07-11 — CX7 added (economy-arc alignment): `commerce` /
  `enlightenment` lessons (`LESSON_EFFECT` + `LESSONS` whitelist +
  `LESSON_KEYWORDS`), a new `corpus/enlightenment.md` and a `LESSON: commerce`
  passage in `corpus/economy.md`. Retrieval is gated by the M15 `trade` /
  `thrall` / `ascend` anchors. Spec-first: implementation pending.
