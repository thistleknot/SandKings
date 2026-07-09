# Spec: Timber, Bone & Flame (fortifications, organic weapons, decay, fire)

Layer: **Requirements** + **Behavioral** (fire spread). Owns shared
T-numbers **T41–T47**. Governs: trees, bone/wood stores, palisade
fortifications, crafted weapons with organic decay, and fire in
`sandkings.py`; viewer surface R28; anchors M12. Status: draft →
implement → reconcile (log at bottom).

## 1. Intent (user's words)

Fortifications — simple like Minecraft now, long-term like Dwarf
Fortress. Weapons built from trees and bones. Natural decay for natural
items — *why precious metals are valuable*. Fire.

The design law: everything organic ROTS (wood walls crumble, spears
splinter, stored timber decays); metal is forever. Cheap-and-perishable
vs dear-and-durable is the round's economic sentence.

## 2. Implementation Requirements (constants)

- Voxels: `WOOD = 14` (palm/scrub trunk; solid, not tunnelable,
  FLAMMABLE), `WOOD_WALL = 15` (palisade; solid, not tunnelable,
  flammable, ROTS). Both added to all five rendering/spec surfaces.
- `TREE_CLUSTERS = 5` at generation: 3 in the oasis ring (r ∈ [4, 9] of
  center), 2 scattered scrub; each 2–4 trunks on the surface.
- `TREE_REGROWTH_P = 0.02` — per Flood-season feeding tick, each living
  WOOD voxel may sprout one new trunk on adjacent surface sand (world
  WOOD capped at `TREE_CAP = 40`).
- `CHOP_TIME = 4` worker-steps per WOOD voxel → `colony.wood += 1`.
- Bone: harvesting a CORPSE additionally yields `colony.bone += 1`.
- Organic store rot: every `ROT_INTERVAL = 100` steps, `colony.wood` and
  `colony.bone` each lose 1 (floor 0). Metals (`colony.ore`) never rot.
- `PALISADE_RING = 2` (Chebyshev ring radius around the maw),
  `PALISADE_COST = 1` wood per WOOD_WALL voxel, `WALL_ROT = 800` steps
  (2 seasons) tracked in a sparse registry `sim.rot: pos -> expiry`.
- Weapons (consumed at soldier spawn, copper-armor pattern):
  `SPEAR_COST = (1 wood, 1 bone)` → `SPEAR_ATTACK = 4` bonus;
  `SPEAR_LIFE = 400` steps, then it splinters (decision-log entry,
  attack bonus removed). `TORCH_COST = 1 wood` → at-war soldiers carry a
  torch enabling ignition (T45). Copper armor remains permanent — the
  documented contrast.
- Fire: registry `sim.fires: pos -> burn_ticks`; `FIRE_TICK = 5` (rides
  the machine/crop cadence), `FIRE_BURN = 8` ticks, `FIRE_SPREAD_P =
  0.5` per adjacent flammable per tick, `FIRE_DAMAGE = 2` per tick to
  units within Chebyshev 1. FLAMMABLE = {WOOD, WOOD_WALL, CROP,
  CROP_RIPE}. Burnout → SAND (crop/soil cells) or AIR (elevated wood).
  Ignition sources: (a) torch-armed at-war soldiers adjacent to enemy
  flammables (extends the T21 raze branch — "puts fields to the
  torch"); (b) Dust-season storm lightning: per storm step, p = 0.02
  one random surface flammable ignites (`Wildfire!` event, once per
  storm); (c) radiation hot zones (> RAD_HOT) auto-ignite flammables.
  Sand and stone stop fire — firebreaks (dug trenches, EXCAVATE) emerge.

## 3. Functional Requirements

- **T41 (trees & felling)** Generation places the clusters; Flood
  regrowth per the constants. Workers CHOP exposed WOOD at CHOP_TIME.
  **Felling is directional** (user: "felling a tree to bridge water"):
  when the chop completes, the trunk FALLS away from the chopper — up to
  `FELL_LENGTH = 3` WOOD voxels laid into consecutive AIR cells along
  the fall line, dropping into gaps (each laid voxel settles downward
  onto the first support, filling trenches/cavern mouths — a BRIDGE an
  army can cross). Only when no AIR cell can receive the trunk does the
  chop yield `colony.wood += 1` directly. Laid trunk voxels are
  themselves choppable — fell first, bridge, then salvage the bridge.
  First fell logs `Colony {id} fells its first palm`.
- **T42 (bone & rot)** Corpse harvest pays HARVEST_YIELD food AND 1 bone.
  Organic stores rot on ROT_INTERVAL; ore never does. The manager
  stores line shows `wood:W bone:B` beside copper/gold.
- **T43 (palisades)** While `colony.farming`-style gate is irrelevant —
  the trigger is defense: a worker with no higher-priority task, when
  `random() < genome.defense_investment` (the trait is FINALLY live) or
  the learner posture is FORTIFY, places WOOD_WALL on an AIR cell of the
  PALISADE_RING around the maw (cost 1 wood, registry expiry step +
  WALL_ROT). Walls rot to SAND at expiry (silent; they're organic).
  First palisade logs `Colony {id} raises palisades`. Gate-dome cells
  (T32) are TUNNEL_WALL and do NOT rot — machine walls are the upgrade.
- **T44 (weapons)** At soldier spawn: spear if affordable (attack +
  SPEAR_ATTACK, `weapon_expires = step + SPEAR_LIFE`); torch as a
  separate boolean if wood remains and the colony is at war. When a
  spear expires the attack bonus is removed and the decision log gets
  `his spear splinters`. Copper armor (T25) is unchanged and permanent.
- **T44b (the battering ram)** An at-war colony with `RAM_COST = 3` wood
  crafts a ram (`colony.ram_until = step + RAM_LIFE (600)`; event
  `Colony {id} builds a battering ram from a fallen palm`). While the
  ram lives: the colony's units SMASH adjacent enemy walls (WOOD_WALL
  and TUNNEL_WALL → SAND — the counter to the T32 gate dome; consumes
  the unit's action, raze-branch pattern) and its maw-siege damage is
  ×`RAM_SIEGE_MULT = 2`. The ram is organic: it expires silently at
  RAM_LIFE (a season and a half) or when the war ends. Arms race
  complete: palisade < gate dome < ram.
- **T45 (fire)** Per FIRE_TICK: each burning cell damages adjacent
  units, rolls spread onto adjacent flammables, decrements; at 0 the
  voxel burns out (SAND at/below its column surface context, else AIR)
  and leaves the crops/rot registries consistent (purge). Torch
  ignition replaces razing when the raze target is flammable — event
  `Colony {a} puts Colony {b}'s fields to the torch!` (once per war per
  pair, raze-event pattern). Storm lightning and radiation ignition per
  §2. Fire never spreads through SAND/STONE/GLASS/AIR.
- **T46 (surfacing)** Glyphs: WOOD `¶` (34,139,34 palm green),
  WOOD_WALL `|` (139,105,20); burning cells render `^` in flame orange
  (255,120,0) OVERRIDING the voxel glyph while in `sim.fires` (overlay,
  not a voxel). EVENT_TINTS: "fells"/"palisades" wood-brown, "torch"/
  "Wildfire" flame orange. New anchor M12: `fire` — a burning cell
  within Chebyshev 3 of the unit (34 seeds; vocabulary rebuild).
  Armed soldiers render their letter with a `'` prime? NO — keep glyphs
  clean; spears show in the manager roster (`spear:120` steps left).
- **T47 (acceptance)** Tests: tree gen counts + Flood regrowth cap;
  chop yields wood; corpse harvest yields bone; stores rot on interval
  while ore persists; palisade placed on the ring at 1 wood, rots at
  expiry; spear boosts attack then splinters on schedule; torch
  ignition fires the event and starts a blaze; fire spreads only
  through flammables, damages adjacent units, burns out to SAND/AIR,
  and a sand gap stops it (firebreak); storm-lightning and radiation
  ignition paths; pickle round-trip of fires/rot registries; old-
  checkpoint resume. Soak (3 years): ≥ 1 palisade raised, ≥ 1 spear
  crafted, ≥ 1 fire event, forests neither extinct nor unbounded
  (WOOD count in [1, TREE_CAP]), all liveness criteria, ≥ 19 sps.

- **T48 (fauna — the food web)** Wild creatures with no hive mind:
  `sim.fauna: List[SandKing]` with `colony_id = -99` and a `species`
  attribute; ALWAYS hostile to every colony (diplomacy never applies);
  soldier/scout scans and combat include them; kills leave a corpse
  bounty. Spawn roll every `MARAUDER_INTERVAL = 700` steps (p = 0.5,
  never while ≥ 6 alive), species weighted:

  | Species | Glyph | HP | ATK | Pack | Spawns | Hunts | Bounty | Special |
  |---|---|---|---|---|---|---|---|---|
  | spider (0.30) | `x` violet | 25 | 8 | 2–3 | a CAVERN pocket | units ≤ 20 | 2 | lays a WEB voxel at its trail every 8 steps |
  | rabbit (0.25) | `r` dun | 60 | 6 | 1–2 | surface edge | nothing (wanders; fights back) | 6 | dangerous megafauna prey — the mammoth hunt |
  | squirrel (0.20) | `q` chestnut | 30 | 3 | 1–2 | a WOOD voxel (tree-born) | nothing — POACHES: eats nearby FOOD/CROP_RIPE | 4 | never strikes first; SLIPS AWAY (2 moves/step flee) unless ≥ 2 units are adjacent — coordination pins it. `A squirrel raids Colony {id}'s fields` |
  | bird (0.15) | `v` sky-grey | 20 | 12 | 1 | anywhere aloft | SURFACE units ≤ 40, preferring the target with fewest allies within 4 (picks off stragglers) | 2 | flies: 3 moves/step through AIR; flees for good after taking any hit. `A shadow wheels overhead!` |
  | scorpion (0.10) | `c`? no — `t` amber | 22 | 6 | 1–2 | surface/cavern | units ≤ 15 | 2 | POISON sting: victims take 1 HP/step for 20 steps (`poisoned_until`) |
  | snake (0.06) | `S` olive | 80 | 18 | 1 | beneath (substrate) | units ≤ 25 | 5 | swims through SAND (the only burrowing fauna): `Something long moves beneath the sand...` |
  | rodent (0.12) | `n` grey | 12 | 2 | 3–4 | surface edge | nothing — SCAVENGES: eats CORPSE voxels (raids the bone/cannibal economy) | 1 | flees units at 2 moves/step |
  | anteater (0.04) | `A` rust | 150 | 25 | 1 | surface edge | units ≤ 30 | 8 | apex terror: `An anteater stalks the sands!` |

  Scale note (user): sand kings are scorpion-sized — scorpions are PEER
  rivals; rabbits are megafauna; anteaters are dinosaurs. Spider weight
  0.20, rabbit 0.18, squirrel 0.15, rodent 0.12, bird 0.15, scorpion
  0.10, snake 0.06, anteater 0.04.

  `WEB = 16` voxel (not solid, not tunnelable, flammable): a unit whose
  step enters a WEB cell clears it but LOSES the action (snared). Events:
  `Spiders crawl up from the deep!` / `A great rabbit lopes onto the
  sands` / the anteater line; `Colony {id} slays a {species}` on kills.
  Fauna die in fire like anything else. Existing danger/enemy/clueless
  anchors read fauna through the unit scans.

  **Minecraft-mob rhythm (user):** fauna spawn probability doubles in the
  dark seasons (Dust, Chill) — winter belongs to the monsters; caverns
  are the darkness they crawl from.

### T48 backlog (user musings, specced for the NEXT fauna batch)
- **fish** — requires real WATER voxels at the oasis center (a feature in
  itself: swimming, drinking, drowning, fishing); parked until water ships.
- **prairie dog** — sentinel burrower: colonies of 2–3 near the surface;
  barks deposit DANGER pheromone all colonies can read (a neutral
  early-warning network).
- **mole** — blind burrower that eats crops FROM BELOW (undermines farms
  invisibly; detected only by the vanishing fields).
- **crow** — intelligent bird: steals ORE/GOLD from maw stockpiles
  (shiny things), remembers rich colonies, flees like the bird.
- **ant** — the peer eusocial rival: a raiding column that picks up FOOD
  voxels and hauls them toward its spawn point; kill the column or lose
  the dole.

## 4. Behavioral Spec — fire tick

```
Every FIRE_TICK steps, for (pos, ticks) in list(fires.items()):
    For units within Chebyshev 1: take FIRE_DAMAGE (deaths -> corpses)
    For each face-neighbor voxel in FLAMMABLE and not already burning:
        with p = FIRE_SPREAD_P: fires[neighbor] <- FIRE_BURN
    ticks -= 1
    If ticks <= 0:
        voxel[pos] <- SAND if the cell had soil context (CROP/CROP_RIPE
                      or WOOD_WALL on ground) else AIR (standing WOOD)
        purge pos from crops / rot registries; del fires[pos]
Invariant: every fires key is a FLAMMABLE voxel (purge-first like crops)
```

## 5. Reconciliation Log

- 2026-07-08 (commit pending): T41-T48 implemented and soaked.
  Implementation deltas from the draft, all deliberate:
  - WEB = VoxelType 16 (flammable, non-solid); snare implemented in
    `_step_toward` - stepping into silk tears it (WEB->AIR) and costs
    the move. Spiders lay silk adjacent while hunting (p=0.3/step).
  - Fauna engine is self-contained: `Beast` dataclass + `sim.fauna`
    list (lazy `_fauna()` accessor); combat is an adjacent exchange
    inside `_fauna_tick`/`_beast_combat`, NOT threaded through
    `_resolve_conflicts`. Soldiers always engage; neutral species
    (rabbit, squirrel, rodent) strike only once provoked.
  - Bestiary table is `FAUNA[species] = (weight, hp, atk, pack,
    hunt_range, bounty)`; hunt_range 0 encodes "neutral".
  - DF-invader principle enforced: no spawn roll while any beast
    lives; unslain packs wander off after FAUNA_RAMPAGE=500 steps
    ("the ... incursion moves on"). Dark-season rhythm: spawn p is
    FAUNA_SPAWN_P=0.3, FAUNA_SPAWN_P_DARK=0.6 in Dust/Chill.
  - Monitor integration: beasts deposit DANGER pheromone for every
    colony each tick (feeds overlays + flee behavior) and a new
    "monster" anchor (beast within 6) joins "fire" (burning cell
    within Chebyshev 3) - M12 is TWO anchors, lexicon now 35 seeds.
    GloVe rebuild: fire -> "bombs raid burning blast explosion";
    monster -> "snake robot horror dragon ghost" (kept: thematic).
  - Fire ignition sources shipped: thrown torches (wartime soldiers,
    one throw each), dry lightning during Dust storms (p=0.02/storm
    step), and radiation hot zones now IGNITE crops instead of
    instantly deleting them (T40 coupling).
  - Fell mechanics: the cut trunk always banks (+1 wood); the crown
    falls away from the chopper, laying <= FELL_LENGTH trunks into
    open AIR at cut height (floating logs ARE the bridges); crown
    voxels with nowhere to fall bank as wood too. Choppers only work
    when colony wood < 4 (labor stays food-first).
  - Palisade gate: FORTIFY posture or genome.defense_investment > 0.5
    (getattr-guarded; the trait finally has a phenotype).
  - Trees are depth-gated (d >= 8) like ore/caverns: shallow test
    worlds stay sterile.
  - Weapons at spawn thread the sim step (`Colony.spawn_unit(type,
    step)`); spears splinter via the economy-block sweep.
  Verification: tests/test_timber.py (12 tests) + all 6 prior suites
  green; 3-year harsh soak PASS - 910 incursion-steps, 91 fire-steps,
  4 first-fell events, palisades by step 975, 536 armed-soldier
  steps, snake and squirrel slain, lightning fire, 24 steps/s.
  Balance watch: colony wood hovers near 0 (consumed by spears/rams
  as fast as chopped) - rams rare in soak; acceptable scarcity, worth
  a future knob.
