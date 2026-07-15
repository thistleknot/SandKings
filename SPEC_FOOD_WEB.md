# SPEC — The Terrarium Food Web (weather-rotated RPS ecosystem)

Status: IN PROGRESS (Phase 1 SHIPPED 2026-07-14). Baseline-ON per guild (opt-out flags).

## Premise

The guppy pond (SPEC_GUPPIES) is one isolated aquatic loop. The **sandkings are the predators** — a
standalone pike was redundant (explored + rejected: logistic-damped predator-prey just damps to a static
point). The real design is a **holistic, weather-rotated food web**: three harvestable guilds whose
abundance rotates with the four seasons, so **no single foraging strategy is always best** and colonies
must adapt by season. This directly feeds the maw RL (its obs already carries season-phase, Bundle 4).

## The three guilds (weather rotation = intransitive coexistence via a fluctuating driver)

| Guild | Booms in | Model | → colony food via |
|-------|----------|-------|-------------------|
| **Aquatic** — guppies + algae | Flood/Growth (wet) | `guppy_dynamics` (SPEC_GUPPIES) | oasis FOOD voxels |
| **Terrestrial** — crickets | **Dust (dry/warm)** | `cricket_dynamics` (Phase 1) | land FOOD voxels + fall into water |
| **Fauna bounty** — incursions | Dust/Chill (dark, 2× spawn) | `FAUNA` beasts | CORPSE voxels on kill |

Each season favours a different food: aquatic (Flood/Growth) → insects (Dust) → beast-bounty/lean (Chill).

## Cross-couplings (the holistic synthesis — Phase 2, SHIPPED 2026-07-14)

- **crops → crickets**: cricket `forage` = standing crop density; a big swarm (>0.5·CAP) nibbles up to
  `CRICKET_CROP_DMG` crops/tick (a pest) — the keeper's seeds feed the crickets. (`_cricket_tick`.)
- **crickets → guppies**: a normalized `_cricket_influx` (=swarm fraction × `CRICKET_INFLUX`, amplified to
  `CRICKET_FLOOD_INFLUX` during a flood) + a crop-`GUPPY_DROPPINGS` term feed the shoal via
  `guppy_dynamics(..., extra_food=...)` — guppies' diet now extends beyond algae to crickets + droppings.
- **fauna → crickets**: active `CRICKET_PREDATORS` beasts (spider/bird/scorpion/anteater) cull the swarm
  by `CRICKET_CULL` each (predator control).
- **weather**: flood drowns crickets but washes them to the guppies (feast); drought thins guppies+crops
  while crickets thrive (dry-boost); frost kills crickets and surges fauna.
Verified: `test_guppy_extra_food_lifts_breeding` (extra_food lifts breeding + 3-arg back-compat), full
battery 53/53 byte-identical, live smoke clean.

## Snares (Phase 3, SHIPPED 2026-07-14)

A `WEB` voxel (spider silk OR a keeper string/toothpick weir) passively catches guppies (near water) or
crickets (on land) into FOOD each `SNARE_TICK` — no foraging unit needed (`_snare_tick`, `SNARE_YIELD`).
Dropping `string`/`toothpick` by the water (`keeper_material` + `_near_water`) sets a snare (a WEB weir)
instead of crafting a weapon. Gated `SNARES_ENABLED` baseline-on (`--no-snares`). Verified:
`tests/test_snares.py` (web-near-water catches guppies→FOOD / web-on-land catches crickets / gate-off
no-op), full battery 54/54 byte-identical.

## Intelligence payoff — the maw learns seasonal foraging (Phase 4, SHIPPED 2026-07-14)

`MAW_DIRECTIVE_DIM` 3→4: a **forage-mode** dim (d3), warm-started neutral (0.5; no genome instinct), that
the RL learns. `_forage_mode(colony)` maps d3 → aquatic (<0.33) / hunt (<0.67) / terrestrial; wired into
the *worker* forage-target selection (`_find_food_target(..., prefer=...)`, `FORAGE_PREFER_DISCOUNT`) —
the maw's learned directive discounts the preferred guild's distance so foragers steer to oasis FOOD
(aquatic) / land FOOD + ripe crops (terrestrial) / CORPSE (hunt). Gated by `MAW_RL_ENABLED` → `prefer`
is None when off (byte-identical). With season-phase in its obs, the food/survival reward teaches it to
forage aquatic in wet, hunt crickets in Dust, chase bounty in Chill.
**Observability**: HUD "Pond:" + "Swarm:" abundance lines (`live_view.build_hud_entries`); `EVENT_TINTS`
for cricket/snare drama. Verified: `tests/test_forage_mode.py` (bias + classification), maw suite + battery
55/55 byte-identical, headless HUD check, live-view suite green.

## Phase 1 — Crickets (SHIPPED 2026-07-14)

A persistent land population mirroring the guppy template. `sandkings.py`:
- Constants `CRICKET_*` (beside the guppy block); pure `cricket_dynamics(cricket, forage, dry, flood,
  frost) -> (cricket, catch)` — logistic breeding on plant matter, `CRICKET_DRY_BOOST=1.6` in Dust,
  `CRICKET_DROWN`/`CRICKET_FROST` losses in flood/Chill; surplus → land FOOD voxels (map-wide).
- `_cricket_tick` (beside `_guppy_tick`), `_cricket_drama` (boom/collapse/recovery), `_spawn_cricket_pack`
  (occasional visible cricket Beasts — ambient neutral prey, NOT an incursion). The single-incursion gate
  in `_fauna_tick` now ignores crickets, so ambient crickets don't block wild incursions (byte-identical
  when no crickets exist).
- Gate `CRICKETS_ENABLED` default False (battery byte-identical); entrypoint flips on (opt-out
  `--no-crickets`); in `run_tests._GATE_NAMES`.
- Verified: 8-test dynamics battery (`tests/test_crickets.py`) — bounded / persists / dry-boom /
  flood+frost crash / catch floor / gate-off no-state / gate-on lives. Full battery 53/53 byte-identical.

## Open (Phases 2–4)

Cross-couplings + guppy-diet extension + weather-rotation tuning (2); snares (3); the maw forage-mode
lever + HUD/drama observability (4). See `docs/decisions/` and the plan.
