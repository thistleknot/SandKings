"""Acceptance tests for SPEC_LIVE_VIEW.md.

Preconditions: pygame installed; runs headlessly (dummy SDL driver is set
before pygame import). Failure modes covered: palette drift from the GIF
renderer, surfarray axis-order mistakes, pacer math, loop hangs.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from live_view import (
    DEPTH_SHADE_FACTOR,
    DEPTH_SHADE_MIN,
    MAX_STEPS_PER_FRAME,
    RETREAT_BORDER_COLOR,
    VOID_COLOR,
    LiveViewer,
    StepPacer,
    ViewMode,
    build_hud_lines,
    build_voxel_palette,
    depth_shade,
    slice_color_array,
    topdown_color_array,
    unit_draw_color,
    unit_visible_depth,
)
from sandkings import SandKingsSimulation, VoxelType, VoxelWorld

RENDER_Z_SLICE_COLORS = {
    VoxelType.AIR: (20, 20, 20),
    VoxelType.SAND: (194, 178, 128),
    VoxelType.STONE: (50, 50, 50),
    VoxelType.GLASS: (100, 100, 100),
    VoxelType.FOOD: (0, 255, 0),
    VoxelType.CORPSE: (128, 0, 0),
    VoxelType.TUNNEL_WALL: (139, 90, 43),
}


def make_sim(seed: int = 42) -> SandKingsSimulation:
    import random
    random.seed(seed)
    np.random.seed(seed)
    return SandKingsSimulation(width=20, height=10, depth=5, num_colonies=2)


def test_palette_matches_gif_renderer():
    palette = build_voxel_palette()
    for voxel_type, color in RENDER_Z_SLICE_COLORS.items():
        assert tuple(palette[voxel_type.value]) == color, voxel_type


def test_slice_color_array_shape_and_territory_tint():
    sim = make_sim()
    z = sim.world.depth // 2
    # Force one known owned-air voxel for colony 0
    sim.world.voxels[5, 5, z] = VoxelType.AIR.value
    sim.world.ownership[5, 5, z] = 0
    colors = slice_color_array(sim.world, sim.colonies, z)
    assert colors.shape == (sim.world.width, sim.world.height, 3)
    expected = tuple(int(c * 0.3) for c in sim.colonies[0].color)
    assert tuple(colors[5, 5]) == expected


def test_unit_draw_color_retreat_distinct():
    for colony_color in [(255, 0, 0), (255, 255, 255), (0, 0, 0), (255, 165, 0)]:
        normal = unit_draw_color(colony_color, retreating=False)
        retreat = unit_draw_color(colony_color, retreating=True)
        assert retreat[1] == RETREAT_BORDER_COLOR
        assert normal != retreat
    # Contrast borders: light colony -> black border, dark -> white
    assert unit_draw_color((255, 255, 255), False)[1] == (0, 0, 0)
    assert unit_draw_color((0, 0, 0), False)[1] == (255, 255, 255)


def make_empty_world(w: int = 8, h: int = 6, d: int = 6) -> VoxelWorld:
    """Deterministic all-air world (terrain gen wiped) for top-down tests."""
    world = VoxelWorld(w, h, d)
    world.voxels[:] = VoxelType.AIR.value
    world.ownership[:] = -1
    return world


def test_topdown_first_nonair_and_depth_shading():
    world = make_empty_world()
    world.voxels[3, 3, 2] = VoxelType.SAND.value
    world.voxels[4, 4, 4] = VoxelType.STONE.value
    colors = topdown_color_array(world, [], z_level=4)
    assert colors.shape == (8, 6, 3)
    sand = build_voxel_palette()[VoxelType.SAND.value].astype(float)
    expected_sand = (sand * depth_shade(2)).astype(np.uint8)
    assert tuple(colors[3, 3]) == tuple(expected_sand), "sand 2 below must be shaded"
    stone = build_voxel_palette()[VoxelType.STONE.value]
    assert tuple(colors[4, 4]) == tuple(stone), "terrain at z_level is unshaded"
    assert tuple(colors[1, 1]) == VOID_COLOR, "bottomless column renders void"


def test_topdown_territory_blend():
    world = make_empty_world()
    world.voxels[2, 2, 1] = VoxelType.SAND.value
    world.ownership[2, 2, 1] = 0
    sim_colony = make_sim().colonies[0]
    sim_colony.colony_id = 0
    plain = topdown_color_array(world, [], z_level=3)[2, 2]
    tinted = topdown_color_array(world, [sim_colony], z_level=3)[2, 2]
    assert tuple(plain) != tuple(tinted), "owned surface voxel must blend colony color"


def test_depth_shade_curve():
    assert depth_shade(0) == 1.0
    assert depth_shade(1) == DEPTH_SHADE_FACTOR
    assert depth_shade(100) == DEPTH_SHADE_MIN


def test_unit_visible_depth():
    world = make_empty_world()
    assert unit_visible_depth(world, (2, 2, 1), z_level=3) == 2, "clear column: visible"
    assert unit_visible_depth(world, (2, 2, 3), z_level=3) == 0, "unit at z_level"
    world.voxels[2, 2, 2] = VoxelType.SAND.value
    assert unit_visible_depth(world, (2, 2, 1), z_level=3) is None, "occluded by sand"
    assert unit_visible_depth(world, (2, 2, 4), z_level=3) is None, "above z_level"


def test_hud_lines_content():
    sim = make_sim()
    lines = build_hud_lines(sim, sps=5.0, paused=True, z_level=2, capturing=False,
                            view_mode=ViewMode.TOPDOWN)
    joined = "\n".join(lines)
    assert f"Step {sim.step_count}" in joined
    assert "PAUSED" in joined
    assert "TOPDOWN" in joined, "HUD must name the active view mode (R14)"
    for colony in sim.colonies:
        assert f"Colony {colony.colony_id}" in joined
    assert "food:" in joined and "maw:" in joined and "retreat:" in joined


def test_pacer_paused_and_single_step():
    pacer = StepPacer(steps_per_second=10)
    assert pacer.update(1000, paused=True) == 0
    pacer.request_single_step()
    assert pacer.update(16, paused=True) == 1, "single step must yield exactly 1"
    assert pacer.update(16, paused=True) == 0, "single step consumed"


def test_pacer_owed_steps_and_clamp():
    pacer = StepPacer(steps_per_second=10)  # 100 ms per step
    assert pacer.update(250, paused=False) == 2
    assert pacer.update(50, paused=False) == 1  # 50ms residual carried over
    assert pacer.update(60_000, paused=False) == MAX_STEPS_PER_FRAME
    assert pacer.update(0, paused=False) == 0, "clamp must discard residual debt"


def test_pacer_speed_clamps():
    pacer = StepPacer(steps_per_second=50)
    pacer.faster()
    assert pacer.steps_per_second == 60.0
    for _ in range(20):
        pacer.slower()
    assert pacer.steps_per_second == 0.5


def test_full_loop_headless_auto_exit():
    sim = make_sim()
    viewer = LiveViewer(sim, steps_per_second=60.0, max_steps=5)
    viewer.run()  # must terminate, not hang
    assert sim.step_count == 5
    assert viewer.steps_done == 5


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all live view tests passed")
