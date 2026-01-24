"""
Sand Kings v1.3 - GPU Acceleration with PyTorch
Replaces NumPy operations with GPU-accelerated PyTorch tensors

Usage:
    python sandkings_evolution.py --mode demo --sim-steps 5000 --gpu
"""

import torch
import torch.nn.functional as F
import random
from typing import Tuple, List, Dict

# Import all components from base (we'll only accelerate physics)
from sandkings import (
    VoxelType, VoxelWorld, UnitType, PheromoneType, PheromoneLayer,
    ColonyGenome, SandKing, Maw, Colony, Visualizer, CellularAutomata
)


class SandKingsSimulationGPU:
    """
    GPU-accelerated Sand Kings simulation.
    Uses GPU for physics (gravity, pheromone diffusion).
    Uses CPU for unit AI (tunneling, foraging, combat).
    """
    
    def __init__(self, width: int = 80, height: int = 40, depth: int = 20, 
                 num_colonies: int = 4, device: str = 'cuda'):
        self.device = torch.device(device if torch.cuda.is_available() else 'cpu')
        self.step_count = 0
        
        # Standard CPU components (full behavior)
        self.world = VoxelWorld(width, height, depth)
        self.pheromones = PheromoneLayer((width, height, depth), num_colonies)
        self.automata = CellularAutomata()
        self.colonies: List[Colony] = []
        
        # GPU tensors for physics acceleration
        self._init_gpu_tensors()
        
        # Initialize colonies
        self._spawn_colonies(num_colonies)
    
    def _init_gpu_tensors(self):
        """Create GPU tensors for accelerated physics"""
        w, h, d = self.world.dimensions
        
        # GPU copy of voxel grid (synced periodically)
        self.voxels_gpu = torch.tensor(self.world.voxels, dtype=torch.int8, device=self.device)
        
        # GPU pheromone layers
        self.pheromones_gpu = torch.zeros((4, w, h, d), dtype=torch.float32, device=self.device)
        
        # Diffusion kernel
        self.diffusion_kernel = torch.ones((4, 1, 3, 3, 3), device=self.device) / 27.0
        self.diffusion_kernel[:, :, 1, 1, 1] = 0.5
    
    def _spawn_colonies(self, num_colonies: int):
        """Spawn Maw queens at different locations"""
        w, h, d = self.world.dimensions
        
        positions = [
            (w//4, h//4, d//2),
            (3*w//4, h//4, d//2),
            (w//4, 3*h//4, d//2),
            (3*w//4, 3*h//4, d//2)
        ]
        
        for i in range(min(num_colonies, 4)):
            genome = ColonyGenome()
            genome.aggression = random.random()
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.random()
            
            colony = Colony(i, positions[i], genome)
            self.colonies.append(colony)
            
            x, y, z = positions[i]
            self.world.set_voxel(x, y, z, VoxelType.AIR, colony_id=i)
            
            # Spawn initial workers
            for _ in range(3):
                colony.spawn_unit(UnitType.WORKER)
    
    def _sync_to_gpu(self):
        """Sync CPU voxel state to GPU"""
        self.voxels_gpu = torch.tensor(self.world.voxels, dtype=torch.int8, device=self.device)
    
    def _sync_from_gpu(self):
        """Sync GPU voxel state back to CPU"""
        self.world.voxels = self.voxels_gpu.cpu().numpy()
    
    def _apply_gravity_gpu(self):
        """GPU-accelerated gravity"""
        # Find falling voxels (sand/food above air)
        is_falling = ((self.voxels_gpu == VoxelType.SAND.value) | 
                     (self.voxels_gpu == VoxelType.FOOD.value))
        
        below = torch.roll(self.voxels_gpu, shifts=1, dims=2)
        below[:, :, 0] = VoxelType.STONE.value
        
        can_fall = is_falling & (below == VoxelType.AIR.value)
        
        falling_types = self.voxels_gpu[can_fall].clone()
        self.voxels_gpu[can_fall] = VoxelType.AIR.value
        
        fall_coords = torch.nonzero(can_fall, as_tuple=False)
        if len(fall_coords) > 0:
            fall_coords[:, 2] -= 1
            valid = fall_coords[:, 2] >= 0
            fall_coords = fall_coords[valid]
            falling_types = falling_types[valid]
            
            if len(fall_coords) > 0:
                self.voxels_gpu[fall_coords[:, 0], fall_coords[:, 1], fall_coords[:, 2]] = falling_types
    
    def _diffuse_pheromones_gpu(self, decay_rate: float = 0.95):
        """GPU-accelerated pheromone diffusion"""
        pheromones = self.pheromones_gpu.unsqueeze(0)
        diffused = F.conv3d(pheromones, self.diffusion_kernel, padding=1, groups=4)
        self.pheromones_gpu = (diffused.squeeze(0) * decay_rate).clamp(0, 100)
    
    def step(self):
        """Execute one simulation step with hybrid GPU/CPU"""
        self.step_count += 1
        
        # 1. GPU Physics (fast)
        self._sync_to_gpu()
        
        if self.step_count % 5 == 0:
            self._apply_gravity_gpu()
        
        self._diffuse_pheromones_gpu()
        
        self._sync_from_gpu()
        
        # 2. CPU Cellular automata (very expensive, run rarely)
        if self.step_count % 100 == 0:
            self.automata.apply_territory_spread(self.world, self.colonies)
        
        # 3. Food consumption and starvation (DARWINIAN PRESSURE)
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            
            # Maintenance cost: 0.5 food per unit per step
            maintenance_cost = len(colony.units) * 0.5
            colony.maw.food_stored -= maintenance_cost
            
            # Starvation: kill units if food negative
            if colony.maw.food_stored < 0 and colony.units:
                units_to_kill = []
                while colony.maw.food_stored < 0 and colony.units:
                    dead_unit = random.choice(colony.units)
                    units_to_kill.append(dead_unit)
                    colony.maw.food_stored += 2  # Recover some food
                
                for dead_unit in units_to_kill:
                    colony.remove_unit(dead_unit)
                    self.world.set_voxel(*dead_unit.position, VoxelType.CORPSE)
            
            # Adjust spawn threshold by expansion_rate
            spawn_threshold = 20 / max(0.1, colony.genome.expansion_rate)
            
            # Maw spawning
            if colony.maw.food_stored > spawn_threshold and len(colony.units) < 50:
                if random.random() < colony.genome.fertility:
                    unit_type = UnitType.WORKER if random.random() < 0.7 else UnitType.SOLDIER
                    colony.spawn_unit(unit_type)
            
            # Unit AI
            for unit in colony.units[:]:
                self._execute_unit_ai(unit, colony)
        
        # 4. Combat resolution
        self._resolve_conflicts()
    
    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Full AI for unit behavior (same as CPU version)"""
        x, y, z = unit.position
        
        if unit.unit_type == UnitType.WORKER:
            # Look for food or corpses nearby (CORPSES NOW EDIBLE)
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            found_food = False
            for nx, ny, nz in neighbors:
                voxel = self.world.get_voxel(nx, ny, nz)
                if voxel == VoxelType.FOOD or voxel == VoxelType.CORPSE:
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(10)
                    found_food = True
                    break
            
            # If no food found, tunnel
            if not found_food and random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    self.pheromones.deposit(unit.position, colony.colony_id, 
                                          PheromoneType.TERRITORY, 1.0)
        
        elif unit.unit_type == UnitType.SOLDIER:
            # MORALE CHECK: Retreat if wounded (<10% HP)
            if unit.retreating:
                # Find closest enemy to flee from
                closest_enemy = None
                min_dist = float('inf')
                for enemy_colony in self.colonies:
                    if enemy_colony.colony_id == colony.colony_id:
                        continue
                    for enemy in enemy_colony.units:
                        dist = abs(enemy.position[0] - x) + abs(enemy.position[1] - y)
                        if dist < min_dist:
                            min_dist = dist
                            closest_enemy = enemy
                
                if closest_enemy:
                    # Flee away
                    dx = -1 if closest_enemy.position[0] > x else (1 if closest_enemy.position[0] < x else random.choice([-1, 1]))
                    dy = -1 if closest_enemy.position[1] > y else (1 if closest_enemy.position[1] < y else random.choice([-1, 1]))
                    dz = 0
                    new_pos = (x + dx, y + dy, z + dz)
                    if (self.world.in_bounds(*new_pos) and 
                        self.world.get_voxel(*new_pos).is_tunnelable()):
                        unit.move(new_pos)
            else:
                # Find closest enemy unit (ENEMY-SEEKING AI)
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
                
                # If enemy within foraging range, move toward it
                if closest_enemy and min_dist < colony.genome.foraging_range:
                    if random.random() < colony.genome.aggression:
                        # Move toward enemy
                        dx = int(closest_enemy.position[0] - x)
                        dy = int(closest_enemy.position[1] - y)
                        dz = int(closest_enemy.position[2] - z)
                        # Normalize to unit step
                        if dx != 0:
                            dx = 1 if dx > 0 else -1
                        if dy != 0:
                            dy = 1 if dy > 0 else -1
                        if dz != 0:
                            dz = 1 if dz > 0 else -1
                        new_pos = (x + dx, y + dy, z + dz)
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
        """Resolve combat with area-of-effect (radius 1) - AGGRESSION > DEFENSE"""
        units_to_remove = {}
        
        for colony in self.colonies:
            for unit in colony.units:
                # Skip retreating units
                if hasattr(unit, 'retreating') and unit.retreating:
                    continue
                    
                # Check radius 1 for enemies (AoE COMBAT)
                neighbors = self.world.get_neighbors_3d(unit.position, radius=1)
                
                for nx, ny, nz in neighbors:
                    for enemy_colony in self.colonies:
                        if enemy_colony.colony_id == colony.colony_id:
                            continue
                        
                        for enemy in enemy_colony.units:
                            if enemy.position == (nx, ny, nz):
                                # COMBAT! Increased damage (12 base), resilience capped at 30%
                                if unit.take_damage(enemy.attack, colony.genome.resilience * 0.6):  # Weaker defense
                                    if colony.colony_id not in units_to_remove:
                                        units_to_remove[colony.colony_id] = []
                                    units_to_remove[colony.colony_id].append(unit)
                                
                                if enemy.take_damage(unit.attack, enemy_colony.genome.resilience * 0.6):
                                    if enemy_colony.colony_id not in units_to_remove:
                                        units_to_remove[enemy_colony.colony_id] = []
                                    units_to_remove[enemy_colony.colony_id].append(enemy)
        
        # Remove dead units and create corpses
        for colony_id, dead_units in units_to_remove.items():
            colony = next((c for c in self.colonies if c.colony_id == colony_id), None)
            if colony:
                for unit in dead_units:
                    if unit in colony.units:
                        colony.remove_unit(unit)
                        self.world.set_voxel(*unit.position, VoxelType.CORPSE)
                    for i, (colony1, unit1) in enumerate(occupants):
                        for colony2, unit2 in occupants[i+1:]:
                            if colony1.colony_id != colony2.colony_id:
                                if unit1.take_damage(unit2.attack):
                                    colony1.remove_unit(unit1)
                                    self.world.set_voxel(*pos, VoxelType.CORPSE)
                                
                                if unit2.take_damage(unit1.attack):
                                    colony2.remove_unit(unit2)
    
    def get_status(self) -> str:
        """Get simulation status"""
        alive_colonies = [c for c in self.colonies if c.is_alive()]
        status = f"Step {self.step_count} | Colonies: {len(alive_colonies)}/{len(self.colonies)}\n"
        
        for colony in self.colonies:
            if colony.is_alive():
                status += f"  Colony {colony.colony_id}: {len(colony.units)} units, "
                status += f"{colony.maw.food_stored:.0f} food, {colony.maw.health:.0f} health\n"
        
        return status
