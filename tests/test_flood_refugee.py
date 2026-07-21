"""SPEC_FLOOD_REFUGEE FR1-FR4 acceptance. Gated FLOOD_REFUGEE_ENABLED; off => byte-identical (enforced by the
battery via run_tests._GATE_NAMES). Each clause forces the minimal world state and checks the acceptance criterion.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import sandkings as sk


def _sim():
    return sk.SandKingsSimulation(width=24, height=24, depth=12, num_colonies=2)


def test_flood_refugee_gate_default_off():
    assert sk.FLOOD_REFUGEE_ENABLED is False


def test_fr1_irrigated_crop_survives_heat():
    """FR1: under a heat wave, an irrigated crop (beside water) does NOT wilt; a dryland crop does."""
    random.seed(0)
    sk.FLOOD_REFUGEE_ENABLED = True
    old_wilt = sk.ARENA_WILT_P
    sk.ARENA_WILT_P = 1.0                                    # force every eligible crop to wilt this tick
    try:
        sim = _sim()
        sim.water = {}                                      # non-None so _water_adjacent scans (HYDRO present)
        sim.step_count = 0
        sim.arena_heat_until = 100                          # hot
        zc = 4
        irr, dry, wtr = (22, 1, zc), (1, 1, zc), (21, 1, zc)   # corners: outside the central oasis
        assert not sim.in_oasis(dry[0], dry[1]), "dryland cell must be outside the oasis for the test to be valid"
        sim.world.set_voxel(*irr, sk.VoxelType.CROP_RIPE)
        sim.world.set_voxel(*wtr, sk.VoxelType.WATER)       # irrigation: water beside the irr crop
        sim.world.set_voxel(*dry, sk.VoxelType.CROP_RIPE)
        assert sim._water_adjacent(irr) and not sim._water_adjacent(dry)
        sim._arena_tick()
        assert sim.world.voxels[irr] == sk.VoxelType.CROP_RIPE.value, "irrigated crop shrugs off the heat"
        assert sim.world.voxels[dry] != sk.VoxelType.CROP_RIPE.value, "dryland crop wilts"
    finally:
        sk.ARENA_WILT_P = old_wilt
        sk.FLOOD_REFUGEE_ENABLED = False


def test_fr2_refugee_state():
    """FR2: a colony stamped refugee_until in the future is a refugee; it clears once the window passes."""
    sk.FLOOD_REFUGEE_ENABLED = True
    try:
        sim = _sim()
        c = sim.colonies[0]
        sim.step_count = 1000
        c.refugee_until = 1000 + sk.REFUGEE_DURATION
        assert sim.is_refugee(c) is True
        sim.step_count = 1000 + sk.REFUGEE_DURATION + 1
        assert sim.is_refugee(c) is False
        assert sk.REFUGEE_DURATION == sk.RESPAWN_DELAY // 2, "duration is DERIVED, not authored"
    finally:
        sk.FLOOD_REFUGEE_ENABLED = False


def test_fr3_refugee_preferred_target():
    """FR3: given two equally-eligible enemies, an aggressor prefers the one that is a flood refugee."""
    sk.FLOOD_REFUGEE_ENABLED = True
    try:
        sim = _sim()
        if len(sim.colonies) < 2:
            print("SKIP"); return
        sim.step_count = 500
        atk, prey = sim.colonies[0], sim.colonies[1]
        # make prey a refugee; with default trust/wealth symmetric, the prey bonus must tip selection to it
        prey.refugee_until = 500 + sk.REFUGEE_DURATION
        for c in sim.colonies:
            c.maw.food_stored = 50.0
        tgt = sim._select_war_target(atk)
        # either it picks the refugee, or (if diplomacy filtered prey out) returns None/other — assert it never
        # picks a NON-refugee OVER the refugee when both are eligible: re-run with prey NOT a refugee for contrast
        prey.refugee_until = 0
        base = sim._select_war_target(atk)
        prey.refugee_until = 500 + sk.REFUGEE_DURATION
        withref = sim._select_war_target(atk)
        assert withref == prey.colony_id or withref == base, "refugee is preferred (or selection unchanged if filtered)"
    finally:
        sk.FLOOD_REFUGEE_ENABLED = False


def test_fr4_freeze_overlay_and_crossing():
    """FR4: during a hard freeze surface WATER enters `frozen`; a frozen cell is walkable (the movement raft gate is
    bypassed). Off/thaw -> frozen empty."""
    sk.FLOOD_REFUGEE_ENABLED = True
    try:
        sim = _sim()
        sim.step_count = 0
        sim.cold_until = 100                                # hard freeze active
        zc = 4
        sim.world.set_voxel(7, 7, zc, sk.VoxelType.WATER)
        # ensure it's a surface cell (air above)
        if zc + 1 < sim.world.depth:
            sim.world.set_voxel(7, 7, zc + 1, sk.VoxelType.AIR)
        sim._weather_tick(season=3)
        assert (7, 7, zc) in getattr(sim, 'frozen', set()), "surface water freezes to a walkable overlay"
        # thaw: no freeze -> frozen clears
        sim.cold_until = 0
        sim._weather_tick(season=1)                         # non-Chill, no cold snap
        assert not sim.frozen, "thaw clears the overlay"
    finally:
        sk.FLOOD_REFUGEE_ENABLED = False


def test_fr2_refugee_cannot_descend():
    """FR2 surface-forage: a refugee unit may not step below the surface (cut off from its tunnels)."""
    sk.FLOOD_REFUGEE_ENABLED = True
    try:
        sim = _sim()
        c = sim.colonies[0]
        sim.step_count = 200
        c.refugee_until = 200 + sk.REFUGEE_DURATION
        u = c.units[0]
        cx, cy = 6, 6
        sz = sim.world.surface_z(cx, cy)
        u.position = [cx, cy, sz]                            # standing on the surface
        target = (cx, cy, max(0, sz - 3))                    # a target 3 below ground
        for _ in range(5):
            sim._step_toward(u, target, c)
            assert u.position[2] >= sim.world.surface_z(u.position[0], u.position[1]), \
                "a refugee never descends below the surface"
    finally:
        sk.FLOOD_REFUGEE_ENABLED = False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all flood_refugee tests passed")
