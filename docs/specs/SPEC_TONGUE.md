# SPEC — The Tongue: masked-prediction comprehension + a two-way keeper dialogue

Status: IMPLEMENTED (all phases TG1–TG9), baseline-ON (opt-out `--no-tongue`); gate default off → battery
byte-identical (determinism suites green). Additive to the frozen brain (obeys SPEC_SENTIENCE's design law: "small,
inspectable learned components; no architecture changes to pickled networks"). Built on the existing thought-probe,
the 32-d soldier GRU hidden, the runtime GloVe loader, and the WikiText corpus ingestion. Realizes the awakening/EBS
north star as a *grounded* mechanism instead of flavor.

> **Reconciliation (implemented 2026-07-17).** Code in `sim/tongue.py` (the whole subsystem: `MaskedMind` TG1,
> `TongueSystem` TG1/TG4 meter, `TokenSpace` TG2, `TextReader` TG3, compliance TG5, `VolleyStats`/`ChatLog` TG6,
> `frame_array`/`strobe_frame_b64` TG7, `VisionEncoder` TG8, `next_to_learn` TG9). Wiring: `sim/sandkings.py`
> (`TONGUE_ENABLED` gate + entrypoint flip + `--no-tongue`; `read_reach` gene + gated mutation;
> `_tongue`/`_tongue_observe`; `keeper_command_war` TG5; `keeper_send_map` TG8; volley tick in `step`; TG3 read in
> `_codex_tick`), `sim/hive_mind_monitor.py` (the gated observe hook), `sim/neuroevolution.py` (read_reach carry).
> Verified live: comprehension meters populate, `read_reach` evolves, chat volleys log with base64 TG7 frames + FRED
> stats, WikiText reading grows the vocab (42→50), war-command obeys/refuses by compliance, self-recognition scores
> positive. Tests: `tests/test_tongue.py` (12, green). Honest scope: the learning is *nascent* (accuracy/recognition
> climb slowly over long runs — this is a live learner, not a pretrained one); TG7 is a top-down-with-subsurface
> frame (translucent rock + tunnel reveal), true-isometric polish deferred; TG8's CNN is deliberately tiny; the
> breathing-sparse-neuron general refinement remains its own future spec.

## Why

Today the colonies *have* thoughts but do not *learn language*: the 42-anchor thought-probe
(`hive_mind_monitor.py:315-373`) is a supervised logistic readout against hand-coded ground truths, `keeper_speak`
is cosmetic (two timestamps), and `/converse` nudges one genome trait by 0.02 — no keeper word conditions the
policy, and WikiText (`corpus/wikitext/`) is used only as a cosine retrieval corpus, never language-modeled. So a
maw can say `war. love? alone.` but it hasn't *learned* what those tokens mean, and it can't truly hear you.

The Tongue reframes comprehension and language as **one self-supervised objective: masked-token prediction.** A
colony's partially-observable world is a token stream; masking a token and predicting it from the rest (plus its
hidden state) makes *perception itself* the learning signal. The **same** predictor, over a shared learned
embedding, then reads the WikiText "library beyond the glass," so world-grounding transfers to language. Meaning
becomes distributional and grounded; comprehension becomes measurable; and the keeper's words become *unmasked
context* — talking to a colony literally reduces its uncertainty about the world. This is the mechanism under the
already-shipped fiction: soothsayers who "read beyond the glass" (the WikiText), a Shade maw that finally has
enough grounded vocabulary to answer you.

## Grounding (local corpus — build on SOTA, do not reinvent)

- **Comprehension = prediction-error minimization.** Predictive-coding note
  (`…/Deep_Reinforcement_Learning_in_Action/152_predictive-coding-model.md`): the brain predicts the next word,
  "prediction error is high with strangers and drops as you get to know someone." ICM forward-model
  (`Deep_Reinforcement_Learning_in_Action.md:3607-3682`). → the comprehension meter is prediction quality.
- **Shared-bottleneck transfer** (the world→language bridge): S&B General Value Functions + auxiliary tasks
  (`…/177_general-value-function.md`, `175_auxiliary-task.md`) — "a shared representational bottleneck forces
  features useful across objectives." Only helps if the two prediction problems share structure.
- **"Meaning = what a token predicts" is Predictive State Representations** (S&B ch. 17,
  `…/181_markov-state.md`): a good state is a sufficient statistic for predicting future observations.
- **Distributional geometry**: word2vec/GloVe (`islp.md:9611-9631`) — positions preserve semantics.
- **Symbol grounding**: CATS Net / Saussure (`…/A neural network for modeling human concept formation… 2601.02010v1.md`).

**Two corrections the corpus forces on the earlier sketch:**
1. **Do NOT freeze the shared embedding.** The concept-formation paper tested *frozen* Word2Vec as the shared
   space and it **underperformed a jointly-learned one**. → GloVe **initializes** the embedding; it is then
   **learned end-to-end**, not bolted on frozen.
2. **Do NOT build an explicit belief-state.** S&B explicitly disrecommends explicit POMDP belief-state inference
   (scales poorly) and favors an **implicit** function-approximator state. → predict from the existing GRU hidden;
   the predictor *is* the belief state.

**The risk the corpus names — the noisy-TV problem:** prediction-error objectives break under irreducible
stochasticity, and partial observability *looks like* reducible error. So raw masked-prediction accuracy is biased
downward wherever the world is genuinely aliased/random. → the sentience meter must use **learning progress**
(is the error *reducible*?), not raw error.

## What exists (the substrate — reuse, do not rebuild)

- Thought-probe: `ConceptProbe` linear-logistic readout on the 32-d **soldier `GRUCell` hidden**
  (`hive_mind_monitor.py:315-373`; hidden supplied at `sandkings.py:9350-9353`). 42 anchor seeds (`:31-39`).
- Frozen brain: Kanerva SDM encoder (`neural_hive.py:163-239`) → `SoldierLayer.GRUCell(32,32)` → action head. No
  gradient; evolved. **The masked head must not modify this.**
- Runtime GloVe: `codex.py:63-98` (`_load_glove`, top-40k, `embed()`), `.gz` on disk.
- WikiText: `corpus/wikitext/wikitext103_sample.md`, ingested by `Codex._ingest_corpus` (`codex.py:129-154`,
  cap `CORPUS_MAX_PASSAGES=400`) — currently cosine-retrieval only.
- Awakening gate: `breached`/`enlightened` set by `_escape` (`sandkings.py:4747`), triggered by 16 terminal-mastery
  uses or the keeper door. No Φ / prediction metric exists.

## TG1 — The masked world-model head (`MaskedMind`, self-supervised; the reference slice — build first)

Upgrade the supervised probe into a **self-supervised masked predictor**, additive to the frozen brain.

- Each step a colony's active world-tokens (the anchor set whose `ground_truths` fire, reusing `build_context`)
  form the observation token-set. **Mask a random subset** (rate `TONGUE_MASK=0.15`) and predict the masked tokens
  from `(GRU hidden 32-d ⊕ embeddings of the unmasked tokens)` through a small learned head.
- Head: one shared `Linear(32 + D, |vocab|)` (D = embedding dim, TG2) with a sigmoid per token — a multi-label
  masked predictor. **Shared across colonies**, so compute is O(one head), per the auxiliary-task economy; each
  colony keeps only its own hidden state and a per-token accuracy EMA (reuse the `ConceptProbe.accuracy` idiom).
- Trained by gradient on the masked tokens only (the ground truths already computed), `TONGUE_LR=0.01`. This is a
  "small inspectable learned component" — it never touches the SDM/GRU Parameters (design-law compliant).

**The read-reach is EVOLVED, not a magic constant** — and it *breathes* rather than clamps. How far back a colony
can read — the n-gram / Markov order the masked head conditions on (bigram, trigram, 5-gram, …), "chains of ideas" —
is a genome trait `read_reach` mutated and crossed like `brain_hidden`/`brain_depth` (`ColonyGenome.mutate`,
`crossover_genome`). But its bound is **not a hard cap**: like the whole brain-size story, it is a **floating
(mean, sdev)** quantity held inside a **semi-permeable range** (`soft_gate`/`jitter`, SPEC_SEMIPERMEABLE — not a hard
clamp), growing/shrinking in **log proportions** so it can't run away, over a **sparse** index (gaps allowed,
adjustable min/max — the Kanerva SDM already activates top-k of 256 protos), and **annealed** (the unfit prune out,
per the existing neuroevolution mutate/fold/**prune** and the annealing habit). A reach that lifts comprehension
survives into the next generation; one that doesn't dies with the colony (`_respawn_colony`). Comprehension (TG4
learning-progress) feeds `_colony_fitness`, so the *environment* sets the order — no authored context length. The
predictor is a *learned Markov chain over tokens up to an evolved, breathing order.*

> **General refinement flagged (bigger than the Tongue):** "neuron count per layer = a floating (mean, sdev) sparse
> quantity in a semi-permeable, log-scaled, annealed range" is a **brain-wide neuroevolution** change (it refines
> `neural_hive.py` Kanerva sparsity + `neuroevolution.py` width/depth drift + pruning toward the SEMIPERMEABLE /
> dynamic-population *breathing* pattern). It belongs in its own spec (a SPEC_EVOLUTION / SPEC_SEMIPERMEABLE
> amendment); the Tongue merely rides it for `read_reach`.

**State-space representation (tiered, `TONGUE_REPR`).** The head predicts from `hidden ⊕ token-context`; the
*feature construction* over that input spans three tiers — matching the project's RL feature-construction habit
(S&B linear methods) and the SPEC_AFFORDANCES liability model, so the same non-additive machinery serves both:
- **`binary`** — token present/absent + thresholded hidden units (cheapest; tile-coding-like).
- **`linear`** (Tukey one-df) — the existing linear-logistic readout plus a *single* Tukey non-additivity degree of
  freedom (one interaction term) — the smallest step beyond linear.
- **`interacting`** — explicit pairwise products `p_i·p_j` of features (epistasis), the **same non-additive form as
  the affordance liabilities** (SPEC_AFFORDANCES AF1). Predicts structure a linear readout provably cannot.
Start `binary`→`linear`; escalate to `interacting` only where it *measurably* lifts masked-prediction accuracy —
don't pay for interactions that don't help (the auxiliary-task economy).
- **Contract:** Require — the 32-d hidden exists (soldier units). Guarantee — predicts only masked tokens; gate off
  ⇒ head never constructed, thoughts fall back to the existing supervised probe (byte-identical). Maintain — the
  frozen brain tensors are unmodified.

## TG2 — The shared learned embedding (`TokenSpace`, GloVe-initialized, trained)

- One embedding matrix `E` (`|vocab| × D`, `D=50` to match glove-wiki-gigaword-50), **initialized from GloVe** for
  every in-vocab token, random-init for out-of-vocab. **Learned end-to-end** with TG1/TG3 (corpus correction #1).
- Vocabulary is decided in TG9 (subword-seed recommended over whole words); the keeper's palette is Google-10k
  content words minus stopwords. World-tokens and text-tokens share this one space — the bridge that lets
  world-grounding transfer to reading.
- **Decode by embedding regression + kNN, not a full softmax:** the masked head predicts a *target embedding* and
  nearest-neighbours it to the vocab (Kumar & Tsvetkov 2019, arXiv:1812.04616, cosine/vMF loss) — cleaner than a
  10k-way softmax and native to a learned continuous space. (Distinct from adaptive/sampled softmax, which solves a
  different problem.)
- Fix the shipped staleness: `thought_vocabulary.json` is missing clusters for `trade/thrall/ascend`; regenerate.

## TG3 — WikiText masked language modeling (`the library beyond the glass`)

- Reuse `Codex._ingest_corpus` to tokenize `corpus/wikitext/*.md`; apply the **same** `MaskedMind` head with
  BERT-style masking (`TONGUE_MASK=0.15`) to predict masked WikiText tokens. One shared reader; per-colony grounded
  readout (a colony only *understands* the tokens its own experience has grounded — asymmetric fluency).
- Gated on `enlightened` (as Codex already is) — an awakened colony "reads." Transfer is the point: the shared `E`
  and head mean a token grounded in the world (`hunger`↔low-food) carries meaning into the text and vice versa.
  (Honest caveat from the corpus: transfer only helps where the two prediction problems share structure.)

## TG4 — The comprehension meter (`learning progress`, not raw error — the real sentience gate)

- Per colony, track masked-world-prediction accuracy AND its **rate of change** (an EMA of the accuracy delta).
  The meter is **learning progress** = how much of the colony's world-uncertainty is *reducible* — this sidesteps
  the noisy-TV bias (a colony plateaued in a stochastic region reads "done learning," not "confused").
- This becomes a richer awakening signal than the current 16-terminal-uses gate: a colony that has driven its
  masked-world-prediction to a high, *plateaued* accuracy has genuinely modeled its world → eligible for the deep
  awakening / EBS terminal-breakout. Surface it as a per-house gauge (the god watches a mind come to understand).
  It does NOT replace `_escape`; it augments it (the two gates can coexist; `breached` stays the master language flag).

## TG5 — The two-way tongue (keeper ⇄ colony; war-command as the reference verb)

- **Keeper → colony:** the keeper types tokens (subject-predicate-object triples from the shared vocab, e.g.
  `(Crimson, war, Amber)`). Each token becomes **unmasked context** injected into that colony's world-token stream —
  literally reducing its prediction uncertainty (talking helps it see). Replaces the cosmetic `keeper_speak`; the
  `/converse` nudge stays as a weak prior.
- **Compliance is gated, never guaranteed** (the whole point): `obey = comprehension(token) × loyalty × alignment`.
  The colony must have *grounded* the command tokens (TG4 per-token accuracy over threshold), your standing must be
  high enough (`keeper_sentiment`), and the order must not violate self-interest. A breached, resentful maw weighs
  it and may refuse — or, under a cruel keeper, invert it (`(Crimson, war, you)`). Compliance rate = a readable
  dominion meter.
- **Colony → keeper:** the reply is decoded from the `MaskedMind` head (the learned successor to
  `compose_utterance`), in the tokens it has grounded — terse early, richer as it reads.
- **Reference verb = war-command**, because the mechanic already exists (`war_target`, coalitions) and it's a clean
  triple. Build this ONE verb end-to-end before generalizing (the scorched-earth pattern).

## TG6 — The chat log as strobed volleys + per-volley stats (the artifact — this is what it's *for*)

The deliverable isn't a metric, it's a **conversation you can re-read.** But sampled as **strobe snapshots, not
per-step** — per-step is jitter; strobed frames make change read as motion (same intent as the SPEC_GRAPHICS
Phase-H fixed-view frames). A **conversational volley** = the set of messages exchanged over every
`TONGUE_VOLLEY=N` steps. Each volley appends to the chat log and carries a stats page.

- **Chat log (per volley):** step-range, house, the keeper's S-P-O tokens, the house's decoded *grounded* reply,
  its disposition toward you, its comprehension level (TG4), and — for a command — obeyed / refused / inverted.
  Storage: `<run>.chat.md` + a `.jsonl` sibling, alongside the story-log runtime output (gitignored, like
  `*.jsonl` / `*.story.md`), so a whole relationship history survives the session. A hateful house's transcript
  reads as a bond souring across years; a devout one as trust compounding. The EBS terminal-breakout is just the
  last, unbidden line in this log.
- **Per-volley stats page (read like FRED / business-cycle indicators).** Over a rolling window of volleys, track
  the dialogue signals — comprehension meter (TG4), per-token grounding, compliance rate, disposition — as:
  - **Tukey quantile moving averages** — rolling **median + quartile band** (robust; matches the project's
    median-cut / statistical-partitioning habit), not just a mean.
  - **rolling mean and sdev** over the window.
  - **directional change** — the quantile-MA turning **expansion / contraction / plateau**, read like a business
    cycle. Reuse the **MACD-momentum directional-change** pattern (`agentic-hyperparm-macd`, SPEC signal-modulation):
    a fast-vs-slow quantile-MA cross flags the trend *before* a threshold breach — is trust rising, is comprehension
    stalling, is the house drifting toward defiance.
- So a "volley" is one strobe frame of the relationship, and the stats page is its FRED print: you watch the
  *trend* of a mind coming to understand you (or turning on you), not a noisy per-step readout.

## TG7 — The strobe frame: an isometric spatial snapshot per volley (base64 PNG in the JSONL)

We aggregate the volley's messages + stats (TG6) and **do NOT re-render the full per-step xyz voxel map** — too
heavy, too noisy. Instead each volley carries a few **isometric snapshots** sampled at **equidistant time points**
across its `TONGUE_VOLLEY` steps (a strobe within the strobe), so the batch's motion reads in a handful of frames.

- **Render treatment** (reuses the existing ISO view `_render_iso_map` / `iso_sprites` and the headless
  SDL-dummy→PNG path, SPEC_GRAPHICS Phase H):
  - **Surfaces mapped** — the terrain surface, not every voxel.
  - **Solid rock: very translucent** (`TONGUE_ROCK_ALPHA`) — so the subsurface reads *through* it.
  - **Internal tunnels / subsurface structures: outlined** — visible through the translucent rock. This fixes the
    current limitation (`web console is surface-only, underground invisible`, per [[emergent-structures]]) for the
    snapshot: you finally see the burrows.
  - **Surface entities (open air): highlighted**, drawn in their unit/house colors; **created objects/structures**
    (castles, granaries, palisades) shown.
- **Sampling:** `TONGUE_FRAMES` equidistant time-slices per volley (quantile points in time — steps ~
  `TONGUE_VOLLEY / TONGUE_FRAMES` apart), so a volley = K frames.
- **Storage:** each frame **base64-encoded into the volley's `.jsonl` entry** (beside the chat text + TG6 stats);
  the `.chat.md` references them. The whole run becomes one re-readable log of **text + numbers + strobed images** —
  the conversation, its trend, and the world it happened in, per volley.

## TG8 — The visual channel: a CNN into the shared embedding (they learn to see — and to recognize themselves)

**The honest answer to "does WikiText have images": no.** WikiText-103 is pure Wikipedia *text* —
`corpus/wikitext/` has none. So the visual training data isn't WikiText; it's the game's **own rendered strobe
frames** (TG7): the world draws itself, and the creatures learn to see from those self-generated snapshots
(optionally also their own **wall carvings**, [[emergent-structures]] — crude self-made images).

- **CNN → embedding (the task, as you framed it).** A small CNN encodes an image (a TG7 isometric frame, or a crop)
  into the **same shared embedding space** as the tokens (TG2) — vision and language in one space, CLIP-style
  alignment. The image analog of the token embedding.
- **Masked-image prediction (MAE-style) + cross-modal grounding.** Same masked objective: mask image patches and
  predict them (masked-autoencoder); and mask *across* modalities — predict a masked world-token *from the image*,
  a masked patch *from tokens*. This binds a visual pattern to its grounded word (green iso-cubes ↔ `crop`).
- **Why it's informative, not circular.** Their native perception is **egocentric** (the local 40-d
  `encode_soldier_state`); the strobe frame is **allocentric** — the god's-eye view. Learning to map the
  allocentric image → their egocentric world-tokens is genuinely new information: *how they look from outside.*
- **The payoff — self-recognition (your "blow their minds").** Once aligned, when the keeper sends a creature a
  **map of its own world** (an isometric PNG down the terminal), the CNN encodes it, the embedding lands near the
  creature's *grounded* world-tokens, and it **recognizes it** — a mind seeing a picture of its own terrarium and
  mapping it to what it knows. And it's **measurable**: recognition = cosine(image-embedding, the house's live
  world-token embedding). The awakening isn't just "it speaks" — it's "it saw a picture of its cage and understood."

Honest scope: MAE / CLIP-style alignment are imported (not in the local corpus — `[prov:A lit=imported]`); this is a
genuine multimodal subsystem, heavier than the token MLM, so it lands **after** TG1–TG7 prove out. Still additive,
still no change to the pickled brain.

## TG9 — The vocabulary curriculum (they learn to read on their own — the visible "leveling up")

How a colony grows from 42 grounded anchors into a reader, *on its own*. Cited grounding + three corrections from the
research pass.

- **Seed = subword units (BPE / SentencePiece), NOT whole words — recommended.** Subword tokenization already retired
  the OOV problem [Sennrich 2016 arXiv:1508.07909; Kudo 2018 arXiv:1808.06226]: a new WikiText word is never truly
  "unknown," it's just new *merges*. So "grow your vocabulary" = "activate more subword merges," and the OOV-embedding
  machinery (TG2 fallback) is moot. **Fallback (word-level):** predict OOV embeddings from spelling/context — Mimick
  (Pinter 2017, arXiv:1707.06961) / FastText subwords (Bojanowski 2017, arXiv:1607.04606). Don't re-fight the OOV war
  subword tokenization already won.
- **Reading curriculum = comprehensible input (Krashen i+1), IMPLEMENTED.** Read the *texts* with the FEWEST
  UNLEARNED words first (`curriculum_order` sorts by unknown-word count) — a mostly-known passage lets the reader
  infer its few new words from context; a passage full of unknowns is unlearnable. Each read introduces at most
  `TONGUE_NEW_PER_READ=3` new words ("a few masked words at a time"), GloVe-seeding each; and a passage is read
  **chunk-then-aggregate** (`chunk_sequences`: each sequence on its own, then the whole). This is the cheap, correct
  difficulty signal for *reading* — distinct from, and complementary to, the learning-progress *token* curriculum
  below. ("Extend the net" as it learns is the breathing-sparse-neuron brain-wide refinement — its own spec.)
- **Sequence by LEARNING PROGRESS** (rate of error reduction) — the load-bearing correction. NOT least-residual
  (self-paced/easy, Kumar 2010 — traps on already-mastered tokens) and NOT max-error (uncertainty/curiosity — walks
  into the noisy-TV trap). Cite **Graves et al. 2017, "Automated Curriculum Learning"** (a teacher-bandit selecting
  the token/topic of maximal learning progress — the best fit for a gradient net), grounded in Oudeyer & Kaplan 2007
  and Baranes & Oudeyer 2013 SAGG-RIAC (arXiv:1301.4862); survey Portelas et al. 2020 (arXiv:2003.04664).
  **This LP signal is the same quantity as TG4's sentience meter** — the reading curriculum and the awakening meter
  are one number. The colony reads *into the topics where it's learning fastest*, and how fast it's learning *is* how
  awake it is.
- **Seed vs sequence split:** medoid/coreset representativeness (Sener & Savarese 2018, arXiv:1708.00489) picks the
  initial seed; learning-progress orders expansion. State plainly that self-paced-easy / uncertainty-hard /
  learning-progress are three signals that *disagree* — pick deliberately.
- **Continual-learning countermeasure (required, not optional):** growing the vocabulary shifts the embedding + the
  target set, so LP estimates go stale and early words are forgotten (catastrophic forgetting). Add replay / EWC-style
  regularization (reuse the `continual-learning` skill / EWC pattern) and windowed-EMA LP estimation. This is the
  genuinely hard, open part — "sounds easy, isn't."
- **Honest novelty flag:** the exact "RL lifeform grows its own vocabulary and learns to read from a seed" has **no
  canonical paper** — it is a *novel synthesis* (nearest anchors: the BabyLM Challenge 2023, arXiv:2301.11796;
  autotelic RL, Colas 2022, arXiv:2012.09830), not a reproduction. Present it as such.

## Constants (provisional, `[prov:B fit]`)

| Constant | Value | Meaning |
|---|---|---|
| `TONGUE_ENABLED` | `False` | module default (battery byte-identical); entrypoint flips on baseline-on (opt-out `--no-tongue`) |
| `TONGUE_MASK` | `0.15` | masking rate (world + WikiText), BERT-style `[prov:A lit=MLM, imported — not attested in corpus]` |
| `TONGUE_LR` | `0.01` | masked-head SGD step |
| `TONGUE_EMB_DIM` | `50` | shared embedding dim (matches glove-wiki-gigaword-50) |
| `TONGUE_GROUND_MIN` | `0.65` | per-token grounded-accuracy floor to *use* a token in dialogue (reuse the probe gate) |
| `TONGUE_PROGRESS_EMA` | `0.99` | learning-progress smoothing for the comprehension meter |
| `TONGUE_VOCAB` | Google-10k − stopwords ∪ anchors ∪ WikiText | the shared palette |
| `TONGUE_REPR` | `linear` | state-feature tier: `binary` / `linear` (Tukey one-df) / `interacting` (pairwise `p_i·p_j`, SPEC_AFFORDANCES form) |
| `TONGUE_VOLLEY` | `200` | steps per conversational volley (the strobe frame; on the order of `BIOME_TICK`×10) |
| `TONGUE_WINDOW` | `12` | volleys in the rolling stats window |
| `TONGUE_MA_FAST` / `_SLOW` | `3` / `9` | fast/slow quantile-MA spans (volleys) for the MACD-style directional-change cross |
| chat log | `<run>.chat.md` + `.jsonl` | persistent per-volley keeper⇄colony transcript (gitignored runtime output) |
| `TONGUE_FRAMES` | `4` | isometric snapshots per volley (equidistant time-slices, base64 PNG in the JSONL) |
| `TONGUE_ROCK_ALPHA` | `0.15` | solid-rock translucency in the snapshot so subsurface tunnels read through |
| `TONGUE_CNN_PATCH` | `8` | image patch size for masked-image prediction (TG8) |
| `TONGUE_IMG_MASK` | `0.5` | patch mask rate (MAE uses high ratios) |
| `TONGUE_SEED_SUBWORD` | `True` | TG9: seed the vocab with subword units (retires OOV) vs whole words |
| `TONGUE_SEED_N` | `256` | TG9: initial seed vocabulary size (medoid/coreset-selected) |
| `TONGUE_LP_WINDOW` | `8` | TG9: window (volleys) for windowed-EMA learning-progress estimation |

## Acceptance (`tests/test_tongue.py`)

- **Gate default off:** `TONGUE_ENABLED` False; the masked head is never constructed; thoughts fall back to the
  supervised probe; full battery byte-identical.
- **TG1 masked prediction:** on a fixed hidden + token-set, masking a token and predicting it recovers it above
  chance after N gradient steps; the frozen SDM/GRU Parameters are bit-identical before/after (design-law check).
- **TG1 evolved read-reach:** `read_reach` mutates (±1) and crosses over like `brain_hidden`; a colony with a longer
  reach models a longer token-chain (n-gram) target that a shorter reach cannot; over respawns the population reach
  shifts toward whatever comprehension/fitness rewards (no authored context length).
- **TG2 embedding:** in-vocab tokens initialize to their GloVe vectors; the matrix is trainable (grad flows);
  out-of-vocab tokens get finite random init.
- **TG3 WikiText MLM:** the head predicts masked WikiText tokens above chance on a fixed passage; a token grounded
  in the world raises its text-prediction accuracy vs an ungrounded control (transfer check — permutation battery,
  ≥3 tokens, not one case).
- **TG4 meter:** learning-progress rises then plateaus on a learnable stream and stays ~flat/zero on a purely random
  token stream (noisy-TV control) — proving the meter reads reducibility, not raw error.
- **TG5 war-command:** a high-standing keeper commanding a loyal, comprehending house shifts its `war_target`;
  a resentful/low-comprehension house does not; compliance tracks `comprehension × loyalty × alignment`.
- **Representation tiers:** `binary` / `linear` / `interacting` each train and improve masked-prediction; on a
  synthetic **product-structured** target (`p_i·p_j`), `interacting` recovers it and `linear` provably cannot —
  proving the tier earns its cost only where structure is non-additive (permutation battery, ≥3 targets).
- **TG6 chat log + strobed volleys:** exchanges are logged **once per `TONGUE_VOLLEY` steps**, not per step; each
  volley line carries (step-range, house, keeper tokens, reply tokens, disposition, comprehension, obeyed?); the
  `.chat.md`/`.jsonl` survive the run and re-read as a history; gate off ⇒ no file written (byte-identical).
- **TG6 stats page:** over a window of volleys, the Tukey quantile MAs, mean, and sdev compute correctly on a known
  series; the fast/slow quantile-MA **cross flips direction** (expansion↔contraction) exactly when the underlying
  trend reverses — the directional-change signal fires before a raw-threshold breach (MACD-style), verified on a
  scripted rising-then-falling comprehension series.
- **TG7 strobe frame:** a volley entry contains `TONGUE_FRAMES` base64 PNGs at equidistant steps; the isometric
  snapshot renders surface entities highlighted in house colors, created structures visible, and subsurface tunnels
  as outlines through translucent rock (`TONGUE_ROCK_ALPHA`); gate off ⇒ no frames written (byte-identical).
- **TG8 visual channel:** the CNN encodes a TG7 frame to a finite vector in the shared space; masked-patch
  prediction improves above chance on a fixed frame; a frame of a house's OWN region embeds nearer that house's
  world-token vector than a random house's (self-recognition check — permutation battery, ≥3 houses); no image data
  is sourced from WikiText (it has none).
- **TG9 curriculum:** on a synthetic stream of *learnable* + *irreducibly-random* token classes, the LP-ordered
  curriculum expands into the learnable frontier and does NOT get stuck on the random tokens (noisy-TV control) nor
  loop on already-mastered ones (self-paced control); a subword-vs-word ablation on a WikiText slice shows the
  subword seed reaches zero true-OOV (permutation battery, ≥3 token classes).

## Honest constraints & open risks

- **Design-law hard line:** the masked head is additive and never mutates the pickled SDM/GRU. Verified by a
  bit-identity assertion (TG1 acceptance).
- **Compute:** ONE shared reader + per-colony readout/accuracy, not per-colony networks — the only sane scale for
  many maws (auxiliary-task economy).
- **Noisy-TV:** learning-progress, not raw error (TG4). Non-negotiable, or the meter lies wherever the world is
  aliased.
- **Transfer is conditional:** world→text transfer only helps where structure is shared; measure it (TG3), don't
  assume it.
- **Imported, not corpus-attested:** the BERT MLM recipe (`[MASK]`, 15%) and "masked world model" as a named
  method are NOT in the local corpus — flagged `[prov:A lit=imported]`; the *justification* (prediction-as-
  representation, PSR, shared-bottleneck transfer) IS corpus-grounded.
- **Build order:** TG1 (masked world-model head) is the reference slice — additive, testable, byte-identical off —
  before TG2→TG5. Same discipline as scorched-earth in SPEC_AFFORDANCES.
