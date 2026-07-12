"""Breakout tests (SPEC_BREAKOUT.md BRK-B1, BRK-C1, BRK-C2).

The keeper's open-door breach and the breakout-proximity gauge:
- BRK-B1: pure fn breakout_progress across no-pi, unlocking, mastering, breached phases
- BRK-C1: open the door breaches a colony (idempotent on state and log)
- BRK-C2: bound-god gate (hand_stayed) blocks open door without breaching
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
