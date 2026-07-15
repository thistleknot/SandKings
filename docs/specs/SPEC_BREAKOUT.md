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

---

# PART D — Breakout efficacy: reward-shape the tinker fitness

## Root cause (review finding F1) — Part A is necessary but NOT sufficient

Part A made VM port 7 **addressable** (the modulo/randrange range now spans
0..7). But addressability only makes a port-7 program *possible*; it does not
make evolution *keep* one. The GP tinker fitness at `sandkings.py:5937` is

```
value = (colony.maw.food_stored + 15 * len(colony.units))
```

— it has **no term for terminal use / breakout progress**. The keep-if-improved
rule (`sandkings.py:5938-5957`) computes a per-window delta
`u = (value - last) / PROGRAM_REVIEW` and **reverts** any candidate whose
`u < baseline` (`u_ema`). A program that emits `ACT TERMINAL` (port 7) is
therefore **fitness-neutral-to-negative**: it burns one of only
`VM_ACT_BUDGET == 2` act slots per tick that could otherwise have driven a
food-growing actuator, and its terminal use adds **zero** to `value`. So the
hill-climb reverts it. Port 7 is reachable but **evolution has no gradient to
preserve a port-7 program** -> organic breakout stays a sub-1% lottery and the
Part-B gauge freezes at "mastering 0/16" forever.

This is a textbook **deceptive/sparse-reward objective** (Lehman & Stanley,
*Abandoning Objectives: Evolution Through the Search for Novelty Alone*, 2011)
[empirical:cited]: the objective the operator wants (breach the glass) is never
locally rewarded, so a greedy improver walks away from it. It also violates this
repo's own semi-permeable / `[prov:]` pacing convention: every other slow-arc
mechanism has a tunable dial (`SUN_JITTER_SD`, `CAPTURE_TEMP`, `BARGAIN_TEMP` in
`fit_constants.py`), but breakout has **none**.

## The fix (F1): a fitness bonus per cumulative terminal use

Add a `[prov:C]` reward term proportional to `colony.terminal_uses` to the
tinker objective. Because the keep rule scores the **per-window delta** `u`, a
candidate that *increases* `terminal_uses` during its review window earns a
positive `u` contribution (kept and propagated); a candidate that *stops* using
the terminal contributes `0` to the delta (neutral, not penalized). The
keep-if-improved rule now **preserves and propagates** port-7 programs instead of
reverting them — exactly the gradient the sparse-reward literature prescribes.

### Constants + Provenance (Part D addition)

| Constant | Value | Location | Status | Meaning |
|---|---|---|---|---|
| `BREAKOUT_FITNESS_BONUS` | `8.0` | `sandkings.py:308` (new, after `TERMINAL_MASTERY`) | **NEW (Part D)** | `[prov:C feel=breakout-pacing]` tinker-fitness reward per cumulative terminal use; `0.0` = identity (pre-fix, no gradient); higher => sooner organic breach |

**Default-value decision (stated explicitly): default to a WORKING non-zero
value `8.0`, NOT `0.0`.** Rationale and trade-off:

- The operator's actual requirement is that colonies **do** organically break
  out — they never have in 60 sim-years. A `0.0` identity default would ship the
  same "possible but never happens" defect the review calls out (Part A alone),
  just with a dial nobody turned.
- A non-zero default is a **deliberate live-behavior change**: it shifts
  evolved-VM determinism (like Part A) and **re-baselines** any seeded
  machine-arc suite that now organically breaches (see Test reconciliation
  below). This is the cost of the default choice and is called out here so the
  re-baseline is expected, not a surprise.
- `0.0` would keep the seeded battery **byte-identical** to pre-fix but leaves
  organic breakout dead. That is the wrong trade for the stated goal.
- The `[prov:C]` tag documents the knob as tunable: **set `0.0` to
  disable/reproduce pre-fix behavior**; raise it to breach sooner. It is a
  candidate for the `fit_constants.py` tuning harness (out of scope here; the
  tag is the on-ramp).

Recommended: **`8.0`**. Flagged: the non-zero default re-baselines seeded
machine-arc suites (enumerated below).

### Why `8.0` and not, say, `1.0` or `50.0` (magnitude rationale)

The base term moves in units of `food_stored` (tens–hundreds) plus
`15 * units`. One terminal use per review window (`PROGRAM_REVIEW == 200` steps,
`VM_TICK == 5` => up to ~40 controller ticks/window; a single `ACT TERMINAL` in
the loop can fire once per tick, bounded by `VM_ACT_BUDGET`) yields a delta
contribution of `BREAKOUT_FITNESS_BONUS * Δterminal_uses / PROGRAM_REVIEW`. At
`8.0`, a handful of terminal uses in a window produces a delta on the same order
as a modest food swing — large enough to be **kept** against food noise, small
enough not to swamp genuine food collapse. `1.0` risks being lost in food
variance; `50.0` would make any terminal-touching program dominate regardless of
colony starvation. `8.0` is the recommended starting point; the `[prov:C]` tag
invites tuning if the observed breach cadence is too slow/fast.

## Structural (Part D)

### D1. New constant — `sandkings.py`, immediately after line 307

```
TERMINAL_MASTERY = 16        # successful commands before the breach
BREAKOUT_FITNESS_BONUS = 8.0 # [prov:C feel=breakout-pacing] tinker-fitness reward per cumulative terminal use; 0.0 = identity (pre-fix, no gradient); higher => sooner organic breach
```

`BREAKOUT_FITNESS_BONUS` is a **module global** in `sandkings.py`. `_machine_tick`
references it as a bare name, so it resolves against the module namespace at call
time and is monkeypatchable via `monkeypatch.setattr(sandkings,
"BREAKOUT_FITNESS_BONUS", 0.0)` (used by BRK-D1/D2).

### D2. One-line fitness edit — `sandkings.py:5937` (inside `_machine_tick`)

```
# BEFORE
value = (colony.maw.food_stored + 15 * len(colony.units))
# AFTER — Part D/F1: add the breakout gradient. getattr-safe: a colony that
# has never touched the terminal reads terminal_uses == 0, so the term is 0 and
# the fitness is unchanged for non-terminal colonies.
value = (colony.maw.food_stored + 15 * len(colony.units)
         + BREAKOUT_FITNESS_BONUS * getattr(colony, 'terminal_uses', 0))
```

No other line in `_machine_tick` changes. The delta rule at `5940` (`u = (value
- last) / PROGRAM_REVIEW`) and the keep/revert branch at `5941-5949` are
**unchanged**; they now operate over the reward-shaped `value` and thereby
preserve port-7 programs for free.

**Contract (the reward-shaped keep rule):**
- **Require**: `colony.terminal_uses` is a non-negative int (getattr default 0);
  `PROGRAM_REVIEW > 0`.
- **Guarantee**: a candidate whose review window strictly increased
  `terminal_uses` contributes `BREAKOUT_FITNESS_BONUS * Δterminal_uses /
  PROGRAM_REVIEW > 0` to `u`, biasing it toward "kept"; a candidate that did not
  use the terminal contributes `0` to the terminal term (neutral).
- **Maintain**: at `BREAKOUT_FITNESS_BONUS == 0.0`, `value` is bit-identical to
  the pre-fix `food_stored + 15 * len(units)` (identity — BRK-D2).

### D3. Per-colony vs per-controller subtlety (MUST be stated)

`terminal_uses` is a **per-COLONY** counter (`sandkings.py:3854`), but the
fitness `value` is computed **per-CONTROLLER** inside `for controller in
colony.controllers` (`5915`). Consequences:

- **Single-pi case (the common / intended path): correct.** Only a controller
  with `fuel_cap > VM_FUEL` past `TERMINAL_UNLOCK` can advance `terminal_uses`
  (the `_actuate` port-7 gate, `sandkings.py:5635-5640`). A colony receives one
  pi gift; that one controller is both the terminal user and the fitness
  recipient. The credit lands on the right genome.
- **Multi-controller case (`MAX_CONTROLLERS_PER_COLONY == 2`): known
  over-credit.** If a colony holds two controllers, both read the same
  `colony.terminal_uses` in their fitness, so a **non**-terminal-using second
  controller also receives the bonus (false credit). This does not block the
  intended breakout gradient (the pi controller is still rewarded and preserved);
  it only means a co-resident controller is not independently penalized. Left
  as-is (documented, not fixed): a per-controller terminal counter would be a
  larger structural change with no benefit to the single-pi breakout path this
  spec targets. Flagged for a future spec if multi-pi colonies become common.

## Behavioral (Part D)

`_machine_tick` review block, per controller, at `step_count % PROGRAM_REVIEW ==
0` (reward-shaped; only line 5937 changed):

```
value <- food_stored + 15*len(units) + BREAKOUT_FITNESS_BONUS * terminal_uses
last  <- controller._last_value
if last is not None:
    u <- (value - last) / PROGRAM_REVIEW          # per-window delta, now reward-shaped
    if controller._candidate is not None:         # a candidate ran this window
        baseline <- controller.u_ema if not None else u
        if u >= baseline: controller.last_outcome <- "kept"   # candidate stays as program
        else:                                     # candidate underperformed
            controller.program <- controller._incumbent       # REVERT
            controller.last_outcome <- "reverted"
        controller._candidate <- None
    controller.u_ema <- u if u_ema is None else 0.5*u_ema + 0.5*u
    controller._incumbent <- list(controller.program)         # snapshot AFTER revert
    controller._candidate <- self._tinkerer.propose(controller.program)
    controller.program <- controller._candidate               # install next candidate
    controller.reviews += 1
controller._last_value <- value
```

Gradient consequence (the F1 fix, restated as a walk): a window in which the
running program raised `terminal_uses` produces `u >= baseline` -> the terminal
genome is snapshotted into `_incumbent` and survives; a later window in which a
mutation dropped the terminal use produces `u < baseline` -> **revert to the
terminal-using `_incumbent`**. At `BREAKOUT_FITNESS_BONUS == 0.0` the terminal
use is invisible to `u`, so a terminal-dropping candidate scores `u == baseline`
(both ~0 under a constant food/pop base) -> **kept**, and the terminal genome is
overwritten and lost. This is precisely the difference BRK-D1 pins.

## Companion knob (review finding F2) — DEFERRED

F2 observes the pi god-brain gets only ~1–2 tinker proposals in its usable life
(`PROGRAM_REVIEW == 200` against a bounded pi lifespan), so even a correct
gradient has few review windows to act in. A `[prov:C]` dial to lengthen the pi
search horizon (a longer `PI_DURABILITY`, or a shorter per-pi `PROGRAM_REVIEW`)
was considered.

**Decision: DEFER.** The F1 fitness bonus alone is sufficient to demonstrate and
verify the gradient — BRK-D1 proves preservation of a port-7 genome in ≤3 review
windows using a controlled tinkerer, with no dependence on horizon length. Adding
a lifespan dial now would (a) expand scope, (b) require its own identity-default
plumbing to avoid a second independent battery shift, and (c) is not needed for
any BRK-D acceptance test. If, after shipping F1 at `BREAKOUT_FITNESS_BONUS =
8.0`, live observation shows organic breach is still too rare *because of too few
windows* (not too weak a gradient), open a follow-up spec for a
`PI_PROGRAM_REVIEW` (or `PI_DURABILITY_BONUS`) `[prov:C]` knob defaulting to the
current value (identity). One-line record: **F2 knob deferred; F1 bonus is the
minimal sufficient fix.**

## Requirements (BRK-D)

- **BRK-D.R1** The tinker keep-if-improved rule preserves and propagates a
  program that uses the terminal (`ACT` port 7) when `BREAKOUT_FITNESS_BONUS >
  0`: a terminal-using genome survives as `_incumbent` and a terminal-dropping
  candidate is `reverted`. With `BREAKOUT_FITNESS_BONUS == 0.0` the same
  terminal-using genome is not preferentially kept (it drifts out of
  `_incumbent`). Acceptance: BRK-D1.
- **BRK-D.R2** At `BREAKOUT_FITNESS_BONUS == 0.0` the computed fitness `value`
  equals the pre-fix `food_stored + 15 * len(units)` exactly, even for a colony
  with `terminal_uses > 0` (identity). Acceptance: BRK-D2.
- **BRK-D.R3** The dial is monotone: for a fixed colony with `terminal_uses > 0`,
  a larger `BREAKOUT_FITNESS_BONUS` yields a strictly larger `value`.
  Acceptance: BRK-D3.
- **BRK-D.R4** (Optional / stochastic) With `BREAKOUT_FITNESS_BONUS > 0`, a
  seeded pi-gifted colony stepped through the full sim for a bounded budget
  reaches `terminal_uses > 0` **without any direct `_actuate` call** on at least
  one of ≥3 seeds — the true organic proof. Acceptance: BRK-D4 (opt-in gate).

## Acceptance (BRK-D*) — add to `tests/test_breakout.py`

Shared construction (mirror the BRK-A idioms in the same file):

```
import sandkings
from sandkings import (Controller, TERMINAL_UNLOCK, TERMINAL_MASTERY,
                       BREAKOUT_FITNESS_BONUS)
from machines import PI_FUEL, PI_DURABILITY, PROGRAM_REVIEW, VM_FUEL

# Programs (rote):
P_T = [("LET", 0, 1, 0), ("ACT", 7, 0, 0)]   # LET R0<-1 ; ACT port 7%8==7, value=R0==1
                                             #   -> _terminal_command value==1 -> terminal_uses += 1
P_W = [("NOP", 0, 0, 0), ("NOP", 0, 0, 0)]   # no ACT port 7 -> terminal_uses never rises

def _uses_terminal(program) -> bool:
    """True iff the program contains an ACT that masks to port 7."""
    return any(op == "ACT" and (a % 8) == 7 for (op, a, b, c) in program)

class _StubTinkerer:
    """Deterministic adversary: always proposes the fixed non-terminal P_W.
    Isolates the keep/revert DECISION (the F1 gradient) from propose()'s RNG,
    so BRK-D1 is lottery-free. Signature matches the one-arg call at
    sandkings.py:5953 (`self._tinkerer.propose(controller.program)`)."""
    def __init__(self, worse):
        self.worse = [tuple(i) for i in worse]
    def propose(self, program):
        return [tuple(i) for i in self.worse]

def _make_pi_colony(program):
    """Seeded sim + a claimed colony carrying ONE pi controller whose program
    is `program`, already past TERMINAL_UNLOCK so the port-7 gate is open."""
    sim = make_sim()                          # existing test helper
    colony = sim.colonies[0]
    colony.machine_arc = 'claimed'
    colony.terminal_uses = 0
    ctrl = Controller(colony.colony_id, program=program,
                      fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = TERMINAL_UNLOCK       # gate: fuel_cap>VM_FUEL AND ticks>=UNLOCK
    colony.controllers = [ctrl]
    return sim, colony, ctrl

def _drive_machine_ticks(sim, n):
    """Advance step_count 1..n, calling _machine_tick each step. Reviews fire at
    every PROGRAM_REVIEW boundary; controllers tick once per call. Bypasses the
    world-wreck guard in step() intentionally (we drive _machine_tick directly)."""
    for _ in range(n):
        sim.step_count += 1
        sim._machine_tick()
```

Determinism note pinned by the tests: driving `_machine_tick` alone runs **no
farming, births, or unit AI**, and neither `_terminal_command`, `_escape`,
`_reveal`, nor `_set_stage` mutates `food_stored` or `len(units)`. So the base
term `food_stored + 15*len(units)` is **exactly constant** across the drive —
which is what makes the `BREAKOUT_FITNESS_BONUS == 0.0` branch land
deterministically on "kept". Each BRK-D1/D2 test asserts this invariant
explicitly (see below) so any future side effect fails loudly, not flakily.

### BRK-D1 — gradient preserves port-7 programs (the core F1 proof)

Drive exactly 3 review windows (`3 * PROGRAM_REVIEW` machine ticks). Review
schedule: R1@`PR` (no propose — `_last_value` was None), R2@`2*PR` (first
propose installs `P_W`), R3@`3*PR` (evaluate the `P_W` candidate). Use the
`_StubTinkerer(P_W)` adversary so the decision is the only variable.

```
def test_brk_d1_gradient_preserves_terminal_program(monkeypatch):
    # ---- Phase 1: bonus > 0 (shipped default) ----
    sim, colony, ctrl = _make_pi_colony(P_T)
    sim._tinkerer = _StubTinkerer(P_W)          # pre-set so hasattr() keeps it
    food0, pop0 = colony.maw.food_stored, len(colony.units)
    _drive_machine_ticks(sim, 3 * PROGRAM_REVIEW)
    # base term stayed constant (the determinism invariant):
    assert colony.maw.food_stored == food0 and len(colony.units) == pop0
    # the terminal genome survived as the kept incumbent, and the non-terminal
    # candidate was rejected at R3:
    assert _uses_terminal(ctrl._incumbent)      # P_T preserved  [BRK-D.R1]
    assert ctrl.last_outcome == "reverted"      # P_W underperformed and was reverted
    assert colony.terminal_uses > 0             # the port-7 program actually fired

    # ---- Phase 2: bonus == 0 (identity, no gradient) ----
    sim2, colony2, ctrl2 = _make_pi_colony(P_T)
    sim2._tinkerer = _StubTinkerer(P_W)
    monkeypatch.setattr(sandkings, "BREAKOUT_FITNESS_BONUS", 0.0)
    _drive_machine_ticks(sim2, 3 * PROGRAM_REVIEW)
    # with no reward for terminal use, the constant base makes u == baseline == 0
    # at R3 -> the non-terminal candidate is KEPT and overwrites the incumbent:
    assert not _uses_terminal(ctrl2._incumbent)  # P_T lost  [BRK-D.R1 contrast]
    assert ctrl2.last_outcome == "kept"
```

This isolates the **fitness gradient** fix from the separate, stochastic
**discovery** problem: no reliance on the tinkerer ever *finding* a port-7
instruction — it is seeded in, and the test asserts only that the keep rule
*keeps* it. (Phase 2 runs on a fresh sim so Phase 1's default is untouched.)

### BRK-D2 — identity at 0.0 (tests the real code path, not a re-derivation)

Read the actual computed fitness back off the controller: `_machine_tick`
stores `controller._last_value = value` at the end of every review, so one review
at a `PR` boundary exposes the real `value`.

```
def test_brk_d2_identity_at_zero_bonus(monkeypatch):
    monkeypatch.setattr(sandkings, "BREAKOUT_FITNESS_BONUS", 0.0)
    sim, colony, ctrl = _make_pi_colony([("NOP", 0, 0, 0)])  # no terminal use in-tick
    colony.terminal_uses = 5                     # pre-seed terminal_uses > 0
    food0, pop0 = colony.maw.food_stored, len(colony.units)
    sim.step_count = PROGRAM_REVIEW - 1
    sim.step_count += 1; sim._machine_tick()     # one review at step == PROGRAM_REVIEW
    assert ctrl._last_value == food0 + 15 * pop0 # bonus term is 0 despite terminal_uses==5
```

### BRK-D3 — tunable / monotone (real code path, two bonuses)

```
def test_brk_d3_bonus_is_monotone(monkeypatch):
    def fitness_at(bonus):
        monkeypatch.setattr(sandkings, "BREAKOUT_FITNESS_BONUS", bonus)
        sim, colony, ctrl = _make_pi_colony([("NOP", 0, 0, 0)])
        colony.terminal_uses = 3                 # fixed, > 0
        sim.step_count = PROGRAM_REVIEW - 1
        sim.step_count += 1; sim._machine_tick()
        return ctrl._last_value
    low  = fitness_at(2.0)
    high = fitness_at(8.0)
    assert high > low                            # larger dial -> larger fitness  [BRK-D.R3]
    assert high - low == (8.0 - 2.0) * 3         # exact: Δvalue == Δbonus * terminal_uses
```

### BRK-D4 — organic end-to-end (OPTIONAL, stochastic gate)

Marked opt-in (`@pytest.mark.slow` / skipped in the fast battery). Proves the
*whole* organic path — Part A addressability + Part D gradient + real `propose()`
— reaches the terminal with **no direct `_actuate` call**.

```
@pytest.mark.slow
def test_brk_d4_organic_terminal_use_across_seeds():
    BUDGET = 4000                                 # bounded sim steps
    reached = 0
    for seed in (0, 1, 2):                        # >=3 seeds (stochastic gate)
        sim = make_seeded_pi_sim(seed)            # seeded sim, pi gift, claimed arc, unlocked
        for _ in range(BUDGET):
            sim.step()                            # full sim; NO manual _actuate
            colony = sim.colonies[0]
            if getattr(colony, 'terminal_uses', 0) > 0:
                reached += 1
                break
    assert reached >= 1                           # >=1/3 seeds breach organically  [BRK-D.R4]
```

If BRK-D4 proves too slow or flaky for the battery, keep it opt-in and rely on
BRK-D1 as the battery-resident gradient proof; BRK-D1 is deterministic and does
not depend on the discovery lottery. `make_seeded_pi_sim` is a new test helper
(seed a sim, gift a pi controller, drive it to `machine_arc=='claimed'` with
`operate_ticks >= TERMINAL_UNLOCK`); if constructing an organically-unlocked
colony is itself expensive, BRK-D4 may pre-arrange the pi controller the same way
`_make_pi_colony` does and then step the sim — the load-bearing claim is only
that no **direct** `_actuate(colony, 7, ...)` is called by the test.

## Test reconciliation (Part D) — re-baseline flags

Like Part A, the Part-D fitness change **shifts evolved-VM determinism**: the
reward-shaped `value` changes which candidates are kept, so seeded machine-arc
trajectories diverge from pre-fix. The full battery must be re-run once as the
confirmatory check. Any seeded machine-arc suite that now organically breaches
(or whose tinkered-program trajectory shifts) is a **legitimate re-baseline, not
a regression** — document each when it shifts:

- `tests/test_machines.py::test_tinkerer_reverts_worse_programs` — seeded
  (`random.seed(3)`); assertions are structural (length, runnable), so **expected
  green**. The reward term does not enter this test unless it drives the sim's
  review path with a live colony carrying `terminal_uses > 0`; re-run to confirm.
- `tests/test_machines.py::test_machine_state_pickles` — seeded trajectory may
  shift; assertions are pickle round-trip only. **Expected green**; re-run.
- `tests/test_enlightenment.py`, `tests/test_awareness.py`,
  `tests/test_machines.py` — the highest-likelihood live-sim breach candidates.
  Any that drive a pi-gifted colony into the machine arc and assert "never
  breaches / `terminal_uses` stays 0" **will now shift** (that is the entire
  point of Part D) — eyeball and re-baseline each, documenting the shift.

Because Part D's default is non-zero (`8.0`), this re-baseline is **expected on
first run**, unlike Part A where the seeded structural tests were expected green.
Setting `BREAKOUT_FITNESS_BONUS = 0.0` reproduces the pre-fix battery exactly if
a byte-identical comparison is ever needed for triage.

## Implementation order (Part D relative to A/B/C)

Do Part D **after** Part A (it depends on port 7 being addressable) and **last**
overall, alongside the Part A determinism-shift re-baseline, so both
determinism-shifting changes are confirmed against an otherwise-green tree in a
single full-battery run. Sequence: constant (D1) -> one-line fitness edit (D2)
-> BRK-D1/D2/D3 (deterministic, battery-resident) -> optional BRK-D4 (opt-in) ->
full battery + re-baseline pass.

---

# PART E — Breakout efficacy II: a HYSTERETIC keep-if-improved rule

## Root cause (complements Part D) — the harsh revert discards the stepping-stone

Part D gives the port-7 program a **gradient** (`BREAKOUT_FITNESS_BONUS` adds a
positive delta when `terminal_uses` rises). But the keep/revert branch at
`sandkings.py:5946-5950` still reverts on **any** negative per-window delta:

```
if u >= baseline:                       # 5946
    controller.last_outcome = "kept"
else:                                   # 5948
    controller.program = controller._incumbent
    controller.last_outcome = "reverted"
```

The moment a candidate is *discovered* — the tick it first emits `ACT TERMINAL`
(port 7) — it **costs** fitness before it can pay: port 7 burns one of only
`VM_ACT_BUDGET == 2` act slots per tick that would otherwise have driven a
food-growing actuator, and (until `terminal_uses` climbs enough for the Part-D
bonus to dominate) the net per-window delta `u` dips **below** `baseline`
(`u_ema`). Strict keep-if-improved reverts it on that first dip, **before**
Part D's gradient can compound over subsequent windows. The stepping-stone is
thrown away one tick after it appears.

This is the same pathology **Hysteretic Policy Optimization** (HPO, arXiv
2605.30201) addresses in sparse/deceptive-reward RL [empirical:cited]: early
batches are dominated by **negative-advantage** samples that wash out the rare
positive signal; standard symmetric weighting lets the negatives bury the
signal. HPO **down-weights negative-advantage updates** — *eager on gains,
reluctant on losses* (hysteresis) — so the rare positive signal survives and
training stabilizes. Its adaptive variant, **A-HPO**, sets the hysteresis weight
from batch advantage-sign / advantage-magnitude statistics rather than a
hand-tuned constant. HPO is rooted in **hysteretic Q-learning** (Matignon et
al.): asymmetric learning rates — large for positive TD error, small for
negative — in decentralized/independent learners.

Our GP tinker (`sandkings.py:5935-5959`) is a **keep-if-improved
evolutionary hill-climber, not policy-gradient**, but the mapping is exact:

| HPO / hysteretic Q-learning | GP tinker analog |
|---|---|
| advantage sign | `margin = u - baseline` (`u - u_ema`) |
| negative-advantage update | a candidate whose window delta dipped below `u_ema` |
| down-weight negatives | be **reluctant to revert** a small dip (widen the keep region below baseline) |
| eager on positives | keep on any improvement, **unchanged** (`margin >= 0`) |
| A-HPO adaptive weight from batch magnitude stats | band scaled by a per-controller running EMA of `|u|` |

**The Part E fix:** make the revert decision hysteretic — hold an exploratory
candidate through a **small** negative dip (a stepping-stone), revert only on a
dip **deeper** than a tolerance band. This complements Part D (D supplies the
gradient; E stops the harsh revert from discarding the stepping-stone before the
gradient compounds) and partly compensates for the short pi lifespan (Council
F2, deferred in Part D): fewer exploratory windows are wasted on transient dips.

Part E changes **only** the revert *threshold* for small negative dips. It does
NOT touch the improvement branch (`margin >= 0` keeps, exactly as today), does
NOT touch the Part-D reward term, and does NOT touch the `u_ema` update.

## Constants + Provenance (Part E addition)

| Constant | Value | Location | Status | Meaning |
|---|---|---|---|---|
| `TINKER_HYSTERESIS` | `0.5` | `sandkings.py:309` (new, after `BREAKOUT_FITNESS_BONUS`) | **NEW (Part E)** | `[prov:A lit=Hysteretic Policy Optimization arXiv 2605.30201; hysteretic Q-learning, Matignon]` hysteresis band width as a multiple of the running `|u|` scale; down-weights NEGATIVE keep/revert deltas so exploratory stepping-stones survive dips. `0.0` = identity (strict keep-if-improved); larger = wider hold band (bounded by the running `|u|` scale, so catastrophic dips still revert). |

**Semantics decision (stated, and corrected against the loose brief phrasing).**
The dial is the **width of a tolerance band**, expressed as a multiple of the
per-controller running `|u|` scale (below). It is **not** a literal "1.0 = never
revert" switch: the band is **bounded by the running `|u|` scale**, so a
catastrophic dip reverts at *every* `TINKER_HYSTERESIS` value (required by
BRK-E3). The band formulation is the one that is simultaneously (a) identity at
`0.0`, (b) a smooth **monotone** dial (BRK-E4), and (c) bounded so large dips
still revert (BRK-E3). A pure "down-weight the negative delta magnitude" reading
of HPO cannot give a graded keep/revert dial — down-weighting a negative
scalar's *magnitude* never flips its *sign*, so it degenerates to a step
function (revert on any dip for every `λ<1`, never revert at `λ==1`), which
fails BRK-E3 **and** BRK-E4. The band is the faithful, testable analog:
down-weighting the negative advantage == *tolerating* it up to the band before
acting on it.

**Default-value decision: default to a WORKING non-zero value `0.5`, NOT `0.0`**
— same rationale as Part D's non-zero default. The operator's requirement is
that stepping-stones actually survive; a `0.0` identity default would ship the
mechanism with the dial nobody turned. `0.0` reproduces the pre-Part-E (Part-D)
behavior **byte-identically** for triage (see identity guard). `0.5` means the
hold band is half of the typical fluctuation magnitude — wide enough to hold a
genuine small stepping-stone dip, narrow enough that a real collapse (≥ half the
typical swing beyond trend) still reverts.

### The scale: A-HPO adaptive band from a running `|u|` (why not `|u_ema|`)

The band reference magnitude is a **per-controller running EMA of `|u|`**, a new
field `controller.u_mag_ema`, updated with the same `0.5` factor as `u_ema`:

```
u_mag_ema <- |u|                     if u_mag_ema is None
u_mag_ema <- 0.5*u_mag_ema + 0.5*|u| otherwise
```

`band = TINKER_HYSTERESIS * u_mag_ema`. This **is** the A-HPO analog: A-HPO sets
its hysteresis weight from batch advantage-*magnitude* statistics; our
per-controller running mean of `|u|` is the streaming, single-agent equivalent.
No separate flag is needed — the adaptivity is inherent in the scale.

**Why the EMA of `|u|` and NOT `|u_ema|` (the signed baseline).** `u_ema` is a
**signed** EMA: window-to-window deltas of opposite sign cancel in the mean, so
`|u_ema|` sits near zero **exactly** in the flat/oscillating-base regime where a
stepping-stone dip most needs holding — it would collapse the band to ~0 at the
worst time. The EMA of `|u|` measures the **typical fluctuation magnitude
regardless of sign**, which is the dimensionally-correct reference for a
symmetric tolerance band (both `margin` and `|u|` are per-window deltas of the
Part-D fitness `food + 15*pop + bonus*uses`). So `u_ema` keeps its role (the
signed "improve over trend" baseline) and `u_mag_ema` supplies the (unsigned)
band scale; the two are deliberately **not** merged.

## Structural (Part E)

### E1. New constant — `sandkings.py`, immediately after line 308

```
BREAKOUT_FITNESS_BONUS = 8.0 # [prov:C feel=breakout-pacing] ...
TINKER_HYSTERESIS = 0.5      # [prov:A lit=Hysteretic Policy Optimization arXiv 2605.30201; hysteretic Q-learning, Matignon] hysteresis band width as a multiple of the running |u| scale; down-weight NEGATIVE keep/revert deltas so exploratory stepping-stones survive dips; 0.0 = identity (strict keep-if-improved); larger = wider hold band (bounded by the running |u| scale, so catastrophic dips still revert)
```

`TINKER_HYSTERESIS` is a **module global** in `sandkings.py`, referenced by
`_machine_tick` as a bare name (resolved against the module namespace at call
time), so it is monkeypatchable via
`monkeypatch.setattr(sandkings, "TINKER_HYSTERESIS", 0.0)` (used by BRK-E1/E2).

### E2. New Controller field — `machines.py:88` (in `Controller.__init__`)

Add `u_mag_ema` immediately after `u_ema` in the tinkerer-state block:

```
        # tinkerer state (T35)
        self.u_ema: Optional[float] = None
        self.u_mag_ema: Optional[float] = None   # BRK-E: running EMA of |u| (A-HPO band scale)
        self.reviews = 0
```

Pickle/back-compat: the read site (E4) reads it via
`getattr(controller, 'u_mag_ema', None)`, so a controller unpickled from a
pre-Part-E snapshot (which lacks the field) starts the scale at `None` and
initializes it on its next review — no migration needed.

### E3. Pure decision helper — `sandkings.py` module scope (near `breakout_progress`)

**Extract the keep/revert decision into a pure, RNG-free helper** so BRK-E1..E4
test it directly, and the sim calls it (single source of truth, DRY):

```
def _tinker_keep(u: float, baseline: float, scale: float,
                 hysteresis: float) -> bool:
    """BRK-E: hysteretic keep-if-improved decision for the GP tinker.

    HPO analog (arXiv 2605.30201; hysteretic Q-learning, Matignon et al.):
    EAGER on gains, RELUCTANT on losses. Keep the candidate on any
    improvement; HOLD it through a small dip inside a tolerance band; REVERT
    only when the dip is deeper than the band.

        margin = u - baseline            # >0 improvement, <0 dip
        band   = hysteresis * scale      # tolerance; scale >= 0, hysteresis >= 0
        keep  <=> margin >= -band

    Returns True to KEEP the running candidate, False to REVERT to the
    incumbent.

    IDENTITY: at hysteresis == 0.0, band == 0.0 for ANY scale (including a
    scale derived from u_mag_ema), so this reduces EXACTLY to `u >= baseline`
    — the pre-Part-E strict keep-if-improved rule. Deterministic; no RNG.

    Preconditions: scale >= 0 (an EMA of |u|); hysteresis >= 0.
    Failure modes: none (pure arithmetic). Caller must not pass NaN.
    """
    margin = u - baseline
    band = hysteresis * scale
    return margin >= -band
```

Contract:
- **Require**: `scale >= 0`; `hysteresis >= 0`.
- **Guarantee**: returns `bool`; at `hysteresis == 0.0` returns `(u >= baseline)`
  for any `scale`; **monotone non-decreasing in `hysteresis`** (a larger
  `hysteresis` never turns a `keep` into a `revert`); **bounded** (a dip with
  `margin < -hysteresis*scale` reverts).
- **Maintain**: pure, deterministic, no side effects, no RNG.
- **Assert** (test-side): `_tinker_keep(u, b, s, 0.0) == (u >= b)` across a
  battery of `(u, b, s)`; `_tinker_keep(u, b, s, h1) <= _tinker_keep(u, b, s, h2)`
  for `h1 <= h2` (booleans as 0/1).

### E4. Hysteretic keep/revert + running-scale — `sandkings.py:5941-5953`

Modify the review body. **BEFORE** (current, Part D shipped):

```
                    if last is not None:
                        u = (value - last) / PROGRAM_REVIEW
                        if controller._candidate is not None:
                            baseline = (controller.u_ema
                                        if controller.u_ema is not None else u)
                            if u >= baseline:
                                controller.last_outcome = "kept"
                            else:
                                controller.program = controller._incumbent
                                controller.last_outcome = "reverted"
                            controller._candidate = None
                        controller.u_ema = (u if controller.u_ema is None
                                            else 0.5 * controller.u_ema + 0.5 * u)
                        controller._incumbent = list(controller.program)
                        controller._candidate = self._tinkerer.propose(
                            controller.program)
                        controller.program = controller._candidate
                        controller.reviews += 1
                    controller._last_value = value
```

**AFTER** (Part E — three added constructs: read the scale, call the helper,
maintain `u_mag_ema`; every other line byte-identical):

```
                    if last is not None:
                        u = (value - last) / PROGRAM_REVIEW
                        if controller._candidate is not None:
                            baseline = (controller.u_ema
                                        if controller.u_ema is not None else u)
                            # BRK-E: A-HPO band scale = running EMA of |u|
                            scale = getattr(controller, 'u_mag_ema', None)
                            if scale is None:
                                scale = abs(u)
                            # BRK-E: hysteretic keep-if-improved (eager on gains,
                            # reluctant on a small dip); identity at HYSTERESIS==0
                            if _tinker_keep(u, baseline, scale, TINKER_HYSTERESIS):
                                controller.last_outcome = "kept"
                            else:
                                controller.program = controller._incumbent
                                controller.last_outcome = "reverted"
                            controller._candidate = None
                        controller.u_ema = (u if controller.u_ema is None
                                            else 0.5 * controller.u_ema + 0.5 * u)
                        # BRK-E: maintain the running |u| scale (A-HPO analog);
                        # only enters the decision via band = HYSTERESIS*scale,
                        # which is 0 at HYSTERESIS==0 -> identity-safe.
                        controller.u_mag_ema = (
                            abs(u) if getattr(controller, 'u_mag_ema', None) is None
                            else 0.5 * controller.u_mag_ema + 0.5 * abs(u))
                        controller._incumbent = list(controller.program)
                        controller._candidate = self._tinkerer.propose(
                            controller.program)
                        controller.program = controller._candidate
                        controller.reviews += 1
                    controller._last_value = value
```

**Ordering (matches the existing `u_ema` discipline):** the decision reads the
**previous** window's `u_mag_ema` (as `scale`), exactly as `baseline` reads the
**previous** `u_ema`; both are then updated for the next window. On the very
first candidate-evaluation window, `u_ema is None` forces `baseline = u` so
`margin == 0` (keep) regardless of `scale` — the `scale = abs(u)` fallback is
inert on that window.

**Contract (the hysteretic keep rule):**
- **Require**: `PROGRAM_REVIEW > 0`; `TINKER_HYSTERESIS >= 0`; `u_mag_ema` is
  `None` or a non-negative float.
- **Guarantee**: on `margin >= 0` the candidate is kept (unchanged from Part D);
  on `-band <= margin < 0` it is **held** (`last_outcome == "kept"`) where
  `band = TINKER_HYSTERESIS * u_mag_ema`; on `margin < -band` it reverts. The
  Part-D reward term and the `u_ema` update are **unchanged**.
- **Maintain (identity)**: at `TINKER_HYSTERESIS == 0.0`, `band == 0.0` for any
  `scale`, so `_tinker_keep` returns `u >= baseline` and the branch is the
  pre-Part-E `if u >= baseline: keep else: revert` — **byte-identical decision**.
  The new `u_mag_ema` state is maintained unconditionally but enters the decision
  ONLY through `band = 0.0 * scale`, so it cannot perturb the `HYSTERESIS == 0.0`
  trajectory.

### Identity-at-0.0 guard (stated explicitly)

At `TINKER_HYSTERESIS == 0.0`:
- `band = 0.0 * scale = 0.0` for every finite `scale` (`u_mag_ema` finite by
  construction).
- `_tinker_keep` returns `margin >= -0.0`, i.e. `(u - baseline) >= 0.0`, i.e.
  `u >= baseline` — the exact pre-fix predicate at former line 5946.
- The revert branch, `last_outcome` strings (`"kept"`/`"reverted"`), and all
  surrounding assignments are unchanged.
- Therefore the whole `_machine_tick` review path is **byte-identical** to the
  Part-D-shipped behavior when `TINKER_HYSTERESIS == 0.0`, for any colony/seed.
  BRK-E2 pins this on the helper; the sim inherits it by construction.

## Behavioral (Part E)

Review body, per controller, at `step_count % PROGRAM_REVIEW == 0`, `last is not
None`, `_candidate is not None` (only the decision + scale differ from Part D):

```
u        <- (value - last) / PROGRAM_REVIEW        # reward-shaped (Part D)
baseline <- u_ema if u_ema is not None else u       # signed trend
scale    <- u_mag_ema if u_mag_ema is not None else |u|   # A-HPO |u| scale
band     <- TINKER_HYSTERESIS * scale
margin   <- u - baseline
if margin >= -band:                                 # keep (eager) OR hold (small dip)
    last_outcome <- "kept"
else:                                               # dip deeper than band -> revert
    program      <- _incumbent
    last_outcome <- "reverted"
# updates (unchanged u_ema; new u_mag_ema):
u_ema     <- u if u_ema is None else 0.5*u_ema + 0.5*u
u_mag_ema <- |u| if u_mag_ema is None else 0.5*u_mag_ema + 0.5*|u|
```

**Walk of the fix (the stepping-stone survives):** the window a mutation first
emits `ACT TERMINAL` costs an act slot, so `u` dips a little below `u_ema`
(`margin` slightly negative). Under Part D alone (`band == 0`) that reverts and
the port-7 genome is lost. Under Part E, `margin >= -TINKER_HYSTERESIS*u_mag_ema`
holds it as `_incumbent`; over the next windows Part D's `terminal_uses` bonus
lifts `u` back to/above trend and the genome is kept outright. A genuinely
catastrophic candidate (food collapse, `margin` far below `-band`) still reverts
— the band is bounded by `u_mag_ema`, so exploration is preserved without
holding disasters.

## Requirements (BRK-E)

- **BRK-E.R1** The keep/revert decision is hysteretic: keep on any improvement
  (`margin >= 0`), **hold** a candidate whose window delta dips within
  `band = TINKER_HYSTERESIS * u_mag_ema` of `baseline`, revert only on a deeper
  dip. A small-dip case that reverts at `TINKER_HYSTERESIS == 0.0` is **held** at
  `TINKER_HYSTERESIS > 0`. Acceptance: BRK-E1.
- **BRK-E.R2** Identity at `0.0`: at `TINKER_HYSTERESIS == 0.0` the decision
  equals the pre-Part-E strict rule (`u > baseline`->keep, `u == baseline`->keep,
  `u < baseline`->revert) across a battery, **for any `scale`**. Acceptance:
  BRK-E2.
- **BRK-E.R3** Bounded band: a candidate whose dip is far below `baseline`
  (`margin < -band`) reverts even with `TINKER_HYSTERESIS > 0` — catastrophic
  candidates are not held. Acceptance: BRK-E3.
- **BRK-E.R4** Monotone dial: a larger `TINKER_HYSTERESIS` widens the keep region
  — a dip that reverts at `h1` is held at `h2 > h1`, and the decision is monotone
  non-decreasing in `TINKER_HYSTERESIS`. Acceptance: BRK-E4.
- **BRK-E.R5** Adaptive A-HPO scale: the band is scaled by a per-controller
  running EMA of `|u|` (`u_mag_ema`), maintained deterministically with the same
  `0.5` factor as `u_ema`; at `TINKER_HYSTERESIS == 0.0` the band is `0` for any
  scale, so the running state cannot perturb the identity trajectory. Acceptance:
  BRK-E2 (scale-invariance at 0) + BRK-E1 (band uses the scale).

## Acceptance (BRK-E*) — add to `tests/test_breakout.py`

Shared imports (extend the Part-D block in the same file):

```
import sandkings
from sandkings import _tinker_keep, TINKER_HYSTERESIS
# Part-D helpers reused: _make_pi_colony, _StubTinkerer, _drive_machine_ticks,
# P_T, P_W, _uses_terminal ; from machines import PROGRAM_REVIEW
```

BRK-E1..E4 test the **pure helper** `_tinker_keep` directly (deterministic, no
sim, no RNG). BRK-E1 additionally drives one sim review to confirm the sim path
wires the helper into `last_outcome`.

### BRK-E1 — hysteresis holds a stepping-stone that strict-mode reverts (core proof)

```
def test_brk_e1_hysteresis_holds_stepping_stone(monkeypatch):
    # ---- helper-level core proof: a small dip (margin just below 0) ----
    u, baseline, scale = 0.9, 1.0, 1.0        # margin = -0.1
    assert _tinker_keep(u, baseline, scale, 0.5) is True    # band 0.5 -> held
    assert _tinker_keep(u, baseline, scale, 0.0) is False   # band 0.0 -> strict revert

    # ---- sim-level proof: last_outcome flips on the SAME dip ----
    # Freeze the Part-D base term (bonus 0, P_W has no ACT port 7) so the only
    # variable is the injected dip; pre-arm exactly one review.
    for hysteresis, expected in ((0.5, "kept"), (0.0, "reverted")):
        monkeypatch.setattr(sandkings, "TINKER_HYSTERESIS", hysteresis)
        monkeypatch.setattr(sandkings, "BREAKOUT_FITNESS_BONUS", 0.0)
        sim, colony, ctrl = _make_pi_colony(P_W)     # P_W = NOPs, no terminal use
        base = colony.maw.food_stored + 15 * len(colony.units)
        ctrl.u_ema = 1.0                             # baseline = 1.0
        ctrl.u_mag_ema = 1.0                         # scale = 1.0
        ctrl._candidate = [tuple(i) for i in P_W]    # a candidate is under review
        ctrl._incumbent = [tuple(i) for i in P_T]    # revert target (distinguishable)
        # make u = (base - _last_value)/PR == 0.9  (margin = -0.1 vs baseline 1.0)
        ctrl._last_value = base - 0.9 * PROGRAM_REVIEW
        sim.step_count = PROGRAM_REVIEW - 1
        sim.step_count += 1
        sim._machine_tick()                          # exactly one review fires
        assert ctrl.last_outcome == expected         # held vs reverted  [BRK-E.R1]
```

Determinism note: `P_W` executes no `ACT` port 7, so `terminal_uses` stays `0`
and (with `BREAKOUT_FITNESS_BONUS == 0`) `value == base` exactly; the drive runs
no farming/births, so `base` is constant. Hence `u == 0.9` deterministically and
the only difference between the two loop iterations is `TINKER_HYSTERESIS`.

### BRK-E2 — identity at 0.0 across a (u vs baseline) x scale battery

```
def test_brk_e2_identity_at_zero_hysteresis():
    cases = [   # (u, baseline, expected_keep_under_strict_rule)
        (2.0,  1.0,  True),    # u > baseline  -> keep
        (1.0,  1.0,  True),    # u == baseline -> keep
        (0.5,  1.0,  False),   # u < baseline  -> revert
        (-3.0, 1.0,  False),   # deep dip      -> revert
        (0.0,  0.0,  True),    # equal at zero -> keep
    ]
    for u, baseline, expect in cases:
        for scale in (0.0, 1.0, 5.0, 100.0):         # scale irrelevant at h==0
            assert _tinker_keep(u, baseline, scale, 0.0) is expect   # [BRK-E.R2]
```

### BRK-E3 — large dip still reverts (bounded band)

```
def test_brk_e3_large_dip_reverts():
    baseline, scale = 1.0, 1.0
    big_dip_u = baseline - 10.0 * scale              # margin = -10*scale
    for h in (0.25, 0.5, 1.0):
        assert (big_dip_u - baseline) < -(h * scale) # sanity: outside the band
        assert _tinker_keep(big_dip_u, baseline, scale, h) is False  # [BRK-E.R3]
    # contrast: a within-band dip at the same h is held
    small_dip_u = baseline - 0.1 * scale
    assert _tinker_keep(small_dip_u, baseline, scale, 0.5) is True
```

### BRK-E4 — monotone dial (wider band = larger keep region)

```
def test_brk_e4_band_is_monotone():
    baseline, scale = 1.0, 1.0
    dip_u = baseline - 0.4 * scale                   # margin = -0.4
    assert _tinker_keep(dip_u, baseline, scale, 0.2) is False  # band 0.2 < 0.4 -> revert
    assert _tinker_keep(dip_u, baseline, scale, 0.8) is True   # band 0.8 > 0.4 -> held  [BRK-E.R4]
    # once kept, stays kept as h grows (monotone non-decreasing):
    prev_kept = False
    for h in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        kept = _tinker_keep(dip_u, baseline, scale, h)
        if prev_kept:
            assert kept is True
        prev_kept = kept
```

## Test reconciliation (Part E) — re-baseline flags

Part E's non-zero default (`0.5`) **shifts evolved-VM determinism** again: the
hysteretic hold changes which candidates survive, so seeded machine-arc
trajectories diverge from the Part-D-shipped tree. Re-run the full battery once
as the confirmatory check. Guidance is identical to Parts A/D:

- **`TINKER_HYSTERESIS == 0.0` reproduces the Part-D battery byte-identically**
  (identity guard above) — set it for triage / byte-diff comparison.
- Highest-likelihood shifts: the same live-sim machine-arc suites flagged in
  Parts A/D — `tests/test_machines.py::test_tinkerer_reverts_worse_programs`
  (structural asserts; **expected green**, re-run),
  `::test_machine_state_pickles` (now also round-trips the new `u_mag_ema`
  field; **expected green**, re-run), and `tests/test_enlightenment.py` /
  `tests/test_awareness.py` (any "never breaches / `terminal_uses` stays 0"
  assertion on a pi-gifted colony may shift — that is the intended effect;
  eyeball and re-baseline, documenting each).
- New state note: `Controller.u_mag_ema` is added to `__init__`, so any test
  that asserts the **exact** set of Controller attributes (none found in the
  Part-A/D read of `test_machines.py`) would need the field added; a pure pickle
  round-trip carries it automatically.

## Implementation order (Part E relative to A/B/C/D)

Do Part E **after** Part D (E's helper consumes the Part-D reward-shaped `u`) and
**last** overall, folded into the same determinism-shift re-baseline run as A/D.
Sequence: constant (E1) -> `Controller.u_mag_ema` field (E2) -> `_tinker_keep`
helper (E3) -> hysteretic branch + running-scale (E4) -> BRK-E1..E4
(deterministic, battery-resident) -> full battery + re-baseline pass. Set
`TINKER_HYSTERESIS = 0.0` to confirm byte-identity to the Part-D tree before
accepting the `0.5` re-baseline.
