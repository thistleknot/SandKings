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

## Cross-couplings (the holistic synthesis — Phase 2)

- **crops → crickets**: a large swarm damages nearby `CROP`/`CROP_RIPE` (a pest); the keeper's seeds feed
  the crickets.
- **crickets → guppies**: crickets near water fall in (amplified during a flood) → a guppy food/breeding
  boost; guppies' diet extends to **crickets + crop droppings + in-water plant growth**.
- **fauna → crickets**: an active incursion culls the swarm (predator control).
- **weather**: flood drowns crickets but washes them to the guppies; drought thins guppies+crops while
  crickets thrive; frost kills crickets and surges fauna.

## Snares (Phase 3)

`string`/`toothpick` (already `tech.py:MATERIALS`, today → bow/spear) gain a **weir/snare** use that
passively converts nearby `guppy_pop`/`cricket_pop` → FOOD (a trap; keeper can drop them by the pond).
The existing `WEB` voxel (spider silk, "snares a step") over water also catches guppies/crickets.

## Intelligence payoff — the maw learns seasonal foraging (Phase 4)

A 4th maw directive dim **forage-mode** (aquatic / terrestrial / hunt bias), wired into the *worker*
forage-target selection (not the 7-action soldier space): the maw's learned directive biases which FOOD
the colony seeks. With season-phase already in its obs, the food/survival reward teaches it to forage
aquatic in Flood, hunt crickets in Dust, chase bounty in Chill.

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
