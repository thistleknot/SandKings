# Progress — objective tracking over time

Format: **feature → timestamp → progress description** (newest first per feature).
Objectives defined in `objective.md`. Dates are absolute.

---

## RL v2 upgrade (RLOO + entropy + warm-start + plasticity-LR + verticality + kills-reward)

- **2026-07-14 (Bundle 4 + erosion study, measured)** — richer raw obs (35→39-d: +kills, at_war, wood,
  **seasonal phase**), reducing random-Kanerva dependence. Measured (1700-step): I1 **+0.0158 (up from
  +0.004)**, colonies healthier (pops 25–30 vs a pop-1 near-death prior), I2 0.603, G5 0.908, dreams
  {1,1,1,1}, no NaN; 50/50 battery. **Erosion study (30k steps, 74 maw updates on the longest-lived
  colony): drift FLAT (0.113→0.117), reward level ROSE, `erosion_detected: false`** → the held
  anti-erosion anchor is closed as UNNECESSARY (empirically no chess-style erosion; web-council recon).
- **2026-07-14 (Bundle 3, measured)** — dreaming / elite-replay consolidation (Lin 1992 / S4). The maw
  banks lifetime (obs,directive,reward) memories; on Chill it self-distills its top-8 by reward (BC on the
  mean, log_std untouched) — "distillation > self-play" (chess). Wired to the existing Chill dream hook.
  **Live-run bug fixed** (stale autograd graph: BC mutates weights while PG log_probs pending → drop the
  partial PG batch first; regression test added). Measured (1700-step): dreams={1,1,1,1} (fires per Chill),
  I1 +0.004, I2 0.615, I5 1.248, G1 4/4, G5 0.968, no NaN. 25 unit + 2 integ + 50 battery green.
- **2026-07-13 (Bundle 2, measured)** — `patience` gene → discount γ∈[0.80,0.97] + n-step returns
  shipped (`maw_brain._discounted_returns`/`patience_to_gamma`, wired in `_maw_rl_tick`; chess λ≈0.9
  interior prior). Measured (1500-step): I1 +0.011, **I2 0.665 ↑, I5 1.284 ↑**, G1 4/4, G5 0.968, no
  NaN; 20 unit + 2 integ + 50 battery green. No regression; divergence & anti-collapse improved.
  patience→territory A/B not resolvable at 1500 steps (territory≈1) — deferred to a controlled study.
- **2026-07-13 (measured)** — v2 shipped + measured (1500-step, 4-colony neural run, seed 7).
  **All objective metrics PASS**: I1 slope +0.019 (↑), I2 divergence 0.555, I3 expressiveness
  0.297, I5 anti-collapse 1.03× (grew — entropy holds), I4 maw[3,3,3,3]/spawn[448,381,427,376],
  G1 4/4 alive, G3 3.27 events/100, G5 warm-start corr **0.968**, no NaN. Unit 17/17,
  integration 2/2, full battery 50/50 green. Warm-start signature verified per-colony (aggressive
  genomes pushed more aggressive by RL; tunneler stayed tunneler).
- **2026-07-13** — Spec updated + `maw_brain.py` reimplemented. Grounded in S&B §13.4 (baseline
  unbiased), RLOO (small-group), AEPO (entropy-collapse), INSPIRATIONS + chess-deep-q `RL_FINDINGS`
  (never-tabula-rasa / Baldwin / measure-with-deployment / decisive-coverage=kills-reward).
- **HARVESTED (chess-deep-q Codas 5,7 "definitive"):** RL on self-play OUTCOMES *erodes* a sound
  starting point (distillation > self-play). Our maw = outcome-REINFORCE on the sound genome
  instinct → same setup. **Latent risk** (only 3 maw updates in 1500 steps; not yet manifesting).
  Bundle-2 candidate: **anchor/trust-region the maw policy toward its warm-start instinct** so RL
  refines without eroding. λ≈0.9 interior prior for the patience→γ mapping (their `l07`–`l09` models).

## Guppies — oasis pond ecosystem (SPEC_GUPPIES)

- **2026-07-14** — Added a consumer-resource pond seeded in the oasis from world-gen (baseline-ON,
  opt-out `--no-guppies`): algae grows (sunlight/water), guppies eat + **breed** (logistic, food-
  modulated), surplus surfaces as harvestable FOOD voxels colonies forage (a commons; Ostrom). Pure
  `guppy_dynamics` pinned by an 8-test battery (bounded / persists / recovers-after-crash / drought-
  thins / catch-floor + gate-off byte-identical + gate-on lives). Equilibria: ~99 guppies @ water 0.6,
  ~107 @ 1.0 (boom drama in wet seasons), ~86 in drought; catch ~3 food/tick. Full battery 51/51;
  live entrypoint smoke clean.

## Observability — learned personality as drama

- **2026-07-14** — The maw narrates a **strategy shift** when its learned directive crosses an
  archetype (war-drums / burrows-deep / spreads / draws-inward), throttled to transitions, gated.
  Turns the RL's learning into watchable narrative (the "quasi-sentient life" directive).

## Patience→γ A/B (Bundle 2 validation)

- **2026-07-14 (4 seeds: 3,5,9,14; identical instinct, vary ONLY `patience`)** — HONEST result: the
  γ→temperament effect is **directionally present but WEAK and noisy** at the maw's update budget
  (~11–15 updates). aggression gap (impatient−patient): {+0.28, +0.001, +0.07, +0.03} — positive on
  3/4 but small; mobility gap (patient−impatient): {+0.13, −0.05, +0.05, +0.26} — positive on 3/4, one
  reversal. The strong seed-3 run (0.28 aggr gap) was the HIGH end, NOT typical. Reward-level: patient
  colonies end healthier on 2/3 new seeds. **The mechanism works (γ differs → credit assignment differs),
  but the behavioral signal is subtle** — like the near-zero I1, a consequence of the update-limited maw.
  A firm effect would need far more updates (longer runs / smaller batch) or larger n. Not overclaimed.

## Cross-seed robustness (3-seed sweep, seeds 11/22/33 + seed 7)

- **2026-07-14** — I1 reward-trend {+0.019, −0.001, +0.012, −0.004} → **hovers near zero, seed-
  dependent** (honest: the update-limited maw — 3 batch updates/1700 steps — MAINTAINS/slightly grows
  reward, not a dramatic optimizer). I2 divergence {0.40–0.60}, I5 anti-collapse {0.73–1.03}, G5
  warm-start {0.86–0.98}, G1 4/4, no NaN — **all targets hold on every seed**. The RL is robust, not
  seed-lucky; the reward-trend near-zero is the honest ceiling at this update budget.

## Baseline (pre-v2, real-RL 85:15 as shipped)

- **2026-07-12** — 520-step run: maw updates [1,1,1], spawn updates [66,94,107]; 3 colonies
  developed distinct aggression/mobility directives (Nith-Kal 0.42/0.32, Gash-Vrash 0.76/0.47,
  Naud-Szik 0.58/0.41). I2 divergence ~present; entropy/anti-collapse (I5) not yet instrumented.
  Full battery green; no crash. This is the reference the v2 upgrade must beat on I1/I3/I5.

---

### Metric log (append rows as runs are measured)

| date | feature | I1 reward↑ | I2 diverge | I3 express | I5 anti-collapse | G1 alive | notes |
|------|---------|-----------|-----------|-----------|------------------|----------|-------|
| 2026-07-12 | pre-v2 baseline | n/m | ~0.1+ | ~0.15 | n/m | 3/3 | from 520-step log |
| 2026-07-13 | v2 (RLOO+entropy+warmstart+plasticity+vert+kills) | +0.019 | 0.555 | 0.297 | 1.03× | 4/4 | G5 warm corr 0.968; 1500 steps seed7; all targets pass |
| 2026-07-13 | Bundle 2 (+ patience→γ n-step returns) | +0.011 | 0.665 | 0.267 | 1.28× | 4/4 | no regression; divergence & anti-collapse ↑; patience→territory A/B deferred (territory≈1 at scale) |
| 2026-07-14 | Bundle 3 (+ Chill dreaming/elite-replay) | +0.004 | 0.615 | 0.270 | 1.25× | 4/4 | dreams={1,1,1,1}; live-run stale-graph bug fixed; all targets pass |
| 2026-07-14 | Bundle 4 (+ richer raw obs: kills/war/wood/season) | +0.0158 | 0.603 | 0.271 | 1.14× | 4/4 | reward trend ↑; colonies healthier (pops 25–30); G5 0.908; dreams fire |
| 2026-07-14 | erosion study (30k, 74 updates) | level↑ | — | — | drift FLAT | — | erosion_detected=false → anchor NOT needed (closed) |
