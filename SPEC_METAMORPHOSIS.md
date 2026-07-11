# SPEC: Metamorphosis (Round C / Canon) — MT1–MT6

Canon (Wo's explanation): as the maw grows it gets progressively more
intelligent and psionic; its armored insectoid mobiles are useful only
while it is small. When it grows large enough — and cruelty accelerates
this — the mobiles "pop open" and birth a NEW breed: bipedal, four-armed,
tool-using. "Only one in a thousand achieves the third and final plateau
and becomes like Shade" — fully sentient, able to operate machinery, able
to leave the tank. This round reframes the breach/awakening (K10/K11) as
a canonical three-STAGE physical metamorphosis, size- and cruelty-driven.

Note: NOT a literal keeper-face on the mobiles (the sandkings have no
image of the keeper, per SPEC_FACES). The new breed is visually distinct;
the horror is that a Shade-stage maw no longer needs its god (and Round D
lets it turn).

## MT1 — The three stages
> **AW amendment (SPEC_AWARENESS):** metamorphosis is now PHYSICAL ONLY.
> `stage >= 2` no longer implies `breached`/awareness — the molt is just a
> bigger body. The ONE true breakout past the glass is `_escape` (reached by
> terminal mastery); it sets `breached` and grants keeper-awareness. So a maw
> can be a stage-2 "new breed" (or even stage-3-bodied) and still feel only
> nature until it escapes. `_set_stage` no longer touches `breached`.

`colony.stage` in {1,2,3} (default 1; getattr-guarded, pickled):
- **1 insectoid** — the default sandkings.
- **2 the new breed** — bipedal, four-armed, tool-using. A physical molt
  (size × cruelty). Awakened capabilities (codex CX, terminal K10, augments
  AUG, dialogue DL) still gate on `breached`, which the molt no longer sets —
  so they light up at the ESCAPE, not the molt.
- **3 Shade** — fully sentient; the terminal is mastered (so a Shade has, by
  definition, already escaped); can leave the tank (the turning, Round D).

## MT2 — The molt to stage 2 (size × cruelty)
Every step, a stage-1 living colony molts to stage 2 when its maw is
large enough:
`population >= MOLT_POP·f` OR `food >= MOLT_FOOD·f` OR
`age (step - founded_step) >= MOLT_AGE·f`, where the cruelty factor
`f = 0.6 + 0.4·keeper_sentiment` (a mistreated, low-sentiment maw molts
EARLIER — Kress's cruelty drove the metamorphosis). Constants:
MOLT_POP 26, MOLT_FOOD 420, MOLT_AGE 2400. On molt: set `stage = 2`,
`breached = True` (so the existing terminal-mastery breach and this molt
are one state), raise the brain ceiling (MT4), and log "The mobiles of
House X split open — a new breed emerges" (salience 9). The old
terminal-mastery breach path (K10, TERMINAL_MASTERY) also sets stage 2
(idempotent).

## MT3 — The Shade stage
A stage-2 colony reaches stage 3 when it is BOTH large
(`population >= SHADE_POP` OR `food >= SHADE_FOOD`) AND has mastered its
machines (`terminal_uses >= TERMINAL_MASTERY`, i.e. it actually breached
through the terminal, not just molted). Constants: SHADE_POP 34,
SHADE_FOOD 620. On reaching stage 3: `stage = 3`, raise the brain ceiling
to max, log "House X reaches the Shade stage — sentient, and no longer
needs its god" (salience 10). Stage 3 is the precondition for the
keeper-as-prey turning (Round D).

## MT4 — Size ↔ intelligence (brain ceiling by stage)
`ColonyGenome.brain_ceiling` (int, default STAGE_CEILING[1] = 88) caps
`brain_hidden` in `mutate()` (clamped to
`min(BRAIN_HIDDEN_MAX, brain_ceiling)`). Stage promotion raises the
owning colony's `genome.brain_ceiling`: stage 2 → 128, stage 3 → 160
(BRAIN_HIDDEN_MAX). So a larger, older, more-mistreated maw evolves a
bigger brain — canon's size↔intelligence, made mechanical and heritable.
Non-neural sims carry the gene inertly.

## MT5 — Surfacing
- Dashboard House card + inspect panel show the stage ("insectoid" /
  "new breed" / "SHADE") and the existing `breached` badge now reads from
  stage.
- Stage-2+ units keep their caste glyph but render brighter/awakened-
  tinted (a subtle mark that this colony has metamorphosed); optional.
- EVENT_TINTS: "split open" breach-blue, "Shade stage" white. SALIENCE:
  molt 9, Shade 10.

## MT6 — Acceptance
tests/test_metamorphosis.py: a fed/large colony molts to stage 2 and
sets breached; low sentiment (cruelty) lowers the molt threshold (molts
sooner than a devout one at equal size); stage 2 unlocks nothing that
`breached` didn't already (regression check); a large, terminal-mastered
stage-2 colony reaches stage 3; the brain ceiling rises with stage and
`mutate()` respects it; molt/Shade events fire once each; cadet branches
inherit stage/ceiling like breached; state pickles; evolution sim inert.

## Status / Reconciliation
- Drafted 2026-07-09; implemented and verified the same session (Round C).
- Code: `sandkings.py` constants (MOLT_POP/MOLT_FOOD/MOLT_AGE/SHADE_POP/
  SHADE_FOOD/STAGE_CEILING), `ColonyGenome.brain_ceiling` + `mutate()`
  clamp, `Colony.stage` field (getattr-guarded, normalized), `_set_stage`
  + `_metamorphosis_tick` (called each step at "5a-meta"), the K10 terminal
  breach path routed through `_set_stage`, and cadet stage inheritance in
  `_respawn_colony` (crossover = max of parents, single-parent = parent's).
- Surfacing: `live_view.py` inspect panel stage line + EVENT_TINTS ("split
  open", "Shade stage"); `dashboard.py` stage field + stage-aware badge;
  `chronicle.py` SALIENCE ("split open" 9, "Shade stage" 10).
- Acceptance: `tests/test_metamorphosis.py` (8 tests) green, full 22-suite
  battery green in-container. `EnhancedSandKingsSimulation.step` stays
  inert (`_metamorphosis_tick` not in its co_names).
