"""
Sand Kings v1.1 - Evolution Extensions
Adds MapElites, Ollama LLM, and behavioral DSL to v1.0

Usage:
    python sandkings_evolution.py --mode demo --sim-steps 100
    python sandkings_evolution.py --mode evolve --use-llm --rounds 10
"""

import asyncio
import argparse
import hashlib
import re
import pickle
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
import numpy as np
from tqdm import tqdm

# Import v1.0 base
from sandkings import (
    VoxelWorld, VoxelType, ColonyGenome, SandKing, UnitType,
    Maw, Colony, PheromoneLayer, PheromoneType,
    CellularAutomata, Visualizer, SandKingsSimulation
)

# ============================================================================
# OLLAMA LLM INTEGRATION
# ============================================================================

class OllamaGPT:
    """Ollama-compatible LLM client"""
    
    def __init__(self, model: str = "hf.co/unsloth/granite-4.0-h-1b-GGUF:granite-4.0-h-1b-Q6_K.gguf",
                 base_url: str = "http://localhost:11434/v1",
                 system_prompt: str = "",
                 temperature: float = 0.7):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(base_url=base_url, api_key="ollama")
            self.available = True
        except ImportError:
            print("⚠ openai package not installed. LLM evolution disabled.")
            self.available = False
    
    async def get_completion_async(self, prompt: str, n_responses: int = 1) -> List[str]:
        if not self.available:
            return ["# Fallback\\nWHEN near_food THEN dig PRIORITY 1"]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                n=n_responses,
            )
            return [r.message.content for r in response.choices]
        except Exception as e:
            print(f"LLM error: {e}")
            return ["# Error fallback\\nWHEN near_food THEN dig PRIORITY 1"]
    
    async def get_multiple_completions_async(self, prompts: List[str], n_responses: int = 1) -> List[List[str]]:
        results = await asyncio.gather(*(self.get_completion_async(p, n_responses) for p in prompts))
        return results

# ============================================================================
# BEHAVIORAL DSL
# ============================================================================

@dataclass
class BehaviorRule:
    conditions: List[str]
    action: str
    priority: int = 5

class BehaviorInterpreter:
    """Parse and execute WHEN/THEN DSL scripts"""
    
    def __init__(self, script: str):
        self.rules = self._parse_script(script)
        self.rules.sort(key=lambda r: r.priority)
    
    def _parse_script(self, script: str) -> List[BehaviorRule]:
        rules = []
        for line in script.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            match = re.match(r'WHEN (.+?) THEN (\w+)(?: PRIORITY (\d+))?', line, re.IGNORECASE)
            if match:
                conditions_str = match.group(1)
                conditions = [c.strip() for c in re.split(r'\s+AND\s+', conditions_str, flags=re.IGNORECASE)]
                action = match.group(2)
                priority = int(match.group(3)) if match.group(3) else 5
                rules.append(BehaviorRule(conditions, action, priority))
        
        return rules
    
    def get_action(self, context: Dict[str, bool]) -> Optional[str]:
        for rule in self.rules:
            if self._evaluate_conditions(rule.conditions, context):
                return rule.action
        return None
    
    def _evaluate_conditions(self, conditions: List[str], context: Dict[str, bool]) -> bool:
        for cond in conditions:
            if cond.startswith('NOT '):
                if context.get(cond[4:].lower(), False):
                    return False
            else:
                if not context.get(cond.lower(), False):
                    return False
        return True

# ============================================================================
# MAPELITES
# ============================================================================

@dataclass
class SandKingsPhenotype:
    """Evolvable phenotype for MAP-Elites"""
    genome: ColonyGenome
    behavioral_script: str = ""
    fitness: float = -np.inf
    bc: Tuple[int, int] = None
    outputs: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: hashlib.sha256(str(np.random.random()).encode()).hexdigest()[:8])
    parent_id: str = None

class SandKingsMapElites:
    """Quality-diversity evolution"""
    
    def __init__(self):
        self.archive: Dict[Tuple[int, int], SandKingsPhenotype] = {}
        self.history: List[SandKingsPhenotype] = []
    
    def sample(self) -> Optional[SandKingsPhenotype]:
        if not self.archive:
            return None
        return np.random.choice(list(self.archive.values()))
    
    def place(self, phenotype: SandKingsPhenotype) -> bool:
        if phenotype.bc is None or phenotype.fitness is None:
            return False
        
        should_place = (phenotype.bc not in self.archive or 
                       phenotype.fitness > self.archive[phenotype.bc].fitness)
        
        if should_place:
            self.archive[phenotype.bc] = phenotype
        
        self.history.append(phenotype)
        return should_place
    
    def get_bc_features(self, phenotype: SandKingsPhenotype) -> Tuple[int, int]:
        """Bin by (territory, aggression)"""
        territory = phenotype.outputs.get('territory_size', 0)
        aggression = phenotype.outputs.get('aggression_events', 0)
        
        for bc, thresh in enumerate([50, 200, 500, 1000, 2000, np.inf]):
            if territory < thresh:
                bc_territory = bc
                break
        
        for bc, thresh in enumerate([5, 20, 50, 100, 200, np.inf]):
            if aggression < thresh:
                bc_aggression = bc
                break
        
        return (bc_territory, bc_aggression)
    
    def get_fitness(self, phenotype: SandKingsPhenotype) -> float:
        w = phenotype.outputs
        return (w.get('survival_time', 0) * 1.0 + 
                w.get('population_peak', 0) * 0.1 +
                w.get('territory_size', 0) * 0.01 +
                w.get('enemy_kills', 0) * 0.5)
    
    def get_best(self) -> Optional[SandKingsPhenotype]:
        if not self.archive:
            return None
        return max(self.archive.values(), key=lambda p: p.fitness)
    
    def get_coverage(self) -> float:
        return len(self.archive) / 36  # 6x6 grid

# ============================================================================
# LLM BEHAVIOR GENERATOR
# ============================================================================

class SandKingsGPT:
    """LLM-powered behavioral script generation"""
    
    def __init__(self, model: str = "hf.co/unsloth/granite-4.0-h-1b-GGUF:granite-4.0-h-1b-Q6_K.gguf",
                 temperature: float = 0.7):
        system_prompt = """You are an expert at designing Sand Kings colony behaviors.
Generate tactical decision rules using this DSL:

WHEN <condition> [AND <condition>...] THEN <action> [PRIORITY <n>]

Conditions: near_food, near_enemy, low_health, carrying_food, in_territory, near_maw
Actions: dig, attack, flee, return_food, patrol, fortify
Priority: 1 (highest) to 9 (lowest)

Example:
WHEN near_enemy AND low_health THEN flee PRIORITY 1
WHEN near_food AND NOT carrying_food THEN dig PRIORITY 2
WHEN carrying_food THEN return_food PRIORITY 3

Generate 5-10 rules for effective colony behavior."""
        
        self.gpt = OllamaGPT(model=model, system_prompt=system_prompt, temperature=temperature)
        self.new_prompt = "Create a behavioral script for a Sand Kings colony."
        self.mutate_prompt = "Modify this script to improve survival:\n\n"
    
    async def new_behavior_async(self, n: int = 1) -> List[SandKingsPhenotype]:
        if not self.gpt.available:
            # Fallback: simple hardcoded behaviors
            scripts = ["WHEN near_food THEN dig PRIORITY 1\nWHEN near_enemy THEN attack PRIORITY 2"] * n
        else:
            responses = await self.gpt.get_multiple_completions_async([self.new_prompt] * n)
            scripts = [self._clean(r[0]) for r in responses]
        
        return [SandKingsPhenotype(genome=ColonyGenome(), behavioral_script=s) for s in scripts]
    
    async def mutate_behavior_async(self, phenotypes: List[SandKingsPhenotype]) -> List[SandKingsPhenotype]:
        if not self.gpt.available:
            # Fallback: genome mutation only
            return [SandKingsPhenotype(genome=p.genome.mutate(0.1), behavioral_script=p.behavioral_script, parent_id=p.id) 
                    for p in phenotypes]
        
        prompts = [f"{self.mutate_prompt}{p.behavioral_script}" for p in phenotypes]
        responses = await self.gpt.get_multiple_completions_async(prompts)
        
        new_phenotypes = []
        for old_p, response_list in zip(phenotypes, responses):
            script = self._clean(response_list[0]) if response_list else old_p.behavioral_script
            new_p = SandKingsPhenotype(
                genome=old_p.genome.mutate(0.05),
                behavioral_script=script,
                parent_id=old_p.id
            )
            new_phenotypes.append(new_p)
        
        return new_phenotypes
    
    def _clean(self, script: str) -> str:
        script = re.sub(r'```[a-z]*\n', '', script)
        script = re.sub(r'```', '', script)
        return script.strip()

# ============================================================================
# ENHANCED SIMULATION WITH BEHAVIORAL SCRIPTS
# ============================================================================

class EnhancedSandKingsSimulation(SandKingsSimulation):
    """v1.1 simulation with behavioral script support"""
    
    def __init__(self, *args, phenotype: Optional[SandKingsPhenotype] = None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize metrics for all colonies
        for colony in self.colonies:
            if not hasattr(colony, 'metrics'):
                colony.metrics = {'territory': 0, 'population': 0, 'aggression_events': 0, 'enemy_kills': 0}
        
        # Override colony 0 with phenotype
        if phenotype:
            self.colonies[0].genome = phenotype.genome
            if phenotype.behavioral_script:
                self.colonies[0].behavior_interpreter = BehaviorInterpreter(phenotype.behavioral_script)
                # Initialize context tracking
                for unit in self.colonies[0].units:
                    unit.behavior_context = {}
    
    def step(self):
        """Enhanced step with context updates"""
        self.step_count += 1
        
        # Physics
        if self.step_count % 5 == 0:
            self.world.apply_gravity()
        
        # Cellular automata
        if self.step_count % 10 == 0:
            self.automata.apply_territory_spread(self.world, self.colonies)
        
        # Pheromones
        self.pheromones.step()
        
        # Colony actions with context updates
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            
            # Spawning
            if colony.maw.food_stored > 20 and len(colony.units) < 50:
                if np.random.random() < colony.genome.fertility:
                    unit_type = UnitType.WORKER if np.random.random() < 0.7 else UnitType.SOLDIER
                    colony.spawn_unit(unit_type)
            
            # Unit AI with behavior context
            for unit in colony.units[:]:
                self._execute_enhanced_ai(unit, colony)
        
        # Combat
        self._enhanced_combat()
        
        # Collect metrics
        for colony in self.colonies:
            colony.metrics['territory'] = np.sum(self.world.ownership == colony.colony_id)
            colony.metrics['population'] = len(colony.units)
    
    def _execute_enhanced_ai(self, unit: SandKing, colony: Colony):
        """Unit AI with behavioral script support"""
        x, y, z = unit.position
        
        # Update context
        self._update_unit_context(unit, colony)
        
        # Try behavioral script
        action = None
        if hasattr(colony, 'behavior_interpreter') and colony.behavior_interpreter:
            action = colony.behavior_interpreter.get_action(unit.behavior_context)
        
        # Execute action
        if action == 'dig':
            self._action_dig(unit, colony)
        elif action == 'attack':
            self._action_attack(unit, colony)
        elif action == 'flee':
            self._action_flee(unit, colony)
        elif action == 'return_food':
            self._action_return_food(unit, colony)
        else:  # patrol or fallback
            self._action_patrol(unit, colony)
    
    def _update_unit_context(self, unit: SandKing, colony: Colony):
        """Update unit's behavioral context"""
        # Initialize if needed
        if not hasattr(unit, 'behavior_context'):
            unit.behavior_context = {}
        
        x, y, z = unit.position
        unit.behavior_context['low_health'] = unit.health < 10
        unit.behavior_context['carrying_food'] = unit.carrying == 'food'
        unit.behavior_context['in_territory'] = self.world.ownership[x, y, z] == colony.colony_id
        
        neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
        unit.behavior_context['near_food'] = any(
            self.world.get_voxel(nx, ny, nz) == VoxelType.FOOD for nx, ny, nz in neighbors
        )
        
        unit.behavior_context['near_enemy'] = False
        for other in self.colonies:
            if other.colony_id != colony.colony_id:
                for enemy in other.units:
                    dist = abs(enemy.position[0] - x) + abs(enemy.position[1] - y) + abs(enemy.position[2] - z)
                    if dist <= 3:
                        unit.behavior_context['near_enemy'] = True
                        break
        
        maw_dist = abs(colony.maw.position[0] - x) + abs(colony.maw.position[1] - y) + abs(colony.maw.position[2] - z)
        unit.behavior_context['near_maw'] = maw_dist <= 5
    
    def _action_dig(self, unit: SandKing, colony: Colony):
        x, y, z = unit.position
        directions = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        direction = directions[np.random.randint(len(directions))]
        if self.world.tunnel(unit.position, direction, colony.colony_id):
            unit.move((x + direction[0], y + direction[1], z + direction[2]))
    
    def _action_attack(self, unit: SandKing, colony: Colony):
        x, y, z = unit.position
        colony.metrics['aggression_events'] = colony.metrics.get('aggression_events', 0) + 1
        for other in self.colonies:
            if other.colony_id != colony.colony_id and other.units:
                target = other.units[0]
                dx = np.sign(target.position[0] - x)
                dy = np.sign(target.position[1] - y)
                dz = np.sign(target.position[2] - z)
                new_pos = (x + dx, y + dy, z + dz)
                if self.world.in_bounds(*new_pos) and self.world.get_voxel(*new_pos).is_tunnelable():
                    unit.move(new_pos)
                break
    
    def _action_flee(self, unit: SandKing, colony: Colony):
        x, y, z = unit.position
        flee_dirs = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0)]
        flee_dir = flee_dirs[np.random.randint(len(flee_dirs))]
        new_pos = (x + flee_dir[0], y + flee_dir[1], z + flee_dir[2])
        if self.world.in_bounds(*new_pos) and self.world.get_voxel(*new_pos).is_tunnelable():
            unit.move(new_pos)
    
    def _action_return_food(self, unit: SandKing, colony: Colony):
        x, y, z = unit.position
        mx, my, mz = colony.maw.position
        dx, dy, dz = np.sign(mx - x), np.sign(my - y), np.sign(mz - z)
        new_pos = (x + dx, y + dy, z + dz)
        if self.world.in_bounds(*new_pos) and self.world.get_voxel(*new_pos).is_tunnelable():
            unit.move(new_pos)
            if new_pos == colony.maw.position and unit.carrying == 'food':
                colony.maw.eat(10)
                unit.carrying = None
    
    def _action_patrol(self, unit: SandKing, colony: Colony):
        # Default random behavior
        if unit.unit_type == UnitType.WORKER:
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            for nx, ny, nz in neighbors:
                if self.world.get_voxel(nx, ny, nz) == VoxelType.FOOD:
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    colony.maw.eat(10)
                    return
            
            if np.random.random() < colony.genome.tunnel_preference:
                self._action_dig(unit, colony)
        
        elif unit.unit_type == UnitType.SOLDIER:
            if np.random.random() < 0.3:
                x, y, z = unit.position
                directions = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
                direction = directions[np.random.randint(len(directions))]
                new_pos = (x + direction[0], y + direction[1], z + direction[2])
                if self.world.in_bounds(*new_pos) and self.world.get_voxel(*new_pos).is_tunnelable():
                    unit.move(new_pos)
    
    def _enhanced_combat(self):
        """Combat with cover/criticals"""
        position_map = {}
        for colony in self.colonies:
            for unit in colony.units:
                if unit.position not in position_map:
                    position_map[unit.position] = []
                position_map[unit.position].append((colony, unit))
        
        for pos, occupants in position_map.items():
            if len(occupants) > 1:
                colony_ids = set(c.colony_id for c, u in occupants)
                if len(colony_ids) > 1:
                    for i, (colony1, unit1) in enumerate(occupants):
                        for colony2, unit2 in occupants[i+1:]:
                            if colony1.colony_id != colony2.colony_id:
                                terrain = self.world.get_voxel(*pos)
                                cover = 1 if terrain == VoxelType.TUNNEL_WALL else 0
                                
                                ap1 = int(colony1.genome.aggression * 3)
                                hit1 = np.random.randint(1, 7)
                                if hit1 >= (4 - ap1 + cover):
                                    dmg1 = unit1.attack * (2 if hit1 == 6 else 1)
                                    if unit2.take_damage(dmg1):
                                        colony2.remove_unit(unit2)
                                        colony1.metrics['enemy_kills'] = colony1.metrics.get('enemy_kills', 0) + 1
                                        self.world.set_voxel(*pos, VoxelType.CORPSE)
                                
                                ap2 = int(colony2.genome.aggression * 3)
                                hit2 = np.random.randint(1, 7)
                                if hit2 >= (4 - ap2 + cover):
                                    dmg2 = unit2.attack * (2 if hit2 == 6 else 1)
                                    if unit1.take_damage(dmg2):
                                        colony1.remove_unit(unit1)
                                        colony2.metrics['enemy_kills'] = colony2.metrics.get('enemy_kills', 0) + 1

# ============================================================================
# EVOLUTION ORCHESTRATOR
# ============================================================================

class SandKingsEvolution:
    """MapElites evolution loop"""
    
    def __init__(self, args):
        self.args = args
        self.mapelites = SandKingsMapElites()
        self.gpt = SandKingsGPT() if args.use_llm else None
    
    async def run_evolution(self):
        print(f"Evolution: {self.args.rounds} rounds × {self.args.iterations} iterations")
        print(f"LLM: {'Ollama' if self.args.use_llm else 'Disabled (genome mutation only)'}")
        
        for round_num in range(self.args.rounds):
            print(f"\n{'='*60}")
            print(f"Round {round_num + 1}/{self.args.rounds}")
            print(f"{'='*60}")
            
            if not self.mapelites.archive:
                phenotypes = await self._init_population(10)
            else:
                phenotypes = await self._mutate_population(self.args.iterations)
            
            for phenotype in tqdm(phenotypes, desc="Evaluating"):
                phenotype = self._evaluate(phenotype)
                self.mapelites.place(phenotype)
            
            best = self.mapelites.get_best()
            coverage = self.mapelites.get_coverage()
            print(f"Coverage: {coverage*100:.1f}% | Best fitness: {best.fitness:.1f}")
            
            if (round_num + 1) % 5 == 0:
                self._save_checkpoint(round_num + 1)
    
    async def _init_population(self, n: int) -> List[SandKingsPhenotype]:
        if self.gpt:
            return await self.gpt.new_behavior_async(n)
        return [SandKingsPhenotype(genome=ColonyGenome(), behavioral_script="") for _ in range(n)]
    
    async def _mutate_population(self, n: int) -> List[SandKingsPhenotype]:
        parents = [self.mapelites.sample() for _ in range(n)]
        if self.gpt:
            return await self.gpt.mutate_behavior_async(parents)
        return [SandKingsPhenotype(genome=p.genome.mutate(0.1), behavioral_script=p.behavioral_script, parent_id=p.id) 
                for p in parents]
    
    def _evaluate(self, phenotype: SandKingsPhenotype) -> SandKingsPhenotype:
        sim = EnhancedSandKingsSimulation(
            width=self.args.width, height=self.args.height, depth=self.args.depth,
            num_colonies=4, phenotype=phenotype
        )
        
        territory_history = []
        population_history = []
        
        for step in range(self.args.sim_steps):
            sim.step()
            colony = sim.colonies[0]
            if not colony.is_alive():
                break
            
            territory_history.append(colony.metrics.get('territory', 0))
            population_history.append(colony.metrics.get('population', 0))
        
        phenotype.outputs = {
            'survival_time': step,
            'territory_size': max(territory_history) if territory_history else 0,
            'population_peak': max(population_history) if population_history else 0,
            'aggression_events': sim.colonies[0].metrics.get('aggression_events', 0),
            'enemy_kills': sim.colonies[0].metrics.get('enemy_kills', 0),
        }
        
        phenotype.fitness = self.mapelites.get_fitness(phenotype)
        phenotype.bc = self.mapelites.get_bc_features(phenotype)
        
        return phenotype
    
    def _save_checkpoint(self, round_num: int):
        filename = f"sandkings_archive_r{round_num}.pkl"
        with open(filename, 'wb') as f:
            pickle.dump(self.mapelites.archive, f)
        print(f"✓ Checkpoint: {filename}")

# ============================================================================
# CLI MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sand Kings v1.1 Evolution")
    parser.add_argument('--mode', choices=['demo', 'evolve'], default='demo')
    parser.add_argument('--sim-steps', choices=[50, 100, 200, 500, 1000, 2000], 
                       type=int, default=100)
    parser.add_argument('--width', type=int, default=80)
    parser.add_argument('--height', type=int, default=40)
    parser.add_argument('--depth', type=int, default=20)
    parser.add_argument('--use-llm', action='store_true')
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--iterations', type=int, default=20)
    
    args = parser.parse_args()
    
    print("="*60)
    print("SAND KINGS v1.1 - EVOLUTION")
    print(f"Mode: {args.mode.upper()} | Steps: {args.sim_steps}")
    print("="*60)
    
    if args.mode == 'demo':
        # Single sim with visualization
        sim = SandKingsSimulation(width=args.width, height=args.height, 
                                  depth=args.depth, num_colonies=4)
        viz = Visualizer()
        
        frames_2d = []
        frames_3d = []
        print(f"\nRunning {args.sim_steps} steps...")
        
        for step in tqdm(range(args.sim_steps)):
            sim.step()
            
            # 2D slice every step
            z_level = sim.world.depth // 2
            frame_2d = viz.render_z_slice(sim.world, sim.colonies, z_level)
            frames_2d.append(frame_2d)
            
            # 3D scatter every 5 steps
            if step % 5 == 0:
                frame_3d = viz.generate_3d_frame(sim.world, sim.colonies)
                frames_3d.append(frame_3d)
        
        # Save both animations
        frames_2d[0].save('sandkings_demo_2d.gif', save_all=True, append_images=frames_2d[1:], 
                         duration=max(50, 5000//len(frames_2d)), loop=0)
        
        if frames_3d:
            frames_3d[0].save('sandkings_demo_3d.gif', save_all=True, append_images=frames_3d[1:],
                             duration=500, loop=0)
        
        print(f"\n{sim.get_status()}")
        print("✓ Saved sandkings_demo_2d.gif")
        if frames_3d:
            print("✓ Saved sandkings_demo_3d.gif")
    
    else:  # evolve
        evolution = SandKingsEvolution(args)
        asyncio.run(evolution.run_evolution())
    
    print("\nComplete!")

if __name__ == "__main__":
    main()
