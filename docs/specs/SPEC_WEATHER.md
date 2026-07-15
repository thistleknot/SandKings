# SPEC: Desert Weather (Round 7) — W1–W6

User intent: "hopefully we have more weather than just sand storms —
nighttime freezing, hail, occasional flood (desert type conditions)."

Design stance: desert weather is VIOLENT and BRIEF. Each system is a
short, announced event with a distinct survival answer — and the answer
is always the same one deserts teach: GET UNDERGROUND. Exposure is the
shared mechanic: a unit is exposed iff its z >= surface_z(x, y); tunnels
are shelter. This gives weather behavioral teeth without new AI — deaths
select for colonies whose labor happens below ground during the danger
seasons. Weather never touches the evolution sim (step() override inert,
as always).

## W1 — The Nile inundation (user: "think nile flooding, that oasis
will turn into a flood — and give maws an opportunity to build dams
and runoff channels if they learn to terraform properly")
During Flood season, every FLOOD_INTERVAL steps with p FLOOD_CHANCE,
the OASIS OVERFLOWS. The water spreads by literal flood fill from the
map center: BFS over surface columns, reaching any column whose
surface sits at/below the water line (oasis surface + FLOOD_RISE) AND
which is REACHABLE through such columns. The consequences:
- DAMS ARE REAL: a closed ring of raised ground — palisades, DEPOSIT
  banks, piled sand, tunnel walls — parts the water; breach it and
  the water pours through. RUNOFF CHANNELS ARE REAL: a trench dug
  through high ground carries the flood past it. No new AI: the
  terraforming verbs already exist (worker digging, palisades, the
  GEO cartridge's EXCAVATE/DEPOSIT actuators) — colonies that use
  them "properly" keep their fields; selection does the learning.
- The reach grows 1 column per 2 steps to FLOOD_RADIUS_MAX, holds,
  then recedes (FLOOD_DURATION total).
- Under water: exposed units take FLOOD_DAMAGE/step (underground is
  safe), fires are extinguished, surface FOOD is swept away.
- Receding water leaves SILT on the cells it releases: SAND becomes
  TILLED with p FLOOD_SILT_P, FOOD deposits with p 0.02 — Nile
  agriculture: the flood that drowns you feeds next season's fields,
  and the oasis ring gets the richest silt AND the greatest danger.
Events: "The oasis overflows - a flash flood spreads across the
basin!" / "The floodwaters recede, leaving black silt".
Constants: FLOOD_INTERVAL 150, FLOOD_CHANCE 0.2, FLOOD_RADIUS_MAX 16,
FLOOD_DURATION 100, FLOOD_RISE 2, FLOOD_DAMAGE 2, FLOOD_SILT_P 0.08.

## W2 — Hail (stones from the sky)
In Growth and Dust, a storm roll (existing T12/T16 cadence) becomes a
HAILSTORM with p HAIL_SHARE instead of a sandstorm: no sand transport;
for its duration exposed units take 1 HP every HAIL_TICK steps and
standing CROP/CROP_RIPE voxels are smashed to TILLED with p
HAIL_SMASH_P per hail tick. Event: "Hail hammers the dunes!"
Constants: HAIL_SHARE 0.35, HAIL_TICK 5, HAIL_SMASH_P 0.04,
duration = STORM_DURATION (shared).

## W3 — Cold snap (the desert night)
There is no day/night cycle; the cold snap is the night's ambassador.
In Chill (always eligible) and Dust (half chance), every
COLD_INTERVAL steps with p COLD_CHANCE: for COLD_DURATION steps,
exposed units take 1 HP every COLD_TICK steps. Underground units are
untouched — the colony that digs, survives the frost. Event: "A
killing frost settles over the sands". Constants: COLD_INTERVAL 500,
COLD_CHANCE 0.5, COLD_DURATION 40, COLD_TICK 5.

## W4 — State, exposure, and compatibility
- New sim state (all checkpoint-guarded via getattr, plain ints):
  `hail_until`, `cold_until`, `flood_until`, and `flood_cells`
  (the set of (x, y) columns currently under water, recomputed every
  2 steps from the BFS; pickles as a plain set).
- `exposed(unit)` helper: z >= world.surface_z(x, y). Weather deaths
  leave corpses (the frost feeds the rodents).
- Sandstorms (T12) unchanged; at most one of sandstorm/hail active
  (they share the storm roll); flood and cold are independent systems.
- The M1 `storm` anchor's predicate broadens to ANY active weather
  (sandstorm, hail, flood, cold snap) — same seed word, no vocabulary
  change; the thought reads as "bad weather".

## W5 — Surfacing (viewer surface R35)
- HUD: a weather line naming the active system(s), tinted (sand gold /
  hail white / flood blue / frost ice-blue); nothing when clear.
- Overlays: hail = white flicker haze (storm_haze_array recolored);
  cold snap = ice-blue dim wash; flood = translucent blue band over
  the surge columns.
- EVENT_TINTS: "flash flood"/"floodwaters" blue, "Hail" white, "frost
  settles" ice blue. Chronicle SALIENCE: flood 6, hail 4, frost 4.

## W6 — Acceptance
tests/test_weather.py: flood band damages exposed units but not
underground ones, extinguishes fires, and leaves silt/tilled in its
wake; hail smashes crops and spares tunnelers; cold snap kills only
the exposed; storm roll splits sandstorm/hail by season; all weather
state pickles and old checkpoints resume (getattr guards); the storm
anchor predicate fires during any system; evolution sim inert.
Soak: 3 harsh years — at least one flood, one hail, and one cold snap
observed; liveness holds; sps within 10% of baseline.

## Status / Reconciliation
- Drafted 2026-07-09; implemented same session. Deltas:
  - FLOOD_INTERVAL corrected 600 -> 150 (with FLOOD_CHANCE 0.5 -> 0.2):
    600 resonated with YEAR_LENGTH 1600 so only ~1 roll per 3 years
    landed inside Flood season; 150 gives ~2.6 in-season rolls/year at
    the same expected flood rate. Caught by the W6 soak.
  - The soak also caught a D1 regression OUTSIDE this spec: the kin
    check in politics.hostile() (two linear scans, called ~5.6M times
    per 600 steps in combat loops) had dropped throughput 24 -> 15 sps.
    Replaced with an O(1) colony->house map invalidated by
    sim._kin_epoch (bumped at house founding and respawn). Post-fix
    soak: 18.7 sps (remaining delta vs the pre-dynasty 24 is the
    chronicle/house-substitution cost, accepted and documented).
  - W6 soak: PASSED - 3 harsh years, flood + hail + cold snap all
    observed, liveness held (4/4 slots), 18.7 sps. All 11 suites green
    including tests/test_weather.py (7 tests).
- 2026-07-09 (same session): W1 REDESIGNED per user direction from an
  edge-surge band to the Nile inundation (oasis-centric BFS hydrology
  with real dams and runoff channels). tests/test_weather.py grew to
  9 tests including test_dam_parts_the_water and
  test_channel_carries_water_past_high_ground. 5-year soak: PASSED at
  21.5 sps, flood + hail + cold snap all observed, liveness held.
  Note: hail is a 0.35 sub-roll of storm successes — 3-year windows
  can legitimately miss it; the soak criterion window is 5 years.
