# Objective — Sand Kings brain (RL under GA)

**North star:** *balance colony intelligence with gameplay experience.* Not loss curves —
outcomes (INSPIRATIONS chess `RL_FINDINGS`: "judge the agent by outcomes, not loss curves").

This file defines the objective functions we track. It is freely updated as the objective
sharpens. Time-stamped measurements live in `progress.md`.

## The blended objective

```
J = w_I * Intelligence + w_G * Gameplay        (w_I = w_G = 0.5 for now)
```

Both sub-scores are in [0,1]; higher is better. We do NOT collapse to one number blindly —
we watch the components, because a high J with a dead component is a failure.

## Intelligence metrics (is the RL actually learning + individuating?)

| id | metric | how measured | target |
|----|--------|--------------|--------|
| I1 | **reward trend** | mean per-colony maw reward, last-quartile vs first-quartile of a run | up (>0 slope) |
| I2 | **directive divergence** | mean pairwise L2 distance between colonies' final directive vectors | ≥ 0.15 (colonies differ) |
| I3 | **expressiveness** | mean \|directive − 0.5\| across colonies (are they taking positions?) | ≥ 0.10 (not stuck neutral) |
| I4 | **learning liveness** | maw updates > 0 AND spawn updates > 0 for surviving colonies | all surviving learn |
| I5 | **anti-collapse** | directive divergence (I2) at end ≥ 0.6× its mid-run value (no collapse to sameness) | ≥ 0.6× |

## Gameplay metrics (is it alive, varied, and watchable?)

| id | metric | how measured | target |
|----|--------|--------------|--------|
| G1 | **no heat-death** | ≥ 2 colonies alive at end of a 600-step run | ≥ 2 alive |
| G2 | **population breathing** | population is non-constant across the run (min ≠ max) | varies |
| G3 | **drama** | drama-feed events emitted per 100 steps | ≥ 1 / 100 |
| G4 | **behavioral variety** | distinct dominant-action mix across colonies (not all doing the same thing) | ≥ 2 distinct profiles |
| G5 | **personality-from-start** | warm-started directive correlates with genome instinct at step ~50 (never tabula rasa) | corr > 0 |

## Guardrails (hard gates — a fail here voids the run)

| id | guard | check |
|----|-------|-------|
| Q1 | **battery green** | `run_tests.py` exit 0 with gate default-off (byte-identical) |
| Q2 | **no NaN / crash** | a 600-step headless run completes, no RuntimeError/NaN in directives |
| Q3 | **perf budget** | wall-clock per 100 steps within the fast-iteration budget (small sims) |
| Q4 | **GA preserved** | neuroevolution path untouched; evolution suites green |

## Measurement protocol

- Small headless run (fast-iteration budget: width≈48 height≈32 depth≈12, 4 colonies, ≤600 steps).
- Parse the run's directive logs / summary for I1–I5, G1–G5.
- Record one dated row per feature in `progress.md` (feature → timestamp → progress description).
