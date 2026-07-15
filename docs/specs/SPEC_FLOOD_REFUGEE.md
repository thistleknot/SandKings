# SPEC: Flood, Refugees & the Irrigation Edge — FR1…FR3

Status: DRAFT (spec-first; not yet implemented). Governing intent (user, verbatim):

> "the oasis/flooding … creates the initial conditions for both supplement and devastation. If harnessed
> properly, it can give an edge, but if ignored, it can be a detriment and creates its own dynamic pressures
> (flooding = devastation and pressure for food as well as loss of life, unless channeled then has the
> potential for farming surplus — crops will never suffer from heat swells)."
> "as soon as flooding happens, disaster strikes which creates a refugee type status. People can overthrow
> whoever is devastated, and those who are must search for food as they can't access their tunnels."
> "food accumulation is a thing. These creatures need to gather and store food."

The oasis is a **double-edged initial condition**: a water budget that either feeds a channeled civilization or
drowns a careless one. Much of this ALREADY emerges from shipped systems (catalogued below); this spec closes
the three gaps the intent names — heat-immune irrigation, the flood-refugee state, and overthrow of the
devastated. Baseline-ON, opt-out `--no-flood-refugee`, in `_GATE_NAMES`, byte-identical off.

---

## Already emergent (do NOT rebuild — cite and lean on these)

The double-edge is largely realized today; this spec only adds to it.

- **Devastation** — a flood (`_weather_tick` W1 Nile inundation → `flood_cells`) drowns exposed units
  (`_weather_kill(..., _flood_damage(colony))`, `FLOOD_DAMAGE`), and washes out the cricket swarm
  (`CRICKET_DROWN`) → a food shock. Frost (`cold_until`) and hail (`hail_until`, `HAIL_SMASH_P` smashes crops)
  add to the pressure.
- **Channeling pays** — a colony that dug a **reservoir** takes *halved* flood damage
  (`_flood_damage` → `HYDRO_RESERVOIR_ABSORB`); dams/dug channels **steer** the inundation
  (`_compute_flood_cells` respects raised banks / trenches — terraforming IS flood control); receding water
  leaves **silt** that tills sand for farming (`FLOOD_SILT_P`); a unit can **raft** rather than drown.
- **Irrigation surplus** — oasis and water-adjacent fields grow faster (`_grow_crops` → `OASIS_GROWTH_MULT`,
  `_water_adjacent` → `HYDRO_IRRIG_GROWTH`) and grow **through** the Dust drought and the Chill frost that
  STALL/KILL dryland crops (the oasis branch bypasses the season penalty).
- **Food accumulation** — colonies gather and store food in the maw (`maw.food_stored`, `maw.eat`); the hoard
  gates war footing (`WAR_CHEST`), winter survival (`SPEC_WINTER`), and tech (`TECH_GRAIN_COST`). Already a
  first-class resource — FR2 makes losing access to it the core of the refugee pressure.
- **Heat already wilts** — `_arena_temp_tick` (heat wave, `arena_heat_until`) drains hoards per exposed unit
  and wilts crops (`ARENA_WILT_P`: `CROP_RIPE`→`CROP`, `CROP`→dead `TILLED`).

---

## FR1 — Irrigated crops are immune to the heat swell

**Gap:** `_arena_temp_tick`'s heat wilt hits EVERY crop indiscriminately, so the intent's "crops will never
suffer from heat swells [if channeled]" does not pay off — the irrigation edge is missing under acute heat.

**Requirement.** During a heat wave, a crop cell that is **irrigated** — `in_oasis(x, y)` OR
`_water_adjacent((x, y, z))` (beside standing WATER: a channel/reservoir/pond) — MUST NOT wilt. Dryland crops
wilt as today. (Cold/hail are unchanged; this is heat-specific — water buffers heat, not frost.)

**Behavioral (pseudocode, in `_arena_temp_tick`'s crop loop, gated).**
```
for each CROP / CROP_RIPE cell p=(x,y,z):
    if FLOOD_REFUGEE_ENABLED and hot and (in_oasis(x,y) or _water_adjacent(p)):
        continue                      # irrigated: heat cannot wither it
    ... existing ARENA_WILT_P wilt ...
```
**Contract.** Guarantee: an irrigated crop never transitions on a heat tick; a dryland crop's wilt is
unchanged. Identity: gate off → the exemption is skipped → today's behavior exactly (byte-identical).

**Acceptance FR1.** Under a forced heat wave with `ARENA_WILT_P=1.0`: a crop beside WATER (and one in the
oasis) survives every heat tick; a dryland crop wilts. Gate off → both wilt (battery byte-identical).

---

## FR2 — Flood-refugee status (cut off from the tunnels, driven to the surface)

**Gap:** a flooded colony keeps operating normally; there is no "disaster → refugee" consequence, no loss of
tunnel access, no forced surface foraging.

**Requirement.** When a colony's **maw is inundated** — `maw.position (x,y) ∈ flood_cells` (its warren mouth
is underwater) — the colony enters a **REFUGEE** state for `REFUGEE_DURATION` steps after the water recedes
(a `refugee_until` step stamp; getattr-guarded, pickled). While a refugee:
- **Tunnels are sealed:** its underground stores/warren are unreachable — units may not descend below the
  surface to forage or shelter (they cannot access the flooded tunnels), so they must **surface-forage**
  (bias `_find_food_target` / movement to the surface z; no digging-down this window).
- **Weakened:** the disruption is a real cost — no new war footing is entered while refugee (it is reeling,
  not raiding), and its confidence/agitation reflect the ruin (a dread spike via the disposition system).
Recovery: once `refugee_until` passes AND the maw cell is dry, the colony returns to `POP_ACTIVE` and normal
subterranean life resumes.

**Structural.** Reuse the `pop_state` lifecycle (add `POP_REFUGEE`) OR a lighter `refugee_until: int` stamp
(preferred — no interaction with the DORMANT/SUCCESSION slot machinery). Set in `_weather_tick`/flood handling
when `maw ∈ flood_cells`. New reads are getattr-guarded (old pickles resume clear).

**Behavioral (pseudocode).**
```
# in the flood step, per living colony:
if colony.maw.position[:2] in flood_cells:
    colony.refugee_until = step + REFUGEE_DURATION
    (log once) "House {name} is drowned out — its people scatter as refugees"
# a refugee's foragers:
if is_refugee(colony):           # step < refugee_until
    forbid dig-down / tunnel-shelter; force surface foraging target
    skip war-footing entry (SPEC war loop)
```
**Contract.** Require: flood handling runs (always-on weather). Guarantee: `refugee_until` ∈ ℤ; a refugee
never enters war footing and never descends; state auto-clears. Identity: gate off → `refugee_until` never set,
`is_refugee` always False → byte-identical.

**Acceptance FR2.** Force a flood over a colony's maw: it becomes a refugee (`refugee_until > step`), its
foragers target only surface cells, and it enters no war footing that window; after `REFUGEE_DURATION` + dry
maw it returns to `POP_ACTIVE`. Gate off → no refugee state (battery byte-identical).

---

## FR3 — The devastated are overthrown

**Gap:** a wrecked colony is not preferentially attacked; the intent's "people can overthrow whoever is
devastated" is unmodeled.

**Requirement.** A **refugee (devastated) colony is a preferred target of opportunity**: rivals weight it up in
`_select_war_target` (kick a house while it is down — reuse the SPEC_SCARCITY_WAR "raid the weak" logic and the
`power()` index, which a refugee already scores low on). Optionally, its own succession pressure rises (a
devastated maw is more easily challenged — a hook for SPEC_DYNASTIES succession / SPEC_MADNESS, not required in
FR3's first cut).

**Behavioral (pseudocode, in `_select_war_target`, gated).**
```
score(candidate) *= REFUGEE_TARGET_MULT if is_refugee(candidate) else 1.0
```
**Contract.** Guarantee: target ranking is unchanged when no colony is a refugee. Identity: gate off (or no
refugees) → selection identical → byte-identical.

**Acceptance FR3.** With one colony a refugee and an aggressor at war footing, the aggressor selects the
refugee over an equally-weak non-refugee. Gate off → selection identical.

---

## Constants (sandkings.py, provisional)

```
FLOOD_REFUGEE_ENABLED = False   # gate (module default False -> byte-identical; entrypoint --no-flood-refugee)
REFUGEE_DURATION   = 120        # steps a drowned-out colony stays a refugee after the water recedes
REFUGEE_TARGET_MULT = 1.6       # FR3: how much rivals prefer a devastated colony as a war target
# FR1 reuses ARENA_WILT_P / in_oasis / _water_adjacent; no new constant.
```

## Cross-references
- **SPEC_HYDRO / SPEC_WEATHER** — own `flood_cells`, `_weather_tick`, `_flood_damage`, reservoir absorb, silt.
- **SPEC_TERRARIUM_LIVENESS / SPEC_SUCCESSION** — own `pop_state`; FR2 prefers a lighter `refugee_until` stamp
  over a new `pop_state` to avoid the DORMANT/SUCCESSION slot machinery.
- **SPEC_SCARCITY_WAR** — the "raid the weak" precedent FR3 reuses in `_select_war_target`.
- **SPEC_WINTER / SPEC_FLORA** — the hoard-vs-starve and crop systems FR1/FR2 pressure.
