# SPEC — Domestication: taming wild beasts (war, labor, livestock)

Status: IN PROGRESS (A World Alive arc). Baseline-ON, opt-out `--no-domestication`, in `_GATE_NAMES`,
byte-identical off. Depends on the fauna system (SPEC_FAUNA_ECOLOGY, SPEC_ARENA). Greenfield: `Beast` had no
owner/tame concept; the `laboring_for` thrall pattern on units is the ownership template mirrored here.

## Why

The tank has wild beasts that are pure threat. The user's vision: spawn should be able to **domesticate** them —
harmless ones easily, dangerous ones barely ("you don't tame a lion") — for war, labor (ants dig, bees make
honey, hornets fly air-support), and livestock, maintaining a feeding economy. This spec covers the **core**
(tame → own → friend-or-foe); upkeep and per-species roles are DM3/DM4 (later).

## DM1 — Ownership (getattr-guarded, no dataclass change)

A tamed beast carries `owner` (colony_id), attached dynamically like `unit.defiance` — `getattr(beast, 'owner',
-1)`, default -1 = wild. No `Beast.__init__` change → old checkpoints load; the friend-or-foe reads are
**owner-inert** (a `colony.colony_id == owner` skip never fires while `owner == -1`), so the hot combat loops are
byte-identical until something is actually tamed.

## DM2 — Tame attempt (`_taming_tick`, gated, danger-scaled)

Called from `_fauna_tick` only when `DOMESTICATION_ENABLED` (byte-identical off). For each **wild** beast, a
colony with a living unit adjacent (Chebyshev ≤ 1) rolls a danger-scaled success:
`p = TAME_BASE · (1 − hunt_range / TAME_DANGER_CEIL)`, clamped: `p ≤ 0` (hunt_range ≥ ceil) → **untameable**.
- hunt_range is the danger axis (SPEC_ARENA): 0 (ant, beetle, rabbit, mouse, cricket) → easy; scorpion(15) →
  hard; hornets(30) → very hard; cat(60) → near-impossible; anything ≥ `TAME_DANGER_CEIL=65` → impossible.
- On success: `beast.owner = colony_id`, `provoked = False`, event "House X tames a {species}!". First adjacent
  living colony wins the roll.
- Constants (sandkings.py): `TAME_BASE=0.03`, `TAME_DANGER_CEIL=65.0`.

## DM2b — Friend-or-foe (`_beast_ai`, `_beast_combat`; owner-inert, byte-safe)

A tamed beast never turns on its owner:
- `_beast_ai` nearest-target selection **skips the owner colony** — so a tamed predator naturally targets the
  nearest NON-owner (i.e. enemy) unit, becoming a war asset.
- `_beast_combat` excludes the owner's units from the adjacency list — no friendly fire.
Both are a single `owner = getattr(beast,'owner',-1)` + `if colony.colony_id == owner: continue`, inert (and thus
byte-identical) until a beast is tamed.

## DM2c — Rendering

`live_view.py` tints an owned beast `TAMED_BEAST_COLOR` (bright friendly green) instead of the predator/neutral
danger class, so a domesticated beast reads as *yours* at a glance.

## DM3 — Feeding upkeep (`_tame_upkeep`, gated) — IMPLEMENTED

Every `TAME_UPKEEP_INTERVAL` steps a tamed beast eats `TAME_UPKEEP` of its owner's food. An owner that cannot
feed it (`food_stored < TAME_UPKEEP`) for `TAME_STARVE_LIMIT` consecutive intervals loses it — the beast goes
feral (`owner → -1`, event "an unfed {species} slips its leash"). A dead/absent owner also frees it. Husbandry
is a real cost — you must maintain a food system. Gated + owner-guarded → byte-identical off. Constants:
`TAME_UPKEEP=3.0`, `TAME_UPKEEP_INTERVAL=100`, `TAME_STARVE_LIMIT=3`.

## DM4 — Tamed roles (`_tamed_work`, gated) — IMPLEMENTED

A tamed **harmless** beast (`hunt_range == 0`, owner ≥ 0) labors instead of running its wild AI (routed in
`_beast_ai`; a tamed beast also no longer deposits the DANGER alarm). By species:
- **Foragers/livestock (ant, rodent, beetle, squirrel, …):** harvest an adjacent `FOOD`/`CORPSE` and deliver
  `TAME_FORAGE_YIELD` to the owner's maw (offsets the DM3 upkeep — husbandry pays), leaving a **`FOOD_TRAIL`**
  scent (the first real use of that pheromone channel); else move to the nearest food; else follow the owner.
- **Diggers (ant/rodent/beetle):** with no food nearby, excavate one `SAND` cell toward the owner's maw and stamp
  its ownership — extending the warren.
- **Bees:** produce **honey** (`colony.honey`, getattr) = `HONEY_YIELD` food to the hive each work tick, and
  pollinate (sow a `CROP` on an adjacent `TILLED` cell). `bee` is a new keeper-gift species (glyph `∵`).
- **War beasts (tamed predators, `hunt_range > 0`):** keep the normal predator AI — but DM2b friend-or-foe makes
  them hunt the nearest NON-owner (enemy) unit, so a tamed spider/hornet/cat is automatic **air/ground support**.

Constants: `TAME_FORAGE_YIELD=8.0`, `HONEY_YIELD=2.0`. Gated + owner-guarded → byte-identical off.
Deferred still: an explicit livestock *slaughter* verb (today livestock pay via forage yield), a honey→food
conversion UI, and richer pollination.

## Acceptance (`tests/test_domestication.py`)

- Gate default off.
- A harmless (hunt_range 0) beast adjacent to a unit is tamed (owner = that colony); a beast at the danger
  ceiling is never tamed.
- A tamed beast strikes neither in `_beast_combat` nor targets in `_beast_ai` its owner's spawn.
- Gate off: `_fauna_tick` never tames even with a guaranteed roll — full battery byte-identical off.
