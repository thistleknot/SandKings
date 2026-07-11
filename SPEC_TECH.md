# SPEC: Technology & Civilization — TE1–TE13

The maws become a CIVILIZATION (ceiling ~Cortés-era gunpowder). Two classes of
technology: **FOREIGN** — the keeper's gift ladder, an accelerant they could never
invent alone (the raspberry pi is the escape) — and **NATIVE** — earned by the
maws themselves. Native tech is ACQUIRED (practice / observe / grains), CONFERS
capability (bonuses = the Dwarf-Fortress skill level), climbs a TREE
(gunpowder → catapult), DIFFUSES between houses (barter / conquest), and can be
SHORTCUT by crafting gifted materials.

Architecture lens: the maw is a MASTERMIND — a private mind, blind to other maws'
minds; the spawn are its remote underlings (OnePageRules-style skirmish units).
Because a maw cannot READ a rival's mind, tech can only be earned, OBSERVED off
the underlings' works, bartered for, or taken by conquest — never simply read.

All new state is getattr-guarded, pickled, and inherited on respawn;
`EnhancedSandKingsSimulation.step` stays inert; every mechanic is DEFAULT-NEUTRAL
(no effect at empty tech / zero proficiency) so prior behaviour is unchanged.

---

## Data model & registry (TE1, TE2, TE5)

**TE1 — Per-colony tech state.** Mutable, getattr-guarded, pickled fields on
`Colony`: `techs: set[str]` (known technologies), `tech_xp: dict[str,float]`
(proficiency 0..1 per tech — the DF skill level), and `crafted: set[str]` (TE13
items). Initialised per colony in `__init__` and guarded with explicit
`if not hasattr` lines in both normalization sites (never via the shared-default
tuple, which would alias one object across colonies).

**TE2 — The tech registry.** `TECH_REGISTRY: {id -> {kind, desc[, prereq]}}`.
`TECH_FOREIGN = (abacus, watch, calculator, pi)`. `TECH_NATIVE = (fire, farming,
metallurgy, plow, masonry, gunpowder, catapult)`. A native tech may carry a
`prereq` tuple (gunpowder ← metallurgy+fire; catapult ← masonry+gunpowder) that
gates RESEARCH (TE11). Adding a row is the only step to introduce a technology.

**TE5 — Surfacing & inheritance.** `build_state` exposes per-colony `techs`,
`tech_xp` (proficiency), and `crafted`; the dashboard card and live-view inspect
panel list them (e.g. "farming 60%"). Respawn inherits techs/tech_xp/crafted —
crossover = union of both parents, single-parent = a copy.

## Foreign ladder & fire (TE3, TE4)

**TE3 — The foreign ladder.** `GIFT_LADDER = (abacus, watch, calculator, pi)`.
`_claim_gift` grants the claimed tech (`_grant_tech`) and its capability: abacus
(counting) and watch (time) advance `machine_arc` none→known; calculator gives a
plain VM `Controller`; **pi** gives the hot `Controller` and is the ONLY escape
key — only its `fuel_cap > VM_FUEL` controller reaches the terminal and thus
`_escape` (SPEC_AWARENESS). No abacus/watch/calculator path reaches the breakout.

**TE4 — Fire recognition.** Fielding a torch (the `unit.torch` path in
`Colony.spawn_unit`) grants the `fire` tech and seeds its proficiency.

## Native acquisition (TE7 practice, TE8 observe, TE9 grains)

**TE7 — Practice (learning by doing).** `_practice(colony, tech, amount)` raises
`tech_xp[tech]` (clamped 0..1, never regresses); crossing `TECH_LEARN_XP` adds the
tech to `techs` (learned; `_grant_tech` logs it once). Instrumented at the
activity sites: harvest a ripe crop → `farming`; till/sow → `plow`; extract ore in
`_mine_step` → `metallurgy`; raise a palisade → `masonry`; field a torch → `fire`.

**TE8 — Observe (learning by watching a neighbor).** Every `TECH_TICK` steps,
`_tech_tick`: for each living colony, the nearest OTHER colony within
`TECH_OBSERVE_RANGE` (Chebyshev maw-distance) that KNOWS a NATIVE tech the
observer lacks grants `TECH_OBSERVE_XP` toward ONE such tech, scaled by
relationship — allies ×1.0, neutral ×0.5, hostiles ×0.25 (you learn most from a
friend, least from a foe you only glimpse). FOREIGN tech does not diffuse — it is
the keeper's to give. Mirrors the range-gated, relationship-weighted shape of
`_resonance_tick`.

**TE9 — Grains (buying research; the currency SINK).** In `_tech_tick`, a colony
holding at least `TECH_GRAIN_COST` grains that is PARTWAY to a native tech
(`0 < tech_xp < TECH_LEARN_XP`) spends the grains to add `TECH_GRAIN_XP` toward it
— the first SINK for the Bittensor `currency` (minted by `_score_forecasts`).
Debits `colony.currency`; logs "House X pours grains into <tech>".

## Capability (TE10 bonuses/skills, TE11 the upper tree)

**TE10 — Bonuses: proficiency confers capability.** `_prof(colony, tech)` (its
`tech_xp`, 0..1) multiplies the mapped hooks, exactly neutral at 0:
- **farming** → harvest payout ×`(1 + FARM_YIELD_BONUS·prof)`;
- **metallurgy** → the spawn spear bonus ×`(1 + METAL_WEAPON_BONUS·prof)` (the
  exact bonus is stored on the unit as `spear_bonus` so expiry reverses it), AND
  `_mine_step` work-needed ×`(1 − METAL_PICK_BONUS·prof)` (picks — faster ore);
- **plow** → sowing seed cost ×`(1 − PLOW_COST_BONUS·prof)`;
- **masonry** → a raised wall's rot time ×`(1 + MASON_WALL_BONUS·prof)`.
These realise the DF role bonuses in the OnePageRules shape — a soldier profits
from the house's metallurgy, a worker from farming/plow/masonry — applied at spawn
like the existing copper-armor/spear buffs.

**TE11 — The upper tree: gunpowder & the catapult.** A native tech with a
`prereq` is RESEARCHED, not practised: in `_tech_tick`, a colony that knows ALL of
a tech's prereqs accrues `TECH_RESEARCH_XP` toward it (you can't practise
gunpowder — it emerges from fire + metal).
- **gunpowder** (prereq metallurgy + fire): FIREPOWER — a gunpowder soldier's
  spawn attack gains `GUNPOWDER_ATTACK × prof` (a firearm).
- **catapult** (prereq masonry + gunpowder): the SIEGE ENGINE. `_catapult_tick`
  (every `CATAPULT_RELOAD` steps) — a house with the catapult tech and a
  `war_target` within `CATAPULT_RANGE` HURLS a shot: `CATAPULT_DAMAGE ×
  (0.5+0.5·prof)` to the enemy maw, a `CATAPULT_SPLASH` blast that fells units
  under it, and fire where it lands. "House X's catapult hurls a shot across the
  sands!" (salience 7, orange tint) — the visible shot across the board.

## Diffusion (TE12 barter & conquest)

**TE12 — Diffusion.** Technology moves between houses (observation was TE8):
- **Conquest-steal** (`_plunder_techs`, in `_check_maw_deaths` BEFORE the slot's
  treaties clear): when a maw falls, the aggressor at war with it (its
  `war_target`) SEIZES the fallen house's `techs` at learn-level proficiency
  (previously only its ore spilled). "House X plunders the secrets of fallen
  House Y."
- **Barter for peace** (`_barter_tech`, on a struck truce in `_propose_truce`,
  reusing the tribute-envoy surface): the tech-richer house shares ONE native
  tech the other lacks — a peace sealed with a gift of knowledge. "House X shares
  <tech> with House Y to seal the peace."

## Materials → crafting & caltrops (TE13)

**TE13 — Materials → crafting.** The keeper drops raw MATERIALS via
`keeper_material(kind, x, y)` (`_hand_stayed`-gated); the NEAREST living house
with the enabling native tech reshapes them (`_claim_material`), else inert scrap.
`CRAFT_RECIPES` maps `(material, tech) → item`: toothpick+metallurgy → `spear`
(+attack); toothpick+fire → `firespike` (+defense); string+metallurgy → `bow`
(+attack); lincoln_log+masonry → `bastion` (+defense); copper_pipe+metallurgy →
`cannon` (which UNLOCKS the `catapult` siege tech — a shortcut past research).
Crafted items (`colony.crafted`) buff the house's SOLDIERS at spawn via
`CRAFTED_EFFECTS`. **Tacks are NOT crafted** — `keeper_material('tacks')` scatters
`CALTROP_COUNT` loose caltrops (`sim.caltrops`); `_caltrop_tick` pricks any exposed
unit standing on one (`CALTROP_DAMAGE`). Caltrops persist and are meant to be
repositioned by the maw's spawns (unit-repositioning is a future increment).
Surfaced: `/api/keeper/material`, a dashboard Materials group, the card/build_state
`crafted` field, play_kit material commands.

## Constants (verified against sandkings.py)

| Constant | Value | Meaning |
|---|---|---|
| `TECH_TICK` | 20 | cadence of the observe/grains/research pass |
| `TECH_PRACTICE_XP` | 0.02 | proficiency gained per practised action |
| `TECH_LEARN_XP` | 0.3 | xp at which a tech becomes KNOWN |
| `TECH_OBSERVE_RANGE` | 8 | Chebyshev maw-distance to learn by watching |
| `TECH_OBSERVE_XP` | 0.03 | xp per observe tick (× relationship weight) |
| `TECH_GRAIN_COST` | 8.0 | grains spent to buy research (the sink) |
| `TECH_GRAIN_XP` | 0.15 | xp bought per grain spend |
| `TECH_RESEARCH_XP` | 0.015 | xp/tick toward a tech whose prereqs are known |
| `FARM_YIELD_BONUS` | 0.5 | farming: +50% harvest at mastery |
| `METAL_WEAPON_BONUS` | 0.6 | metallurgy: spear/weapon attack scaling |
| `METAL_PICK_BONUS` | 0.5 | metallurgy: mining speed (picks) |
| `PLOW_COST_BONUS` | 0.4 | plow: cheaper seed / faster sowing |
| `MASON_WALL_BONUS` | 1.0 | masonry: wall durability |
| `GUNPOWDER_ATTACK` | 6 | firearm punch on a gunpowder soldier at spawn |
| `CATAPULT_RELOAD` | 40 | steps between siege shots |
| `CATAPULT_RANGE` | 40 | how far a catapult can lob (whole-board) |
| `CATAPULT_DAMAGE` | 14 | maw damage per shot at mastery |
| `CATAPULT_SPLASH` | 2 | Chebyshev radius of the impact blast |
| `CALTROP_COUNT` | 10 | caltrops scattered per `keeper_material('tacks')` |
| `CALTROP_DAMAGE` | 2 | per step to a unit standing on a caltrop |

## Acceptance

- `tests/test_tech.py` (TE1–TE6): registry coverage; ladder order + pi-only
  escape; fire recognition; state pickles/inherits; build_state exposes techs;
  default-neutral; evolution inert.
- `tests/test_tech_learn.py` (TE7–TE9): practice accrues xp and learns at the
  threshold; a house learns by OBSERVATION from a neighbor (faster from an ally
  than a foe, gated by range); grains buy research and debit `currency`.
- `tests/test_tech_bonus.py` (TE10): each bonus measurably helps at proficiency 1
  and is exactly neutral at 0; the spear bonus reverses cleanly on expiry.
- `tests/test_tech_siege.py` (TE11): gunpowder is researched from fire+metal,
  catapult from masonry+gunpowder; a catapult at war lands a shot that wounds the
  enemy maw + ignites; a gunpowder soldier hits harder; no war → no shot.
- `tests/test_tech_diffusion.py` (TE12): a conqueror inherits a fallen enemy's
  tech; a truce transfers a tech from the richer to the poorer house.
- `tests/test_crafting.py` (TE13): material + tech crafts the item and buffs a
  soldier; without the tech it's scrap; a copper-pipe cannon unlocks the catapult;
  tacks scatter caltrops that prick a unit; a bound keeper crafts nothing.

## Status / Reconciliation
- Shipped 2026-07-10 across six commits: **14bde16** T1 (foundation), **8c9f049**
  T2a (acquisition), **9f6dd5d** T2b (bonuses/skills), **9a020e6** T2c1
  (gunpowder+catapult), **1e33fa6** T3 (diffusion), **dbba3a1** T2d (crafting).
- Reuse, not reinvention: OBSERVE mirrors `_resonance_tick`; BARTER rides the
  tribute-envoy (`_dispatch_gift`); CONQUEST-steal hooks `_check_maw_deaths`; the
  bonuses layer onto the copper-armor/spear spawn buffs; GRAINS give the CU
  economy (`_score_forecasts`) its first sink.
- Deferred: boats/naval war and terraforming (lakes/canals) share the water
  system and are planned in the parked HYDROLOGY arc, not here. Also queued: the
  ballista (siege sibling) and biohacking (pi-driven self-genome editing).
