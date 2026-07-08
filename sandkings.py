"""
Sand Kings Simulation
Combines Core War's evolution with 1pageskirmish's tactics in a 3D voxel terrarium

Inspired by GRRM's Sand Kings novella - 4 colored Maw colonies compete for territory
"""

import random
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
        
        # Scatter initial food nodes (reduced for resource scarcity)
        num_food = (w * h) // 500  # Was // 100, now 5x less
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
        self.health = 100
        self.food_stored = 200  # Higher starting food
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
        self.pheromones = PheromoneLayer(self.world.dimensions, num_colonies)
        self.automata = CellularAutomata()
        self.colonies: List[Colony] = []
        self.step_count = 0
        
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
                # Random position in safe zone (not edges)
                x = random.randint(w//8, 7*w//8)
                y = random.randint(h//8, 7*h//8)
                z = d//2  # Mid-depth
                
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
            genome.expansion_rate = random.random()
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
            
            # Maintenance cost: 1.0 food per unit per step (balanced pressure)
            maintenance_cost = len(colony.units) * 1.0
            colony.maw.food_stored -= maintenance_cost
            
            # Starvation: kill units if food negative
            if colony.maw.food_stored < 0 and colony.units:
                units_to_kill = []
                while colony.maw.food_stored < 0 and colony.units:
                    dead_unit = random.choice(colony.units)
                    units_to_kill.append(dead_unit)
                    colony.maw.food_stored += 2  # Recover some food from dead unit
                
                for dead_unit in units_to_kill:
                    colony.remove_unit(dead_unit)
                    # Create edible corpse
                    self.world.set_voxel(*dead_unit.position, VoxelType.CORPSE)
            
            # Adjust spawn threshold by expansion_rate
            spawn_threshold = 30 / max(0.1, colony.genome.expansion_rate)
            
            # Maw spawning decisions (reduced max units)
            if colony.maw.food_stored > spawn_threshold and len(colony.units) < 30:
                if random.random() < colony.genome.fertility:
                    unit_type = UnitType.WORKER if random.random() < 0.7 else UnitType.SOLDIER
                    colony.spawn_unit(unit_type)
            
            # Unit AI (simplified)
            for unit in colony.units[:]:  # Copy list to allow removal
                self._execute_unit_ai(unit, colony)
        
        # 5. Combat resolution
        self._resolve_conflicts()
    
    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Simple AI for unit behavior - NEURAL or RULE-BASED"""
        x, y, z = unit.position
        
        # Workers: dig and gather food/corpses
        if unit.unit_type == UnitType.WORKER:
            # Look for food or corpses nearby (CORPSES NOW EDIBLE)
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            found_food = False
            for nx, ny, nz in neighbors:
                voxel = self.world.get_voxel(nx, ny, nz)
                if voxel == VoxelType.FOOD or voxel == VoxelType.CORPSE:
                    # Move toward food/corpse
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(15)  # Both give 15 food
                    
                    # Track neural performance
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10
                    
                    found_food = True
                    break
            
            # If no food found, tunnel
            if not found_food and random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    # Leave territory pheromone
                    self.pheromones.deposit(unit.position, colony.colony_id, 
                                          PheromoneType.TERRITORY, 1.0)
        
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
                    # Random patrol if no enemies nearby
                    if random.random() < 0.3:
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
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Run Sand Kings simulation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sand Kings 3D Colony Simulation")
    parser.add_argument('--steps', type=int, default=20, help='Number of simulation steps')
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
    
    # Create simulation
    sim = SandKingsSimulation(width=args.width, height=args.height, 
                             depth=args.depth, num_colonies=args.num_colonies)
    
    # Enable neural mode if requested
    if args.use_neural:
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
    
    viz = Visualizer()
    
    # Run simulation and capture frames
    num_steps = args.steps
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
    print("\nSimulation complete!")

if __name__ == "__main__":
    main()
