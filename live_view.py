"""Live pygame viewer for the Sand Kings simulation.

Renders the voxel terrarium in real time with a stats HUD, in two view
modes: TOPDOWN (Dwarf-Fortress-style look-down with depth shading, the
default) and SLICE (single-z cross-section). Governed by SPEC_LIVE_VIEW.md.

Preconditions: a constructed SandKingsSimulation; pygame installed. Runs
headlessly under SDL_VIDEODRIVER=dummy. Failure modes: pygame init failure
raises; the sim stepping is clamped per frame so slow (neural) steps degrade
speed instead of freezing the UI.
"""

import threading
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pygame

from sandkings import (MAW_MAX_HEALTH, Colony, PheromoneType, SandKingsSimulation,
                       UnitType, VoxelType, VoxelWorld, TERMINAL_MASTERY, breakout_progress)


class ViewMode(Enum):
    TOPDOWN = 0   # DF-style: look down z through open space, depth-shaded
    SLICE = 1     # single-z cross-section
    ISO = 2       # stonesense-style sprite view (R36)


class RenderStyle(Enum):
    GLYPH = 0     # DF-style character grid (default; spec R18)
    BLOCKS = 1    # plain colored rects
    TILES = 2     # procedural top-down sprites (creatures LOOK like bugs/beasts; reuses the iso forge)

HUD_WIDTH = 320
DEFAULT_CELL_SIZE = 12
DEFAULT_STEPS_PER_SECOND = 5.0
SPS_MIN, SPS_MAX = 0.5, 60.0
MAX_STEPS_PER_FRAME = 10
MIRROR_MIN_MS = 700  # U8: min wall-ms between glyph-view mirror snapshots
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
LEGEND_SIDEBAR_W = 250     # px; the toggleable legend sidebar strip (overlays the map's left edge)
GLYPHS = {                 # DF-style terrain glyphs (spec R18/R22)
    VoxelType.AIR.value: " ",
    VoxelType.SAND.value: "░",
    VoxelType.STONE.value: "▓",
    VoxelType.GLASS.value: "#",
    VoxelType.FOOD.value: "•",
    VoxelType.CORPSE.value: "%",
    VoxelType.TUNNEL_WALL.value: "≡",
    VoxelType.TILLED.value: "~",
    VoxelType.CROP.value: ";",
    VoxelType.CROP_RIPE.value: "*",
    VoxelType.COPPER_ORE.value: "£",
    VoxelType.GOLD_ORE.value: "$",
    VoxelType.HULL.value: "Ξ",
    VoxelType.SALVAGE.value: "&",
    VoxelType.WOOD.value: "¶",
    VoxelType.WOOD_WALL.value: "|",
    VoxelType.WEB.value: "╳",          # spider silk — a net (distinct from the spider glyph)
    VoxelType.CASTLE.value: "Π",       # stone castle / gatehouse (K5)
    VoxelType.WATER.value: "≈",        # standing water (HYDRO flow sim)
    VoxelType.SHRUB.value: "♣",        # growing berry bush — not yet food (SPEC_FLORA)
    VoxelType.SHRUB_RIPE.value: "♠",   # ripe berries — forageable food
}
FIRE_GLYPH = "^"                    # burning-cell overlay (T46)
FIRE_COLOR = (255, 120, 0)
POISON_GLYPH = "§"                  # poison-cloud overlay (SPEC_CHEMICAL_WAR CW1)
POISON_COLOR = (120, 210, 60)       # sickly chemical green
# Fauna (T48): shape-distinct glyphs, colored by DANGER CLASS so threat is pre-attentive.
BEAST_GLYPHS = {
    'spider': "Ж", 'scorpion': "‡", 'snake': "§", 'anteater': "▼", 'bird': "⌃",
    'hornets': "∴", 'rabbit': "∩", 'squirrel': "∪", 'rodent': "◦",
    # smaller / keeper-introduced fauna (previously fell through to "?")
    'cricket': "λ", 'ant': "α", 'fly': "×", 'small_spider': "⋆", 'mouse': "ω",
    'cat': "Ψ", 'beetle': "⊙", 'bee': "∵", 'guppy': "»",
}
BEAST_PREDATORS = frozenset(('spider', 'scorpion', 'snake', 'anteater', 'bird', 'hornets', 'cat', 'guppy'))
PREDATOR_COLOR = (235, 95, 70)      # warm red — a threat
NEUTRAL_BEAST_COLOR = (150, 175, 150)  # cool grey-green — harmless
TAMED_BEAST_COLOR = (120, 220, 160)  # bright friendly green — a domesticated beast (SPEC_DOMESTICATION)
BEAST_COLOR = (200, 80, 220)        # legacy violet (fallback / BLOCKS mode)
# A World Alive: the pond shoal + rafts, drawn by the renderer from sim scalars/flags (no sim state)
FISH_GLYPHS = ("›", "‹", "◦")       # a darting shoal over the oasis/water (count ∝ guppy_pop)
FISH_COLOR = (150, 200, 235)        # silvery pond blue
FISH_MAX = 16                       # cap on drawn fish (never crowd the pond)
FISH_PER = 9                        # guppy_pop units per drawn fish
BOAT_GLYPH = "≈"                    # a raft hull drawn under a rafted unit (spawn rides on top)
BOAT_COLOR = (170, 110, 50)         # timber brown
CARVE_COLORS = {                    # F4: sentiment carving colours by glyph
    '♥': (255, 235, 140),  # devout - gold
    '◦': (170, 170, 180),  # wary - pale grey
    '☠': (230, 70, 60),    # hateful - red
    '⌂': (150, 180, 255),  # machine-carved - blue
    '☀': (255, 210, 90),   # AW2 bounty - warm sun
    '☁': (170, 185, 200),  # AW2 lean - pale cloud
    '☈': (120, 160, 235),  # AW2 dread - storm
}
COPPER_TINT = (184, 115, 51)  # armored soldier letters (R22)
# Units: solid, shape-distinct silhouettes (circle / diamond / triangle) that POP as "figure" in bright
# colony color against the dimmed terrain "ground" — far more legible than the old w/s/c letters.
UNIT_GLYPHS = {UnitType.WORKER: "●", UnitType.SOLDIER: "◆", UnitType.SCOUT: "▲"}
MAW_GLYPH = "Ω"
TERRAIN_GLYPH_DIM = 0.6            # mute terrain glyph colors so creatures (figure) stand out (ground)
EVENT_TINTS = (            # substring -> HUD color (spec R19/R24)
    ("Keeper", (120, 210, 120)),
    ("besieges", (255, 165, 60)),
    ("fallen", (255, 85, 85)),
    ("arrives", (90, 200, 255)),
    ("season begins", (200, 190, 120)),
    ("strikes", (255, 208, 0)),
    ("razes", (255, 120, 60)),
    ("harvest", (170, 220, 90)),
    ("sows", (120, 200, 90)),
    ("frost", (150, 190, 230)),
    ("oasis", (80, 200, 170)),
    ("shoal", (120, 200, 235)),        # guppy pond (SPEC_GUPPIES)
    ("guppies", (120, 200, 235)),
    ("crickets", (200, 210, 120)),     # cricket swarm (SPEC_FOOD_WEB)
    ("cricket swarm", (200, 210, 120)),
    ("snare", (210, 190, 150)),        # snares / weirs
    ("chirp again", (200, 210, 120)),
    ("war-drums", (255, 100, 80)),     # maw strategy shifts (learned personality)
    ("burrows", (180, 150, 110)),
    ("across the sands", (150, 210, 120)),
    ("maw learns", (180, 170, 230)),
    ("betrays", (255, 60, 120)),
    ("truce", (120, 220, 120)),
    ("tribute", (230, 200, 90)),
    ("envoy", (230, 200, 90)),
    ("coalition", (100, 200, 255)),
    ("raids", (255, 140, 60)),
    ("seethes", (150, 150, 160)),
    ("fells", (34, 139, 34)),
    ("palisades", (139, 105, 20)),
    ("torch", (255, 120, 0)),
    ("Wildfire", (255, 80, 0)),
    ("Lightning", (255, 240, 120)),
    ("ram smashes", (255, 165, 60)),
    ("slain", (200, 80, 220)),
    ("incursion", (200, 80, 220)),
    ("Spiders", (200, 80, 220)),
    ("rabbit", (200, 80, 220)),
    ("squirrel", (200, 80, 220)),
    ("shadow wheels", (200, 80, 220)),
    ("Rodents", (200, 80, 220)),
    ("Scorpions", (200, 80, 220)),
    ("beneath the sand", (200, 80, 220)),
    ("anteater", (200, 80, 220)),
    ("too strange", (200, 80, 220)),
    ("dream", (150, 180, 255)),
    ("flash flood", (90, 140, 255)),
    ("floodwaters", (90, 140, 255)),
    ("Hail", (235, 235, 245)),
    ("hail relents", (235, 235, 245)),
    ("frost settles", (170, 210, 255)),
    ("blood feud", (255, 60, 120)),
    ("will be remembered", (230, 210, 140)),
    ("rises (", (230, 210, 140)),
    ("keeper's hand", (255, 215, 0)),
    ("withholds", (255, 80, 80)),
    ("rains of the keeper", (120, 210, 120)),
    ("worship", (255, 215, 0)),
    ("hateful", (255, 80, 80)),
    ("castle", (240, 240, 240)),
    ("pads across", (200, 80, 220)),
    ("grieving", (255, 80, 80)),
    ("gift", (255, 215, 0)),
    ("god-brain", (150, 180, 255)),
    ("probing the glass", (150, 180, 255)),
    ("no longer a wall", (255, 255, 255)),
    ("ascends", (255, 255, 255)),          # enlightenment ascension (economy arc)
    ("in bondage", (200, 80, 220)),        # a maw enslaves a rival's spawn
    ("kneel to", (200, 80, 220)),          # thralls convert to their captor
    ("turns the whip", (200, 80, 220)),    # bargain -> subjugate
    ("marches to annihilate", (255, 85, 85)),  # bargain -> annihilate
    ("turns to trade", (230, 200, 90)),    # bargain -> wage/trade (mercantile gold)
    ("contracts", (230, 200, 90)),         # a labor/goods/license contract opens
    ("breaks free", (150, 200, 150)),      # a thrall wins its freedom
    ("split open", (150, 180, 255)),
    ("Shade stage", (255, 255, 255)),
    ("turns on its god", (230, 60, 200)),
    ("hand will not move", (230, 60, 200)),
    ("blistering heat", (255, 140, 60)),   # AR3 arena temperature
    ("biting cold", (150, 200, 255)),
    ("easy prey to learn", (150, 200, 150)),
    ("deluge over the sands", (60, 140, 240)),   # HH2 the hand's water
    ("rain waters the sands", (110, 170, 240)),
    ("scatters seeds", (150, 200, 150)),
    ("lights a firecracker", (255, 120, 40)),    # arena firecracker disaster
    ("catapult hurls", (255, 160, 60)),          # TE11 siege
    ("SPEAKS", (255, 255, 255)),
    ("fall as noise", (150, 150, 160)),
    ("augments its mind", (150, 180, 255)),
    ("computes its fortunes", (150, 180, 255)),
    ("foresees", (150, 200, 200)),
    ("mints", (240, 210, 90)),
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
    palette[VoxelType.TILLED.value] = (110, 80, 50)
    palette[VoxelType.CROP.value] = (80, 160, 60)
    palette[VoxelType.CROP_RIPE.value] = (190, 220, 60)
    palette[VoxelType.COPPER_ORE.value] = (184, 115, 51)
    palette[VoxelType.GOLD_ORE.value] = (255, 208, 0)
    palette[VoxelType.HULL.value] = (120, 130, 150)
    palette[VoxelType.SALVAGE.value] = (170, 190, 210)
    palette[VoxelType.WOOD.value] = (34, 139, 34)
    palette[VoxelType.WOOD_WALL.value] = (139, 105, 20)
    palette[VoxelType.WEB.value] = (210, 210, 220)
    palette[VoxelType.CASTLE.value] = (200, 195, 210)   # pale stone monument (K5)
    palette[VoxelType.WATER.value] = (40, 90, 200)      # standing water (HYDRO)
    palette[VoxelType.SHRUB.value] = (60, 120, 55)      # growing berry bush (SPEC_FLORA)
    palette[VoxelType.SHRUB_RIPE.value] = (150, 40, 90)  # ripe berries — magenta pop
    return palette


def oasis_blend(world, colors: np.ndarray) -> np.ndarray:
    """Blend oasis-disc columns 35% toward teal (spec R23); both view modes."""
    from sandkings import OASIS_RADIUS
    w, h = world.width, world.height
    cx, cy = w // 2, h // 2
    xs, ys = np.meshgrid(np.arange(w), np.arange(h), indexing='ij')
    mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= OASIS_RADIUS ** 2
    teal = np.array((70, 160, 140), dtype=np.float32)
    blended = colors.astype(np.float32)
    blended[mask] = 0.65 * blended[mask] + 0.35 * teal
    return blended.astype(np.uint8)


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
    return oasis_blend(world, colors)


def depth_shade(delta: int) -> float:
    """Brightness multiplier for terrain `delta` z-levels below the view level."""
    return max(DEPTH_SHADE_MIN, DEPTH_SHADE_FACTOR ** delta)


def iso_metrics(w: int, h: int, depth: int, area_w: int,
                area_h: int) -> Tuple[int, int, int, int, int]:
    """R36: largest even tile width whose dimetric projection fits the
    map area; returns (tile_w, tile_h, z_step, origin_x, origin_y)."""
    tw = 4
    for cand in range(4, 65, 2):
        proj_w = (w + h) * cand // 2
        proj_h = (w + h) * cand // 4 + depth * cand // 4 + cand
        if proj_w <= area_w and proj_h <= area_h:
            tw = cand
        else:
            break
    th = tw // 2
    zs = th
    origin_x = (h - 1) * tw // 2   # keeps x=0..w-1, y=h-1 on-canvas
    origin_y = depth * zs          # room for the tallest cubes
    return tw, th, zs, origin_x, origin_y


def iso_project(x: int, y: int, z: int, tw: int, zs: int, ox: int,
                oy: int) -> Tuple[int, int]:
    """R36 dimetric transform: +x runs down-right, +y down-left, +z up."""
    th = tw // 2
    return (ox + (x - y) * (tw // 2),
            oy + (x + y) * (th // 2) - z * zs)


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

    # X-RAY: reveal subsurface tunnels (owned carved AIR below the surface) as a
    # dim ghost of the digging house's color, so the warren shows from above.
    vox = world.voxels
    # a genuine subsurface tunnel = owned carved AIR with SOLID ground above it
    # (excludes surface-owned air over the nest, so the X-ray shows warrens, not
    # territory).
    _solid = (vox != VoxelType.AIR.value) & (vox != VoxelType.WATER.value)
    _solid_above = np.zeros_like(_solid)
    _solid_above[:, :, :-1] = np.cumsum(_solid[:, :, ::-1], axis=2)[:, :, ::-1][:, :, 1:] > 0
    tunnel3d = (vox == VoxelType.AIR.value) & (world.ownership >= 0) & _solid_above
    has_tunnel = tunnel3d.any(axis=2)
    if has_tunnel.any():
        d = world.depth
        z_top = (d - 1) - np.argmax(tunnel3d[:, :, ::-1], axis=2)
        owner = np.take_along_axis(world.ownership, z_top[:, :, None], axis=2)[:, :, 0]
        for colony in colonies:
            m = has_tunnel & (owner == colony.colony_id) & has_terrain
            if m.any():
                # a clearly visible colony-tinted overlay over a column with a warren
                # beneath it (X-ray from above), not a faint ghost.
                ghost = np.array(colony.color, dtype=np.float32)
                colors[m] = 0.45 * colors[m] + 0.55 * ghost

    colors[~has_terrain] = VOID_COLOR
    return oasis_blend(world, colors.astype(np.uint8))


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
    """Text health bar like [====....] (full-height block glyphs overflow
    the HUD's 18px line box and bleed into neighboring lines)."""
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "[" + "=" * filled + "." * (width - filled) + "]"


def _breakout_target(view) -> Optional[Colony]:
    """BRK-C target rule: inspected unit/maw's colony, else the living
    colony whose maw is nearest the cursor (covers 'under the cursor'
    and the colony-0 degenerate). Never a beast (no colony_id)."""
    insp = view.inspected                      # ('unit'|'maw'|'beast', obj)
    if insp is not None and insp[0] in ('unit', 'maw'):
        cid = getattr(insp[1], 'colony_id', None)
        if cid is not None:
            c = view.sim._colony_by_id(cid)
            if c is not None and c.is_alive():
                return c
    living = [c for c in view.sim.colonies if c.is_alive()]
    if not living:
        return None
    cx, cy = view.cursor
    def _d2(c):
        mx, my, _ = c.maw.position
        return (mx - cx) ** 2 + (my - cy) ** 2
    return min(living, key=_d2)


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
    if callable(getattr(sim, 'season_index', None)):  # Round-1 sims (R23)
        season_tints = ((80, 200, 170), (120, 210, 120),
                        (200, 180, 110), (150, 190, 230))
        si = sim.season_index()
        from sandkings import SEASONS
        entries.insert(3, (f"Year {sim.year()} - {SEASONS[si]}"
                           f"  (dole {sim.dole_factor() * 100:.0f}%)",
                           season_tints[si]))
        holder = sim.oasis_holder()
        entries.insert(4, ("Oasis: " + (f"Colony {holder}" if holder is not None
                                        else "unclaimed"), (80, 200, 170)))
        if getattr(sim, 'guppy_pop', None) is not None:   # SPEC_GUPPIES pond readout
            gp = sim.guppy_pop
            entries.insert(5, (f"Pond: {gp:.0f} guppies, algae {getattr(sim, 'algae', 0):.0f}",
                               (120, 200, 235) if gp >= 20 else (230, 170, 90)))
        if getattr(sim, 'cricket_pop', None) is not None:  # SPEC_FOOD_WEB terrestrial guild
            cp = sim.cricket_pop
            entries.insert(6, (f"Swarm: {cp:.0f} crickets",
                               (200, 210, 120) if cp >= 15 else (170, 150, 110)))
        # BI6: the panel readout - the closed water budget and the daylight
        wl = getattr(sim, 'water_level', 0.6)
        sh = getattr(sim, 'sun_hours', 12)
        entries.insert(5, (f"Water {wl * 100:.0f}%   Sun {sh:.0f}h",
                           (90, 170, 230) if wl >= 0.35 else (230, 170, 90)))
        # W5: the weather line (nothing when clear)
        active = [(name, tint) for attr, name, tint in (
            ("storm_until", "sandstorm", (200, 180, 110)),
            ("hail_until", "hail", (235, 235, 245)),
            ("flood_until", "flash flood", (90, 140, 255)),
            ("cold_until", "killing frost", (170, 210, 255)),
            ("arena_heat_until", "HEAT WAVE", (255, 140, 60)),   # AR3
            ("arena_cold_until", "COLD WAVE", (150, 200, 255)),  # AR3
        ) if getattr(sim, attr, 0) > sim.step_count]
        if getattr(sim, 'kw_until', 0) > sim.step_count:  # HH2
            active.append(("deluge" if getattr(sim, 'kw_big', False)
                           else "rain", (90, 160, 255)))
        if active:
            entries.insert(5, ("Weather: " + ", ".join(n for n, _t in active),
                               active[0][1]))
        if getattr(sim, 'drought', False):  # K1: the withheld dole
            entries.insert(5, ("DROUGHT - the keeper withholds",
                               (255, 80, 80)))
        # PS2/PS5: the terrarium reaches back - and may bind the god
        if getattr(sim, 'keeper_bound', False):
            entries.insert(5, (f"BOUND - House {getattr(sim, 'keeper_bound_by', '?')}"
                               " holds your hand", (230, 60, 200)))
        elif hasattr(sim, 'keeper_influence_word'):
            word = sim.keeper_influence_word()
            if word:
                tint = ((200, 120, 255)
                        if getattr(sim, 'keeper_influence', 0.0) < 0
                        else (150, 220, 170))
                entries.insert(5, (f"You feel {word}", tint))
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
        diplomacy = getattr(sim, 'diplomacy', None)
        war = ""
        if getattr(colony, 'at_war', False):
            target = (diplomacy.war_target.get(colony.colony_id)
                      if diplomacy is not None else None)
            war = f" [WAR->{target}]" if target is not None else " [WAR]"
        marks = ""
        if diplomacy is not None:
            truced = [str(c.colony_id) for c in sim.colonies
                      if c.colony_id != colony.colony_id
                      and diplomacy.truce_active(colony.colony_id,
                                                 c.colony_id, sim.step_count)]
            allies = [str(c.colony_id) for c in sim.colonies
                      if c.colony_id != colony.colony_id
                      and diplomacy.ally(colony.colony_id, c.colony_id)]
            if truced:
                marks += " T:" + ",".join(truced)
            if allies:
                marks += " A:" + ",".join(allies)
        if getattr(colony, 'house', ''):
            from chronicle import house_label
            name = house_label(colony.house, getattr(colony, 'generation', 1))
            entries.append((f"{colony.colony_id}:{name}{war}{marks}"[:38],
                            color))
        else:
            entries.append((f"Colony {colony.colony_id}{war}{marks}", color))
        entries.append((f"  W:{castes[UnitType.WORKER]} S:{castes[UnitType.SOLDIER]}"
                        f" Sc:{castes[UnitType.SCOUT]} retreat:{retreating}", color))
        maw_line = f"  food:{colony.maw.food_stored:.0f} maw:{colony.maw.health:.0f}"
        hp_frac = colony.maw.health / MAW_MAX_HEALTH
        if hp_frac < 1.0:
            maw_line += f" {hp_bar(hp_frac)}"
        entries.append((maw_line, color))
        # BRK-B: breakout-proximity gauge (reuses hp_bar; skipped once breached).
        # Suppressed for pre-machine colonies with no pi (pure noise on every house).
        phase, frac, label = breakout_progress(colony)
        if not (phase == "nopi" and getattr(colony, 'machine_arc', 'none') == 'none'):
            if phase == "breached":
                gauge = "  BREACHED"
            elif phase == "nopi":
                gauge = "  breakout: no pi"
            elif phase == "unlocking":
                gauge = f"  unlock:{hp_bar(frac)}"
            else:  # mastering
                uses = int(getattr(colony, 'terminal_uses', 0))
                gauge = f"  breach:{hp_bar(frac)} {uses}/{TERMINAL_MASTERY}"
            entries.append((gauge, color))
    events = list(getattr(sim, 'events', []))[-EVENT_LINES:]
    if events:
        entries.append(("", HUD_FG))
        sub = getattr(sim, '_substitute_houses', None)
        for step, message in events:
            shown = sub(message) if callable(sub) else message
            entries.append((f"[{step}] {shown}"[:38], event_tint(message)))
    for help_line in ("", "SPACE pause  S step", "+/- speed  </> or UP/DN z",
                      "TAB view  P pheromones  R style",
                      "I inspect (click too)  F follow  L legend",
                      "M manager  H saga  G capture  ESC quit",
                      "GIFTS: 1food 2crick 3ant 4spidr 5tech",
                      "       w rain  j seeds",
                      "WRATH: 6spidr 7scorp 8snake 9drgt 0cat",
                      "       [ cold  ] heat  d deluge  u firecrckr",
                      "       T speak  o open the door",
                      "NEUTRAL: n squirrel  b rabbit",
                      "PANEL: x/c water +/-  a/z sun +/-"):
        entries.append((help_line, (140, 140, 150)))
    return entries


def build_saga_entries(sim: SandKingsSimulation
                       ) -> List[Tuple[str, Tuple[int, int, int]]]:
    """The saga screen (D5): the chronicle rendered as readable history.

    Rows are already house-substituted at write time; this just frames
    them by year and season. Pure: no pygame."""
    from chronicle import saga_rows
    from sandkings import SEASONS, SEASON_LENGTH, YEAR_LENGTH
    entries: List[Tuple[str, Tuple[int, int, int]]] = [
        ("== THE SAGA OF THE TERRARIUM ==", (230, 210, 140)), ("", HUD_FG)]
    rows = saga_rows(getattr(sim, 'chronicle', None) or [])
    if not rows:
        entries.append(("The chronicle is yet unwritten.", (140, 140, 150)))
    last_year = -1
    for step, text, salience in rows:
        year = step // YEAR_LENGTH
        if year != last_year:
            last_year = year
            entries.append((f"-- In the year {year + 1} --", (150, 150, 160)))
        season = SEASONS[(step // SEASON_LENGTH) % 4]
        color = event_tint(text) if salience >= 7 else (185, 185, 190)
        entries.append((f" {season:>6}: {text}"[:76], color))
    entries.append(("", HUD_FG))
    entries.append(("H close   E export saga   M manager", (140, 140, 150)))
    return entries


VOXEL_LEGEND = {  # R34: every non-AIR GLYPHS row gets a name
    VoxelType.SAND.value: "sand (tunnelable)",
    VoxelType.STONE.value: "stone substrate",
    VoxelType.GLASS.value: "terrarium glass",
    VoxelType.FOOD.value: "food",
    VoxelType.CORPSE.value: "corpse (edible)",
    VoxelType.TUNNEL_WALL.value: "reinforced tunnel wall",
    VoxelType.TILLED.value: "tilled soil",
    VoxelType.CROP.value: "growing crop",
    VoxelType.CROP_RIPE.value: "ripe crop (harvestable)",
    VoxelType.COPPER_ORE.value: "copper ore (soldier armor)",
    VoxelType.GOLD_ORE.value: "gold ore (tribute hoard)",
    VoxelType.HULL.value: "ancient wreck hull",
    VoxelType.SALVAGE.value: "salvage (machine parts)",
    VoxelType.WOOD.value: "palm trunk (choppable)",
    VoxelType.WOOD_WALL.value: "palisade (rots, burns)",
    VoxelType.WEB.value: "spider silk (snares)",
    VoxelType.CASTLE.value: "castle (prosperity, never rots)",
    VoxelType.WATER.value: "standing water (rivers, reservoirs)",
    VoxelType.SHRUB.value: "berry bush (growing)",
    VoxelType.SHRUB_RIPE.value: "ripe berries (forageable)",
}


def column_inhabitants(sim: SandKingsSimulation, x: int,
                       y: int) -> List[Tuple[str, object]]:
    """Everything living at column (x, y), highest z first (R32)."""
    found: List[Tuple[int, Tuple[str, object]]] = []
    for colony in sim.colonies:
        if colony.is_alive() and colony.maw.position[:2] == (x, y):
            found.append((colony.maw.position[2], ('maw', colony)))
        for unit in colony.units:
            if unit.position[0] == x and unit.position[1] == y:
                found.append((unit.position[2], ('unit', unit)))
    for beast in getattr(sim, 'fauna', None) or []:
        if beast.position[0] == x and beast.position[1] == y:
            found.append((beast.position[2], ('beast', beast)))
    return [t for _z, t in sorted(found, key=lambda p: -p[0])]


def target_alive(sim: SandKingsSimulation, target) -> bool:
    """R33: object references validated per frame, never stale indices."""
    kind, obj = target
    if kind == 'unit':
        colony = next((c for c in sim.colonies
                       if c.colony_id == obj.colony_id), None)
        return colony is not None and obj in colony.units
    if kind == 'maw':
        return obj in sim.colonies and obj.is_alive()
    return obj in (getattr(sim, 'fauna', None) or [])


def target_position(target) -> Tuple[int, int, int]:
    kind, obj = target
    return obj.maw.position if kind == 'maw' else obj.position


def build_inspect_entries(sim: SandKingsSimulation,
                          target) -> List[Tuple[str, Tuple[int, int, int]]]:
    """R33 inspect panel content as (text, color) pairs. Pure: no pygame."""
    kind, obj = target
    if not target_alive(sim, target):
        gone = "has fallen" if kind != 'beast' else "is gone"
        return [(f"[{kind}] {gone}", (200, 90, 90))]
    entries: List[Tuple[str, Tuple[int, int, int]]] = []
    step = sim.step_count
    if kind == 'unit':
        colony = next(c for c in sim.colonies if c.colony_id == obj.colony_id)
        label = (sim._unit_label(obj) if hasattr(sim, '_unit_label')
                 else obj.unit_type.name.lower())
        house = sim._house(colony) if hasattr(sim, '_house') else ""
        color = hud_text_color(colony.color)
        entries.append((f"{label} of House {house}"[:44], color))
        entries.append((f"HP {obj.health:.0f}/{obj.max_health}"
                        f"  ATK {obj.attack}"
                        + (" (spear)" if getattr(obj, 'weapon_expires', 0) > step
                           else ""), color))
        flags = [f for f, on in (
            ("armored", getattr(obj, 'armored', False)),
            ("torch", getattr(obj, 'torch', False)),
            ("POISONED", getattr(obj, 'poisoned_until', 0) > step),
            ("retreating", obj.retreating)) if on]
        # Economy: wage-laborer or THRALL status
        wage_ratio = getattr(obj, 'wage_ratio', 0.0)
        laboring_for = getattr(obj, 'laboring_for', -1)
        if wage_ratio > 0:
            flags.append("wage-laborer")
        elif laboring_for >= 0:
            flags.append("THRALL")
        if flags:
            entries.append(("  " + ", ".join(flags), (230, 160, 90)))
        if obj.carrying:
            entries.append((f"  carrying {obj.carrying}", (200, 200, 140)))
        if obj.brain_layer is not None:
            entries.append((f"  kills {obj.brain_layer.kills}"
                            f"  steps {obj.brain_layer.steps_alive}",
                            (150, 180, 255)))
        entries.append((f"  thinks: {getattr(obj, 'thought', '...')}"[:44],
                        (200, 190, 120)))
        # K11/K12: the awakened speak - and can be spoken to (T)
        if getattr(colony, 'breached', False):
            from hive_mind_monitor import compose_utterance
            utterance = compose_utterance(obj, colony, sim)
            if utterance:
                entries.append((f'  says: "{utterance}"'[:44],
                                (255, 230, 150)))
            entries.append(("  [T] speak to it", (150, 150, 160)))
    elif kind == 'maw':
        house = sim._house(obj) if hasattr(sim, '_house') else str(obj.colony_id)
        color = hud_text_color(obj.color)
        entries.append((f"MAW of House {house}"[:44], color))
        entries.append((f"HP {obj.maw.health:.0f}/{MAW_MAX_HEALTH}"
                        f"  food {obj.maw.food_stored:.0f}"
                        f"  units {len(obj.units)}", color))
        posture = sim._posture(obj) if hasattr(sim, '_posture') else "?"
        aug = getattr(obj, 'memory_augment', 0)
        stage = getattr(obj, 'stage', 1)
        stage_name = {1: "insectoid", 2: "new breed", 3: "SHADE"}.get(stage, "")
        entries.append((f"  posture {posture}   stage: {stage_name}"
                        + (f"   mem+{aug}" if aug else ""), (170, 200, 140)))
        # Economy: enlightened, currency, thralls, bargain mode
        econ_line = ""
        if getattr(obj, 'enlightened', False):
            econ_line += "enlightened "
        currency = getattr(obj, 'currency', 0.0)
        if currency > 0:
            econ_line += f"grains:{currency:.0f} "
        thralls_held = sum(1 for u in obj.units
                          if getattr(u, 'laboring_for', -1) >= 0)
        thralls_lost = sum(1 for other in sim.colonies
                          for u in other.units
                          if getattr(u, 'laboring_for', -1) == obj.colony_id)
        if thralls_held or thralls_lost:
            econ_line += f"thralls:{thralls_held}↓/{thralls_lost}↑ "
        # Find dominant bargain mode for this colony
        bargain_map = getattr(sim, 'bargain_modes', {})
        for pair, mode in bargain_map.items():
            if mode != 'none' and obj.colony_id in pair:
                econ_line += f"mode:{mode} "
                break
        if econ_line:
            entries.append((f"  {econ_line}"[:46], (230, 200, 90)))
        # Disposition (DP9): boldness / favour / agitation
        conf = getattr(obj, 'confidence', 0.5)
        fav = getattr(obj, 'favoritism', 0.0)
        agit = getattr(obj, 'agitation', 0.0)
        disp = "bold" if conf > 0.62 else "timid" if conf < 0.38 else "steady"
        disp_line = f"disp:{disp}"
        if fav > 0.15:
            disp_line += " favoured"
        elif fav < -0.15:
            disp_line += " abused"
        if agit > 0.3:
            disp_line += " agitated"
        if disp != "steady" or abs(fav) > 0.15 or agit > 0.3:
            entries.append((f"  {disp_line}"[:46], (210, 170, 230)))
        techs = sorted(getattr(obj, 'techs', set()))  # TE5/TE9
        if techs:
            xp = getattr(obj, 'tech_xp', {})
            shown = ", ".join(f"{t} {int(xp.get(t, 0) * 100)}%" for t in techs)
            entries.append((f"  tech: {shown}", (170, 200, 200)))
        g = obj.genome
        entries.append((f"  agg {g.aggression:.2f} pat "
                        f"{getattr(g, 'patience', 0.5):.2f} loy "
                        f"{getattr(g, 'loyalty', 0.5):.2f} pla "
                        f"{getattr(g, 'plasticity', 0.5):.2f}",
                        (150, 180, 255)))
    else:  # beast
        entries.append((f"{obj.species.upper()} (wild)", BEAST_COLOR))
        entries.append((f"HP {obj.health}  ATK {obj.attack}"
                        f"  bounty {obj.bounty}", BEAST_COLOR))
        moods = [f for f, on in (("provoked", obj.provoked),
                                 ("fleeing", obj.fleeing)) if on]
        if moods:
            entries.append(("  " + ", ".join(moods), (230, 160, 90)))
    return entries


def build_look_entries(sim: SandKingsSimulation, x: int,
                       y: int, z: int) -> List[Tuple[str, Tuple[int, int, int]]]:
    """R32: what the look cursor sees at its cell. Pure: no pygame."""
    v = int(sim.world.voxels[x, y, z])
    name = VOXEL_LEGEND.get(v, "open air")
    owner = int(sim.world.ownership[x, y, z])
    line = f"({x},{y},{z}) {name}"
    if owner >= 0:
        line += f" [Colony {owner}]"
    if (x, y, z) in (getattr(sim, 'fires', None) or {}):
        line += " ON FIRE"
    entries = [(line[:46], (230, 210, 140))]
    carving = (getattr(sim, 'carvings', None) or {}).get((x, y, z))
    if carving:  # F4/AW2: name what a carving expresses
        nature = {'☀': "a carving of the plentiful sun (unexplained)",
                  '☁': "a carving of a quiet sky (unexplained)",
                  '☈': "a carving of a ruinous storm (unexplained)"}
        if carving in nature:
            entries.append((f" {nature[carving]}",
                            CARVE_COLORS.get(carving, (255, 235, 170))))
        else:
            meaning = {'♥': "devout", '◦': "impassive, watching",
                       '☠': "twisted with hate", '⌂': "machine-carved"}.get(
                           carving, carving)
            entries.append((f" a carving: sentiment {meaning}",
                            CARVE_COLORS.get(carving, (255, 235, 170))))
    kinds = column_inhabitants(sim, x, y)
    if kinds:
        entries.append((f"here: {len(kinds)} "
                        f"(V/ENTER cycles, F follows)", (150, 150, 160)))
    return entries


def build_legend_entries() -> List[Tuple[str, Tuple[int, int, int]]]:
    """R34: the legend, enumerated from the LIVE glyph dicts so nothing
    can silently go missing. Pure: no pygame."""
    palette = build_voxel_palette()
    entries: List[Tuple[str, Tuple[int, int, int]]] = [
        ("== LEGEND ==", (230, 210, 140)), ("", HUD_FG),
        ("-- terrain --", (150, 150, 160))]
    for value, glyph in GLYPHS.items():
        if value == VoxelType.AIR.value:
            continue
        name = VOXEL_LEGEND.get(value, f"voxel {value}")
        entries.append((f" {glyph}  {name}", tuple(int(c) for c in palette[value])))
    entries.append(("", HUD_FG))
    entries.append(("-- creatures --", (150, 150, 160)))
    for unit_type, glyph in UNIT_GLYPHS.items():
        entries.append((f" {glyph}  {unit_type.name.lower()}"
                        " (colony-colored)", HUD_FG))
    entries.append((f" {MAW_GLYPH}  maw (the queen; health bar when hurt)",
                    MAW_COLOR))
    for species, glyph in BEAST_GLYPHS.items():
        klass = PREDATOR_COLOR if species in BEAST_PREDATORS else NEUTRAL_BEAST_COLOR
        entries.append((f" {glyph}  {species} (wild)", klass))
    entries.append((f" {FIRE_GLYPH}  fire", FIRE_COLOR))
    entries.append((f" {POISON_GLYPH}  poison cloud (siege; decays)", POISON_COLOR))
    entries.append(("", HUD_FG))
    entries.append(("-- carvings (AW): forces before breakout, the god after --",
                    (150, 150, 160)))
    from sandkings import CARVE_SYMBOLS, NATURE_SYMBOLS
    carve_names = {'devout': "devout - they love their god",
                   'wary': "wary - impassive, watching",
                   'hateful': "hateful - the god has soured (look to it!)",
                   'machine': "machine-carved (the terminal)",
                   'bounty': "bounty - unexplained plenty (pre-breakout)",
                   'lean': "lean - the forces are quiet (pre-breakout)",
                   'dread': "dread - unexplained ruin (pre-breakout)"}
    for key, symbol in {**NATURE_SYMBOLS, **CARVE_SYMBOLS}.items():
        entries.append((f" {symbol}  {carve_names.get(key, key)}",
                        CARVE_COLORS.get(symbol, (255, 235, 170))))
    entries.append(("", HUD_FG))
    entries.append(("-- reading it --", (150, 150, 160)))
    entries.append((" bright = life, dim = terrain", (150, 150, 160)))
    entries.append((" red beast = predator", PREDATOR_COLOR))
    entries.append((" grey beast = harmless", NEUTRAL_BEAST_COLOR))
    entries.append((" copper = armored", COPPER_TINT))
    entries.append((" magenta = retreating", (255, 0, 255)))
    entries.append((" gold = envoy", (255, 200, 60)))
    entries.append((" underline = thrall", HUD_FG))
    entries.append((" red-pulse maw = siege", (235, 40, 30)))
    entries.append(("", HUD_FG))
    entries.append(("-- keeper verbs --", (150, 150, 160)))
    entries.append((" o  open the door -> breach", (150, 150, 160)))
    entries.append(("L close   I inspect cursor", (140, 140, 150)))
    return entries


def build_legend_compact() -> List[Tuple[str, Tuple[int, int, int]]]:
    """A CONDENSED legend for the toggleable sidebar, grouped into alphabetically-sorted CATEGORIES (and
    alphabetical WITHIN each), short labels so two narrow columns fit. Pure; enumerated from the glyph dicts."""
    import re
    palette = build_voxel_palette()
    cats: dict = {}
    cats['spawn'] = [(f"{g}  {ut.name.lower()}", HUD_FG) for ut, g in UNIT_GLYPHS.items()]
    cats['spawn'].append((f"{MAW_GLYPH}  maw", MAW_COLOR))
    cats['beasts'] = [(f"{g}  {sp}", PREDATOR_COLOR if sp in BEAST_PREDATORS else NEUTRAL_BEAST_COLOR)
                      for sp, g in BEAST_GLYPHS.items()]
    cats['pond'] = [(f"{FISH_GLYPHS[0]}  fish", FISH_COLOR), (f"{BOAT_GLYPH}  raft", BOAT_COLOR)]
    cats['hazards'] = [(f"{FIRE_GLYPH}  fire", FIRE_COLOR), (f"{POISON_GLYPH}  poison", POISON_COLOR)]
    cats['terrain'] = [(f"{GLYPHS[v.value]}  {v.name.lower().replace('_', ' ')}",
                        tuple(int(c) for c in palette[v.value]))
                       for v in (VoxelType.FOOD, VoxelType.WATER, VoxelType.CROP_RIPE, VoxelType.CORPSE,
                                 VoxelType.SAND, VoxelType.TUNNEL_WALL, VoxelType.WEB, VoxelType.SHRUB_RIPE)]
    cats['reading'] = [
        ("red=predator", PREDATOR_COLOR), ("grey=harmless", NEUTRAL_BEAST_COLOR),
        ("green=tamed", TAMED_BEAST_COLOR), ("red strobe=combat", (255, 40, 30)),
        ("magenta=retreat", (255, 0, 255)), ("gold=envoy", (255, 200, 60)),
        ("copper=armor", COPPER_TINT), ("underline=thrall", HUD_FG),
        ("pulse maw=siege", (235, 40, 30)),
    ]

    def namekey(entry):                         # sort by the NAME, skipping a leading glyph/symbol
        return re.sub(r'^[^0-9A-Za-z]+', '', entry[0]).lower()

    out: List[Tuple[str, Tuple[int, int, int]]] = [("== LEGEND (L) ==", (230, 210, 140))]
    for cat in sorted(cats):
        out.append((f"-- {cat} --", (150, 150, 160)))
        for label, color in sorted(cats[cat], key=namekey):
            out.append((f" {label}", color))
    return out


LEGEND_LINE_H = 16     # px between legend rows (matches the historical single-column spacing)
LEGEND_TOP = 10        # px top (and bottom) margin inside the legend area
LEGEND_LEFT = 14       # px left margin of the first column


def legend_layout(n_entries: int, area_w: int, area_h: int,
                  line_h: int = LEGEND_LINE_H, top: int = LEGEND_TOP,
                  left: int = LEGEND_LEFT) -> List[Tuple[int, int]]:
    """R34: column-wrapped (x, y) pixel position for each of the n_entries legend
    rows, so the legend NEVER overflows area_h. The historical single-column layout
    placed row i at y=top+i*line_h with no height bound, so once the entry count
    exceeded the window height the bottom rows rendered off-screen (cut off). Here
    the rows fill as many columns as needed: each column holds `max_rows` rows that
    fit within area_h, and the columns are spread evenly across area_w.

    Pure: no pygame. Guarantees every returned y is within [top, area_h) as long as
    a single row fits (line_h <= area_h - 2*top); columns advance in x instead.
    """
    usable_h = max(line_h, area_h - 2 * top)
    max_rows = max(1, usable_h // line_h)
    n_cols = max(1, (n_entries + max_rows - 1) // max_rows)
    col_w = max(1, (area_w - left) // n_cols)
    positions: List[Tuple[int, int]] = []
    for i in range(n_entries):
        col, row = divmod(i, max_rows)
        positions.append((left + col * col_w, top + row * line_h))
    return positions


def build_manager_entries(sim: SandKingsSimulation,
                          colony_id: int) -> List[Tuple[str, Tuple[int, int, int]]]:
    """Manager screen content as (text, color) pairs (SPEC_HIVE_MONITOR M5).

    Colony header + mood, the 35-anchor concept table (SPEC_HIVE_MONITOR
    M1-M13; probe accuracy and
    live active counts), top soldiers with individual stats and thoughts,
    and the decision log. Pure: no pygame."""
    colony = next((c for c in sim.colonies if c.colony_id == colony_id), None)
    if colony is None:
        return [("no such colony", HUD_FG)]
    color = hud_text_color(colony.color)
    monitor = sim._monitor(colony_id)
    neural = bool(getattr(colony.genome, 'use_neural', False))
    mode = "thoughts (decoded from hidden state)" if neural else "instincts (state predicates)"

    entries: List[Tuple[str, Tuple[int, int, int]]] = []
    war = " [WAR]" if getattr(colony, 'at_war', False) else ""
    if colony.is_alive():
        castes = {t: 0 for t in UnitType}
        for unit in colony.units:
            castes[unit.unit_type] += 1
        house = (sim._house(colony) if hasattr(sim, '_house')
                 else f"Colony {colony_id}")
        entries.append((f"== HOUSE {house} (Colony {colony_id}){war} ==",
                        color))
        entries.append((f"food:{colony.maw.food_stored:.0f}"
                        f"  maw:{colony.maw.health:.0f}"
                        f"  W:{castes[UnitType.WORKER]}"
                        f" S:{castes[UnitType.SOLDIER]}"
                        f" Sc:{castes[UnitType.SCOUT]}", color))
        entries.append((f"mood: {monitor.colony_thought(sim, colony)}", (200, 190, 120)))
        # D6: the house's self-model - pride, vengeance, legacy
        moods = []
        my_house = getattr(colony, 'house', '')
        grudges = getattr(sim, 'house_grudges', None) or {}
        if any(victim == my_house for (victim, _t) in grudges):
            moods.append("vengeance")
        holder = (sim.oasis_holder()
                  if callable(getattr(sim, 'oasis_holder', None)) else None)
        diplo = getattr(sim, 'diplomacy', None)
        if colony_id in (holder, getattr(diplo, 'hegemon', None)):
            moods.append("pride")
        if (getattr(colony, 'generation', 1) >= 3
                and colony.maw.health < MAW_MAX_HEALTH * 0.5):
            moods.append("legacy")
        if moods and my_house:
            entries.append((f"House {my_house} broods on "
                            + ", ".join(moods), (200, 150, 220)))
        # S5: how much the hive is of one mind
        if (getattr(colony.genome, 'use_neural', False)
                and hasattr(sim, 'resonance_of')):
            res, k = sim.resonance_of(colony)
            if k >= 2:
                entries.append((f"resonance: {res:.2f} across {k} soldiers",
                                (150, 180, 255)))
        if hasattr(sim, '_farm_counts'):  # Round-1 economy line (R24)
            plots, ripe = sim._farm_counts(colony)
            ore = getattr(colony, 'ore', {})
            learner = (sim.learners.get(colony_id)
                       if hasattr(sim, 'learners') else None)
            if learner is not None:
                from colony_learner import observe_state
                posture = (f"{learner.posture}"
                           f" (best:{learner.best_posture(observe_state(sim, colony))})")
            else:
                posture = "FORAGE"
            entries.append((f"farms:{plots} ({ripe} ripe)"
                            f"  Cu:{ore.get('copper', 0)} Au:{ore.get('gold', 0)}"
                            f"  posture:{posture}", (170, 200, 140)))
            ram = getattr(colony, 'ram_until', 0) > sim.step_count
            entries.append((f"wood:{getattr(colony, 'wood', 0)}"
                            f" bone:{getattr(colony, 'bone', 0)}"
                            + ("  [RAM]" if ram else ""), (139, 155, 60)))
    else:
        entries.append((f"== MANAGER: Colony {colony_id}: DEAD ==", (140, 60, 60)))
    entries.append((f"mind: {mode}", (140, 140, 150)))
    entries.append(("", HUD_FG))

    diplomacy = getattr(sim, 'diplomacy', None)
    if diplomacy is not None and colony is not None and colony.is_alive():
        entries.append(("RELATIONS", (120, 180, 220)))
        allies, truces, wars = [], [], []
        for other in sim.colonies:
            oid = other.colony_id
            if oid == colony_id or not other.is_alive():
                continue
            if diplomacy.ally(colony_id, oid):
                allies.append(f"C{oid}")
            if diplomacy.truce_until.get(frozenset((colony_id, oid)), -1) > sim.step_count:
                truces.append(f"C{oid}")
            if (diplomacy.war_target.get(colony_id) == oid
                    or diplomacy.war_target.get(oid) == colony_id):
                wars.append(f"C{oid}")
        entries.append((f"  allies: {', '.join(allies) or '—'}"
                        f"   truce: {', '.join(truces) or '—'}"
                        f"   war: {', '.join(wars) or '—'}", HUD_FG))
        entries.append(("", HUD_FG))

    # THOUGHTS sidebar (SPEC_HIVE_MONITOR): only the anchors actually firing — not the whole
    # vocabulary (a wall of "100% 0" rows carries no signal).
    rows = monitor.concept_rows(sim, colony) if colony.is_alive() else []
    avg_acc = (sum(r[1] for r in rows) / len(rows)) if rows else 0.0
    entries.append((f"THOUGHTS  (probes {avg_acc * 100:.0f}% accurate — decoded, not fabricated)",
                    (120, 180, 220)))
    npop = max(1, len(colony.units)) if colony.is_alive() else 1
    live = sorted((r for r in rows if r[2] > 0), key=lambda r: r[2], reverse=True)[:6]
    if live:
        for i in range(0, len(live), 2):
            parts = [f"{name:>10} {hp_bar(min(1.0, active / npop), 6)}"
                     for name, acc, active in live[i:i + 2]]
            entries.append(("  " + "    ".join(parts), HUD_FG))
    else:
        entries.append(("  (quiet)", (140, 140, 150)))
    entries.append(("", HUD_FG))

    # MAW -> MANAGER -> SWARM: the communication pipeline the user watches — the 85% maw directive,
    # how the manager broadcasts it, and the pheromone field the swarm senses/acts on.
    if colony.is_alive():
        entries.append(("MAW -> MANAGER -> SWARM", (120, 180, 220)))
        mrl = getattr(colony, 'maw_rl', None)
        d = getattr(mrl, 'last_directive', None) if mrl is not None else None
        if d is not None:
            dv = ([float(x) for x in (d.tolist() if hasattr(d, 'tolist') else d)] + [.5, .5, .5, .5])[:4]
            entries.append((f"  maw  aggr{hp_bar(dv[0], 5)} mob{hp_bar(dv[1], 5)}"
                            f" vert{hp_bar(dv[2], 5)} forage{hp_bar(dv[3], 5)}", (210, 170, 140)))
        else:
            entries.append(("  maw  instinct (rule-based; no learned directive)", (140, 140, 150)))
        learner = sim.learners.get(colony_id) if hasattr(sim, 'learners') else None
        posture = learner.posture if learner is not None else "FORAGE"
        entries.append((f"  mgr  posture:{posture}  ->  broadcasting to {len(colony.units)} kin",
                        (170, 200, 140)))
        pher = getattr(sim, 'pheromones', None)
        if pher is not None and getattr(pher, 'trails', None) is not None:
            tr = pher.trails
            def _chan(pt: int) -> float:
                try:
                    return float(min(1.0, tr[:, :, :, colony_id, pt].max()))
                except Exception:
                    return 0.0
            entries.append((f"  pher food{hp_bar(_chan(0), 5)} danger{hp_bar(_chan(1), 5)}"
                            f" territory{hp_bar(_chan(2), 5)}", (150, 180, 220)))
        entries.append(("", HUD_FG))

    entries.append(("TOP SOLDIERS", (120, 180, 220)))
    soldiers = [u for u in colony.units if u.unit_type == UnitType.SOLDIER]
    if neural:
        soldiers.sort(key=lambda u: (u.brain_layer.get_performance_score()
                                     if u.brain_layer else 0.0), reverse=True)
    else:
        soldiers.sort(key=lambda u: u.health, reverse=True)
    for unit in soldiers[:3]:
        uid = getattr(unit, 'unit_id', 0)
        thought = getattr(unit, 'thought', '...')
        if neural and unit.brain_layer is not None:
            b = unit.brain_layer
            line = (f"#{uid:<4} k:{b.kills} dmg:{b.damage_dealt:.0f}/"
                    f"{b.damage_taken:.0f} age:{b.steps_alive}"
                    f" perf:{b.get_performance_score():.2f}  {thought}")
        else:
            line = f"#{uid:<4} hp:{unit.health:.0f}/{unit.max_health}  {thought}"
        entries.append((line[:76], color))
    if not soldiers:
        entries.append(("  (no soldiers alive)", (140, 140, 150)))

    arc = getattr(colony, 'machine_arc', 'none') if colony else 'none'
    if arc != 'none':  # PROGRAM panel (SPEC_MACHINE_AGE T36)
        steel = (150, 200, 220)
        entries.append(("", HUD_FG))
        salvage = getattr(colony, 'salvage', 0)
        entries.append((f"MACHINE: {arc} · salvage {salvage}", steel))
        for device in getattr(colony, 'devices', []):
            entries.append((f"  {device.kind:<8}{hp_bar(device.durability / 240)}"
                            f" {device.durability}/240", steel))
        for controller in getattr(colony, 'controllers', [])[:1]:
            entries.append((f"  CONTROLLER {hp_bar(controller.durability / 240)}"
                            f" ticks:{controller.operate_ticks}"
                            f" U:{controller.u_ema if controller.u_ema is None else round(controller.u_ema, 2)}"
                            f" reviews:{controller.reviews} ({controller.last_outcome})",
                            steel))
            for line in controller.listing()[:8]:
                entries.append((f"   {line}"[:76], (120, 160, 175)))
            regs = " ".join(f"R{i}={v}" for i, v in
                            enumerate(controller.registers[:6]))
            entries.append((f"   {regs}", (110, 140, 155)))

    entries.append(("", HUD_FG))
    entries.append(("DECISIONS", (120, 180, 220)))
    decisions = list(monitor.decisions)[-5:]
    for step, actor, event, thought in decisions:
        entries.append((f"[{step}] {actor} {event} -- {thought}"[:76],
                        event_tint(event) if "war" in event else HUD_FG))
    if not decisions:
        entries.append(("  (no recorded decisions yet)", (140, 140, 150)))
    entries.append(("", HUD_FG))
    entries.append(("M close   LEFT/RIGHT colony", (140, 140, 150)))
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

    def __init__(self, target, cell_size: int = DEFAULT_CELL_SIZE,
                 steps_per_second: float = DEFAULT_STEPS_PER_SECOND,
                 max_steps: Optional[int] = None,
                 save_path: Optional[str] = None):
        # U2: attach to a TerrariumRunner (the shared engine), or wrap a bare
        # sim in one so the standalone/test path keeps a single, deterministic
        # lock discipline. Either way the viewer never steps the sim itself.
        from dashboard import TerrariumRunner
        if isinstance(target, TerrariumRunner):
            self.runner = target
            self._owns_runner = False
            if save_path is None:
                save_path = target.save_path
        else:
            self.runner = TerrariumRunner(target, sps=steps_per_second,
                                          save_path=save_path)
            self._owns_runner = True
        self.save_path = save_path  # sqlite terrarium db (spec T13); None = off
        self.sim = self.runner.sim
        w, h = self.sim.world.width, self.sim.world.height
        self.cell_size = max(2, min(cell_size,
                                    (MAX_WINDOW[0] - HUD_WIDTH) // w,
                                    MAX_WINDOW[1] // h))
        self.pacer = StepPacer(self.runner.sps)
        self.max_steps = max_steps
        self.steps_done = 0
        self.view_mode = ViewMode.TOPDOWN
        self.z_level = self.sim.world.depth - 1  # surface view (spec R14)
        self.capturing = False
        self.overlay_index = 0  # index into PHEROMONE_OVERLAYS (spec R17)
        self.render_style = RenderStyle.GLYPH  # dazzle by default (spec R18)
        self.manager_open = False   # SPEC_HIVE_MONITOR M5
        self.manager_colony = 0
        self.saga_open = False      # SPEC_DYNASTIES D5
        self.legend_open = False    # R34
        self.look_mode = False      # R32 look cursor
        self.cursor = (self.sim.world.width // 2, self.sim.world.height // 2)
        self.inspected = None       # ('unit'|'maw'|'beast', object) (R33)
        self.follow = False         # R33 follow mode
        self._select_cycle = 0      # V/ENTER cycles column inhabitants
        self.captured_frames: List[np.ndarray] = []
        self.running = False
        self._screen = None
        self._font = None
        self._cell_font = None
        self._maw_font = None
        self._glyph_cache: dict = {}  # (char, color, big) -> Surface
        self._last_mirror_ms = 0      # U8: last glyph-mirror snapshot tick

    @property
    def paused(self) -> bool:
        """U4: pause is the runner's state - one truth across window and web."""
        return self.runner.paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self.runner.paused = bool(value)

    def run(self) -> None:
        pygame.init()
        try:
            w, h = self.sim.world.width, self.sim.world.height
            size = (w * self.cell_size + HUD_WIDTH, max(h * self.cell_size, 400))
            self._screen = pygame.display.set_mode(size)
            pygame.display.set_caption("Sand Kings — Live Terrarium")
            # Held keys auto-repeat: after 250ms, re-fire every 60ms — so holding an arrow pans
            # the look cursor continuously (and Shift+arrow jumps 10 cells per repeat).
            pygame.key.set_repeat(250, 60)
            self._load_fonts()
            clock = pygame.time.Clock()
            self.running = True

            while self.running:
                dt = clock.tick(60)
                for event in pygame.event.get():
                    self._handle_event(event)

                if self._owns_runner:
                    # U2 standalone/deterministic: pace and step synchronously
                    # (the test path). Clamp so steps_done lands exactly on
                    # max_steps rather than overshooting a partial frame.
                    owed = self.pacer.update(dt, self.paused)
                    if self.max_steps is not None:
                        owed = max(0, min(owed, self.max_steps - self.steps_done))
                    stepped = owed > 0
                    self.steps_done += self.runner.step_owed(owed)
                    if (self.max_steps is not None
                            and self.steps_done >= self.max_steps):
                        self.running = False
                else:
                    # U2 attached: the runner thread owns stepping; the window
                    # only advances the pacer (HUD sps) and mirrors the count so
                    # the on-screen counter equals the browser's.
                    self.pacer.update(dt, self.paused)
                    self.steps_done = self.sim.step_count
                    stepped = False
                    if (self.max_steps is not None
                            and self.steps_done >= self.max_steps):
                        self.running = False

                self._render()
                if self.capturing and stepped:
                    self._capture_frame()
                if not self._owns_runner and self.runner.mirror:
                    self._mirror_snapshot()

            assert self.max_steps is None or self.steps_done <= self.max_steps
            self._save_capture()
        finally:
            # U4: one save path - the owner of the runner stops (and saves) it.
            # In attached mode the entrypoint stops the shared runner after run().
            if self._owns_runner:
                self.runner.stop()
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
                self.runner.single_step()  # U4: one locked step while paused
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
                self.runner.sps = self.pacer.steps_per_second  # U4
            elif key in (pygame.K_MINUS, pygame.K_COMMA, pygame.K_KP_MINUS):
                self.pacer.slower()
                self.runner.sps = self.pacer.steps_per_second  # U4
            elif self.look_mode and key in (pygame.K_UP, pygame.K_DOWN,
                                            pygame.K_LEFT, pygame.K_RIGHT):
                step = 10 if (event.mod & pygame.KMOD_SHIFT) else 1   # Shift = jump 10 cells
                dx = {pygame.K_LEFT: -step, pygame.K_RIGHT: step}.get(key, 0)
                dy = {pygame.K_UP: -step, pygame.K_DOWN: step}.get(key, 0)
                self.cursor = (
                    max(0, min(self.sim.world.width - 1, self.cursor[0] + dx)),
                    max(0, min(self.sim.world.height - 1, self.cursor[1] + dy)))
                self.follow = False  # steering the cursor breaks the leash
            elif key == pygame.K_UP:
                self.z_level = min(self.sim.world.depth - 1, self.z_level + 1)
            elif key == pygame.K_DOWN:
                self.z_level = max(0, self.z_level - 1)
            elif key == pygame.K_TAB:
                order = (ViewMode.TOPDOWN, ViewMode.SLICE, ViewMode.ISO)
                self.view_mode = order[(order.index(self.view_mode) + 1)
                                       % len(order)]
            elif key == pygame.K_g:
                self.capturing = not self.capturing
            elif key == pygame.K_p:
                self.overlay_index = (self.overlay_index + 1) % len(PHEROMONE_OVERLAYS)
            elif key == pygame.K_r:
                order = (RenderStyle.GLYPH, RenderStyle.BLOCKS, RenderStyle.TILES)
                self.render_style = order[(order.index(self.render_style) + 1) % len(order)]
            elif key == pygame.K_m:
                self.manager_open = not self.manager_open
                self.saga_open = False
                self.legend_open = False
            elif key == pygame.K_h:
                self.saga_open = not self.saga_open
                self.manager_open = False
                self.legend_open = False
            elif key == pygame.K_l:  # R34 legend
                self.legend_open = not self.legend_open
                self.manager_open = False
                self.saga_open = False
            elif key == pygame.K_i:  # R32 look cursor
                self.look_mode = not self.look_mode
                self.manager_open = False
                self.saga_open = False
                self.legend_open = False
                if not self.look_mode:
                    self.inspected = None
                    self.follow = False
            elif self.look_mode and key in (pygame.K_v, pygame.K_RETURN):
                targets = column_inhabitants(self.sim, *self.cursor)
                if targets:
                    self.inspected = targets[self._select_cycle % len(targets)]
                    self._select_cycle += 1
                    self.follow = False
            # AR6: the keeper's arena console (any keeper key disarms auto).
            # U3: every verb under the runner lock. GIFTS 1-5, WRATH 6-0 + [],
            # NEUTRAL n/b.
            elif key == pygame.K_1:                     # GIFT: manna
                if not self.look_mode:
                    self.look_mode = True
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_drop_food(*self.cursor)
            elif key == pygame.K_2:                     # GIFT: crickets
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('cricket')
            elif key == pygame.K_3:                     # GIFT: ants
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('ant')
            elif key == pygame.K_4:                     # GIFT: small spider
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('small_spider')
            elif key == pygame.K_5:                     # GIFT: tech
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_gift(pos=self.cursor)
            elif key == pygame.K_6:                     # WRATH: big spider
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('spider')
            elif key == pygame.K_7:                     # WRATH: scorpion
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('scorpion')
            elif key == pygame.K_8:                     # WRATH: snake
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('snake')
            elif key == pygame.K_9:                     # WRATH: drought
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_drought(not getattr(self.sim, 'drought',
                                                        False))
            elif key == pygame.K_0:                     # WRATH: the cat
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release_cat()
            elif key == pygame.K_LEFTBRACKET:           # WRATH: cold wave
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_temperature('cold')
            elif key == pygame.K_RIGHTBRACKET:          # WRATH: heat wave
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_temperature('heat')
            elif key == pygame.K_n:                     # NEUTRAL: squirrel
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('squirrel')
            elif key == pygame.K_b:                     # NEUTRAL: rabbit
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_release('rabbit')
            elif key == pygame.K_w:                     # GIFT: rain (irrigate)
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_water(*self.cursor, big=False)
            elif key == pygame.K_j:                     # GIFT: seeds
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_seed(*self.cursor)
            elif key == pygame.K_d:                     # WRATH: deluge
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_water(*self.cursor, big=True)
            elif key == pygame.K_u:                     # WRATH: firecracker
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    self.sim.keeper_ignite(*self.cursor)
            elif key == pygame.K_o:                     # BRK-C: keeper opens the door
                with self.runner.lock:
                    self.sim.keeper_auto = False
                    target = _breakout_target(self)
                    if target is not None:
                        self.sim.keeper_open_door(target)
            elif key == pygame.K_x:                     # PANEL: more water
                with self.runner.lock:
                    self.sim.keeper_set_water(
                        getattr(self.sim, 'water_target', 0.6) + 0.1)
            elif key == pygame.K_c:                     # PANEL: less water
                with self.runner.lock:
                    self.sim.keeper_set_water(
                        getattr(self.sim, 'water_target', 0.6) - 0.1)
            elif key == pygame.K_a:                     # PANEL: more sun
                with self.runner.lock:
                    self.sim.keeper_set_sun(
                        getattr(self.sim, 'sun_hours', 12) + 2)
            elif key == pygame.K_z:                     # PANEL: less sun
                with self.runner.lock:
                    self.sim.keeper_set_sun(
                        getattr(self.sim, 'sun_hours', 12) - 2)
            elif (key == pygame.K_t and self.inspected is not None
                  and self.inspected[0] == 'unit'
                  and target_alive(self.sim, self.inspected)):
                with self.runner.lock:
                    self.sim.keeper_speak(self.inspected[1])  # K12
            elif key == pygame.K_f and self.inspected is not None:
                self.follow = not self.follow  # R33
            elif key == pygame.K_e:  # D11: the terrarium writes its book
                from chronicle import write_saga
                count = write_saga(self.sim, "terrarium_saga.txt")
                print(f"[saga] {count} rows written to terrarium_saga.txt")
            elif self.manager_open and key in (pygame.K_LEFT, pygame.K_RIGHT):
                ids = [c.colony_id for c in self.sim.colonies]
                if ids:
                    step_by = 1 if key == pygame.K_RIGHT else -1
                    current = (ids.index(self.manager_colony)
                               if self.manager_colony in ids else 0)
                    self.manager_colony = ids[(current + step_by) % len(ids)]
            elif key == pygame.K_k and self.save_path:
                self.runner.save()  # U4: single save path
                with self.runner.lock:
                    if hasattr(self.sim, '_log_event'):
                        self.sim._log_event("The keeper preserves the terrarium")
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # R32: a click IS the look cursor
            if not (self.manager_open or self.saga_open or self.legend_open):
                x = event.pos[0] // self.cell_size
                y = event.pos[1] // self.cell_size
                if (0 <= x < self.sim.world.width
                        and 0 <= y < self.sim.world.height):
                    self.look_mode = True
                    self.cursor = (x, y)
                    self.follow = False
                    targets = column_inhabitants(self.sim, x, y)
                    self.inspected = targets[0] if targets else None
                    self._select_cycle = 1

    def _load_fonts(self) -> None:
        """Load the HUD + map glyph fonts. Prefer DejaVu Sans Mono (broad unicode -> distinctive
        creature/terrain glyphs), fall back to Consolas/Courier. Builds bold cell/maw fonts plus an
        UNDERLINED cell variant for alert states (R18 + storytelling-with-data legibility)."""
        self._font = pygame.font.SysFont("consolas,courier", 14)
        dejavu = None
        try:                                          # matplotlib bundles DejaVuSansMono.ttf (full unicode)
            import os as _os
            import matplotlib.font_manager as _fm
            p = _fm.findfont("DejaVu Sans Mono")
            if p and _os.path.exists(p) and "Mono" in p:
                dejavu = p
        except Exception:
            dejavu = None
        if dejavu is None:                            # last resort: whatever the OS matches (may be partial)
            dejavu = pygame.font.match_font("dejavusansmono")
        if dejavu:
            self._cell_font = pygame.font.Font(dejavu, self.cell_size + 3)
            self._maw_font = pygame.font.Font(dejavu, self.cell_size * 2)
            self._cell_font_ul = pygame.font.Font(dejavu, self.cell_size + 3)
        else:
            self._cell_font = pygame.font.SysFont("consolas,couriernew", self.cell_size + 3)
            self._maw_font = pygame.font.SysFont("consolas,couriernew", self.cell_size * 2)
            self._cell_font_ul = pygame.font.SysFont("consolas,couriernew", self.cell_size + 3)
        for f in (self._cell_font, self._maw_font, self._cell_font_ul):
            f.set_bold(True)
        self._cell_font_ul.set_underline(True)
        self._legend_font = pygame.font.SysFont("consolas,courier", 11)  # compact legend sidebar

    def _blink_on(self, period_ms: int = 400) -> bool:
        """Blink phase from the wall clock — reserved for rare urgent alerts (a maw under siege)."""
        return (pygame.time.get_ticks() // period_ms) % 2 == 0

    def _glyph(self, char: str, color: Tuple[int, int, int],
               big: bool = False, underline: bool = False) -> "pygame.Surface":
        """Cached rendered glyph; the grid never re-renders text per frame (R18)."""
        key = (char, color, big, underline)
        surface = self._glyph_cache.get(key)
        if surface is None:
            font = self._maw_font if big else (self._cell_font_ul if underline else self._cell_font)
            surface = font.render(char, True, color)
            self._glyph_cache[key] = surface
        return surface

    def _blit_glyph(self, char: str, color: Tuple[int, int, int],
                    cx: int, cy: int, big: bool = False, underline: bool = False) -> None:
        """Blit a glyph centered on the cell at pixel (cx, cy)."""
        cell = self.cell_size
        span = cell * 2 if big else cell
        surface = self._glyph(char, color, big, underline)
        self._screen.blit(surface, (cx + (span - surface.get_width()) // 2,
                                    cy + (span - surface.get_height()) // 2))

    def _sprite(self, kind: str, arg, tint, tw: int) -> "pygame.Surface":
        """Forge (internally cached) a top-down creature sprite for TILES mode, reusing the ISO forge —
        so a soldier LOOKS like a mandibled bug, a spider like a spider. kind: 'bug' (arg=caste,
        tint=colony) | 'maw' (tint=color) | 'beast' (arg=species)."""
        from iso_sprites import forge_bug, forge_maw, forge_beast
        if kind == 'bug':
            return forge_bug(arg, tint, tw)
        if kind == 'maw':
            return forge_maw(tint, tw)
        return forge_beast(arg, tw)

    def _render(self) -> None:
        # U3: the whole on-screen render reads sim state (voxels in place) and
        # may consume the global np.random stream (storm haze) or lazily build
        # monitors/probes on the manager screen - all under the runner lock so
        # it never races the background stepping thread.
        with self.runner.lock:
            self._render_body()

    def _render_body(self) -> None:
        cell = self.cell_size
        w, h = self.sim.world.width, self.sim.world.height

        if self.manager_open:
            self._render_manager(w * cell, max(h * cell, 400))
            return
        if self.saga_open:
            self._render_saga(w * cell, max(h * cell, 400))
            return
        # NB: the legend is a toggleable SIDEBAR overlay (drawn after the map, below), not a
        # full-screen takeover — so the terrarium stays visible while it is open.

        # R33 follow: the leash updates cursor and z before drawing
        if self.inspected is not None and self.follow:
            if target_alive(self.sim, self.inspected):
                tx, ty, tz = target_position(self.inspected)
                self.cursor = (tx, ty)
                self.z_level = tz
            else:
                self.follow = False

        # R36: the stonesense path draws its own map area
        if self.view_mode == ViewMode.ISO:
            self._screen.fill(HUD_BG)
            self._render_iso_map(w * cell, max(h * cell, 400))
            self._draw_look_panel()
            hud_x = w * cell + 12
            for i, (line, color) in enumerate(build_hud_entries(
                    self.sim, self.pacer.steps_per_second,
                    self.paused, self.z_level, self.capturing,
                    self.view_mode, PHEROMONE_OVERLAYS[self.overlay_index])):
                if line:
                    self._screen.blit(self._font.render(line, True, color),
                                      (hud_x, 10 + i * 18))
            if self.legend_open:
                self._draw_legend_sidebar(max(h * cell, 400))
            pygame.display.flip()
            return

        glyph_mode = (self.render_style == RenderStyle.GLYPH
                      and cell >= GLYPH_MIN_CELL)
        tiles_mode = (self.render_style == RenderStyle.TILES
                      and cell >= GLYPH_MIN_CELL)   # procedural top-down creature sprites

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
                        tc = col_colors[y]                      # mute terrain -> "ground"
                        self._blit_glyph(char, (int(tc[0] * TERRAIN_GLYPH_DIM),
                                                int(tc[1] * TERRAIN_GLYPH_DIM),
                                                int(tc[2] * TERRAIN_GLYPH_DIM)),
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
                if tiles_mode:
                    spr = self._sprite('bug', unit.unit_type.name.lower(), colony.color, cell)
                    self._screen.blit(spr, (ux * cell + (cell - spr.get_width()) // 2,
                                            uy * cell + (cell - spr.get_height()) // 2))
                elif glyph_mode:
                    char = UNIT_GLYPHS.get(unit.unit_type, "?")
                    if getattr(unit, 'rafted', False):     # afloat on a raft — draw the hull, spawn rides on top
                        self._blit_glyph(BOAT_GLYPH, BOAT_COLOR, ux * cell, uy * cell)
                        color = hud_text_color(fill)
                    elif getattr(unit, 'gift_to', -1) >= 0:  # envoy caravan (P13)
                        color = (255, 200, 60)
                    elif unit.retreating:
                        color = border
                    elif getattr(unit, 'armored', False):  # copper armor (R22)
                        color = tuple(int(c * depth_shade(depth)) for c in COPPER_TINT)
                    else:
                        color = hud_text_color(fill)
                    thrall = getattr(unit, 'laboring_for', -1) >= 0   # a captive laboring for a captor
                    self._blit_glyph(char, color, ux * cell, uy * cell, underline=thrall)
                else:
                    rect = pygame.Rect(ux * cell + 1, uy * cell + 1, cell - 2, cell - 2)
                    pygame.draw.rect(self._screen, fill, rect)
                    pygame.draw.rect(self._screen, border, rect, 1)
            if colony.is_alive():
                depth = self._visible_depth(colony.maw.position)
                if depth is not None:
                    mx, my = colony.maw.position[0], colony.maw.position[1]
                    hp_frac = colony.maw.health / MAW_MAX_HEALTH
                    fill = tuple(int(c * depth_shade(depth)) for c in MAW_COLOR)
                    if hp_frac < 1.0 and self._blink_on():   # UNDER SIEGE -> pulse red (rare urgent alert)
                        fill = (235, 40, 30)
                    rect = pygame.Rect(mx * cell - cell // 2, my * cell - cell // 2,
                                       cell * 2, cell * 2)
                    if tiles_mode:
                        spr = self._sprite('maw', None, fill, cell)
                        self._screen.blit(spr, (rect.x + (rect.width - spr.get_width()) // 2,
                                                rect.y + (rect.height - spr.get_height()) // 2))
                    elif glyph_mode:
                        self._blit_glyph(MAW_GLYPH, fill, rect.x, rect.y, big=True)
                    else:
                        pygame.draw.rect(self._screen, fill, rect)
                        pygame.draw.rect(self._screen, (0, 0, 0), rect, 2)
                    # Siege health bar (spec R16): only shown when damaged
                    if hp_frac < 1.0:
                        bar = pygame.Rect(rect.x, rect.y - 5, rect.width, 3)
                        pygame.draw.rect(self._screen, (80, 0, 0), bar)
                        fg = pygame.Rect(rect.x, rect.y - 5,
                                         max(1, int(rect.width * hp_frac)), 3)
                        pygame.draw.rect(self._screen,
                                         (int(255 * (1 - hp_frac)), int(220 * hp_frac), 0), fg)

        # Fire overlay (T46): burning cells flare orange carets
        for pos in list(getattr(self.sim, 'fires', None) or {}):
            if self._visible_depth(pos) is None:
                continue
            if glyph_mode:
                self._blit_glyph(FIRE_GLYPH, FIRE_COLOR,
                                 pos[0] * cell, pos[1] * cell)
            else:
                rect = pygame.Rect(pos[0] * cell, pos[1] * cell, cell, cell)
                pygame.draw.rect(self._screen, FIRE_COLOR, rect, 1)

        # Poison overlay (SPEC_CHEMICAL_WAR CW1): a lingering chemical cloud glows sickly green. Pure read
        # of the sim's transient poison dict (empty unless POISON_ENABLED lobbed a shell).
        for pos in list(getattr(self.sim, 'poison', None) or {}):
            if self._visible_depth(pos) is None:
                continue
            if glyph_mode:
                self._blit_glyph(POISON_GLYPH, POISON_COLOR, pos[0] * cell, pos[1] * cell)
            else:
                rect = pygame.Rect(pos[0] * cell, pos[1] * cell, cell, cell)
                pygame.draw.rect(self._screen, POISON_COLOR, rect, 1)

        # Launched effects (SPEC_FAUNA_ECOLOGY, gated EFFECTS_ENABLED): a catapult shot arcs across the board
        # and bursts; a firecracker flashes. Pure read of the sim's transient effects list.
        for e in getattr(self.sim, 'effects', None) or []:
            pos = e.get('pos')
            if pos is None or self._visible_depth(pos) is None:
                continue
            if e.get('kind') == 'shot':
                self._blit_glyph("•", (255, 225, 130), pos[0] * cell, pos[1] * cell)
            elif e.get('kind') == 'bolt':          # SE1: a fast steel ballista bolt
                self._blit_glyph("»", (200, 205, 215), pos[0] * cell, pos[1] * cell)
            else:
                col = (60, 150, 240) if e.get('kind') == 'splash' else (255, 90, 30)
                pygame.draw.rect(self._screen, col,
                                 pygame.Rect(pos[0] * cell, pos[1] * cell, cell, cell), max(2, cell // 4))

        # Wild beasts (T48): colored by DANGER CLASS — warm red for predators, cool grey for neutrals
        for beast in getattr(self.sim, 'fauna', None) or []:
            depth = self._visible_depth(beast.position)
            if depth is None:
                continue
            bx, by = beast.position[0], beast.position[1]
            klass = (TAMED_BEAST_COLOR if getattr(beast, 'owner', -1) >= 0
                     else (PREDATOR_COLOR if beast.species in BEAST_PREDATORS else NEUTRAL_BEAST_COLOR))
            color = tuple(int(c * depth_shade(depth)) for c in klass)
            if tiles_mode:
                spr = self._sprite('beast', beast.species, None, cell)
                self._screen.blit(spr, (bx * cell + (cell - spr.get_width()) // 2,
                                        by * cell + (cell - spr.get_height()) // 2))
            elif glyph_mode:
                self._blit_glyph(BEAST_GLYPHS.get(beast.species, "?"), color,
                                 bx * cell, by * cell)
            else:
                rect = pygame.Rect(bx * cell + 1, by * cell + 1,
                                   cell - 2, cell - 2)
                pygame.draw.rect(self._screen, color, rect)

        # A World Alive — the pond shoal: scatter fish over the oasis disc + real WATER cells, count ~ guppy_pop.
        # Pure renderer: reads the sim scalar, mutates nothing, uses NO shared RNG (deterministic hash + a
        # wall-clock phase so the shoal darts). Draws over the surface pond in glyph mode.
        gp = float(getattr(self.sim, 'guppy_pop', 0.0) or 0.0)
        if gp > 0 and glyph_mode:
            from sandkings import OASIS_RADIUS
            cx, cy = w // 2, h // 2
            cells = [(x, y)
                     for x in range(max(1, cx - OASIS_RADIUS), min(w - 1, cx + OASIS_RADIUS + 1))
                     for y in range(max(1, cy - OASIS_RADIUS), min(h - 1, cy + OASIS_RADIUS + 1))
                     if (x - cx) ** 2 + (y - cy) ** 2 <= OASIS_RADIUS ** 2]
            water = np.argwhere(self.sim.world.voxels[:, :, self.z_level] == VoxelType.WATER.value)
            cells += [(int(wx), int(wy)) for wx, wy in water]
            if cells:
                n = min(len(cells), FISH_MAX, 1 + int(gp / FISH_PER))
                phase = pygame.time.get_ticks() // 350          # ~3 darts/sec (view-only animation)
                cells.sort(key=lambda c: ((c[0] * 73856093) ^ (c[1] * 19349663) ^ (phase * 83492791)) & 0xffff)
                for (fx, fy) in cells[:n]:
                    g = FISH_GLYPHS[(fx + fy + phase) % len(FISH_GLYPHS)]
                    self._blit_glyph(g, FISH_COLOR, fx * cell, fy * cell)

        # Combat strobe: fighting flashes RED (the visual language of combat). Pure renderer — detects
        # adjacency between hostile units and between units and threatening beasts, then strobes on the wall
        # clock (a red pulse at each combat cell + a red screen-edge vignette). Reads only; mutates nothing.
        upos = {}                                    # (x, y) -> (colony_id, z) for a quick adjacency probe
        for colony in self.sim.colonies:
            for unit in colony.units:
                upos[(unit.position[0], unit.position[1])] = (colony.colony_id, unit.position[2])
        combat = set()                               # (x, y, z) cells currently in combat
        for beast in getattr(self.sim, 'fauna', None) or []:
            if beast.hunt_range <= 0 and not getattr(beast, 'provoked', False):
                continue
            bx, by, bz = beast.position
            owner = getattr(beast, 'owner', -1)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    hit = upos.get((bx + dx, by + dy))
                    if hit is not None and hit[0] != owner:
                        combat.add((bx, by, bz)); combat.add((bx + dx, by + dy, hit[1]))
        from politics import hostile
        pair_hostile = {}
        for colony in self.sim.colonies:
            cid = colony.colony_id
            for unit in colony.units:
                ux, uy, uz = unit.position
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        hit = upos.get((ux + dx, uy + dy))
                        if hit is None or hit[0] == cid:
                            continue
                        key = (cid, hit[0]) if cid < hit[0] else (hit[0], cid)
                        h = pair_hostile.get(key)
                        if h is None:
                            h = hostile(self.sim, cid, hit[0]); pair_hostile[key] = h
                        if h:
                            combat.add((ux, uy, uz)); combat.add((ux + dx, uy + dy, hit[1]))
        if combat and self._blink_on(150):           # ~3 Hz red strobe while combat is live
            thick = max(2, cell // 5)
            for pos in combat:
                if self._visible_depth(pos) is None:
                    continue
                pygame.draw.rect(self._screen, (255, 40, 30),
                                 pygame.Rect(pos[0] * cell, pos[1] * cell, cell, cell), thick)
            edge = max(3, cell // 3)                  # red screen-edge vignette: the tank is at war
            haze = pygame.Surface((w * cell, h * cell), pygame.SRCALPHA)
            for r in (pygame.Rect(0, 0, w * cell, edge),
                      pygame.Rect(0, h * cell - edge, w * cell, edge),
                      pygame.Rect(0, 0, edge, h * cell),
                      pygame.Rect(w * cell - edge, 0, edge, h * cell)):
                pygame.draw.rect(haze, (220, 30, 20, 95), r)
            self._screen.blit(haze, (0, 0))

        # K4/F4: carvings - the colonies' sentiment toward the keeper,
        # coloured by band (devout gold -> wary grey -> hateful red)
        if glyph_mode:
            for pos, symbol in (getattr(self.sim, 'carvings', None)
                                or {}).items():
                if self._visible_depth(pos) is not None:
                    self._blit_glyph(symbol, CARVE_COLORS.get(
                        symbol, (255, 235, 170)),
                        pos[0] * cell, pos[1] * cell)

        if getattr(self.sim, 'storm_until', 0) > self.sim.step_count:
            haze = pygame.transform.scale(
                pygame.surfarray.make_surface(storm_haze_array((w, h))),
                (w * cell, h * cell))
            self._screen.blit(haze, (0, 0), special_flags=pygame.BLEND_ADD)

        # W5 weather overlays: hail flicker, frost wash, the flood band
        step = self.sim.step_count
        if getattr(self.sim, 'hail_until', 0) > step:
            wash = pygame.Surface((w * cell, h * cell))
            wash.fill((240, 240, 255))
            wash.set_alpha(20 + (step % 3) * 12)  # flicker
            self._screen.blit(wash, (0, 0))
        if getattr(self.sim, 'cold_until', 0) > step:
            wash = pygame.Surface((w * cell, h * cell))
            wash.fill((150, 190, 255))
            wash.set_alpha(38)
            self._screen.blit(wash, (0, 0))
        if getattr(self.sim, 'flood_until', 0) > step:
            water = pygame.Surface((cell, cell))
            water.fill((40, 90, 220))
            water.set_alpha(110)
            for (x, y) in getattr(self.sim, 'flood_cells', None) or ():
                self._screen.blit(water, (x * cell, y * cell))
        if getattr(self.sim, 'kw_until', 0) > step:  # HH2: the hand's water
            kw = pygame.Surface((cell, cell))
            kw.fill((60, 140, 240))
            kw.set_alpha(90 if getattr(self.sim, 'kw_big', False) else 55)
            for (x, y) in getattr(self.sim, 'kw_cells', None) or ():
                self._screen.blit(kw, (x * cell, y * cell))

        # R32/R33: look cursor, target highlight, and the inspect panel
        if self.look_mode:
            cx, cy = self.cursor
            pygame.draw.rect(self._screen, (255, 215, 0),
                             pygame.Rect(cx * cell - 1, cy * cell - 1,
                                         cell + 2, cell + 2), 2)
            if (self.inspected is not None
                    and target_alive(self.sim, self.inspected)):
                tx, ty, _tz = target_position(self.inspected)
                pygame.draw.rect(self._screen, (255, 255, 255),
                                 pygame.Rect(tx * cell - 2, ty * cell - 2,
                                             cell + 4, cell + 4), 1)
            self._draw_look_panel()

        hud_x = w * cell + 12
        for i, (line, color) in enumerate(build_hud_entries(
                self.sim, self.pacer.steps_per_second,
                self.paused, self.z_level, self.capturing,
                self.view_mode, PHEROMONE_OVERLAYS[self.overlay_index])):
            if line:
                text = self._font.render(line, True, color)
                self._screen.blit(text, (hud_x, 10 + i * 18))

        if self.legend_open:
            self._draw_legend_sidebar(max(h * cell, 400))
        pygame.display.flip()

    def _render_manager(self, area_w: int, area_h: int) -> None:
        """Manager screen over the map area (SPEC_HIVE_MONITOR M5).

        The HUD panel stays live on the right; a tall stat block column-wraps
        (R34, the same fix as the legend) so it NEVER overflows area_h and cuts
        off — hidden state is untrustworthy state."""
        self._screen.fill(HUD_BG)
        pygame.draw.rect(self._screen, (30, 30, 40),
                         pygame.Rect(0, 0, area_w, area_h), 1)
        m_entries = build_manager_entries(self.sim, self.manager_colony)
        positions = legend_layout(len(m_entries), area_w, area_h,
                                  line_h=17, top=10, left=14)
        char_w = max(1, self._font.size("M")[0])
        for (line, color), (x, y) in zip(m_entries, positions):
            if line:
                # keep every row inside the map area so it can never bleed into the
                # HUD sidebar at area_w+12 (the old top-right garble)
                max_chars = max(4, (area_w - x - 6) // char_w)
                self._screen.blit(self._font.render(line[:max_chars], True, color), (x, y))

        hud_x = area_w + 12
        for i, (line, color) in enumerate(build_hud_entries(
                self.sim, self.pacer.steps_per_second,
                self.paused, self.z_level, self.capturing,
                self.view_mode, PHEROMONE_OVERLAYS[self.overlay_index])):
            if line:
                self._screen.blit(self._font.render(line, True, color),
                                  (hud_x, 10 + i * 18))
        pygame.display.flip()

    def _render_saga(self, area_w: int, area_h: int) -> None:
        """Saga screen over the map area (SPEC_DYNASTIES D5)."""
        self._screen.fill(HUD_BG)
        pygame.draw.rect(self._screen, (40, 36, 26),
                         pygame.Rect(0, 0, area_w, area_h), 1)
        entries = build_saga_entries(self.sim)
        max_rows = max(4, (area_h - 20) // 16)
        head, tail = entries[:3], entries[3:]
        for i, (line, color) in enumerate(head + tail[-(max_rows - 3):]):
            if line:
                self._screen.blit(self._font.render(line, True, color),
                                  (14, 10 + i * 16))
        hud_x = area_w + 12
        for i, (line, color) in enumerate(build_hud_entries(
                self.sim, self.pacer.steps_per_second,
                self.paused, self.z_level, self.capturing,
                self.view_mode, PHEROMONE_OVERLAYS[self.overlay_index])):
            if line:
                self._screen.blit(self._font.render(line, True, color),
                                  (hud_x, 10 + i * 18))
        pygame.display.flip()

    def _draw_look_panel(self) -> None:
        """R32/R33: the translucent look/inspect text box (all views)."""
        if not self.look_mode:
            return
        cx, cy = self.cursor
        panel = build_look_entries(self.sim, cx, cy,
                                   min(self.z_level,
                                       self.sim.world.depth - 1))
        if self.inspected is not None:
            panel += build_inspect_entries(self.sim, self.inspected)
            if self.follow:
                panel.append(("FOLLOWING (F releases)", (255, 215, 0)))
        box = pygame.Surface((330, len(panel) * 17 + 10))
        box.set_alpha(210)
        box.fill(HUD_BG)
        self._screen.blit(box, (6, 6))
        for i, (line, color) in enumerate(panel):
            if line:
                self._screen.blit(self._font.render(line, True, color),
                                  (12, 11 + i * 17))

    def _render_iso_map(self, area_w: int, area_h: int) -> None:
        """R36: the stonesense-style sprite map (painter's order s=x+y).

        Each column draws its top visible voxel (<= z_level) as a baked
        iso cube, then its water, fire, inhabitants, and (if placed)
        the look cursor - correct occlusion by construction.
        """
        from iso_sprites import (forge_beast, forge_bug, forge_cube,
                                 forge_cursor, forge_flame, forge_maw,
                                 forge_water)
        sim = self.sim
        w, h, depth = sim.world.width, sim.world.height, sim.world.depth
        tw, th, zs, ox, oy = iso_metrics(w, h, depth, area_w, area_h)
        found, depth_below, has_terrain, _own = topdown_cells(
            sim.world, self.z_level)
        occupants: dict = {}
        for colony in sim.colonies:
            for unit in colony.units:
                x, y, z = unit.position
                if z <= self.z_level:
                    occupants.setdefault((x, y), []).append(
                        ('unit', unit, colony))
            if colony.is_alive() and colony.maw.position[2] <= self.z_level:
                mx, my, _mz = colony.maw.position
                occupants.setdefault((mx, my), []).append(
                    ('maw', colony, None))
        for beast in getattr(sim, 'fauna', None) or []:
            x, y, z = beast.position
            if z <= self.z_level:
                occupants.setdefault((x, y), []).append(
                    ('beast', beast, None))
        fire_cols: dict = {}
        for (fx, fy, fz) in getattr(sim, 'fires', None) or {}:
            if fz <= self.z_level:
                fire_cols[(fx, fy)] = max(fz, fire_cols.get((fx, fy), -1))
        flooding = getattr(sim, 'flood_until', 0) > sim.step_count
        flood = getattr(sim, 'flood_cells', None) or set() if flooding \
            else set()
        water_z = (min(sim.world.surface_z(w // 2, h // 2) + 1, self.z_level)
                   if flooding else 0)

        for s in range(w + h - 1):
            for x in range(max(0, s - h + 1), min(w, s + 1)):
                y = s - x
                if not has_terrain[x, y]:
                    continue
                z = int(self.z_level - depth_below[x, y])
                sx, sy = iso_project(x, y, z, tw, zs, ox, oy)
                self._screen.blit(forge_cube(int(found[x, y]), tw, zs),
                                  (sx, sy))
                if (x, y) in flood:
                    wx, wy = iso_project(x, y, water_z, tw, zs, ox, oy)
                    self._screen.blit(forge_water(tw), (wx, wy))
                if (x, y) in fire_cols:
                    fx, fy = iso_project(x, y, fire_cols[(x, y)] + 1,
                                         tw, zs, ox, oy)
                    self._screen.blit(forge_flame(tw), (fx, fy - th))
                for kind, obj, extra in occupants.get((x, y), ()):
                    ez = (obj.maw.position[2] if kind == 'maw'
                          else obj.position[2])
                    ex, ey = iso_project(x, y, ez + 1, tw, zs, ox, oy)
                    if kind == 'unit':
                        sprite = forge_bug(obj.unit_type.name.lower(),
                                           extra.color, tw)
                    elif kind == 'maw':
                        sprite = forge_maw(obj.color, tw)
                    else:
                        sprite = forge_beast(obj.species, tw)
                    self._screen.blit(
                        sprite, (sx + tw // 2 - sprite.get_width() // 2,
                                 ey - sprite.get_height() // 2))
                if self.look_mode and self.cursor == (x, y):
                    cxp, cyp = iso_project(x, y, z + 1, tw, zs, ox, oy)
                    self._screen.blit(forge_cursor(tw), (cxp, cyp))

    def _draw_legend_sidebar(self, area_h: int) -> None:
        """Toggleable legend SIDEBAR (R34): an opaque strip over the map's LEFT edge so the terrarium
        stays visible (not a full-screen takeover). Column-wrapped to the narrow width; drawn after the
        map, before the flip. Uses a compact font so the whole legend fits."""
        w = LEGEND_SIDEBAR_W
        panel = pygame.Surface((w, area_h))
        panel.set_alpha(238)
        panel.fill(HUD_BG)
        self._screen.blit(panel, (0, 0))
        pygame.draw.rect(self._screen, (70, 70, 55), pygame.Rect(0, 0, w, area_h), 1)
        entries = build_legend_compact()
        line_h, top, left = 12, 5, 6
        max_rows = max(1, (area_h - 2 * top) // line_h)
        n_cols = max(1, (len(entries) + max_rows - 1) // max_rows)
        col_w = max(1, (w - left) // n_cols)
        char_w = max(1, self._legend_font.size("M")[0])
        max_chars = max(3, (col_w - 4) // char_w)        # keep each row inside its column (no bleed/overlap)
        positions = legend_layout(len(entries), w, area_h, line_h=line_h, top=top, left=left)
        for (line, color), (x, y) in zip(entries, positions):
            if line:
                self._screen.blit(self._legend_font.render(line[:max_chars], True, color), (x, y))

    def _visible_depth(self, position: Tuple[int, int, int]) -> Optional[int]:
        """Depth an entity renders at in the active view mode, None if hidden.

        SLICE shows only exact-z matches at depth 0; TOPDOWN applies the
        R13 look-down visibility rule.
        """
        if self.view_mode == ViewMode.SLICE:
            return 0 if position[2] == self.z_level else None
        return unit_visible_depth(self.sim.world, position, self.z_level)

    def _mirror_snapshot(self) -> None:
        """U8: throttled snapshot of the live glyph surface -> runner.glyph_png
        so the web console can mirror the desktop view. Main-thread only (reads
        the pygame surface); the byte-string ref swap is atomic under the GIL,
        so the web thread reads it without a lock."""
        now = pygame.time.get_ticks()
        if now - self._last_mirror_ms < MIRROR_MIN_MS:
            return
        self._last_mirror_ms = now
        from io import BytesIO

        from PIL import Image
        raw = pygame.image.tobytes(self._screen, "RGB")
        img = Image.frombytes("RGB", self._screen.get_size(), raw)
        buf = BytesIO()
        img.save(buf, "PNG")
        self.runner.glyph_png = buf.getvalue()

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
             steps_per_second: float = DEFAULT_STEPS_PER_SECOND,
             save_path: Optional[str] = None, serve: bool = False,
             host: str = "127.0.0.1", port: int = 8010,
             save_every: int = 600) -> None:
    """Entry point from sandkings.main(): the pygame window on the MAIN thread,
    driven by ONE shared TerrariumRunner (U1). When `serve`, the web console
    attaches to the SAME runner via uvicorn on a daemon thread (U5), so the
    on-screen and browser step counters are one and the same. Desktop-only
    (`serve=False`) imports no fastapi/uvicorn.

    A BOUNDED run (`max_steps` set - e.g. `--steps N`, and the test harness)
    is a deterministic headless batch: the viewer drives stepping itself and
    NO engine thread or web server is started, so the count lands exactly on
    `max_steps`. Only an OPEN-ENDED run attaches the background engine and the
    web console."""
    if max_steps is not None:
        LiveViewer(sim, steps_per_second=steps_per_second,
                   max_steps=max_steps, save_path=save_path).run()
        return
    from dashboard import TerrariumRunner
    runner = TerrariumRunner(sim, sps=steps_per_second, save_path=save_path,
                             save_every=save_every)
    runner.start()  # the single writer: background stepping under the lock
    server = None
    if serve:
        from dashboard import create_app
        import uvicorn
        config = uvicorn.Config(create_app(runner), host=host, port=port,
                                log_level="warning")
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
        print(f"[keeper] web console attached on http://{host}:{port}")
    try:
        LiveViewer(runner, steps_per_second=steps_per_second).run()
    finally:
        if server is not None:
            server.should_exit = True
        runner.stop()  # autosaves once
