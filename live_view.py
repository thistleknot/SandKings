"""Live pygame viewer for the Sand Kings simulation.

Renders the voxel terrarium in real time with a stats HUD, in two view
modes: TOPDOWN (Dwarf-Fortress-style look-down with depth shading, the
default) and SLICE (single-z cross-section). Governed by SPEC_LIVE_VIEW.md.

Preconditions: a constructed SandKingsSimulation; pygame installed. Runs
headlessly under SDL_VIDEODRIVER=dummy. Failure modes: pygame init failure
raises; the sim stepping is clamped per frame so slow (neural) steps degrade
speed instead of freezing the UI.
"""

from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pygame

from sandkings import (MAW_MAX_HEALTH, Colony, PheromoneType, SandKingsSimulation,
                       UnitType, VoxelType, VoxelWorld)


class ViewMode(Enum):
    TOPDOWN = 0   # DF-style: look down z through open space, depth-shaded
    SLICE = 1     # single-z cross-section


class RenderStyle(Enum):
    GLYPH = 0     # DF-style character grid (default; spec R18)
    BLOCKS = 1    # plain colored rects

HUD_WIDTH = 320
DEFAULT_CELL_SIZE = 12
DEFAULT_STEPS_PER_SECOND = 5.0
SPS_MIN, SPS_MAX = 0.5, 60.0
MAX_STEPS_PER_FRAME = 10
RETREAT_BORDER_COLOR = (255, 0, 255)
RETREAT_FILL_FACTOR = 0.4
MAX_WINDOW = (1600, 900)
TERRITORY_TINT = 0.3  # matches Visualizer.render_z_slice owned-air factor
DEPTH_SHADE_FACTOR = 0.85  # brightness multiplier per z-level of depth
DEPTH_SHADE_MIN = 0.3      # floor so deep terrain stays legible
VOID_COLOR = (10, 10, 12)  # column with no terrain down to z=0
MAW_COLOR = (255, 255, 0)
HUD_BG = (12, 12, 16)
HUD_FG = (220, 220, 220)
EVENT_LINES = 4            # drama-feed entries shown in the HUD (spec R15)
GLYPH_BG_DIM = 0.45        # background dimming under glyphs (spec R18)
GLYPH_MIN_CELL = 8         # px; below this glyphs are illegible -> BLOCKS
GLYPHS = {                 # DF-style terrain glyphs (spec R18)
    VoxelType.AIR.value: " ",
    VoxelType.SAND.value: "░",
    VoxelType.STONE.value: "▓",
    VoxelType.GLASS.value: "#",
    VoxelType.FOOD.value: "•",
    VoxelType.CORPSE.value: "%",
    VoxelType.TUNNEL_WALL.value: "≡",
}
UNIT_GLYPHS = {UnitType.WORKER: "w", UnitType.SOLDIER: "s", UnitType.SCOUT: "c"}
MAW_GLYPH = "Ω"
EVENT_TINTS = (            # substring -> HUD color (spec R19)
    ("Keeper", (120, 210, 120)),
    ("besieges", (255, 165, 60)),
    ("fallen", (255, 85, 85)),
    ("arrives", (90, 200, 255)),
)
PHEROMONE_OVERLAYS = (None, PheromoneType.FOOD_TRAIL, PheromoneType.TERRITORY,
                      PheromoneType.DANGER)  # P-key cycle (spec R17)
PHEROMONE_BRIGHTNESS = 140  # additive glow ceiling per channel


def build_voxel_palette() -> np.ndarray:
    """(256, 3) uint8 LUT mirroring Visualizer.render_z_slice colors exactly."""
    palette = np.zeros((256, 3), dtype=np.uint8)
    palette[VoxelType.AIR.value] = (20, 20, 20)
    palette[VoxelType.SAND.value] = (194, 178, 128)
    palette[VoxelType.STONE.value] = (50, 50, 50)
    palette[VoxelType.GLASS.value] = (100, 100, 100)
    palette[VoxelType.FOOD.value] = (0, 255, 0)
    palette[VoxelType.CORPSE.value] = (128, 0, 0)
    palette[VoxelType.TUNNEL_WALL.value] = (139, 90, 43)
    return palette


def slice_color_array(world: VoxelWorld, colonies: List[Colony], z_level: int) -> np.ndarray:
    """(w, h, 3) uint8 color array for one z-slice: voxel LUT + territory tint."""
    voxels = world.voxels[:, :, z_level]
    ownership = world.ownership[:, :, z_level]
    colors = build_voxel_palette()[voxels]

    owned_air = (voxels == VoxelType.AIR.value) & (ownership >= 0)
    for colony in colonies:
        mask = owned_air & (ownership == colony.colony_id)
        if mask.any():
            tint = tuple(int(c * TERRITORY_TINT) for c in colony.color)
            colors[mask] = tint
    return colors


def depth_shade(delta: int) -> float:
    """Brightness multiplier for terrain `delta` z-levels below the view level."""
    return max(DEPTH_SHADE_MIN, DEPTH_SHADE_FACTOR ** delta)


def topdown_cells(world: VoxelWorld, z_level: int):
    """Per-column look-down data at z_level (spec R12/R18).

    Returns (found_voxels, depth_below, has_terrain, ownership): the first
    non-AIR voxel type per column, how far below z_level it sits, whether
    any terrain exists down to z=0, and the ownership at the found voxel.
    """
    sub_voxels = world.voxels[:, :, :z_level + 1]
    nonair_from_top = (sub_voxels != VoxelType.AIR.value)[:, :, ::-1]
    depth_below = np.argmax(nonair_from_top, axis=2)      # 0 = terrain at z_level
    has_terrain = nonair_from_top.any(axis=2)
    z_found = z_level - depth_below
    found_voxels = np.take_along_axis(sub_voxels, z_found[..., None], axis=2)[..., 0]
    ownership = np.take_along_axis(world.ownership[:, :, :z_level + 1],
                                   z_found[..., None], axis=2)[..., 0]
    return found_voxels, depth_below, has_terrain, ownership


def topdown_color_array(world: VoxelWorld, colonies: List[Colony], z_level: int) -> np.ndarray:
    """(w, h, 3) uint8 DF-style top-down view at z_level (spec R12).

    Per (x, y) column: the first non-AIR voxel at or below z_level, shaded
    darker with depth; owned surface voxels blend TERRITORY_TINT of the
    colony color; bottomless columns render VOID_COLOR.
    """
    found_voxels, depth_below, has_terrain, ownership = topdown_cells(world, z_level)
    colors = build_voxel_palette()[found_voxels].astype(np.float32)
    colors *= np.maximum(DEPTH_SHADE_MIN, DEPTH_SHADE_FACTOR ** depth_below)[..., None]

    for colony in colonies:
        mask = has_terrain & (ownership == colony.colony_id)
        if mask.any():
            tint = np.array(colony.color, dtype=np.float32)
            colors[mask] = (1 - TERRITORY_TINT) * colors[mask] + TERRITORY_TINT * tint

    colors[~has_terrain] = VOID_COLOR
    return colors.astype(np.uint8)


def unit_visible_depth(world: VoxelWorld, position: Tuple[int, int, int],
                       z_level: int) -> Optional[int]:
    """Depth below z_level at which a unit is visible top-down (spec R13).

    None when the unit is above z_level or occluded by non-AIR voxels in
    its column between the unit and the view level.
    """
    x, y, z = position
    if z > z_level:
        return None
    if not np.all(world.voxels[x, y, z + 1:z_level + 1] == VoxelType.AIR.value):
        return None
    return z_level - z


def pheromone_overlay_array(pheromones, colonies: List[Colony], z_level: int,
                            ptype: PheromoneType) -> np.ndarray:
    """(w, h, 3) uint8 additive glow of one pheromone type at a z-slice.

    Per cell, each colony contributes its color scaled by trail intensity
    (clipped to [0, 1]); contributions are max-combined so overlapping
    territories stay readable.
    """
    w, h = pheromones.trails.shape[0], pheromones.trails.shape[1]
    overlay = np.zeros((w, h, 3), dtype=np.float32)
    for colony in colonies:
        intensity = np.clip(
            pheromones.trails[:, :, z_level, colony.colony_id, ptype.value], 0.0, 1.0)
        glow = intensity[..., None] * (np.array(colony.color, dtype=np.float32)
                                       / 255.0) * PHEROMONE_BRIGHTNESS
        overlay = np.maximum(overlay, glow)
    return overlay.astype(np.uint8)


def storm_haze_array(shape_wh: Tuple[int, int]) -> np.ndarray:
    """(w, h, 3) uint8 flickering sand speckle for active storms (spec T12)."""
    w, h = shape_wh
    speckle = (np.random.random((w, h, 1)) > 0.55).astype(np.float32)
    sand = np.array((194, 178, 128), dtype=np.float32) * 0.35
    return (speckle * sand).astype(np.uint8)


def unit_draw_color(colony_color: Tuple[int, int, int],
                    retreating: bool) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """(fill, border) for a unit marker; retreating units dim + magenta border."""
    if retreating:
        fill = tuple(int(c * RETREAT_FILL_FACTOR) for c in colony_color)
        return fill, RETREAT_BORDER_COLOR
    r, g, b = colony_color
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    border = (0, 0, 0) if luminance >= 128 else (255, 255, 255)
    return tuple(colony_color), border


def hud_text_color(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """A colony color made legible on the dark HUD panel (spec R19)."""
    r, g, b = color
    if 0.299 * r + 0.587 * g + 0.114 * b < 60:
        return (150, 150, 150)
    return color


def event_tint(message: str) -> Tuple[int, int, int]:
    """HUD color for a drama-feed message (spec R19)."""
    for needle, color in EVENT_TINTS:
        if needle in message:
            return color
    return HUD_FG


def hp_bar(fraction: float, width: int = 8) -> str:
    """Text health bar like [███░░░░░]."""
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def build_hud_entries(sim: SandKingsSimulation, sps: float, paused: bool,
                      z_level: int, capturing: bool,
                      view_mode: ViewMode = ViewMode.TOPDOWN,
                      overlay: Optional[PheromoneType] = None
                      ) -> List[Tuple[str, Tuple[int, int, int]]]:
    """HUD content as (text, color) pairs: state, colonies, drama feed (R19)."""
    entries = [
        (f"Step {sim.step_count}", HUD_FG),
        (f"{'PAUSED' if paused else 'RUNNING'} @ {sps:.1f} steps/s", HUD_FG),
        (f"{view_mode.name}  z={z_level}/{sim.world.depth - 1}", HUD_FG),
        (f"Capture: {'ON' if capturing else 'off'}"
         + (f"  Pher: {overlay.name}" if overlay else ""), HUD_FG),
        ("", HUD_FG),
    ]
    for colony in sim.colonies:
        color = hud_text_color(colony.color)
        if not colony.is_alive():
            due = getattr(sim, 'pending_respawns', {}).get(colony.colony_id)
            suffix = (f" (respawn in {max(0, due - sim.step_count)})"
                      if due is not None else "")
            entries.append((f"Colony {colony.colony_id}: DEAD{suffix}", (140, 60, 60)))
            continue
        castes = {t: 0 for t in UnitType}
        retreating = 0
        for unit in colony.units:
            castes[unit.unit_type] += 1
            if unit.retreating:
                retreating += 1
        war = " [WAR]" if getattr(colony, 'at_war', False) else ""
        entries.append((f"Colony {colony.colony_id}{war}", color))
        entries.append((f"  W:{castes[UnitType.WORKER]} S:{castes[UnitType.SOLDIER]}"
                        f" Sc:{castes[UnitType.SCOUT]} retreat:{retreating}", color))
        maw_line = f"  food:{colony.maw.food_stored:.0f} maw:{colony.maw.health:.0f}"
        hp_frac = colony.maw.health / MAW_MAX_HEALTH
        if hp_frac < 1.0:
            maw_line += f" {hp_bar(hp_frac)}"
        entries.append((maw_line, color))
    events = list(getattr(sim, 'events', []))[-EVENT_LINES:]
    if events:
        entries.append(("", HUD_FG))
        for step, message in events:
            entries.append((f"[{step}] {message}"[:38], event_tint(message)))
    for help_line in ("", "SPACE pause  S step", "+/- speed  </> or UP/DN z",
                      "TAB view  P pheromones  R style", "G capture  ESC quit"):
        entries.append((help_line, (140, 140, 150)))
    return entries


def build_hud_lines(sim: SandKingsSimulation, sps: float, paused: bool,
                    z_level: int, capturing: bool,
                    view_mode: ViewMode = ViewMode.TOPDOWN,
                    overlay: Optional[PheromoneType] = None) -> List[str]:
    """Text-only projection of build_hud_entries (kept for callers/tests)."""
    return [text for text, _ in build_hud_entries(
        sim, sps, paused, z_level, capturing, view_mode, overlay)]


class StepPacer:
    """Fixed-timestep accumulator: wall-clock frame deltas -> owed sim steps.

    update() returns 0..MAX_STEPS_PER_FRAME; debt beyond the clamp is
    discarded so the UI never freezes (spec R6). Single steps are honored
    only while paused (spec R4).
    """

    def __init__(self, steps_per_second: float = DEFAULT_STEPS_PER_SECOND):
        self.steps_per_second = float(np.clip(steps_per_second, SPS_MIN, SPS_MAX))
        self._accumulator_ms = 0.0
        self._single_step_pending = False

    def update(self, dt_ms: float, paused: bool) -> int:
        if paused:
            self._accumulator_ms = 0.0
            if self._single_step_pending:
                self._single_step_pending = False
                return 1
            return 0
        self._single_step_pending = False
        self._accumulator_ms += dt_ms
        ms_per_step = 1000.0 / self.steps_per_second
        owed = int(self._accumulator_ms / ms_per_step)
        if owed > MAX_STEPS_PER_FRAME:
            self._accumulator_ms = 0.0
            return MAX_STEPS_PER_FRAME
        self._accumulator_ms -= owed * ms_per_step
        return owed

    def faster(self) -> None:
        self.steps_per_second = min(SPS_MAX, self.steps_per_second * 1.5)

    def slower(self) -> None:
        self.steps_per_second = max(SPS_MIN, self.steps_per_second / 1.5)

    def request_single_step(self) -> None:
        self._single_step_pending = True


class LiveViewer:
    """Owns the pygame window and event loop for one live run.

    run() blocks until the user quits or max_steps sim steps have executed;
    pygame.init/quit are bracketed inside run().
    """

    def __init__(self, sim: SandKingsSimulation, cell_size: int = DEFAULT_CELL_SIZE,
                 steps_per_second: float = DEFAULT_STEPS_PER_SECOND,
                 max_steps: Optional[int] = None):
        self.sim = sim
        w, h = sim.world.width, sim.world.height
        self.cell_size = max(2, min(cell_size,
                                    (MAX_WINDOW[0] - HUD_WIDTH) // w,
                                    MAX_WINDOW[1] // h))
        self.pacer = StepPacer(steps_per_second)
        self.max_steps = max_steps
        self.steps_done = 0
        self.paused = False
        self.view_mode = ViewMode.TOPDOWN
        self.z_level = sim.world.depth - 1  # surface view (spec R14)
        self.capturing = False
        self.overlay_index = 0  # index into PHEROMONE_OVERLAYS (spec R17)
        self.render_style = RenderStyle.GLYPH  # dazzle by default (spec R18)
        self.captured_frames: List[np.ndarray] = []
        self.running = False
        self._screen = None
        self._font = None
        self._cell_font = None
        self._maw_font = None
        self._glyph_cache: dict = {}  # (char, color, big) -> Surface

    def run(self) -> None:
        pygame.init()
        try:
            w, h = self.sim.world.width, self.sim.world.height
            size = (w * self.cell_size + HUD_WIDTH, max(h * self.cell_size, 400))
            self._screen = pygame.display.set_mode(size)
            pygame.display.set_caption("Sand Kings — Live Terrarium")
            self._font = pygame.font.SysFont("consolas,courier", 14)
            self._cell_font = pygame.font.SysFont("consolas,couriernew",
                                                  self.cell_size + 3, bold=True)
            self._maw_font = pygame.font.SysFont("consolas,couriernew",
                                                 self.cell_size * 2, bold=True)
            clock = pygame.time.Clock()
            self.running = True

            while self.running:
                dt = clock.tick(60)
                for event in pygame.event.get():
                    self._handle_event(event)

                owed = self.pacer.update(dt, self.paused)
                stepped = False
                for _ in range(owed):
                    self.sim.step()
                    self.steps_done += 1
                    stepped = True
                    if self.max_steps is not None and self.steps_done >= self.max_steps:
                        self.running = False
                        break

                self._render()
                if self.capturing and stepped:
                    self._capture_frame()

            assert self.max_steps is None or self.steps_done <= self.max_steps
            self._save_capture()
        finally:
            pygame.quit()

    def _handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:
                self.running = False
            elif key == pygame.K_SPACE:
                self.paused = not self.paused
            elif key == pygame.K_s and self.paused:
                self.pacer.request_single_step()
            # DF-style z-navigation (spec R8a): '<' rises, '>' descends.
            # Must be checked before the speed branch, which shares , and .
            elif event.unicode == '<' or (key == pygame.K_COMMA and
                                          event.mod & (pygame.KMOD_CTRL | pygame.KMOD_SHIFT)):
                self.z_level = min(self.sim.world.depth - 1, self.z_level + 1)
            elif event.unicode == '>' or (key == pygame.K_PERIOD and
                                          event.mod & (pygame.KMOD_CTRL | pygame.KMOD_SHIFT)):
                self.z_level = max(0, self.z_level - 1)
            elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_PERIOD, pygame.K_KP_PLUS):
                self.pacer.faster()
            elif key in (pygame.K_MINUS, pygame.K_COMMA, pygame.K_KP_MINUS):
                self.pacer.slower()
            elif key == pygame.K_UP:
                self.z_level = min(self.sim.world.depth - 1, self.z_level + 1)
            elif key == pygame.K_DOWN:
                self.z_level = max(0, self.z_level - 1)
            elif key == pygame.K_TAB:
                self.view_mode = (ViewMode.SLICE if self.view_mode == ViewMode.TOPDOWN
                                  else ViewMode.TOPDOWN)
            elif key == pygame.K_g:
                self.capturing = not self.capturing
            elif key == pygame.K_p:
                self.overlay_index = (self.overlay_index + 1) % len(PHEROMONE_OVERLAYS)
            elif key == pygame.K_r:
                self.render_style = (RenderStyle.BLOCKS
                                     if self.render_style == RenderStyle.GLYPH
                                     else RenderStyle.GLYPH)

    def _glyph(self, char: str, color: Tuple[int, int, int],
               big: bool = False) -> "pygame.Surface":
        """Cached rendered glyph; the grid never re-renders text per frame (R18)."""
        key = (char, color, big)
        surface = self._glyph_cache.get(key)
        if surface is None:
            font = self._maw_font if big else self._cell_font
            surface = font.render(char, True, color)
            self._glyph_cache[key] = surface
        return surface

    def _blit_glyph(self, char: str, color: Tuple[int, int, int],
                    cx: int, cy: int, big: bool = False) -> None:
        """Blit a glyph centered on the cell at pixel (cx, cy)."""
        cell = self.cell_size
        span = cell * 2 if big else cell
        surface = self._glyph(char, color, big)
        self._screen.blit(surface, (cx + (span - surface.get_width()) // 2,
                                    cy + (span - surface.get_height()) // 2))

    def _render(self) -> None:
        cell = self.cell_size
        w, h = self.sim.world.width, self.sim.world.height
        glyph_mode = (self.render_style == RenderStyle.GLYPH
                      and cell >= GLYPH_MIN_CELL)

        topdown = self.view_mode == ViewMode.TOPDOWN
        if topdown:
            colors = topdown_color_array(self.sim.world, self.sim.colonies, self.z_level)
        else:
            colors = slice_color_array(self.sim.world, self.sim.colonies, self.z_level)

        base = (colors * GLYPH_BG_DIM).astype(np.uint8) if glyph_mode else colors
        surf = pygame.surfarray.make_surface(base)  # axis 0 = x, no transpose
        surf = pygame.transform.scale(surf, (w * cell, h * cell))
        self._screen.fill(HUD_BG)
        self._screen.blit(surf, (0, 0))

        if glyph_mode:
            if topdown:
                found_voxels, _, has_terrain, _ = topdown_cells(self.sim.world, self.z_level)
                cell_voxels = np.where(has_terrain, found_voxels, VoxelType.AIR.value)
            else:
                cell_voxels = self.sim.world.voxels[:, :, self.z_level]
            for x in range(w):
                col_voxels = cell_voxels[x]
                col_colors = colors[x]
                for y in range(h):
                    char = GLYPHS.get(int(col_voxels[y]), " ")
                    if char != " ":
                        self._blit_glyph(char, tuple(int(c) for c in col_colors[y]),
                                         x * cell, y * cell)

        overlay_type = PHEROMONE_OVERLAYS[self.overlay_index]
        if overlay_type is not None:
            glow = pheromone_overlay_array(self.sim.pheromones, self.sim.colonies,
                                           self.z_level, overlay_type)
            glow_surf = pygame.transform.scale(
                pygame.surfarray.make_surface(glow), (w * cell, h * cell))
            self._screen.blit(glow_surf, (0, 0), special_flags=pygame.BLEND_ADD)

        for colony in self.sim.colonies:
            for unit in colony.units:
                depth = self._visible_depth(unit.position)
                if depth is None:
                    continue
                ux, uy = unit.position[0], unit.position[1]
                fill, border = unit_draw_color(colony.color, unit.retreating)
                fill = tuple(int(c * depth_shade(depth)) for c in fill)
                if glyph_mode:
                    char = UNIT_GLYPHS.get(unit.unit_type, "?")
                    color = border if unit.retreating else hud_text_color(fill)
                    self._blit_glyph(char, color, ux * cell, uy * cell)
                else:
                    rect = pygame.Rect(ux * cell + 1, uy * cell + 1, cell - 2, cell - 2)
                    pygame.draw.rect(self._screen, fill, rect)
                    pygame.draw.rect(self._screen, border, rect, 1)
            if colony.is_alive():
                depth = self._visible_depth(colony.maw.position)
                if depth is not None:
                    mx, my = colony.maw.position[0], colony.maw.position[1]
                    fill = tuple(int(c * depth_shade(depth)) for c in MAW_COLOR)
                    rect = pygame.Rect(mx * cell - cell // 2, my * cell - cell // 2,
                                       cell * 2, cell * 2)
                    if glyph_mode:
                        self._blit_glyph(MAW_GLYPH, fill, rect.x, rect.y, big=True)
                    else:
                        pygame.draw.rect(self._screen, fill, rect)
                        pygame.draw.rect(self._screen, (0, 0, 0), rect, 2)
                    # Siege health bar (spec R16): only shown when damaged
                    hp_frac = colony.maw.health / MAW_MAX_HEALTH
                    if hp_frac < 1.0:
                        bar = pygame.Rect(rect.x, rect.y - 5, rect.width, 3)
                        pygame.draw.rect(self._screen, (80, 0, 0), bar)
                        fg = pygame.Rect(rect.x, rect.y - 5,
                                         max(1, int(rect.width * hp_frac)), 3)
                        pygame.draw.rect(self._screen,
                                         (int(255 * (1 - hp_frac)), int(220 * hp_frac), 0), fg)

        if getattr(self.sim, 'storm_until', 0) > self.sim.step_count:
            haze = pygame.transform.scale(
                pygame.surfarray.make_surface(storm_haze_array((w, h))),
                (w * cell, h * cell))
            self._screen.blit(haze, (0, 0), special_flags=pygame.BLEND_ADD)

        hud_x = w * cell + 12
        for i, (line, color) in enumerate(build_hud_entries(
                self.sim, self.pacer.steps_per_second,
                self.paused, self.z_level, self.capturing,
                self.view_mode, PHEROMONE_OVERLAYS[self.overlay_index])):
            if line:
                text = self._font.render(line, True, color)
                self._screen.blit(text, (hud_x, 10 + i * 18))

        pygame.display.flip()

    def _visible_depth(self, position: Tuple[int, int, int]) -> Optional[int]:
        """Depth an entity renders at in the active view mode, None if hidden.

        SLICE shows only exact-z matches at depth 0; TOPDOWN applies the
        R13 look-down visibility rule.
        """
        if self.view_mode == ViewMode.SLICE:
            return 0 if position[2] == self.z_level else None
        return unit_visible_depth(self.sim.world, position, self.z_level)

    def _capture_frame(self) -> None:
        frame = pygame.surfarray.array3d(self._screen).transpose(1, 0, 2)
        self.captured_frames.append(frame.copy())

    def _save_capture(self) -> None:
        if not self.captured_frames:
            return
        from PIL import Image
        images = [Image.fromarray(f, 'RGB') for f in self.captured_frames]
        images[0].save('sandkings_live.gif', save_all=True,
                       append_images=images[1:], duration=100, loop=0)
        print(f"Saved sandkings_live.gif ({len(images)} frames)")


def run_live(sim: SandKingsSimulation, max_steps: Optional[int] = None,
             steps_per_second: float = DEFAULT_STEPS_PER_SECOND) -> None:
    """Entry point from sandkings.main(): open the live window and block until done."""
    LiveViewer(sim, steps_per_second=steps_per_second, max_steps=max_steps).run()
