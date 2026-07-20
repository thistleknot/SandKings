# Spec: Dynamic Population & Succession — Phase 0 (inert scaffolding + slot-scrub choke point)

Layer: **Structural** (constants, a per-colony state field, one new method + signature)
+ **Behavioral** (the `_deactivate_slot` scrub, the save/load shim) + **Requirements**
(the identity-at-neutral guarantee). Governs `sandkings.py` colony construction and the
respawn spine.

> **Phase 0 of the dynamic-population + succession redesign.** A fixed pool of
> `MAX_COLONIES = 8` slots, each carrying a lifecycle `pop_state`
> (`ACTIVE` / `SUCCESSION` / `DORMANT`). Emergent population (2..8, equilibrium ~4)
> is delivered by later phases via activation transitions. **Phase 0 builds only the
> SCAFFOLDING and the scrub contract, all behind a default-off flag.** Nothing in
> Phase 0 changes runtime behavior.

> **CURRENT STATUS (updated 2026-07-20): SHIPPED through Phase 6, baseline-ON in the live
> game.** The document below is the Phase-0 record; the arc has since been fully built —
> pool-breathe 2..MAX (`sandkings.py:2642`), activation/succession transitions
> (`:8778,:8942,:9020-9133`). It is baseline-ON in a normal run because the entrypoint
> constructs the sim with `dynamic_population=True` (`:10295`). The module master flag
> `DYNAMIC_POPULATION` stays `False` (`:67`) and the constructor defaults to it when the arg
> is omitted (`:2056`), so the regression battery — which constructs at the default — remains
> byte-identical (asserted in `tests/test_population.py:52-54`). There is no `--dynamic` CLI
> flag; opting out means constructing with `dynamic_population=False`.

---

## 0. Provenance & governing-record status

Provenance keys used below:
- **[prov:C]** — from the governing architecture (bounded-pool decision), as relayed
  in the Phase-0 tasking. **See the discrepancy note.**
- **[prov:V]** — VERIFIED directly against `sandkings.py` / `politics.py` at spec time
  (line numbers cited inline).

**Governing-record discrepancy (must read).** The tasking cites a scope decision record
at `docs/decisions/2026-07-11-dynamic-population-and-succession.md`. **That file does
not exist in the repo.** The only decision record present is
`docs/decisions/2026-07-09-intercolony-relations-spectrum.md` (unrelated: the wage/force
labor model). The bounded-pool architecture in this spec is therefore sourced entirely
from the Phase-0 tasking text, not from a committed decision record. **Recommendation:**
commit the decision record before Phase 1, so later phases have a citable governing doc.
This does not block Phase 0 (the architecture is fully specified in the tasking), but the
`[prov:C]` claims are un-cross-checkable against a repo artifact.

**Two `[prov:C]` "merge-debris" duplicate claims from the tasking were checked and are
FALSE — DO NOT fix them:**

1. *Claim:* "duplicate `pending_respawns` init ~1565/1570." **FALSE.** There is exactly
   ONE initialization: `self.pending_respawns: Dict[int, int] = {}` at
   `sandkings.py:1570` [prov:V]. Line 1565 is `num_colonies = random.randint(3, 5)`
   (the random colony-count resolver), not a `pending_respawns` init. No dedup to do.
2. *Claim:* "duplicate `record_event('respawn')` lines." **FALSE.** There is **no
   `record_event` symbol anywhere in the codebase** [prov:V] (grep across all `*.py`:
   zero matches). Drama is logged via `self._log_event(...)`. The two respawn-related
   `_log_event` calls that exist — `sandkings.py:6293` ("has fallen!") in
   `_check_maw_deaths` and `sandkings.py:6439` ("A new colony … arrives") in
   `_respawn_colony` — are DISTINCT events in DIFFERENT methods (death vs arrival), not
   duplicates. No dedup to do.

Because neither claimed duplicate exists, **Phase 0 contains no merge-debris cleanup
item.** (The tasking's item 5 is conditional — "only if you CONFIRM the duplicates" — so
it is correctly omitted.)

**Other tasking anchors that were inaccurate against the code (flagged, non-blocking):**
- `COLOR_PAIRS` — cited as a respawn anchor. **Does not exist in `sandkings.py`** [prov:V].
  The colony palette is `Colony.COLORS` (a 4-tuple, `sandkings.py:1136`). See POP-4 note.
- `bound_to` — cited as a thrall link field. **Does not exist** [prov:V]. The only thrall
  link is `SandKing.laboring_for` (`sandkings.py:1029`); the only envoy link is
  `SandKing.gift_to` (`sandkings.py:1021`). The scrub targets `laboring_for` and
  `gift_to`; there is no `bound_to` to scrub.

---

## 1. What Phase 0 delivers (and explicitly does NOT)

**Delivers (all inert at the flag-off default):**
1. `Constant: MAX_COLONIES = 8` — the fixed slot-pool cap. [prov:C]
2. A default-off flag `dynamic_population` (module constant + sim instance attr). [prov:C]
3. A per-colony lifecycle field `colony.pop_state ∈ {ACTIVE, SUCCESSION, DORMANT}`,
   default `ACTIVE`, getattr-guarded + pickled, **inert** in Phase 0. [prov:C]
4. The slot-scrub choke point `SandKingsSimulation._deactivate_slot(self, cid)` —
   defined and TESTED, but **unwired** at the flag-off default (called only by
   future flag-gated paths). [prov:C]
5. Save/load compatibility for the new fields (getattr-guarded defaults). [prov:C]

**Does NOT (deferred to Phases 1–9):**
- Does not change `num_colonies` (stays 4 default / canon-4 / random 3–5). [prov:V]
- Does not add or fire any `DORMANT`/`SUCCESSION`/founding transition.
- Does not touch madness, succession, founding, or `_check_maw_deaths` /
  `_process_respawns` / `_respawn_colony` runtime behavior.
- Does not flip `dynamic_population` to `True` anywhere.

---

## 2. Structural Spec

### 2.1 Constants & flag (module scope, `sandkings.py`)

Place next to the existing respawn constants (`RESPAWN_DELAY` at `sandkings.py:62`) [prov:V]:

```
Constant: MAX_COLONIES = 8            # fixed slot-pool cap (bounded pool)   [prov:C]
Constant: DYNAMIC_POPULATION = False  # master flag; OFF reproduces today    [prov:C]

# pop_state lifecycle values (string constants; no Enum dependency, pickle-trivial)
Constant: POP_ACTIVE     = "ACTIVE"     # a live, participating slot         [prov:C]
Constant: POP_SUCCESSION = "SUCCESSION" # reserved: Phase-1+ succession       [prov:C]
Constant: POP_DORMANT    = "DORMANT"    # reserved: Phase-1+ empty slot        [prov:C]
POP_STATES = frozenset({POP_ACTIVE, POP_SUCCESSION, POP_DORMANT})
```

Rationale (Structural, constants-vs-config): these are **constants**, not config — a
Phase-0 rote implementation must not surface them as tunables. `pop_state` is stored as a
plain string (not `enum.Enum`) to keep pickle round-trips trivial and getattr-guarding a
one-liner, matching the repo's existing string/scalar attr idiom.

### 2.2 Sim instance flag

In `SandKingsSimulation.__init__` (`sandkings.py:1556`) [prov:V], after the existing
attribute block, add:

```
self.dynamic_population = DYNAMIC_POPULATION   # instance override hook; Phase 0 = False
```

**Require:** nothing in Phase 0 reads `self.dynamic_population` (no branch keys on it).
It exists only so later phases have a per-sim toggle without a module edit. Setting it is
a pure attribute assignment — no RNG, no control-flow change.

### 2.3 Per-colony `pop_state` field

In `Colony.__init__` (`sandkings.py:1138`) [prov:V], alongside the existing field block
(after `self.crafted = set()` at `sandkings.py:1169`):

```
self.pop_state = POP_ACTIVE   # lifecycle slot state; inert in Phase 0     [prov:C]
```

**Maintain:** at the flag-off default, every live colony's `pop_state` is `POP_ACTIVE`
for the entire sim — no code path mutates it except `_deactivate_slot`, which is unwired.

### 2.4 New method signature (the choke point)

```
class SandKingsSimulation:
    def _deactivate_slot(self, cid: int) -> None: ...
```

**Contract (Design-by-Contract):**
- **Require:** `cid` is a valid colony id present in `self.colonies`
  (`self._colony_by_id(cid) is not None`).
- **Guarantee:** on return, slot `cid` carries NO stale per-colony state anywhere in the
  sim — see the scrub inventory (§3.1). `self.colonies[index].pop_state == POP_DORMANT`.
  The slot's `colony_id` (and thus its color + pheromone channel index) is preserved; the
  `Colony` object at the index is NOT replaced (refounding a fresh genome is a later
  phase).
- **Maintain:** every OTHER slot's state (units, ownership, pheromones, relations,
  disposition) is untouched. `len(self.colonies)` unchanged; no id reassigned.
- **Assert:** after scrubbing, `not (self.world.ownership == cid).any()` and
  `not self.pheromones.trails[:, :, :, cid, :].any()`.

**Wiring decision (load-bearing): `_deactivate_slot` is NOT wired into the live path in
Phase 0.** Justification (this is the top risk the architecture flagged): the current
stale-state teardown is **intentionally split** across two methods and is **NOT a pure
scrub** —
- `_check_maw_deaths` (`sandkings.py:6196`) [prov:V] does ownership wipe
  (`:6265`), pheromone zero (`:6266`), and `d.clear_slot(cid)` (`:6282`), but
  `clear_slot` deletes only **outbound** relations and deliberately **keeps inbound**
  relations to become the P12 folk-memory shadow (`politics.py:115–141`) [prov:V];
- `_respawn_colony` (`sandkings.py:6304`) [prov:V] then applies
  `apply_respawn_shadow(cid)` (`:6435`) to dampen that surviving inbound trust.

A full `_deactivate_slot` scrub clears **both** directions (no folk-memory shadow), so
wiring it into today's death→respawn path would **change behavior** (kill the P12 shadow)
and is therefore **NOT identity**. Per the tasking's stated preference ("wire into the
existing respawn ONLY if provably identity"), Phase 0 **defines + tests the choke point
standalone and leaves it unwired.** Later phases call it from the flag-gated
`DORMANT`/founding transitions, where a total scrub is the intended semantics.

---

## 3. Behavioral Spec

### 3.1 Scrub inventory — what state a slot carries (derived from the real teardown)

Enumerated by reading `_check_maw_deaths` + `_respawn_colony` + `politics.clear_slot`
[prov:V]. Each row is a distinct stale-state surface a refound could leak; `_deactivate_slot`
centralizes ALL of them:

| # | Surface | Where it lives | Scrub op |
|---|---------|----------------|----------|
| 1 | Pheromone channel | `self.pheromones.trails[:,:,:,cid,:]` | zero it (mirrors `sandkings.py:6266`) |
| 2 | Ownership voxels | `self.world.ownership == cid` | set to `-1` (mirrors `sandkings.py:6265`) |
| 3 | Politics — outbound relations | `diplomacy.relations[(cid, *)]` | delete (mirrors `clear_slot`, `politics.py:130–132`) |
| 3b| Politics — inbound relations | `diplomacy.relations[(*, cid)]` | delete (FULL scrub; NO folk-memory shadow) |
| 4 | Politics — truces/allies/rejected | keys containing `cid` in `truce_until`/`allied`/`rejected_at` | delete (mirrors `clear_slot`) |
| 5 | Politics — war targets | `war_target[cid]` and any `war_target[x]==cid` | pop / set `None` (mirrors `clear_slot`) |
| 6 | Politics — betrayal / hegemon | `last_betrayal[cid]`; `hegemon` if `==cid` | pop; clear hegemon to `None` |
| 7 | Thralls held BY this slot (captor) | units in OTHER colonies with `laboring_for == cid` | set `laboring_for=-1`, `defiance=0.0` (mirrors SJ6b, `sandkings.py:6227–6233`) |
| 8 | Inbound gifts | units in OTHER colonies with `gift_to == cid` | set `gift_to=-1` |
| 9 | Monitor state | `self.monitors[cid]` | pop (mirrors `sandkings.py:6432`) |
| 10| Learner state | `self.learners[cid]` | pop (mirrors `sandkings.py:6434`) |
| 11| Pending respawn | `self.pending_respawns[cid]` | pop (so a deactivated slot isn't also scheduled) |
| 12| This slot's own units | `colony.units` | clear (units of a deactivated slot vanish) |
| 13| Disposition | `colony.favoritism`, `colony.agitation`, `colony.confidence` | reset to neutral `0.0/0.0/0.5` |
| 14| Kin cache | `self._kin_epoch` | bump (mirrors `sandkings.py:6423`, forces `hostile()` re-read) |

**Out-of-scope (NOT scrubbed by `_deactivate_slot`, by design — flagged):**
- `sim.house_grudges` (`sandkings.py:2089`) [prov:V] is keyed by **house NAME**, not
  `colony_id`. Grudges are a lineage/dynasty property, not a slot property; a slot scrub
  must not erase another house's memory of a bloodline. POP-3 asserts id-keyed state is
  clean and asserts house-name grudges are **left intact** (they are not slot state).
- The `Colony` object itself is NOT replaced and the genome is NOT re-rolled — that is
  founding (later phase).

### 3.2 Pseudocode — `_deactivate_slot` (rote-implementable)

```
def _deactivate_slot(self, cid: int) -> None:
    # Require
    colony = self._colony_by_id(cid)
    assert colony is not None, f"_deactivate_slot: unknown colony id {cid}"

    # (1) pheromone channel
    self.pheromones.trails[:, :, :, cid, :] = 0.0
    # (2) ownership voxels
    self.world.ownership[self.world.ownership == cid] = -1

    # (3–6) politics: total slot clear (BOTH directions — no folk-memory shadow)
    d = getattr(self, 'diplomacy', None) or self._diplomacy()
    for (a, b) in list(d.relations.keys()):          # 3 + 3b: both directions
        if a == cid or b == cid:
            del d.relations[(a, b)]
    for key in [k for k in d.truce_until   if cid in k]: del d.truce_until[key]
    for key in [k for k in d.allied        if cid in k]: del d.allied[key]
    for key in [k for k in d.rejected_at   if cid in k]: del d.rejected_at[key]
    d.war_target.pop(cid, None)                       # 5
    for other_id, target in list(d.war_target.items()):
        if target == cid:
            d.war_target[other_id] = None
    d.last_betrayal.pop(cid, None)                    # 6
    if d.hegemon == cid:
        d.hegemon = None

    # (7,8) cross-colony unit references: thralls held by cid, gifts bound for cid
    for other in self.colonies:
        if other.colony_id == cid:
            continue
        for unit in other.units:
            if getattr(unit, 'laboring_for', -1) == cid:
                unit.laboring_for = -1
                unit.defiance = 0.0
            if getattr(unit, 'gift_to', -1) == cid:
                unit.gift_to = -1

    # (9,10,11) sim-level per-colony dicts
    if hasattr(self, 'monitors'):        self.monitors.pop(cid, None)
    if hasattr(self, 'learners'):        self.learners.pop(cid, None)
    if hasattr(self, 'pending_respawns'): self.pending_respawns.pop(cid, None)

    # (12) this slot's own units vanish
    colony.units.clear()

    # (13) disposition -> neutral
    colony.favoritism = 0.0
    colony.agitation = 0.0
    colony.confidence = 0.5

    # state + kin cache
    colony.pop_state = POP_DORMANT
    self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1   # 14

    # Assert (Guarantee)
    assert not (self.world.ownership == cid).any()
    assert not self.pheromones.trails[:, :, :, cid, :].any()
```

Notes for the implementer (no design latitude): use `list(...)` snapshots before any
`del` over a dict being mutated (as the existing `clear_slot` does). `_colony_by_id`
already exists (`sandkings.py:4717`) [prov:V]. Do not import or call `apply_respawn_shadow`
here — the FULL scrub is the point.

### 3.3 Behavioral Spec — save/load shim (pickle compatibility)

The repo normalizes older-checkpoint colonies inside `step()` via a getattr-guarded
default loop (`sandkings.py:1843–1864`) [prov:V]. Add `pop_state` to that loop so
pre-Phase-0 saves (which lack the field) load as `POP_ACTIVE`:

```
# inside the existing per-colony normalization loop (sandkings.py ~1850-1864),
# extend the (attr, default) tuple list with:
                                  ('pop_state', POP_ACTIVE),   # POP: lifecycle slot state
```

**Compat contract:**
- **Require:** an unpickled `Colony` may lack `pop_state` (old save) — never read it
  without a default.
- **Guarantee:** after one `step()` normalization pass, every colony has
  `pop_state == POP_ACTIVE`. Any read outside the normalization site uses
  `getattr(colony, 'pop_state', POP_ACTIVE)`.
- **Guarantee (sim flag):** `dynamic_population` is read as
  `getattr(sim, 'dynamic_population', DYNAMIC_POPULATION)`; old `SandKingsSimulation`
  pickles (lacking the attr) resolve to `False`.
- **Maintain:** adding these fields does not change pickle-ability of any existing object
  (plain str/bool scalars).

---

## 4. Identity-at-neutral guarantee (load-bearing)

**Require (hard identity):** with `dynamic_population == False` (the default), a full sim
run is **byte-identical** to the pre-Phase-0 build:
- No new RNG draw is introduced. (`pop_state`/`dynamic_population` assignment and the
  normalization tuple addition draw no randomness.) [prov:V — the additions are constant
  assignments only]
- No control-flow branch keys on the flag or on `pop_state` in Phase 0.
- The legacy spine `_check_maw_deaths → pending_respawns → _process_respawns →
  _respawn_colony` is **untouched** (not one line edited). [prov:V]
- `_deactivate_slot` is defined but **never called** at the flag-off default, so it
  cannot perturb any run.
- The full 45-suite battery stays green.

---

## 5. Acceptance criteria (POP-*) — `tests/test_population.py`

New test file, mirroring `tests/test_terrarium.py::make_sim` (seed 11, 40×30×12, 3
colonies) [prov:V] and the `tests/test_disposition.py` disposition idioms. Each POP-*
cites the clause it verifies.

### POP-1 — Identity (§4). Load-bearing.
- **Given** `make_sim()` (flag default off), **when** the legacy respawn contract runs
  (kill colony 2's maw → `_check_maw_deaths` → `_process_respawns` after `RESPAWN_DELAY`),
  **then** it behaves exactly as `test_terrarium.py::test_maw_death_cascade_and_respawn`
  (`tests/test_terrarium.py:135`) [prov:V]: `victim_id in pending_respawns`;
  units corpsed; `ownership==victim_id` empty; pheromone channel zeroed; after
  `RESPAWN_DELAY`, slot refills with same `colony_id`, 3 starter workers,
  `victim_id not in pending_respawns`.
- **And** `getattr(sim, 'dynamic_population', None) is False`.
- **And** the full 45-suite battery remains green (run the suite; no delta).

### POP-2 — `pop_state` field (§2.3, §3.3).
- Fresh colony: `sim.colonies[0].pop_state == POP_ACTIVE`.
- Getattr guard on a bare/old object: build a `Colony` via `object.__new__`-style bare
  instance OR delete the attr (`del c.pop_state`), then assert
  `getattr(c, 'pop_state', POP_ACTIVE) == POP_ACTIVE`, and that one `sim.step()`
  normalization restores `c.pop_state == POP_ACTIVE`.
- Pickle round-trip: `pickle.loads(pickle.dumps(colony)).pop_state == POP_ACTIVE`.

### POP-3 — Scrub choke point (§2.4, §3.1, §3.2). Trickiest integration.
Permutation battery — **≥3 varied pre-states**, all must scrub clean after
`sim._deactivate_slot(cid)`. Vary entity/structure/values (do NOT seed from one case):
- **P1 (politics + ownership):** set inbound & outbound relations, a truce, an ally latch,
  a war target both directions, and paint ownership voxels for `cid`. After scrub:
  no `relations` key touching `cid`; no `truce_until`/`allied` key with `cid`;
  `war_target` clean; `not (ownership==cid).any()`.
- **P2 (thralls + gifts + pheromones):** make units in another colony `laboring_for == cid`
  and one unit `gift_to == cid`; deposit pheromones on channel `cid`. After scrub:
  those units `laboring_for == -1` (defiance 0) and `gift_to == -1`;
  `not trails[...,cid,:].any()`.
- **P3 (disposition + monitors/learners + pending):** set `favoritism/agitation/confidence`
  off-neutral; touch `sim.monitors[cid]`/`sim.learners[cid]`; schedule
  `pending_respawns[cid]`. After scrub: disposition == `0.0/0.0/0.5`; `cid` absent from
  `monitors`, `learners`, `pending_respawns`; `colony.pop_state == POP_DORMANT`.
- **And (out-of-scope guard):** seed a `sim.house_grudges` entry keyed by a house NAME and
  assert `_deactivate_slot` leaves it intact (slot scrub must not erase lineage grudges).

### POP-4 — `MAX_COLONIES` cap (§2.1).
- `MAX_COLONIES == 8` and `0 < sim.num_colonies <= MAX_COLONIES`.
- Construction across `num_colonies ∈ {2, 4, 8}` succeeds without raising (assert
  `len(sim.colonies) == n` and `sim.pheromones.trails.shape[3] == n`).
- **Known-limitation note (do not fix in Phase 0):** `Colony.COLORS` has 4 entries and
  `color = COLORS[colony_id % 4]` (`sandkings.py:1144`) [prov:V], so ids 4–7 reuse colors
  0–3. Distinct 8-slot palette is a later-phase concern; Phase 0 only asserts construction
  does not crash. There is no `COLOR_PAIRS` to extend.

---

## 6. Enumerated Phase-0 edits (for the implementer)

All in `sandkings.py` unless noted. Rote, no design decisions:

1. **Module constants** — after `RESPAWN_FOOD` (`:63`): add `MAX_COLONIES`,
   `DYNAMIC_POPULATION`, `POP_ACTIVE`, `POP_SUCCESSION`, `POP_DORMANT`, `POP_STATES`
   (§2.1 block, verbatim).
2. **Sim flag** — in `SandKingsSimulation.__init__` (`:1556`), after the attribute block
   (e.g. after `:1580`): `self.dynamic_population = DYNAMIC_POPULATION`.
3. **Colony field** — in `Colony.__init__` after `:1169`:
   `self.pop_state = POP_ACTIVE`.
4. **Save shim** — extend the normalization tuple list at `:1850-1862` with
   `('pop_state', POP_ACTIVE),` (§3.3).
5. **New method** — add `SandKingsSimulation._deactivate_slot(self, cid)` (§3.2 pseudocode
   verbatim). Place near the respawn spine (after `_respawn_colony`, ~`:6440`). **Do not
   wire any call site.**
6. **New tests** — create `tests/test_population.py` with `test_pop1_identity`,
   `test_pop2_state_field`, `test_pop3_scrub_battery` (P1/P2/P3 + grudge guard),
   `test_pop4_max_colonies`, mirroring `test_terrarium.py`/`test_disposition.py` imports
   and `make_sim` (§5).

**No edits to** `_check_maw_deaths`, `_process_respawns`, `_respawn_colony`, `politics.py`,
`num_colonies` resolution, or any runtime branch. No merge-debris dedup (none exists, §0).

---

## 7. Verification-against-code log (what was confirmed at spec time)

- `pending_respawns` init: single, `sandkings.py:1570`. Duplicate claim **DENIED** [prov:V].
- `record_event`: symbol absent repo-wide. Duplicate claim **DENIED** [prov:V].
- Respawn spine confirmed: `_check_maw_deaths` `:6196`, `_process_respawns` `:6296`,
  `_respawn_colony` `:6304`, dispatched from `step()` at `:2042-2043` [prov:V].
- Scrub surfaces confirmed: pheromone `:6266`, ownership `:6265`, `clear_slot`
  outbound-only + inbound-shadow `politics.py:115-141`, thrall-free SJ6b `:6227-6233`,
  monitors/learners pop `:6432/:6434`, `apply_respawn_shadow` `:6435` [prov:V].
- Disposition fields: `favoritism/agitation/confidence` on `Colony`, `sandkings.py:1161-1163`;
  normalization loop `:1843-1864` [prov:V].
- `Colony.COLORS` = 4 entries, modulo-indexed `:1136/:1144`; `COLOR_PAIRS` absent;
  `bound_to` absent; thrall link is `laboring_for` `:1029`, envoy link `gift_to` `:1021`
  [prov:V].
- Governing decision record `2026-07-11-dynamic-population-and-succession.md` **absent**
  from `docs/decisions/` (§0).
