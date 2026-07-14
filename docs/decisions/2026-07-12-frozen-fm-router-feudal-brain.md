# Decision: Real-RL 85:15 maw/spawn brain (under the GA)

Date: 2026-07-12. Status: **ACCEPTED + IMPLEMENTED** (commits 8518429 → a200225).
Supersedes the earlier "frozen foundation-model router / feudal" design in this file's
git history (see "Design history" below — that whole direction was explored and dropped).

## What this is

A real **deep-RL** brain for the Sand Kings, layered **UNDER the existing GA**
(neuroevolution): within a lifetime colonies learn by RL; across generations the GA still
evolves genomes/brains (mutate/mate/graft/sexual-respawn — untouched). No LLM, no foundation
model, no 7 GB weights — those were explored and dropped. Honours the DRQ lineage
("neural nets + word2vec + deep-RL"). Everything is **gated + identity-at-neutral** so the
regression battery stays byte-identical; the game turns it on baseline.

The 85:15 compute split is realized: the maw (85%) is the strategic learner, the spawn (15%)
the local learner, on two clocks.

## Architecture

### Maw — 85% tier, batch clock (`maw_brain.MawPolicy` / `ColonyMawRL`)
- A small **gradient-trained Gaussian policy** (REINFORCE) that emits a colony **directive** —
  6 continuous constants in (0,1). `MawPolicy.act` samples a directive + log_prob; `.update`
  is batch-REINFORCE with a **batch-mean baseline / whitened advantage**.
- **Obs** = mean of the colony's frozen-encoder outputs (`_colony_encodings`, 32-d) ++ colony
  **state** `[pop, food, territory]` (3) = **35-d** → the directive is state-responsive.
- `ColonyMawRL` is the two-timescale wrapper: `act` each cycle, `observe_reward` (survival/
  dominance delta) for the previous directive, flush an update every `MAW_UPDATE_EVERY=8`
  cycles. Rides `POP_TICK_INTERVAL=50`, staggered per colony.
- **Reward** = Δ(`pop + food/50 + territory/100 + 2·maw_alive`).

### Spawn — 15% tier, step clock (`maw_brain.SpawnResidualPolicy` / `ColonySpawnRL`)
- A **shared per-colony** Gaussian policy → a **bounded** (±`MAW_RESIDUAL_CLIP=0.15`) additive
  action-logit **residual**; last layer zero-init so the deterministic residual starts at
  **identity**. Shared weights ⇒ batchable (distinction lives in each spawn's encoding, not
  weights).
- `ColonySpawnRL` applies the residual per spawn, books each spawn's **local performance delta**
  (`SoldierLayer.get_performance_score`) as reward, flushes every `SPAWN_UPDATE_EVERY=32`
  spawn-steps. Drops stale pending log-probs on update (fixes a cross-step autograd bug).

### Loop closure (`apply_directive`, `apply_residual`, `sandkings._maw_rl_tick`)
- `_maw_rl_tick` (batch clock, in `step()`): builds obs, books reward, acts → `colony.maw_directive`.
- In the neural soldier path: **`apply_directive`** tilts the action (d0 aggression → ATTACK,
  d1 mobility → MOVE actions; **identity at the neutral 0.5**), then **`apply_residual`** adds the
  spawn's bounded play. So directive → behaviour → survival → reward closes the loop.

### "Frozen" = between batches (the trick)
Weights are held fixed **during a rollout**, updated **at the batch boundary** — standard
two-timescale batched RL, not a permanently-frozen net. The Kanerva/ZCA encoder is a fixed
feature basis feeding the obs; it is **not pretrained** (a random projection + online whitening),
an acknowledged limitation — see "Open / future".

### Stability (`_reinforce_update`)
Shared batch-REINFORCE for both tiers: batch-mean baseline, **gradient clipping**
(`MAW_GRAD_CLIP=1.0`, default) or opt-in **signSGD** (`MAW_SIGN_SGD`, sign-quantized gradient),
read from module globals at call time.

### Gating / identity-at-neutral
`MAW_RL_ENABLED` module default **False** (battery byte-identical; the tick returns immediately,
draws no python/numpy RNG — only torch RNG when on). The game flips it on **baseline** unless
`--no-maw-rl` (needs neural). Registered in `run_tests._GATE_NAMES`.

### Observability
On each maw update: `HOUSE maw learns: aggr=X mob=Y (upd N, loss L)` in the drama feed
(`sim.events`), so the player watches the 85% tier train and colonies diverge.

## Files
- `maw_brain.py` (new) — `MawPolicy`, `ColonyMawRL`, `SpawnResidualPolicy`, `ColonySpawnRL`,
  `apply_directive`, `apply_residual`, `_reinforce_update`; constants `MAW_*`/`SPAWN_*`.
- `sandkings.py` — `MAW_RL_ENABLED` gate, `_maw_rl_tick`, the gated directive+residual in the
  neural path, entrypoint baseline enable, `dynamic_population` old-checkpoint compat.
- `neural_hive.py` — frozen ZCA/Kanerva encoder + `_colony_encodings` batching (Phase 0a) +
  z-norm fix; the evolutionary `HiveMindBrain`/`SoldierLayer` (the GA base) are unchanged.
- `run_tests.py` — `MAW_RL_ENABLED` in `_GATE_NAMES`.
- `tests/test_maw_rl.py` (14 unit tests), `tests/test_maw_integration.py` (gate-off identity +
  gate-on in-sim).

## Verification (done)
- Unit: both policies + wrappers converge on toy objectives; signSGD converges; bounded/identity;
  pickle-safe; the cross-update autograd repro passes.
- Integration: gate-off = no maw/spawn state (identity); gate-on sets directives + spawn RL runs.
- Full battery **green** (exit 0) at each commit. Live 520-step run: maw updates [1,1,1], spawn
  updates [66,94,107], three colonies developed **distinct** aggression/mobility directives.

## Preserved
The **GA / neuroevolution is intact** — RL is additive and gated, a within-lifetime layer under
the across-generation GA. Not to be removed.

## v2 RL upgrade (2026-07-13) — SOTA estimator + GA↔RL coupling

Grounded in **S&B §13.4** (REINFORCE-with-baseline: an action-independent baseline is unbiased
and variance-reducing; the canonical return carries γ; the policy step-size is problem-dependent),
2024-25 **RLOO** (leave-one-out baseline, unbiased, best in the small-group regime — our maw batch
is K=8), the **entropy-collapse** literature (AEPO 2510.08141: on-policy entropy declines
monotonically → premature deterministic collapse), and the **INSPIRATIONS** design laws
(chess `RL_FINDINGS` "never tabula rasa, small & inspectable"; Sutton&Barto "γ = patience gene";
Baldwin "LR = plasticity gene").

- **RLOO leave-one-out baseline** (`_reinforce_update`, `MAW_RLOO=True`): advantage_i = r_i −
  mean(r_{j≠i}). Unbiased (S&B §13.4), lower-variance than the old GRPO-style mean/std whitening at
  K=8. Whitening retained as the K≤1 / opt-out fallback.
- **Entropy bonus** (`MAW_ENTROPY_COEF=0.01`): `loss -= coef·H(policy)`, H the diagonal-Gaussian
  differential entropy (a function of `log_std` only). Sustains exploration so **colonies keep
  diverging over a long game** instead of collapsing to one strategy — a gameplay requirement
  (the "pet you check on across days"). Applied to both maw and spawn policies.
- **Warm-start from genome instinct** ("never tabula rasa"): `MawPolicy(warm_start=…)` sets the final
  layer to **zero weights + bias=logit(instinct)** so the untrained deterministic directive **equals
  the colony's genome instincts**, not neutral 0.5. Map: d0←`aggression`, d1←`expansion_rate`,
  d2←`tunnel_preference`. Colonies express personality from step 1; RL modulates from there.
- **`plasticity` gene → learning rate** (Baldwin): `ColonyMawRL(lr=MAW_LR·(0.5+genome.plasticity))`.
  The GA's evolved learning-speed gene now actually sets the RL step size — learning and evolution
  couple. (S&B: α^θ is the hard, problem-dependent knob → let selection tune it.)
- **3rd directive lever = verticality** (`MAW_DIRECTIVE_DIM` 6→**3**, killing dead capacity, honoring
  "small & inspectable"): `apply_directive` d2 tilts the vertical moves (idx 4,5: ±z) vs planar,
  identity at 0.5. Colonies that tunnel-down vs hold-surface become visibly distinct in the z-slice.
- **Richer reward** — colony **kills delta** added to the maw reward snap (`+0.5·Σ unit.brain_layer.kills`),
  so the 85% tier learns that winning fights (not only pop/food/territory) pays.

Gate unchanged (`MAW_RL_ENABLED` default False → battery byte-identical). Directive-dim reduction is
forward-safe: old checkpoints keep their 6-d policy (recreated only on obs-dim change); new colonies
get the 3-d warm-started policy.

### Bundle 2 (2026-07-13) — `patience` gene → discount γ + n-step returns
Each maw directive is now credited by its **γ-discounted downstream return** over the rollout buffer
(`_discounted_returns`, S&B §13.4: the REINFORCE return carries γ), then RLOO-baselined — not just the
immediate next-cycle delta. `patience_to_gamma` maps the evolved `patience` gene (0..1) into an
**interior band γ∈[0.80, 0.97]** (never 0 or 1 — chess-deep-q found the interior λ≈0.9 the sweet spot,
their `l07`–`l09` models). Patient colonies weight long-horizon territory/pop growth; impatient ones
chase immediate gains — Sutton&Barto's "γ = temperament" made literal. Wired in `_maw_rl_tick`
(`gamma=patience_to_gamma(genome.patience)`); spawn (fast reactive tier) stays immediate-reward.

**The anti-erosion anchor is intentionally NOT built** (web-council round 1, `docs/council.md`): the
chess "self-play erodes the sound point" lesson was imported from a single-persistent-net-no-reset
setting, but drq resets each colony's RL to the sound genome instinct on **respawn**
(`sandkings.py:6957` builds a fresh `Colony` → fresh warm-started maw_rl) — Baldwinian, the erosion-reset
chess lacked. Anchor held as insurance for long-lived dominant colonies only.

### Bundle 3 (2026-07-13) — dreaming / elite-replay consolidation (Lin 1992, INSPIRATIONS S4)
The maw banks a ring buffer (`MAW_DREAM_BUFFER=64`) of its lifetime `(obs, directive, reward)` memories.
On the **Chill season** (once per colony per year, wired into the existing `learner.dream` hook,
`sandkings.py` ~2000, "the maws dream through the long frost"), `ColonyMawRL.dream()` runs **elite
self-distillation**: it takes the `MAW_DREAM_TOPK=8` highest-reward memories and supervised-imitates
them (`MAW_DREAM_EPOCHS=3` BC passes, `MAW_DREAM_LR=1e-3`) on the policy **mean only** — `log_std`
untouched so exploration survives. This is distillation toward the colony's OWN best past, NOT stale
on-policy replay (chess-deep-q: **distillation > self-play**), and it doubles as a soft anti-erosion pull
(consolidating good directives resists drift) and as **sample-efficiency** (the maw is severely
update-limited on the batch clock; replay multiplies each real transition's signal).

Live-run bug fixed (caught by measurement, not unit tests): dreaming's BC step mutates the policy weights
inplace, so any pending on-policy PG log_probs sampled under the pre-dream weights had **stale autograd
graphs** — `dream()` now drops the partial PG batch first (mirrors the spawn stale-pending fix). Regression
test `test_dream_mid_pg_batch_no_stale_graph`. Verified: 25 unit + 2 integration + 50 battery green;
1700-step run dreams={1,1,1,1}, all objective metrics pass, no NaN.

## Open / future (Bundle 4+)
- **Anchor / trust-region toward warm-start** (HELD): only if the erosion study shows a long-lived
  dominant colony drifting from its instinct with declining reward. Note Bundle 3's dreaming already adds
  a soft self-distillation anti-erosion pull, so an explicit anchor may prove unnecessary.
- **Drop the random-Kanerva dependence:** re-point RL obs to **raw** state (learned features, frozen
  only between batches); self-supervised encoder pretrain.
- **Controlled `patience`→γ A/B:** a genome-controlled study to confirm patient colonies develop more
  long-horizon (territory/pop) behavior than impatient ones (not resolvable at 1500-step scale).

## Design history (explored + dropped — full reasoning in git history)
- **Frozen foundation-model router (TabFM/TabPFN):** dropped — 7 GB/model, Prior-Labs login gate,
  overkill for small regression/scoring, representation friction. (`get_embeddings` API exists but
  not worth it.)
- **LLM (Qwen) + TextGrad manager tier, pheromone thought-tags, regional-consensus polls, grounded
  directives, 3-tier feudal, manager two-head refiner:** shelved — strayed from the deep-RL origin;
  RL + GA is the core. Available as future polish, never a dependency.
- **Pre-prescribed formula registry:** an intermediate pivot from TabFM, also dropped in favour of
  learning the policy directly.
