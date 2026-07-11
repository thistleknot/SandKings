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
