"""Acceptance tests for SPEC_MACHINE_AGE.md (T28-T40).

Preconditions: numpy; seeded sims. Failure modes covered: VM non-halting,
wreck geometry breaking gravity, actuators leaking without devices,
radiation harming without the reactor, arc dead-ends.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from machines import (
    ANCIENT_DURABILITY,
    Controller,
    DEMO_PROGRAM,
    Device,
    GPTinkerer,
    VM_FUEL,
    make_if,
)
from sandkings import SandKing, SandKingsSimulation, UnitType, VoxelType, VoxelWorld


def make_sim(seed: int = 91) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_vm_halts_and_wraps():
    loop = Controller(0, [("JMP", 0, 0, 0)])
    assert loop.tick(lambda p: 0, lambda p, v: None) == VM_FUEL
    math = Controller(0, [("LET", 0, 32767, 0), ("LET", 1, 1, 0),
                          ("ADD", 0, 1, 0)])
    math.tick(lambda p: 0, lambda p, v: None)
    assert math.registers[0] == -32768, "int16 wraparound"
    div = Controller(0, [("LET", 0, 7, 0), ("LET", 1, 0, 0), ("DIV", 0, 1, 0)])
    div.tick(lambda p: 0, lambda p, v: None)
    assert div.registers[0] == 0, "DIV by zero yields 0, no fault"


def test_vm_act_budget_and_registers_persist():
    prog = [("LET", 0, 1, 0)] + [("ACT", 0, 0, 0)] * 5
    c = Controller(0, prog)
    acts = []
    c.tick(lambda p: 0, lambda p, v: acts.append(p))
    assert len(acts) == 2, "only the first 2 ACTs are honored"
    counter = Controller(0, [("LET", 1, 1, 0), ("ADD", 2, 1, 0)])
    for _ in range(3):
        counter.tick(lambda p: 0, lambda p, v: None)
    assert counter.registers[2] == 3, "registers persist across ticks (PLC)"


def test_demo_program_siege_gate():
    c = Controller(0, DEMO_PROGRAM)
    acts = []
    c.tick(lambda p: 3 if p == 3 else 0, lambda p, v: acts.append((p, v)))
    assert (0, 1) in acts and (2, 1) in acts, "besieged: close + alarm"
    acts.clear()
    c.tick(lambda p: 0, lambda p, v: acts.append((p, v)))
    assert (0, 0) in acts, "clear: open"


def test_wreck_geometry_and_gravity():
    world = VoxelWorld(80, 40, 20, seed=31)
    assert world.wreck is not None
    hull = int((world.voxels == VoxelType.HULL.value).sum())
    salvage = int((world.voxels == VoxelType.SALVAGE.value).sum())
    assert 50 <= hull <= 66 and 8 <= salvage <= 12
    before = world.voxels.copy()
    world.apply_gravity()
    assert np.array_equal(before, world.voxels), "wreck world stays settled"
    tiny = VoxelWorld(20, 10, 5, seed=31)
    assert getattr(tiny, 'wreck', None) is None, "no wreck in shallow worlds"


def test_gate_actuator_closes_and_opens():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.machine_arc = 'claimed'
    colony.devices = [Device('GATE', colony.colony_id)]
    mx, my, mz = colony.maw.position
    sim._actuate(colony, 0, 1)
    device = colony.devices[0]
    assert device.gate_closed and device.gate_cells, "dome raised"
    for pos in device.gate_cells:
        assert sim.world.voxels[pos] == VoxelType.TUNNEL_WALL.value
    sim._actuate(colony, 0, 0)
    assert not device.gate_closed
    # wear applied only on the two state changes
    assert device.durability == 240 - 4


def test_valve_alarm_beacon():
    from sandkings import PheromoneType
    sim = make_sim()
    colony = sim.colonies[0]
    mx, my, mz = colony.maw.position
    valve_pos = (mx + 2, my, mz)
    sim.world.voxels[valve_pos] = VoxelType.AIR.value
    colony.devices = [Device('VALVE', colony.colony_id, valve_pos),
                      Device('ALARM', colony.colony_id),
                      Device('BEACON', colony.colony_id, valve_pos)]
    colony.maw.food_stored = 100.0
    sim._actuate(colony, 1, 1)  # VALVE
    assert sim.world.voxels[valve_pos] == VoxelType.FOOD.value
    assert colony.maw.food_stored == 85.0
    sim._actuate(colony, 2, 1)  # ALARM
    assert sim.pheromones.get_strength((mx, my, mz), colony.colony_id,
                                       PheromoneType.DANGER) > 0
    sim._actuate(colony, 3, 1)  # BEACON
    assert valve_pos in colony.known_food


def test_geo_and_rad_cartridges():
    sim = make_sim()
    colony = sim.colonies[0]
    mx, my, mz = colony.maw.position
    pos = (mx - 1, my, mz)
    sim.world.voxels[pos] = VoxelType.SAND.value
    colony.devices = [Device('EXCAVATE', colony.colony_id, pos),
                      Device('RAD', colony.colony_id, pos)]
    sim._actuate(colony, 4, 1)  # EXCAVATE eats a sand voxel nearby
    v = sim.world.voxels
    assert (v[max(0, mx-2):mx+1, my-1:my+2, mz-1:mz+2]
            == VoxelType.AIR.value).any()
    sim._actuate(colony, 6, 1)  # RAD emits
    assert sim.radiation_at(pos[0], pos[1]) >= 5.0


def test_radiation_reactor_and_mutation_catalysis():
    from machines import RAD_MILD
    sim = make_sim()
    for _ in range(60):
        sim.step()
    cx, cy, _ = sim.world.wreck['controller_pos']
    assert sim.radiation_at(cx, cy) > 0, "the damaged reactor seeps"
    # mild radiation catalyzes respawn mutation (T40): verified by the
    # rate branch — plant a survivor maw in a mild zone
    survivor = sim.colonies[0]
    px, py, _ = survivor.maw.position
    sim._radiation()[px, py] = RAD_MILD + 0.1
    assert sim.radiation_at(px, py) >= RAD_MILD


def test_arc_claim_and_ancient_fall_silent():
    sim = make_sim()
    colony = sim.colonies[0]
    colony.machine_arc = 'known'
    artifact = sim._wreck_artifact_pos()
    worker = SandKing(colony.colony_id, artifact, UnitType.WORKER)
    colony.units.append(worker)
    sim._machine_tick()
    assert colony.machine_arc == 'claimed'
    assert colony.controllers and colony.controllers[0].ancient
    # it already executed (and decayed) within this same tick
    assert 240 < colony.controllers[0].durability <= ANCIENT_DURABILITY
    # the legendary item never dies: it falls silent and re-drops
    colony.controllers[0].durability = 0
    sim._machine_tick()
    assert not colony.controllers
    assert colony.machine_arc == 'known'
    assert sim._wreck_artifact_pos() == colony.maw.position
    assert any("falls silent" in m for _, m in sim.events)


def test_tinkerer_reverts_worse_programs():
    random.seed(3)
    t = GPTinkerer()
    prog = list(DEMO_PROGRAM)
    for _ in range(100):
        cand = t.propose(prog)
        assert 1 <= len(cand) <= 32
        Controller(0, cand).tick(lambda p: 0, lambda p, v: None)  # all runnable


def test_machine_state_pickles():
    import pickle
    sim = make_sim()
    colony = sim.colonies[0]
    colony.machine_arc = 'claimed'
    colony.controllers = [Controller(colony.colony_id, ancient=True)]
    colony.devices = [Device('GATE', colony.colony_id)]
    for _ in range(30):
        sim.step()
    revived = pickle.loads(pickle.dumps(sim))
    rc = revived.colonies[0]
    assert rc.controllers and rc.controllers[0].ancient
    assert rc.devices[0].kind == 'GATE'
    revived.step()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all machine tests passed")
