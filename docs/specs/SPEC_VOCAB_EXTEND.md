# SPEC — Extending the represented vocabulary: the anchors' concept cloud

Status: **IMPLEMENTED** (2026-07-18) — `tongue.extended_vocab` (+ `_neighbors_per_anchor` reusing KANERVA_ACTIVE),
`TongueSystem.__init__` wiring, `VOCAB_EXTEND_ENABLED` gate baseline-on, offline tool builds the extended ensemble.
Live: vocab 42 → **698** (the anchors' concept cloud), the 698-word ensemble mixture loads, and the J-lens reads the
enlarged space; battery 81/0 byte-identical; `tests/test_vocab_extend.py` green. Extends SPEC_TONGUE,
SPEC_ENSEMBLE_EMBED (the geometry it grows along), SPEC_JLENS (the lens reads the larger space).

## Why

The colonies' inner vocabulary is the 42 `ANCHOR_SEEDS` — everything the masked-mind can predict and the J-lens can
read. The ensemble models embed *any* word, so the *represented* space can be far larger. But a generic top-N word
list would fill a medieval-insectoid mind with "government, market, company." Instead, grow the vocabulary along the
universal geometry we already built: each anchor pulls in its **nearest neighbors** (`war → siege, battle, blood`),
yielding a thematically coherent concept cloud of a few hundred words. Separate two vocabularies:

- **Active vocab** (unchanged: the 42 anchors) — what colonies OBSERVE from game state (`instincts_for`) and are
  SUPERVISED on. Game activation is unchanged.
- **Represented vocab** (extended) — what the head / embeddings / J-lens COVER. The colonies can now *think* (light
  up in the J-space) a wide, coherent concept space, seeded by the ensemble, even before a word is game-activated.

## Decisions (resolved)

- **Source of the extension:** each anchor's top-M nearest neighbors in GloVe (reuse `codex._load_glove`), cosine
  over the 50-d vectors, deduped and unioned with the anchors. M a config; the anchors always lead the index (ids
  0..41 stay the active set, so `instincts_for` token ids are unchanged).
- **Supervision unchanged:** the masked-prediction target is the multi-hot of ACTIVE words over the represented
  output; inactive represented words are pushed toward 0 but keep their ensemble-seeded geometry (the J-lens reads
  them by similarity). No new supervision signal, no game-logic change.
- **Gated:** `VOCAB_EXTEND_ENABLED` default False ⇒ vocab stays the 42 anchors ⇒ Tongue/ensemble/J-lens battery
  byte-identical. Entrypoint flips baseline-on; the ensemble npz + MaskedMind head size to the extended vocab.
- **Determinism:** the neighbor expansion is a pure function of GloVe + M (no RNG), so the extended vocab is a fixed
  ordered list — reproducible, and the ensemble builds against it.

## Structural (additions)

Constant: VOCAB_EXTEND_ENABLED — gate; off ⇒ the 42-anchor vocab (byte-identical).
(Neighbors per anchor is NOT an authored knob: it REUSES the sparse-code width `neural_hive.KANERVA_ACTIVE` — how
many concepts co-activate — via `_neighbors_per_anchor()`.)

def extended_vocab(anchors: list, glove: dict, m: int) -> list: pure — anchors first (ids preserved), then their
    deduped top-m GloVe cosine neighbors; free function, no state. Returns anchors unchanged if glove is empty
    (graceful → identical to today).

`TongueSystem.__init__` uses `extended_vocab(ANCHOR_SEEDS, glove, M)` when VOCAB_EXTEND_ENABLED, else `ANCHOR_SEEDS`;
`self._active = set(range(len(ANCHOR_SEEDS)))` records the supervised subset. Everything downstream (`MaskedMind`
head/emb size, ensemble match, `read_thoughts`) already keys off `len(self.vocab)`, so they size to the extension
automatically.

## Behavioral (build-time vocab assembly, pure)

Input: anchors — the 42 ANCHOR_SEEDS, list[str]
Input: glove — the loaded {word: vec50} table (may be empty)
Parameters: m — VOCAB_NEIGHBORS_PER_ANCHOR
Initialize: vocab ← list(anchors); seen ← set(anchors)          # anchors lead, ids 0..41 preserved
Loop over each anchor a in anchors (only when glove is non-empty):
    neighbors ← the m words with highest cosine(glove[a], glove[·]), excluding a and already-seen
    append each new neighbor to vocab and seen
Assert: on completion, vocab[:len(anchors)] == anchors (active ids stable) and vocab has no duplicates.

## Acceptance

- Given VOCAB_EXTEND_ENABLED False, When TongueSystem builds, Then vocab == the 42 anchors and the Tongue/ensemble/
  J-lens suites stay byte-identical.
- Given the gate on with GloVe present, When the vocab is built, Then len(vocab) >> 42, the first 42 entries are the
  anchors in order, and there are no duplicates.
- Given the extended vocab, When the ensemble is rebuilt for it, Then the MaskedMind loads a matching mixture and the
  J-lens `read_thoughts` ranks over the full extended space (a colony can surface a non-anchor concept).
- Given GloVe absent, When the vocab is built with the gate on, Then it falls back to the 42 anchors (graceful).

## Gating

`VOCAB_EXTEND_ENABLED` module default False → `_GATE_NAMES`-style reset → entrypoint baseline-on. The extended
ensemble npz is rebuilt offline for the extended vocab; with the gate off (battery), the 42-vocab path is unchanged.

## Provenance

Grows along SPEC_ENSEMBLE_EMBED's universal geometry; read by SPEC_JLENS. Relates to [[tongue-arc-masked-mind]],
[[multi-view-ensemble-learning]].
