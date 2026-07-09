# Spec: Hive Mind Monitor (concept probes, thoughts, manager screen)

Layer: **Requirements** + **Structural** (new module `hive_mind_monitor.py`,
manager screen in `live_view.py`). Governs: the concept lexicon, probe
learning, thought generation, decision logging, and the manager screen.
Status: draft → implement → reconcile (log at bottom). IDs M1-M8.

## 1. Intent

Make the little guys legible: per-unit stats, a manager view of each
colony, and human-readable "thoughts" that are honestly grounded — decoded
from the soldier's recurrent hidden state by linear probes whose accuracy
against measurable ground truth is always shown. A concept is only claimed
as a thought when its probe demonstrably reads it from the mind.

*Method rationale:* linear probes over hidden states are the standard
interpretability tool; the ground-truth predicates supply supervised
signal, so "what correlates" is learned online without RL machinery.
Expression vocabulary comes from real word embeddings (M9): each anchor
concept fans out to a cluster of common-English neighbors derived from
GloVe vectors at build time — the embeddings shape how thoughts *read*,
while the probes decide what is *true*. WordNet was skipped (a dependency
with no ground truth).

## 2. Implementation Requirements

- New module `hive_mind_monitor.py`: numpy only (hidden states arrive as
  numpy arrays; no torch, no pygame).
- Constant: `PROBE_LR = 0.05` — online logistic-regression step size.
- Constant: `PROBE_ACC_DECAY = 0.99` — accuracy EMA horizon.
- Constant: `THOUGHT_MIN_P = 0.6` — decoded probability gate for a thought.
- Constant: `THOUGHT_MIN_ACC = 0.65` — probe accuracy gate: below this the
  concept is not claimed as a thought (the mind is not readable for it).
- Constant: `THOUGHT_MAX = 4` — display truncation only: every anchor
  passing the gates emits (user requirement: multiple simultaneous
  thoughts), the roster line simply truncates to the strongest THOUGHT_MAX.
- Constant: `THOUGHT_CAPS_P = 0.85` — decoded probability above which the
  word renders in CAPS (intensity).
- Constant: `DECISION_LOG_LEN = 30` — per-colony decision entries kept.
- `SandKing` gains a display-only `unit_id` (process-local serial; identity
  for the roster, not a persistence key — ids may repeat after a resume).
- Monitors live on the sim (`sim.monitors: Dict[colony_id, HiveMindMonitor]`)
  and MUST survive pickling with it (T13); a respawned colony gets a fresh
  monitor (new brain, new mind).
- Perf: observe cost is O(units × concepts) numpy dot products per step.

## 3. Functional Requirements

- **M1 (anchor lexicon)** The module MUST define ANCHORS — 20 concepts,
  each a seed word (the M9 cluster key) plus a ground-truth predicate over
  (unit, colony, sim), all measurable per unit per step:

  | Anchor | Ground truth |
  |---|---|
  | food | FOOD voxel within radius 2 |
  | hunger | colony food < 2 × BOOTSTRAP_FLOOR |
  | war | colony.at_war |
  | defense | enemy within foraging_range AND unit within 6 of own maw |
  | underground | unit z < its column's `surface_z` |
  | danger | enemy unit within Manhattan 5 |
  | flee | unit.retreating |
  | hunt | soldier with an enemy within foraging_range, not retreating |
  | wounded | health < 50% of max |
  | home | Manhattan distance to own maw ≤ 5 |
  | feast | CORPSE voxel within radius 2 |
  | buried | ≥ 4 solid voxels among the 6 face-neighbors |
  | crowd | ≥ 3 allied units within Manhattan 3 |
  | alone | no allied unit within Manhattan 6 |
  | rich | colony food > WAR_CHEST |
  | storm | sim.storm_until > sim.step_count |
  | death | ≥ 2 CORPSE voxels within radius 3 |
  | enemy | enemy unit within foraging_range |
  | victory | soldier with ≥ 1 kill (blooded) |
  | siege | enemy Maw within Chebyshev 2 |

- **M2 (probes)** Per colony and concept, a logistic readout of the
  soldier's GRU hidden state (32-d): `p = sigmoid(w·h + b)`. When a neural
  soldier is observed, every probe MUST update online
  (`w ← w − PROBE_LR·(p − y)·h`, y = ground truth) and fold the correctness
  of its thresholded prediction into an accuracy EMA (PROBE_ACC_DECAY).
- **M3 (thoughts)** A neural soldier's thought MUST include EVERY anchor
  whose decoded `p ≥ THOUGHT_MIN_P` with probe accuracy ≥ THOUGHT_MIN_ACC,
  ordered by p descending (display truncates to the strongest THOUGHT_MAX);
  when nothing qualifies the thought is `"..."` (unreadable mind — honesty
  over invention). Each emitted anchor renders as a word from its M9
  cluster: the index scales with p across the cluster (mild neighbor at
  p ≈ THOUGHT_MIN_P up to the seed word near p = 1), and the word renders
  in CAPS when p > THOUGHT_CAPS_P. Any unit (all castes, rule-based
  colonies included) has **instincts**: every ground-truth-active anchor
  rendered by its seed word (same ordering rule, truth is binary so no
  intensity scaling). The manager screen labels which of the two it shows.
- **M4 (decision log)** Each colony's monitor MUST keep a deque
  (DECISION_LOG_LEN) of `(step, actor, event, thought)` capturing outcome
  moments: a unit kills an enemy; a unit dies; the colony declares war;
  a unit lands siege first-blood on a Maw. The thought recorded is the
  actor's cached thought (neural) or instincts (rule-based) at that moment.
- **M5 (manager screen)** When `M` is pressed the viewer MUST toggle the
  manager screen, which replaces the map area while the sim keeps stepping
  (HUD panel and all other keys stay live). While it is open, LEFT/RIGHT
  MUST cycle the inspected colony. The screen MUST show: colony header
  (war state, food, maw HP, population by caste); the concept table
  (name, probe accuracy %, count of units for which it is currently
  ground-truth-active); a roster of the top 8 soldiers by
  `get_performance_score` (unit id, generation, kills, damage dealt/taken,
  steps alive, score, current thought/instincts); and the last 8 decision
  log entries. Content MUST come from a pure function
  `build_manager_entries(sim, colony_id) -> list[(text, color)]` so it is
  headlessly testable.
- **M6 (persistence)** Monitors pickle with the sim and keep learning after
  a resume; `_respawn_colony` MUST drop the dead colony's monitor.
- **M7 (integration)** The sim MUST observe every unit each step it acts:
  neural soldiers via `observe_neural(unit, colony, sim, hidden)` (probe
  update + thought cache), all other units via
  `observe_instincts(unit, colony, sim)` (instinct cache only). Decision
  hooks live where the outcomes happen (`_resolve_conflicts` kills,
  starvation/combat deaths are out of scope for v1 beyond kills, war
  transition, siege first-blood).
- **M8 (honesty)** The manager screen MUST display probe accuracy so the
  user can see which concepts the hive mind demonstrably encodes; thoughts
  are never fabricated from inputs alone for neural soldiers.
- **M9 (vocabulary builder)** `thought_vocabulary.py` (build-time, run
  manually, stdlib + numpy only — no gensim) MUST: download the GloVe
  wiki-gigaword-50 vectors (gensim-data GitHub release asset, ~66MB, cached
  locally); take the first 10,000 frequency-ordered entries as the
  vocabulary; for each M1 anchor's seed word, select up to 5 in-vocabulary
  nearest neighbors by cosine similarity ≥ 0.5, assigning each candidate
  word only to its closest anchor, with a per-anchor blocklist for manual
  pruning; and write `thought_vocabulary.json` as `{anchor: [seed,
  neighbors... ordered mild → seed]}`. The JSON is committed; the game
  reads only the JSON and MUST fall back to `{anchor: [seed]}` clusters
  when the file is missing. When the download fails, the builder MUST emit
  its embedded curated fallback table and say so.

## 4. Structural Spec

```
hive_mind_monitor.py
  CONCEPTS: tuple[Concept, ...]           # M1 lexicon (name, phrase, predicate)
  class ConceptProbe:                     # M2 logistic readout
      predict(h) -> float
      update(h, truth: bool) -> None      # SGD + accuracy EMA
      accuracy: float
  class HiveMindMonitor:                  # per-colony
      probes: dict[str, ConceptProbe]
      thoughts: dict[unit_id, str]        # last cached thought/instincts
      decisions: deque[(step, actor, event, thought)]
      observe_neural(unit, colony, sim, hidden: np.ndarray) -> str
      observe_instincts(unit, colony, sim) -> str
      log_decision(step, actor, event) -> None
      concept_rows(sim, colony) -> list[(name, accuracy, active_count)]
  instincts_for(unit, colony, sim) -> list[str]   # pure

live_view.py additions
  build_manager_entries(sim, colony_id) -> list[(text, color)]   # pure, M5
  LiveViewer: manager_open: bool, manager_colony: int; M/LEFT/RIGHT keys
sandkings.py additions
  sim.monitors lazy dict; observe calls in _execute_unit_ai;
  decision hooks in _resolve_conflicts / war transition / siege first-blood
```

## 5. Acceptance (Given/When/Then)

- (M2) Given synthetic hidden states where a concept's truth is `h[3] > 0`,
  When ~300 observations stream through, Then that probe's accuracy
  exceeds 0.8 (the probe finds the correlation).
- (M3) Given a probe below THOUGHT_MIN_ACC, Then its concept never appears
  in a neural thought even at p = 1.0; Given no qualifying concepts, the
  thought is `"..."`. Given a retreating unit, instincts include "must run!".
- (M4) Given a soldier that kills an enemy in `_resolve_conflicts`, Then its
  colony's decision log gains a kill entry carrying the actor's thought.
- (M5) Given `build_manager_entries` on a running sim, Then the entries
  include the colony header, every concept with an accuracy figure, roster
  rows for soldiers, and decision entries; Given the M key, the viewer
  toggles manager_open; LEFT/RIGHT changes manager_colony (wrapping).
- (M6) Given a pickled/loaded sim, Then monitors, probe weights, and
  decision logs survive and further observes keep learning.

## 6. Reconciliation Log

- (fill in after implementation)
