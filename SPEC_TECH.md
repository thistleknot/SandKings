# SPEC: Technology & Civilization — TE1–TE12

The maws become a CIVILIZATION. FOREIGN technology (keeper gifts) and NATIVE
technology (earned). Techs confer capability; proficiency is the DF skill level.
T1 (TE1-TE6) laid the model; T2a (TE7-TE9) is the acquisition engine.

Architecture lens: the maw is a MASTERMIND (a private mind, blind to other maws'
minds); the spawn are its remote underlings. A maw cannot READ a rival's tech —
it earns it, OBSERVES the underlings' works, barters, or conquers for it.

## TE1 — Per-colony tech state
Getattr-guarded, pickled fields on `Colony`: `techs: set[str]` (known techs;
default empty) and `tech_xp: dict[str,float]` (proficiency 0..1 per tech; the DF
skill level). Mutable → initialised per colony in `__init__` and guarded with
explicit `if not hasattr` lines in both normalization sites.

## TE2 — The tech registry
`TECH_REGISTRY: {id -> {kind, desc}}`; `TECH_FOREIGN` (abacus/watch/calculator/
pi) and `TECH_NATIVE` (fire/farming/metallurgy/plow/masonry; extended in T2c).

## TE3 — The foreign ladder
`GIFT_LADDER = ('abacus','watch','calculator','pi')`; `_claim_gift` grants the
tech (`_grant_tech`) and its capability. The pi is the ONLY escape key (only its
`fuel_cap > VM_FUEL` controller reaches the terminal → `_escape`).

## TE4 — Fire recognition
Fielding a torch (`Colony.spawn_unit`) grants the `fire` tech.

## TE5 — Surfacing & inheritance
`build_state` per-colony `techs` (+ TE9 proficiency); dashboard card + live-view
inspect list them. Respawn inherits techs/tech_xp (crossover = union, single-
parent = copy).

## TE6 — Foundation acceptance (tests/test_tech.py)
Registry coverage; ladder order + pi-only escape; fire recognition; state
pickles/inherits; build_state exposes techs; default-neutral; evolution inert.

## TE7 — Practice (learning by doing)
`_practice(colony, tech, amount=TECH_PRACTICE_XP)` raises `tech_xp[tech]`
(clamped 0..1); when it crosses `TECH_LEARN_XP` (0.3) the tech is added to
`techs` (learned; `_grant_tech` logs it once). Instrumented at the activity
sites (each call small): harvest a ripe crop → `farming`; till/sow → `plow`;
extract ore in `_mine_step` → `metallurgy`; build a palisade/castle → `masonry`;
field a torch → `fire`. Practice never regresses. Constant TECH_PRACTICE_XP 0.02.

## TE8 — Observe (learning by watching a neighbor)
Every `TECH_TICK` (20) steps, `_tech_tick` spreads tech by proximity: for each
living colony, the nearest OTHER colony whose maw is within `TECH_OBSERVE_RANGE`
(8, Chebyshev) that KNOWS a NATIVE tech the observer lacks grants the observer
`TECH_OBSERVE_XP` (0.03) toward ONE such tech, scaled by relationship — allies
×1.0, neutral ×0.5, hostiles ×0.25 (you learn most from a friend, least from a
foe you only glimpse). Foreign techs do NOT spread by observation (they are the
keeper's to give). This crossing `TECH_LEARN_XP` also learns the tech.

## TE9 — Grains (buying research; the currency SINK)
In `_tech_tick`, a colony holding at least `TECH_GRAIN_COST` (8) grains that is
PARTWAY to a tech (`0 < tech_xp < TECH_LEARN_XP`) may spend the grains to add
`TECH_GRAIN_XP` (0.15) toward it — the first SINK for the Bittensor `currency`.
Debits `colony.currency`, logs "House X pours grains into <tech>". `tech_xp`
surfaces as proficiency on the card/inspect (e.g. "farming 60%").

## TE7-TE9 acceptance (tests/test_tech_learn.py)
Practicing an activity accrues xp and learns the tech at the threshold; an
un-taught house beside a teacher learns by OBSERVATION (and faster from an ally
than an enemy); a house with grains and partial xp SPENDS them to research (and
its `currency` drops); proficiency is exposed; all default-neutral; pickles;
evolution inert.

## TE10 — Bonuses: proficiency confers capability (T2b)
A colony's `_prof(colony, tech)` (its `tech_xp`, 0..1) multiplies the mapped
hooks, DEFAULT-NEUTRAL at 0 (every prior behaviour unchanged at proficiency 0):
- **farming** → harvest payout ×`(1 + FARM_YIELD_BONUS·prof)` (up to +50%);
- **metallurgy** → the spawn spear bonus ×`(1 + METAL_WEAPON_BONUS·prof)` (the
  exact bonus is stored on the unit so expiry reverses it), AND `_mine_step`
  work-needed ×`(1 - METAL_PICK_BONUS·prof)` (picks — faster ore);
- **plow** → sowing seed cost ×`(1 - PLOW_COST_BONUS·prof)` (the seed goes
  further);
- **masonry** → a raised wall's rot time ×`(1 + MASON_WALL_BONUS·prof)` (walls
  endure). These are the DF role bonuses realised: a soldier profits from the
  house's metallurgy, a worker from its farming/plow/masonry/metallurgy skill,
  in the OnePageRules shape (skill→better weapon/defense/efficiency).
Acceptance (tests/test_tech_bonus.py): each bonus measurably helps at proficiency
1 and is exactly neutral at 0; the spear bonus reverses cleanly on expiry.

## TE11 — The upper tree: gunpowder & the catapult (T2c)
A real tech TREE with prerequisites, ceiling ~Cortés-era gunpowder. A native
tech with a `prereq` in `TECH_REGISTRY` is RESEARCHED, not practised: in
`_tech_tick`, a colony that KNOWS all of a tech's prereqs accrues
`TECH_RESEARCH_XP` toward it (you can't practise gunpowder — it emerges from
fire + metal).
- **gunpowder** (prereq metallurgy + fire): FIREPOWER — a gunpowder soldier's
  spawn attack gains `GUNPOWDER_ATTACK × prof` (a firearm).
- **catapult** (prereq masonry + gunpowder): the SIEGE ENGINE. `_catapult_tick`
  (every `CATAPULT_RELOAD` steps) — a house with the catapult tech and a war
  target within `CATAPULT_RANGE` HURLS a shot: `CATAPULT_DAMAGE × (0.5+0.5·prof)`
  to the enemy maw, a `CATAPULT_SPLASH` blast that fells units under it, and
  fire where it lands. "House X's catapult hurls a shot across the sands!"
  (salience 7, orange tint). The visible shot across the board.
Acceptance (tests/test_tech_siege.py): a colony with fire+metallurgy researches
gunpowder over time; with masonry+gunpowder, catapult; a catapult at war lands a
shot that damages the enemy maw + ignites at impact; a gunpowder soldier hits
harder; boats/naval + terraforming follow in T2c2.

## Status / Reconciliation
- T1 (TE1-TE6) drafted+implemented 2026-07-10 (commit 14bde16). T2a (TE7-TE9)
  same session. T2b (bonuses/skills), T2c (gunpowder/siege/naval), T2d (crafting)
  and T3 (diffusion) extend this and get their own spec sections/files.
