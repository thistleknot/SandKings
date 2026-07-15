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
    # Force one known owned-air voxel for colony 0, OUTSIDE the oasis disc
    # (oasis columns are teal-blended per R23)
    sim.world.voxels[2, 2, z] = VoxelType.AIR.value
    sim.world.ownership[2, 2, z] = 0
    colors = slice_color_array(sim.world, sim.colonies, z)
    assert colors.shape == (sim.world.width, sim.world.height, 3)
    expected = tuple(int(c * 0.3) for c in sim.colonies[0].color)
    assert tuple(colors[2, 2]) == expected


def test_unit_draw_color_retreat_distinct():
    for colony_color in [(255, 0, 0), (255, 255, 255), (0, 0, 0), (255, 165, 0)]:
        normal = unit_draw_color(colony_color, retreating=False)
        retreat = unit_draw_color(colony_color, retreating=True)
        assert retreat[1] == RETREAT_BORDER_COLOR
        assert normal != retreat
    # Contrast borders: light colony -> black border, dark -> white
    assert unit_draw_color((255, 255, 255), False)[1] == (0, 0, 0)
    assert unit_draw_color((0, 0, 0), False)[1] == (255, 255, 255)


def make_empty_world(w: int = 20, h: int = 14, d: int = 6) -> VoxelWorld:
    """Deterministic all-air world (terrain gen wiped) for top-down tests.

    Sized so the low-coordinate test cells sit OUTSIDE the oasis disc
    (center (10,7), r=6 per R23) and keep their un-blended colors."""
    world = VoxelWorld(w, h, d)
    world.voxels[:] = VoxelType.AIR.value
    world.ownership[:] = -1
    return world


def test_topdown_first_nonair_and_depth_shading():
    world = make_empty_world()
    world.voxels[3, 3, 2] = VoxelType.SAND.value
    world.voxels[4, 4, 4] = VoxelType.STONE.value
    colors = topdown_color_array(world, [], z_level=4)
    assert colors.shape == (20, 14, 3)
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
    for colony in sim.colonies:  # D1: roster leads with slot id + house
        assert (f"{colony.colony_id}:{colony.house}" in joined
                or f"Colony {colony.colony_id}" in joined)
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
    # D1: the roster line leads with the slot id, speaks in houses
    roster = next(t for t in by_text
                  if t.startswith(f"{wounded.colony_id}:")
                  or t == f"Colony {wounded.colony_id}")
    assert by_text[roster] == hud_text_color(wounded.color)
    maw_line = next(t for t in by_text if t.startswith("  food:") and "[" in t)
    assert "=" in maw_line and "." in maw_line, "damaged maw shows text hp bar"
    assert by_text["[1] Keeper scatters 40 food"] == event_tint("Keeper")
    siege = next(t for t in by_text if t.startswith("[2] ") and "besieges" in t)
    assert by_text[siege] == event_tint("besieges"), "house-substituted tint"


def test_r_key_toggles_render_style():
    import pygame
    from live_view import RenderStyle
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=1)
    assert viewer.render_style == RenderStyle.GLYPH, "glyph is the default"
    viewer._handle_event(make_keydown(pygame.K_r))
    assert viewer.render_style == RenderStyle.BLOCKS
    viewer._handle_event(make_keydown(pygame.K_r))
    assert viewer.render_style == RenderStyle.TILES        # 3-way cycle: GLYPH -> BLOCKS -> TILES
    viewer._handle_event(make_keydown(pygame.K_r))
    assert viewer.render_style == RenderStyle.GLYPH, "wraps back to glyph"


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
    assert f"HOUSE {sim._house(sim.colonies[0])} (Colony {cid})" in joined
    # Redesigned manager: a focused per-maw inspector. THOUGHTS shows only the anchors
    # actually firing (not the full 35-anchor wall), plus the MAW->MANAGER->SWARM comms
    # pipeline (directive -> broadcast -> pheromone field) the user cycles through.
    assert "THOUGHTS" in joined, "thoughts section present"
    assert "MAW -> MANAGER -> SWARM" in joined, "the maw->manager->pheromone pipeline present"
    assert ("  mgr  posture:" in joined and "pher food" in joined), "manager broadcast + pheromone field shown"
    assert "RELATIONS" in joined and "TOP SOLDIERS" in joined and "DECISIONS" in joined
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


def test_attached_viewer_shares_runner_and_mirrors():
    # U2/U8: a viewer built on a TerrariumRunner shares its sim/lock and never
    # owns stepping; with mirror on it snapshots the glyph surface to PNG.
    import pygame

    from dashboard import TerrariumRunner
    sim = make_sim()
    runner = TerrariumRunner(sim)
    viewer = LiveViewer(runner)  # attached mode
    assert viewer.sim is sim and viewer.runner is runner
    assert viewer._owns_runner is False
    # pause proxies the runner (one truth across window and web)
    viewer.paused = True
    assert runner.paused is True
    # snapshot the glyph surface (throttle bypassed)
    pygame.init()
    viewer._screen = pygame.display.set_mode((64, 48))
    viewer._screen.fill((18, 18, 28))
    viewer._last_mirror_ms = -10 ** 9
    viewer._mirror_snapshot()
    pygame.quit()
    assert runner.glyph_png and runner.glyph_png[:8] == b"\x89PNG\r\n\x1a\n"


def test_world_alive_render_is_pure():
    """A World Alive (Phase 1): the fish + boat + beast-glyph render passes draw without crashing and MUTATE
    NOTHING — they are pure renderers over sim scalars/flags (guppy_pop, unit.rafted, sim.fauna)."""
    import pygame
    sim = make_sim()
    for _ in range(20):                 # populate units, water, guppy_pop
        sim.step()
    sim.guppy_pop = 120.0               # a healthy shoal so the fish layer draws
    for c in sim.colonies:              # put a unit on a raft so the boat pass runs
        if c.units:
            c.units[0].rafted = True
            break
    viewer = LiveViewer(sim, max_steps=1)
    pygame.init()
    viewer._screen = pygame.display.set_mode(
        (sim.world.width * viewer.cell_size + 400, sim.world.height * viewer.cell_size + 40))
    viewer._load_fonts()                # fonts are lazy (run() calls this) — needed for _blit_glyph
    gp_before, step_before = sim.guppy_pop, sim.step_count
    viewer._render_body()               # exercises the new fish + boat + beast-glyph passes
    pygame.quit()
    assert sim.guppy_pop == gp_before and sim.step_count == step_before, \
        "the World-Alive render passes must not mutate sim state (pure renderer)"


def test_combat_strobe_renders_pure():
    """Combat strobe: with two hostile units adjacent and the strobe forced ON, _render_body draws the red
    combat pulse without crashing and mutates nothing (pure renderer)."""
    import pygame
    sim = make_sim()
    for _ in range(10):
        sim.step()
    a = next((c for c in sim.colonies if c.units), None)
    b = next((c for c in sim.colonies if c is not a and c.units), None)
    if a is not None and b is not None:            # force an adjacency so the combat pass draws
        ax, ay, az = a.units[0].position
        b.units[0].position = (ax + 1, ay, az)
    viewer = LiveViewer(sim, max_steps=1)
    pygame.init()
    viewer._screen = pygame.display.set_mode(
        (sim.world.width * viewer.cell_size + 400, sim.world.height * viewer.cell_size + 40))
    viewer._load_fonts()
    viewer._blink_on = lambda *a, **k: True        # force the strobe ON to exercise the red draw path
    step0 = sim.step_count
    viewer._render_body()
    pygame.quit()
    assert sim.step_count == step0, "the combat strobe must not mutate the sim (pure renderer)"


def test_poison_cloud_renders_pure():
    """Chemical war (SPEC_CHEMICAL_WAR CW1): the poison-cloud overlay draws without crashing and mutates
    nothing — a pure read of sim.poison (mirrors the fire overlay)."""
    import pygame
    sim = make_sim()
    for _ in range(10):
        sim.step()
    # seed a poison cloud at a visible surface cell so the overlay pass runs
    cx, cy = sim.world.width // 2, sim.world.height // 2
    sim.poison = {(cx, cy, sim.world.surface_z(cx, cy)): 12}
    viewer = LiveViewer(sim, max_steps=1)
    pygame.init()
    viewer._screen = pygame.display.set_mode(
        (sim.world.width * viewer.cell_size + 400, sim.world.height * viewer.cell_size + 40))
    viewer._load_fonts()
    cloud_before, step0 = dict(sim.poison), sim.step_count
    viewer._render_body()
    pygame.quit()
    assert sim.poison == cloud_before and sim.step_count == step0, \
        "the poison overlay must not mutate the sim (pure renderer)"


def test_sky_sign_renders_pure():
    """Revelation (SPEC_REVELATION R1): the night-sky sign inscription draws without crashing and mutates
    nothing — a pure read of sim.sky_sign."""
    import pygame
    sim = make_sim()
    for _ in range(10):
        sim.step()
    sim.sky_sign = {'kind': 'edict', 'since': sim.step_count, 'decoded_by': set()}
    viewer = LiveViewer(sim, max_steps=1)
    pygame.init()
    viewer._screen = pygame.display.set_mode(
        (sim.world.width * viewer.cell_size + 400, sim.world.height * viewer.cell_size + 40))
    viewer._load_fonts()
    sign_before, step0 = dict(sim.sky_sign), sim.step_count
    viewer._render_body()
    pygame.quit()
    assert sim.sky_sign == sign_before and sim.step_count == step0, \
        "the night-sky sign overlay must not mutate the sim (pure renderer)"


def test_siege_tower_renders_pure():
    """Siege (SPEC_SIEGE SE2): the siege-tower overlay draws without crashing and mutates nothing — a pure
    read of sim.siege_towers."""
    import pygame
    sim = make_sim()
    for _ in range(10):
        sim.step()
    cx, cy = sim.world.width // 2, sim.world.height // 2
    sim.siege_towers = [{'owner': sim.colonies[0].colony_id,
                         'pos': (cx, cy, sim.world.surface_z(cx, cy)),
                         'target': (cx + 5, cy, sim.world.surface_z(cx + 5, cy))}]
    viewer = LiveViewer(sim, max_steps=1)
    pygame.init()
    viewer._screen = pygame.display.set_mode(
        (sim.world.width * viewer.cell_size + 400, sim.world.height * viewer.cell_size + 40))
    viewer._load_fonts()
    towers_before, step0 = [dict(t) for t in sim.siege_towers], sim.step_count
    viewer._render_body()
    pygame.quit()
    assert sim.siege_towers == towers_before and sim.step_count == step0, \
        "the siege-tower overlay must not mutate the sim (pure renderer)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all live view tests passed")


# ---- R32-R34: look cursor, inspect + follow, legend ----

def test_legend_covers_every_glyph_and_species():
    from live_view import (BEAST_GLYPHS, GLYPHS, build_legend_entries)
    from sandkings import VoxelType
    joined = "\n".join(t for t, _c in build_legend_entries())
    for value, glyph in GLYPHS.items():
        if value == VoxelType.AIR.value:
            continue
        assert glyph in joined, f"glyph {glyph!r} missing from legend"
    for species in BEAST_GLYPHS:
        assert species in joined, f"{species} missing from legend"
    assert "fire" in joined and "armored" in joined


def test_legend_layout_never_cuts_off_vertically():
    """R34 regression: the legend column-wraps so NO entry renders past area_h.
    The old single-column layout placed row i at y=10+i*16 with no height bound,
    so once the entries exceeded the window height the bottom rows were cut off."""
    from live_view import (build_legend_entries, legend_layout,
                           LEGEND_TOP, LEGEND_LINE_H)
    entries = build_legend_entries()
    n = len(entries)
    # a window deliberately shorter than a single legend column would need
    area_w, area_h = 672, 400
    single_col_bottom = LEGEND_TOP + n * LEGEND_LINE_H
    assert single_col_bottom > area_h, (
        "test premise: the legend must overflow one column at this size "
        f"(needs {single_col_bottom}px, have {area_h}px)")
    positions = legend_layout(n, area_w, area_h)
    assert len(positions) == n, "every entry must get a position (none dropped)"
    for (x, y) in positions:
        assert LEGEND_TOP <= y < area_h, f"entry at y={y} is cut off (area_h={area_h})"
        assert 0 <= x < area_w, f"entry at x={x} is outside area_w={area_w}"
    # the fix must actually wrap into more than one column here
    assert len({x for x, _y in positions}) >= 2, "layout should use multiple columns"


def test_castle_voxel_has_distinct_glyph_and_color():
    """K5: a CASTLE voxel renders with its own glyph, legend name, and a color
    distinct from the generic reinforced tunnel wall — so a castle is
    recognizable, not indistinguishable brown wall."""
    from live_view import GLYPHS, VOXEL_LEGEND, build_voxel_palette
    from sandkings import VoxelType
    assert VoxelType.CASTLE.value in GLYPHS, "castle needs a glyph"
    assert VoxelType.CASTLE.value in VOXEL_LEGEND, "castle needs a legend name"
    pal = build_voxel_palette()
    castle_c = tuple(int(x) for x in pal[VoxelType.CASTLE.value])
    wall_c = tuple(int(x) for x in pal[VoxelType.TUNNEL_WALL.value])
    assert castle_c != (0, 0, 0), "castle needs a palette color"
    assert castle_c != wall_c, "castle must look different from a tunnel wall"


def test_manager_layout_never_cuts_off_vertically():
    """Regression (same class as the legend R34): the manager stat block
    column-wraps via legend_layout so NO row renders past area_h. The old
    _render_manager placed row i at y=10+i*17 with no height bound, so a tall
    colony block (35-anchor concept table + soldiers + decision log) ran off the
    bottom and cut off."""
    from live_view import build_manager_entries, legend_layout
    sim = make_sim()
    for _ in range(4):  # let instincts/soldiers populate the block
        sim.step()
    cid = sim.colonies[0].colony_id
    entries = build_manager_entries(sim, cid)
    n = len(entries)
    line_h, top, left = 17, 10, 14        # the values _render_manager passes
    area_w, area_h = 672, 400             # a window too short for one column
    single_col_bottom = top + n * line_h
    assert single_col_bottom > area_h, (
        "test premise: the manager block must overflow one column at this size "
        f"(needs {single_col_bottom}px, have {area_h}px)")
    positions = legend_layout(n, area_w, area_h, line_h=line_h, top=top, left=left)
    assert len(positions) == n, "every entry must get a position (none dropped)"
    for (x, y) in positions:
        assert top <= y < area_h, f"manager row at y={y} is cut off (area_h={area_h})"
        assert 0 <= x < area_w, f"manager row at x={x} is outside area_w={area_w}"
    assert len({x for x, _y in positions}) >= 2, "layout should wrap into columns"


def test_column_inhabitants_orders_by_height_and_inspect_reads():
    from live_view import (build_inspect_entries, column_inhabitants,
                           target_alive)
    from sandkings import Beast, SandKing, UnitType
    sim = make_sim()
    colony = sim.colonies[0]
    low = SandKing(colony.colony_id, (5, 5, 1), UnitType.WORKER)
    high = SandKing(colony.colony_id, (5, 5, 3), UnitType.SOLDIER)
    colony.units += [low, high]
    beast = Beast('spider', (5, 5, 2), 25, 8, 20, 2)
    sim._fauna().append(beast)
    targets = column_inhabitants(sim, 5, 5)
    assert [t[0] for t in targets] == ['unit', 'beast', 'unit']
    assert targets[0][1] is high, "highest z first"
    text = "\n".join(t for t, _c in build_inspect_entries(sim, ('unit', high)))
    assert "HP 20/20" in text and "House" in text and "thinks:" in text
    text = "\n".join(t for t, _c in build_inspect_entries(sim, ('beast', beast)))
    assert "SPIDER" in text and "bounty" in text
    colony.remove_unit(high)
    assert not target_alive(sim, ('unit', high))
    text = "\n".join(t for t, _c in build_inspect_entries(sim, ('unit', high)))
    assert "has fallen" in text


def test_inspect_maw_shows_posture_and_traits():
    from live_view import build_inspect_entries
    sim = make_sim()
    colony = sim.colonies[0]
    text = "\n".join(t for t, _c in build_inspect_entries(sim, ('maw', colony)))
    assert "MAW of House" in text and "posture" in text
    assert "agg" in text and "pla" in text, "genome traits shown"


def test_look_keys_cursor_select_follow():
    import pygame
    from sandkings import SandKing, UnitType
    sim = make_sim()
    colony = sim.colonies[0]
    viewer = LiveViewer(sim, max_steps=1)
    viewer._handle_event(make_keydown(pygame.K_i))
    assert viewer.look_mode
    start = viewer.cursor
    viewer._handle_event(make_keydown(pygame.K_RIGHT))
    viewer._handle_event(make_keydown(pygame.K_UP))
    assert viewer.cursor == (start[0] + 1, max(0, start[1] - 1))
    for _ in range(100):  # clamped at the map edge
        viewer._handle_event(make_keydown(pygame.K_LEFT))
    assert viewer.cursor[0] == 0
    unit = SandKing(colony.colony_id, (0, viewer.cursor[1], 2), UnitType.WORKER)
    colony.units.append(unit)
    viewer._handle_event(make_keydown(pygame.K_v))
    assert viewer.inspected == ('unit', unit)
    viewer._handle_event(make_keydown(pygame.K_f))
    assert viewer.follow
    viewer._handle_event(make_keydown(pygame.K_RIGHT))
    assert not viewer.follow, "steering the cursor breaks the leash"
    viewer._handle_event(make_keydown(pygame.K_i))
    assert not viewer.look_mode and viewer.inspected is None


def test_legend_key_exclusive_with_manager():
    import pygame
    viewer = LiveViewer(make_sim(), max_steps=1)
    viewer._handle_event(make_keydown(pygame.K_l))
    assert viewer.legend_open
    viewer._handle_event(make_keydown(pygame.K_m))
    assert viewer.manager_open and not viewer.legend_open
    viewer._handle_event(make_keydown(pygame.K_l))
    assert viewer.legend_open and not viewer.manager_open


# ---- R36: isometric sprite view ----

def test_sprite_forge_covers_every_voxel_and_species():
    import pygame
    pygame.init()
    from iso_sprites import forge_beast, forge_bug, forge_cube, forge_maw
    from live_view import BEAST_GLYPHS
    from sandkings import VoxelType
    for voxel in VoxelType:
        if voxel == VoxelType.AIR:
            continue
        surf = forge_cube(voxel.value, 12, 6)
        assert surf.get_size() == (12, 12), voxel
    for species in BEAST_GLYPHS:
        assert forge_beast(species, 12).get_width() > 0, species
    for caste in ("worker", "soldier", "scout"):
        assert forge_bug(caste, (255, 0, 0), 12).get_width() > 0
    assert forge_maw((255, 165, 0), 12).get_width() > 0
    # deterministic + cached: same key returns the same surface object
    from iso_sprites import forge_cube as fc
    assert fc(VoxelType.SAND.value, 12, 6) is fc(VoxelType.SAND.value, 12, 6)


def test_iso_metrics_fit_and_projection():
    from live_view import iso_metrics, iso_project
    w, h, depth = 80, 40, 20
    area_w, area_h = 960, 480
    tw, th, zs, ox, oy = iso_metrics(w, h, depth, area_w, area_h)
    assert tw >= 4 and th == tw // 2 and zs == th
    assert (w + h) * tw // 2 <= area_w, "projection fits horizontally"
    assert (w + h) * tw // 4 + depth * tw // 4 + tw <= area_h, "and vertically"
    # every corner column lands on-canvas at z=0
    for (x, y) in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        sx, sy = iso_project(x, y, 0, tw, zs, ox, oy)
        assert 0 <= sx <= area_w and 0 <= sy <= area_h + tw, (x, y, sx, sy)
    # +z rises on screen; +x runs down-right; +y down-left
    sx0, sy0 = iso_project(5, 5, 0, tw, zs, ox, oy)
    assert iso_project(5, 5, 3, tw, zs, ox, oy)[1] < sy0
    assert iso_project(6, 5, 0, tw, zs, ox, oy)[0] > sx0
    assert iso_project(5, 6, 0, tw, zs, ox, oy)[0] < sx0


def test_tab_cycles_three_view_modes():
    import pygame
    viewer = LiveViewer(make_sim(), max_steps=1)
    assert viewer.view_mode == ViewMode.TOPDOWN
    viewer._handle_event(make_keydown(pygame.K_TAB))
    assert viewer.view_mode == ViewMode.SLICE
    viewer._handle_event(make_keydown(pygame.K_TAB))
    assert viewer.view_mode == ViewMode.ISO
    viewer._handle_event(make_keydown(pygame.K_TAB))
    assert viewer.view_mode == ViewMode.TOPDOWN


def test_iso_full_loop_headless():
    sim = make_sim()
    viewer = LiveViewer(sim, max_steps=6, steps_per_second=60.0)
    viewer.view_mode = ViewMode.ISO
    viewer.look_mode = True  # exercise the iso cursor path too
    viewer.run()
    assert viewer.steps_done == 6, "ISO view runs the loop to completion"


def test_breakout_target_rules():
    """W2 FIX 3 (relocated from test_breakout to keep that suite pygame-free):
    _breakout_target — inspected unit/maw -> its colony, else the living colony
    whose maw is nearest the cursor, else None. Lives here because _breakout_target
    is a live_view helper and this file already imports pygame (test_dashboard's
    pygame-free invariant sorts before test_breakout but after nothing here)."""
    from live_view import _breakout_target
    from sandkings import SandKing, UnitType, Beast
    sim = make_sim()
    c0, c1 = sim.colonies[0], sim.colonies[1]

    class StubView:
        def __init__(self, sim, cursor, inspected):
            self.sim, self.cursor, self.inspected = sim, cursor, inspected

    # (a) inspected unit -> its colony
    unit = SandKing(c0.colony_id, (5, 5, 2), UnitType.WORKER)
    assert _breakout_target(StubView(sim, (8, 8), ('unit', unit))) is c0

    # (b) inspected beast (no colony_id) -> falls through to nearest-cursor colony
    beast = Beast('spider', (10, 10, 3), 25, 8, 20, 2)
    tgt = _breakout_target(StubView(sim, (8, 8), ('beast', beast)))
    assert tgt is not None and tgt in sim.colonies

    # (c) no inspection, cursor near a maw -> nearest living colony
    c1.maw.position = (8, 9, 2)
    tgt = _breakout_target(StubView(sim, (8, 8), None))
    assert tgt is not None and tgt.is_alive()

    # (d) all colonies dead -> None
    for c in sim.colonies:
        c.maw.alive = False
    assert _breakout_target(StubView(sim, (8, 8), None)) is None
