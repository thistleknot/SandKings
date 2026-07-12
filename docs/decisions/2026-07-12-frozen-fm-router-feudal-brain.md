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

## Open / future
- **Drop the random-Kanerva dependence:** re-point the RL obs to **raw** state so the nets learn
  their own features (frozen only between batches). Offered, not yet done.
- **"Start intelligent":** behavior-clone the rule-based instincts into the base policy (warm start),
  and/or self-supervised encoder pretraining (learned frozen basis).
- **Richer reward / more levers:** kills/deaths, threat-in-obs, more directive dims — the reward is
  the research tail (tuning turns "the RL runs" into "the RL visibly improves").

## Design history (explored + dropped — full reasoning in git history)
- **Frozen foundation-model router (TabFM/TabPFN):** dropped — 7 GB/model, Prior-Labs login gate,
  overkill for small regression/scoring, representation friction. (`get_embeddings` API exists but
  not worth it.)
- **LLM (Qwen) + TextGrad manager tier, pheromone thought-tags, regional-consensus polls, grounded
  directives, 3-tier feudal, manager two-head refiner:** shelved — strayed from the deep-RL origin;
  RL + GA is the core. Available as future polish, never a dependency.
- **Pre-prescribed formula registry:** an intermediate pivot from TabFM, also dropped in favour of
  learning the policy directly.
