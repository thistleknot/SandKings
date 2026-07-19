# SPEC — Ensemble embeddings for the Tongue: a learned, universal-geometry mixture

Status: **IMPLEMENTED** (2026-07-18) — `sim/ensemble_embed.py` (gate, `relative_representation`, loader,
module-level `MixtureEmbedding`), `sim/tongue.py` MaskedMind hook, `tools/build_ensemble_embeddings.py`, gated
`ENSEMBLE_EMBED_ENABLED` baseline-on-iff-npz-present. Live `ensemble_embed.npz` = **all 7 angles** (6 distributional
+ WordNet symbolic) over the extended 698-word vocab: bert, glove, word2vec, jina, nomic, minilm, wordnet. (jina runs
via its published `model-w-mean-pooling.onnx`
through onnxruntime — its remote torch modeling code is incompatible with transformers 5.3 / torch 2.11; see
`tools/build_ensemble_embeddings.py:fetch_jina`.) Battery byte-identical; `tests/test_ensemble_embed.py`
green; NEAT+Tongue+ensemble run live and checkpoint. Baseline-ON, gate default False → battery byte-identical.
Extends SPEC_TONGUE. Design law: member tables FROZEN; only the mixture + residual learn.

## Why

The colonies learn communication (SPEC_TONGUE) on a single GloVe-seeded table. The keeper's idea: learn each concept
from ≥3 angles (5–20 ideal; chosen roster 6) — an ENSEMBLE of embedding models — combined via the universal geometry
of representations (Platonic Representation Hypothesis). Different spaces aren't directly averageable, so members are
aligned into one comparable frame via relative representations (each token = cosine-sims to shared anchors). The
blend is NOT a fixed geometric mean — it is LEARNED by the masked-prediction loss ("weights learned between what
helps reduce loss between guesses"). Frozen members = the universal substrate; learned mixture = the task-tuned blend.

## Decisions (resolved; no open questions)

- **Roster = 7:** 6 DISTRIBUTIONAL — BERT/DistilBERT (contextual — the mask/CLS co-occurrence angle), GloVe,
  word2vec, Jina v2 small, Nomic, MiniLM — plus 1 SYMBOLIC: **WordNet** (IS-A/synonym path-similarity to the anchor
  synsets via nltk, a fixed labeled taxonomy the mixture learns to weight; already in the anchor frame, so it skips
  `relative_representation`). Config list; floor 3 (builder aborts below 3 available), graceful degradation above.
- **Alignment:** relative representations at `ENSEMBLE_ANCHORS` anchors, `ENSEMBLE_ANCHORS == TONGUE_HIDDEN (32)` so
  each member table is `(vocab × 32)` and plugs into the 32-d MaskedMind head with no projection.
- **Target:** the MaskedMind head table (`sim/tongue.py:52`, the empty `# TG2: GloVe-seed + learn this` hook) — where
  the masked-prediction loss flows. The 50-d TokenSpace ensemble-seed is a secondary, seed-only follow-on.
- **Compute:** the 6 models run OFFLINE once → a frozen `ensemble_embed.npz`; runtime is a table lookup + a tiny
  learned mixture (never a transformer per step).

## Deferred angles

- **BM25 / sparse lexical** — deferred to the corpus phase: it is a sparse TF×IDF *lexical* signal (a different
  representation class), needs a document corpus for IDF (absent until wikitext / colony-emitted text), is
  vocab-dimensional (blows up the 32-d frame), and largely re-captures word2vec's co-occurrence angle. A good 7th
  angle once a domain corpus exists, not now.

## Structural

### Ensemble embedding, for a learned universal-geometry mixture over frozen member tables feeding the MaskedMind

Constant: ENSEMBLE_EMBED_ENABLED — feature gate; off ⇒ MaskedMind.emb is the current random table (byte-identical).
Constant: ENSEMBLE_ROSTER — the 6 intended member model names, developer-authored (availability is runtime).
Constant: ENSEMBLE_FLOOR — minimum members that must resolve or the builder aborts (no npz); business rule = 3.
Constant: ENSEMBLE_ANCHORS — relative-representation frame width; == TONGUE_HIDDEN (32) so no projection is needed.

class MemberEmbedding [value]: one model's frozen, anchor-aligned `(vocab × ENSEMBLE_ANCHORS)` table + its name
    state: name — str, immutable; state: table — float32 (vocab, D), immutable

class EnsembleBundle [value]: the stacked frozen members the npz holds — what the runtime loads
    state: members — (K, vocab, D) float32, immutable
    state: tokens — the vocab index (list[str]), immutable
    state: names — the K member names, immutable

class MixtureEmbedding [entity]: the runtime learned mixture (an nn.Module replacing MaskedMind.emb)
    state: members — (K, vocab, D) FROZEN buffer (never gradient-updated)
    state: mix — learned nn.Parameter, per-member logits (K,) [expansive variant (K, D)], mutated by the optimizer
    forward(token_ids) -> Tensor: mixed embedding Σ_m softmax(mix)_m · members[m, ids]; fails closed to member 0 if
        mix is degenerate (Maintain: members stay frozen — no in-place grad on the member buffer)

class EnsembleBuilder [service]: offline — gather roster vectors, align to the anchor frame, emit the bundle
    build(vocab, roster) -> EnsembleBundle: assemble the frozen bundle; fails (raises) if < ENSEMBLE_FLOOR resolve

def relative_representation(raw: Tensor, anchor_ids: list) -> Tensor: pure — each token row → its cosine
    similarities to the anchor tokens, an L2-normalized `(vocab × len(anchor_ids))` space-invariant table; free
    function — no state, it is the alignment primitive shared by every member

def load_ensemble(path: str) -> EnsembleBundle: load ensemble_embed.npz, or None if absent/unreadable (falls back
    to the GloVe seed); free function mirroring neural_hive._load_learned_basis — a pure I/O boundary, no state

`Tensor`, `nn.Module`, `nn.Parameter`, and the member models (gensim/sentence-transformers/transformers) are
external — referenced bare, never classified.

## Behavioral — EnsembleBuilder.build (offline align pipeline)

Input: vocab — the Tongue's token list, list[str]
Input: roster — the member model names to attempt, list[str] (ENSEMBLE_ROSTER)
Uses: fetch_member — load a model and embed the vocab, name → raw (vocab, d) Tensor or None if unavailable
Uses: relative_representation — raw (vocab, d) → aligned (vocab, ENSEMBLE_ANCHORS)
Initialize: anchor_ids ← the ENSEMBLE_ANCHORS most-frequent/curated vocab tokens   # global to the build
Initialize: members ← empty list                                                   # global; collects survivors

Loop over each name in roster:
    raw ← fetch_member(name)
    When raw is None:
        skip this member (log the drop — never silently truncate)
    Otherwise:
        aligned ← relative_representation(raw, anchor_ids)
        append MemberEmbedding(name, aligned) to members
If len(members) < ENSEMBLE_FLOOR: raise (abort — no npz written)
Assert: on normal completion, every member table is (len(vocab), ENSEMBLE_ANCHORS) and L2-row-normalized, and
        ENSEMBLE_FLOOR ≤ len(members) ≤ len(roster).

## Runtime behavior (MixtureEmbedding, trained by the existing MaskedMind SGD)

The mixture participates in `MaskedMind`'s existing optimizer (`sim/tongue.py:75`): each `observe` SGD step updates
`mix` by the masked-prediction BCE gradient; `members` is a frozen buffer and receives no update. No new training
loop — the mixture is just a learnable parameter in the head that already learns.

Given ENSEMBLE_EMBED_ENABLED is False or ensemble_embed.npz is absent, When a colony's MaskedMind is built, Then its
  emb MUST be the current random `nn.Embedding` and the Tongue suites MUST stay byte-identical.
Given EnsembleBuilder.build with fewer than ENSEMBLE_FLOOR resolvable members, When build runs, Then it MUST raise
  and write no npz.
Given two aligned member tables, When comparing a token pair's similarity rank across members, Then the anchor-frame
  makes them comparable (a fixed battery of ≥3 pairs whose agreed ranks match expectation).
Given the mixture on a fixed masked-prediction task, When trained N steps, Then its loss MUST be ≤ the random-init
  baseline's and `mix.grad` MUST be nonzero while `members` stays unchanged (frozen).
Given a seeded live Tongue soak with the gate on, When accuracy is read (`recovery()`), Then it SHOULD climb faster
  than the random-seed baseline; the sim MUST run clean.

## Gating

`ENSEMBLE_EMBED_ENABLED` module default False → `run_tests._GATE_NAMES` → entrypoint flips baseline-on IFF
`load_ensemble` returns a bundle (npz present) — mirrors `LEARNED_BASIS_ENABLED` + `learned_basis.npz`. Off or npz
absent ⇒ current random MaskedMind.emb ⇒ byte-identical battery.

## Provenance

Platonic Representation Hypothesis (Huh et al. 2024), relative representations (Moschella et al. 2023), the
keeper's multi-view principle ([[multi-view-ensemble-learning]]). The 7th member is SYMBOLIC — WordNet IS-A/synonym
path-similarity (retrofitting, Faruqui et al. 2015), a fixed labeled taxonomy the mixture learns to weight against
the 6 distributional views. Harvest context: docs/HARVEST_ALIFE.md.

Local grounding (skills_master): the relative-representation frame is a cosine/dissimilarity construction
(`misc/cosine-similarity`, `misc/dissimilarity-measure`, `misc/binary-similarity`); the learned blend over frozen
members is ensemble learning (`trees-ensembles/`, `misc/adaboostclassifier-with-c5`).
