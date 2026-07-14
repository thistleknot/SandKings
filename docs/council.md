# Web-Council Ledger — drq maw/spawn RL

**Accepted-arm hit rate:** overall 1/1 (1 scored) · critique n/a (held→resolved) · pipeline n/a (vetoed)
· next-question 1/1. Rounds convened at RL verdict/plateau/novel-territory forks. Protocol:
`.claude/skills/web-council`.

### Reconciliation — 2026-07-14 (erosion study resolved the round-1 open items)
Ran the erosion study (`scratchpad/erosion_study.py`, 30k steps, longest-lived colony = **74 maw
updates**): drift-from-instinct FLAT (0.113→0.117, slope +0.0001/update), reward LEVEL rose
(19.4→20.4), `erosion_detected: false`.
- **Proposal C (next-question, the reframe) → HIT.** Predicted the GA/Baldwinian reset means no
  chess-style erosion; the study confirms no erosion even for a long-lived colony. Lesson (reinforce):
  when importing a lesson from another repo, first check the *architectural precondition* that made it
  true there (chess: one persistent net, no reset) still holds here — it didn't.
- **Proposal A (critique, the anchor) → RESOLVED, not needed.** Its unblock condition (a long-lived
  dominant colony drifting from instinct with declining reward) was tested and did NOT occur. Holding
  rather than building was correct. Bundle 3's dreaming adds a soft self-distillation anti-erosion pull
  anyway. Anchor closed as unnecessary; reopen only on new evidence.

## Lens briefs (evolving)

- **Critique** — "What is the weakest load-bearing assumption in what we're doing right now, and
  what would the literature say?" One falsifiable critique + the refuting search.
- **Pipeline-restructure** — "If the pipeline were the tunable program, which stage to recompose,
  reorder, or re-target?" One change + prior-art search.
- **Next-question** — "Which question, if answered, most changes the plan?" The highest-info query,
  run immediately.

---

## Round 1 — 2026-07-13

**Context:** RL v2 shipped + measured (all objective metrics pass: I1 +0.019, I2 divergence 0.555,
G5 warm-start corr 0.968, 4/4 alive, entropy anti-collapse 1.03×). Design: REINFORCE + RLOO baseline
+ entropy, warm-started from genome instinct, plasticity→LR, kills-reward, under the GA. Open question:
add an anti-erosion anchor now (chess-deep-q RL_FINDINGS: self-play OUTCOME-RL "definitively" erodes a
sound warm-start) or prioritize patience→γ / dreaming?

### Proposal A — Critique: add a KL/anchor penalty toward the warm-start instinct NOW
- **Refutation query:** "KL penalty to reference policy unnecessary or harmful RLHF trust region warm-start negative results."
- **Result:** refutation FAILED — KL-to-reference is pervasive and principled ("prevents reward hacking...
  without that anchor, policies collapse onto high-scoring gibberish within a few hundred PPO steps";
  Bayesian justification). Caveat (Catastrophic Goodhart, arXiv:2407.14503): KL does NOT save you under
  **heavy-tailed** reward error — but suffices for light-tailed error. drq's reward is bounded/light-tailed.
- **Verdict: HELD.** Sound and cheap, but not urgent given Proposal C. Unblocks when a **long-lived
  dominant colony** shows directive drift away from its instinct across >20 updates with declining reward.
- **Scoreable prediction (if later accepted):** adding an L2/KL anchor(coef≈0.01) to warm-start keeps a
  1M-step dominant colony's |directive−instinct| bounded while I1 stays ≥0.

### Proposal B — Pipeline: recompose the hand-weighted reward into potential-based (policy-invariant) shaping
- **Refutation query:** "potential-based reward shaping limitations failure modes practical problems."
- **Result:** refutation SUCCEEDED — PBRS effectiveness "depends on accuracy of the potential estimates,"
  flat/ineffective under sparse-delayed reward, and has **multi-agent failure modes** (non-stationarity
  violations, coordination-reward misalignment; arXiv:2511.00034) — precisely drq's non-stationary
  multi-colony setting. No evidence the current reward is the bottleneck (I1 +0.019, colonies growing).
- **Verdict: VETOED** (Simplicity-First; multi-agent PBRS failure modes; current reward works). Protocol success.

### Proposal C — Next-question: does the outer GA already self-correct inner-RL erosion? (the reframe)
- **Refutation query:** "evolutionary outer loop fails to correct within-lifetime learning drift Baldwin
  Lamarckian instability population-based training."
- **Result:** No evidence the outer loop FAILS. Baldwin is "purely Darwinian — acquired characteristics
  are NOT directly inherited"; "best performance is Baldwinian... Lamarckian is a very clear loser."
  **Verified in code** (`sandkings.py:6957-6958`): colony death → a fresh `Colony(...)` → `_maw_rl_tick`
  builds a NEW maw_rl warm-started from the evolved genome. The eroded within-lifetime RL is **not
  inherited**; the sound genome is. drq is Baldwinian — the erosion-reset chess-deep-q lacked.
- **Verdict: ACCEPTED (reframe, no arm).** The chess erosion lesson was imported wholesale from a
  single-persistent-net-no-reset setting; drq resets each colony's RL to the sound point on respawn, so
  **erosion is bounded to one colony lifetime and self-corrects at the population level.** This de-biases
  the plan: the anchor drops from "urgent" to "held insurance."

**Round disposition (agent decides):** Anchor = HELD (not urgent — the GA handles it; residual risk =
long-lived dominant colonies only). PBRS = VETOED. **Next arm = `patience` gene → discount γ + n-step
returns** (Sutton&Barto T26; S&B §13.4 return carries γ; chess-validated λ≈0.9 interior, their `l07`–`l09`
models) — adds temporal temperament (patient colonies value long-horizon growth) = intelligence + visible
personality. **Mis-framing corrected:** over-trusted chess's no-outer-loop erosion; drq's Baldwinian GA is
the correction chess didn't have.

**Round quality:** not low-information — one veto (B) and one plan-changing reframe (C). Discovery ✓.
