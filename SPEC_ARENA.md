# SPEC: Arena Mode — the keeper's gifts, wrath, and neutrals (AR1–AR7)

The keeper's hand, reorganized into a Dwarf-Fortress "arena" / SimCity
"disaster" console. What the god drops onto the sand is classified by intent:
GIFTS to feed and teach, WRATH to torment (non-lethal discomfort + real
predators), NEUTRALS that just wander (and bite back if cornered).

## AR1 — The roster, classified
Canonical classification lives in `sandkings.py` (single source; dashboard
imports it):
- **KEEPER_GIFTS = ('cricket', 'ant', 'small_spider')** — food and learning.
  `small_spider` is NEW: weak, non-hunting, high food-bounty prey the maws
  learn to catch. FAUNA row `(0.0, 10, 2, (2,4), 0, 3)` (weight 0 =
  keeper-only), event "Small spiders are set loose - easy prey to learn on".
- **KEEPER_WRATH = ('spider', 'scorpion', 'snake')** — the arena predators
  (the existing `spider` is the LARGE, web-spinning one). Real threats.
- **KEEPER_NEUTRAL = ('squirrel', 'rabbit')** — ambient fauna; they flee and
  bite back but do not hunt.
- `KEEPER_FAUNA = KEEPER_GIFTS + KEEPER_WRATH + KEEPER_NEUTRAL`.
- `cat` remains the special apex disaster (its own verb); `drought` and the
  arena temperatures (AR3) are non-fauna wrath.

## AR2 — Release validated against the roster
`keeper_release(species)` accepts any species in `KEEPER_FAUNA` (unchanged
spawn logic; still `_hand_stayed`-gated by PS5). `dashboard.GARAGE_SPECIES`
becomes `KEEPER_FAUNA` (imported, not a separate hand-maintained tuple), so
the API and the roster can never drift.

## AR3 — Arena temperature (uncomfortable, NOT lethal)
A keeper-driven temperature track, SEPARATE from the natural (lethal) frost
of SPEC_WEATHER W3. `keeper_temperature(direction)` with direction in
{'heat','cold'} (`_hand_stayed`-gated): sets `arena_heat_until` /
`arena_cold_until` = `step + ARENA_TEMP_DURATION` (60) and logs
"The keeper turns the air to a blistering heat" / "...to a biting cold".
While active, every `ARENA_TEMP_TICK` (3) steps, `_arena_tick`:
- drains each colony's `maw.food_stored` by `ARENA_FOOD_DRAIN` (0.6) per
  EXPOSED unit (capped at ARENA_DRAIN_CAP=6 units), floored at 0 —
  thermoregulation costs the hoard;
- wilts crops with prob `ARENA_WILT_P` (0.05): CROP_RIPE→CROP, CROP→TILLED.
NEVER reduces unit HP (the discomfort is pressure, not death — per the
"nothing lethal" rule). Heat and cold can run at once; each expires on its
own timer. The mayhem is emergent: drained hoards and wilted fields drive
hunger, raids, and migration.

## AR4 — Natural weather unchanged
The W3 cold snap (`cold_until`, lethal frost) and hail stay exactly as they
are — arena temperature is an ADDITIONAL keeper track, not a replacement. A
maw can suffer a natural frost and a keeper heat wave in the same run.

## AR5 — Surfaces
- **Endpoint** `POST /api/keeper/temp {dir:'heat'|'cold'}` → keeper_temperature.
- **Dashboard** console regrouped into three labelled groups — GIFTS (Feed,
  Crickets, Ants, Small Spider, Tech Gift), WRATH (Large Spider, Scorpion,
  Snake, Heat, Cold, Withhold, The Cat), NEUTRAL (Squirrel, Rabbit).
- **build_state weather** list gains "heat wave"/"cold snap" while the arena
  timers run (distinct from natural "killing frost").
- **Live view**: keeper keys regrouped (see AR6); the weather HUD line shows
  the arena bands; EVENT_TINTS colour the heat (orange) and cold (pale blue)
  arena lines and the new release events.

## AR6 — Live-view keys (regrouped, arena console)
GIFTS: `1` food(manna) · `2` crickets · `3` ants · `4` small spider ·
`5` tech gift. WRATH: `6` large spider · `7` scorpion · `8` snake ·
`9` drought(toggle) · `0` cat · `[` cold · `]` heat. NEUTRAL: `n` squirrel ·
`b` rabbit. `T` speak (unchanged). Legend + help text + `build_hud`'s keeper
lines updated to the three groups.

## AR7 — Acceptance (tests/test_arena.py)
- `KEEPER_GIFTS/WRATH/NEUTRAL` partition `KEEPER_FAUNA` (disjoint, union);
  `small_spider` in FAUNA, weak (hp<15) and high-bounty (>=3), hunt 0.
- `dashboard.GARAGE_SPECIES is KEEPER_FAUNA` (no drift); release of a gift, a
  wrath predator, and a neutral each spawns beasts.
- `keeper_temperature('heat')` sets `arena_heat_until` and, after stepping,
  drains a fed colony's food but leaves every unit's HP unchanged (non-lethal);
  crops may wilt. `'cold'` likewise.
- `/api/keeper/temp` wired; a bound keeper (`keeper_bound`) can't release or
  change temperature (PS5).
- state pickles; `EnhancedSandKingsSimulation.step` stays inert
  (`_arena_tick` not in its co_names).

## Status / Reconciliation
- Drafted 2026-07-10; implemented the same session (the mayhem mandate).
- SPEC_WEATHER note: arena temperature is a keeper track distinct from W3.
