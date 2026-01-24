"""
Sand Kings Simulation
Combines Core War's evolution with 1pageskirmish's tactics in a 3D voxel terrarium

Inspired by GRRM's Sand Kings novella - 4 colored Maw colonies compete for territory
"""

import random
import numpy as np
import math
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
from typing import List, Tuple, Set, Optional, Dict
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image
import io
import os
from tqdm import tqdm

# ============================================================================
# VOXEL TYPES & WORLD
# ============================================================================

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

class VoxelWorld:
    """800x400x200 3D voxel terrarium with physics"""
    
    def __init__(self, width=80, height=40, depth=20):  # Start smaller for testing
        self.dimensions = (width, height, depth)
        self.width, self.height, self.depth = width, height, depth
        
        # Core voxel data
        self.voxels = np.full(self.dimensions, VoxelType.AIR.value, dtype=np.uint8)
        self.ownership = np.full(self.dimensions, -1, dtype=np.int8)  # -1 = unowned
        self.stability = np.ones(self.dimensions, dtype=np.float32)
        
        # Initialize terrain
        self._generate_terrain()
    
    def _generate_terrain(self):
        """Create base terrarium with sand, walls, and substrate"""
        w, h, d = self.dimensions
        
        # Glass walls (terrarium boundaries)
        self.voxels[0, :, :] = VoxelType.GLASS.value
        self.voxels[-1, :, :] = VoxelType.GLASS.value
        self.voxels[:, 0, :] = VoxelType.GLASS.value
        self.voxels[:, -1, :] = VoxelType.GLASS.value
        self.voxels[:, :, 0] = VoxelType.GLASS.value
        
        # Stone substrate (bottom 20%)
        substrate_height = d // 5
        self.voxels[:, :, :substrate_height] = VoxelType.STONE.value
        
        # Fill with sand (above substrate)
        sand_top = int(d * 0.7)
        self.voxels[1:-1, 1:-1, substrate_height:sand_top] = VoxelType.SAND.value
        
        # Add some stone pillars/obstacles
        num_pillars = random.randint(3, 6)
        for _ in range(num_pillars):
            px = random.randint(w//4, 3*w//4)
            py = random.randint(h//4, 3*h//4)
            pillar_height = random.randint(substrate_height, d//2)
            pillar_radius = random.randint(2, 4)
            
            for dx in range(-pillar_radius, pillar_radius+1):
                for dy in range(-pillar_radius, pillar_radius+1):
                    if dx*dx + dy*dy <= pillar_radius*pillar_radius:
                        x, y = px + dx, py + dy
                        if 1 <= x < w-1 and 1 <= y < h-1:
                            self.voxels[x, y, substrate_height:pillar_height] = VoxelType.STONE.value
        
        # Scatter initial food nodes
        num_food = (w * h) // 100
        for _ in range(num_food):
            fx = random.randint(1, w-2)
            fy = random.randint(1, h-2)
            fz = random.randint(sand_top, d-2)
            self.voxels[fx, fy, fz] = VoxelType.FOOD.value
    
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
    
    def mutate(self, mutation_rate: float = 0.1):
        """Gaussian mutation of genome parameters"""
        mutated = ColonyGenome()
        for attr in ['aggression', 'tunnel_preference', 'expansion_rate', 
                     'defense_investment', 'fertility', 'resilience']:
            current = getattr(self, attr)
            noise = np.random.normal(0, mutation_rate)
            setattr(mutated, attr, np.clip(current + noise, 0.0, 1.0))
        
        mutated.foraging_range = max(5, int(self.foraging_range + np.random.normal(0, 2)))
        mutated.swarm_threshold = max(10, int(self.swarm_threshold + np.random.normal(0, 5)))
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
    attack: int = 2
    carrying: Optional[str] = None  # 'food', 'sand', None
    task_queue: deque = field(default_factory=deque)
    
    def __post_init__(self):
        # Set stats based on unit type
        if self.unit_type == UnitType.WORKER:
            self.health = 10
            self.attack = 2
        elif self.unit_type == UnitType.SOLDIER:
            self.health = 25
            self.attack = 8
        elif self.unit_type == UnitType.SCOUT:
            self.health = 5
            self.attack = 1
    
    def move(self, new_position: Tuple[int, int, int]):
        """Move to new position"""
        self.position = new_position
    
    def take_damage(self, damage: int) -> bool:
        """Take damage, return True if killed"""
        self.health -= damage
        return self.health <= 0

class Maw:
    """Queen entity - heart of each colony"""
    
    def __init__(self, colony_id: int, position: Tuple[int, int, int], genome: ColonyGenome):
        self.colony_id = colony_id
        self.position = position
        self.genome = genome
        self.health = 100
        self.food_stored = 50
        self.spawn_queue = deque()
        self.alive = True
    
    def spawn_unit(self, unit_type: UnitType) -> Optional[SandKing]:
        """Spawn worker/soldier, costs food"""
        cost = {UnitType.WORKER: 5, UnitType.SOLDIER: 10, UnitType.SCOUT: 3}
        if self.food_stored >= cost[unit_type]:
            self.food_stored -= cost[unit_type]
            return SandKing(self.colony_id, self.position, unit_type)
        return None
    
    def eat(self, food_amount: int):
        """Consume food"""
        self.food_stored += food_amount
    
    def take_damage(self, damage: int) -> bool:
        """Take damage, return True if killed"""
        self.health -= damage
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
        Territory expansion rules (Conway-inspired):
        - Empty owned space spawns new ownership if 3+ adjacent owned cells (Birth)
        - Owned cell loses ownership if <2 or >5 adjacent owned cells (Death)
        """
        new_ownership = world.ownership.copy()
        
        for colony in colonies:
            if not colony.is_alive():
                continue
            
            # Find all territory cells
            territory_coords = np.where(world.ownership == colony.colony_id)
            
            for i in range(len(territory_coords[0])):
                x = territory_coords[0][i]
                y = territory_coords[1][i]
                z = territory_coords[2][i]
                pos = (x, y, z)
                
                neighbors = world.get_neighbors_3d(pos, radius=1)
                colony_neighbors = sum(1 for n in neighbors 
                                     if world.ownership[n] == colony.colony_id)
                
                # Death rule: too few or too many neighbors
                if colony_neighbors < 2 or colony_neighbors > 5:
                    new_ownership[x, y, z] = -1
                
                # Birth rule: check empty neighbors
                for nx, ny, nz in neighbors:
                    if (world.ownership[nx, ny, nz] == -1 and 
                        world.get_voxel(nx, ny, nz) == VoxelType.AIR):
                        neighbor_count = sum(1 for nn in world.get_neighbors_3d((nx, ny, nz))
                                           if world.ownership[nn] == colony.colony_id)
                        if neighbor_count >= 3:
                            new_ownership[nx, ny, nz] = colony.colony_id
        
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
    def generate_3d_frame(world: VoxelWorld, colonies: List[Colony], 
                         cluster_size: int = 5, alpha: float = 0.1) -> Image.Image:
        """
        Generate 3D visualization with clustering to reduce points.
        Uses outline cubes for impassable terrain (translucent).
        """
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        w, h, d = world.dimensions
        
        # Cluster voxels to reduce rendering load
        cluster_w = max(1, w // cluster_size)
        cluster_h = max(1, h // cluster_size)
        cluster_d = max(1, d // cluster_size)
        
        # Collect clustered voxel data
        for cx in range(cluster_w):
            for cy in range(cluster_h):
                for cz in range(cluster_d):
                    # Sample center of cluster
                    x = cx * cluster_size + cluster_size // 2
                    y = cy * cluster_size + cluster_size // 2
                    z = cz * cluster_size + cluster_size // 2
                    
                    if not world.in_bounds(x, y, z):
                        continue
                    
                    voxel = VoxelType(world.voxels[x, y, z])
                    owner = world.ownership[x, y, z]
                    
                    # Draw different voxel types
                    if voxel == VoxelType.STONE or voxel == VoxelType.GLASS:
                        # Outline cube for solid terrain
                        Visualizer._draw_cube_outline(ax, x, y, z, cluster_size, 
                                                     color='gray', alpha=alpha)
                    elif voxel == VoxelType.SAND:
                        ax.scatter(x, y, z, c='tan', s=10, alpha=0.3)
                    elif voxel == VoxelType.FOOD:
                        ax.scatter(x, y, z, c='green', s=50, marker='o')
                    elif voxel == VoxelType.AIR and owner >= 0:
                        # Owned territory - faint colony color
                        colony = next((c for c in colonies if c.colony_id == owner), None)
                        if colony:
                            color = np.array(colony.color) / 255.0
                            ax.scatter(x, y, z, c=[color], s=5, alpha=0.2)
        
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
        img = Image.open(buf)
        plt.close(fig)
        
        return img
    
    @staticmethod
    def _draw_cube_outline(ax, x, y, z, size, color='gray', alpha=0.1):
        """Draw outline of a cube at position"""
        # Define cube edges
        s = size / 2
        vertices = [
            [x-s, y-s, z-s], [x+s, y-s, z-s], [x+s, y+s, z-s], [x-s, y+s, z-s],
            [x-s, y-s, z+s], [x+s, y-s, z+s], [x+s, y+s, z+s], [x-s, y+s, z+s]
        ]
        
        # Define edges connecting vertices
        edges = [
            [0, 1], [1, 2], [2, 3], [3, 0],  # Bottom
            [4, 5], [5, 6], [6, 7], [7, 4],  # Top
            [0, 4], [1, 5], [2, 6], [3, 7]   # Vertical
        ]
        
        for edge in edges:
            points = [vertices[edge[0]], vertices[edge[1]]]
            ax.plot3D(*zip(*points), color=color, alpha=alpha, linewidth=0.5)

# ============================================================================
# MAIN SIMULATION ENGINE
# ============================================================================

class SandKingsSimulation:
    """Main simulation engine coordinating all systems"""
    
    def __init__(self, width=80, height=40, depth=20, num_colonies=4):
        self.world = VoxelWorld(width, height, depth)
        self.pheromones = PheromoneLayer(self.world.dimensions, num_colonies)
        self.automata = CellularAutomata()
        self.colonies: List[Colony] = []
        self.step_count = 0
        
        # Initialize colonies at corners
        self._spawn_colonies(num_colonies)
    
    def _spawn_colonies(self, num_colonies: int):
        """Spawn Maw queens at different locations"""
        w, h, d = self.world.dimensions
        
        # Place Maws at corners (middle Z level)
        positions = [
            (w//4, h//4, d//2),
            (3*w//4, h//4, d//2),
            (w//4, 3*h//4, d//2),
            (3*w//4, 3*h//4, d//2)
        ]
        
        for i in range(num_colonies):
            genome = ColonyGenome()
            # Randomize some traits
            genome.aggression = random.random()
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.random()
            
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
        
        # 4. Colony actions
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            
            # Maw spawning decisions
            if colony.maw.food_stored > 20 and len(colony.units) < 50:
                if random.random() < colony.genome.fertility:
                    unit_type = UnitType.WORKER if random.random() < 0.7 else UnitType.SOLDIER
                    colony.spawn_unit(unit_type)
            
            # Unit AI (simplified)
            for unit in colony.units[:]:  # Copy list to allow removal
                self._execute_unit_ai(unit, colony)
        
        # 5. Combat resolution
        self._resolve_conflicts()
    
    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Simple AI for unit behavior"""
        x, y, z = unit.position
        
        # Workers: dig and gather food
        if unit.unit_type == UnitType.WORKER:
            # Random tunneling
            if random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    # Leave territory pheromone
                    self.pheromones.deposit(unit.position, colony.colony_id, 
                                          PheromoneType.TERRITORY, 1.0)
            
            # Look for food nearby
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            for nx, ny, nz in neighbors:
                if self.world.get_voxel(nx, ny, nz) == VoxelType.FOOD:
                    # Move toward food
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(10)
                    break
        
        # Soldiers: patrol and attack
        elif unit.unit_type == UnitType.SOLDIER:
            # Random patrol
            if random.random() < 0.3:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                new_pos = (x + direction[0], y + direction[1], z + direction[2])
                if (self.world.in_bounds(*new_pos) and 
                    self.world.get_voxel(*new_pos).is_tunnelable()):
                    unit.move(new_pos)
    
    def _resolve_conflicts(self):
        """Resolve combat between units in same position"""
        # Group units by position
        position_map: Dict[Tuple[int,int,int], List[Tuple[Colony, SandKing]]] = {}
        
        for colony in self.colonies:
            for unit in colony.units:
                if unit.position not in position_map:
                    position_map[unit.position] = []
                position_map[unit.position].append((colony, unit))
        
        # Find conflicts
        for pos, occupants in position_map.items():
            if len(occupants) > 1:
                # Check if different colonies
                colony_ids = set(c.colony_id for c, u in occupants)
                if len(colony_ids) > 1:
                    # Combat!
                    for i, (colony1, unit1) in enumerate(occupants):
                        for colony2, unit2 in occupants[i+1:]:
                            if colony1.colony_id != colony2.colony_id:
                                # Mutual damage
                                if unit1.take_damage(unit2.attack):
                                    colony1.remove_unit(unit1)
                                    # Leave corpse
                                    self.world.set_voxel(*pos, VoxelType.CORPSE)
                                
                                if unit2.take_damage(unit1.attack):
                                    colony2.remove_unit(unit2)
    
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
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Run Sand Kings simulation"""
    print("="*60)
    print("SAND KINGS SIMULATION")
    print("3D Voxel Terrarium with Cellular Automata")
    print("="*60)
    
    # Create simulation
    sim = SandKingsSimulation(width=80, height=40, depth=20, num_colonies=4)
    viz = Visualizer()
    
    # Run simulation and capture frames
    num_steps = 20
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
            frame_3d = viz.generate_3d_frame(sim.world, sim.colonies, cluster_size=5)
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
    print("\nSimulation complete!")

if __name__ == "__main__":
    main()
