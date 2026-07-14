# Progress — objective tracking over time

Format: **feature → timestamp → progress description** (newest first per feature).
Objectives defined in `objective.md`. Dates are absolute.

---

## RL v2 upgrade (RLOO + entropy + warm-start + plasticity-LR + verticality + kills-reward)

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
