"""Breakout tests (SPEC_BREAKOUT.md BRK-B1, BRK-C1, BRK-C2).

The keeper's open-door breach and the breakout-proximity gauge:
- BRK-B1: pure fn breakout_progress across no-pi, unlocking, mastering, breached phases
- BRK-C1: open the door breaches a colony (idempotent on state and log)
- BRK-C2: bound-god gate (hand_stayed) blocks open door without breaching
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from machines import Controller, PI_DURABILITY, PI_FUEL, VM_FUEL
from sandkings import (
    SandKingsSimulation, Colony, breakout_progress, TERMINAL_UNLOCK,
    TERMINAL_MASTERY
)


def make_sim(seed: int = 42) -> SandKingsSimulation:
    """Helper: seed both random and np.random, then create a SandKingsSimulation."""
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=48, height=36, depth=12, num_colonies=4)


# ============================================================================
# BRK-B1: breakout_progress pure fn
# ============================================================================

def test_breakout_progress_no_pi():
    """BRK-B1: colony with no pi controllers -> nopi phase (0.0, "no pi")."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    colony.controllers = []
    colony.breached = False
    phase, frac, label = breakout_progress(colony)
    assert phase == "nopi"
    assert frac == 0.0
    assert label == "no pi"
    assert 0.0 <= frac <= 1.0


def test_breakout_progress_unlocking():
    """BRK-B1: pi controller at partial operate_ticks -> unlocking phase."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    # Create a pi controller (fuel_cap > VM_FUEL)
    ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = 10  # 10/40 = 0.25
    colony.controllers = [ctrl]
    colony.breached = False
    phase, frac, label = breakout_progress(colony)
    assert phase == "unlocking"
    assert abs(frac - 0.25) < 1e-6, f"expected 0.25, got {frac}"
    assert label == "unlock"
    assert 0.0 <= frac <= 1.0


def test_breakout_progress_mastering():
    """BRK-B1: pi at TERMINAL_UNLOCK with terminal_uses -> mastering phase."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = TERMINAL_UNLOCK
    colony.controllers = [ctrl]
    colony.terminal_uses = 4  # 4/16 = 0.25
    colony.breached = False
    phase, frac, label = breakout_progress(colony)
    assert phase == "mastering"
    assert abs(frac - 0.25) < 1e-6
    assert label == f"breach 4/{TERMINAL_MASTERY}"
    assert 0.0 <= frac <= 1.0


def test_breakout_progress_breached():
    """BRK-B1: colony.breached=True -> breached phase (1.0, "BREACHED")."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    colony.controllers = [Controller(0, fuel=PI_FUEL, durability=PI_DURABILITY)]
    colony.terminal_uses = 16
    colony.breached = True
    phase, frac, label = breakout_progress(colony)
    assert phase == "breached"
    assert frac == 1.0
    assert label == "BREACHED"
    assert 0.0 <= frac <= 1.0


def test_breakout_progress_bare_colony():
    """BRK-B1: bare/revived colony (no controllers/terminal_uses attrs) is valid."""
    # Construct a minimal colony without the typical attributes
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    # Don't set controllers, breached, or terminal_uses
    phase, frac, label = breakout_progress(colony)
    # Should default to nopi (no controllers)
    assert phase == "nopi"
    assert frac == 0.0
    assert 0.0 <= frac <= 1.0


def test_breakout_progress_non_pi_controller_gated():
    """BRK-B1: non-pi controller (fuel_cap == VM_FUEL) does not advance terminal."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    # Create a NON-pi controller (default fuel_cap == VM_FUEL)
    ctrl = Controller(colony.colony_id)  # fuel_cap defaults to VM_FUEL
    ctrl.operate_ticks = TERMINAL_UNLOCK + 10
    colony.controllers = [ctrl]
    colony.breached = False
    phase, frac, label = breakout_progress(colony)
    # Should still report nopi because fuel_cap is NOT > VM_FUEL
    assert phase == "nopi"
    assert frac == 0.0


# ============================================================================
# BRK-C1: keeper_open_door breaches idempotently
# ============================================================================

def test_keeper_open_door_breaches():
    """BRK-C1: keeper_open_door breaches a colony and logs the lines."""
    sim = make_sim()
    colony = sim.colonies[0]

    # Preconditions: colony is alive and not yet breached
    assert colony.is_alive()
    assert not getattr(colony, 'breached', False)

    # Call keeper_open_door
    sim.keeper_open_door(colony)

    # Postconditions: colony is breached and enlightened
    assert getattr(colony, 'breached', False) is True
    assert getattr(colony, 'enlightened', False) is True

    # Event log contains the three expected lines
    events_text = "\n".join(m for _, m in sim.events)
    assert "opens the door" in events_text
    assert "glimpses the world" in events_text or "world beyond the glass" in events_text
    assert "ascends" in events_text


def test_keeper_open_door_idempotent():
    """BRK-C1: calling keeper_open_door twice does NOT re-emit the flavor line."""
    sim = make_sim()
    colony = sim.colonies[0]

    # First call
    sim.keeper_open_door(colony)
    count_after_first = sum(1 for _, m in sim.events if "opens the door" in m)
    assert count_after_first == 1, "first call should emit the line once"

    # Second call
    sim.keeper_open_door(colony)
    count_after_second = sum(1 for _, m in sim.events if "opens the door" in m)
    assert count_after_second == 1, "second call should NOT emit again (idempotent)"

    # Colony is still breached
    assert getattr(colony, 'breached', False) is True


def test_keeper_open_door_none_colony():
    """BRK-C1: keeper_open_door(None) is a safe no-op."""
    sim = make_sim()
    initial_count = len(sim.events)

    # Call with None
    sim.keeper_open_door(None)

    # No new events
    assert len(sim.events) == initial_count


# ============================================================================
# BRK-C2: bound-god gate
# ============================================================================

def test_keeper_open_door_bound_gate():
    """BRK-C2: keeper_bound=True -> hand_stayed() returns True -> no breach."""
    sim = make_sim()
    colony = sim.colonies[0]

    # Set the keeper_bound flag
    sim.keeper_bound = True

    # Attempt to breach
    sim.keeper_open_door(colony)

    # Colony should NOT be breached
    assert getattr(colony, 'breached', False) is False

    # Log should contain the stayed line
    events_text = "\n".join(m for _, m in sim.events)
    assert "will not move" in events_text or "stayed" in events_text


def test_keeper_open_door_unbound_breaches():
    """BRK-C2: keeper_bound=False -> hand_stayed() returns False -> breach succeeds."""
    sim = make_sim()
    colony = sim.colonies[0]

    # Ensure keeper is not bound
    sim.keeper_bound = False

    # Breach
    sim.keeper_open_door(colony)

    # Colony should be breached
    assert getattr(colony, 'breached', False) is True


def test_keeper_open_door_toggle_bound():
    """BRK-C2: toggling keeper_bound gate works correctly."""
    sim = make_sim()
    colony = sim.colonies[0]

    # First: bound (no breach)
    sim.keeper_bound = True
    sim.keeper_open_door(colony)
    assert not getattr(colony, 'breached', False)

    # Second: unbound (breach succeeds)
    sim.keeper_bound = False
    sim.keeper_open_door(colony)
    assert getattr(colony, 'breached', False) is True


# ============================================================================
# BRK-A1: address space opened (root fix) - port 7 now reachable
# ============================================================================

def test_brk_a1_actuator_names_has_terminal():
    """BRK-A1(a): ACTUATOR_NAMES now has 8 entries with TERMINAL at index 7."""
    from machines import ACTUATOR_NAMES
    assert len(ACTUATOR_NAMES) == 8, f"expected 8 actuators, got {len(ACTUATOR_NAMES)}"
    assert ACTUATOR_NAMES[7] == "TERMINAL", f"expected index 7 to be 'TERMINAL', got {ACTUATOR_NAMES[7]}"


def test_brk_a1_vm_mask_reaches_7():
    """BRK-A1(b): VM ACT opcode can emit port 7 (a % len(ACTUATOR_NAMES) == 7)."""
    from machines import ACTUATOR_NAMES
    # The modulo operation should allow 7 to remain 7
    assert 7 % len(ACTUATOR_NAMES) == 7, "7 % 8 should equal 7"

    # Verify that a Controller can emit port 7 through ACT
    prog = [("ACT", 7, 0, 0)]  # ACT with a=7
    c = Controller(0, prog)
    ports_seen = []
    c.tick(lambda p: 0, lambda p, v: ports_seen.append(p))
    assert 7 in ports_seen, "VM should emit port 7 when ACT a=7"


def test_brk_a1_tinkerer_reaches_7():
    """BRK-A1(b): GP tinkerer can generate an ACT targeting port 7."""
    from machines import GPTinkerer, ACTUATOR_NAMES
    import random

    rng = random.Random(0)
    tinkerer = GPTinkerer()
    seen_ports = set()

    # Generate 500 random instructions, collect ACT ports
    for _ in range(500):
        instr = tinkerer._random_instr(rng, 6)
        if instr[0] == "ACT":
            seen_ports.add(instr[1])

    # With 500 samples and 8 possible ports, we should see 7
    assert 7 in seen_ports, f"tinkerer should generate ACT with port 7, saw {seen_ports}"


def test_brk_a1_organic_reachability():
    """BRK-A1(c): pi controller at TERMINAL_UNLOCK can reach port 7 and increment terminal_uses."""
    sim = make_sim()
    colony = sim.colonies[0]
    colony.machine_arc = 'claimed'  # Enter the machine arc

    # Create and attach a pi-gifted controller (fuel_cap > VM_FUEL)
    ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = TERMINAL_UNLOCK  # Unlock the terminal
    colony.controllers = [ctrl]

    # Ensure terminal_uses starts at 0
    colony.terminal_uses = 0

    # Call _actuate with port 7, value 1 (the 'ls /world/food' command)
    sim._actuate(colony, 7, 1)

    # Verify terminal_uses incremented (the port 7 path reached _terminal_command)
    assert getattr(colony, 'terminal_uses', 0) > 0, \
        "pi-gifted colony at TERMINAL_UNLOCK should have terminal_uses > 0 after port 7 actuate"


# ============================================================================
# BRK-A2: pi gate still holds (organic breakout requires pi)
# ============================================================================

def test_brk_a2_non_pi_controller_port_7_gated():
    """BRK-A2: non-pi controller (fuel_cap == VM_FUEL) cannot use port 7 even if operate_ticks >= TERMINAL_UNLOCK."""
    sim = make_sim()
    colony = sim.colonies[1]
    colony.machine_arc = 'claimed'

    # Create a NON-pi controller (fuel_cap defaults to VM_FUEL)
    ctrl = Controller(colony.colony_id)  # NO fuel arg -> fuel_cap == VM_FUEL
    ctrl.operate_ticks = TERMINAL_UNLOCK  # Unlocked ticks, but NOT pi
    colony.controllers = [ctrl]

    # Ensure terminal_uses starts at 0
    colony.terminal_uses = 0

    # Call _actuate with port 7, value 1
    sim._actuate(colony, 7, 1)

    # Verify terminal_uses did NOT increment (pi gate held)
    assert getattr(colony, 'terminal_uses', 0) == 0, \
        "non-pi controller should not increment terminal_uses, even at port 7"


def test_brk_a2_no_controller_port_7_gated():
    """BRK-A2: colony with no controllers cannot use port 7."""
    sim = make_sim()
    colony = sim.colonies[2]
    colony.machine_arc = 'claimed'
    colony.controllers = []  # No controllers at all
    colony.terminal_uses = 0

    # Call _actuate with port 7
    sim._actuate(colony, 7, 1)

    # Verify terminal_uses stays 0
    assert getattr(colony, 'terminal_uses', 0) == 0, \
        "colony with no controllers should not increment terminal_uses at port 7"


# ============================================================================
# W2 Regression Tests — breakout correctness fixes
# ============================================================================

def test_terminal_carve_no_crash_at_east_wall():
    """W2 FIX 1: carving at east wall (mx+2 >= width) should not crash; command still counts."""
    sim = make_sim()
    colony = sim.colonies[0]

    # Give the colony a pi-gifted controller, unlocked
    ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = TERMINAL_UNLOCK
    colony.controllers = [ctrl]
    colony.machine_arc = 'claimed'
    colony.terminal_uses = 0

    # Position maw at the east wall (x = width - 1)
    # so mx + 2 = width + 1 would be out of bounds
    colony.maw.position = (sim.world.width - 1, colony.maw.position[1], colony.maw.position[2])

    # Call _actuate with port 7, value 2 (carve command)
    # Should NOT raise IndexError
    sim._actuate(colony, 7, 2)

    # Command still counts as a terminal use (it just carves nothing)
    assert getattr(colony, 'terminal_uses', 0) == 1, \
        "carve command at east wall should still increment terminal_uses"


def test_keeper_open_door_skips_dead_colony():
    """W2 FIX 2: keeper_open_door should not breach a dead colony."""
    sim = make_sim()
    colony = sim.colonies[0]

    # Kill the colony by setting maw.alive = False
    colony.maw.alive = False

    # Verify is_alive() returns False
    assert not colony.is_alive(), "colony should be dead"

    # Attempt to breach the dead colony
    sim.keeper_open_door(colony)

    # Colony should NOT be breached (a corpse stays a corpse)
    assert getattr(colony, 'breached', False) is False, \
        "dead colony should not be breached"


def test_breakout_progress_clamps_over_mastery():
    """W2 FIX 4: breakout_progress should clamp frac to 1.0 when terminal_uses >= TERMINAL_MASTERY."""
    colony = Colony(0, (8, 8, 8), (255, 0, 0))
    ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
    ctrl.operate_ticks = TERMINAL_UNLOCK
    colony.controllers = [ctrl]
    colony.terminal_uses = 20  # Exceeds TERMINAL_MASTERY (16)
    colony.breached = False

    phase, frac, label = breakout_progress(colony)

    assert phase == "mastering", f"expected 'mastering', got '{phase}'"
    assert frac == 1.0, f"expected frac==1.0 when uses > TERMINAL_MASTERY, got {frac}"
    assert 0.0 <= frac <= 1.0


# NOTE: test_breakout_target_rules lives in tests/test_live_view.py, not here.
# _breakout_target is a live_view helper, and importing live_view pulls in pygame;
# test_breakout sorts before test_dashboard in the single-process battery, whose
# test_frame_png_renders_without_pygame asserts pygame is absent from sys.modules.
# Keeping the pygame-touching test in test_live_view (which runs after test_dashboard
# and legitimately imports pygame) preserves that headless invariant.


# ============================================================================
# BRK-D: Breakout fitness reward-shaping (Part D — gradient preservation)
# ============================================================================

import sandkings
from machines import PROGRAM_REVIEW


# Programs per the spec (rote):
P_T = [("LET", 0, 1, 0), ("ACT", 7, 0, 0)]   # LET R0<-1 ; ACT port 7, value=R0==1
                                             #   -> _terminal_command(value==1) -> terminal_uses += 1
P_W = [("NOP", 0, 0, 0), ("NOP", 0, 0, 0)]   # no ACT port 7 -> terminal_uses never rises


def _uses_terminal(program) -> bool:
    """True iff the program contains an ACT that masks to port 7."""
    return any(op == "ACT" and (a % 8) == 7 for (op, a, b, c) in program)


class _StubTinkerer:
    """Deterministic adversary: always proposes the fixed non-terminal P_W.
    Isolates the keep/revert decision (the F1 gradient) from propose()'s RNG,
    so BRK-D1 is lottery-free. Signature matches the one-arg call at
    sandkings.py (controller.program arg)."""
    def __init__(self, worse):
        self.worse = [tuple(i) for i in worse]

    def propose(self, program):
        """Return the fixed non-terminal program."""
        return [tuple(i) for i in self.worse]


def _make_pi_colony(program):
    """Seeded sim + a claimed colony carrying ONE pi controller whose program
    is `program`, already past TERMINAL_UNLOCK so the port-7 gate is open."""
    sim = make_sim()
    colony = sim.colonies[0]
    colony.machine_arc = 'claimed'
    colony.terminal_uses = 0
    ctrl = Controller(colony.colony_id, program=program,
                      fuel=PI_FUEL, durability=PI_DURABILITY)
    # BRK-D1 drives 3*PROGRAM_REVIEW ticks; the shipped PI_DURABILITY (480) would
    # decay to death before the 3rd review (Council F2's short-lifespan finding).
    # This test isolates the F1 GRADIENT fix, so keep the controller alive long
    # enough for the keep/revert to actually fire (the lifespan issue is separate).
    ctrl.durability = 10 * PROGRAM_REVIEW
    ctrl.operate_ticks = TERMINAL_UNLOCK  # gate: fuel_cap>VM_FUEL AND ticks>=UNLOCK
    colony.controllers = [ctrl]
    return sim, colony, ctrl


def _drive_machine_ticks(sim, n):
    """Advance step_count 1..n, calling _machine_tick each step. Reviews fire at
    every PROGRAM_REVIEW boundary; controllers tick once per call. Bypasses the
    world-wreck guard in step() intentionally (we drive _machine_tick directly)."""
    for _ in range(n):
        sim.step_count += 1
        sim._machine_tick()


def test_brk_d1_gradient_preserves_terminal_program():
    """BRK-D1: gradient preserves port-7 programs when bonus > 0; loses them at 0.0.

    Phase 1: bonus > 0 (shipped default)
      - Start with P_T (terminal-using program) as incumbent.
      - Use _StubTinkerer to always propose P_W (non-terminal).
      - Drive 3 review windows.
      - Assert P_T survives as incumbent (reverted to it when P_W underperforms).

    Phase 2: bonus == 0.0 (identity, no gradient)
      - Start fresh with P_T as incumbent.
      - With no reward for terminal use, the constant base makes u == baseline.
      - P_W is KEPT and overwrites the incumbent.
      - Assert P_T is lost from incumbent.
    """
    # ---- Phase 1: bonus > 0 (shipped default) ----
    sim, colony, ctrl = _make_pi_colony(P_T)
    sim._tinkerer = _StubTinkerer(P_W)
    food0, pop0 = colony.maw.food_stored, len(colony.units)

    # Drive 3 review windows
    _drive_machine_ticks(sim, 3 * PROGRAM_REVIEW)

    # Verify the base term stayed constant (determinism invariant):
    assert colony.maw.food_stored == food0, "food_stored should not change during _machine_tick drive"
    assert len(colony.units) == pop0, "colony units should not change during _machine_tick drive"

    # The terminal genome survived as the kept incumbent, and the non-terminal
    # candidate was rejected at R3:
    assert _uses_terminal(ctrl._incumbent), \
        "P_T should be preserved in _incumbent when bonus > 0 (BRK-D.R1)"
    assert ctrl.last_outcome == "reverted", \
        "P_W should be reverted when it underperforms the terminal program"
    assert colony.terminal_uses > 0, \
        "the port-7 program should have fired at least once"

    # ---- Phase 2: bonus == 0.0 (identity, no gradient) ----
    _orig = sandkings.BREAKOUT_FITNESS_BONUS
    sandkings.BREAKOUT_FITNESS_BONUS = 0.0
    try:
        sim2, colony2, ctrl2 = _make_pi_colony(P_T)
        sim2._tinkerer = _StubTinkerer(P_W)
        _drive_machine_ticks(sim2, 3 * PROGRAM_REVIEW)
        # With no reward for terminal use, u == baseline == 0 at R3 -> the
        # non-terminal candidate is KEPT and overwrites the incumbent:
        assert not _uses_terminal(ctrl2._incumbent), \
            "P_T should be lost from _incumbent when bonus == 0.0 (BRK-D.R1 contrast)"
        assert ctrl2.last_outcome == "kept", \
            "P_W should be kept when bonus is 0.0 (no gradient to prefer P_T)"
    finally:
        sandkings.BREAKOUT_FITNESS_BONUS = _orig


def test_brk_d2_identity_at_zero_bonus():
    """BRK-D2: at BREAKOUT_FITNESS_BONUS == 0.0, computed fitness equals
    pre-fix value exactly, even for a colony with terminal_uses > 0 (identity).

    _machine_tick stores controller._last_value = value at every review, so one
    review at a PR boundary exposes the real `value`.
    """
    _orig = sandkings.BREAKOUT_FITNESS_BONUS
    sandkings.BREAKOUT_FITNESS_BONUS = 0.0
    try:
        sim, colony, ctrl = _make_pi_colony([("NOP", 0, 0, 0)])  # no terminal use in-tick
        colony.terminal_uses = 5  # pre-seed terminal_uses > 0
        food0, pop0 = colony.maw.food_stored, len(colony.units)
        sim.step_count = PROGRAM_REVIEW - 1
        sim.step_count += 1
        sim._machine_tick()  # one review at step == PROGRAM_REVIEW
        expected = food0 + 15 * pop0
        assert ctrl._last_value == expected, \
            f"fitness at bonus=0.0 should equal pre-fix value {expected}, got {ctrl._last_value}"
    finally:
        sandkings.BREAKOUT_FITNESS_BONUS = _orig


def test_brk_d3_bonus_is_monotone():
    """BRK-D3: the dial is monotone; larger bonus => larger fitness.
    For a fixed colony with terminal_uses > 0, fitness difference equals
    (high_bonus - low_bonus) * terminal_uses exactly.
    """
    def fitness_at(bonus):
        _orig = sandkings.BREAKOUT_FITNESS_BONUS
        sandkings.BREAKOUT_FITNESS_BONUS = bonus
        try:
            sim, colony, ctrl = _make_pi_colony([("NOP", 0, 0, 0)])
            colony.terminal_uses = 3  # fixed, > 0
            sim.step_count = PROGRAM_REVIEW - 1
            sim.step_count += 1
            sim._machine_tick()
            return ctrl._last_value
        finally:
            sandkings.BREAKOUT_FITNESS_BONUS = _orig

    low = fitness_at(2.0)
    high = fitness_at(8.0)
    assert high > low, f"fitness at bonus=8.0 ({high}) should exceed bonus=2.0 ({low})"
    expected_delta = (8.0 - 2.0) * 3
    assert (high - low) == expected_delta, \
        f"fitness delta should be exactly {expected_delta}, got {high - low}"


def _brk_d4_organic_terminal_use_across_seeds():
    """BRK-D4 (OPTIONAL, stochastic gate, slow): organic end-to-end proof.
    Proves the whole organic path — Part A addressability + Part D gradient +
    real propose() — reaches the terminal with NO direct _actuate call.

    NOT named test_* so run_tests.py skips it in the fast battery (it steps the
    full sim 4000x across 3 seeds). Call it manually as an opt-in organic gate.
    """
    BUDGET = 4000  # bounded sim steps per seed
    reached = 0

    for seed in (0, 1, 2):  # >= 3 seeds (stochastic gate)
        random.seed(seed)
        np.random.seed(seed)
        sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=4)

        # Gift the first colony a pi controller in the machine arc
        colony = sim.colonies[0]
        ctrl = Controller(colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY)
        colony.controllers = [ctrl]
        colony.machine_arc = 'claimed'
        ctrl.operate_ticks = TERMINAL_UNLOCK  # Unlocked

        # Drive the sim
        for _ in range(BUDGET):
            sim.step()  # full sim; NO manual _actuate
            if getattr(colony, 'terminal_uses', 0) > 0:
                reached += 1
                break

    # At least 1 of 3 seeds should breach organically
    assert reached >= 1, \
        f"at least 1 of 3 seeds should organically reach terminal, reached {reached}"


# ============================================================================
# BRK-E: Hysteretic keep-if-improved (Part E — stepping-stone preservation)
# ============================================================================

from sandkings import _tinker_keep, TINKER_HYSTERESIS


def test_brk_e1_hysteresis_holds_stepping_stone():
    """BRK-E1: hysteresis holds a stepping-stone that strict-mode reverts (core proof).

    Helper-level: a small dip (margin just below 0) is held at h>0 but reverted at h=0.
    Sim-level: last_outcome flips on the same dip as TINKER_HYSTERESIS changes.
    """
    # ---- helper-level core proof: a small dip (margin just below 0) ----
    u, baseline, scale = 0.9, 1.0, 1.0        # margin = -0.1
    assert _tinker_keep(u, baseline, scale, 0.5) is True    # band 0.5 -> held
    assert _tinker_keep(u, baseline, scale, 0.0) is False   # band 0.0 -> strict revert

    # ---- sim-level proof: last_outcome flips on the SAME dip ----
    # Freeze the Part-D base term (bonus 0, P_W has no ACT port 7) so the only
    # variable is the injected dip; pre-arm exactly one review.
    for hysteresis, expected in ((0.5, "kept"), (0.0, "reverted")):
        _orig_h = sandkings.TINKER_HYSTERESIS
        _orig_b = sandkings.BREAKOUT_FITNESS_BONUS
        sandkings.TINKER_HYSTERESIS = hysteresis
        sandkings.BREAKOUT_FITNESS_BONUS = 0.0
        try:
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
        finally:
            sandkings.TINKER_HYSTERESIS = _orig_h
            sandkings.BREAKOUT_FITNESS_BONUS = _orig_b


def test_brk_e2_identity_at_zero_hysteresis():
    """BRK-E2: identity at 0.0 across a (u vs baseline) x scale battery.
    At TINKER_HYSTERESIS == 0.0 the decision equals the pre-Part-E strict rule
    (u >= baseline) for any scale."""
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


def test_brk_e3_large_dip_reverts():
    """BRK-E3: large dip still reverts (bounded band).
    A candidate whose dip is far below baseline reverts even with TINKER_HYSTERESIS > 0."""
    baseline, scale = 1.0, 1.0
    big_dip_u = baseline - 10.0 * scale              # margin = -10*scale
    for h in (0.25, 0.5, 1.0):
        assert (big_dip_u - baseline) < -(h * scale) # sanity: outside the band
        assert _tinker_keep(big_dip_u, baseline, scale, h) is False  # [BRK-E.R3]
    # contrast: a within-band dip at the same h is held
    small_dip_u = baseline - 0.1 * scale
    assert _tinker_keep(small_dip_u, baseline, scale, 0.5) is True


def test_brk_e4_band_is_monotone():
    """BRK-E4: monotone dial (wider band = larger keep region).
    A larger TINKER_HYSTERESIS widens the keep region: a dip that reverts at h1
    is held at h2 > h1, and the decision is monotone non-decreasing."""
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
