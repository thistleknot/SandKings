# SPEC — Dog-eat-dog scarcity war (invert the trigger)

Status: IN PROGRESS (War & Survival arc, Phase 3). Baseline-ON, opt-out `--no-scarcity-war`. Amends
SPEC_POLITICS war-footing (T10/P5). Depends on Phase 2 (winter must make colonies starve for the trigger
to fire).

## Why

Today war is prosperity-gated: a colony declares only when `food_stored > WAR_CHEST(400)` and stands down
below 200; starvation *lowers* aggression and locks a hungry colony out of war; raiding yields **zero
loot**. That is the inverse of the user's vision — "war is the way of things under starving dog-eat-dog
conditions; they can cannibalize each other." Phase 3 inverts it: the starving *declare* war to raid,
hunger *raises* aggression, raiding *plunders* food, and the starving eat the fallen. Both triggers
coexist (Hickam): a rich colony wars for dominance, a starving one wars to eat. **Truces hold and kin are
safe** — hunger raids enemies and strangers only (`_select_war_target` already excludes kin/allies/truced;
the stand-down still honours a truce).

Gate `SCARCITY_WAR_ENABLED` (module default False → battery byte-identical; entrypoint flips on; in
`_GATE_NAMES`). Constants: `HUNGER_WAR_FLOOR=60` (below the prosperity stand-down 200, above hard-starve 0),
`SCARCITY_AGG_K=0.6`, `PLUNDER_FRAC=0.15`, `PLUNDER_MAW_FRAC=0.35`, `CANNIBAL_HUNGER_BONUS=10`, `SACK_RADIUS=6`.

## SW1 — Scarcity trigger + stand-down redesign (war footing, sandkings.py ~2152-2187)

- Entry: keep the prosperity branch verbatim; OR-in a gated scarcity path — a colony with
  `food_stored < HUNGER_WAR_FLOOR` and ≥1 unit and an eligible non-kin/non-truced target (via the
  existing `_select_war_target`) declares war. Distinct event "raids to survive — the maws hunger".
- Stand-down: today drops the target when `food < WAR_CHEST/2`. Under the gate, a colony with
  `food < HUNGER_WAR_FLOOR` no longer stands down for poverty (`poor := False`); only a dead/resolved
  target or an active truce ends its war. Off → `poor = food < WAR_CHEST/2` exactly as today.
- Gating: when off, both the scarcity flag and the poverty override are False/skipped, so the entry
  condition and the stand-down boolean are bit-identical to today. No RNG draw-order change.

## SW2 — Hunger raises aggression (`_aggression_eff`, ~3236)

`_aggression_eff` is pure but feeds hot `random.random() < eff` combat comparisons, so any change to its
return value shifts downstream RNG — the desperation term is strictly gated. Under `SCARCITY_WAR_ENABLED`,
when `food < HUNGER_WAR_FLOOR` add `SCARCITY_AGG_K * (1 - food/HUNGER_WAR_FLOOR)` so desperation dominates
the confidence dip (the starving fight harder). Off → the exact original expression, byte-identical.

## SW3 — Plunder (raiding relieves scarcity; combat transfers zero food today)

Two deterministic channels (no new RNG), both gated:
- **Per-kill** (`_resolve_conflicts`, the two kill sites ~8303/8325): when a unit is killed (capture
  failed → real death), the victor's maw seizes `PLUNDER_FRAC` of the loser colony's `food_stored`. Plunder
  only **moves** food (subtract from loser, `maw.eat` on victor) — never mints it, so total food is
  conserved.
- **Maw-sack** (`_check_maw_deaths`, after the succession skip): when a colony's maw falls, a besieger —
  the living colony whose `war_target` is the dead colony with a unit within `SACK_RADIUS` of the fallen
  maw (`_sack_besieger`) — seizes `PLUNDER_MAW_FRAC` of the residual `food_stored`. No clear besieger → no
  sack (food lost as before).

## SW4 — Eat the fallen (`_resolve...` grab loop CORPSE branch, ~7834)

Corpse-forage stays ownership-blind (eating the already-dead is fine — "kin safe" governs *killing* kin,
not foraging corpses). Under the gate, a forager whose colony was starving (`food < 2*BOOTSTRAP_FLOOR`
captured **before** the base credit) gains `CANNIBAL_HUNGER_BONUS` on top of `HARVEST_YIELD`; a fed colony
gets today's exact +15. Throttled "the starving fall upon the fallen" event. Off → no bonus, byte-identical.

## Balance (real stakes, must not extinct all colonies)

`PLUNDER_FRAC` small (0.15); scarcity war requires a live unit + an eligible target; plunder conserves
food (cannot inflate a runaway). Respawn (`RESPAWN_FOOD=50`) backstops extinction so the terrarium never
empties. A soak (a few seeds × 500 steps `--harsh`) must confirm ≥2 living colonies at step 500 before the
baseline-on values are trusted.

## Acceptance (`tests/test_scarcity_war.py`)

- A hungry colony (`food < HUNGER_WAR_FLOOR`, ≥1 unit, eligible enemy) declares war and does NOT stand
  down while it stays hungry.
- Plunder conservation: a kill moves exactly `PLUNDER_FRAC * loser_food` to the victor; total food across
  both maws is unchanged.
- `_aggression_eff` rises when hungry (gate on) and is unchanged (gate off).
- Gate-off: a hungry colony still stands down at `food < WAR_CHEST/2`; `_aggression_eff` un-augmented.
- Full battery byte-identical with the gate off.
