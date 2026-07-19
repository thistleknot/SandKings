# SPEC — Comprehension drives the RL: the Tongue catalyzes the maw's objective

Status: **I1 + I2(reduced) IMPLEMENTED** (2026-07-18), baseline-ON (gate `COMPREHENSION_RL_ENABLED` default False →
battery byte-identical; entrypoint flips on with the maw-RL). I3/I4 remain FUTURE — they need PER-COLONY heads (see
below). **Couples SPEC_TONGUE (comprehension) → the maw-RL reward** (frozen-fm-router-feudal-brain). The missing
feedback loop: communication/understanding *drives* what and how fast the colony learns, not sit beside it.

**Implemented:** I1 — `sandkings._maw_rl_tick` reward = Δsurvival + need_met·(floor+k)·Δobjective (gated). I2(reduced)
— `TongueSystem.transmit` diffuses comprehension along non-hostile edges (`politics.hostile`), on the volley cadence.
**Floor correction:** the floor is `1/MAW_DIRECTIVE_DIM` (a real structural constant — one directive-dim's share for
an illiterate colony), NOT `BOOTSTRAP_FLOOR` (that is a food quantity, wrong semantics — spec self-corrected).
`need_met` = `food_stored/(food_stored+pop)`, a threshold-free soft food-security ratio (no authored cutoff).

## Why (the keeper's design)

> "our system should enable communication as a driver of improving RL. The level of knowledge understanding (word
> identification is a proxy) should catalyze RL training in terms of the objective function — say collecting more
> resources and maintaining high life based on their prior actions. Real simple heuristic objective."

Right now the Tongue (masked-token comprehension) and the maw-RL (directive policy) run in parallel but don't touch.
This closes the loop: **a colony that UNDERSTANDS its world more gets a stronger, richer learning signal for the
"sophisticated" objective (gather resources, hold territory, keep the brood alive); a colony that understands little
is credited only for bare survival.** Understanding *catalyzes* the pursuit of resources and life. The loop:
comprehension ↑ → reward for resource/life ↑ → maw-RL pursues them → colony thrives → more to communicate →
comprehension ↑. Language grounds and accelerates the RL instead of decorating it.

## The simple heuristic (one line, no magic constants)

Today the maw reward is `Δsnap = Δ(pop + food/50 + territory/100 + kills·0.5 + survival)` (credited to the maw's
PRIOR directive — "based on their prior actions"). The change: **split it into a survival floor (always credited)
plus a comprehension-gated objective (resources + territory + kills)**, with the colony's comprehension `k ∈ [0,1]`
(`TongueSystem.comprehension(colony_id)`, the word-ID/masked-recovery level — the proxy) as the catalyst:

```
survival_term  = Δ(pop + survival)                       # always credited — staying alive is table stakes (NATURE)
objective_term = Δ(food/50 + territory/100 + kills·0.5   # gather + hold + defend
                   + farm_yield + cooperation + resource_efficiency)   # the CIVILIZED objective (NURTURE)
need_met       = basic-need satisfaction in [0,1]        # food security; -> 0 in drought/flood/famine (reuse scarcity state)
reward = survival_term + need_met * (COMPREHENSION_FLOOR + k) * objective_term
```

**Nature > nurture when the shit hits the fan (the Maslow gate — a hard design law).** The comprehension-unlocked
civilized objective is a LUXURY OF PLENTY. `need_met` is basic-need satisfaction (physiological/safety — food
stocked, not starving, not mid-catastrophe), derived from the EXISTING scarcity state (`maw.food_stored`, winter
bite, drought/flood/famine flags — SPEC_SCARCITY_WAR / SPEC_WEATHER), NOT an authored threshold. When
`need_met → 0` (famine, flood, drought) the whole nurture layer collapses: the objective reverts to bare
`survival_term`, the colony feeds itself first and turf-wars over the last food; when `need_met → 1` (plenty),
comprehension + culture unlock farming/cooperation/economy. This same gate suppresses I2 SHARE and treaty/trade
under scarcity — you do not teach irrigation while starving, and geopolitical pressure (proximity + scarcity +
grievance) can keep colonies from EVER reaching cooperative equanimity. Peace is emergent and not guaranteed.

- `k` is comprehension in [0,1]; `COMPREHENSION_FLOOR` is a small floor so an illiterate colony still gets a weak
  objective signal (never zero — the RL must be able to bootstrap comprehension in the first place). Reuse an
  existing floor constant (e.g. `BOOTSTRAP_FLOOR`), do NOT author a new magic number ([[no-authored-threshold-constants]]).
- At `k=0` the colony learns mostly to survive; as `k→1` the objective term is fully weighted → it learns to gather,
  hold, **farm, cooperate, and use resources efficiently**. Understanding literally unlocks CIVILIZED behavior — an
  illiterate colony scrabbles to survive; a literate one farms, allies, and economizes (each term reuses an existing
  sim signal: farm tiles/yield, tribute/alliance acts, food-per-unit efficiency). No new economy — new CREDIT.
- No change to WHAT the maw does (directive → action tilt); only the reward it learns from. Gate off ⇒ the exact
  current `Δsnap` reward (byte-identical).

## Variant (deferred, note only): comprehension → plasticity

A stronger form of "knowledge catalyzes learning": scale the maw-RL learning rate by `k` (understanding → faster
updates). This directly attacks the sample-inefficiency finding ([[frozen-fm-router-feudal-brain]] H2), but it
changes learning dynamics, not just the objective. Deferred to Increment 2; Increment 1 is the reward-shaping above.

## The cultural-evolution loop (staged increments — reuse, don't reinvent; each mouse-gated + overhead-gated)

The comprehension-gated reward (Increment 1) is the FIRST turn of a larger loop the keeper is after: **language as
the carrier of technology and cooperation across colonies.** Each increment grounds in machinery already built and
ships only if it clears the mouse + overhead gates.

- **I1 — Comprehension-gated objective** (above): understanding unlocks the civilized objective (farm/cooperate/
  economize). Reward-shaping only. SHIPPABLE FIRST.
- **I2 — Technology as words (colony→colony transmission), OPTIONAL and DIPLOMACY-GATED.** A colony TRANSCRIBES a
  learned strategy into a FOL triplet (logos — externalizing internal knowledge: `improves(irrigation, yield)`,
  `feeds(farm, brood)`) and MAY speak it; a listening colony that CHOOSES to receive TRAINS on it via
  `MaskedMind.observe_triplet` (SPEC_FOL_TONGUE). Knowledge = a triplet that spreads by being spoken and comprehended
  — "tribal knowledge communicated as technology through words." Reuses the TG6 volley/chat log as the channel.
  **Two hard design laws:**
  - **Speaking is an RL CHOICE, not a reflex.** The maw's directive gains a SHARE channel (reuse an affordance
    channel, no new head) — the maw LEARNS whether to broadcast (reciprocity/alliance payoff) or stay silent (guard
    the edge). Sharing is never forced; a maw can choose isolation.
  - **Hostility breaks the wire.** Transmission flows ONLY along non-hostile diplomatic edges (`politics.hostile`
    False). Enemies have broken-down communications by construction — no shared logos across a war footing. Allies/
    neutrals/trade-partners can exchange; a triplet a colony can't yet say, it can't teach (comprehension gates supply).
- **I3/I4 status (2026-07-18):** in the current SHARED-HEAD Tongue, I3 (convergence) and I4 (memory) are SUBSUMED by
  I1+I2 — colonies already share concept weights (convergence is the comprehension-diffusion pulling `level`s
  together), and the durable "memory of what was taught" IS the comprehension gain persisted in `level` and fed back
  through the I1 reward. The FULL distinct-per-colony-ontology forms below require PER-COLONY MaskedMind heads (each
  colony a separate learner + triplet store), a real architectural increment (with checkpoint/pickle implications) —
  FUTURE. The reduced forms ship now; the rich forms wait on per-colony heads.

- **I3 — Concept-topology convergence through conversation.** Repeated inter-colony triplet exchange pulls the two
  colonies' MaskedMind embeddings toward a SHARED frame — the relative-representations alignment primitive from
  SPEC_ENSEMBLE_EMBED (`relative_representation`), applied SOCIALLY: each colony aligns its concept space to the
  anchors it shares with its interlocutor, so dialogue → a converged ontology (kg_ontology canonical concept
  identity emerges from talk, not authored). "Civs converge on a new topology of concepts." Measurable: cross-colony
  embedding cosine rises with conversation count.
- **I4 — Conversational memory (learn from what was said).** Each colony keeps an EPISODIC store of heard triplets —
  (source colony, step, the triplet, the reward-outcome that followed) — and REPLAYS them for learning, reusing the
  maw's existing elite-replay **dream** buffer (`ColonyMawRL._mem` / Chill-season dreaming, [[frozen-fm-router-feudal-brain]])
  and the `agentic_kg_memory` episodic pattern. "Memory of their conversations to learn from" — a colony that heard
  `improves(irrigation, yield)` and then prospered replays that association; a colony betrayed after a parley
  remembers the source. Memory turns one-shot talk into durable culture.

The loop closes: comprehend → transmit as triplets (I2) → converge shared ontology (I3) → remember (I4) → the
comprehended, remembered knowledge raises `k` and enriches the objective (I1) → the colony farms/cooperates/thrives
→ it has more to say. Language becomes the substrate of cultural evolution, and — per the H2 finding — the thing that
finally gives the update-starved maw-RL a signal worth the few updates it gets: a curriculum, not just a reward.

## Mouse test FIRST (per [[mouse-model-testing]] — small, seconds, no game)

Before any game run, in the isolated `ColonyMawRL` harness (`tools/mouse_maw_parallel.py` shrunk to a real mouse,
~a few hundred episodes): give two arms the SAME bandit but one with a comprehension-gated reward (sweep a fixed
`k ∈ {0, 0.5, 1.0}` as a static catalyst, and a rising-`k` schedule). Metric: does the comprehension-gated reward
reach the lift threshold in FEWER episodes than the flat reward? If yes → the coupling helps; translate to game. If
no → the shaping is inert and we don't ship it. This gates the spec, not a live run.

## Constants

| Constant | Value | Meaning |
|---|---|---|
| `COMPREHENSION_RL_ENABLED` | `False` | gate; module default off (battery byte-identical); entrypoint flips baseline-on |
| `COMPREHENSION_FLOOR` | reuse `BOOTSTRAP_FLOOR` | floor weight on the objective term at k=0 (no new magic number) |

Derived (NOT new constants): `k` = `TongueSystem.comprehension(colony_id)`; `need_met` from existing scarcity state
(`maw.food_stored`, winter-bite / drought / flood / famine flags); the SHARE decision from a reused maw affordance
channel; the transmission edge-filter from `politics.hostile`. No authored thresholds — every gate rides a signal
that already exists.

## Acceptance

- Gate off ⇒ maw reward is the exact current `Δsnap`, byte-identical battery.
- Gate on ⇒ reward = survival_term + need_met·(floor + comprehension)·objective_term; a high-comprehension colony
  gets a larger objective-term gradient than a low-comprehension one for the SAME resource gain (unit-checkable).
- **Maslow gate:** at `need_met → 0` (famine/flood/drought) the reward collapses to `survival_term` (nature > nurture)
  — a fixed battery of {plenty, famine} states shows the objective weight shrink to ~0 under scarcity.
- **Optional + diplomacy-gated (I2):** a maw may choose NOT to share (silence is a valid learned policy); a triplet
  transmits ONLY across a non-hostile edge — a hostile pair exchanges nothing (unit-checkable via `politics.hostile`).
- **Emergent, not scripted:** no acceptance test asserts colonies REACH cooperation — peace is an emergent outcome
  of RL-weight convergence under geopolitical pressure and may never occur; the test asserts the MECHANISM (edges,
  gates, transmission), never a guaranteed cooperative end-state.
- MOUSE gate: the comprehension-catalyzed reward reaches the lift threshold in ≤ the flat reward's episodes on a
  ≥3-`k` battery, else the coupling is not shipped.

## Gating / Provenance

`COMPREHENSION_RL_ENABLED` module default False → `run_tests._GATE_NAMES` → entrypoint baseline-on. Provenance:
the keeper's "communication as a driver of RL" directive; reward shaping (Ng et al. 1999, potential-based caution);
comprehension = SPEC_TONGUE masked-recovery level; the maw reward lives in `sandkings._maw_rl_tick`. Tested in mice
first ([[mouse-model-testing]]); must clear the overhead rule ([[balance-objective-computational-efficiency]]).
