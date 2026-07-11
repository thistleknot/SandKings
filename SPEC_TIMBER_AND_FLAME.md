# Spec: Timber, Bone & Flame (fortifications, organic weapons, decay, fire)

Layer: **Requirements** + **Behavioral** (fire spread). Owns shared
T-numbers **T41–T47**. Governs: trees, bone/wood stores, palisade
fortifications, crafted weapons with organic decay, and fire in
`sandkings.py`; viewer surface R29 (SPEC_LIVE_VIEW R25-R31 ledger); anchors M13. Status: draft →
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
- `TREE_CLUSTERS = 5` (inline at the generation site; not a named
  code constant) at generation: 3 in the oasis ring (r ∈ [4, 9] of
  center), 2 scattered scrub; each 2–4 trunks on the surface.
- `TREE_REGROWTH_P = 0.02` — per Flood-season feeding tick, each living
  WOOD voxel may sprout one new trunk on adjacent surface sand (world
  WOOD capped at `TREE_CAP = 40`).
- `CHOP_TIME = 4` worker-steps per WOOD voxel → `colony.wood += 1`.
- Bone: harvesting a CORPSE additionally yields `colony.bone += 1`.
- Organic store rot: every `ROT_INTERVAL = 100` steps, `colony.wood` and
  `colony.bone` each lose 1 (floor 0). Metals (`colony.ore`) never rot.
- `PALISADE_RING = 2` (Chebyshev ring radius around the maw),
  `PALISADE_COST = 1` wood per WOOD_WALL voxel (inline at site), `WALL_ROT = 800` steps
  (2 seasons) tracked in a sparse registry `sim.rot: pos -> expiry`.
- Weapons (consumed at soldier spawn, copper-armor pattern):
  `SPEAR_COST = (1 wood, 1 bone)` (inline in Colony.spawn_unit) →
  `SPEAR_ATTACK = 4` bonus;
  `SPEAR_LIFE = 400` steps, then it splinters (decision-log entry,
  attack bonus removed). `TORCH_COST = 1 wood` (inline in Colony.spawn_unit) → at-war soldiers carry a
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
  "Wildfire" flame orange. New anchors M13: `fire` — a burning cell
  within Chebyshev 3 of the unit — and `monster` — a beast within
  Manhattan 6 (35 seeds; vocabulary rebuild).
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
  bounty. Spawn roll every `MARAUDER_INTERVAL = 700` steps
  (p = `FAUNA_SPAWN_P` 0.3, `FAUNA_SPAWN_P_DARK` 0.6 in Dust/Chill,
  never while ≥ 6 alive), species weighted:

  | Species | Glyph | HP | ATK | Pack | Spawns | Hunts | Bounty | Special |
  |---|---|---|---|---|---|---|---|---|
  | spider (0.20) | `x` violet | 25 | 8 | 2–3 | a CAVERN pocket | units ≤ 20 | 2 | lays a WEB voxel at its trail every 8 steps |
  | rabbit (0.18) | `r` dun | 60 | 6 | 1–2 | surface edge | nothing (wanders; fights back) | 6 | dangerous megafauna prey — the mammoth hunt |
  | squirrel (0.15) | `q` chestnut | 30 | 3 | 1–2 | a WOOD voxel (tree-born) | nothing — POACHES: eats nearby FOOD/CROP_RIPE | 4 | never strikes first; SLIPS AWAY (2 moves/step flee) unless ≥ 2 units are adjacent — coordination pins it. `A squirrel raids Colony {id}'s fields` |
  | bird (0.15) | `v` sky-grey | 20 | 12 | 1 | anywhere aloft | SURFACE units ≤ 40, preferring the target with fewest allies within 4 (picks off stragglers) | 2 | flies: 3 moves/step through AIR; flees for good after taking any hit. `A shadow wheels overhead!` |
  | scorpion (0.10) | `c`? no — `t` amber | 22 | 6 | 1–2 | surface/cavern | units ≤ 15 | 2 | POISON sting: victims take 1 HP/step for 20 steps (`poisoned_until`) |
  | snake (0.06) | `S` olive | 80 | 18 | 1 | beneath (substrate) | units ≤ 25 | 5 | swims through SAND (the only burrowing fauna): `Something long moves beneath the sand...` |
  | rodent (0.12) | `n` grey | 12 | 2 | 3–4 | surface edge | nothing — SCAVENGES: eats CORPSE voxels (raids the bone/cannibal economy) | 1 | flees units at 2 moves/step |
  | anteater (0.04) | `A` rust | 150 | 25 | 1 | surface edge | units ≤ 30 | 8 | apex terror: `An anteater stalks the sands!` |
  | hornets (0.05) | `z` violet | 8 | 4 | 6–10 | surface edge / aloft | units ≤ 30 — RELENTLESS (never flees) | 1 | SCOURGE (T48b): flies `HORNET_SPEED`=3/step through AIR; each sting sets `poisoned_until` (venom 1 HP/step for `HORNET_STING_DURATION`=20); the swarm spreads stings to FRESH targets (breadth, not focus). `A hornet scourge boils out of the dark...` |

  Scale note (user): sand kings are scorpion-sized — scorpions are PEER
  rivals; rabbits are megafauna; anteaters are dinosaurs. Spider weight
  0.20, rabbit 0.18, squirrel 0.15, rodent 0.12, bird 0.15, scorpion
  0.10, snake 0.06, anteater 0.04, hornets 0.05 (rare venom scourge).

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

### T48b (hornets — the venom scourge)

Layer: **Requirements** + **Behavioral**. A swarming SCOURGE: a large,
fragile, fast-flying pack of relentless venomous stingers. It wins by
NUMBERS + VENOM BREADTH, not durability or per-hit damage — distinct
from every existing beast. Character, held fixed (do not re-open):

- **SWARM** — one incursion spawns a big pack (`pack = (6, 10)`).
- **FRAGILE** — `hp = 8`; a soldier swats a hornet in one or two hits.
- **FAST / FLYING** — moves `HORNET_SPEED = 3` cells/tick through AIR
  (mirrors the bird case in `_beast_move`).
- **RELENTLESS** — `hunt_range = 30`; homes on the nearest unit and,
  unlike the bird, NEVER sets `fleeing` after striking. Keeps coming
  until killed or the incursion ages out at `FAUNA_RAMPAGE = 500`.
- **VENOM BREADTH (signature)** — each sting sets the target's
  `poisoned_until` (the scorpion mechanism, 1 HP/step). The swarm
  spreads stings to FRESH (un-envenomed) targets, so a cluster of
  hornets adjacent to several units envenoms MANY of them — breadth,
  not focused damage on one.

#### Constants & tables (rote — exact keys/values)

`sandkings.py` (fauna block, ~L127-170):

- `FAUNA['hornets'] = (0.05, 8, 4, (6, 10), 30, 1)`
  — `(weight, hp, attack, pack, hunt_range, bounty)`. Weight 0.05 puts
  it in the `random.choices` roll in `_spawn_incursion` (rare, like
  snake/anteater). Per-species HP/atk/pack/bounty live ONLY here — no
  separate constants for them.
- `FAUNA_EVENTS['hornets'] = "A hornet scourge boils out of the dark - the air itself turns to venom"`
  — MANDATORY (a missing key KeyErrors on spawn). MUST NOT contain the
  word "slain".
- `KEEPER_WRATH = ('spider', 'scorpion', 'snake', 'hornets')`
  — classify as an arena predator so `keeper_release('hornets')` is
  accepted. This propagates automatically through
  `KEEPER_FAUNA = KEEPER_GIFTS + KEEPER_WRATH + KEEPER_NEUTRAL` and the
  dashboard whitelist `GARAGE_SPECIES = KEEPER_FAUNA`.
- In `keeper_release` (~L2560), add `'hornets'` to the disposition-wrath
  tuple so wrath fires on release:
  `if species in ('scorpion', 'spider', 'rodent', 'hornets'):`.
- New constant block beside the other fauna constants (~L169-170),
  provenance-tagged (the fauna block predates `[prov:]`, but the file
  uses it elsewhere; the new lines follow the convention):
  - `HORNET_SPEED = 3            # [prov:C feel=swarm] cells/tick; flies through AIR like the bird`
  - `HORNET_STING_DURATION = 20  # [prov:C feel=venom] sting DoT ticks (1 HP/step); mirrors POISON_DURATION`

`live_view.py` (BEAST_GLYPHS, ~L74-77):

- `BEAST_GLYPHS['hornets'] = "z"` — a buzzing glyph. Verified
  NON-COLLIDING against every live glyph value: terrain `GLYPHS`
  (` ░▓#•%≡~;*£$Ξ&¶|x`), `FIRE_GLYPH` (`^`), `MAW_GLYPH` (`Ω`),
  `UNIT_GLYPHS` (`w s c`), and existing `BEAST_GLYPHS`
  (`x r q v n t S A`). `z` is used by none.
- `BEAST_COLOR` (violet) is shared by all wild beasts — no per-species
  color needed. `build_legend_entries` (~L760) already enumerates every
  `BEAST_GLYPHS` species, so the legend row for hornets is automatic.

#### Behavioral spec — movement, AI, combat

**`_beast_move` (~L4312-4334): give hornets `HORNET_SPEED` steps.**
Only the `steps` selection changes; the move loop (which already permits
AIR moves for any species via the `v == VoxelType.AIR` clause) is
unchanged — hornets fly through AIR, and do NOT get the snake's SAND
burrow.

```
def _beast_move(beast, target):
    if beast.species == 'hornets':
        steps = HORNET_SPEED          # 3 cells/tick, flying
    elif beast.species == 'bird':
        steps = 3
    else:
        steps = 1
    for _ in range(steps):
        # ... existing sign/step-toward loop UNCHANGED ...
        # (AIR always passable; snake also passes SAND; hornets need only AIR)
```

**`_beast_ai` (~L4336-4384): NO new branch required.**
Hornets have `hunt_range = 30 > 0`, so they already fall into the
existing `elif beast.hunt_range > 0:` hunt branch, which yields exactly
the relentless-homing behavior:
- relentless approach ← `ndist <= hunt_range` moves toward `nearest`;
- non-scatter ← hornets are not in `('rodent', 'ant')` (the only
  scatter species);
- no web ← the `if beast.species == 'spider'` web guard excludes them.

Do NOT add a duplicate `elif beast.species == 'hornets'` branch — it
would be dead code identical to the `hunt_range > 0` path. (The
relentless-vs-bird difference is a COMBAT property — no fleeing — handled
below, not an AI property.)

**`_beast_combat` (~L4391-4451): two edits inside the existing
`if beast.hunt_range > 0 or beast.provoked:` block; death/fight-back
path unchanged.**

Edit A — victim selection (add the hornets branch to the pick):

```
if beast.species == 'bird':
    unit, colony = min(adjacent, key=<fewest same-colony allies near>)  # straggler
elif beast.species == 'hornets':
    # SCOURGE breadth: sting a FRESH (un-envenomed) target so the swarm
    # spreads venom widely instead of focus-firing one victim. Hornets
    # are processed sequentially in _fauna_tick, so a poisoned_until set
    # by an earlier hornet THIS tick is visible to later hornets -> the
    # swarm walks venom across distinct units.
    fresh = [uc for uc in adjacent
             if getattr(uc[0], 'poisoned_until', 0) <= self.step_count]
    unit, colony = random.choice(fresh) if fresh else random.choice(adjacent)
else:
    unit, colony = random.choice(adjacent)
```

Edit B — apply venom on a surviving sting (extend the scorpion elif):

```
if unit.take_damage(beast.attack, colony.genome.resilience):
    # UNCHANGED death path: remove unit, set CORPSE, log
    #   "was slain by a hornets"
    ...
elif beast.species == 'scorpion':
    unit.poisoned_until = self.step_count + POISON_DURATION
elif beast.species == 'hornets':
    unit.poisoned_until = self.step_count + HORNET_STING_DURATION
```

Do NOT extend the `if beast.species == 'bird': beast.fleeing = True`
line to hornets — hornets are relentless and MUST leave `fleeing`
untouched (stays False).

Fight-back & death — UNCHANGED and load-bearing: because
`hunt_range > 0`, every adjacent unit strikes back
(`beast.health -= unit.attack`); with `hp = 8` a hornet dies within one
or two `_beast_combat` calls via the generic death path, which drops the
bounty voxel(s) and logs `"The hornets is slain - a feast for the
bold!"`. That line contains "slain" (feeds the chronicle
`is slain -> the Beast-Slayer` epithet at chronicle.py:108). Keep the
GENERIC kill line — do not add a hornet-specific one. (The plural-noun
grammar "The hornets is slain" is acceptable; any optional singular
line MUST still contain "slain".)

Swarm breadth emerges naturally: many hornets each sting their own
adjacent unit, and Edit A steers each toward a not-yet-poisoned victim,
so N hornets adjacent to N units yield venom on multiple units in one
tick — the scourge signature.

#### Acceptance criteria (mechanically verifiable)

Construct beasts like `tests/test_timber.py`
(`Beast('hornets', (x, y, z), 8, 4, 30, 1, spawned_at=0)`), place via
`sim._fauna().append(...)`, place units with `SandKing(colony_id, pos,
UnitType.*)` and append to `colony.units`, drive with
`_beast_ai` / `_beast_combat`. `make_sim` per that file. New tests go in
`tests/test_timber.py` or a new `tests/test_hornets.py`.

1. **HORNET-1 (swarm spawn)** — `sim.keeper_release('hornets')`
   (deterministic; hornets ∈ KEEPER_FAUNA) spawns a pack with
   `6 <= len(sim._fauna()) <= 10` and every beast `.species == 'hornets'`.
   [clause: `FAUNA['hornets']` pack `(6, 10)`]. (Equivalently, monkeypatch
   `_spawn_incursion` / seed so the roll lands on hornets — but
   `keeper_release` is the deterministic path.)
2. **HORNET-2 (venom sting)** — one `Beast('hornets', …, 8, 4, 30, 1)`;
   place a WORKER at an adjacent cell (Chebyshev 1) with enough HP to
   survive one sting; record `pre = unit.health`; call
   `sim._beast_combat(beast)`. Assert
   `unit.poisoned_until == sim.step_count + HORNET_STING_DURATION`
   AND `unit.health < pre` (took the `attack`, resilience-mitigated).
   [Edit B]
3. **HORNET-3 (breadth)** — 3 hornets + 3 units clustered so each hornet
   is adjacent to at least one unit; run one tick
   (`for b in sim._fauna()[:]: sim._beast_combat(b)`). Assert
   `sum(1 for u in units if getattr(u, 'poisoned_until', 0) > sim.step_count) > 1`
   — venom on MULTIPLE units, not a single focus target.
   [Edit A fresh-target rule + sequential processing]
4. **HORNET-4 (relentless)** — after HORNET-2's combat, assert
   `beast.fleeing is False` (contrast the bird, which sets it). The
   hornet keeps hunting. [no fleeing clause]
5. **HORNET-5 (fragile)** — one `Beast('hornets', …, 8, 4, 30, 1)`
   adjacent to a SOLDIER (add attackers or call `_beast_combat` twice so
   fight-back exceeds hp 8); assert the beast is removed from
   `sim._fauna()`, a CORPSE bounty voxel is placed at/near its position,
   and `any("slain" in m for _, m in sim.events)`. [generic death path]
6. **HORNET-6 (roster)** — assert
   `'hornets' in FAUNA and 'hornets' in FAUNA_EVENTS and 'hornets' in
   KEEPER_WRATH and 'hornets' in KEEPER_FAUNA`; `sim.keeper_release(
   'hornets')` grows `sim._fauna()` (accepted, not refused) and fires
   disposition wrath; `BEAST_GLYPHS['hornets']` exists and its value is
   unique across all glyph dicts. [roster + glyph edits]
7. **HORNET-7 (glyph/legend coverage)** — the existing
   `test_legend_covers_every_glyph_and_species`
   (tests/test_live_view.py) still passes unchanged:
   `build_legend_entries` enumerates `BEAST_GLYPHS`, so `hornets` and
   `z` appear automatically. The existing
   `test_sprite_forge_covers_every_voxel_and_species` also passes via the
   `forge_beast` violet-dot fallback (iso_sprites.py:265) — no sprite
   branch required. [live_view/iso_sprites enumerations]

#### Existing-test & consumer impact (flags)

- **test_arena.py (L18-53): NO edit required.** `test_roster_partitions_
  and_small_spider` derives its sets from the LIVE constants
  (`set(KEEPER_WRATH)` etc.) and asserts disjointness + `g|w|n ==
  set(KEEPER_FAUNA)`. Adding `'hornets'` only to `KEEPER_WRATH` keeps the
  partition disjoint and the union valid, so the test passes as-is.
  `test_garage_species_is_the_roster` checks the `is`-identity
  `GARAGE_SPECIES is KEEPER_FAUNA` — still true. (Correction to the task
  brief: these are constant-derived and need no edit.)
- **test_keeper.py: NO edit required.** No hardcoded roster-union
  assertion exists.
- **test_dashboard.py (L87-95): NOT edited, but now EXERCISES hornets.**
  `test_keeper_release_validates_species` loops `for sp in
  GARAGE_SPECIES` and releases each — it will now release `'hornets'`,
  which KeyErrors unless `FAUNA_EVENTS['hornets']` (and the FAUNA tuple)
  exist. This is the guard that makes the mandatory companion-table keys
  non-optional.
- **Spawn distribution shift (flag):** adding weight 0.05 makes the
  `_spawn_incursion` `random.choices` weights sum 1.00 → 1.05 (hornets
  ≈ 4.76%; all others shrink proportionally). NO test asserts a
  natural-spawn species distribution — only `'cat'`, which is
  keeper-released. `test_timber.py:132` reassigns its beast to `'rabbit'`
  before asserting, so it is unaffected.
- **play_kit.py `_SPECIES` (L347): OPTIONAL parity.** Add `'hornets'`
  so the bare REPL command `hornets` works; `release hornets` already
  works without it. Non-blocking.
- **iso_sprites.py `forge_beast`: OPTIONAL sprite branch.** A dedicated
  hornet-swarm sprite may be added, but the existing `else` violet-dot
  fallback (L265) already satisfies
  `test_sprite_forge_covers_every_voxel_and_species`.
- **chronicle.py SALIENCE: OPTIONAL.** A salience row for the
  scourge-arrival line may be added; not required for the battery.

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
    within Chebyshev 3) - M13 is TWO anchors, lexicon now 35 seeds.
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

- 2026-07-11 (T48b hornets, spec draft): added the venom-scourge sub-
  requirement. FAUNA tuple `(0.05, 8, 4, (6,10), 30, 1)`; new constants
  HORNET_SPEED=3, HORNET_STING_DURATION=20; glyph `z`; KEEPER_WRATH gains
  'hornets'. AI reuses the hunt_range>0 branch (no new branch);
  _beast_move adds the 3-step case; _beast_combat adds fresh-target
  selection + venom application, relentless (no fleeing). Awaiting Haiku
  impl + Sonnet verification against HORNET-1..7.
