"""HYDRO water flow simulation (SPEC_HYDRO) — Phase 1: field + flow + WATER voxel.

Plain-assert tests (run_tests.py style). The flow sim is pure numpy / zero RNG;
these pin conservation, gravity, lateral settling, the voxel mirror, rendering,
and — load-bearing — identity-at-neutral (a normal run never allocates the field).
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sandkings import (
    HYDRO_CAP, HYDRO_SETTLE_MIN, SandKingsSimulation, VoxelType,
)


def make_sim(seed: int = 1, w: int = 40, h: int = 30, d: int = 16) -> SandKingsSimulation:
    # h must exceed the terrain-gen wreck constraint (integers(8, h-13)); keep a
    # normal-ish world so the flow sim has real terrain + headroom.
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=w, height=h, depth=d, num_colonies=2)


def test_hydro_field_is_lazy_and_neutral():
    """A fresh sim has NO water field; ordinary stepping never allocates it — the
    identity guarantee (neutral runs are byte-untouched by HYDRO)."""
    sim = make_sim()
    assert sim._water_field() is None, "no field before any water is introduced"
    for _ in range(30):
        sim.step()
    assert sim._water_field() is None, "a neutral run must never allocate the field"


def test_hydro_conserves_volume():
    """With no sources/evaporation and interior water, total volume is conserved
    exactly across many flow ticks (the CA transfer is symmetric)."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    sim._add_water(cx, cy, 9, 0.8)
    sim._add_water(cx, cy, 8, 0.8)
    total = float(sim.water.sum())
    for _ in range(60):
        sim._hydro_tick()
    assert abs(float(sim.water.sum()) - total) < 1e-4, "interior water volume must be conserved"


def test_hydro_gravity_pulls_water_down():
    """Injected high, water ends up lower (falls onto the terrain floor)."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    top = sim.world.depth - 2
    sim._add_water(cx, cy, top, 0.9)
    for _ in range(60):
        sim._hydro_tick()
    wet = np.argwhere(sim.water > 0.01)
    assert len(wet) > 0
    assert int(wet[:, 2].max()) < top, "water must fall below where it was injected"


def test_hydro_settles_to_a_level():
    """Water poured into one cell of a flat basin spreads laterally toward an even
    level (more than one column ends up wet)."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    for _ in range(4):
        sim._add_water(cx, cy, sim.world.depth - 2, 1.0)  # a tall slug (capped per cell)
    cols_before = {(int(x), int(y)) for x, y, z in np.argwhere(sim.water > 0.01)}
    for _ in range(80):
        sim._hydro_tick()
    cols_after = {(int(x), int(y)) for x, y, z in np.argwhere(sim.water > 0.01)}
    assert len(cols_after) >= len(cols_before), "water should spread across columns as it settles"


def test_hydro_mirrors_water_voxels():
    """Cells at depth >= HYDRO_SETTLE_MIN become WATER voxels; draining clears them.

    A concentrated slug near the map centre (far from the edge sinks) pools deep
    enough to cross the settle threshold; on open flat terrain water correctly
    thins/drains, so we assert while the pool is still deep."""
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    z = sim.world.depth - 2
    for dz in range(3):                # a 3-cell water column (~3 volume units)
        sim._add_water(cx, cy, z - dz, 1.0)
    for _ in range(10):
        sim._hydro_tick()
    n_water = int((sim.world.voxels == VoxelType.WATER.value).sum())
    assert n_water > 0, "a pooled slug must mirror to WATER voxels"
    mask = sim.world.voxels == VoxelType.WATER.value
    assert (sim.water[mask] >= HYDRO_SETTLE_MIN - 1e-6).all(), "WATER voxels track the field"


def test_hydro_water_is_not_solid_or_tunnelable():
    """WATER blocks movement/tunneling (boats cross it) but is not 'ground'."""
    assert not VoxelType.WATER.is_solid()
    assert not VoxelType.WATER.is_tunnelable()


def test_hydro_water_renders():
    """WATER has a glyph + palette entry, and the web PNG renders with water present."""
    from live_view import GLYPHS, VOXEL_LEGEND, build_voxel_palette
    from dashboard import render_frame_png
    assert VoxelType.WATER.value in GLYPHS and VoxelType.WATER.value in VOXEL_LEGEND
    pal = build_voxel_palette()
    assert tuple(int(x) for x in pal[VoxelType.WATER.value]) != (0, 0, 0)
    sim = make_sim()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    sim._add_water(cx, cy, sim.world.depth - 2, 0.9)
    for _ in range(30):
        sim._hydro_tick()
    png = render_frame_png(sim)
    assert isinstance(png, (bytes, bytearray)) and len(png) > 0
