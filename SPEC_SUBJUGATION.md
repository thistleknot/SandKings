# SPEC: Subjugation — Capture, Coercion & Conversion — SJ1–SJ8

Module **M2** of the inter-colony political-economy arc (governing scope record:
`intercolony-relations-spectrum`). Depends ONLY on M1 `SPEC_LABOR` (the
`laboring_for` field, `_credit_labor`, `composite_power`). M3 `SPEC_WAGES` and M4
`SPEC_BARGAIN` are NOT specified here.

**The mechanic.** Instead of killing a broken enemy unit, a dominant captor may
CAPTURE it — the unit lives at low health as a THRALL, its production redirected to
the captor (`laboring_for := captor.colony_id`, brute wage `w = W_BRUTE = 0`). The
thrall's birth allegiance (`colony_id`) never changes — psionic conditioning is
unoverwritable — so a thrall accrues DEFIANCE when unguarded, especially near its
birth maw; a captor must GUARD and COERCE it or it BREAKS FREE. Only when the birth
maw DIES does the psionic link sever and the thrall permanently CONVERT to the
captor.

> **TOP INVARIANT (default-neutral) & FIRST ACCEPTANCE CLAUSE.** The capture path
> MUST short-circuit on `CAPTURE_CHANCE <= 0.0` BEFORE any `random.random()` (or
> any other RNG) call. A single consumed RNG draw at a lethal branch would desync
> every seeded regression test even though no capture occurs. With
> `CAPTURE_CHANCE = 0.0`: no unit is ever captured, no unit ever holds
> `laboring_for >= 0`, `_subjugation_tick` finds no thralls and consumes no RNG,
> and the entire regression battery is byte-identical to a pre-M2 run.

All new state is getattr-guarded, pickled, inherited per the `stage`/`breached`
convention; `EnhancedSandKingsSimulation.step` stays inert.

---

## Capture, not kill (SJ1)

**SJ1 — Capture at the lethal branch.** In `_resolve_conflicts`, the two lethal
branches queue a dying unit for removal: `sandkings.py:5487–5490` (the defender
`unit` of `colony` dies to `enemy`) and `:5507–5510` (the `enemy` dies to `unit`).
Wrap each removal-plus-telemetry block in a capture check:

```
# branch A (:5487) — `unit` is dying to attacker `enemy`
if unit.take_damage(enemy.attack, colony.genome.resilience):
    if not self._try_capture(enemy_colony, enemy, unit, colony):   # NEW
        <existing :5488–5505 block: queue units_to_remove, kills++, grievance, monitor>

# branch B (:5507) — `enemy` is dying to attacker `unit`
if enemy.take_damage(unit.attack, enemy_colony.genome.resilience):
    if not self._try_capture(colony, unit, enemy, enemy_colony):   # NEW
        <existing :5508–5525 block: queue units_to_remove, kills++, grievance, monitor>
```

`_try_capture` — the RNG-guarded predicate:
```
def _try_capture(self, captor_colony, captor_unit, victim, victim_colony) -> bool:
    """Attempt to capture `victim` (already at <=0 health from take_damage)
    instead of killing it. Returns True iff captured (caller then SKIPS removal,
    corpse, and kill telemetry).

    Require: victim.take_damage just returned True (victim would die this step).
    Guarantee: on True, victim.laboring_for == captor_colony.colony_id,
      victim.health == CAPTURE_HEALTH (> 0), victim stays in victim_colony.units
      (birth colony_id unchanged); corpse voxel and kill bookkeeping are NOT run.
      On False, ZERO RNG consumed unless a capture was genuinely possible.
    """
    if CAPTURE_CHANCE <= 0.0:
        return False                                   # (1) HARD GATE — no RNG, default-neutral
    if not self._subjugate_stance(captor_colony, victim_colony):
        return False                                   # (2) stance gate (default False) — no RNG
    if not self._local_dominance(captor_colony, captor_unit, victim, victim_colony):
        return False                                   # (3) SJ2 dominance — no RNG
    if random.random() >= CAPTURE_CHANCE:              # (4) RNG reached ONLY past 1–3
        return False
    # CAPTURE
    victim.laboring_for = captor_colony.colony_id
    victim.health = CAPTURE_HEALTH
    victim.defiance = 0.0
    return True
```

- The four gates are ordered so the constant test (1) precedes every RNG draw. Gates
  (2) and (3) are deterministic; only gate (4) draws. At `CAPTURE_CHANCE = 0`,
  gate (1) returns immediately → the existing removal block always runs → the combat
  loop is byte-identical.
- On capture the victim is NOT queued into `units_to_remove`, so the corpse voxel at
  `:5560` and the `remove_unit` at `:5559` never touch it; the ecology invariant
  (corpse→food) and telemetry (kills/grievance/monitor) are simply the KILL path,
  which capture bypasses — a capture is not a kill and logs none of it. (A capture
  MAY log its own salience event; that is display-only and adds no RNG.)

`_subjugate_stance(captor_colony, victim_colony) -> bool` — the downstream stance
predicate, defaulting False:
```
return bool(getattr(captor_colony, 'subjugation_stance', False))
```
(A later increment sets `subjugation_stance`; until then it is False and, combined
with `CAPTURE_CHANCE = 0`, capture is doubly gated off.)

Contract at the capture hook:
- **Require** — called only inside a lethal branch, after `take_damage` returned True.
- **Guarantee** — captured victim survives at `CAPTURE_HEALTH` with
  `laboring_for = captor.colony_id`; uncaptured victim reaches the unchanged
  removal/corpse/telemetry path.
- **Maintain** — no unit migration; `colony_id` unchanged on capture; RNG stream
  untouched whenever `CAPTURE_CHANCE <= 0`.
- **Assert** — after capture, `victim.health > 0` and `victim not in units_to_remove`.

## Local dominance (SJ2)

**SJ2 — `_local_dominance`.** Capture requires the captor to physically DOMINATE
the spot: a captor enforcer (soldier) adjacent to the victim and NO free defender of
the victim's birth house adjacent to protect it.
```
def _local_dominance(self, captor_colony, captor_unit, victim, victim_colony) -> bool:
    vx, vy, vz = victim.position
    enforcers = 0     # captor soldiers within radius 1 of the victim
    defenders = 0     # victim's-birth free units within radius 1 (would-be rescuers)
    for other in self._units_near(victim.position, radius=1):     # Chebyshev r1, incl. captor_unit
        if other is victim:
            continue
        if (other.colony_id == captor_colony.colony_id
                and other.unit_type == UnitType.SOLDIER):
            enforcers += 1
        elif (other.colony_id == victim_colony.colony_id
                and getattr(other, 'laboring_for', -1) < 0):      # a free birth-house unit = a rescuer
            defenders += 1
    return enforcers >= 1 and defenders == 0
```
(`captor_unit` — the attacker that just won the exchange — already sits adjacent, so
it counts as an enforcer; the predicate still scans to catch rescuers.)
- **Require** — victim and captor units have valid positions.
- **Guarantee** — True only when at least one captor soldier and zero free birth-
  house defenders are within Chebyshev radius 1 of the victim.
- **Maintain** — pure read; no mutation, no RNG.

## The defiance meter (SJ3)

**SJ3 — Per-unit `defiance`.** A getattr-guarded float on `SandKing`, default `0.0`,
pickled. In `_subjugation_tick`, for each living THRALL (`laboring_for >= 0`):
```
captor = self._colony_by_id(unit.laboring_for)
guarded = captor is not None and captor.is_alive() and any(
    u.unit_type == UnitType.SOLDIER
    and _chebyshev(u.position, unit.position) <= GUARD_RADIUS
    for u in captor.units)

if guarded:
    unit.defiance = max(0.0, getattr(unit,'defiance',0.0) - DEFIANCE_CALM)
else:
    birth = self._colony_by_id(unit.colony_id)
    prox = _birth_maw_proximity(unit, birth)          # 0..1, 1 on the maw
    rise = DEFIANCE_RISE * (1.0 + DEFIANCE_MAW_ACCEL * prox)
    unit.defiance = min(1.0, getattr(unit,'defiance',0.0) + rise)
```
`_birth_maw_proximity(unit, birth)` = `max(0.0, 1.0 - _chebyshev(unit.position,
birth.maw.position) / GUARD_RADIUS)` when `birth` is alive, else `0.0` (no maw to
call to — a thrall of a dead birth house is handled by SJ6 conversion, not here).
- **Guarantee** — `defiance ∈ [0,1]`; rises only when unguarded, faster near the
  birth maw; calms when a captor soldier is within `GUARD_RADIUS`.
- **Maintain** — a captor-dead or absent extractor pointer is left for SJ6/`_credit_labor`
  self-heal; SJ3 never writes `colony_id` or `laboring_for`.

## Threat of harm (SJ4)

**SJ4 — Coercion & refusal.** In the same tick, a thrall whose `defiance >=
DEFIANCE_ACTIVE` is COERCED by the nearest captor soldier and may resist:
```
if getattr(unit,'defiance',0.0) >= DEFIANCE_ACTIVE:
    enforcer = self._nearest_unit(captor.units, unit.position,
                                  kind=UnitType.SOLDIER)     # None if captor has no soldier near
    if enforcer is not None:
        unit.take_damage(COERCION_DAMAGE, birth.genome.resilience)   # threat of harm
        if unit.health <= 0:                                          # coerced to death -> a kill
            <queue for removal via the tick's own dead-thrall list; corpse as normal>
    # refuse labor: deny the captor this step's production
    unit.forage_target = None
    unit.mine_target = getattr(unit, 'mine_target', None) and None
    # strike back at low rate (RNG reached ONLY because a thrall exists => CAPTURE_CHANCE>0)
    if enforcer is not None and random.random() < STRIKE_CHANCE:
        enforcer.take_damage(unit.attack, captor.genome.resilience)
        if enforcer.health <= 0:
            <queue enforcer for removal + corpse (a thrall's revolt can kill a guard)>
```
- Refusal = the thrall performs no deposit this step (targets cleared), so NO labor-
  value reaches the captor — modeled WITHOUT touching `_credit_labor` (LV2 stays as
  written); the thrall simply idles.
- The `random.random()` for the strike is reachable only when a thrall exists, which
  requires a prior capture, which requires `CAPTURE_CHANCE > 0`. So the strike draw
  cannot perturb a `CAPTURE_CHANCE = 0` run.
- **Guarantee** — a defiant thrall takes `COERCION_DAMAGE` from a nearby captor
  soldier and yields no production that step; may strike the guard at `STRIKE_CHANCE`.
- **Maintain** — coercion deaths route through the normal corpse/ecology path.

## Break free (SJ5)

**SJ5 — Break free.** Past the threshold, the coercion fails and the thrall bolts
home:
```
if getattr(unit,'defiance',0.0) >= DEFIANCE_THRESHOLD:
    unit.laboring_for = -1        # free again; birth colony_id was never lost
    unit.defiance = 0.0
    birth = self._colony_by_id(unit.colony_id)
    if birth is not None and birth.is_alive():
        unit.forage_target = birth.maw.position   # flee toward the birth maw
    self._log_event(f"A thrall of House {captor_house} breaks free and flees home")
```
- **Guarantee** — a thrall at `defiance >= DEFIANCE_THRESHOLD` is freed
  (`laboring_for = -1`), defiance reset, and steered to its birth maw; its production
  reverts to its birth colony via `_credit_labor`'s free path (LV2) automatically.
- **Maintain** — `colony_id` unchanged (it was never the captor's).

## True conversion on birth-maw death (SJ6)

**SJ6 — Permanent conversion.** In `_check_maw_deaths` (`sandkings.py:4858`), for a
colony whose maw has fallen, run conversion BEFORE the unit-corpse loop at `:4863`
and the ownership wipe at `:4892`:
```
# --- SJ6a: this dead birth house's OWN thralls convert to their captors ---
for unit in list(colony.units):                     # snapshot: we mutate the list
    ext_id = getattr(unit, 'laboring_for', -1)
    if ext_id < 0:
        continue                                    # a free birth unit: today's death (corpse) below
    captor = self._colony_by_id(ext_id)
    if captor is not None and captor.is_alive():     # captor-alive edge -> convert
        unit.colony_id = ext_id                     # psionic link severed: permanent conversion
        unit.laboring_for = -1
        unit.defiance = 0.0
        colony.units.remove(unit)                   # leave the dying house
        captor.units.append(unit)                   # join the captor -> spared the :4863 corpse loop
    # else captor also dead/absent: fall through, unit stays -> today's death at :4863

# --- SJ6b: this dead house was an EXTRACTOR; free any thralls it still held ---
for other in self.colonies:
    if other is colony:
        continue
    for unit in other.units:
        if getattr(unit, 'laboring_for', -1) == colony.colony_id:
            unit.laboring_for = -1                  # extractor gone -> freed
            unit.defiance = 0.0

# --- then the EXISTING :4863 loop corpses whatever units REMAIN in colony.units ---
```
- Pre-existing thralls convert (SJ6a); non-thrall survivors keep today's behavior
  (corpse) — exactly the resolved decision. The kin-map (`_kin_epoch`) must be bumped
  after a conversion so `hostile()` re-reads the reassigned unit's side; reuse the
  existing respawn/founding bump path.
- Runs before `:4892` so a converted unit's voxel ownership is not spuriously wiped
  to `-1` for its NEW house (ownership arrays are per-colony_id; conversion changes
  the unit, not owned voxels — the wipe of the DEAD id's voxels is still correct).
- **Require** — invoked once per fallen colony, before `:4863`/`:4892`.
- **Guarantee** — every own-thrall with a living captor is reassigned
  (`colony_id := laboring_for`, `laboring_for := -1`) and moved to the captor's
  units, thus NOT corpsed; own-thralls with a dead captor die as today; the dead
  house's outbound thralls are freed.
- **Maintain** — corpse/ore-spill/telemetry invariants of `_check_maw_deaths` hold
  for the units that remain; `_plunder_techs` (`:4891`) is unaffected.
- **Assert** — after SJ6, no surviving unit has `laboring_for` pointing at the dead
  colony_id.

## Tick placement & thrall hostility (SJ7)

**SJ7a — `_subjugation_tick` placement.** Call it in `step()` between combat
resolution (`_resolve_conflicts`, `:1726`) and maw-death (`_check_maw_deaths`,
`:1731`), following the numbered-comment convention:
```
        # 6. Combat resolution
        self._resolve_conflicts()

        # 6b. SUBJUGATION (SPEC_SUBJUGATION): defiance, coercion, break-free
        self._subjugation_tick()

        # 7. Maw migration, regen, colony collapse, and new arrivals
        self._migrate_threatened_maws()
        ...
        self._check_maw_deaths()
```
`_subjugation_tick` MUST early-out before any RNG when there are no thralls:
```
def _subjugation_tick(self):
    thralls = [u for c in self.colonies for u in c.units
               if getattr(u, 'laboring_for', -1) >= 0]
    if not thralls:
        return                       # DEFAULT-NEUTRAL: no thralls => no work, no RNG
    for unit in thralls:
        <SJ3 defiance>; <SJ4 coercion/refusal/strike>; <SJ5 break-free>
```
Placed AFTER combat (thralls captured this step start docile) and BEFORE maw-death
(a thrall freed by SJ5 this step is correctly free when its captor's death is
processed).

**SJ7b — Thrall hostility.** A thrall keeps its BIRTH `colony_id` (psionic loyalty
intact), so colony-level `politics.hostile()` (`politics.py:144`) is UNCHANGED — do
not modify it. A thrall therefore still fights FOR its birth house and against its
birth house's enemies; it is extracted labor, not a turned soldier. The one
exception is a per-unit short-circuit in `_resolve_conflicts` targeting: a captor
unit and a unit it holds thrall do not fight each other:
```
# in the targeting/adjacency filter, before engaging a pair (a, b):
if (getattr(b,'laboring_for',-1) == a.colony_id
        or getattr(a,'laboring_for',-1) == b.colony_id):
    continue        # a captor does not kill its own labor; guarded by laboring_for>=0
```
Because both `getattr(...,'laboring_for',-1)` default to `-1`, this filter is NEVER
taken when no thralls exist (`CAPTURE_CHANCE = 0`) — byte-identical. A thrall's only
violence against its captor is the SJ4 low-rate strike.
- **Guarantee** — thralls fight for their birth side and are not attacked by their
  captor; `hostile()` is untouched; the combat filter is inert at `CAPTURE_CHANCE = 0`.

Contract at `_subjugation_tick`:
- **Require** — called once per step, after `_resolve_conflicts`.
- **Guarantee** — no RNG and no state change when no thralls exist; otherwise
  evolves defiance, coerces, and frees per SJ3–SJ5.
- **Maintain** — `colony_id` written only by SJ6 (conversion), never by the tick.
- **Assert** — every unit touched has `laboring_for >= 0` (a thrall).

## Constants & acceptance (SJ8)

**SJ8 — Constants.**

| Constant | Value | Meaning |
|---|---|---|
| `CAPTURE_CHANCE` | `0.0` | probability a dominant captor takes a broken enemy alive; `0` disables capture AND the RNG draw (default-neutral gate) |
| `CAPTURE_HEALTH` | `3` | health a captured thrall is revived to (low — freshly broken) |
| `GUARD_RADIUS` | `6` | Chebyshev range within which a captor soldier keeps a thrall docile / that scales birth-maw proximity |
| `DEFIANCE_RISE` | `0.05` | defiance gained per tick while unguarded |
| `DEFIANCE_CALM` | `0.10` | defiance shed per tick while guarded (cowed faster than it festers) |
| `DEFIANCE_MAW_ACCEL` | `1.0` | multiplier on defiance rise at the birth maw (×2 on the maw, decaying with distance) |
| `DEFIANCE_ACTIVE` | `0.5` | defiance at which coercion, refusal, and strikes begin |
| `DEFIANCE_THRESHOLD` | `1.0` | defiance at which the thrall breaks free |
| `COERCION_DAMAGE` | `2` | threat-of-harm damage a captor soldier deals a defiant thrall per tick |
| `STRIKE_CHANCE` | `0.1` | probability a defiant thrall strikes its guard back |
| `W_BRUTE` | `0.0` | brute-mode wage (from `SPEC_LABOR`); a captured thrall's `w` |

New pickled/getattr-guarded state: `SandKing.defiance` (float, default `0.0`);
`Colony.subjugation_stance` (bool, default False, read by `_subjugate_stance`).
Surfacing (SJ, display-only): `build_state` may expose per-colony `thralls_held`
(count of units across all colonies with `laboring_for == this colony_id`) and
`thralls_lost` (own units with `laboring_for >= 0`); no control flow keys off them.

**SJ8 — Acceptance.** `tests/test_subjugation.py`:

1. **DEFAULT-NEUTRAL / RNG (FIRST clause).** With `CAPTURE_CHANCE = 0.0`: a fixed-
   seed run is byte-identical to a pre-M2 golden — the RNG stream and the full
   regression battery match exactly. Assert specifically that `_try_capture` and
   `_subjugation_tick` consume ZERO `random.*` draws when no capture is possible /
   no thralls exist (e.g. patch `random.random` with a counting spy across a
   multi-step run and assert the count equals the pre-M2 count).
2. **Forced capture → thrall, not corpse.** With `CAPTURE_CHANCE = 1.0`,
   `subjugation_stance = True`, and local dominance satisfied, a broken enemy unit
   becomes a thrall (`laboring_for == captor.colony_id`, `health == CAPTURE_HEALTH`,
   still in its birth `units`, NO corpse voxel written, kill telemetry NOT incremented).
3. **Labors for the captor (via LV2).** A thrall's deposit routes through
   `_credit_labor`: at `w = W_BRUTE = 0` the captor colony receives the whole value
   and the birth colony receives none; conservation holds.
4. **Defiance & break-free.** An UNGUARDED thrall's defiance rises (faster within
   `GUARD_RADIUS` of its birth maw) and at `DEFIANCE_THRESHOLD` it breaks free
   (`laboring_for = -1`, steered to the birth maw); a GUARDED thrall's defiance stays
   suppressed.
5. **Threat of harm.** A defiant thrall (`defiance >= DEFIANCE_ACTIVE`) takes
   `COERCION_DAMAGE` from a nearby captor soldier and yields no production that step;
   the strike-back fires at `STRIKE_CHANCE` (verify with a seeded/patched RNG).
6. **Permanent conversion.** When a thrall's BIRTH maw dies, `_check_maw_deaths`
   converts it (`colony_id := former laboring_for`, `laboring_for := -1`), moves it
   into the captor's units, and spares it the corpse loop; a thrall whose captor is
   ALSO dead falls through to today's death.
7. **`_check_maw_deaths` ordering.** Conversion (SJ6) runs before the `:4863`
   corpse loop and the `:4892` ownership wipe; a converted unit is not corpsed and
   not spuriously un-owned; `_plunder_techs` still runs.
8. **Persistence & inertness.** `defiance` / `subjugation_stance` pickle and
   getattr-guard (pre-M2 pickles read as `0.0` / False); `EnhancedSandKingsSimulation.step`
   produces no captures and is byte-identical to a pre-M2 run.

## Ambiguities resolved

- **RNG ordering.** All cheap deterministic gates (constant, stance, dominance)
  precede the single `random.random()` in `_try_capture`; the strike RNG in SJ4 is
  reachable only when a thrall already exists. Both guarantee zero RNG perturbation
  at `CAPTURE_CHANCE = 0`.
- **Which side a thrall fights for.** Birth side (psionic loyalty intact,
  `colony_id` unchanged); `hostile()` is left untouched; only a per-unit combat
  filter (inert without thralls) stops a captor from killing its own thrall.
- **Refusal without touching LV2.** A refusing thrall is idled (work targets
  cleared) so it produces nothing that step; `_credit_labor` needs no `refusing`
  branch, keeping `SPEC_LABOR` LV2 exactly as written.
- **Captor-dead conversion edge.** Resolved by testing `captor.is_alive()` at
  conversion time; a thrall whose captor died the same step falls through to the
  existing death path.

## Runtime enablement (SJ9 — interim, until M4)

`subjugation_stance` is meant to be driven per-pair by M4 `SPEC_BARGAIN`, which is
not yet built. To let the capture economy be exercised (and played) before M4, a
`--subjugation` launcher flag turns it on for a run WITHOUT disturbing the
default-neutral gate:
- The module default `CAPTURE_CHANCE` stays `0.0` (the regression battery is
  byte-identical). `--subjugation` bumps the live module global to
  `SUBJUGATION_LIVE_CHANCE` (0.4) and sets `sim.subjugation_enabled = True`.
- `_subjugate_stance` returns True when a colony's explicit `subjugation_stance` is
  set OR (`sim.subjugation_enabled` AND the captor is `at_war`) — a stand-in for M4:
  "this only happens in condition of war." When M4 lands, it supersedes the
  war-driven branch with proper per-pair EV bargaining.
- This changes NO default behavior: with the flag off, `subjugation_enabled` is
  absent (False) and `CAPTURE_CHANCE` is 0.0, so every gate is closed.

## Status / Reconciliation

- **Drafted + implemented 2026-07-10.** SJ1–SJ8 implemented in `sandkings.py`
  (constants, `_try_capture`/`_local_dominance`/`_subjugation_tick`/the SJ6 block in
  `_check_maw_deaths`, the SJ7b combat filter) plus the SJ9 runtime enablement.
  Helpers `_chebyshev`/`_units_near`/`_nearest_unit`/`_birth_maw_proximity` added;
  the kin-map bump reuses the existing `_kin_epoch` mechanism. `defiance` /
  `subjugation_stance` are getattr-guarded (pickle-safe). Verified: full 37-suite
  Docker battery green (default-neutral holds at `CAPTURE_CHANCE=0`);
  `tests/test_subjugation.py` (8 clauses incl. the RNG-spy and the coerced-to-death
  removal strengthened in review). A 700-step `--subjugation` smoke run produced
  thralls with the tank staying alive.
- Depends on M1 `SPEC_LABOR` (`laboring_for`, `_credit_labor`, `composite_power`,
  `W_BRUTE`). Feeds M3 `SPEC_WAGES` (bargained `w` replacing the brute constant) and
  M4 `SPEC_BARGAIN` (renegotiation cadence + proper stance, superseding SJ9).
- Reuse, not reinvention: capture hooks the existing lethal branches; conversion
  hooks `_check_maw_deaths` beside `_plunder_techs`; the tick slots into the existing
  numbered `step()` sequence; thrall hostility rides the existing `colony_id`-keyed
  `hostile()` with a single inert per-unit filter.
