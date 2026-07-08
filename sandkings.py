"""
Sand Kings Simulation
Combines Core War's evolution with 1pageskirmish's tactics in a 3D voxel terrarium

Inspired by GRRM's Sand Kings novella - 4 colored Maw colonies compete for territory
"""

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
MAW_MAX_HEALTH = 500
MAW_REGEN = 0.5              # HP per step while unbesieged
RESPAWN_DELAY = 300          # steps a fallen colony slot stays empty
RESPAWN_FOOD = 50            # starting food for an arriving colony
WAR_CHEST = 400              # food hoard that sends a colony to war (SPEC T10)
SCOUT_ALARM_RANGE = 5        # Manhattan distance that triggers a scout alarm (SPEC T11)
KNOWN_FOOD_CAP = 8           # shared food-intel entries per colony (SPEC T11)
STORM_INTERVAL = 600         # steps between storm rolls (SPEC T12)
STORM_CHANCE = 0.5           # probability a roll spawns a storm
STORM_DURATION = 25          # steps a storm blows
STORM_COLUMNS_FRACTION = 1 / 50  # surface columns disturbed per storm step


class VoxelType(Enum):
    AIR = 0
    SAND = 1           # Tunnelable, movable
    STONE = 2          # Immovable substrate
    GLASS = 3          # Terrarium walls
    FOOD = 4           # Resource nodes
    CORPSE = 5         # Dead units = food
    TUNNEL_WALL = 6    # Reinforced colony walls
    
    def is_tunnelable(self):
        return self in (VoxelType.SAND, VoxelType.AIR)
    
    def is_solid(self):
        return self in (VoxelType.STONE, VoxelType.GLASS, VoxelType.TUNNEL_WALL)

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
    
    # Neural hive mind (Maw brain)
    brain: Optional[HiveMindBrain] = None
    use_neural: bool = False       # Toggle neural vs rule-based AI
    
    def mutate(self, mutation_rate: float = 0.1):
        """Gaussian mutation of genome parameters"""
        mutated = ColonyGenome()
        mutated.use_neural = self.use_neural
        
        for attr in ['aggression', 'tunnel_preference', 'expansion_rate', 
                     'defense_investment', 'fertility', 'resilience']:
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

@dataclass
class SandKing:
    """Individual colony unit (worker/soldier/scout)"""
    colony_id: int
    position: Tuple[int, int, int]
    unit_type: UnitType
    health: int = 10
    max_health: int = 10
    attack: int = 2
    carrying: Optional[str] = None  # 'food', 'sand', None
    task_queue: deque = field(default_factory=deque)
    retreating: bool = False  # Morale flag
    forage_target: Optional[Tuple[int, int, int]] = None  # Cached food/corpse goal
    
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
        
    def spawn_unit(self, unit_type: UnitType):
        """Spawn new unit from Maw"""
        unit = self.maw.spawn_unit(unit_type)
        if unit:
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
        
        # Generate positions ensuring min distance
        positions = []
        max_attempts = 100
        
        for i in range(num_colonies):
            for attempt in range(max_attempts):
                # Random position in safe zone (not edges), on the surface
                x = random.randint(w//8, 7*w//8)
                y = random.randint(h//8, 7*h//8)
                z = min(self.world.surface_z(x, y) + 1, d - 1)

                pos = (x, y, z)
                
                # Check distance to existing colonies
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
            genome.resilience = random.uniform(0.0, 0.3)  # Defense weaker
            
            colony = Colony(i, positions[i], genome)
            self.colonies.append(colony)
            
            # Mark starting position
            x, y, z = positions[i]
            self.world.set_voxel(x, y, z, VoxelType.AIR, colony_id=i)
            
            # Spawn initial workers
            for _ in range(3):
                colony.spawn_unit(UnitType.WORKER)
    
    def step(self):
        """Execute one simulation step"""
        self.step_count += 1
        
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

        # 3c. SANDSTORMS: wind reshapes the dunes (SPEC T12); storms never overlap
        if (self.step_count % STORM_INTERVAL == 0
                and self.storm_until <= self.step_count
                and random.random() < STORM_CHANCE):
            self.storm_until = self.step_count + STORM_DURATION
            self._storm_wind = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            self._log_event("A sandstorm rises!")
        if self.storm_until > self.step_count:
            self._blow_sand()
            if self.storm_until == self.step_count + 1:
                self._log_event("The sandstorm passes")

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

            # WAR FOOTING: a hoard converts into raids (SPEC T10).
            # Hysteresis: enter above WAR_CHEST, stand down below half of it
            was_at_war = colony.at_war
            threshold = WAR_CHEST / 2 if colony.at_war else WAR_CHEST
            colony.at_war = colony.maw.food_stored > threshold
            if colony.at_war and not was_at_war:
                self._log_event(f"Colony {colony.colony_id} marches to war!")

            # BOOTSTRAP: a colony with no units always fields a worker (SPEC T2)
            if not colony.units and colony.maw.food_stored >= 3:
                colony.spawn_unit(UnitType.WORKER)
            # Maw spawning decisions (reduced max units); war flips the mix
            elif colony.maw.food_stored > spawn_threshold and len(colony.units) < 30:
                if random.random() < colony.genome.fertility:
                    roll = random.random()
                    if colony.at_war:  # SPEC T11 mix: 0.30 W / 0.60 S / 0.10 C
                        unit_type = (UnitType.WORKER if roll < 0.30 else
                                     UnitType.SOLDIER if roll < 0.90 else UnitType.SCOUT)
                    else:              # peacetime: 0.60 W / 0.25 S / 0.15 C
                        unit_type = (UnitType.WORKER if roll < 0.60 else
                                     UnitType.SOLDIER if roll < 0.85 else UnitType.SCOUT)
                    colony.spawn_unit(unit_type)
            
            # Unit AI (simplified)
            for unit in colony.units[:]:  # Copy list to allow removal
                self._execute_unit_ai(unit, colony)
        
        # 6. Combat resolution
        self._resolve_conflicts()

        # 7. Maw regen, colony collapse, and new arrivals (SPEC T4-T6)
        self._apply_maw_regen()
        self._check_maw_deaths()
        self._process_respawns()

    def _log_event(self, message: str):
        """Append to the drama feed shown in the live HUD (SPEC T9)."""
        self.events.append((self.step_count, message))

    def _feed_terrarium(self) -> int:
        """Scatter FOOD on the surface and floor colony reserves (SPEC T1).

        Feed amount balances TARGET_POP units per colony against maintenance
        over one interval. Returns the number of voxels actually placed.
        """
        w, h, d = self.world.dimensions
        n = round(TARGET_POP * len(self.colonies) * MAINTENANCE_COST
                  * FEED_INTERVAL / HARVEST_YIELD)
        n = max(4 * len(self.colonies), min(n, (w * h) // 40))
        placed = 0
        for _ in range(n):
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
        hits = np.argwhere((box == VoxelType.FOOD.value) | (box == VoxelType.CORPSE.value))
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

    def _pull_known_food(self, colony: Colony,
                         position: Tuple[int, int, int]) -> Optional[Tuple[int, int, int]]:
        """Nearest still-valid scout-reported food; stale entries dropped (SPEC T11)."""
        valid = []
        for entry in colony.known_food:
            if self.world.get_voxel(*entry) in (VoxelType.FOOD, VoxelType.CORPSE):
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
            self.world.ownership[self.world.ownership == colony.colony_id] = -1
            self.pheromones.trails[:, :, :, colony.colony_id, :] = 0.0
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
        self.world.set_voxel(*pos, VoxelType.AIR, colony_id=colony_id)
        for _ in range(3):
            colony.spawn_unit(UnitType.WORKER)
        self._log_event(f"A new colony {colony_id} arrives")
        print(f"[+] A new colony {colony_id} has arrived!")

    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Simple AI for unit behavior - NEURAL or RULE-BASED"""
        x, y, z = unit.position
        
        # Workers: gather food/corpses with directed foraging (SPEC T3)
        if unit.unit_type == UnitType.WORKER:
            # (1) Radius-2 grab (CORPSES EDIBLE)
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            acted = False
            for nx, ny, nz in neighbors:
                voxel = self.world.get_voxel(nx, ny, nz)
                if voxel == VoxelType.FOOD or voxel == VoxelType.CORPSE:
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(HARVEST_YIELD)
                    unit.forage_target = None

                    # Track neural performance
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10

                    acted = True
                    break

            # (2)+(3) Walk toward a known food target, scanning when needed
            if not acted:
                target = unit.forage_target
                if target is not None and self.world.get_voxel(*target) not in (
                        VoxelType.FOOD, VoxelType.CORPSE):
                    target = unit.forage_target = None  # stale: someone ate it
                if target is None:
                    target = self._find_food_target(unit.position,
                                                    colony.genome.foraging_range)
                    if target is None:
                        target = self._pull_known_food(colony, unit.position)
                    unit.forage_target = target
                if target is not None:
                    acted = self._step_toward(unit, target, colony)

            # (4) No food known: random dig
            if not acted and random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    # Leave territory pheromone
                    self.pheromones.deposit(unit.position, colony.colony_id,
                                          PheromoneType.TERRITORY, 1.0)
        
        # Scouts: fast surface surveyors and sentinels (SPEC T11)
        elif unit.unit_type == UnitType.SCOUT:
            nearest_enemy, enemy_dist = None, float('inf')
            for enemy_colony in self.colonies:
                if enemy_colony.colony_id == colony.colony_id:
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
                
                # Gather enemy positions
                enemy_positions = []
                for enemy_colony in self.colonies:
                    if enemy_colony.colony_id != colony.colony_id:
                        enemy_positions.extend([e.position for e in enemy_colony.units])
                
                # Encode state
                state_tensor = encode_soldier_state(unit, colony, self.world, enemy_positions)
                
                # Forward pass through Maw brain → Soldier layer
                with torch.no_grad():
                    encoding = colony.genome.brain(state_tensor)
                    action_probs = unit.brain_layer(encoding)
                
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
                # Find closest enemy unit
                closest_enemy = None
                min_dist = float('inf')
                
                for enemy_colony in self.colonies:
                    if enemy_colony.colony_id == colony.colony_id:
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
                    # No enemy unit in range: SIEGE the nearest enemy Maw (SPEC T4)
                    closest_maw, maw_dist = None, float('inf')
                    for enemy_colony in self.colonies:
                        if enemy_colony.colony_id == colony.colony_id or not enemy_colony.is_alive():
                            continue
                        m = enemy_colony.maw.position
                        dist = abs(m[0] - x) + abs(m[1] - y) + abs(m[2] - z)
                        if dist < maw_dist:
                            maw_dist, closest_maw = dist, enemy_colony.maw

                    if (closest_maw is not None
                            and (colony.at_war or maw_dist < colony.genome.foraging_range)
                            and random.random() < colony.genome.aggression):
                        if not self._step_toward(unit, closest_maw.position, colony):
                            pass  # boxed in this step; siege pressure resumes next step
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
        
        for colony in self.colonies:
            for unit in colony.units:
                # Check radius 1 for enemies (AoE COMBAT)
                neighbors = self.world.get_neighbors_3d(unit.position, radius=1)
                
                for nx, ny, nz in neighbors:
                    # Find enemy units at this position
                    for enemy_colony in self.colonies:
                        if enemy_colony.colony_id == colony.colony_id:
                            continue
                        
                        for enemy in enemy_colony.units:
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
                                if unit.take_damage(enemy.attack, colony.genome.resilience):
                                    if colony.colony_id not in units_to_remove:
                                        units_to_remove[colony.colony_id] = []
                                    units_to_remove[colony.colony_id].append(unit)
                                    
                                    # Track kill for neural performance
                                    if enemy.brain_layer is not None:
                                        enemy.brain_layer.kills += 1
                                
                                if enemy.take_damage(unit.attack, enemy_colony.genome.resilience):
                                    if enemy_colony.colony_id not in units_to_remove:
                                        units_to_remove[enemy_colony.colony_id] = []
                                    units_to_remove[enemy_colony.colony_id].append(enemy)
                                    
                                    # Track kill for neural performance
                                    if unit.brain_layer is not None:
                                        unit.brain_layer.kills += 1
        
        # MAW SIEGE: units adjacent to an enemy Maw damage it (SPEC T4)
        for colony in self.colonies:
            if not colony.maw.alive:
                continue
            mx, my, mz = colony.maw.position
            for enemy_colony in self.colonies:
                if enemy_colony.colony_id == colony.colony_id:
                    continue
                for enemy in enemy_colony.units:
                    ex, ey, ez = enemy.position
                    if max(abs(ex - mx), abs(ey - my), abs(ez - mz)) <= 1:
                        if colony.maw.health >= MAW_MAX_HEALTH:  # first blood of a siege
                            self._log_event(f"Colony {enemy_colony.colony_id} besieges"
                                            f" Colony {colony.colony_id}!")
                        colony.maw.take_damage(enemy.attack)

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
    return pickle.loads(row[0]) if row else None


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
