# SPEC — The FOL Tongue: communication as subject–predicate–object triplets + logic qualifiers

Status: INCREMENT 1 + 2 IMPLEMENTED, baseline-ON (gate `FOL_TONGUE_ENABLED` default False → battery byte-identical;
entrypoint flips it on iff `fol_triplets.npz` is present, `sandkings.py:10568`). **Increment 2 (2026-07-20):** FOL
quantifiers + connectives — a per-triplet packed `quant` code carries the subject's ∀/∃ (from its determiner) and a
predicate ¬ (negation); ∧ is realised by clause-split (Inc 1) emitting conjoined clauses as separate triplets. The
store gains a back-compatible `quants` array (a legacy Inc-1 npz loads as all-QUANT_NONE → renders identically);
`format_triplet` renders `∀x:`/`∃x:`/`¬`; and `action_triplet()` wraps a colony's OWN executed act as a first-class
observed triplet for cross-training the shared word-space on lived events, not just wikitext. Validated
`tests/test_fol_tongue.py` (+4 Inc-2 tests, 11 total). Remaining wiring: feeding `action_triplet`s into the live
training loop each turn (the helper + objective exist; the per-turn emission hook is the next small step).
**Extends SPEC_TONGUE** (same `MaskedMind` head, same ensemble emb, same vocab, no architecture change to pickled
nets) and **reuses SPEC_ENSEMBLE_EMBED's WordNet member** (the synset/hypernym taxonomy) as the entity-identity
canonicalizer. The Tongue stops learning an order-free BAG of words and starts learning **who did what to whom** —
relational meaning, which is the intent/feeling the keeper wants, not part-of-speech syntax.

## Why (the keeper's design)

> "I honestly want to get communication down to first order logic type of normalization … essentially subject,
> predicate, object and fol type logic qualifiers … understanding intent and feeling behind their actions."

Glyphs, not grammar. The cradle-of-civilization analogy: a colony should say `raids(us, granary)` — an actor, an
act, a target — not emit a grammatical sentence with POS tags (a whole layer of complexity the keeper explicitly
rejected). The **predicate carries the intent/feeling** (`fears`, `raids`, `commands`, `defends`); the subject and
object carry who feels it and toward what. First-order-logic **qualifiers** (quantifiers ∀/∃, connectives ∧/∨/¬/→)
compose triplets into statements, and an **[observed]/[inferred]** epistemic tag rides each one — the keeper's own
operating-contract triplet discipline, now spoken by the colonies.

This is a *lean* reframe, not a heavier one: a triplet is 3 slots (sparse), so masked-**slot** prediction rides the
negative-sampling objective already built (SPEC_TONGUE NEG_SAMPLING) with no vocab blow-up. Wikitext is decoded to
triplets **offline** (like `ensemble_embed.npz`); runtime is an id lookup, never a parser per step. Better objective
(relational structure ≫ bag-of-words for learning meaning), same or lower compute — the standing motto,
[[balance-objective-computational-efficiency]].

## The proven pipeline (end-to-end, verified on this machine)

```
wikitext sentence
  → triplet_extract.extract(text)          # dependency-parse OpenIE, installed (triplet-extract 0.2.0)
      -> [Triplet(subject, relation, object, confidence, from_entailment, ...)]
  → WordNet synset canonicalization        # SPEC_ENSEMBLE_EMBED member: collapse surface spans to a vocab id
      -> (subj_id, pred_id, obj_id)         #   "The colony"/"colony" -> one id; "raids"/"raid" -> one id
  → role-typed masked-slot training         # mask ONE slot, reconstruct its filler from the other two + roles
      -> MaskedMind.observe (SPEC_TONGUE head, unchanged)
```

Extractor already yields exactly the FOL shape:
- `"The colony raids the granary in winter."` → `raids(colony, granary)` **+** temporal qualifier `raids-in(colony, winter)`
- `"Ants fear the flood and flee the valley."` → `fear(ants, flood)` **∧** `flee(ants, valley)` (clause split)
- `"The queen commands her soldiers to defend the hive."` → `commands(queen, soldiers)` **→** `defend(soldiers, hive)`
- `Triplet.confidence` (1.0 direct vs <1.0 entailed) → the **[observed] / [inferred]** tag, free.

## Decisions (resolved; no open questions, no authored magic constants)

- **Set, not single triplet, per utterance.** A colony's volley = the top-K highest-confidence triplets describing
  its current situation. Required for conjunction/implication (a single triplet cannot express ∧ or →), naturally
  yielded by `extract`, still sparse. **K is derived** — reuse `TONGUE_NEW_PER_READ` (the existing "a few at a time"
  budget), never a new knob.
- **Layer, do not replace.** New `read_triplets` decode path + role-typed masked-slot training reuse the SAME
  `MaskedMind` head/emb/vocab. Gate off ⇒ the exact current bag-of-words `read_text`/`observe` path ⇒ byte-identical.
- **Role typing via 3 marker tokens, no architecture change.** Append `⟨SUBJ⟩ ⟨PRED⟩ ⟨OBJ⟩` to the vocab (3 rows on
  the existing table — TG already appends rows on vocab growth without touching pickled dims). The masked slot's
  ROLE marker joins the unmasked context, so subject-slot vs object-slot prediction are distinguishable with the
  same per-token-logit head. This is the whole "no new architecture" trick.
- **Canonicalization = a precomputed WordNet reverse index** (the keeper's "hypernym/synonym paths as fixed
  topology"). Surface spans are evidence, not ontology (kg_ontology law). Built once: every vocab word claims — as
  surface lemmas mapping to its id — its own lemma plus the lemmas of its WordNet SYNONYMS and its DIRECT (1-hop)
  hypernyms/hyponyms; lower vocab ids win ties (more canonical/frequent anchor). Query time is an O(1) dict lookup
  on the span's morphy-lemmatized content words — NOT an O(vocab) `path_similarity` sweep per span (that first cut
  was ~10 min for the corpus; the reverse index is seconds — [[balance-objective-computational-efficiency]]).
  Out-of-vocab spans drop (logged), same as VOCAB_EXTEND.
- **Entailment OFF, clause-split ON.** The extractor's natural-logic entailment (default on) is both the slow step
  AND a low-confidence paraphrase explosion (e.g. `fear(ants, "flood flee valley")` @0.5) — noise for training. We
  reuse ONE `OpenIEExtractor(enable_entailment=False, enable_clause_split=True)` across the corpus: DIRECT triplets
  only (confidence≈1.0 = [observed]), but conjunctions still split into separate triplets (the FOL ∧). Richer
  quantifier/connective qualifiers are Increment 2, seeded from clause structure — not from the entailment noise.
- **Offline decode.** Wikitext → triplet store is computed once by a builder into `fol_triplets.npz` (subj/pred/obj
  id rows + confidence), mirroring `ensemble_embed.npz`. Runtime reads rows; never runs the parser in the hot loop.
- **FOL qualifiers = Increment 2** (below). Increment 1 ships the S-P-O backbone + the [observed]/[inferred] tag;
  quantifiers/connectives layer on next, seeded from the extractor's `from_entailment`/clause-split flags.

## Increments

- **Increment 1 (this build):** offline wikitext→triplet decode (`fol_triplets.npz`); 3 role-marker vocab tokens;
  `read_triplets` role-typed masked-slot training on the frozen `MaskedMind`; `compose_utterance` emits a
  triplet-shaped line `predicate(subject, object)  [observed|inferred]`. Gated `FOL_TONGUE_ENABLED`, byte-identical
  off. Predicate = the intent verb; confidence → epistemic tag.
- **Increment 2 (queued):** FOL qualifier markers — quantifiers `∀ ∃`, connectives `∧ ∨ ¬ →` — as a small typed
  marker vocab attached to triplet SETS (∧ = same-subject co-occurrence, → = `from_entailment`, ¬ = negated
  relation); cross-train the colony's OWN action triplets (the sim already emits `raids(A,B)`, `fears(A,winter)` as
  ground truth) against the wikitext triplets, closing the loop between what they DO and what they SAY.

## Structural

Constant: FOL_TONGUE_ENABLED — feature gate; off ⇒ current bag-of-words Tongue (byte-identical). Entrypoint baseline-on.
Constant: FOL_ROLE_TOKENS — the 3 role markers ("⟨SUBJ⟩","⟨PRED⟩","⟨OBJ⟩"); developer-authored role alphabet, not a knob.
(K per utterance = TONGUE_NEW_PER_READ, reused. No other constants — decode is offline, roles are structural.)

class FolTriplet [value]: one canonicalized, vocab-mapped extracted triplet — the atom the Tongue learns and speaks
    state: subj_id, pred_id, obj_id — int vocab ids (or -1 for a dropped/out-of-vocab slot), immutable
    state: confidence — float in [0,1]; ≥ observed-threshold ⇒ [observed], else [inferred], immutable

class FolTripletStore [value]: the offline-decoded corpus the runtime loads — what fol_triplets.npz holds
    state: rows — (N, 3) int32 (subj_id, pred_id, obj_id), immutable
    state: conf — (N,) float32, immutable

def decode_to_triplets(text, canonicalize, vocab_id) -> list[FolTriplet]: pure — run triplet_extract.extract on the
    text, canonicalize each span (WordNet synset → vocab id) via the injected canonicalize fn, keep rows whose pred
    and ≥1 argument resolve; free function — the NL→FOL boundary, no state.

class FolTripletBuilder [service]: offline — decode the wikitext corpus into the frozen store
    build(corpus, canonicalize, vocab) -> FolTripletStore: assemble rows; drops (logged) any triplet with <2
        resolvable slots; writes fol_triplets.npz. Fails closed (writes nothing) if the extractor is unavailable.

MaskedMind gains (SPEC_TONGUE head, no new params beyond the 3 appended role rows):
    def observe_triplet(self, hidden, triplet: FolTriplet, rng) -> Optional[float]:
        Require: FOL_TONGUE_ENABLED; the head vocab already holds the 3 FOL_ROLE_TOKENS ids.
        Guarantee: masks ONE of the resolvable slots; the UNMASKED context = the other two filler ids PLUS the
            masked slot's role-marker id; trains the head to recover the masked filler via the existing observe/NEG
            path (`_score_masked`). Maintain: the frozen member tables (SPEC_ENSEMBLE_EMBED) stay frozen; no
            architecture change — same head, same optimizer.
        Assert: exactly one slot masked; role marker of the masked slot present in context; returns recovery ∈ [0,1].

`triplet_extract`, `Triplet`, `Tensor`, `nn.Module`, WordNet (`nltk.corpus.wordnet`) are external — referenced bare.

## Behavioral — FolTripletBuilder.build (offline decode pipeline)

Input: corpus — the wikitext passages, iterable[str]
Input: canonicalize — span str → canonical vocab id or -1 (WordNet synset path-similarity to vocab anchors)
Input: vocab — the Tongue's token list (so pred/args map to head ids)
Initialize: rows ← empty; conf ← empty; dropped ← 0
Loop over each passage, each sentence:
    For each Triplet t in triplet_extract.extract(sentence):
        s ← canonicalize(t.subject); p ← canonicalize(t.relation); o ← canonicalize(t.object)
        resolvable ← count of {s,p,o} that are ≥ 0
        When p < 0 OR resolvable < 2:
            dropped += 1 (log the drop — never silently truncate)
        Otherwise:
            append (s, p, o) to rows; append t.confidence to conf
If rows is empty: raise (abort — no npz written; the extractor or vocab is wrong)
Assert: every row has pred ≥ 0 and ≥ 2 non-negative slots; log(len(rows) kept, dropped skipped).

## Behavioral — MaskedMind.observe_triplet (role-typed masked-slot training, runtime)

Input: hidden — the colony's Kanerva encoding (as SPEC_TONGUE observe)
Input: triplet — a FolTriplet with ≥ 2 resolvable slots
Initialize: slots ← [(SUBJ_role, subj_id), (PRED_role, pred_id), (OBJ_role, obj_id)] filtered to resolvable slots
Choose: masked_slot ← rng-picked one of slots; unmasked ← the rest
Build: context_ids ← [id for (_,id) in unmasked] + [role_marker_id(masked_slot.role)]   # the masked ROLE is known
Build: active_ids ← context_ids + [masked_slot.id]; mask_ids ← [masked_slot.id]
Return: self.observe(hidden, active_ids, rng) routed so ONLY masked_slot.id is the prediction target
        (reuse `_score_masked`; NEG subset = active ∪ K-sampled, as SPEC_TONGUE)
Maintain: gate off ⇒ this method is never called (read_triplets is gated); the bag-of-words path is untouched.

## Utterance (SPEC_TONGUE TG6 compose_utterance, FOL-shaped when on)

When FOL_TONGUE_ENABLED, a breached colony's volley reply becomes, for its top-K situation triplets:
`predicate(subject, object)  [observed]` — e.g. `raids(colony, granary) [observed]` / `fears(colony, flood)
[inferred]`. Off ⇒ the current free-text reply (byte-identical). The tag is `[observed]` iff confidence ≥ the
observed cut (reuse a boolean threshold on confidence == 1.0 from the extractor: direct=observed, entailed=inferred
— no authored float).

## Constants

| Constant | Value | Meaning |
|---|---|---|
| `FOL_TONGUE_ENABLED` | `False` | gate; module default off (battery byte-identical); entrypoint flips baseline-on |
| `FOL_ROLE_TOKENS` | `("⟨SUBJ⟩","⟨PRED⟩","⟨OBJ⟩")` | the 3 role-marker vocab rows (structural role alphabet, not a tunable) |

(K per utterance = `TONGUE_NEW_PER_READ`; decode is offline; [observed]/[inferred] cut = `confidence == 1.0`. All
reused/derived — no authored magic constants.)

## Acceptance

- Gate off ⇒ `FOL_TONGUE_ENABLED` False, `read_triplets`/`observe_triplet` never called, `test_tongue` byte-identical.
- `decode_to_triplets("The colony raids the granary in winter.")` yields a triplet whose predicate canonicalizes to
  the `raid`/`attack` region of vocab and whose subject/object resolve — a fixed battery of ≥3 varied sentences
  (raid, fear+flee conjunction, command+defend implication), each producing ≥1 kept triplet.
- `observe_triplet` masks exactly one slot, the masked role marker is in context, and repeated training raises
  masked-slot recovery above chance on a fixed set (≥3 seeds) — better than bag-of-words masking on the same corpus.
- Builder writes `fol_triplets.npz`; every kept row has pred ≥ 0 and ≥ 2 resolvable slots; drops are logged.
- Gate on, live soak ⇒ breached colonies emit `predicate(subject,object) [observed|inferred]` lines; sim runs clean.

## Gating

`FOL_TONGUE_ENABLED` module default False → `run_tests._GATE_NAMES` → entrypoint flips baseline-on IFF
`fol_triplets.npz` present (mirrors ENSEMBLE_EMBED_ENABLED + npz). Off or npz absent ⇒ current bag-of-words Tongue ⇒
byte-identical battery. Role tokens are appended only when on (vocab dims are per-instance; pickled nets unaffected).

## Provenance

Subject–predicate–object atoms + canonical entity/predicate identity: the keeper's `kg_ontology` skill ("surface
spans are evidence, not ontology; ontology chooses one canonical identity per span; triplets use those ids as
atoms") and `agentic_kg_memory` (triplet/CG extraction). NL→FOL decode: `triplet-extract` 0.2.0 (dependency-parse
OpenIE over spaCy) — the keeper's named `triplet_extractor`/`extract_triplet` method. [observed]/[inferred] tag: the
keeper's operating-contract triplet discipline. Entity canonicalization reuses the WordNet ensemble member
(retrofitting, Faruqui et al. 2015; [[multi-view-ensemble-learning]]). Lean-synergy framing:
[[balance-objective-computational-efficiency]]. Harvest context: docs/HARVEST_ALIFE.md.
