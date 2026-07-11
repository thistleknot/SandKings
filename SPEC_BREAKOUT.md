# SPEC: The Breakout (Round 9) — BRK-A / BRK-B / BRK-C

Placement decision: **new file `SPEC_BREAKOUT.md`**, cross-referencing
`SPEC_KEEPER.md` K10 (root intent — "the terminal is actuator port 7 on the
VM") and `SPEC_AWARENESS.md` AW4 (revelation, coupled to `_escape`). Rationale:
the feature spans three subsystems (the machine-age VM, the HUD/dashboard render
layer, and the keeper-verb API) plus a new acceptance battery. Folding it into
K10 alone would bury the VM address-space fix under an already-closed clause and
mix render/verb concerns into the keeper spec. This matches the repo's
one-spec-per-arc pattern (SPEC_MACHINE_AGE, SPEC_AWARENESS, SPEC_WEATHER). K10
and AW4 are referenced, not duplicated.

Root cause (verbatim diagnosis): organic breakout is **structurally
impossible**, not merely rare. Breakout = `_escape(colony)`
(`sandkings.py:3189`), reached only from `_terminal_command`
(`sandkings.py:3805-3810`) at `terminal_uses == TERMINAL_MASTERY`, reached only
from `_actuate` port 7 (`sandkings.py:5586-5591`). But the VM can never emit
port 7: `ACTUATOR_NAMES` has 7 entries (`machines.py:52-53`), the ACT opcode
masks `port = a % len(ACTUATOR_NAMES)` = `a % 7` -> 0..6 (`machines.py:130`),
and the GP tinkerer only ever generates `randrange(len(ACTUATOR_NAMES))` = 0..6
(`machines.py:230,257`). Port 7 is unaddressable; `terminal_uses` is frozen at
0. K10 always *intended* port 7 to be the terminal ("actuator port 7 on the
VM", `SPEC_KEEPER.md:147`); the address space was simply one entry too short.

---

## Constants + Provenance

| Constant | Value | Location | Status | Meaning |
|---|---|---|---|---|
| `TERMINAL_UNLOCK` | 40 | `sandkings.py:306` | existing | pi operate-ticks before the terminal opens (K10) |
| `TERMINAL_MASTERY` | 16 | `sandkings.py:307` | existing | successful commands before the breach |
| `PI_FUEL` | 128 | `machines.py:33` | existing | pi-gift ops budget; the "is-pi" discriminator is `fuel_cap > VM_FUEL` |
| `VM_FUEL` | 64 | `machines.py:18` | existing | base VM budget; pi controllers exceed it |
| `ACTUATOR_NAMES` | 8-tuple (was 7) | `machines.py:52-53` | **CHANGED (Part A)** | adds `"TERMINAL"` as the 8th (virtual) port |

No new numeric constants are introduced. Part A widens an existing tuple; the
modulo base changes from 7 to 8 as a *derived* consequence
(`len(ACTUATOR_NAMES)`), not a new literal.

`ACTUATOR_NAMES` "TERMINAL" is a **virtual actuator**: it has NO `Device`, NO
`ACTUATOR_WEAR` entry, NO `CARTRIDGE_KINDS` entry, and is never built or worn. It
exists solely so `a % len(ACTUATOR_NAMES)` and `randrange(len(ACTUATOR_NAMES))`
can address index 7, which `_actuate` intercepts at `sandkings.py:5586` and
routes to `_terminal_command`, returning at `:5591` **before** any
`ACTUATOR_NAMES[port]`, `ACTUATOR_WEAR[kind]`, or cartridge lookup. Verified:
`ACTUATOR_NAMES` is referenced in exactly four places (`machines.py:130,166,230,257`)
and `sandkings.py:5592`; none iterates the tuple to build devices, so a
name without wear/cartridge metadata is inert.

---

# PART A — Open the address space (the root fix)

## Requirements (BRK-A)

- **BRK-A.R1** The VM ACT opcode CAN emit port 7. After the fix,
  `a % len(ACTUATOR_NAMES)` yields 7 for some evolvable `a` (e.g. `a == 7`).
  Acceptance: BRK-A1.
- **BRK-A.R2** The GP tinkerer CAN generate an ACT targeting port 7
  (`randrange(len(ACTUATOR_NAMES))` now spans 0..7). Acceptance: BRK-A1.
- **BRK-A.R3** A pi-gifted, unlocked colony's `terminal_uses` is now
  reachable (> 0 achievable) through the VM path. Organic breakout is no longer
  structurally impossible. Rate need not be fast, only POSSIBLE. Acceptance:
  BRK-A1.
- **BRK-A.R4** The pi/unlock gate is unchanged: a colony **without** a pi
  controller (no controller with `fuel_cap > VM_FUEL` at
  `operate_ticks >= TERMINAL_UNLOCK`) still cannot advance `terminal_uses`. The
  fix opens the port; it does not remove the requirement. Acceptance: BRK-A2.
- **BRK-A.R5** The seven physical actuators (ports 0..6) keep their existing
  names and semantics; port 7 never reaches the name/wear/cartridge lookup.
  Acceptance: existing `test_machines.py` GATE/VALVE/RAD tests stay green.

## Chosen approach — Option (a): add the 8th name

**Decision: Option (a)** — append `"TERMINAL"` to `ACTUATOR_NAMES` (8 entries).

Justification (why (a) over (b)/(c)):

1. **Determinism blast radius is identical to (b).** Both (a) and (b) change the
   modulo base from 7 to 8. Any RNG-stream or ACT-port shift caused by
   `randrange(8)`/`% 8` happens under either option. (a) buys nothing worse than
   (b) on determinism.
2. **(a) is strictly less code.** Lines `130`, `166`, `230`, `257` all read
   `len(ACTUATOR_NAMES)` dynamically, so the single tuple edit propagates
   automatically. Option (b) would require editing three of those sites to a new
   `VM_ACTUATOR_PORTS` constant AND still need a guard at `machines.py:166`
   (`ACTUATOR_NAMES[a % len(ACTUATOR_NAMES)]` would show the wrong name — `7 % 7
   == 0` -> "GATE" — for a port-7 program). Option (a) makes `listing()` render
   `ACT TERMINAL, Rn` correctly and for free.
3. **(a) matches K10 literally.** `SPEC_KEEPER.md:147`: "the terminal is actuator
   port 7 on the VM." Under (a), port 7 IS a named actuator. The manager panel
   disassembly names it. Fiction and mechanism agree.
4. **Auxiliary-structure safety confirmed.** Grep shows `ACTUATOR_NAMES` is never
   iterated to build devices; `_actuate` short-circuits port 7 before any
   `ACTUATOR_WEAR`/`CARTRIDGE_KINDS` access. A name lacking wear/cartridge
   metadata is inert. (c)'s extra surgery is unnecessary.

## Structural (Part A)

Single edit, `machines.py:52-53`:

```
# BEFORE
ACTUATOR_NAMES = ("GATE", "VALVE", "ALARM", "BEACON",
                  "EXCAVATE", "DEPOSIT", "RAD")
# AFTER — TERMINAL is the virtual K10 shell port (index 7); no Device,
# no ACTUATOR_WEAR/CARTRIDGE_KINDS entry (see Provenance); _actuate
# intercepts port 7 before any name/wear/cartridge lookup.
ACTUATOR_NAMES = ("GATE", "VALVE", "ALARM", "BEACON",
                  "EXCAVATE", "DEPOSIT", "RAD", "TERMINAL")
```

No other machines.py edit. Lines `130` (`port = a % len(ACTUATOR_NAMES)`), `166`
(`ACTUATOR_NAMES[a % len(ACTUATOR_NAMES)]`), `230` and `257`
(`rng.randrange(len(ACTUATOR_NAMES))`) inherit the widened range with no textual
change.

## Behavioral (Part A) — no logic change

`_actuate` (`sandkings.py:5586-5591`) already contains the port-7 branch and its
pi/unlock gate. It was dead code because port 7 was unaddressable. Part A does
NOT touch `_actuate`, `_terminal_command`, or `_escape`; it only makes the
existing branch reachable. Contract of the existing gate (restated, unchanged):

- **Require**: `port == 7`.
- **Guarantee**: `_terminal_command(colony, value)` runs **iff** some controller
  has `fuel_cap > VM_FUEL` AND `operate_ticks >= TERMINAL_UNLOCK`; then returns.
- **Maintain**: ports 0..6 route to physical actuators exactly as before.

## Test reconciliation (Part A) — enumerated

Read of `tests/test_machines.py` completed. Findings, per assertion:

- `test_vm_act_budget_and_registers_persist` (`:48-57`): ACT uses `a == 0` ->
  `0 % 8 == 0`. Unchanged. **SAFE.**
- `test_demo_program_siege_gate` (`:60-68`): DEMO_PROGRAM ACT ports `a == 0`,
  `a == 2` -> `% 8` == `% 7` for these values. Asserts `(0,1)`, `(2,1)`,
  `(0,0)`. Unchanged. **SAFE.**
- `test_gate_actuator_closes_and_opens`, `test_valve_alarm_beacon`,
  `test_geo_and_rad_cartridges` (`:83-135`): call `sim._actuate` with explicit
  ports 0-6 (never via VM mask). **SAFE.**
- `test_tinkerer_reverts_worse_programs` (`:173-181`, `random.seed(3)`): the
  seeded RNG stream **shifts** — `rng.randrange(8)` at the ACT-retarget/build
  sites draws differently than `randrange(7)`, so the 100 proposed programs
  differ from the pre-fix trajectory. But the assertions are purely structural:
  `1 <= len(cand) <= 32` and "all runnable" (`Controller(0,cand).tick(...)` with
  a no-op `act` lambda). A port-7 ACT is runnable (no-op act ignores the port).
  **EXPECTED TO STAY GREEN; robust by design. Re-run to confirm.**
- `test_machine_state_pickles` (`:183-196`, seeded 30 steps): trajectory may
  shift, but assertions check only pickle round-trip (ancient controller,
  device kind, `revived.step()`). **EXPECTED GREEN; re-run to confirm.**
- **No assertion in `test_machines.py` pins `len(ACTUATOR_NAMES) == 7`, nor the
  exact VM-masked ACT port, nor exact tinkered program content.** So no
  `test_machines.py` assertion requires editing. If any seeded assertion is
  found to shift on the actual run, updating it is a **legitimate re-baseline**
  (the modulo base genuinely moved), not a regression — call it out explicitly
  when it happens.

Wider suite flag (behavior change, not a bug): port 7 becoming emittable means
that in a **live** seeded sim, a pi-gifted colony whose tinkerer evolves an ACT
port-7 program CAN now organically advance `terminal_uses` and eventually
breach. Any seeded integration test that (a) drives a colony into the machine
arc with a pi gift AND (b) asserts "never breaches / terminal_uses stays 0"
will shift — that is the intended behavior change and a legitimate re-baseline.
Highest-likelihood candidates to eyeball first: `tests/test_enlightenment.py`,
`tests/test_awareness.py`, `tests/test_machines.py`. The remaining seeded
suites almost never reach the pi/claimed machine arc, so trajectory divergence
there is improbable; the full battery is the confirmatory check (run once after
the edit), not the debugging loop.

---

# PART B — The breakout-proximity gauge

## Requirements (BRK-B)

- **BRK-B.R1** A pure function `breakout_progress(colony) -> (phase, fraction,
  label)` reports how close a colony is to breakout, with no pygame dependency,
  usable headlessly by both the HUD and the dashboard. Acceptance: BRK-B1.
- **BRK-B.R2** The HUD (`build_hud_entries`) shows a per-colony gauge line after
  the maw line, reusing `hp_bar()`, skipped/replaced once breached. Acceptance:
  BRK-B1 (fn) + manual/HUD test.
- **BRK-B.R3** `dashboard.build_state` exposes `terminal_uses`,
  `breach_proximity` (float in [0,1]), and `breach_phase` (str) per colony.
  Acceptance: BRK-B2.
- **BRK-B.R4** (Optional) A terrarium-wide "closest to breakout" line in the
  global keeper-state HUD block.

## Structural (Part B)

### B1. Pure helper — in `sandkings.py` (module scope, near the Colony class)

**Placement rationale**: `live_view.py` hard-imports `pygame` at module top
(`live_view.py:18`), so the pure fn CANNOT live there without dragging pygame
into the headless dashboard. `sandkings.py` is pygame-free, already owns
`TERMINAL_UNLOCK`/`TERMINAL_MASTERY` and `Colony`, and is imported by BOTH
`live_view` and `dashboard`. The `label` is renderer-agnostic text (no bar
glyphs); the HUD composes the visual bar by reusing `hp_bar()` (BRK-B.R2). This
is the single source of truth for phase+fraction (DRY).

```
def breakout_progress(colony) -> Tuple[str, float, str]:
    """BRK-B: how close a colony is to breakout. Pure, no pygame.

    Returns (phase, fraction, label):
      phase in {"breached","mastering","unlocking","nopi"}
      fraction in [0.0, 1.0]  (breach_proximity)
      label: renderer-agnostic annotation (NO bar glyphs; the HUD adds
             the hp_bar). Deterministic; no RNG.

    Preconditions: colony may lack any of breached/controllers/
      terminal_uses (all read via getattr with defaults) — a bare or
      revived colony is valid input.
    """
    from machines import VM_FUEL
    if getattr(colony, 'breached', False):
        return ("breached", 1.0, "BREACHED")
    controllers = getattr(colony, 'controllers', None) or []
    pi_ticks = [c.operate_ticks for c in controllers
                if getattr(c, 'fuel_cap', VM_FUEL) > VM_FUEL]
    if not pi_ticks:
        return ("nopi", 0.0, "no pi")
    max_ticks = max(pi_ticks)
    if max_ticks < TERMINAL_UNLOCK:
        frac = max(0.0, min(1.0, max_ticks / TERMINAL_UNLOCK))
        return ("unlocking", frac, "unlock")
    uses = int(getattr(colony, 'terminal_uses', 0))
    frac = max(0.0, min(1.0, uses / TERMINAL_MASTERY))
    return ("mastering", frac, f"breach {uses}/{TERMINAL_MASTERY}")
```

Contract:
- **Require**: `colony` is a Colony-like object (duck-typed via getattr).
- **Guarantee**: returns a 3-tuple; `fraction` clamped to [0,1]; `phase` is one
  of the four literals; deterministic.
- **Assert** (test-side): `0.0 <= fraction <= 1.0`.

### B2. HUD line — `live_view.build_hud_entries` (`live_view.py`, after the maw line ~:485)

Insert immediately after the `entries.append((maw_line, color))` at
`live_view.py:485`, inside the same `for colony in sim.colonies:` living-colony
branch:

```
# BRK-B: breakout-proximity gauge (reuses hp_bar; skipped once breached)
from sandkings import breakout_progress
phase, frac, label = breakout_progress(colony)
if phase == "breached":
    gauge = "  BREACHED"
elif phase == "nopi":
    gauge = "  breakout: no pi"
elif phase == "unlocking":
    gauge = f"  unlock:{hp_bar(frac)}"
else:  # mastering
    uses = int(getattr(colony, 'terminal_uses', 0))
    gauge = f"  breach:{hp_bar(frac)} {uses}/{TERMINAL_MASTERY}"
entries.append((gauge, color))
```

`TERMINAL_MASTERY` and `hp_bar` are already in scope in `live_view`
(`hp_bar` defined `:373`; `TERMINAL_MASTERY` import to be added to the existing
`from sandkings import (...)` block at `live_view.py:20-21`).

### B3. Dashboard state — `dashboard.build_state` (`dashboard.py`, ~:99-114)

Add three keys to the per-colony dict, next to the existing `"breached"` /
`"aware"` fields:

```
# BRK-B: breakout-proximity telemetry (mirrors breached/aware)
"terminal_uses": int(getattr(colony, 'terminal_uses', 0)),
"breach_proximity": round(float(_bp_frac), 2),   # [0,1]
"breach_phase": str(_bp_phase),
```

where, computed once above the dict literal (after the `colony` loop header):

```
from sandkings import breakout_progress
_bp_phase, _bp_frac, _bp_label = breakout_progress(colony)
```

### B4. (Optional) Global "closest to breakout" HUD line — `live_view.py:425-438` block

Spec'd as OPTIONAL. If implemented, inside the global keeper-state block
(the `if callable(getattr(sim, 'season_index', None)):` region, near the
BOUND/keeper-influence inserts), add:

```
# BRK-B.R4 (optional): the terrarium's closest house to the glass
from sandkings import breakout_progress
ranked = [(breakout_progress(c)[1], c) for c in sim.colonies
          if c.is_alive() and not getattr(c, 'breached', False)]
if ranked:
    frac, c = max(ranked, key=lambda t: t[0])
    if frac > 0.0:
        entries.insert(5, (f"Closest to glass: House {c.colony_id}"
                           f" {frac*100:.0f}%", (122, 162, 255)))
```

## Behavioral (Part B)

`breakout_progress` phase ladder (deterministic, first match wins):
1. `breached` (colony.breached truthy) -> (1.0, "BREACHED").
2. `nopi` (no controller with fuel_cap > VM_FUEL) -> (0.0, "no pi").
3. `unlocking` (max pi operate_ticks < TERMINAL_UNLOCK) -> (ticks/40, "unlock").
4. `mastering` (unlocked) -> (min(1, uses/16), "breach uses/16").

Note the deliberate ordering: `breached` is checked FIRST, so a breached colony
that still has a pi controller reports "breached", not "mastering".

---

# PART C — The keeper "open the door" action

## Requirements (BRK-C)

- **BRK-C.R1** `keeper_open_door(self, colony)` on the simulation breaches a
  colony directly: emits the open-door flavor line, then calls `_escape`
  (reveal + enlightenment). Idempotent. Acceptance: BRK-C1.
- **BRK-C.R2** Honors the bound-god gate: with `keeper_bound=True` the hand is
  stayed — no breach, logs the stayed line. Acceptance: BRK-C2.
- **BRK-C.R3** The open-door flavor line persists in the chronicle
  (SALIENCE >= PRUNE_KEEP_SALIENCE). Acceptance: BRK-C1 (line present) + chronicle
  salience table.
- **BRK-C.R4** Wired into all three clients: live_view key, dashboard endpoint +
  button, play_kit REPL command. Acceptance: BRK-C3 (at least one path).

## Structural (Part C)

### C1. Sim verb — `keeper_open_door` (`sandkings.py`, near `keeper_gift` :2819)

```
def keeper_open_door(self, colony: Colony):
    """BRK-C/K10: the keeper's mercy - lift the glass for one house.
    Mirrors every keeper verb: honors the PS5 bound-god gate first, so a
    bound keeper's hand will not move. Then breaches via _escape (AW4
    reveal + EN2 enlightenment). Idempotent on an already-breached colony.

    Preconditions: colony is a living Colony (or None -> no-op).
    Failure modes: bound keeper -> no-op + stayed line; already breached
    -> no-op (no duplicate flavor line).
    """
    if self._hand_stayed():        # PS5: the bound god cannot act
        return
    if colony is None or getattr(colony, 'breached', False):
        return
    self._log_event(f"The keeper opens the door - House "
                    f"{self._house_name(colony)} is invited to step through")
    self._escape(colony)           # AW4 reveal + EN2 enlightenment; sets breached
```

**Design decisions (stated per instruction):**
- **Bound-god gate honored** (not bypassed) for consistency with every other
  keeper verb (`keeper_gift` gates at `sandkings.py:2822`). A bound god's hand
  will not move. Flipping to bypass is a one-line change (delete the
  `_hand_stayed()` guard) — a deliberate design choice, not a bug; left honored.
- **Early `breached` guard added** (beyond `_escape`'s own idempotency) so a
  second call does NOT re-emit the flavor line / spam the log. `_escape` is
  still internally idempotent (`sandkings.py:3194-3195`); the guard just avoids
  the redundant flavor line. Net effect: fully idempotent on state AND log.
- **No "no longer a wall" line**: that phrase is the terminal-mastery flavor
  (`sandkings.py:3809`), emitted only on the organic path. The keeper's door
  emits its own flavor line + `_escape`'s reveal ("glimpses the world beyond the
  glass") + ascend ("ascends") lines. Do NOT add the terminal line here.

Contract:
- **Require**: sim has `_hand_stayed`, `_house_name`, `_log_event`, `_escape`
  (all present).
- **Guarantee**: if not bound and colony not already breached,
  `colony.breached == True` and `colony.enlightened == True` after return, and
  the open-door + reveal + ascend lines are in `sim.events`.
- **Maintain**: a bound keeper leaves `colony.breached` unchanged.

### C2. Chronicle salience — `chronicle.py` SALIENCE (`:28-67`)

Add one row (>= PRUNE_KEEP_SALIENCE=7 so it is never pruned). Place before the
generic keeper rows, e.g. adjacent to `("no longer a wall", 10)` (`:49`):

```
("opens the door", 8),          # BRK-C: the keeper's mercy breach
```

### C3. live_view key — `handle_event` (`live_view.py`, ~:1316 firecracker branch)

Add a new key branch mirroring the `K_u` firecracker branch (`:1316-1319`). Use
`K_o` (free). Insert after the `K_u` branch:

```
elif key == pygame.K_o:                     # BRK-C: keeper opens the door
    target = _breakout_target(self)
    if target is not None:
        with self.runner.lock:
            self.sim.keeper_auto = False
            self.sim.keeper_open_door(target)
```

Target-selection helper (module-level fn in `live_view.py`, deterministic):

```
def _breakout_target(view) -> Optional[Colony]:
    """BRK-C target rule: inspected unit/maw's colony, else the living
    colony whose maw is nearest the cursor (covers 'under the cursor'
    and the colony-0 degenerate). Never a beast (no colony_id)."""
    insp = view.inspected                      # ('unit'|'maw'|'beast', obj)
    if insp is not None and insp[0] in ('unit', 'maw'):
        cid = getattr(insp[1], 'colony_id', None)
        if cid is not None:
            c = view.sim._colony_by_id(cid)
            if c is not None and c.is_alive():
                return c
    living = [c for c in view.sim.colonies if c.is_alive()]
    if not living:
        return None
    cx, cy = view.cursor
    def _d2(c):
        mx, my, _ = c.maw.position
        return (mx - cx) ** 2 + (my - cy) ** 2
    return min(living, key=_d2)
```

`self.inspected` schema confirmed `('unit'|'maw'|'beast', object)`
(`live_view.py:1088`); `self.cursor` is `(x, y)` (`:1087`); `_colony_by_id` is a
sim method (`sandkings.py`, used at `:2844` etc.).

### C4. live_view legend/help text (`live_view.py:493-503` and `build_legend_entries` :742)

- In the help block (`:493-503`), add the key to the keeper section, e.g. append
  to the "GIFTS"/keeper lines a line:
  `"       o open the door (breakout)",`.
- In `build_legend_entries` (`:742`), add a legend row in the keeper-verbs area
  (near the "L close  I inspect" region) describing `o  open the door -> breach`.

### C5. Dashboard endpoint + button — `dashboard.py`

Body model (add beside the other `*Body` classes ~`:351-394`):

```
class OpenDoorBody(BaseModel):
    colony_id: int
```

Endpoint (mirror `gift` `:465-470`, colony-id body like `release`/`speak`):

```
@app.post("/api/keeper/opendoor")
def opendoor(body: OpenDoorBody):
    with runner.lock:
        _disarm_auto()
        colony = runner.sim._colony_by_id(body.colony_id)
        if colony is not None:
            runner.sim.keeper_open_door(colony)
        return build_state(runner.sim)
```

Button (mirror the Tech Gift button `:686`; place in the actions bar). Uses the
JS `selected` colony id (`dashboard.py:719`):

```
<button class="act breach" onclick="openDoor()">Open the Door</button>
```

JS helper (near `post`/`release` `:722-726`):

```
function openDoor(){
  if(selected==null){flash('select a house first');return;}
  post('/api/keeper/opendoor',{colony_id:selected});
}
```

The `.act.breach` CSS class already exists (`dashboard.py:661`); `--breach`
color already defined (`:590`).

### C6. play_kit REPL — `play_kit.py`

Terrarium method (mirror the thin wrappers `:75-79`):

```
def open_door(self, colony_id: int = 0) -> Dict:
    return self._post("/api/keeper/opendoor", {"colony_id": int(colony_id)})
```

Dispatch branch in `dispatch` (`:351-408`, after the `ignite` branch `:373`):

```
elif cmd in ("opendoor", "escape", "breakout"):
    t.open_door(int(args[0]) if args else 0)
```

Note: `play_kit` already calls `sim._escape` directly in scenarios
(`:240,255`); those stay unchanged. The REPL path goes through the HTTP endpoint
(Terrarium is HTTP-backed), which calls `keeper_open_door` (honoring the
bound-god gate), NOT `_escape` directly — so the REPL respects the gate while
the canned scenarios keep their direct-breach behavior.

## Behavioral (Part C)

`keeper_open_door` control flow:
1. `_hand_stayed()` truthy (keeper_bound) -> log stayed line (once) -> return,
   no breach. [BRK-C2 bound branch]
2. colony None or already breached -> return, no-op. [idempotency]
3. else: log open-door flavor line -> `_escape(colony)` -> colony.breached=True,
   colony.enlightened=True, reveal + ascend lines emitted. [BRK-C1]

---

# ACCEPTANCE (BRK-*)

New file `tests/test_breakout.py` for BRK-A1/A2, BRK-B1, BRK-C1/C2; additions to
`tests/test_dashboard.py` for BRK-B2 and BRK-C3. Mirror each target file's
existing idioms (`make_sim`, seeded sims, TestClient).

### BRK-A1 — address space opened (root fix)
Rote steps:
1. **VM mask reaches 7**: `c = Controller(0, [("LET",0,0,0),("ACT",7,0,0)])`;
   `ports=[]`; `c.tick(lambda p:0, lambda p,v: ports.append(p))`;
   `assert 7 in ports`. (Pre-fix `7 % 7 == 0` would fail this.)
2. **Tinkerer reaches 7**: `import random; rng=random.Random(0); t=GPTinkerer();
   seen=set()`; loop 500x: `instr=t._random_instr(rng, 6)`; if `instr[0]=="ACT":
   seen.add(instr[1])`; `assert 7 in seen`.
3. **Organic reachability end-to-end**: `sim=make_sim()`; `colony=sim.colonies[0]`;
   `colony.machine_arc='claimed'`; give a pi controller:
   `ctrl=Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)`;
   `ctrl.operate_ticks = TERMINAL_UNLOCK`; `colony.controllers=[ctrl]`;
   `sim._actuate(colony, 7, 1)`; `assert getattr(colony,'terminal_uses',0) == 1`.
   (Proves VM port 7 -> `_actuate` gate -> `_terminal_command` -> `terminal_uses++`.)

### BRK-A2 — still gated (pi requirement intact)
`sim=make_sim()`; `colony=sim.colonies[1]`; give a NON-pi controller
`Controller(colony.colony_id)` (fuel_cap == VM_FUEL) with
`operate_ticks = TERMINAL_UNLOCK`; `sim._actuate(colony, 7, 1)`;
`assert getattr(colony,'terminal_uses',0) == 0`. The port opens; the pi gate
(`fuel_cap > VM_FUEL`) still holds.

### BRK-B1 — gauge pure fn (`breakout_progress`), no pygame
Deterministic table (build bare objects or use a real colony; getattr-safe):
- **no-pi**: colony with `controllers=[]`, `breached=False` ->
  `("nopi", 0.0, "no pi")`.
- **unlocking**: one pi controller (`fuel_cap=PI_FUEL`) at
  `operate_ticks=10` -> `("unlocking", 0.25, "unlock")` (10/40).
- **mastering**: pi controller at `operate_ticks=TERMINAL_UNLOCK`,
  `terminal_uses=4` -> `("mastering", 0.25, "breach 4/16")`.
- **breached**: `breached=True` -> `("breached", 1.0, "BREACHED")`.
- Assert `0.0 <= fraction <= 1.0` in every case. No pygame import.

### BRK-B2 — dashboard state exposes gauge
`build_state(sim)` per-colony dict contains keys `terminal_uses` (int),
`breach_proximity` (float, `0.0 <= v <= 1.0`), `breach_phase` (str in the four
literals). Assert presence + type + range on at least one colony. Mirror
existing `test_dashboard.py` build_state assertions.

### BRK-C1 — open the door breaches
`sim=make_sim()`; `colony=sim.colonies[0]`; `sim.keeper_open_door(colony)`;
assert `colony.breached is True` and `colony.enlightened is True`; assert some
event message contains "opens the door", one contains "glimpses the world"
(reveal), one contains "ascends". Call `sim.keeper_open_door(colony)` again;
assert still `breached is True`, no exception, and NO second "opens the door"
line was appended (idempotent on log too).

### BRK-C2 — bound-god gate
`sim=make_sim()`; `sim.keeper_bound=True`; `colony=sim.colonies[0]`;
`sim.keeper_open_door(colony)`; assert `colony.breached is False` and some
event contains "will not move" (the stayed line). Then `sim.keeper_bound=False`;
`sim.keeper_open_door(colony)`; assert `colony.breached is True`.

### BRK-C3 — client wiring (at least one path, lightweight)
Dashboard TestClient (mirror `test_dashboard.py`): build app, POST
`/api/keeper/opendoor` with `{"colony_id": 0}`; assert 200 and the returned
state shows colony 0 `breached True` (and `breach_phase == "breached"`). This
proves the endpoint reaches `keeper_open_door`.

---

# Implementation order (low-risk first, determinism-shift last)

1. **Part C** (keeper verb + 3 client hooks + salience): pure additions, zero
   determinism impact. Verify BRK-C1/C2/C3.
2. **Part B** (pure fn in sandkings + HUD line + dashboard keys): additive,
   pygame-free core. Verify BRK-B1/B2.
3. **Part A** (the one-tuple VM fix + test reconciliation): the
   determinism-shifting root fix, done LAST so its re-baseline battery runs
   against an otherwise-green tree. Verify BRK-A1/A2, then run the FULL suite
   once as the confirmatory check; treat any shifted seeded machine-arc
   assertion as a legitimate re-baseline (document each), not a regression.

Every existing test expected to (possibly) shift is flagged in "Test
reconciliation (Part A)": `test_machines.py::test_tinkerer_reverts_worse_programs`
and `::test_machine_state_pickles` (expected green, re-run to confirm), and the
live-sim breach candidates `test_enlightenment.py` / `test_awareness.py`
(eyeball if the full run shifts them).
