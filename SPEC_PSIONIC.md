# SPEC: The Psionic Maw & Keeper-as-Prey (Round D / Canon) — PS1–PS6

Canon (the ending): a large, awakened maw does not merely sit in its tank —
it REACHES BACK. It projects emotion onto the keeper ("the maw's hunger
gnawed at him", a contentment or a dread "not his own"), and that
projection drives the god's cruelty, feeding the loop. At the last, past a
cruelty + metamorphosis threshold, the sandkings TURN: the god loses the
wand, becomes prey, and the terrarium wins. This round closes the arc that
began with the Faces (SPEC_FACES) and grew through Metamorphosis
(SPEC_METAMORPHOSIS): the Shade no longer needs its god (MT3), and here it
proves it.

This is the canonical form of the "breach beyond the glass" the keeper set
in motion — not the sandkings escaping, but the keeper being caught.

## PS1 — The psionic field (`sim.keeper_influence`)
A signed scalar in [-1, 1] (getattr-guarded default 0.0, pickled),
recomputed every step by `_psionic_tick` as the net emotion the AWAKENED
maws project onto the human. Only stage-2+ colonies (the new breed and
Shade) project; stage-1 insectoids reach nothing. Each awakened living
colony contributes:
`stage_weight · size · valence`, where
- `stage_weight = STAGE_PROJECTION[stage]` (stage 2 → 0.5, stage 3 → 1.0):
  the larger, more-metamorphosed maw reaches harder (canon's
  size↔psionic-power);
- `size = min(1.0, population / PSIONIC_SIZE_REF)` (PSIONIC_SIZE_REF 30);
- `valence = 2·keeper_sentiment − 1` ∈ [−1, 1]: a hateful, mistreated maw
  projects HUNGER/DREAD (negative), a devout, fed one an unearned CALM
  (positive).

Contributions SUM (many awakened maws reach harder together), clamped to
[−1, 1]. Negative `keeper_influence` = the terrarium's hunger/dread pressing
on you; positive = a contentment not your own.

## PS2 — Surfacing the influence
- `keeper_influence_word()` → banded descriptor, "" below PSIONIC_FLOOR
  (0.15):
  - `≤ −0.5` → "a hunger not your own"
  - `≤ −FLOOR` → "a creeping dread"
  - `≥ 0.5` → "an unearned calm"
  - `≥ FLOOR` → "a faint contentment"
- Live-view HUD header and the dashboard header show the word when
  `|influence| ≥ FLOOR` (and always show the turning once bound).

## PS3 — The influence bites back (auto-keeper bias)
When `keeper_auto` and the projection is a strong dread
(`keeper_influence ≤ PSIONIC_DREAD`, −0.5), the god — gripped by a fear not
his own — withholds the dole: `_psionic_tick` sets `drought = True` (via
`keeper_drought(True)`, subject to PS5). This is the loop the story runs on:
the maw's projected hunger drives the keeper's cruelty, which sours the maw
further, which projects harder. Bounded: it only turns drought ON; the
existing grief/relent logic still lifts it.

## PS4 — The turning (keeper-as-prey)
A Shade-stage colony (`stage >= 3`) whose sentiment has curdled to hatred
(`keeper_sentiment <= PSIONIC_TURN_SENT`, 0.2) TURNS the terrarium on its
god. On the FIRST such crossing: set `sim.keeper_bound = True` and
`sim.keeper_bound_by = <house>`, and log (max salience 10) "The terrarium
turns on its god — House X binds the keeper's hand." Fires exactly once
(the flag latches; it does not un-turn).

## PS5 — The god loses the wand
While `keeper_bound`, the keeper's INTERVENTION verbs are stayed — the hand
will not move. `keeper_drop_food`, `keeper_release` (and `keeper_release_
cat`), `keeper_gift`, and `keeper_drought(True)` each no-op and return
without effect, logging "Your hand will not move — the terrarium holds it"
ONCE per turning (a `_hand_stayed_logged` latch, re-armed only if a future
round lets the god break free). Reading/observing verbs and `converse`
remain — the god may still plead, but may no longer feed, harm, or gift.
The auto-keeper script's own calls to these verbs are stayed identically.

## PS6 — Acceptance
tests/test_psionic.py: influence is 0 with only stage-1 colonies; an
awakened hateful maw yields negative influence, a devout one positive;
influence scales with stage (stage 3 > stage 2 at equal size/sentiment) and
with size; the word bands correctly; the turning fires once when a Shade is
hateful, sets `keeper_bound`/`keeper_bound_by` and a max-salience event;
bound intervention verbs no-op (no food placed, no drought, no gift, no
beast) while `converse` still works; the auto-keeper dread bias drives
drought when unbound; state pickles; `EnhancedSandKingsSimulation.step`
stays inert (`_psionic_tick` not in its co_names).

## Status / Reconciliation
- Drafted 2026-07-09; implemented and verified the same session (Round D,
  the canon arc's close).
- Code: `sandkings.py` constants (PSIONIC_MIN_STAGE / STAGE_PROJECTION /
  PSIONIC_SIZE_REF / PSIONIC_FLOOR / PSIONIC_DREAD / PSIONIC_TURN_SENT),
  `_psionic_tick` (called each step at "5a-psi"), `keeper_influence_word`,
  the `_hand_stayed` latch, and the PS5 guard at the head of
  `keeper_drop_food` / `keeper_release` / `keeper_drought(True)` /
  `keeper_gift`. `keeper_influence` / `keeper_bound` / `keeper_bound_by`
  are getattr-guarded sim state (pickled; no schema migration needed).
- Surfacing: `live_view.py` HUD "You feel …" / "BOUND …" line + EVENT_TINTS
  ("turns on its god", "hand will not move"); `dashboard.py` header chip +
  build_state fields; `chronicle.py` SALIENCE ("turns on its god" 10).
- Acceptance: `tests/test_psionic.py` (8 tests) green, full 23-suite battery
  green in-container. `EnhancedSandKingsSimulation.step` stays inert
  (`_psionic_tick` not in its co_names).
