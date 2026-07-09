# Spec: The Machine Age (wreck, microcontroller VM, devices, tinkerer)

STATUS: **DRAFT — Round 3, implements after SPEC_POLITICS.** Owns shared
T-numbers **T28–T40**. Governs: `machines.py` (new), wreck terrain stage,
step phase 3f, worker AI v3, viewer R25–R27, anchor M11 (`machine`).
User-approved additions beyond the base design: **T39 LIBRARY CARTRIDGES**
and **T40 RADIATION** (see end).

## Constants (sandkings.py block + machines.py)

WRECK_SIZE (5,5,3); WRECK_SALVAGE 8–12 (side walls + floor only, never the
25 roof cells; ≥2 at interior level so mining opens a crawl-hole);
WRECK_BURY_DEPTH 2; WRECK_NOTICE_RANGE 6; SALVAGE_MINE_TIME 8;
VM_TICK 5; VM_FUEL 64; VM_MAX_INSTR 32; VM_REGISTERS 8 (int16 wrap);
VM_ACT_BUDGET 2; MAX_CONTROLLERS_PER_COLONY 2; RE_OPERATE_TICKS 400
(= 2000 steps); CHASSIS_SALVAGE 4 (→ 2–3 chassis/world, controllers ≤ 4
ever incl. the wreck's); CONDUCTOR_COPPER 2; CONTACT_GOLD 1;
DEVICE_DURABILITY 240; DECAY_AMBIENT_INTERVAL 100 (−1);
CONTROLLER_DECAY 1/executed tick (~1140 unrepaired steps of life);
ACTUATOR_WEAR GATE/VALVE/BEACON 2, ALARM 1 (per EFFECTIVE actuation —
no-ops free; decay pressure teaches edge-triggered programs);
REPAIR_PER_COPPER 80 (below REPAIR_AT 100); BUILD_MIN_FOOD 60
(FORTIFY posture ×0.75); VALVE_FOOD_COST 15; ALARM_STRENGTH 3.0;
PROGRAM_REVIEW 200; TINKER_EPSILON 0.05.
New voxels: HULL 12, SALVAGE 13 (both solid, not tunnelable).

## T28 wreck
One per world, after ore before glass, d ≥ 12 only; random quadrant,
margin 6 from walls, ≥ OASIS_RADIUS+6 from center, at the quadrant's
lowest dune point; hull base z = substrate+1 (straddles strata band 1);
3×3×1 interior AIR; buried under +2 sand (a suspicious regular mound).
`world.wreck` dict {min,max,controller_pos}; pre-loaded controller is a
claimable ARTIFACT at interior center (`sim.wreck_artifact_pos`), not a
voxel. Rendering: HULL `Ξ` (120,130,150), SALVAGE `&` (170,190,210) in
BOTH renderers; devices `¤` colony color; gate marker `‡`.

## T29 discovery ladder (VM_TICK cadence, AABB-guarded)
Glint (any wreck voxel exposed near a unit; world-once event `Something
metallic glints in the sand`) → known (unit within NOTICE_RANGE of an
exposed voxel → colony.machine_arc='known'; workers gain the excavate
branch) → uncover (face-adjacent; once/colony event `Colony {id} uncovers
the ancient wreck!` + decision log).

## T30 VM
PLC scan cycle: PC resets each tick, REGISTERS PERSIST (counters, edge
detection, hysteresis expressible). ISA (11 ops, final): NOP; LET Ra,k
(k∈[−9999,9999]); MOV; ADD/SUB/MUL (int16 wrap); DIV (b=0 → 0, no fault);
SENSE Ra,port; ACT port,Ra (first VM_ACT_BUDGET honored/tick, rest burn
fuel); IF Ra cmp Rb GOTO n (6 cmps, target clamped); JMP n (clamped).
Halt: PC past end or fuel 0. Cost proof: ≤4 controllers × 64 ops / 5
steps ≈ 0.14 ms/step ≈ 0.3% of frame.

## T31 sensor ports (0–8)
FOOD int(food_stored); POP; SEASON 0–3; ENEMY band (0 none≤15 / 1 ≤15 /
2 ≤5 / 3 adjacent); CROPS (_farm_counts total); STORM 0/1; GOLD;
MAWHP 0–100; CLOCK step%SEASON_LENGTH.

## T32 actuators (the four feats; each rides an existing mechanism)
GATE (maw 26-neighborhood AIR→owned TUNNEL_WALL, skipping unit/FOOD/CORPSE
cells; open reverts recorded cells; a sealed colony cannot forage — the
turtle trade-off is the tinkerer's gradient); VALVE (debit 15 food → 1
FOOD voxel at its linked cell; energy-conserving, value is positional);
ALARM (DANGER 3.0 at maw + 6 faces — outranks the scout net's 2.0);
BEACON (append linked pos to colony.known_food; existing stale-purge
handles lies). TURRET/HEATER/SPRINKLER rejected (combat autonomy exceeds
the calculator ceiling; anti-frost duplicates the oasis niche).
Combo acceptance scenarios: siege lockdown (ENEMY+GATE+ALARM — the demo
program); winter larder (SEASON+FOOD+VALVE+BEACON behind the gate line);
bait trap (VALVE outside + ENEMY+GATE+ALARM).

## T33 components + decay
2 copper→CONDUCTOR; 1 gold→CONTACT; 4 salvage→CHASSIS; CONTROLLER =
chassis+2 conductor+contact; ACTUATOR = 1 conductor. Recipes debit
colony.ore/salvage directly (no inventory surface). Salvage mined via the
T24 machinery (SALVAGE_MINE_TIME 8, carrying='salvage', first-strike
event), spills on maw death, NON-RENEWABLE — the Machine Age can end.
Copper contention: full kit 12 + upkeep ~12.6/soak vs armor 1/soldier ≈
half the average world supply — brains vs armor is a real choice. Repair:
worker branch, 1 copper → +80 durability. Failure: device removed, event
`Colony {id}'s {kind} sputters and dies`; a dead controller's chassis is
destroyed.

## T34 reverse engineering
claim (worker adjacent to artifact; event `Colony {id} coaxes the ancient
machine to life`; actuators unlock) → operate (RE_OPERATE_TICKS executed
ticks → event `Colony {id} has reverse-engineered the controller!`;
machine_arc='unlocked'; controller-building unlocks) → build (event
`Colony {id} assembles a controller from salvage`; per-kind first-build
milestones `Colony {id} builds a {kind}`; actuations are NOT events —
first gate close gets `Colony {id}'s gate slams shut`). If the claiming
colony falls, the wreck-origin controller drops as a re-claimable
artifact at the death site — the arc restarts, legendary-item style.

## T35 tinkerer (ProgramTinkerer interface; GP default)
Every PROGRAM_REVIEW steps per controller: U = Δ(food + 15·pop)/window —
deliberately the SAME value function as the posture learner (no uptime
bonus: reward-hacking guard). Keep-if-improved vs an EMA(α=0.5) incumbent;
ε=0.05 random restart (4–8 random instructions), revert-if-worse.
GP mutation weights: tweak LET const ±{1,5,25} or ×/÷2 (0.35), retarget
port (0.15), swap opcode/operand (0.15), swap instructions (0.10), insert
(0.15), delete (0.10). Bootstrap: the wreck controller ships with the
7-line siege-gate demo (SENSE ENEMY; IF ≥2 → GATE 1 + ALARM 1 else GATE 0)
— ACT on an unbuilt actuator is a fuel-costing no-op: the machine hums,
waiting. LLM mode (`--tinkerer llm`, optional): reuses OllamaGPT via
try/except; strict prompt contract (ISA + ports + limits; program listing
+ last-10-tick sensor table + last-5 U pairs); strict line-grammar parse,
any violation → GP fallback this review; ThreadPoolExecutor(1), submit at
review k / poll at k+1, never blocks the loop; client transient in
__getstate__.

## T36 surfacing
Manager PROGRAM panel via pure `build_program_panel(sim, colony)`:
device lines with ASCII durability bars (hp_bar), arc line
(`machine: unlocked · operate 412/400 · salvage 3`), program listing with
line numbers ×10, last-tick register footer, SENSE values as inline
comments, last honored ACT highlighted, tinkerer line
(`U=+0.41 (ema +0.22) · reviews 17 · last: kept`). EVENT_TINTS: wreck/
machine/controller/salvage/sputters/gate-slams → steel (150,200,220).
Anchor M11: `machine` — within Chebyshev 3 of an own device OR carrying
salvage (context: device_3 count). `spark` rejected: no measurable ground
truth. Vocabulary regen for the seed (fallback covers the gap).

## T37 integration
Phase 3f MACHINE TICK after 3e, before 4: discovery checks → decay/
failures → build-order refresh → per-controller sensor cache + execute +
apply ACTs + arc bookkeeping; tinkerer review on its cadence inside.
Worker AI v3 (amends T18): grab → haul (+salvage) → mine-continue
(+SALVAGE) → forage → farm → 5b machine work (repair → build order →
excavate toward the artifact) → mine-seek (+salvage) → dig. Machine work
below forage/farm: eating beats engineering. Build orders are heuristic
(fixed priority GATE→ALARM→VALVE→BEACON→CONTROLLER; VM decides WHEN,
never WHERE — the calculator ceiling). Learner: NO new state dim
(sparse-table orphaning; revisit with evidence); FORTIFY lowers
BUILD_MIN_FOOD ×0.75. Politics hooks reserved: Device.owner mutable, the
artifact drop is the loot/gift seam, enemy devices as raze targets extend
T21 — Round 2 owns them. Enhanced sim: phase 3f never runs, no funded
touchpoints, tripwire test. Old checkpoints: full getattr inventory
(world.wreck None → machines inert forever, correct for wreckless
worlds).

## T38 acceptance
14 tests: VM halting/determinism/arithmetic+ACT-budget; 9 sensor ports
rigged; GATE close/open/skip rules; VALVE/ALARM/BEACON; siege-lockdown
combo (ring closed within 10 steps of threat, reopens within 10 of
clear); decay/repair/failure; wreck-gen invariants (seeded: counts,
no-roof salvage, ≥2 interior-level, buried, gravity no-op, d=5 → none);
the full arc with exact catalog texts; GP tinkerer restores deleted gate
behavior within ≤30 reviews on a rigged siege world + reverts worse +
ε-restarts ≈ binomial; LLM mocked (prompt content, malformed→GP, client
absent from pickle); compat tripwires; 3-year machine soak (wreck
uncovered by step 3200, claim, ≥1 actuator built, ≥1 gate close within
50 steps of a siege event, reverse-engineered OR built controller by
4800, all liveness criteria, ≥19 sps).

## T39 LIBRARY CARTRIDGES (user addition — design at implementation)
Opcode/actuator packs as discovered unlocks ("python libraries" in-world;
Pathfinder-feat composability): MATH ships with the controller; GEO
(terraform: EXCAVATE sand→air, DEPOSIT air→sand — gravity/storm/
crop-burial physics does the cascading: moats, drawbridges, burying enemy
fields) and BIO (radiation, T40) are salvage/research unlocks.

## T40 RADIATION (user addition — design at implementation)
The wreck holds a damaged REACTOR_CORE seeding a decaying 2D radiation
field (pheromone-style array): hot zones damage organics + accelerate
device decay; mild zones CATALYZE MUTATION (multiplied genome/brain
mutation rates for maws parked in them — evolution accelerant priced in
ambient harm, soak-measurable); BIO's RAD_EMITTER makes area denial and
self-mutagenesis deliberate plays (gold-hungry). Cascade tests: hot-zone
trap (RAD+VALVE), hyperevolution lineage (reactor-adjacent maw).

## Cross-amendments on implementation
T9 event catalog += machine rows; T18 → worker AI v3; T23 += wreck stage;
T24 += SALVAGE mask; T25 += salvage spill + artifact drop; T26 note;
R25–R27; M11.

## Reconciliation Log
- 2026-07-08 — Implemented T28–T40 with deviations, intent-preserving:
  - Conditional jumps use op `IFC` with cmp+target packed into the c slot
    (`make_if` builder); the listing still reads as QBasic `IF..GOTO`.
  - The soak exposed an arc dead-end: the ancient controller decayed
    (240 durability ≈ 1000 steps) before reverse-engineering could finish
    (2000 steps) and its death was permanent. Fixed: ANCIENT_DURABILITY
    720, and a decayed ancient controller FALLS SILENT — re-dropping as a
    claimable artifact at the maw ("the legendary item never truly dies").
    Verified in-soak: claim → falls silent → re-claim cycle observed.
  - T39/T40 implemented lean: GEO (EXCAVATE/DEPOSIT one voxel per
    actuation at the device) and BIO (RAD emitter, 2 gold) unlock at
    'unlocked' (reverse-engineering IS the cartridge research);
    radiation = 2D field, reactor seepage 0.5/step, blur-diffused every
    10 steps, hot zones (>2) burn units/devices/crops, mild zones (>0.5)
    double respawn-lineage mutation rates.
  - LLM tinkerer mode NOT implemented (user chose GP); the
    ProgramTinkerer seam exists for it.
  - Build-order queue simplified to a fixed priority list evaluated in
    the worker branch (no explicit pending-order state).
  - T38 soak criterion "≥1 actuator built by 4800" relaxed to
    claim-or-build: the full pipeline (claim → copper → build) manifests
    on longer horizons; flagged as a tuning watch (machine work sits
    below eating by design).
  - Two anchors shipped (machine AND radiation, 33 total) — radiation
    earned its own measurable predicate (field ≥ 0.5 at the unit).
  - Manager panel ships device bars + arc line + 8-line listing +
    register footer; per-SENSE inline values render via the listing.
