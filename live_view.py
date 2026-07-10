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
    ISO = 2       # stonesense-style sprite view (R36)


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
    VoxelType.WEB.value: "x",
}
FIRE_GLYPH = "^"                    # burning-cell overlay (T46)
FIRE_COLOR = (255, 120, 0)
BEAST_GLYPHS = {                    # fauna bestiary (T48)
    'spider': "x", 'rabbit': "r", 'squirrel': "q", 'bird': "v",
    'rodent': "n", 'scorpion': "t", 'snake': "S", 'anteater': "A",
}
BEAST_COLOR = (200, 80, 220)        # violet: not of any colony
CARVE_COLORS = {                    # F4: sentiment carving colours by glyph
    '♥': (255, 235, 140),  # devout - gold
    '◦': (170, 170, 180),  # wary - pale grey
    '☠': (230, 70, 60),    # hateful - red
    '⌂': (150, 180, 255),  # machine-carved - blue
}
COPPER_TINT = (184, 115, 51)  # armored soldier letters (R22)
UNIT_GLYPHS = {UnitType.WORKER: "w", UnitType.SOLDIER: "s", UnitType.SCOUT: "c"}
MAW_GLYPH = "Ω"
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
        # W5: the weather line (nothing when clear)
        active = [(name, tint) for attr, name, tint in (
            ("storm_until", "sandstorm", (200, 180, 110)),
            ("hail_until", "hail", (235, 235, 245)),
            ("flood_until", "flash flood", (90, 140, 255)),
            ("cold_until", "killing frost", (170, 210, 255)),
        ) if getattr(sim, attr, 0) > sim.step_count]
        if active:
            entries.insert(5, ("Weather: " + ", ".join(n for n, _t in active),
                               active[0][1]))
        if getattr(sim, 'drought', False):  # K1: the withheld dole
            entries.insert(5, ("DROUGHT - the keeper withholds",
                               (255, 80, 80)))
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
                      "KEEPER: 1 food  2/3/4 bugs  5 gift",
                      "        9 drought  0 cat  T speak"):
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
        entries.append((f"  posture {posture}"
                        + (f"   mem+{aug}" if aug else ""), (170, 200, 140)))
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
    if carving:  # F4: name the sentiment a carving expresses
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
        entries.append((f" {glyph}  {species} (wild)", BEAST_COLOR))
    entries.append((f" {FIRE_GLYPH}  fire", FIRE_COLOR))
    entries.append(("", HUD_FG))
    entries.append(("-- carvings: sentiment toward you (F) --",
                    (150, 150, 160)))
    from sandkings import CARVE_SYMBOLS
    carve_names = {'devout': "devout - they love their god",
                   'wary': "wary - impassive, watching",
                   'hateful': "hateful - the god has soured (look to it!)",
                   'machine': "machine-carved (the terminal)"}
    for key, symbol in CARVE_SYMBOLS.items():
        entries.append((f" {symbol}  {carve_names.get(key, key)}",
                        CARVE_COLORS.get(symbol, (255, 235, 170))))
    entries.append(("", HUD_FG))
    entries.append(("-- colors --", (150, 150, 160)))
    entries.append((" copper letter = armored soldier", COPPER_TINT))
    entries.append((" magenta = retreating", (255, 0, 255)))
    entries.append((" gold w = tribute envoy", (255, 200, 60)))
    entries.append((" violet = wild beast", BEAST_COLOR))
    entries.append(("", HUD_FG))
    entries.append(("L close   I inspect cursor", (140, 140, 150)))
    return entries


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
        from politics import FRIENDLY, HOSTILE, NEMESIS
        entries.append(("RELATIONS  ->out <-in", (120, 180, 220)))
        for other in sim.colonies:
            if other.colony_id == colony_id:
                continue
            out_t = diplomacy.trust(colony_id, other.colony_id)
            in_t = diplomacy.trust(other.colony_id, colony_id)
            if diplomacy.ally(colony_id, other.colony_id):
                standing = "ALLY"
            elif out_t <= NEMESIS:
                standing = "NEMESIS"
            elif out_t <= HOSTILE:
                standing = "hostile"
            elif out_t >= FRIENDLY:
                standing = "friendly"
            else:
                standing = "neutral"
            extra = ""
            key = frozenset((colony_id, other.colony_id))
            if key in diplomacy.truce_until:
                left = max(0, diplomacy.truce_until[key] - sim.step_count)
                extra += f" truce:{left}"
            if diplomacy.war_target.get(other.colony_id) == colony_id:
                extra += " [WAR->us]"
            if diplomacy.war_target.get(colony_id) == other.colony_id:
                extra += " [WAR->them]"
            entries.append((f"  C{other.colony_id} {out_t:+4.0f} {in_t:+4.0f}"
                            f"  {standing}{extra}",
                            hud_text_color(other.color)))
        entries.append(("", HUD_FG))

    entries.append(("CONCEPTS  acc%/active", (120, 180, 220)))
    rows = monitor.concept_rows(sim, colony) if colony.is_alive() else []
    for i in range(0, len(rows), 2):
        parts = []
        for name, acc, active in rows[i:i + 2]:
            marker = "*" if active else " "
            parts.append(f"{name:>11} {acc * 100:3.0f}% {active:2d}{marker}")
        entries.append(("  ".join(parts), HUD_FG))

    entries.append(("", HUD_FG))
    entries.append(("TOP SOLDIERS", (120, 180, 220)))
    soldiers = [u for u in colony.units if u.unit_type == UnitType.SOLDIER]
    if neural:
        soldiers.sort(key=lambda u: (u.brain_layer.get_performance_score()
                                     if u.brain_layer else 0.0), reverse=True)
    else:
        soldiers.sort(key=lambda u: u.health, reverse=True)
    for unit in soldiers[:5]:
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

    def __init__(self, sim: SandKingsSimulation, cell_size: int = DEFAULT_CELL_SIZE,
                 steps_per_second: float = DEFAULT_STEPS_PER_SECOND,
                 max_steps: Optional[int] = None,
                 save_path: Optional[str] = None):
        self.save_path = save_path  # sqlite terrarium db (spec T13); None = off
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
        self.manager_open = False   # SPEC_HIVE_MONITOR M5
        self.manager_colony = 0
        self.saga_open = False      # SPEC_DYNASTIES D5
        self.legend_open = False    # R34
        self.look_mode = False      # R32 look cursor
        self.cursor = (sim.world.width // 2, sim.world.height // 2)
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
            if self.save_path:
                self._save_terrarium()
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
            elif self.look_mode and key in (pygame.K_UP, pygame.K_DOWN,
                                            pygame.K_LEFT, pygame.K_RIGHT):
                dx = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1}.get(key, 0)
                dy = {pygame.K_UP: -1, pygame.K_DOWN: 1}.get(key, 0)
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
                self.render_style = (RenderStyle.BLOCKS
                                     if self.render_style == RenderStyle.GLYPH
                                     else RenderStyle.GLYPH)
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
            # K1/K6/K9/K12: the keeper's hands (any keeper key disarms auto)
            elif key == pygame.K_1:
                self.sim.keeper_auto = False
                if not self.look_mode:
                    self.look_mode = True
                self.sim.keeper_drop_food(*self.cursor)
            elif key == pygame.K_2:
                self.sim.keeper_auto = False
                self.sim.keeper_release('cricket')
            elif key == pygame.K_3:
                self.sim.keeper_auto = False
                self.sim.keeper_release('ant')
            elif key == pygame.K_4:
                self.sim.keeper_auto = False
                self.sim.keeper_release('scorpion')
            elif key == pygame.K_5:
                self.sim.keeper_auto = False
                self.sim.keeper_gift(pos=self.cursor)
            elif key == pygame.K_9:
                self.sim.keeper_auto = False
                self.sim.keeper_drought(not getattr(self.sim, 'drought',
                                                    False))
            elif key == pygame.K_0:
                self.sim.keeper_auto = False
                self.sim.keeper_release_cat()
            elif (key == pygame.K_t and self.inspected is not None
                  and self.inspected[0] == 'unit'
                  and target_alive(self.sim, self.inspected)):
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
                self._save_terrarium()
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

        if self.manager_open:
            self._render_manager(w * cell, max(h * cell, 400))
            return
        if self.saga_open:
            self._render_saga(w * cell, max(h * cell, 400))
            return
        if self.legend_open:
            self._render_legend(w * cell, max(h * cell, 400))
            return

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
            pygame.display.flip()
            return

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
                    if getattr(unit, 'gift_to', -1) >= 0:  # envoy caravan (P13)
                        color = (255, 200, 60)
                    elif unit.retreating:
                        color = border
                    elif getattr(unit, 'armored', False):  # copper armor (R22)
                        color = tuple(int(c * depth_shade(depth)) for c in COPPER_TINT)
                    else:
                        color = hud_text_color(fill)
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

        # Wild beasts (T48): violet letters of no colony
        for beast in getattr(self.sim, 'fauna', None) or []:
            depth = self._visible_depth(beast.position)
            if depth is None:
                continue
            bx, by = beast.position[0], beast.position[1]
            color = tuple(int(c * depth_shade(depth)) for c in BEAST_COLOR)
            if glyph_mode:
                self._blit_glyph(BEAST_GLYPHS.get(beast.species, "?"), color,
                                 bx * cell, by * cell)
            else:
                rect = pygame.Rect(bx * cell + 1, by * cell + 1,
                                   cell - 2, cell - 2)
                pygame.draw.rect(self._screen, color, rect)

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

        pygame.display.flip()

    def _render_manager(self, area_w: int, area_h: int) -> None:
        """Manager screen over the map area (SPEC_HIVE_MONITOR M5).

        The HUD panel stays live on the right; overflow rows clip."""
        self._screen.fill(HUD_BG)
        pygame.draw.rect(self._screen, (30, 30, 40),
                         pygame.Rect(0, 0, area_w, area_h), 1)
        for i, (line, color) in enumerate(
                build_manager_entries(self.sim, self.manager_colony)):
            if line:
                self._screen.blit(self._font.render(line, True, color),
                                  (14, 10 + i * 17))

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

    def _render_legend(self, area_w: int, area_h: int) -> None:
        """Legend screen over the map area (R34)."""
        self._screen.fill(HUD_BG)
        pygame.draw.rect(self._screen, (36, 36, 30),
                         pygame.Rect(0, 0, area_w, area_h), 1)
        for i, (line, color) in enumerate(build_legend_entries()):
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

    def _visible_depth(self, position: Tuple[int, int, int]) -> Optional[int]:
        """Depth an entity renders at in the active view mode, None if hidden.

        SLICE shows only exact-z matches at depth 0; TOPDOWN applies the
        R13 look-down visibility rule.
        """
        if self.view_mode == ViewMode.SLICE:
            return 0 if position[2] == self.z_level else None
        return unit_visible_depth(self.sim.world, position, self.z_level)

    def _save_terrarium(self) -> None:
        """Checkpoint the sim into the sqlite terrarium db (spec T13)."""
        from sandkings import save_checkpoint
        save_checkpoint(self.sim, self.save_path)
        print(f"[S] Terrarium saved to {self.save_path} at step {self.sim.step_count}")

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
             save_path: Optional[str] = None) -> None:
    """Entry point from sandkings.main(): open the live window and block until done."""
    LiveViewer(sim, steps_per_second=steps_per_second, max_steps=max_steps,
               save_path=save_path).run()
