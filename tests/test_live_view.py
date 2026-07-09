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


def make_keydown(key, mod=0, unicode=""):
    import pygame
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=unicode)


def test_df_z_keys():
    import pygame
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=1)
    top = sim.world.depth - 1
    assert viewer.z_level == top, "starts at surface"

    # '>' descends (shift+period unicode, and ctrl+period)
    viewer._handle_event(make_keydown(pygame.K_PERIOD, mod=pygame.KMOD_LSHIFT, unicode=">"))
    assert viewer.z_level == top - 1
    viewer._handle_event(make_keydown(pygame.K_PERIOD, mod=pygame.KMOD_LCTRL))
    assert viewer.z_level == top - 2

    # '<' rises (DF up), clamped at the top
    viewer._handle_event(make_keydown(pygame.K_COMMA, mod=pygame.KMOD_LSHIFT, unicode="<"))
    viewer._handle_event(make_keydown(pygame.K_COMMA, mod=pygame.KMOD_LCTRL))
    viewer._handle_event(make_keydown(pygame.K_COMMA, mod=pygame.KMOD_LCTRL))
    assert viewer.z_level == top, "clamped at depth-1"

    # unmodified comma/period still control speed, not z
    sps = viewer.pacer.steps_per_second
    viewer._handle_event(make_keydown(pygame.K_PERIOD, unicode="."))
    assert viewer.pacer.steps_per_second > sps and viewer.z_level == top
    viewer._handle_event(make_keydown(pygame.K_COMMA, unicode=","))
    assert viewer.pacer.steps_per_second == sps and viewer.z_level == top


def test_hud_respawn_countdown():
    sim = make_sim()
    dead = sim.colonies[0]
    dead.maw.alive = False
    sim.pending_respawns = {dead.colony_id: sim.step_count + 42}
    lines = build_hud_lines(sim, sps=5.0, paused=False, z_level=2, capturing=False)
    joined = "\n".join(lines)
    assert f"Colony {dead.colony_id}: DEAD (respawn in 42)" in joined


def test_hud_event_feed():
    from collections import deque
    sim = make_sim()
    sim.events = deque([(i, f"event number {i}") for i in range(10)], maxlen=50)
    lines = build_hud_lines(sim, sps=5.0, paused=False, z_level=2, capturing=False)
    joined = "\n".join(lines)
    for i in range(6, 10):
        assert f"[{i}] event number {i}" in joined, "last EVENT_LINES entries shown"
    assert "[5]" not in joined, "older events dropped"


def test_pheromone_overlay_array():
    from live_view import pheromone_overlay_array
    from sandkings import PheromoneType
    sim = make_sim()
    colony = sim.colonies[0]
    pos = (4, 4, 2)
    sim.pheromones.deposit(pos, colony.colony_id, PheromoneType.DANGER, 1.0)
    glow = pheromone_overlay_array(sim.pheromones, sim.colonies, 2, PheromoneType.DANGER)
    assert glow.shape == (sim.world.width, sim.world.height, 3)
    assert glow[4, 4].sum() > 0, "deposited cell glows"
    assert glow[10, 8].sum() == 0, "untouched cell dark"


def test_p_key_cycles_overlay():
    import pygame
    from live_view import PHEROMONE_OVERLAYS
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=1)
    assert PHEROMONE_OVERLAYS[viewer.overlay_index] is None
    seen = []
    for _ in range(len(PHEROMONE_OVERLAYS)):
        viewer._handle_event(make_keydown(pygame.K_p))
        seen.append(PHEROMONE_OVERLAYS[viewer.overlay_index])
    assert seen[-1] is None, "cycle wraps back to off"
    assert len([s for s in seen if s is not None]) == len(PHEROMONE_OVERLAYS) - 1


def test_glyph_map_covers_all_voxel_types():
    from live_view import GLYPHS, UNIT_GLYPHS, MAW_GLYPH
    from sandkings import UnitType
    for vt in VoxelType:
        assert vt.value in GLYPHS, f"no glyph for {vt}"
    for ut in UnitType:
        assert ut in UNIT_GLYPHS, f"no glyph for {ut}"
    assert MAW_GLYPH


def test_hud_text_color_lightens_dark():
    from live_view import hud_text_color
    assert hud_text_color((0, 0, 0)) == (150, 150, 150), "black must be readable"
    assert hud_text_color((255, 255, 255)) == (255, 255, 255)
    assert hud_text_color((255, 0, 0)) == (255, 0, 0)


def test_hud_entries_colors_and_hp_bar():
    from live_view import build_hud_entries, event_tint, hud_text_color
    from collections import deque
    from sandkings import MAW_MAX_HEALTH
    sim = make_sim()
    wounded = sim.colonies[0]
    wounded.maw.health = MAW_MAX_HEALTH * 0.5
    sim.events = deque([(1, "Keeper scatters 40 food"),
                        (2, "Colony 1 besieges Colony 0!")], maxlen=50)
    entries = build_hud_entries(sim, sps=5.0, paused=False, z_level=2, capturing=False)
    by_text = {text: color for text, color in entries}
    assert by_text[f"Colony {wounded.colony_id}"] == hud_text_color(wounded.color)
    maw_line = next(t for t in by_text if t.startswith("  food:") and "[" in t)
    assert "=" in maw_line and "." in maw_line, "damaged maw shows text hp bar"
    assert by_text["[1] Keeper scatters 40 food"] == event_tint("Keeper")
    assert by_text["[2] Colony 1 besieges Colony 0!"] == event_tint("besieges")


def test_r_key_toggles_render_style():
    import pygame
    from live_view import RenderStyle
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=1)
    assert viewer.render_style == RenderStyle.GLYPH, "glyph is the default"
    viewer._handle_event(make_keydown(pygame.K_r))
    assert viewer.render_style == RenderStyle.BLOCKS
    viewer._handle_event(make_keydown(pygame.K_r))
    assert viewer.render_style == RenderStyle.GLYPH


def test_topdown_cells_consistency():
    from live_view import topdown_cells
    world = make_empty_world()
    world.voxels[3, 3, 2] = VoxelType.SAND.value
    found, depth, has, own = topdown_cells(world, 4)
    assert found[3, 3] == VoxelType.SAND.value
    assert depth[3, 3] == 2
    assert has[3, 3] and not has[1, 1]


def test_manager_entries_content():
    from live_view import build_manager_entries
    sim = make_sim()
    for _ in range(4):  # let instincts populate
        sim.step()
    cid = sim.colonies[0].colony_id
    entries = build_manager_entries(sim, cid)
    joined = "\n".join(t for t, _ in entries)
    assert f"MANAGER: Colony {cid}" in joined
    assert "CONCEPTS" in joined and "TOP SOLDIERS" in joined and "DECISIONS" in joined
    from hive_mind_monitor import ANCHOR_SEEDS
    for seed in ANCHOR_SEEDS:
        assert seed in joined, f"concept {seed} missing from manager"
    assert "instincts" in joined, "rule-based colony labeled as instincts"


def test_manager_keys():
    import pygame
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=1)
    assert not viewer.manager_open
    viewer._handle_event(make_keydown(pygame.K_m))
    assert viewer.manager_open
    start = viewer.manager_colony
    viewer._handle_event(make_keydown(pygame.K_RIGHT))
    assert viewer.manager_colony != start
    for _ in range(len(sim.colonies) - 1):
        viewer._handle_event(make_keydown(pygame.K_RIGHT))
    assert viewer.manager_colony == start, "RIGHT wraps around"
    viewer._handle_event(make_keydown(pygame.K_m))
    assert not viewer.manager_open


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
