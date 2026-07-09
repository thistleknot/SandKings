"""
Sand Kings Simulation
Combines Core War's evolution with 1pageskirmish's tactics in a 3D voxel terrarium

Inspired by GRRM's Sand Kings novella - 4 colored Maw colonies compete for territory
"""

import itertools
import os
import pickle
import random
import sqlite3
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
from typing import List, Tuple, Set, Optional, Dict
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from PIL import Image
import io
from tqdm import tqdm
import torch

# Neural hive mind
try:
    from neural_hive import (
        HiveMindBrain, SoldierLayer,
        encode_soldier_state, decode_soldier_action
    )
    NEURAL_AVAILABLE = True
except ImportError:
    NEURAL_AVAILABLE = False
    print("Warning: neural_hive.py not found. Neural mode disabled.")

# ============================================================================
# VOXEL TYPES & WORLD
# ============================================================================

# Terrarium liveness constants (SPEC_TERRARIUM_LIVENESS.md)
MAINTENANCE_COST = 0.1       # food per unit per step
FEED_INTERVAL = 100          # steps between keeper feedings
TARGET_POP = 18              # sustainable units per colony (feed sizing)
HARVEST_YIELD = 15           # food per FOOD/CORPSE voxel harvested
BOOTSTRAP_FLOOR = 10         # minimum colony food after each feeding
STARVATION_MAX_KILLS = 2     # starvation deaths per colony per step
UNIT_CAP = 30                # max units per colony (spawn gate)
MAW_MAX_HEALTH = 500
MAW_REGEN = 0.5              # HP per step while unbesieged
RESPAWN_DELAY = 300          # steps a fallen colony slot stays empty
RESPAWN_FOOD = 50            # starting food for an arriving colony
WAR_CHEST = 400              # food hoard that sends a colony to war (SPEC T10)
SCOUT_ALARM_RANGE = 5        # Manhattan distance that triggers a scout alarm (SPEC T11)
KNOWN_FOOD_CAP = 8           # shared food-intel entries per colony (SPEC T11)
MAW_MIGRATE_HEALTH = 0.4     # HP fraction below which a Maw flees (SPEC T15)
MAW_MIGRATE_COST = 2.0       # food per step of Maw flight
STORM_INTERVAL = 600         # steps between storm rolls (SPEC T12)
STORM_CHANCE = 0.5           # probability a roll spawns a storm
STORM_DURATION = 25          # steps a storm blows
STORM_COLUMNS_FRACTION = 1 / 50  # surface columns disturbed per storm step

# Seasons & Stone constants (SPEC_SEASONS_AND_STONE.md)
SEASON_LENGTH = 400          # steps per season (T16)
SEASONS = ("Flood", "Growth", "Dust", "Chill")
YEAR_LENGTH = 4 * SEASON_LENGTH
DOLE_FACTOR = {0: 1.00, 1: 0.75, 2: 0.50, 3: 0.25}   # by season index (T17)
DOLE_RAMP = (1.00, 0.50, 0.00)                        # per-year floor on the factor
STORM_INTERVAL_DUST = 200    # Dust season storm cadence (T16)
SPOIL_INTERVAL = 10          # Dust spoilage sweep cadence
SPOIL_CHANCE = 0.02          # per exposed FOOD voxel per sweep
SEED_COST = 5                # food paid at sowing (T19)
CROP_TICK = 5                # crop growth phase cadence
CROP_GROWDUR = 300           # grow-steps to ripen (DF GROWDUR range)
CROP_YIELD = 40              # food per ripe crop harvested
FARM_RADIUS = 6              # plots within this Chebyshev xy of own maw
FARM_MAX_PLOTS = 12          # per colony
FARM_START_FOOD = 60         # farming flag on above this...
FARM_STOP_FOOD = 30          # ...off below this (hysteresis)
GROW_SEASONS = (0, 1)        # Flood, Growth (T20)
OASIS_RADIUS = 6             # disc at map center (T22)
OASIS_GROWTH_MULT = 2
OASIS_FEED_BONUS = 2         # keeper voxels placed inside the disc
COPPER_VEINS_PER_BAND = 2    # ore generation (T23)
GOLD_CLUSTERS = 3
MINE_TIME = 5                # worker-steps per ore voxel (T24)
COPPER_ARMOR_HP = 10         # bonus max HP per armored soldier (T25)


class VoxelType(Enum):
    AIR = 0
    SAND = 1           # Tunnelable, movable
    STONE = 2          # Immovable substrate
    GLASS = 3          # Terrarium walls
    FOOD = 4           # Resource nodes
    CORPSE = 5         # Dead units = food
    TUNNEL_WALL = 6    # Reinforced colony walls
    TILLED = 7         # Worked soil, plantable (T19)
    CROP = 8           # Growing plant - not food to anyone
    CROP_RIPE = 9      # Harvestable - food to everyone
    COPPER_ORE = 10    # Vein ore in strata stone (T23)
    GOLD_ORE = 11      # Deep cluster ore, non-renewable

    def is_tunnelable(self):
        return self in (VoxelType.SAND, VoxelType.AIR)

    def is_solid(self):
        return self in (VoxelType.STONE, VoxelType.GLASS, VoxelType.TUNNEL_WALL,
                        VoxelType.COPPER_ORE, VoxelType.GOLD_ORE)

def box_blur(field: np.ndarray, passes: int = 2) -> np.ndarray:
    """Neighbor-mean smoothing via np.roll (wraps at edges); 2D or 3D fields."""
    for _ in range(passes):
        acc = field.copy()
        count = 1
        for axis in range(field.ndim):
            acc = acc + np.roll(field, 1, axis) + np.roll(field, -1, axis)
            count += 2
        field = acc / count
    return field


def value_noise(shape: Tuple[int, ...], cells: int, rng: np.random.Generator,
                octaves: int = 3) -> np.ndarray:
    """Multi-octave value noise in [0, 1] for a 2D or 3D shape (numpy only).

    Each octave draws a coarse random grid (cells * 2^octave per axis,
    capped at the axis size), upsamples by repetition, box-blurs, and sums
    with halving amplitude.
    """
    total = np.zeros(shape, dtype=np.float32)
    amplitude, total_amp = 1.0, 0.0
    for octave in range(octaves):
        coarse_shape = [max(1, min(s, cells * (2 ** octave))) for s in shape]
        coarse = rng.random(coarse_shape).astype(np.float32)
        fine = coarse
        for axis, (s, cs) in enumerate(zip(shape, coarse_shape)):
            fine = np.repeat(fine, -(-s // cs), axis=axis)
        fine = box_blur(fine[tuple(slice(0, s) for s in shape)], passes=2)
        total += amplitude * fine
        total_amp += amplitude
        amplitude *= 0.5
    total /= total_amp
    tmin, tmax = float(total.min()), float(total.max())
    if tmax > tmin:
        total = (total - tmin) / (tmax - tmin)
    return total


class VoxelWorld:
    """800x400x200 3D voxel terrarium with physics"""

    def __init__(self, width=80, height=40, depth=20, seed: Optional[int] = None):
        self.dimensions = (width, height, depth)
        self.width, self.height, self.depth = width, height, depth
        # seed=None derives from the global NumPy stream so np.random.seed()
        # in tests makes terrain reproducible; unseeded runs stay random
        if seed is None:
            seed = int(np.random.randint(0, 2**31))
        self.rng = np.random.default_rng(seed)

        # Core voxel data
        self.voxels = np.full(self.dimensions, VoxelType.AIR.value, dtype=np.uint8)
        self.ownership = np.full(self.dimensions, -1, dtype=np.int8)  # -1 = unowned
        self.stability = np.ones(self.dimensions, dtype=np.float32)

        # Initialize terrain
        self._generate_terrain()
    
    def _generate_terrain(self):
        """DF-style strata terrain: dune heightmap, stone bands, caverns, food.

        Spec: SPEC_TERRARIUM_LIVENESS.md T8. Guarantees: glass shell intact,
        surface heights in [substrate+2, 0.85*depth], cavern roofs cemented
        to STONE, world gravity-settled on return (apply_gravity is a no-op).
        Degrades at depth < 8 (caverns skipped, bands clamped).
        """
        w, h, d = self.dimensions
        rng = self.rng
        zs = np.arange(d)[None, None, :]

        # Stone substrate (bottom 20%)
        substrate_height = d // 5
        self.voxels[:, :, :substrate_height] = VoxelType.STONE.value

        # Dune heightmap: per-column surface height from 3-octave value noise
        h_min = substrate_height + 2
        h_max = max(h_min + 1, int(d * 0.85))
        heightmap = value_noise((w, h), cells=6, rng=rng)
        surface = (h_min + heightmap * (h_max - h_min)).astype(int)

        # Fill sand up to each column's surface
        sand_mask = (zs >= substrate_height) & (zs < surface[:, :, None])
        self.voxels[sand_mask] = VoxelType.SAND.value

        # Stone strata: two noise-thresholded bands, thickness 2
        for band_base in (substrate_height + 2, int(d * 0.45)):
            band_mask = value_noise((w, h), cells=8, rng=rng) > 0.55
            for z in range(band_base, min(band_base + 2, d)):
                layer = self.voxels[:, :, z]
                layer[band_mask & (layer == VoxelType.SAND.value)] = VoxelType.STONE.value

        # Caverns: 3D-noise air pockets inside the sand body, roofs cemented
        # so gravity cannot collapse them column by column
        if d >= 8:
            cave_noise = value_noise((w, h, d), cells=5, rng=rng)
            depth_ok = (zs >= substrate_height + 1) & (zs < np.maximum(surface[:, :, None] - 3, 0))
            cavern = ((cave_noise > np.quantile(cave_noise, 0.92)) & depth_ok &
                      (self.voxels == VoxelType.SAND.value))
            self.voxels[cavern] = VoxelType.AIR.value
            above_cavern = np.roll(cavern, 1, axis=2)
            above_cavern[:, :, 0] = False
            roof = above_cavern & (self.voxels == VoxelType.SAND.value)
            self.voxels[roof] = VoxelType.STONE.value

        # Ore (T23): copper veins threaded through the strata bands, gold
        # clusters at the substrate top. Hosted in STONE only; every vein
        # face touches diggable sand, so mining exposes the next voxel
        if d >= 8:
            for band_base in (substrate_height + 2, int(d * 0.45)):
                band_top = min(band_base + 2, d)
                for _ in range(COPPER_VEINS_PER_BAND):
                    vx = int(rng.integers(2, w - 2))
                    vy = int(rng.integers(2, h - 2))
                    for _ in range(int(rng.integers(8, 17))):
                        vz = int(rng.integers(band_base, band_top))
                        if self.voxels[vx, vy, vz] == VoxelType.STONE.value:
                            self.voxels[vx, vy, vz] = VoxelType.COPPER_ORE.value
                        vx = int(np.clip(vx + rng.integers(-1, 2), 2, w - 3))
                        vy = int(np.clip(vy + rng.integers(-1, 2), 2, h - 3))
            for _ in range(GOLD_CLUSTERS):
                gx = int(rng.integers(2, w - 2))
                gy = int(rng.integers(2, h - 2))
                for _ in range(int(rng.integers(3, 7))):
                    gz = int(rng.integers(max(1, substrate_height - 2), substrate_height))
                    if self.voxels[gx, gy, gz] == VoxelType.STONE.value:
                        self.voxels[gx, gy, gz] = VoxelType.GOLD_ORE.value
                    gx = int(np.clip(gx + rng.integers(-1, 2), 2, w - 3))
                    gy = int(np.clip(gy + rng.integers(-1, 2), 2, h - 3))

        # Glass walls + floor (applied last so they always win)
        self.voxels[0, :, :] = VoxelType.GLASS.value
        self.voxels[-1, :, :] = VoxelType.GLASS.value
        self.voxels[:, 0, :] = VoxelType.GLASS.value
        self.voxels[:, -1, :] = VoxelType.GLASS.value
        self.voxels[:, :, 0] = VoxelType.GLASS.value

        # Surface food patches
        for _ in range(4):
            px, py = int(rng.integers(2, w - 2)), int(rng.integers(2, h - 2))
            for _ in range(int(rng.integers(4, 7))):
                fx = int(np.clip(px + rng.integers(-3, 4), 1, w - 2))
                fy = int(np.clip(py + rng.integers(-3, 4), 1, h - 2))
                fz = self.surface_z(fx, fy) + 1
                if fz < d and self.voxels[fx, fy, fz] == VoxelType.AIR.value:
                    self.voxels[fx, fy, fz] = VoxelType.FOOD.value

        # Buried food pockets
        for _ in range((w * h) // 400):
            fx, fy = int(rng.integers(1, w - 1)), int(rng.integers(1, h - 1))
            top = self.surface_z(fx, fy)
            if top > substrate_height + 1:
                fz = int(rng.integers(substrate_height + 1, top))
                for _ in range(int(rng.integers(1, 4))):
                    bx = int(np.clip(fx + rng.integers(-1, 2), 1, w - 2))
                    by = int(np.clip(fy + rng.integers(-1, 2), 1, h - 2))
                    if self.voxels[bx, by, fz] == VoxelType.SAND.value:
                        self.voxels[bx, by, fz] = VoxelType.FOOD.value

        # Settle any loose sand so post-gen gravity is a no-op
        for _ in range(3):
            self.apply_gravity()

    def surface_z(self, x: int, y: int) -> int:
        """Highest non-AIR z in a column (glass floor guarantees >= 0)."""
        nonair = np.nonzero(self.voxels[x, y, :] != VoxelType.AIR.value)[0]
        return int(nonair[-1]) if len(nonair) else 0

    def in_bounds(self, x, y, z):
        """Check if coordinates are within world bounds"""
        return (0 <= x < self.width and 
                0 <= y < self.height and 
                0 <= z < self.depth)
    
    def get_voxel(self, x, y, z):
        """Get voxel type at position"""
        if self.in_bounds(x, y, z):
            return VoxelType(self.voxels[x, y, z])
        return VoxelType.GLASS  # Out of bounds = wall
    
    def set_voxel(self, x, y, z, voxel_type: VoxelType, colony_id=-1):
        """Set voxel type and ownership"""
        if self.in_bounds(x, y, z):
            self.voxels[x, y, z] = voxel_type.value
            if colony_id >= 0:
                self.ownership[x, y, z] = colony_id
    
    def apply_gravity(self):
        """Sand falls into empty spaces below"""
        # Process from bottom up to avoid cascading issues
        for z in range(1, self.depth):
            sand_mask = self.voxels[:, :, z] == VoxelType.SAND.value
            air_below = self.voxels[:, :, z-1] == VoxelType.AIR.value
            falling = sand_mask & air_below
            
            # Move sand down
            if np.any(falling):
                self.voxels[:, :, z-1][falling] = VoxelType.SAND.value
                self.voxels[:, :, z][falling] = VoxelType.AIR.value
                # Preserve ownership through fall
                self.ownership[:, :, z-1][falling] = self.ownership[:, :, z][falling]
                self.ownership[:, :, z][falling] = -1
    
    def tunnel(self, position: Tuple[int, int, int], direction: Tuple[int, int, int], colony_id: int):
        """Excavate sand, creating tunnel"""
        x, y, z = position
        dx, dy, dz = direction
        target_x, target_y, target_z = x + dx, y + dy, z + dz
        
        if not self.in_bounds(target_x, target_y, target_z):
            return False
        
        target_type = VoxelType(self.voxels[target_x, target_y, target_z])
        
        if target_type == VoxelType.SAND:
            self.voxels[target_x, target_y, target_z] = VoxelType.AIR.value
            self.ownership[target_x, target_y, target_z] = colony_id
            return True
        elif target_type == VoxelType.AIR:
            self.ownership[target_x, target_y, target_z] = colony_id
            return True
        
        return False
    
    def fortify(self, position: Tuple[int, int, int], colony_id: int):
        """Convert sand to reinforced tunnel wall"""
        x, y, z = position
        if self.in_bounds(x, y, z):
            if self.voxels[x, y, z] == VoxelType.SAND.value:
                self.voxels[x, y, z] = VoxelType.TUNNEL_WALL.value
                self.ownership[x, y, z] = colony_id
                return True
        return False
    
    def get_neighbors_3d(self, pos: Tuple[int, int, int], radius: int = 1):
        """Get 3D neighbors (26 for radius=1)"""
        x, y, z = pos
        neighbors = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if dx == dy == dz == 0:
                        continue
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if self.in_bounds(nx, ny, nz):
                        neighbors.append((nx, ny, nz))
        return neighbors

# ============================================================================
# COLONY GENOME & EVOLUTION
# ============================================================================

@dataclass
class ColonyGenome:
    """Evolvable traits for Sand King colonies"""
    aggression: float = 0.5        # 0=passive, 1=aggressive
    tunnel_preference: float = 0.5  # 0=surface, 1=deep
    expansion_rate: float = 0.5    # Resource-to-spawn ratio
    defense_investment: float = 0.5 # Wall-building priority
    foraging_range: int = 10       # Max distance to seek food
    swarm_threshold: int = 20      # Population for swarming behavior
    fertility: float = 0.5         # Spawn rate modifier
    resilience: float = 0.5        # Damage resistance
    patience: float = 0.5          # TD discount gamma - evolvable temperament (T26)
    loyalty: float = 0.5           # hawk-dove axis: honors commitments (P11)
    
    # Neural hive mind (Maw brain)
    brain: Optional[HiveMindBrain] = None
    use_neural: bool = False       # Toggle neural vs rule-based AI
    
    def mutate(self, mutation_rate: float = 0.1):
        """Gaussian mutation of genome parameters"""
        mutated = ColonyGenome()
        mutated.use_neural = self.use_neural
        
        for attr in ['aggression', 'tunnel_preference', 'expansion_rate',
                     'defense_investment', 'fertility', 'resilience', 'patience',
                     'loyalty']:
            current = getattr(self, attr)
            noise = np.random.normal(0, mutation_rate)
            setattr(mutated, attr, np.clip(current + noise, 0.0, 1.0))
        
        mutated.foraging_range = max(5, int(self.foraging_range + np.random.normal(0, 2)))
        mutated.swarm_threshold = max(10, int(self.swarm_threshold + np.random.normal(0, 5)))
        
        # Neural brain mutation (slow - only when Maw survives)
        if self.use_neural and self.brain is not None:
            import copy
            mutated.brain = copy.deepcopy(self.brain)
            mutated.brain.mutate(mutation_rate=mutation_rate * 0.5)  # Slower Maw evolution
        elif self.use_neural:
            mutated.brain = HiveMindBrain()
        
        return mutated

# ============================================================================
# ENTITIES: Maw (Queen), SandKing (Units)
# ============================================================================

class UnitType(Enum):
    WORKER = 0   # Excavates, carries food
    SOLDIER = 1  # Fights, defends
    SCOUT = 2    # Fast, explores

_UNIT_SERIAL = itertools.count(1)  # display-only ids (SPEC_HIVE_MONITOR §2)


@dataclass
class SandKing:
    """Individual colony unit (worker/soldier/scout)"""
    colony_id: int
    position: Tuple[int, int, int]
    unit_type: UnitType
    health: int = 10
    max_health: int = 10
    attack: int = 2
    carrying: Optional[str] = None  # 'food', 'sand', 'copper', 'gold', None
    armored: bool = False  # copper armor consumed at spawn (T25)
    task_queue: deque = field(default_factory=deque)
    retreating: bool = False  # Morale flag
    forage_target: Optional[Tuple[int, int, int]] = None  # Cached food/corpse goal
    unit_id: int = field(default_factory=lambda: next(_UNIT_SERIAL))  # display identity
    thought: str = "..."  # last decoded thought / instincts (SPEC_HIVE_MONITOR M3)
    mine_target: Optional[Tuple[int, int, int]] = None  # ore being worked (T24)
    mine_progress: int = 0
    gift_amount: float = 0.0   # escrowed tribute an envoy carries (P3)
    gift_kind: str = ""        # 'food' | 'gold'
    gift_to: int = -1          # recipient colony id (-1 = not an envoy)
    
    # Neural hive mind extension (soldier's personal layer)
    brain_layer: Optional[SoldierLayer] = None
    
    def __post_init__(self):
        # Set stats based on unit type (AGGRESSION > DEFENSE)
        if self.unit_type == UnitType.WORKER:
            self.health = 10
            self.max_health = 10
            self.attack = 2
        elif self.unit_type == UnitType.SOLDIER:
            self.health = 20  # Reduced from 25
            self.max_health = 20
            self.attack = 12  # Increased from 8 (aggression favored)
        elif self.unit_type == UnitType.SCOUT:
            self.health = 5
            self.max_health = 5
            self.attack = 1
    
    def move(self, new_position: Tuple[int, int, int]):
        """Move to new position"""
        self.position = new_position
    
    def take_damage(self, damage: int, resilience: float = 0.0) -> bool:
        """Take damage with resilience modifier, return True if killed"""
        actual_damage = damage * (1.0 - resilience * 0.5)  # 0-50% damage reduction
        self.health -= actual_damage
                # Track damage for neural layer performance
        if self.brain_layer is not None:
            self.brain_layer.damage_taken += actual_damage
                # Morale check: retreat at 10% HP (ancient Greek tactics)
        if self.health < self.max_health * 0.1 and not self.retreating:
            self.retreating = True
        
        return self.health <= 0

class Maw:
    """Queen entity - heart of each colony"""
    
    def __init__(self, colony_id: int, position: Tuple[int, int, int], genome: ColonyGenome):
        self.colony_id = colony_id
        self.position = position
        self.genome = genome
        self.health = MAW_MAX_HEALTH
        self.food_stored = 120
        self.spawn_queue = deque()
        self.alive = True
        self.fleeing = False  # set while migrating away from attackers (SPEC T15)
    
    def spawn_unit(self, unit_type: UnitType) -> Optional[SandKing]:
        """Spawn worker/soldier, costs food"""
        cost = {UnitType.WORKER: 3, UnitType.SOLDIER: 6, UnitType.SCOUT: 3}
        if self.food_stored >= cost[unit_type]:
            self.food_stored -= cost[unit_type]
            unit = SandKing(self.colony_id, self.position, unit_type)
            
            # Assign neural layer if colony uses neural AI
            if NEURAL_AVAILABLE and hasattr(self, 'genome') and self.genome.use_neural:
                unit.brain_layer = SoldierLayer()
                if self.genome.brain is not None:
                    unit.brain_layer.steps_alive = 0
            
            return unit
        return None
    
    def eat(self, food_amount: int):
        """Consume food"""
        self.food_stored += food_amount
    
    def take_damage(self, damage: int) -> bool:
        """Take damage, return True if killed"""
        self.health = max(0, self.health - damage)
        if self.health <= 0:
            self.alive = False
            return True
        return False

# ============================================================================
# COLONY - Manages all units and strategy
# ============================================================================

class Colony:
    """Manages a Sand King colony"""
    
    # Colony colors for visualization
    COLORS = [(255, 0, 0), (255, 255, 255), (0, 0, 0), (255, 165, 0)]  # Red, White, Black, Orange
    
    def __init__(self, colony_id: int, maw_position: Tuple[int, int, int], genome: ColonyGenome):
        self.colony_id = colony_id
        self.maw = Maw(colony_id, maw_position, genome)
        self.units: List[SandKing] = []
        self.territory: Set[Tuple[int, int, int]] = {maw_position}
        self.genome = genome
        self.color = self.COLORS[colony_id % len(self.COLORS)]
        self.at_war = False  # food hoard > WAR_CHEST drives raids (SPEC T10)
        self.known_food: List[Tuple[int, int, int]] = []  # scout intel (SPEC T11)
        self.farming = False  # 60/30 hysteresis gate on the farm branch (T18)
        self.ore = {'copper': 0, 'gold': 0}  # mined stores (T24/T25)
        self.ore_struck: Set[str] = set()    # first-strike events fired (T24)
        
    def spawn_unit(self, unit_type: UnitType):
        """Spawn new unit from Maw; copper armors new soldiers (T25)"""
        unit = self.maw.spawn_unit(unit_type)
        if unit:
            if (unit.unit_type == UnitType.SOLDIER
                    and getattr(self, 'ore', {}).get('copper', 0) >= 1):
                self.ore['copper'] -= 1
                unit.max_health += COPPER_ARMOR_HP
                unit.health = unit.max_health
                unit.armored = True
            self.units.append(unit)
    
    def remove_unit(self, unit: SandKing):
        """Remove dead unit"""
        if unit in self.units:
            self.units.remove(unit)
    
    def get_population(self) -> int:
        """Get current population count"""
        return len(self.units)
    
    def is_alive(self) -> bool:
        """Check if colony is still alive (Maw alive)"""
        return self.maw.alive

# ============================================================================
# PHEROMONE SYSTEM - Chemical communication
# ============================================================================

class PheromoneType(Enum):
    FOOD_TRAIL = 0
    DANGER = 1
    TERRITORY = 2
    RALLY = 3

class PheromoneLayer:
    """Chemical signaling for colony coordination"""
    
    def __init__(self, dimensions: Tuple[int, int, int], num_colonies: int = 4):
        self.dimensions = dimensions
        self.num_colonies = num_colonies
        # Separate pheromone channels per colony per type
        self.trails = np.zeros((*dimensions, num_colonies, len(PheromoneType)), dtype=np.float32)
        self.decay_rate = 0.95
        self.diffusion_rate = 0.05
    
    def deposit(self, position: Tuple[int, int, int], colony_id: int, 
                pheromone_type: PheromoneType, strength: float = 1.0):
        """Deposit pheromone at position"""
        x, y, z = position
        if 0 <= x < self.dimensions[0] and 0 <= y < self.dimensions[1] and 0 <= z < self.dimensions[2]:
            self.trails[x, y, z, colony_id, pheromone_type.value] += strength
    
    def get_strength(self, position: Tuple[int, int, int], colony_id: int, 
                     pheromone_type: PheromoneType) -> float:
        """Get pheromone strength at position"""
        x, y, z = position
        if 0 <= x < self.dimensions[0] and 0 <= y < self.dimensions[1] and 0 <= z < self.dimensions[2]:
            return self.trails[x, y, z, colony_id, pheromone_type.value]
        return 0.0
    
    def step(self):
        """Decay pheromones each tick"""
        self.trails *= self.decay_rate
    
    def get_gradient(self, position: Tuple[int, int, int], colony_id: int, 
                     pheromone_type: PheromoneType, world: VoxelWorld) -> Optional[Tuple[int, int, int]]:
        """Get direction of strongest pheromone gradient"""
        neighbors = world.get_neighbors_3d(position, radius=1)
        if not neighbors:
            return None
        
        x, y, z = position
        current_strength = self.get_strength(position, colony_id, pheromone_type)
        
        best_neighbor = None
        best_strength = current_strength
        
        for nx, ny, nz in neighbors:
            strength = self.get_strength((nx, ny, nz), colony_id, pheromone_type)
            if strength > best_strength:
                best_strength = strength
                best_neighbor = (nx, ny, nz)
        
        if best_neighbor:
            return (best_neighbor[0] - x, best_neighbor[1] - y, best_neighbor[2] - z)
        return None

# ============================================================================
# CELLULAR AUTOMATA - Territory spread rules
# ============================================================================

class CellularAutomata:
    """Conway-style rules adapted for 3D colony dynamics"""
    
    @staticmethod
    def apply_territory_spread(world: VoxelWorld, colonies: List[Colony]):
        """
        Territory expansion rules (Conway-inspired), vectorized:
        - Birth: unowned AIR with 3+ adjacent same-colony cells joins the colony
        - Death: owned cell with <2 or >5 same-colony neighbors is released

        Neighbor counts come from 26 shifted sums with zeroed wrap borders
        (equivalent to the bounds-checked 26-neighborhood, ~100x faster than
        per-voxel iteration on large territories).
        """
        new_ownership = world.ownership.copy()
        air = world.voxels == VoxelType.AIR.value

        for colony in colonies:
            if not colony.is_alive():
                continue
            owned = world.ownership == colony.colony_id
            if not owned.any():
                continue

            counts = np.zeros(world.ownership.shape, dtype=np.int8)
            owned_i8 = owned.astype(np.int8)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        shifted = np.roll(owned_i8, (dx, dy, dz), axis=(0, 1, 2))
                        if dx == 1:
                            shifted[0, :, :] = 0
                        elif dx == -1:
                            shifted[-1, :, :] = 0
                        if dy == 1:
                            shifted[:, 0, :] = 0
                        elif dy == -1:
                            shifted[:, -1, :] = 0
                        if dz == 1:
                            shifted[:, :, 0] = 0
                        elif dz == -1:
                            shifted[:, :, -1] = 0
                        counts += shifted

            death = owned & ((counts < 2) | (counts > 5))
            new_ownership[death] = -1
            birth = (world.ownership == -1) & air & (counts >= 3)
            new_ownership[birth] = colony.colony_id

        world.ownership = new_ownership

# ============================================================================
# VISUALIZATION - 2D Slices & 3D GIFs
# ============================================================================

class Visualizer:
    """Handles 2D slice views and 3D GIF generation"""
    
    @staticmethod
    def render_z_slice(world: VoxelWorld, colonies: List[Colony], z_level: int, 
                       title: str = "") -> Image.Image:
        """Render 2D cross-section at given Z level"""
        w, h, _ = world.dimensions
        
        # Create RGB image (scale up for visibility)
        scale = 4
        img_array = np.zeros((h * scale, w * scale, 3), dtype=np.uint8)
        
        for x in range(w):
            for y in range(h):
                voxel = VoxelType(world.voxels[x, y, z_level])
                owner = world.ownership[x, y, z_level]
                
                # Color mapping
                if voxel == VoxelType.GLASS:
                    color = (100, 100, 100)
                elif voxel == VoxelType.STONE:
                    color = (50, 50, 50)
                elif voxel == VoxelType.SAND:
                    color = (194, 178, 128)
                elif voxel == VoxelType.TUNNEL_WALL:
                    color = (139, 90, 43)
                elif voxel == VoxelType.FOOD:
                    color = (0, 255, 0)
                elif voxel == VoxelType.CORPSE:
                    color = (128, 0, 0)
                elif voxel == VoxelType.TILLED:
                    color = (110, 80, 50)
                elif voxel == VoxelType.CROP:
                    color = (80, 160, 60)
                elif voxel == VoxelType.CROP_RIPE:
                    color = (190, 220, 60)
                elif voxel == VoxelType.COPPER_ORE:
                    color = (184, 115, 51)
                elif voxel == VoxelType.GOLD_ORE:
                    color = (255, 208, 0)
                elif voxel == VoxelType.AIR:
                    if owner >= 0:
                        # Owned air = faint colony color
                        colony = next((c for c in colonies if c.colony_id == owner), None)
                        if colony:
                            color = tuple(int(c * 0.3) for c in colony.color)
                        else:
                            color = (20, 20, 20)
                    else:
                        color = (20, 20, 20)
                else:
                    color = (0, 0, 0)
                
                # Draw scaled pixel
                img_array[y*scale:(y+1)*scale, x*scale:(x+1)*scale] = color
        
        # Draw units
        for colony in colonies:
            for unit in colony.units:
                if unit.position[2] == z_level:
                    ux, uy = unit.position[0], unit.position[1]
                    # Draw unit as bright dot
                    unit_color = colony.color
                    cx, cy = ux * scale + scale//2, uy * scale + scale//2
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < w*scale and 0 <= ny < h*scale:
                                img_array[ny, nx] = unit_color
            
            # Draw Maw
            if colony.maw.position[2] == z_level:
                mx, my = colony.maw.position[0], colony.maw.position[1]
                # Draw Maw as larger bright square
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        nx = mx * scale + scale//2 + dx
                        ny = my * scale + scale//2 + dy
                        if 0 <= nx < w*scale and 0 <= ny < h*scale:
                            img_array[ny, nx] = (255, 255, 0)  # Yellow for Maw
        
        img = Image.fromarray(img_array, 'RGB')
        return img
    
    @staticmethod
    def generate_3d_frame(world: VoxelWorld, colonies: List[Colony]) -> Image.Image:
        """
        Generate 3D visualization using scatter plots (like 3D Conway's Life).
        Plots all voxels directly without clustering.
        """
        try:
            fig = plt.figure(figsize=(12, 10))
            ax = fig.add_subplot(111, projection='3d')
            
            w, h, d = world.dimensions
            
            # Get coordinates for each voxel type using np.argwhere
            stone_coords = np.argwhere(world.voxels == VoxelType.STONE.value)
            glass_coords = np.argwhere(world.voxels == VoxelType.GLASS.value)
            sand_coords = np.argwhere(world.voxels == VoxelType.SAND.value)
            food_coords = np.argwhere(world.voxels == VoxelType.FOOD.value)
            tunnel_coords = np.argwhere(world.voxels == VoxelType.TUNNEL_WALL.value)
            
            # Plot terrain with depth-based coloring
            if len(stone_coords) > 0:
                ax.scatter(stone_coords[:, 0], stone_coords[:, 1], stone_coords[:, 2],
                          c=stone_coords[:, 2], cmap='gray', s=2, alpha=0.4, vmin=0, vmax=d)
            
            if len(glass_coords) > 0:
                ax.scatter(glass_coords[:, 0], glass_coords[:, 1], glass_coords[:, 2],
                          c='cyan', s=2, alpha=0.3)
            
            if len(sand_coords) > 0:
                ax.scatter(sand_coords[:, 0], sand_coords[:, 1], sand_coords[:, 2],
                          c=sand_coords[:, 2], cmap='YlOrBr', s=1, alpha=0.2, vmin=0, vmax=d)
            
            if len(food_coords) > 0:
                ax.scatter(food_coords[:, 0], food_coords[:, 1], food_coords[:, 2],
                          c='lime', s=50, marker='o', alpha=0.8)
            
            if len(tunnel_coords) > 0:
                ax.scatter(tunnel_coords[:, 0], tunnel_coords[:, 1], tunnel_coords[:, 2],
                          c='brown', s=3, alpha=0.5)
            
            # Plot owned air (territory) colored by colony
            for colony in colonies:
                owned_air = np.argwhere((world.voxels == VoxelType.AIR.value) & 
                                       (world.ownership == colony.colony_id))
                if len(owned_air) > 0:
                    color = np.array(colony.color) / 255.0
                    ax.scatter(owned_air[:, 0], owned_air[:, 1], owned_air[:, 2],
                              c=[color], s=3, alpha=0.3)
            
            # Draw units and Maws
            for colony in colonies:
                color = np.array(colony.color) / 255.0
                
                # Units
                if colony.units:
                    unit_positions = np.array([u.position for u in colony.units])
                    ax.scatter(unit_positions[:, 0], unit_positions[:, 1], unit_positions[:, 2],
                              c=[color], s=100, marker='^', edgecolors='black', linewidths=1)
                
                # Maw
                if colony.maw.alive:
                    mx, my, mz = colony.maw.position
                    ax.scatter(mx, my, mz, c='gold', s=300, marker='*', 
                              edgecolors='black', linewidths=2)
            
            ax.set_xlabel('X')
            ax.set_ylabel('Y')
            ax.set_zlabel('Z')
            ax.set_xlim(0, w)
            ax.set_ylim(0, h)
            ax.set_zlim(0, d)
            ax.set_title('Sand Kings 3D Terrarium')
            
            # Convert plot to image
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            img = Image.open(buf).copy()  # Copy to free buffer
            buf.close()
            plt.close(fig)
            plt.close('all')  # Aggressive cleanup
            
            return img
        
        except Exception as e:
            print(f"Warning: 3D frame generation failed: {e}")
            # Return blank fallback image
            img = Image.new('RGB', (1200, 1000), color='black')
            plt.close('all')
            return img

# ============================================================================
# MAIN SIMULATION ENGINE
# ============================================================================

class SandKingsSimulation:
    """Main simulation engine coordinating all systems"""
    
    def __init__(self, width=80, height=40, depth=20, num_colonies=4):
        self.world = VoxelWorld(width, height, depth)
        # Resolve random colony count here so the pheromone layer's
        # per-colony axis matches the colonies actually spawned
        if num_colonies is None or num_colonies == 0:
            num_colonies = random.randint(3, 5)
        self.pheromones = PheromoneLayer(self.world.dimensions, num_colonies)
        self.automata = CellularAutomata()
        self.colonies: List[Colony] = []
        self.step_count = 0
        self.pending_respawns: Dict[int, int] = {}  # colony_id -> due step
        self.events: deque = deque(maxlen=50)  # (step, message) drama feed (SPEC T9)
        self.monitors: Dict[int, 'HiveMindMonitor'] = {}  # SPEC_HIVE_MONITOR M6
        self.storm_until = 0                   # storm active while > step_count (SPEC T12)
        self._storm_wind = (1, 0)              # per-storm prevailing direction
        
        # Initialize colonies with random count (3-5) and positions
        self._spawn_colonies(num_colonies)
    
    def _spawn_colonies(self, num_colonies: int = None):
        """Spawn Maw queens at randomized locations with min distance"""
        w, h, d = self.world.dimensions
        
        # Variable colony count (3-5) if not specified or 0
        if num_colonies is None or num_colonies == 0:
            num_colonies = random.randint(3, 5)
        
        # Minimum distance = 10% of map diagonal
        min_distance = int(0.1 * ((w**2 + h**2)**0.5))
        
        # Generate positions ensuring min distance. One lucky colony wakes
        # beside the oasis (T22); the others start pushed away from it
        positions = []
        max_attempts = 100
        cx, cy = w // 2, h // 2
        lucky = random.randrange(num_colonies)

        for i in range(num_colonies):
            if i == lucky:
                for attempt in range(max_attempts):
                    angle = random.uniform(0, 2 * np.pi)
                    ring = OASIS_RADIUS + 1
                    x = int(np.clip(cx + ring * np.cos(angle), w // 8, 7 * w // 8))
                    y = int(np.clip(cy + ring * np.sin(angle), h // 8, 7 * h // 8))
                    pos = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))
                    if all(((pos[0]-p[0])**2 + (pos[1]-p[1])**2)**0.5 >= min_distance
                           for p in positions):
                        positions.append(pos)
                        break
                continue
            for attempt in range(max_attempts):
                # Random position in safe zone (not edges), on the surface
                x = random.randint(w//8, 7*w//8)
                y = random.randint(h//8, 7*h//8)
                z = min(self.world.surface_z(x, y) + 1, d - 1)

                pos = (x, y, z)

                # Check distance to existing colonies AND the oasis buffer
                if (((x - cx)**2 + (y - cy)**2)**0.5 < OASIS_RADIUS + 4
                        and attempt < max_attempts - 1):
                    continue
                if all(((pos[0]-p[0])**2 + (pos[1]-p[1])**2)**0.5 >= min_distance
                       for p in positions):
                    positions.append(pos)
                    break
        
        for i in range(len(positions)):
            genome = ColonyGenome()
            # Randomize traits (aggression-focused)
            genome.aggression = random.uniform(0.5, 1.0)  # Favor aggression
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.uniform(0.3, 1.0)  # Spawn threshold bounded [30, 100]
            genome.patience = random.uniform(0.3, 0.95)  # discount gamma (T26)
            genome.loyalty = random.uniform(0.2, 0.9)    # hawk-dove (P11)
            genome.resilience = random.uniform(0.0, 0.3)  # Defense weaker
            
            colony = Colony(i, positions[i], genome)
            self.colonies.append(colony)
            
            # Mark starting position
            x, y, z = positions[i]
            self.world.set_voxel(x, y, z, VoxelType.AIR, colony_id=i)
            
            # Spawn initial workers
            for _ in range(3):
                colony.spawn_unit(UnitType.WORKER)

        holder = self.oasis_holder()
        if holder is not None:
            self._log_event(f"Colony {holder} wakes beside the oasis")
    
    def step(self):
        """Execute one simulation step"""
        self.step_count += 1

        # 0. SEASON TICK (T16) - first, so boundary feedings use the new dole
        if self.step_count % SEASON_LENGTH == 0:
            name = SEASONS[self.season_index()]
            self._log_event(f"The {name} season begins"
                            f" (dole {self.dole_factor() * 100:.0f}%)")

        # 1. Physics
        if self.step_count % 5 == 0:  # Apply gravity every 5 steps
            self.world.apply_gravity()
        
        # 2. Cellular automata (territory spread)
        if self.step_count % 10 == 0:  # Apply CA rules every 10 steps
            self.automata.apply_territory_spread(self.world, self.colonies)
        
        # 3. Pheromone decay
        self.pheromones.step()

        # 3b. KEEPER FEEDING: scatter food on the surface (SPEC T1)
        if self.step_count % FEED_INTERVAL == 0:
            self._feed_terrarium()

        # 3c. SANDSTORMS: wind reshapes the dunes (SPEC T12); storms never
        # overlap. Seasonal cadence (T16): frequent in Dust, none in Chill
        season = self.season_index()
        storm_interval = STORM_INTERVAL_DUST if season == 2 else STORM_INTERVAL
        if (season != 3
                and self.step_count % storm_interval == 0
                and self.storm_until <= self.step_count
                and random.random() < STORM_CHANCE):
            self.storm_until = self.step_count + STORM_DURATION
            self._storm_wind = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            self._log_event("A sandstorm rises!")
        if self.storm_until > self.step_count:
            self._blow_sand()
            if self.storm_until == self.step_count + 1:
                self._log_event("The sandstorm passes")

        # 3d. CROP GROWTH (T19/T20)
        if self.step_count % CROP_TICK == 0:
            self._grow_crops()

        # 3e. DUST SPOILAGE (T16)
        if season == 2 and self.step_count % SPOIL_INTERVAL == 0:
            self._spoil_surface_food()

        # 4. NEURAL PRUNING: Remove rarely activated weights every 50 steps
        if NEURAL_AVAILABLE and self.step_count % 50 == 0:
            for colony in self.colonies:
                if colony.genome.use_neural and colony.genome.brain is not None:
                    pruned = colony.genome.brain.prune_weights(threshold=0.01)
                    if pruned > 0:
                        print(f"Colony {colony.colony_id}: Pruned {pruned} weights")
        
        # 5. Food consumption and starvation (DARWINIAN PRESSURE)
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            
            # Normalize Round-1 attrs for colonies from older checkpoints
            if not hasattr(colony, 'farming'):
                colony.farming = False
                colony.ore = {'copper': 0, 'gold': 0}
                colony.ore_struck = set()

            # LEARNER decision tick (T26): posture biases gates, never rules
            if self.step_count % 25 == 0:
                self._learner(colony.colony_id).decide(
                    self, colony, getattr(colony.genome, 'patience', 0.5))
            posture = self._posture(colony)

            # FARMING FLAG hysteresis: on > FARM_START_FOOD, off < FARM_STOP_FOOD
            # (T18); a FARM posture lowers the entry gate by 25% (T26)
            start_gate = FARM_START_FOOD * (0.75 if posture == "FARM" else 1.0)
            if colony.farming:
                colony.farming = colony.maw.food_stored > FARM_STOP_FOOD
            else:
                colony.farming = colony.maw.food_stored > start_gate

            # Maintenance cost (SPEC constants)
            colony.maw.food_stored -= len(colony.units) * MAINTENANCE_COST

            # Starvation: capped per step so decline is gradual (SPEC T7)
            if colony.maw.food_stored < 0 and colony.units:
                units_to_kill = random.sample(
                    colony.units,
                    min(STARVATION_MAX_KILLS, len(colony.units)))
                for dead_unit in units_to_kill:
                    colony.maw.food_stored += 2  # Recover some food from dead unit
                    colony.remove_unit(dead_unit)
                    # Create edible corpse
                    self.world.set_voxel(*dead_unit.position, VoxelType.CORPSE)

            # Adjust spawn threshold by expansion_rate
            spawn_threshold = 30 / max(0.1, colony.genome.expansion_rate)

            # WAR FOOTING (T10 amended by P5): the hoard picks ONE target;
            # coalition members mobilize at half the chest
            d = self._diplomacy()
            cid = colony.colony_id
            current_target = d.war_target.get(cid)
            coalition_member = d.hegemon is not None and cid != d.hegemon
            enter_at = WAR_CHEST * (0.5 if coalition_member else 1.0)
            if current_target is None:
                if colony.maw.food_stored > enter_at:
                    target = self._select_war_target(colony)
                    d.war_target[cid] = target
                    if target is not None:
                        self._log_event(f"Colony {cid} declares war"
                                        f" on Colony {target}!")
                        monitor = self._monitor(cid)
                        monitor.log_decision(self.step_count, f"Colony {cid}",
                                             f"declares war on Colony {target}",
                                             monitor.colony_thought(self, colony))
                    elif (self.step_count - d.restless_logged.get(cid, -10**9)
                          > SEASON_LENGTH):
                        d.restless_logged[cid] = self.step_count
                        self._log_event(f"Colony {cid} seethes, but has no enemy")
            else:
                target_colony = self._colony_by_id(current_target)
                if (colony.maw.food_stored < WAR_CHEST / 2
                        or target_colony is None
                        or not target_colony.is_alive()
                        or d.truce_active(cid, current_target, self.step_count)):
                    d.war_target[cid] = None  # stand down / target resolved
            colony.at_war = d.war_target.get(cid) is not None

            # BOOTSTRAP: a colony with no units always fields a worker (SPEC T2)
            if not colony.units and colony.maw.food_stored >= 3:
                colony.spawn_unit(UnitType.WORKER)
            # Maw spawning decisions; war flips the mix
            elif colony.maw.food_stored > spawn_threshold and len(colony.units) < UNIT_CAP:
                if random.random() < colony.genome.fertility:
                    roll = random.random()
                    if colony.at_war:  # SPEC T11 mix: 0.30 W / 0.60 S / 0.10 C
                        # RAID posture presses harder: 0.20 W / 0.70 S (T26)
                        worker_cut = 0.20 if posture == "RAID" else 0.30
                        unit_type = (UnitType.WORKER if roll < worker_cut else
                                     UnitType.SOLDIER if roll < 0.90 else UnitType.SCOUT)
                    else:              # peacetime: 0.60 W / 0.25 S / 0.15 C
                        unit_type = (UnitType.WORKER if roll < 0.60 else
                                     UnitType.SOLDIER if roll < 0.85 else UnitType.SCOUT)
                    colony.spawn_unit(unit_type)
            
            # Unit AI (simplified)
            for unit in colony.units[:]:  # Copy list to allow removal
                self._execute_unit_ai(unit, colony)
        
        # 5b. DIPLOMACY (SPEC_POLITICS): a truce signed this step prevents
        # this step's bloodshed
        self._resolve_diplomacy()

        # 6. Combat resolution
        self._resolve_conflicts()

        # 7. Maw migration, regen, colony collapse, and new arrivals (SPEC T4-T6, T15)
        self._migrate_threatened_maws()
        self._apply_maw_regen()
        self._check_maw_deaths()
        self._process_respawns()

    def _log_event(self, message: str):
        """Append to the drama feed shown in the live HUD (SPEC T9)."""
        self.events.append((self.step_count, message))

    # ---- Seasons & Stone helpers (SPEC_SEASONS_AND_STONE.md) ----

    def season_index(self) -> int:
        """Derived season 0-3 (T16); never stored."""
        return (self.step_count // SEASON_LENGTH) % 4

    def year(self) -> int:
        return self.step_count // YEAR_LENGTH

    def dole_factor(self) -> float:
        """Seasonal dole factor with the 2-year ramp floor (T17)."""
        f = DOLE_FACTOR[self.season_index()]
        if not getattr(self, 'harsh', False):
            f = max(f, DOLE_RAMP[min(self.year(), 2)])
        return f

    def in_oasis(self, x: int, y: int) -> bool:
        """Pure positional oasis disc (T22); no state, no pickle surface."""
        cx, cy = self.world.width // 2, self.world.height // 2
        return (x - cx) ** 2 + (y - cy) ** 2 <= OASIS_RADIUS ** 2

    def oasis_holder(self) -> Optional[int]:
        """Colony whose living maw sits on/near the oasis, else None."""
        cx, cy = self.world.width // 2, self.world.height // 2
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            mx, my, _ = colony.maw.position
            if (mx - cx) ** 2 + (my - cy) ** 2 <= (OASIS_RADIUS + 2) ** 2:
                return colony.colony_id
        return None

    def _crops(self) -> Dict[Tuple[int, int, int], int]:
        """Sparse crop registry pos -> grow ticks (T19); checkpoint-guarded."""
        if not hasattr(self, 'crops'):
            self.crops = {}
        return self.crops

    def _grow_crops(self):
        """Crop lifecycle tick (T19/T20 behavioral block); purge-first."""
        crops = self._crops()
        season = self.season_index()
        ripe_at = CROP_GROWDUR // CROP_TICK
        for pos in list(crops.keys()):
            x, y, z = pos
            if self.world.voxels[pos] != VoxelType.CROP.value:
                del crops[pos]
                continue
            if z + 1 < self.world.depth and self.world.voxels[x, y, z + 1] != VoxelType.AIR.value:
                self.world.voxels[pos] = VoxelType.SAND.value  # buried by drift
                del crops[pos]
                continue
            oasis = self.in_oasis(x, y)
            if not oasis:
                if season == 2:      # Dust: stall
                    continue
                if season == 3:      # Chill: the frost takes the young crops
                    self.world.voxels[pos] = VoxelType.SAND.value
                    del crops[pos]
                    owner = int(self.world.ownership[pos])
                    frost_key = (self.year(), owner)
                    if owner >= 0 and getattr(self, '_frost_logged', None) != frost_key:
                        self._frost_logged = frost_key
                        self._log_event(f"The frost takes Colony {owner}'s young crops")
                    continue
            crops[pos] += OASIS_GROWTH_MULT if oasis else 1
            if crops[pos] >= ripe_at:
                self.world.voxels[pos] = VoxelType.CROP_RIPE.value
                del crops[pos]

    def _spoil_surface_food(self):
        """Dust-season spoilage of exposed FOOD (T16)."""
        food_positions = np.argwhere(self.world.voxels == VoxelType.FOOD.value)
        d = self.world.depth
        for x, y, z in food_positions:
            if z + 1 < d and self.world.voxels[x, y, z + 1] == VoxelType.AIR.value:
                if random.random() < SPOIL_CHANCE:
                    self.world.voxels[x, y, z] = VoxelType.AIR.value

    def _monitor(self, colony_id: int) -> 'HiveMindMonitor':
        """Lazy per-colony hive-mind monitor (SPEC_HIVE_MONITOR M6/M7).

        Guarded for sims resumed from pre-monitor checkpoints.
        """
        from hive_mind_monitor import HiveMindMonitor
        if not hasattr(self, 'monitors'):
            self.monitors = {}
        if colony_id not in self.monitors:
            self.monitors[colony_id] = HiveMindMonitor(colony_id)
        return self.monitors[colony_id]

    def _diplomacy(self) -> 'Diplomacy':
        """Lazy political state (SPEC_POLITICS P1); checkpoint-guarded."""
        from politics import Diplomacy
        if not hasattr(self, 'diplomacy') or self.diplomacy is None:
            self.diplomacy = Diplomacy()
        return self.diplomacy

    def _colony_by_id(self, colony_id: int) -> Optional[Colony]:
        return next((c for c in self.colonies if c.colony_id == colony_id), None)

    def _learner(self, colony_id: int) -> 'ColonyLearner':
        """Lazy per-colony posture learner (T26); checkpoint-guarded."""
        from colony_learner import ColonyLearner
        if not hasattr(self, 'learners'):
            self.learners = {}
        if colony_id not in self.learners:
            self.learners[colony_id] = ColonyLearner()
        return self.learners[colony_id]

    def _posture(self, colony: Colony) -> str:
        """The colony's current learned posture (FORAGE when unlearned)."""
        if not hasattr(self, 'learners') or colony.colony_id not in self.learners:
            return "FORAGE"
        return self.learners[colony.colony_id].posture

    def _feed_terrarium(self) -> int:
        """Scatter FOOD on the surface and floor colony reserves (SPEC T1).

        Feed amount balances TARGET_POP units per colony against maintenance
        over one interval. Returns the number of voxels actually placed.
        """
        w, h, d = self.world.dimensions
        f = self.dole_factor()  # seasonal scarcity (T17)
        n = round(TARGET_POP * len(self.colonies) * MAINTENANCE_COST
                  * FEED_INTERVAL / HARVEST_YIELD * f)
        # the lower clamp scales too, or Chill silently floors at f=1/3
        n = max(round(4 * len(self.colonies) * f), min(n, (w * h) // 40))
        placed = 0
        cx, cy = w // 2, h // 2
        for i in range(n):
            if i < OASIS_FEED_BONUS:  # a share always lands in the oasis (T22)
                x = int(np.clip(cx + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, w - 2))
                y = int(np.clip(cy + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, h - 2))
            else:
                x = random.randint(1, w - 2)
                y = random.randint(1, h - 2)
            z = self.world.surface_z(x, y) + 1
            if z < d and self.world.voxels[x, y, z] == VoxelType.AIR.value:
                self.world.voxels[x, y, z] = VoxelType.FOOD.value
                placed += 1
        for colony in self.colonies:
            if colony.is_alive():
                colony.maw.food_stored = max(colony.maw.food_stored, BOOTSTRAP_FLOOR)
        self._log_event(f"Keeper scatters {placed} food")
        return placed

    def _find_food_target(self, position: Tuple[int, int, int],
                          radius: int) -> Optional[Tuple[int, int, int]]:
        """Nearest FOOD/CORPSE voxel within a clipped box, by Manhattan distance."""
        x, y, z = position
        w, h, d = self.world.dimensions
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        z0, z1 = max(0, z - radius), min(d, z + radius + 1)
        box = self.world.voxels[x0:x1, y0:y1, z0:z1]
        hits = np.argwhere((box == VoxelType.FOOD.value)
                           | (box == VoxelType.CORPSE.value)
                           | (box == VoxelType.CROP_RIPE.value))  # ripe = food (T18)
        if len(hits) == 0:
            return None
        coords = hits + np.array([x0, y0, z0])
        best = coords[int(np.argmin(np.abs(coords - np.array(position)).sum(axis=1)))]
        return (int(best[0]), int(best[1]), int(best[2]))

    def _blow_sand(self):
        """One storm step: wind transports surface sand downwind (SPEC T12).

        Moves the top sand voxel of random interior columns to the top of
        the downwind neighbor (with lateral jitter), then settles gravity so
        drifts slump. Whatever the drift covers stays buried but diggable.
        """
        w, h, d = self.world.dimensions
        substrate = d // 5
        wx, wy = self._storm_wind
        n = max(1, int(w * h * STORM_COLUMNS_FRACTION))
        for _ in range(n):
            x = random.randint(1, w - 2)
            y = random.randint(1, h - 2)
            top = self.world.surface_z(x, y)
            if top <= substrate or self.world.voxels[x, y, top] != VoxelType.SAND.value:
                continue
            jitter = random.choice([-1, 0, 1])
            tx = x + wx + (jitter if wx == 0 else 0)
            ty = y + wy + (jitter if wy == 0 else 0)
            if not (1 <= tx < w - 1 and 1 <= ty < h - 1):
                continue
            dst_top = self.world.surface_z(tx, ty)
            if dst_top + 1 >= d:
                continue
            self.world.voxels[x, y, top] = VoxelType.AIR.value
            self.world.voxels[tx, ty, dst_top + 1] = VoxelType.SAND.value
        self.world.apply_gravity()

    def _milestone(self, colony: Colony, key: str, event_text: str, unit=None):
        """Once-per-colony milestone events (first sow/harvest, T19)."""
        if not hasattr(colony, 'milestones'):
            colony.milestones = set()
        if key in colony.milestones:
            return
        colony.milestones.add(key)
        self._log_event(event_text)
        actor = self._unit_label(unit) if unit else f"Colony {colony.colony_id}"
        self._monitor(colony.colony_id).log_decision(
            self.step_count, actor, event_text.split(' ', 2)[-1],
            getattr(unit, 'thought', None) if unit else None)

    def _sow_window_open(self) -> bool:
        """Non-oasis sowing only when the crop can ripen before Dust (T20)."""
        if self.season_index() not in GROW_SEASONS:
            return False
        window_end = self.year() * YEAR_LENGTH + 2 * SEASON_LENGTH
        return window_end - self.step_count >= CROP_GROWDUR

    def _farm_counts(self, colony: Colony) -> Tuple[int, int]:
        """(total plots, ripe plots) owned within the farm box (T18/R24)."""
        mx, my, _ = colony.maw.position
        w, h, _d = self.world.dimensions
        x0, x1 = max(1, mx - FARM_RADIUS), min(w - 1, mx + FARM_RADIUS + 1)
        y0, y1 = max(1, my - FARM_RADIUS), min(h - 1, my + FARM_RADIUS + 1)
        box_v = self.world.voxels[x0:x1, y0:y1, :]
        owned = self.world.ownership[x0:x1, y0:y1, :] == colony.colony_id
        farm = ((box_v == VoxelType.TILLED.value) | (box_v == VoxelType.CROP.value)
                | (box_v == VoxelType.CROP_RIPE.value))
        ripe = box_v == VoxelType.CROP_RIPE.value
        return int((farm & owned).sum()), int((ripe & owned).sum())

    def _farm_plot_count(self, colony: Colony) -> int:
        """Owned TILLED/CROP/CROP_RIPE voxels within the farm box (T18)."""
        return self._farm_counts(colony)[0]

    def _find_farm_site(self, colony: Colony) -> Optional[Tuple[int, int, int]]:
        """Best tillable surface SAND near the maw: oasis first, then close."""
        mx, my, _ = colony.maw.position
        w, h, _d = self.world.dimensions
        best, best_key = None, None
        for dx in range(-FARM_RADIUS, FARM_RADIUS + 1):
            for dy in range(-FARM_RADIUS, FARM_RADIUS + 1):
                px, py = mx + dx, my + dy
                if not (1 <= px < w - 1 and 1 <= py < h - 1):
                    continue
                pz = self.world.surface_z(px, py)
                if self.world.voxels[px, py, pz] != VoxelType.SAND.value:
                    continue
                key = (not self.in_oasis(px, py), abs(dx) + abs(dy))
                if best_key is None or key < best_key:
                    best, best_key = (px, py, pz), key
        return best

    def _farm_step(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 5: sow an adjacent owned TILLED, else till toward a site."""
        x, y, z = unit.position
        if colony.maw.food_stored >= SEED_COST:
            for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                if (self.world.voxels[nx, ny, nz] == VoxelType.TILLED.value
                        and self.world.ownership[nx, ny, nz] == colony.colony_id):
                    colony.maw.food_stored -= SEED_COST
                    self.world.voxels[nx, ny, nz] = VoxelType.CROP.value
                    self._crops()[(nx, ny, nz)] = 0
                    self._milestone(colony, 'sowed',
                                    f"Colony {colony.colony_id} sows its first field",
                                    unit)
                    return True
        if self._farm_plot_count(colony) < FARM_MAX_PLOTS:
            site = self._find_farm_site(colony)
            if site is not None:
                sx, sy, sz = site
                if max(abs(sx - x), abs(sy - y), abs(sz - z)) <= 1:
                    self.world.voxels[site] = VoxelType.TILLED.value
                    self.world.ownership[site] = colony.colony_id
                    return True
                return self._step_toward(unit, site, colony)
        return False

    def _haul_step(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 2: carry mined ore to the maw (deposit at Chebyshev 2)."""
        if unit.carrying not in ('copper', 'gold'):
            return False
        mx, my, mz = colony.maw.position
        x, y, z = unit.position
        if max(abs(mx - x), abs(my - y), abs(mz - z)) <= 2:
            colony.ore[unit.carrying] = colony.ore.get(unit.carrying, 0) + 1
            unit.carrying = None
            return True
        self._step_toward(unit, colony.maw.position, colony)
        return True  # hauling consumes the step even when boxed in

    def _mine_step(self, unit: SandKing, colony: Colony) -> bool:
        """T24: one step of work on an adjacent, still-valid ore target."""
        target = getattr(unit, 'mine_target', None)
        if target is None:
            return False
        voxel = self.world.voxels[target]
        x, y, z = unit.position
        if (voxel not in (VoxelType.COPPER_ORE.value, VoxelType.GOLD_ORE.value)
                or max(abs(target[0] - x), abs(target[1] - y), abs(target[2] - z)) > 1):
            unit.mine_target = None
            unit.mine_progress = 0
            return False
        unit.mine_progress = getattr(unit, 'mine_progress', 0) + 1
        if unit.mine_progress >= MINE_TIME:
            kind = 'copper' if voxel == VoxelType.COPPER_ORE.value else 'gold'
            self.world.voxels[target] = VoxelType.AIR.value
            unit.carrying = kind
            unit.mine_target = None
            unit.mine_progress = 0
            if kind not in colony.ore_struck:
                colony.ore_struck.add(kind)
                self._log_event(f"Colony {colony.colony_id} strikes {kind}!")
                self._monitor(colony.colony_id).log_decision(
                    self.step_count, self._unit_label(unit), f"struck {kind}",
                    getattr(unit, 'thought', None))
        return True

    def _find_ore_target(self, position: Tuple[int, int, int],
                         radius: int) -> Optional[Tuple[int, int, int]]:
        """Nearest EXPOSED ore voxel (>= 1 AIR face) in a clipped box (T24)."""
        x, y, z = position
        w, h, d = self.world.dimensions
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        z0, z1 = max(0, z - radius), min(d, z + radius + 1)
        box = self.world.voxels[x0:x1, y0:y1, z0:z1]
        hits = np.argwhere((box == VoxelType.COPPER_ORE.value)
                           | (box == VoxelType.GOLD_ORE.value))
        best, best_dist = None, None
        for hx, hy, hz in hits:
            pos = (int(hx) + x0, int(hy) + y0, int(hz) + z0)
            exposed = any(
                self.world.in_bounds(pos[0] + dx, pos[1] + dy, pos[2] + dz)
                and self.world.voxels[pos[0] + dx, pos[1] + dy, pos[2] + dz]
                == VoxelType.AIR.value
                for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                   (0, -1, 0), (0, 0, 1), (0, 0, -1)))
            if not exposed:
                continue
            dist = abs(pos[0] - x) + abs(pos[1] - y) + abs(pos[2] - z)
            if best_dist is None or dist < best_dist:
                best, best_dist = pos, dist
        return best

    def _mine_seek(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 6: move to exposed ore; engage when adjacent."""
        target = self._find_ore_target(unit.position, colony.genome.foraging_range)
        if target is None:
            return False
        x, y, z = unit.position
        if max(abs(target[0] - x), abs(target[1] - y), abs(target[2] - z)) <= 1:
            unit.mine_target = target
            unit.mine_progress = 0
            return True
        return self._step_toward(unit, target, colony)

    def _pull_known_food(self, colony: Colony,
                         position: Tuple[int, int, int]) -> Optional[Tuple[int, int, int]]:
        """Nearest still-valid scout-reported food; stale entries dropped (SPEC T11)."""
        valid = []
        for entry in colony.known_food:
            if self.world.get_voxel(*entry) in (VoxelType.FOOD, VoxelType.CORPSE,
                                                VoxelType.CROP_RIPE):
                valid.append(entry)
        colony.known_food = valid
        if not valid:
            return None
        return min(valid, key=lambda p: (abs(p[0] - position[0])
                                         + abs(p[1] - position[1])
                                         + abs(p[2] - position[2])))

    def _step_toward(self, unit: SandKing, target: Tuple[int, int, int],
                     colony: Colony) -> bool:
        """Move one voxel toward target through AIR (walk) or SAND (tunnel).

        Falls back to single-axis sidesteps when the diagonal is blocked.
        Returns True if the unit moved.
        """
        x, y, z = unit.position
        dx = int(np.sign(target[0] - x))
        dy = int(np.sign(target[1] - y))
        dz = int(np.sign(target[2] - z))
        candidates = [(dx, dy, dz), (dx, 0, 0), (0, dy, 0), (0, 0, dz)]
        for step_dir in candidates:
            if step_dir == (0, 0, 0):
                continue
            new_pos = (x + step_dir[0], y + step_dir[1], z + step_dir[2])
            if not self.world.in_bounds(*new_pos):
                continue
            voxel = self.world.get_voxel(*new_pos)
            if voxel == VoxelType.AIR:
                unit.move(new_pos)
                return True
            if voxel == VoxelType.SAND and self.world.tunnel(
                    unit.position, step_dir, colony.colony_id):
                unit.move(new_pos)
                return True
        return False

    def _select_war_target(self, colony: Colony) -> Optional[int]:
        """P5: coalition targets the hegemon; else grievance directs,
        wealth tempts, capability deters."""
        from politics import power
        d = self._diplomacy()
        cid = colony.colony_id
        if d.hegemon is not None and cid != d.hegemon:
            hegemon = self._colony_by_id(d.hegemon)
            if hegemon is not None and hegemon.is_alive():
                return d.hegemon
        eligible = [c for c in self.colonies
                    if c.colony_id != cid and c.is_alive()
                    and not d.truce_active(cid, c.colony_id, self.step_count)
                    and not d.ally(cid, c.colony_id)
                    and not d.co_belligerents(cid, c.colony_id)]
        if not eligible:
            return None
        max_wealth = max(c.maw.food_stored for c in eligible) or 1.0
        max_power = max(power(c) for c in eligible) or 1.0

        def score(c):
            hatred = max(0.0, -d.trust(cid, c.colony_id)) / 100.0
            return (0.45 * hatred
                    + 0.35 * c.maw.food_stored / max_wealth
                    - 0.20 * power(c) / max_power)
        return max(eligible, key=score).colony_id

    def _dispatch_gift(self, colony: Colony, recipient_id: int,
                       kind: str = 'food') -> bool:
        """P3: escrow the amount onto a courier worker; visible drama."""
        from politics import GIFT_COOLDOWN
        d = self._diplomacy()
        rel = d.rel(colony.colony_id, recipient_id)
        if self.step_count - rel.last_gift_sent < GIFT_COOLDOWN:
            return False
        workers = [u for u in colony.units if u.unit_type == UnitType.WORKER
                   and getattr(u, 'gift_to', -1) < 0
                   and u.carrying not in ('copper', 'gold')]
        if not workers:
            return False
        if kind == 'gold':
            if getattr(colony, 'ore', {}).get('gold', 0) < 1:
                return False
            colony.ore['gold'] -= 1
            amount = 5.0
        else:
            amount = min(60.0, 0.25 * colony.maw.food_stored)
            if amount < 20.0 or colony.maw.food_stored < amount:
                return False
            colony.maw.food_stored -= amount  # escrow: committed and at risk
        mx, my, mz = colony.maw.position
        envoy = min(workers, key=lambda u: (abs(u.position[0] - mx)
                                            + abs(u.position[1] - my)))
        envoy.gift_amount = amount
        envoy.gift_kind = kind
        envoy.gift_to = recipient_id
        envoy.forage_target = None
        rel.last_gift_sent = self.step_count
        if self.step_count - rel.window_start > 500:
            rel.window_start = self.step_count
            rel.gifts_in_window = 0
        rel.gifts_in_window += 1
        self._log_event(f"Colony {colony.colony_id} sends tribute"
                        f" to Colony {recipient_id}")
        monitor = self._monitor(colony.colony_id)
        monitor.log_decision(self.step_count, f"Colony {colony.colony_id}",
                             f"sends tribute to Colony {recipient_id}",
                             monitor.colony_thought(self, colony))
        return True

    def _deliver_gift(self, envoy: SandKing, sender: Colony):
        """Envoy arrival / refusal (P3)."""
        from politics import GIFT_TRUST_FOOD, GIFT_TRUST_GOLD
        d = self._diplomacy()
        recipient = self._colony_by_id(envoy.gift_to)
        if recipient is None or not recipient.is_alive():
            envoy.gift_to, envoy.gift_amount = -1, 0.0
            return
        if d.war_target.get(recipient.colony_id) == sender.colony_id:
            self._log_event(f"Colony {recipient.colony_id} spurns"
                            f" Colony {sender.colony_id}'s envoy!")
            d.rel(sender.colony_id, recipient.colony_id).adjust(-25.0)
            envoy.gift_to, envoy.gift_amount = -1, 0.0
            return
        if envoy.gift_kind == 'gold':
            base = GIFT_TRUST_GOLD
            if not hasattr(recipient, 'ore'):
                recipient.ore = {'copper': 0, 'gold': 0}
            recipient.ore['gold'] = recipient.ore.get('gold', 0) + 1
        else:
            base = GIFT_TRUST_FOOD
            recipient.maw.food_stored += envoy.gift_amount
        rel = d.rel(sender.colony_id, recipient.colony_id)
        k = max(0, rel.gifts_in_window - 1)
        d.rel(recipient.colony_id, sender.colony_id).adjust(base * (0.5 ** k))
        rel.last_gift_received = self.step_count  # reciprocation clock (theirs)
        d.rel(recipient.colony_id, sender.colony_id).last_gift_received = self.step_count
        self._log_event(f"Colony {recipient.colony_id} accepts"
                        f" Colony {sender.colony_id}'s tribute")
        envoy.gift_to, envoy.gift_amount, envoy.gift_kind = -1, 0.0, ""

    def _betray(self, colony: Colony, target_id: int):
        """P6 execution: atomic, once per cooldown."""
        from politics import BETRAYAL_OBSERVER, BETRAYAL_VICTIM
        d = self._diplomacy()
        cid = colony.colony_id
        d.truce_until.pop(frozenset((cid, target_id)), None)
        d.rel(target_id, cid).adjust(BETRAYAL_VICTIM)
        d.rel(target_id, cid).last_betrayed_by = self.step_count
        for other in self.colonies:
            if other.colony_id not in (cid, target_id) and other.is_alive():
                d.rel(other.colony_id, cid).adjust(BETRAYAL_OBSERVER)
        d.war_target[cid] = target_id
        colony.at_war = True
        d.last_betrayal[cid] = self.step_count
        self._log_event(f"Colony {cid} betrays Colony {target_id}!")
        monitor = self._monitor(cid)
        monitor.log_decision(self.step_count, f"Colony {cid}",
                             f"betrays Colony {target_id}",
                             monitor.colony_thought(self, colony))

    def _propose_truce(self, colony: Colony, other: Colony) -> bool:
        """P4: proposal + same-tick acceptance by the counterpart's rules."""
        from politics import (GRUDGE_LOCK, NEMESIS, REJECT_COOLDOWN,
                              TRUCE_DURATION, power)
        d = self._diplomacy()
        a, b = colony.colony_id, other.colony_id
        key = frozenset((a, b))
        if d.truce_active(a, b, self.step_count):
            return False
        if self.step_count - d.rejected_at.get(key, -10**9) < REJECT_COOLDOWN:
            return False
        rel_b = d.rel(b, a)
        accepts = False
        if other.maw.food_stored < 2 * BOOTSTRAP_FLOOR:
            accepts = True  # exhaustion peace
        elif (self.step_count - rel_b.last_betrayed_by) < GRUDGE_LOCK:
            accepts = False
        elif rel_b.trust <= NEMESIS:
            accepts = False
        elif (getattr(other.genome, 'aggression', 0.5) > 0.8
                and power(other) > 1.5 * power(colony)):
            accepts = False  # strong hawks refuse peace they don't need
        else:
            accepts = True
        if not accepts:
            d.rejected_at[key] = self.step_count
            return False
        d.truce_until[key] = self.step_count + TRUCE_DURATION
        if d.war_target.get(a) == b:
            d.war_target[a] = None
        if d.war_target.get(b) == a:
            d.war_target[b] = None
        self._log_event(f"Colony {a} and Colony {b} strike a truce")
        for c, o in ((colony, b), (other, a)):
            monitor = self._monitor(c.colony_id)
            monitor.log_decision(self.step_count, f"Colony {c.colony_id}",
                                 f"signs a truce with Colony {o}",
                                 monitor.colony_thought(self, c))
        return True

    def _update_hegemon(self):
        """P7: enter/exit with hysteresis; events on transition."""
        from politics import HEGEMON_ENTER, HEGEMON_EXIT, power
        d = self._diplomacy()
        living = [c for c in self.colonies if c.is_alive()]
        if len(living) < 2:
            if d.hegemon is not None:
                self._log_event(f"The coalition against Colony {d.hegemon} dissolves")
                d.hegemon = None
            return
        total = sum(power(c) for c in living) or 1.0
        n = len(living)
        if d.hegemon is None:
            for c in living:
                if power(c) / total > HEGEMON_ENTER / n:
                    d.hegemon = c.colony_id
                    self._log_event(f"A coalition rises against Colony {c.colony_id}!")
                    for other in living:
                        if other.colony_id != c.colony_id:
                            monitor = self._monitor(other.colony_id)
                            monitor.log_decision(
                                self.step_count, f"Colony {other.colony_id}",
                                f"joins the coalition against Colony {c.colony_id}",
                                monitor.colony_thought(self, other))
                    break
        else:
            hegemon = self._colony_by_id(d.hegemon)
            if (hegemon is None or not hegemon.is_alive()
                    or power(hegemon) / total < HEGEMON_EXIT / n):
                if hegemon is not None and hegemon.is_alive():
                    self._log_event(f"The coalition against Colony {d.hegemon} dissolves")
                d.hegemon = None

    def _run_policy_cascade(self, colony: Colony):
        """P11: first matching rule acts."""
        from politics import power
        d = self._diplomacy()
        cid = colony.colony_id
        living = [c for c in self.colonies
                  if c.is_alive() and c.colony_id != cid]
        if not living:
            return
        aggression = getattr(colony.genome, 'aggression', 0.5)
        loyalty = getattr(colony.genome, 'loyalty', 0.5)

        # R1 BETRAY
        if (aggression > 0.75 and loyalty < 0.35
                and colony.maw.food_stored > WAR_CHEST
                and self.step_count - d.last_betrayal.get(cid, -10**9) > 800):
            for other in living:
                if (d.truce_active(cid, other.colony_id, self.step_count)
                        and other.maw.food_stored > 2 * max(1.0, colony.maw.food_stored)
                        and power(colony) > 1.5 * power(other)):
                    self._betray(colony, other.colony_id)
                    return

        my_power = power(colony)
        total = sum(power(c) for c in self.colonies if c.is_alive()) or 1.0
        n = sum(1 for c in self.colonies if c.is_alive())

        # R2 APPEASE
        for other in living:
            if (d.war_target.get(other.colony_id) == cid
                    and power(other) > 1.4 * my_power
                    and my_power / total < 0.8 / n):
                if self._dispatch_gift(colony, other.colony_id):
                    self._propose_truce(colony, other)
                    return

        # R3 RECIPROCATE
        for other in living:
            rel = d.rel(cid, other.colony_id)
            if (self.step_count - rel.last_gift_received < 300
                    and rel.last_gift_sent < rel.last_gift_received
                    and colony.maw.food_stored > WAR_CHEST / 2):
                if self._dispatch_gift(colony, other.colony_id):
                    return

        # R4 INVEST
        if d.hegemon is not None and cid != d.hegemon:
            partners = [c for c in living if c.colony_id != d.hegemon]
            if partners:
                best = max(partners, key=lambda c: d.trust(cid, c.colony_id))
                if self._dispatch_gift(colony, best.colony_id):
                    return

        # R5 SUE-FOR-PEACE
        from politics import HOSTILE as HOSTILE_T
        for other in living:
            if (d.trust(cid, other.colony_id) > HOSTILE_T
                    and d.trust(other.colony_id, cid) > HOSTILE_T
                    and d.war_target.get(cid) != other.colony_id
                    and d.war_target.get(other.colony_id) != cid
                    and colony.maw.food_stored < WAR_CHEST
                    and other.maw.food_stored < WAR_CHEST):
                if self._propose_truce(colony, other):
                    return

    def _resolve_diplomacy(self):
        """Step phase 5b (SPEC_POLITICS behavioral block)."""
        from politics import (COALITION_CAP, DIPLOMACY_INTERVAL,
                              TRUST_COALITION, TRUST_JOINT_WAR,
                              TRUST_TRUCE_TICK)
        d = self._diplomacy()
        d.decay()
        living = [c for c in self.colonies if c.is_alive()]

        # honored-truce and joint-war ticks; ally latches
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                aid, bid = a.colony_id, b.colony_id
                if d.truce_active(aid, bid, self.step_count):
                    d.rel(aid, bid).adjust(TRUST_TRUCE_TICK)
                    d.rel(bid, aid).adjust(TRUST_TRUCE_TICK)
                if d.co_belligerents(aid, bid):
                    d.rel(aid, bid).adjust(TRUST_JOINT_WAR)
                    d.rel(bid, aid).adjust(TRUST_JOINT_WAR)
                if (d.hegemon is not None
                        and aid != d.hegemon and bid != d.hegemon):
                    for x, y in ((aid, bid), (bid, aid)):
                        if d.trust(x, y) < COALITION_CAP:
                            d.rel(x, y).adjust(TRUST_COALITION)
                d.update_ally_latch(aid, bid)

        # truce expiry: renew silently when both still accept, else lapse
        for key in list(d.truce_until.keys()):
            if d.truce_until[key] <= self.step_count:
                a, b = tuple(key)
                ca, cb = self._colony_by_id(a), self._colony_by_id(b)
                renewed = False
                if (ca is not None and cb is not None and ca.is_alive()
                        and cb.is_alive() and d.trust(a, b) >= 0
                        and d.trust(b, a) >= 0):
                    del d.truce_until[key]
                    renewed = self._propose_truce(ca, cb)
                else:
                    del d.truce_until[key]
                if not renewed:
                    self._log_event(f"The truce between Colony {a}"
                                    f" and Colony {b} lapses")

        self._update_hegemon()

        # envoys move every step (their AI happens here, not in worker AI)
        for colony in living:
            for unit in colony.units[:]:
                if getattr(unit, 'gift_to', -1) >= 0:
                    recipient = self._colony_by_id(unit.gift_to)
                    if recipient is None or not recipient.is_alive():
                        unit.gift_to, unit.gift_amount = -1, 0.0
                        continue
                    mx, my, mz = recipient.maw.position
                    x, y, z = unit.position
                    if max(abs(mx - x), abs(my - y), abs(mz - z)) <= 2:
                        self._deliver_gift(unit, colony)
                    else:
                        self._step_toward(unit, recipient.maw.position, colony)

        # policy cascade on the diplomacy cadence, randomized order
        if self.step_count % DIPLOMACY_INTERVAL == 0:
            order = living[:]
            random.shuffle(order)
            for colony in order:
                self._run_policy_cascade(colony)

    def _apply_maw_siege_damage(self):
        """Units adjacent to an enemy Maw damage it (SPEC T4/T14).

        Shared by the base combat resolution and the evolution sim's step
        so eliminations are real outcomes in both.
        """
        from politics import TRUST_FIRST_BLOOD, TRUST_MAW_HP, hostile
        for colony in self.colonies:
            if not colony.maw.alive:
                continue
            mx, my, mz = colony.maw.position
            for enemy_colony in self.colonies:
                if not hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue  # P9 gate
                for enemy in enemy_colony.units:
                    if getattr(enemy, 'gift_to', -1) >= 0:
                        continue  # envoys don't besiege
                    ex, ey, ez = enemy.position
                    if max(abs(ex - mx), abs(ey - my), abs(ez - mz)) <= 1:
                        if hasattr(self, 'diplomacy') and self.diplomacy is not None:
                            self.diplomacy.rel(colony.colony_id,
                                               enemy_colony.colony_id).adjust(
                                TRUST_MAW_HP * enemy.attack)  # grievance (P1)
                        if colony.maw.health >= MAW_MAX_HEALTH:  # first blood of a siege
                            self._log_event(f"Colony {enemy_colony.colony_id} besieges"
                                            f" Colony {colony.colony_id}!")
                            if hasattr(self, 'diplomacy') and self.diplomacy is not None:
                                self.diplomacy.rel(
                                    colony.colony_id,
                                    enemy_colony.colony_id).adjust(TRUST_FIRST_BLOOD)
                            self._monitor(enemy_colony.colony_id).log_decision(
                                self.step_count, self._unit_label(enemy),
                                "landed first blood on a Maw",
                                getattr(enemy, 'thought', None))
                        colony.maw.take_damage(enemy.attack)

    def _migrate_threatened_maws(self):
        """Wounded Maws crawl away from their attackers (SPEC T15).

        One voxel per step directly away from the nearest enemy unit in
        range, tunneling sand if needed, at MAW_MIGRATE_COST food per move.
        """
        for colony in self.colonies:
            maw = colony.maw
            if not maw.alive:
                continue
            if maw.health >= MAW_MAX_HEALTH * MAW_MIGRATE_HEALTH:
                maw.fleeing = False
                continue
            if maw.food_stored < MAW_MIGRATE_COST:
                continue

            mx, my, mz = maw.position
            from politics import hostile as _hostile
            threat, threat_dist = None, float('inf')
            for enemy_colony in self.colonies:
                if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue  # P9: allies/truced are not threats
                for enemy in enemy_colony.units:
                    dist = (abs(enemy.position[0] - mx) + abs(enemy.position[1] - my)
                            + abs(enemy.position[2] - mz))
                    if dist < threat_dist:
                        threat_dist, threat = dist, enemy
            if threat is None or threat_dist > colony.genome.foraging_range:
                maw.fleeing = False
                continue

            dx = int(-np.sign(threat.position[0] - mx))
            dy = int(-np.sign(threat.position[1] - my))
            if dx == 0 and dy == 0:  # attacker on top of the maw: pick any way out
                dx, dy = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
            w, h, d = self.world.dimensions
            # Directly away first; blocked paths fall back to single axes
            for step_dir in ((dx, dy), (dx, 0), (0, dy)):
                if step_dir == (0, 0):
                    continue
                new_pos = (mx + step_dir[0], my + step_dir[1], mz)
                if not (1 <= new_pos[0] < w - 1 and 1 <= new_pos[1] < h - 1):
                    continue
                if not self.world.get_voxel(*new_pos).is_tunnelable():
                    continue
                if not getattr(maw, 'fleeing', False):
                    maw.fleeing = True
                    self._log_event(f"Colony {colony.colony_id}'s Maw flees!")
                self.world.set_voxel(*new_pos, VoxelType.AIR, colony_id=colony.colony_id)
                maw.position = new_pos
                maw.food_stored -= MAW_MIGRATE_COST
                break

    def _apply_maw_regen(self):
        """Maws heal MAW_REGEN per step while no enemy unit is adjacent (SPEC T4)."""
        for colony in self.colonies:
            if not colony.maw.alive or colony.maw.health >= MAW_MAX_HEALTH:
                continue
            mx, my, mz = colony.maw.position
            besieged = any(
                max(abs(u.position[0] - mx), abs(u.position[1] - my),
                    abs(u.position[2] - mz)) <= 1
                for c in self.colonies if c.colony_id != colony.colony_id
                for u in c.units)
            if not besieged:
                colony.maw.health = min(MAW_MAX_HEALTH, colony.maw.health + MAW_REGEN)

    def _check_maw_deaths(self):
        """Collapse fallen colonies into a corpse feast and schedule arrivals (SPEC T5)."""
        for colony in self.colonies:
            if colony.maw.alive or colony.colony_id in self.pending_respawns:
                continue
            for unit in colony.units:
                self.world.set_voxel(*unit.position, VoxelType.CORPSE)
            colony.units.clear()
            mx, my, mz = colony.maw.position
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    x, y = mx + dx, my + dy
                    if self.world.in_bounds(x, y, mz) and VoxelType(
                            self.world.voxels[x, y, mz]) not in (VoxelType.GLASS, VoxelType.STONE):
                        self.world.voxels[x, y, mz] = VoxelType.CORPSE.value
            # Ore spill (T25): stored ore scatters as re-minable voxels
            ore = getattr(colony, 'ore', None)
            if ore:
                kinds = (['copper'] * ore.get('copper', 0)
                         + ['gold'] * ore.get('gold', 0))
                spill_voxel = {'copper': VoxelType.COPPER_ORE.value,
                               'gold': VoxelType.GOLD_ORE.value}
                for kind in kinds[:30]:
                    for _ in range(10):
                        sx, sy = mx + random.randint(-3, 3), my + random.randint(-3, 3)
                        sz = mz + random.randint(-1, 1)
                        if (self.world.in_bounds(sx, sy, sz)
                                and self.world.voxels[sx, sy, sz]
                                in (VoxelType.AIR.value, VoxelType.SAND.value)):
                            self.world.voxels[sx, sy, sz] = spill_voxel[kind]
                            break
                ore['copper'] = ore['gold'] = 0

            self.world.ownership[self.world.ownership == colony.colony_id] = -1
            self.pheromones.trails[:, :, :, colony.colony_id, :] = 0.0
            # Political death (P12/P8): treaties and grudges die with the
            # colony; a fallen hegemon triggers the victors' quarrel
            d = self._diplomacy()
            if d.hegemon == colony.colony_id:
                from politics import VICTORS_QUARREL, power
                d.hegemon = None
                self._log_event(f"The coalition against Colony {colony.colony_id} dissolves")
                survivors = [c for c in self.colonies
                             if c.is_alive() and c.colony_id != colony.colony_id]
                if len(survivors) >= 2:
                    strongest = max(survivors, key=power)
                    for other in survivors:
                        if other.colony_id != strongest.colony_id:
                            d.rel(other.colony_id,
                                  strongest.colony_id).adjust(VICTORS_QUARREL)
            d.clear_slot(colony.colony_id, self.step_count)

            self.pending_respawns[colony.colony_id] = self.step_count + RESPAWN_DELAY
            self._log_event(f"Colony {colony.colony_id} has fallen!")
            print(f"[x] Colony {colony.colony_id} has fallen! A new colony arrives in {RESPAWN_DELAY} steps")

    def _process_respawns(self):
        """Replace fallen colony slots whose respawn is due (SPEC T6)."""
        due = [cid for cid, when in self.pending_respawns.items()
               if self.step_count >= when]
        for colony_id in due:
            self._respawn_colony(colony_id)
            del self.pending_respawns[colony_id]

    def _respawn_colony(self, colony_id: int):
        """Fill a dead colony's slot in place with a fresh arrival (SPEC T6).

        Same colony_id keeps the color and pheromone channel; genome comes
        from a mutated random survivor (fresh randomized genome if none).
        """
        w, h, d = self.world.dimensions
        survivors = [c for c in self.colonies if c.is_alive()]
        if survivors:
            genome = random.choice(survivors).genome.mutate(0.15)
        else:
            genome = ColonyGenome()
            genome.aggression = random.uniform(0.5, 1.0)
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.uniform(0.3, 1.0)
            genome.resilience = random.uniform(0.0, 0.3)
            genome.patience = random.uniform(0.3, 0.95)
            genome.loyalty = random.uniform(0.2, 0.9)

        min_distance = int(0.1 * ((w**2 + h**2)**0.5))
        living_maws = [c.maw.position for c in survivors]
        pos = None
        for _ in range(100):
            x = random.randint(w // 8, 7 * w // 8)
            y = random.randint(h // 8, 7 * h // 8)
            candidate = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))
            if all(((candidate[0] - p[0])**2 + (candidate[1] - p[1])**2)**0.5 >= min_distance
                   for p in living_maws):
                pos = candidate
                break
        if pos is None:  # crowded map: place anywhere in the safe zone
            x = random.randint(w // 8, 7 * w // 8)
            y = random.randint(h // 8, 7 * h // 8)
            pos = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))

        index = next(i for i, c in enumerate(self.colonies) if c.colony_id == colony_id)
        colony = Colony(colony_id, pos, genome)
        colony.maw.food_stored = RESPAWN_FOOD
        self.colonies[index] = colony
        if hasattr(self, 'monitors'):  # fresh colony, fresh mind (M6)
            self.monitors.pop(colony_id, None)
        if hasattr(self, 'learners'):  # and a fresh policy (T26)
            self.learners.pop(colony_id, None)
        self._diplomacy().apply_respawn_shadow(colony_id)  # folk memory (P12)
        self.world.set_voxel(*pos, VoxelType.AIR, colony_id=colony_id)
        for _ in range(3):
            colony.spawn_unit(UnitType.WORKER)
        self._log_event(f"A new colony {colony_id} arrives")
        print(f"[+] A new colony {colony_id} has arrived!")

    def _unit_label(self, unit: SandKing) -> str:
        """Display identity for decision logs and rosters."""
        return f"{unit.unit_type.name.title()} #{getattr(unit, 'unit_id', 0)}"

    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Simple AI for unit behavior - NEURAL or RULE-BASED"""
        x, y, z = unit.position

        # HIVE MONITOR (SPEC_HIVE_MONITOR M7): non-neural units cache
        # instincts on a 3-step stagger; neural soldiers are observed with
        # their hidden state inside the neural path below
        neural_soldier = (unit.unit_type == UnitType.SOLDIER and NEURAL_AVAILABLE
                          and colony.genome.use_neural
                          and colony.genome.brain is not None
                          and unit.brain_layer is not None)
        if not neural_soldier and (self.step_count + getattr(unit, 'unit_id', 0)) % 3 == 0:
            self._monitor(colony.colony_id).observe_instincts(unit, colony, self)
        
        # Workers: worker AI v2 (SPEC T18) - grab > haul > mine-continue >
        # forage > farm > mine-seek > dig. Wild food ALWAYS outranks farming
        if unit.unit_type == UnitType.WORKER:
            if getattr(unit, 'gift_to', -1) >= 0:
                return  # envoys are single-minded; they move in 5b (P3)
            # (1) Radius-2 grab: wild food +15, ripe crops +40 -> TILLED
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            acted = False
            for nx, ny, nz in neighbors:
                voxel = self.world.get_voxel(nx, ny, nz)
                if voxel in (VoxelType.FOOD, VoxelType.CORPSE):
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(HARVEST_YIELD)
                    unit.forage_target = None
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10
                    acted = True
                    break
                if voxel == VoxelType.CROP_RIPE:
                    owner = int(self.world.ownership[nx, ny, nz])
                    d = self._diplomacy()
                    foreign = owner >= 0 and owner != colony.colony_id
                    if (foreign and not d.ally(colony.colony_id, owner)
                            and d.truce_active(colony.colony_id, owner,
                                               self.step_count)):
                        continue  # truced crops are sacrosanct (P10)
                    tenders = getattr(self, 'crop_tenders', {}).pop(
                        (nx, ny, nz), set())
                    from politics import COOP_YIELD_BONUS
                    payout = CROP_YIELD * (1 + COOP_YIELD_BONUS
                                           if len(tenders) >= 2 else 1)
                    if foreign and d.ally(colony.colony_id, owner):
                        colony.maw.eat(payout * 0.6)  # co-op split (P10)
                        owner_colony = self._colony_by_id(owner)
                        if owner_colony is not None and owner_colony.is_alive():
                            owner_colony.maw.eat(payout * 0.4)
                    else:
                        colony.maw.eat(payout)
                    self.world.voxels[nx, ny, nz] = VoxelType.TILLED.value
                    unit.forage_target = None
                    self._milestone(colony, 'harvested',
                                    f"Colony {colony.colony_id} reaps its first harvest",
                                    unit)
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10
                    acted = True
                    break

            # (2) Haul carried ore home
            if not acted:
                acted = self._haul_step(unit, colony)

            # (3) Continue an adjacent valid mine
            if not acted:
                acted = self._mine_step(unit, colony)

            # (4) Forage: cached target -> scan -> scout intel -> step toward
            if not acted:
                target = unit.forage_target
                if target is not None and self.world.get_voxel(*target) not in (
                        VoxelType.FOOD, VoxelType.CORPSE, VoxelType.CROP_RIPE):
                    target = unit.forage_target = None  # stale: someone ate it
                if target is None:
                    target = self._find_food_target(unit.position,
                                                    colony.genome.foraging_range)
                    if target is None:
                        target = self._pull_known_food(colony, unit.position)
                    unit.forage_target = target
                if target is not None:
                    acted = self._step_toward(unit, target, colony)

            # (5) Farm: gated by the colony flag, sow window, and plot cap
            if not acted and getattr(colony, 'farming', False) and (
                    self._sow_window_open() or self.in_oasis(x, y)):
                acted = self._farm_step(unit, colony)

            # (5c) Tend an allied crop (P10): +1 progress per visit-step
            if not acted:
                d = self._diplomacy()
                for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                    if self.world.voxels[nx, ny, nz] != VoxelType.CROP.value:
                        continue
                    owner = int(self.world.ownership[nx, ny, nz])
                    if owner < 0 or owner == colony.colony_id:
                        continue
                    if not d.ally(colony.colony_id, owner):
                        continue
                    pos = (nx, ny, nz)
                    if pos in self._crops():
                        self.crops[pos] += 1
                        if not hasattr(self, 'crop_tenders'):
                            self.crop_tenders = {}
                        self.crop_tenders.setdefault(pos, set()).add(colony.colony_id)
                        self.crop_tenders[pos].add(owner)
                        acted = True
                        break

            # (6) Seek exposed ore
            if not acted:
                acted = self._mine_seek(unit, colony)

            # (7) No work known: random dig
            if not acted and random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    # Leave territory pheromone
                    self.pheromones.deposit(unit.position, colony.colony_id,
                                          PheromoneType.TERRITORY, 1.0)
        
        # Scouts: fast surface surveyors and sentinels (SPEC T11; P9-gated:
        # allied units passing through are not alarms - safe passage)
        elif unit.unit_type == UnitType.SCOUT:
            from politics import hostile as _hostile
            nearest_enemy, enemy_dist = None, float('inf')
            for enemy_colony in self.colonies:
                if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue
                for enemy in enemy_colony.units:
                    dist = (abs(enemy.position[0] - x) + abs(enemy.position[1] - y)
                            + abs(enemy.position[2] - z))
                    if dist < enemy_dist:
                        enemy_dist, nearest_enemy = dist, enemy

            if nearest_enemy is not None and enemy_dist <= SCOUT_ALARM_RANGE:
                # Alarm: mark danger (feeds the DANGER overlay) and flee
                self.pheromones.deposit(unit.position, colony.colony_id,
                                        PheromoneType.DANGER, 2.0)
                for _ in range(2):
                    ux, uy, uz = unit.position
                    dx = -np.sign(nearest_enemy.position[0] - ux) or random.choice([-1, 1])
                    dy = -np.sign(nearest_enemy.position[1] - uy) or random.choice([-1, 1])
                    flee_pos = (int(ux + dx), int(uy + dy), uz)
                    if (self.world.in_bounds(*flee_pos) and
                            self.world.get_voxel(*flee_pos) == VoxelType.AIR):
                        unit.move(flee_pos)
            else:
                # Survey: long-range food intel for the colony
                found = self._find_food_target(unit.position,
                                               colony.genome.foraging_range * 2)
                if found is not None and found not in colony.known_food:
                    colony.known_food.append(found)
                    del colony.known_food[:-KNOWN_FOOD_CAP]
                # Fast wander through open air (scouts do not tunnel)
                for _ in range(2):
                    ux, uy, uz = unit.position
                    direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                    new_pos = (ux + direction[0], uy + direction[1], uz + direction[2])
                    if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos) == VoxelType.AIR):
                        unit.move(new_pos)

        # Soldiers: NEURAL AI or RULE-BASED
        elif unit.unit_type == UnitType.SOLDIER:
            # NEURAL AI PATH
            if (NEURAL_AVAILABLE and 
                colony.genome.use_neural and 
                colony.genome.brain is not None and 
                unit.brain_layer is not None):
                
                # Gather enemy positions (hostile colonies only, P9)
                from politics import hostile as _hostile
                enemy_positions = []
                for enemy_colony in self.colonies:
                    if _hostile(self, colony.colony_id, enemy_colony.colony_id):
                        enemy_positions.extend([e.position for e in enemy_colony.units])
                
                # Encode state
                state_tensor = encode_soldier_state(unit, colony, self.world, enemy_positions)
                
                # Forward pass through Maw brain → Soldier layer
                with torch.no_grad():
                    encoding = colony.genome.brain(state_tensor)
                    action_probs = unit.brain_layer(encoding)
                
                # HIVE MONITOR: decode this soldier's mind (SPEC_HIVE_MONITOR M2/M3)
                if unit.brain_layer.hidden is not None:
                    hidden_vec = unit.brain_layer.hidden.squeeze(0).numpy()
                    self._monitor(colony.colony_id).observe_neural(
                        unit, colony, self, hidden_vec)

                # Decode action
                action_type, direction = decode_soldier_action(action_probs)
                
                # Execute action
                if action_type == 'move' and direction is not None:
                    new_pos = (x + direction[0], y + direction[1], z + direction[2])
                    if (self.world.in_bounds(*new_pos) and 
                        self.world.get_voxel(*new_pos).is_tunnelable()):
                        unit.move(new_pos)
                # Attack is handled by _resolve_conflicts
                
                # Update performance tracking
                unit.brain_layer.steps_alive += 1
                
            # RULE-BASED AI PATH (fallback)
            else:
                from politics import hostile as _hostile
                # T21: raze an adjacent enemy field (consumes the action)
                if colony.at_war or random.random() < colony.genome.aggression * 0.1:
                    for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                        v = self.world.voxels[nx, ny, nz]
                        owner = int(self.world.ownership[nx, ny, nz])
                        if (v in (VoxelType.TILLED.value, VoxelType.CROP.value)
                                and owner >= 0 and owner != colony.colony_id
                                and _hostile(self, colony.colony_id, owner)):
                            self.world.voxels[nx, ny, nz] = VoxelType.SAND.value
                            self._crops().pop((nx, ny, nz), None)
                            self._diplomacy().rel(owner, colony.colony_id).adjust(-6.0)
                            if not hasattr(self, '_raze_logged'):
                                self._raze_logged = {}
                            key = (colony.colony_id, owner)
                            if self.step_count - self._raze_logged.get(key, -10**9) > SEASON_LENGTH:
                                self._raze_logged[key] = self.step_count
                                self._log_event(f"Colony {colony.colony_id} razes"
                                                f" Colony {owner}'s fields!")
                                self._monitor(colony.colony_id).log_decision(
                                    self.step_count, self._unit_label(unit),
                                    "razed an enemy field",
                                    getattr(unit, 'thought', None))
                            return

                # Find closest enemy unit (hostile colonies only, P9)
                closest_enemy = None
                min_dist = float('inf')

                for enemy_colony in self.colonies:
                    if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                        continue
                    for enemy in enemy_colony.units:
                        dist = abs(enemy.position[0] - x) + abs(enemy.position[1] - y) + abs(enemy.position[2] - z)
                        if dist < min_dist:
                            min_dist = dist
                            closest_enemy = enemy
                
                # MORALE CHECK: Retreat if wounded (<10% HP)
                if unit.retreating and closest_enemy:
                    # Flee away from enemy
                    dx = -np.sign(closest_enemy.position[0] - x) if closest_enemy.position[0] != x else random.choice([-1, 1])
                    dy = -np.sign(closest_enemy.position[1] - y) if closest_enemy.position[1] != y else random.choice([-1, 1])
                    dz = 0  # Stay at same depth when fleeing
                    new_pos = (int(x + dx), int(y + dy), int(z + dz))
                    if (self.world.in_bounds(*new_pos) and 
                        self.world.get_voxel(*new_pos).is_tunnelable()):
                        unit.move(new_pos)
                # If healthy and enemy within range, ATTACK
                elif closest_enemy and min_dist < colony.genome.foraging_range:
                    if random.random() < colony.genome.aggression:
                        # Move toward enemy
                        dx = np.sign(closest_enemy.position[0] - x)
                        dy = np.sign(closest_enemy.position[1] - y)
                        dz = np.sign(closest_enemy.position[2] - z)
                        new_pos = (int(x + dx), int(y + dy), int(z + dz))
                        if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos).is_tunnelable()):
                            unit.move(new_pos)
                else:
                    # No enemy unit in range: SIEGE the nearest enemy Maw
                    # (T4, P5-scoped: cross-map raids only at the war target)
                    war_target = self._diplomacy().war_target.get(colony.colony_id)
                    closest_maw, maw_dist = None, float('inf')
                    for enemy_colony in self.colonies:
                        if not enemy_colony.is_alive():
                            continue
                        if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                            continue
                        m = enemy_colony.maw.position
                        dist = abs(m[0] - x) + abs(m[1] - y) + abs(m[2] - z)
                        # engageable = in local range, OR the war target
                        # (cross-map raids go to the TARGET only, P5)
                        if not (dist < colony.genome.foraging_range
                                or (colony.at_war
                                    and enemy_colony.colony_id == war_target)):
                            continue
                        if dist < maw_dist:
                            maw_dist, closest_maw = dist, enemy_colony.maw

                    if closest_maw is not None and random.random() < colony.genome.aggression:
                        if not self._step_toward(unit, closest_maw.position, colony):
                            pass  # boxed in this step; siege pressure resumes next step
                    # FORTIFY posture: guard the maw and fields (T26)
                    elif (self._posture(colony) == "FORTIFY"
                          and (abs(colony.maw.position[0] - x)
                               + abs(colony.maw.position[1] - y)
                               + abs(colony.maw.position[2] - z)) > FARM_RADIUS + 2):
                        self._step_toward(unit, colony.maw.position, colony)
                    # Random patrol if nothing in range
                    elif random.random() < 0.3:
                        direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                        new_pos = (x + direction[0], y + direction[1], z + direction[2])
                        if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos).is_tunnelable()):
                            unit.move(new_pos)

    
    def _resolve_conflicts(self):
        """Resolve combat with area-of-effect (radius 1) + NEURAL MATING"""
        units_to_remove = {}  # Track units to remove after combat
        mating_pairs = []  # Track soldier encounters for mating
        
        from politics import hostile
        for colony in self.colonies:
            for unit in colony.units:
                if getattr(unit, 'gift_to', -1) >= 0:
                    continue  # envoys never initiate combat (P3)
                # Check radius 1 for enemies (AoE COMBAT)
                neighbors = self.world.get_neighbors_3d(unit.position, radius=1)

                for nx, ny, nz in neighbors:
                    # Find enemy units at this position
                    for enemy_colony in self.colonies:
                        if not hostile(self, colony.colony_id,
                                       enemy_colony.colony_id):
                            continue  # truce/ally/co-belligerent (P9)

                        for enemy in enemy_colony.units:
                            if (getattr(enemy, 'gift_to', -1) == colony.colony_id):
                                continue  # inbound envoys are sacrosanct (P3)
                            if enemy.position == (nx, ny, nz):
                                # NEURAL MATING: Soldiers exchange genetic material during combat!
                                if (NEURAL_AVAILABLE and 
                                    unit.unit_type == UnitType.SOLDIER and 
                                    enemy.unit_type == UnitType.SOLDIER and
                                    unit.brain_layer is not None and 
                                    enemy.brain_layer is not None and
                                    np.random.random() < 0.05):  # 5% chance during combat
                                    mating_pairs.append((unit, enemy, colony, enemy_colony))
                                
                                # COMBAT! Apply damage with resilience
                                # (attackers credit damage_dealt for fitness)
                                if enemy.brain_layer is not None:
                                    enemy.brain_layer.damage_dealt += enemy.attack
                                if unit.brain_layer is not None:
                                    unit.brain_layer.damage_dealt += unit.attack
                                if unit.take_damage(enemy.attack, colony.genome.resilience):
                                    if colony.colony_id not in units_to_remove:
                                        units_to_remove[colony.colony_id] = []
                                    units_to_remove[colony.colony_id].append(unit)

                                    # Track kill for neural performance
                                    if enemy.brain_layer is not None:
                                        enemy.brain_layer.kills += 1
                                    # grievance: victim colony -> killer (P1)
                                    self._diplomacy().rel(
                                        colony.colony_id,
                                        enemy_colony.colony_id).adjust(-4.0)
                                    # HIVE MONITOR: outcomes carry thoughts (M4)
                                    self._monitor(enemy_colony.colony_id).log_decision(
                                        self.step_count, self._unit_label(enemy),
                                        "slew an enemy", getattr(enemy, 'thought', None))
                                    self._monitor(colony.colony_id).log_decision(
                                        self.step_count, self._unit_label(unit),
                                        "fell in battle", getattr(unit, 'thought', None))

                                if enemy.take_damage(unit.attack, enemy_colony.genome.resilience):
                                    if enemy_colony.colony_id not in units_to_remove:
                                        units_to_remove[enemy_colony.colony_id] = []
                                    units_to_remove[enemy_colony.colony_id].append(enemy)

                                    # Track kill for neural performance
                                    if unit.brain_layer is not None:
                                        unit.brain_layer.kills += 1
                                    # grievance: victim colony -> killer (P1)
                                    self._diplomacy().rel(
                                        enemy_colony.colony_id,
                                        colony.colony_id).adjust(-4.0)
                                    # HIVE MONITOR: outcomes carry thoughts (M4)
                                    self._monitor(colony.colony_id).log_decision(
                                        self.step_count, self._unit_label(unit),
                                        "slew an enemy", getattr(unit, 'thought', None))
                                    self._monitor(enemy_colony.colony_id).log_decision(
                                        self.step_count, self._unit_label(enemy),
                                        "fell in battle", getattr(enemy, 'thought', None))
        
        # MAW SIEGE: units adjacent to an enemy Maw damage it (SPEC T4)
        self._apply_maw_siege_damage()

        # NEURAL MATING: Create offspring layers
        for unit1, unit2, colony1, colony2 in mating_pairs:
            if unit1.brain_layer and unit2.brain_layer:
                # Mate soldier layers
                offspring_layer = unit1.brain_layer.mate(unit2.brain_layer)
                
                # Spawn new soldier with hybrid brain in stronger colony
                stronger_colony = colony1 if len(colony1.units) >= len(colony2.units) else colony2
                if stronger_colony.maw.food_stored > 10:
                    new_soldier = stronger_colony.maw.spawn_unit(UnitType.SOLDIER)
                    if new_soldier:
                        new_soldier.brain_layer = offspring_layer
                        stronger_colony.units.append(new_soldier)
        
        # Remove dead units and create corpses
        for colony_id, dead_units in units_to_remove.items():
            colony = next((c for c in self.colonies if c.colony_id == colony_id), None)
            if colony:
                for unit in dead_units:
                    if unit in colony.units:  # Check still in list
                        # NEURAL FOLDING: Incorporate top performers into Maw brain
                        if (NEURAL_AVAILABLE and 
                            colony.genome.use_neural and 
                            colony.genome.brain is not None and
                            unit.brain_layer is not None and
                            unit.unit_type == UnitType.SOLDIER):
                            perf_score = unit.brain_layer.get_performance_score()
                            colony.genome.brain.fold_soldier_layer(unit.brain_layer, perf_score)
                        
                        colony.remove_unit(unit)
                        self.world.set_voxel(*unit.position, VoxelType.CORPSE)

    
    def get_status(self) -> str:
        """Get simulation status string"""
        alive_colonies = [c for c in self.colonies if c.is_alive()]
        status = f"Step {self.step_count} | Colonies: {len(alive_colonies)}/{len(self.colonies)}\n"
        
        for colony in self.colonies:
            if colony.is_alive():
                status += f"  Colony {colony.colony_id}: {len(colony.units)} units, "
                status += f"{colony.maw.food_stored:.0f} food, {colony.maw.health:.0f} health\n"
        
        return status

# ============================================================================
# PERSISTENCE - the terrarium lives between sessions (SPEC T13)
# ============================================================================

def save_checkpoint(sim: 'SandKingsSimulation', path: str) -> int:
    """Pickle the whole simulation into a sqlite checkpoint row.

    Returns the new checkpoint id. Failure mode: raises on unpicklable
    state or unwritable path (callers treat persistence as best-effort).
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "step INTEGER NOT NULL, saved_at TEXT NOT NULL, state BLOB NOT NULL)")
        blob = pickle.dumps(sim, protocol=pickle.HIGHEST_PROTOCOL)
        cursor = conn.execute(
            "INSERT INTO checkpoints (step, saved_at, state) "
            "VALUES (?, datetime('now'), ?)", (sim.step_count, sqlite3.Binary(blob)))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


class _CheckpointUnpickler(pickle.Unpickler):
    """Resolve classes across the script/module identity split.

    A sim pickled by `python sandkings.py` stores classes under
    '__main__'; one pickled from `import sandkings` stores 'sandkings'.
    Checkpoints must load from either context.
    """

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            alt = 'sandkings' if module == '__main__' else '__main__'
            return super().find_class(alt, name)


def load_checkpoint(path: str) -> Optional['SandKingsSimulation']:
    """Latest checkpointed simulation from a sqlite db, or None if absent."""
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    try:
        try:
            row = conn.execute(
                "SELECT state FROM checkpoints ORDER BY id DESC LIMIT 1").fetchone()
        except sqlite3.OperationalError:  # no table: not a terrarium db yet
            return None
    finally:
        conn.close()
    if row is None:
        return None
    import io
    return _CheckpointUnpickler(io.BytesIO(row[0])).load()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Run Sand Kings simulation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sand Kings 3D Colony Simulation")
    parser.add_argument('--steps', type=int, default=None,
                        help='Simulation steps (GIF mode default 20; live mode default: run until quit)')
    parser.add_argument('--live', action='store_true',
                        help='Open a real-time pygame viewer instead of rendering GIFs')
    parser.add_argument('--sps', type=float, default=5.0,
                        help='Live mode: initial simulation steps per second')
    parser.add_argument('--persist', nargs='?', const='terrarium.db', default=None,
                        metavar='DB', help='Resume from and autosave to a sqlite '
                        'terrarium (default file: terrarium.db). Live mode: K saves.')
    parser.add_argument('--harsh', action='store_true',
                        help='Skip the 2-year dole ramp: full seasonal scarcity '
                        'from step 0 (T17)')
    parser.add_argument('--num-colonies', type=int, default=0, help='Number of colonies (0=random 3-5)')
    parser.add_argument('--width', type=int, default=80, help='World width')
    parser.add_argument('--height', type=int, default=40, help='World height')
    parser.add_argument('--depth', type=int, default=20, help='World depth')
    parser.add_argument('--use-neural', action='store_true', help='Use neural hive minds (requires PyTorch)')
    args = parser.parse_args()
    
    print("="*60)
    print("SAND KINGS SIMULATION")
    print("3D Voxel Terrarium with Cellular Automata")
    if args.use_neural and NEURAL_AVAILABLE:
        print("🧠 NEURAL HIVE MINDS ENABLED")
        print("   Maw brain + soldier layers with mating/folding/pruning")
    print("="*60)
    
    # Create or resume the simulation (SPEC T13)
    sim = None
    if args.persist:
        sim = load_checkpoint(args.persist)
        if sim is not None:
            print(f"[>] Resumed terrarium from {args.persist} at step {sim.step_count}")
    fresh = sim is None
    if fresh:
        sim = SandKingsSimulation(width=args.width, height=args.height,
                                 depth=args.depth, num_colonies=args.num_colonies)
    sim.harsh = args.harsh  # T17 ramp control (applies to resumed sims too)

    # Enable neural mode if requested (fresh sims only - resumed sims keep
    # their evolved brains)
    if args.use_neural and fresh:
        if NEURAL_AVAILABLE:
            for colony in sim.colonies:
                colony.genome.use_neural = True
                colony.genome.brain = HiveMindBrain()
                # Assign neural layers to existing units
                for unit in colony.units:
                    if unit.unit_type == UnitType.SOLDIER:
                        unit.brain_layer = SoldierLayer()
                        unit.brain_layer.steps_alive = 0
            print("✓ Neural hive minds initialized for all colonies")
        else:
            print("⚠ Neural mode requested but PyTorch not available. Using rule-based AI.")
    
    if args.live:
        # When run as a script this module is '__main__'; alias it so
        # live_view's `from sandkings import ...` binds to these same
        # classes instead of re-importing a duplicate module
        import sys
        sys.modules.setdefault('sandkings', sys.modules[__name__])
        from live_view import run_live
        run_live(sim, max_steps=args.steps, steps_per_second=args.sps,
                 save_path=args.persist)
        print("\n" + sim.get_status())
        return

    viz = Visualizer()

    # Run simulation and capture frames
    num_steps = args.steps if args.steps is not None else 20
    frames_2d = []
    frames_3d = []
    
    print(f"\nRunning {num_steps} steps...")
    
    for step in tqdm(range(num_steps)):
        sim.step()
        
        # Capture 2D slice every step
        z_level = sim.world.depth // 2
        frame_2d = viz.render_z_slice(sim.world, sim.colonies, z_level, 
                                      title=f"Step {step+1}")
        frames_2d.append(frame_2d)
        
        # Capture 3D frame every 5 steps (slower to render)
        if step % 5 == 0:
            print(f"\nGenerating 3D frame for step {step+1}...")
            frame_3d = viz.generate_3d_frame(sim.world, sim.colonies)
            frames_3d.append(frame_3d)
    
    # Save GIFs
    print("\nSaving 2D animation...")
    frames_2d[0].save('sandkings_2d.gif', save_all=True, append_images=frames_2d[1:], 
                     duration=200, loop=0)
    
    print("Saving 3D animation...")
    if frames_3d:
        frames_3d[0].save('sandkings_3d.gif', save_all=True, append_images=frames_3d[1:], 
                         duration=500, loop=0)
    
    # Final status
    print("\n" + sim.get_status())
    print("\n✓ Saved sandkings_2d.gif (2D cross-section)")
    print("✓ Saved sandkings_3d.gif (3D clustered view)")

    if args.persist:
        save_checkpoint(sim, args.persist)
        print(f"[S] Terrarium saved to {args.persist}")

    print("\nSimulation complete!")

if __name__ == "__main__":
    main()
