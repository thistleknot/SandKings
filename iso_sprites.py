"""The sprite forge: procedurally baked pixel-art for the ISO view (R36).

Purpose: stonesense-style sprites without external assets - every iso
cube, creature, and effect sprite is drawn programmatically from the
live palette, so new voxel types and species can never be missing and
the look always matches the glyph renderers' colors.

Preconditions: pygame imported and display/surface support initialized
(SDL dummy driver is fine - only Surfaces are used, never the screen).
Failure modes: none fatal; unknown kinds fall back to a plain cube or
a plain dot sprite. All forging is deterministic per (kind, size, tint):
a seeded local RNG paints the pixel detail, and results are cached.
"""

import random
from typing import Dict, Optional, Tuple

import pygame

from sandkings import VoxelType

_CACHE: Dict[tuple, "pygame.Surface"] = {}

# per-material pixel detail painters are keyed by voxel value below;
# face shading follows classic iso lighting: top 1.0, left .72, right .5
FACE_TOP, FACE_LEFT, FACE_RIGHT = 1.0, 0.72, 0.5


def _shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _rng(*key) -> random.Random:
    return random.Random(hash(key) & 0x7FFFFFFF)


def _diamond_points(tw: int, th: int, cy: int = 0):
    """Top-face diamond of an iso cube whose top-left bbox corner is 0,0."""
    return [(tw // 2, cy), (tw, cy + th // 2),
            (tw // 2, cy + th), (0, cy + th // 2)]


def forge_cube(voxel_value: int, tw: int, zs: int) -> "pygame.Surface":
    """One iso terrain cube: top diamond + left/right faces + detail.

    Surface size is (tw, th + zs) where th = tw // 2; the cube's top
    face starts at y=0 so callers blit at (sx, sy) from iso_project.
    """
    key = ("cube", voxel_value, tw, zs)
    if key in _CACHE:
        return _CACHE[key]
    from live_view import build_voxel_palette
    th = tw // 2
    base = tuple(int(c) for c in build_voxel_palette()[voxel_value])
    surf = pygame.Surface((tw, th + zs), pygame.SRCALPHA)
    top = _diamond_points(tw, th)
    pygame.draw.polygon(surf, _shade(base, FACE_TOP), top)
    left = [(0, th // 2), (tw // 2, th), (tw // 2, th + zs), (0, th // 2 + zs)]
    right = [(tw // 2, th), (tw, th // 2), (tw, th // 2 + zs), (tw // 2, th + zs)]
    pygame.draw.polygon(surf, _shade(base, FACE_LEFT), left)
    pygame.draw.polygon(surf, _shade(base, FACE_RIGHT), right)
    pygame.draw.polygon(surf, _shade(base, 0.35), top, 1)  # crisp edge

    rng = _rng("detail", voxel_value, tw)
    v = voxel_value

    def speck(n, color, on_top=True):
        for _ in range(n):
            px = rng.randrange(tw // 4, 3 * tw // 4)
            py = (rng.randrange(th // 4, 3 * th // 4) if on_top
                  else rng.randrange(th, th + zs))
            surf.set_at((px, py), color)

    if v == VoxelType.SAND.value:
        speck(max(3, tw // 3), _shade(base, 1.25))
        speck(max(2, tw // 4), _shade(base, 0.8))
    elif v == VoxelType.STONE.value:
        speck(max(3, tw // 3), _shade(base, 1.6))
        if tw >= 10:  # a crack
            pygame.draw.line(surf, _shade(base, 0.5),
                             (tw // 3, th // 2), (2 * tw // 3, th // 3))
    elif v in (VoxelType.COPPER_ORE.value, VoxelType.GOLD_ORE.value):
        glint = (255, 240, 180) if v == VoxelType.GOLD_ORE.value \
            else (255, 190, 140)
        speck(max(3, tw // 3), glint)
    elif v == VoxelType.FOOD.value:
        speck(max(3, tw // 3), (120, 255, 120))
    elif v == VoxelType.CORPSE.value:
        speck(max(2, tw // 4), (230, 225, 210))  # bone flecks
    elif v in (VoxelType.CROP.value, VoxelType.CROP_RIPE.value):
        blades = max(2, tw // 5)
        tip = ((250, 240, 120) if v == VoxelType.CROP_RIPE.value
               else (90, 200, 80))
        for _ in range(blades):
            bx = rng.randrange(tw // 4, 3 * tw // 4)
            by = rng.randrange(th // 4, 3 * th // 4)
            pygame.draw.line(surf, tip, (bx, by), (bx, max(0, by - th // 2)))
    elif v == VoxelType.WOOD.value:
        pygame.draw.ellipse(surf, _shade(base, 1.3),
                            pygame.Rect(tw // 3, th // 4, tw // 3, th // 3), 1)
    elif v == VoxelType.WOOD_WALL.value:
        for fx in range(tw // 6, tw, max(2, tw // 5)):  # stake lines
            pygame.draw.line(surf, _shade(base, 0.6),
                             (fx, th), (fx, th + zs - 1))
    elif v == VoxelType.WEB.value:
        c = (235, 235, 245)
        for pa, pb in ((top[0], top[2]), (top[1], top[3])):
            pygame.draw.line(surf, c, pa, pb)
    elif v == VoxelType.HULL.value:
        speck(max(2, tw // 4), (200, 210, 230))  # rivets
    elif v == VoxelType.SALVAGE.value:
        speck(max(3, tw // 3), (120, 240, 240))  # live circuitry
    elif v == VoxelType.GLASS.value:
        pygame.draw.polygon(surf, (255, 255, 255), top, 1)

    _CACHE[key] = surf
    return surf


def forge_water(tw: int) -> "pygame.Surface":
    """Translucent flood-water diamond (W1 inundation surface)."""
    key = ("water", tw)
    if key in _CACHE:
        return _CACHE[key]
    th = tw // 2
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (50, 110, 230, 150), _diamond_points(tw, th))
    pygame.draw.polygon(surf, (160, 200, 255, 180), _diamond_points(tw, th), 1)
    _CACHE[key] = surf
    return surf


def forge_flame(tw: int) -> "pygame.Surface":
    key = ("flame", tw)
    if key in _CACHE:
        return _CACHE[key]
    th = max(6, tw)
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (255, 120, 0, 230),
                        [(tw // 2, 0), (tw - 2, th - 1), (2, th - 1)])
    pygame.draw.polygon(surf, (255, 230, 90, 230),
                        [(tw // 2, th // 3), (2 * tw // 3, th - 2),
                         (tw // 3, th - 2)])
    _CACHE[key] = surf
    return surf


def forge_bug(caste: str, tint: Tuple[int, int, int],
              tw: int) -> "pygame.Surface":
    """A sand king: segmented bug body, colony-tinted (R36).

    castes: 'worker' (round hauler), 'soldier' (broad, mandibles),
    'scout' (slim, long legs). Size scales with the tile.
    """
    key = ("bug", caste, tint, tw)
    if key in _CACHE:
        return _CACHE[key]
    s = max(8, tw)
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    rng = _rng("bug", caste)
    body = _shade(tint, 0.9)
    dark = _shade(tint, 0.55)
    cx, cy = s // 2, s // 2
    if caste == 'soldier':
        seg = [(cx, cy + s // 5, s // 3), (cx, cy - s // 8, s // 4),
               (cx, cy - s // 3, s // 5)]
    elif caste == 'scout':
        seg = [(cx, cy + s // 4, s // 5), (cx, cy, s // 6),
               (cx, cy - s // 4, s // 7)]
    else:
        seg = [(cx, cy + s // 6, s // 4), (cx, cy - s // 6, s // 5)]
    for i, (bx, by, r) in enumerate(seg):
        pygame.draw.circle(surf, body if i % 2 == 0 else dark, (bx, by), r)
    legs = 4 if caste != 'scout' else 3
    span = s // 2 if caste != 'scout' else 2 * s // 3
    for i in range(legs):
        ly = cy - s // 4 + i * max(2, s // (legs + 1))
        pygame.draw.line(surf, dark, (cx - s // 6, ly), (cx - span // 2, ly + 2))
        pygame.draw.line(surf, dark, (cx + s // 6, ly), (cx + span // 2, ly + 2))
    if caste == 'soldier':  # mandibles
        top = seg[-1]
        pygame.draw.line(surf, dark, (top[0] - 2, top[1] - top[2]),
                         (top[0] - s // 4, top[1] - top[2] - s // 6), 2)
        pygame.draw.line(surf, dark, (top[0] + 2, top[1] - top[2]),
                         (top[0] + s // 4, top[1] - top[2] - s // 6), 2)
    _CACHE[key] = surf
    return surf


def forge_maw(tint: Tuple[int, int, int], tw: int) -> "pygame.Surface":
    """The queen: a fleshy mound with a dark maw-mouth."""
    key = ("maw", tint, tw)
    if key in _CACHE:
        return _CACHE[key]
    s = max(12, tw * 2)
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    pygame.draw.ellipse(surf, _shade(tint, 0.8),
                        pygame.Rect(s // 8, s // 3, 3 * s // 4, s // 2))
    pygame.draw.ellipse(surf, _shade(tint, 1.15),
                        pygame.Rect(s // 5, s // 4, 3 * s // 5, s // 2))
    pygame.draw.ellipse(surf, (25, 10, 15),
                        pygame.Rect(2 * s // 5, s // 2, s // 5, s // 7))
    _CACHE[key] = surf
    return surf


_BEAST_BUILDERS = {}


def forge_beast(species: str, tw: int) -> "pygame.Surface":
    """One wild beast sprite; every BEAST_GLYPHS species is covered."""
    key = ("beast", species, tw)
    if key in _CACHE:
        return _CACHE[key]
    s = max(10, tw + tw // 2)
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    violet = (200, 80, 220)
    dark = _shade(violet, 0.55)
    cx, cy = s // 2, s // 2
    if species == 'spider':
        pygame.draw.circle(surf, dark, (cx, cy), s // 5)
        for i in range(4):
            dy = (i - 1.5) * (s // 6)
            pygame.draw.line(surf, dark, (cx, cy), (2, int(cy + dy)))
            pygame.draw.line(surf, dark, (cx, cy), (s - 3, int(cy + dy)))
    elif species == 'rabbit':
        fur = (200, 185, 160)
        pygame.draw.ellipse(surf, fur, pygame.Rect(s // 6, cy - s // 6,
                                                   2 * s // 3, s // 3))
        pygame.draw.circle(surf, fur, (s - s // 4, cy - s // 8), s // 7)
        for dx in (-2, 2):  # ears
            pygame.draw.line(surf, fur, (s - s // 4 + dx, cy - s // 5),
                             (s - s // 4 + dx, cy - s // 2), 2)
    elif species == 'squirrel':
        fur = (170, 110, 60)
        pygame.draw.circle(surf, fur, (cx, cy), s // 6)
        pygame.draw.circle(surf, _shade(fur, 1.2), (cx - s // 4, cy - s // 8),
                           s // 5)  # the tail is the point
    elif species == 'bird':
        wing = (90, 90, 110)
        pygame.draw.polygon(surf, wing, [(2, cy), (cx, cy - s // 3),
                                         (s - 3, cy), (cx, cy - s // 8)])
    elif species == 'scorpion':
        amber = (220, 170, 60)
        pygame.draw.ellipse(surf, amber, pygame.Rect(s // 5, cy - s // 10,
                                                     s // 2, s // 5))
        pygame.draw.arc(surf, amber, pygame.Rect(cx, cy - s // 2,
                                                 s // 3, s // 2), 0, 3.0, 2)
    elif species == 'snake':
        green = (110, 160, 80)
        pts = [(2 + i * (s - 4) // 5,
                cy + (s // 6 if i % 2 else -s // 6)) for i in range(6)]
        pygame.draw.lines(surf, green, False, pts, max(2, s // 6))
    elif species == 'rodent':
        gray = (150, 140, 130)
        pygame.draw.ellipse(surf, gray, pygame.Rect(s // 4, cy - s // 8,
                                                    s // 2, s // 4))
        pygame.draw.line(surf, gray, (s // 4, cy), (2, cy + s // 8))
    elif species == 'anteater':
        brown = (120, 90, 70)
        pygame.draw.ellipse(surf, brown, pygame.Rect(s // 6, cy - s // 5,
                                                     2 * s // 3, 2 * s // 5))
        pygame.draw.line(surf, brown, (5 * s // 6, cy - s // 10),
                         (s - 2, cy + s // 10), 3)  # the snout
    else:  # unknown species: readable fallback dot
        pygame.draw.circle(surf, violet, (cx, cy), s // 4)
    _CACHE[key] = surf
    return surf


def forge_cursor(tw: int) -> "pygame.Surface":
    key = ("cursor", tw)
    if key in _CACHE:
        return _CACHE[key]
    th = tw // 2
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (255, 215, 0), _diamond_points(tw, th), 2)
    _CACHE[key] = surf
    return surf
