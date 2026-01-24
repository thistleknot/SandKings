"""
Neural Hive Mind Evolution System

Architecture:
- Maw Brain (Colony): Shared encoder, evolves slowly, only dies when conquered
- Soldier Layers: Individual output layers, mate during combat
- Folding: Top-performing soldier layers get incorporated into Maw
- Pruning: Rarely activated weights are removed

Design:
    Maw Brain (Encoder)
         ↓
    [Soldier Layer₁] [Soldier Layer₂] [Soldier Layer₃]
         ↓               ↓               ↓
       Action          Action          Action
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
import copy


@dataclass
class ActivationStats:
    """Track which weights are actually used"""
    activation_counts: torch.Tensor = None
    total_forward_passes: int = 0
    
    def update(self, activations: torch.Tensor):
        """Record which neurons fired"""
        if self.activation_counts is None:
            self.activation_counts = torch.zeros_like(activations)
        
        # Track non-zero activations
        self.activation_counts += (activations.abs() > 1e-6).float()
        self.total_forward_passes += 1
    
    def get_usage_ratio(self) -> torch.Tensor:
        """Get % of time each weight was active"""
        if self.activation_counts is None or self.total_forward_passes == 0:
            return torch.tensor(0.0)  # Return scalar zero if no data
        return self.activation_counts / self.total_forward_passes


class HiveMindBrain(nn.Module):
    """
    Colony-level brain (Maw's shared encoder)
    
    Evolves slowly - only mutates when Maw survives battles
    Incorporates successful soldier layers via folding
    """
    
    def __init__(self, input_dim: int = 40, hidden_dim: int = 64, encoding_dim: int = 32):
        super().__init__()
        
        # Shared perception encoder (slow evolution)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, encoding_dim),
            nn.ReLU()
        )
        
        # Track activation patterns for pruning
        self.activation_stats = {}
        for name, param in self.named_parameters():
            self.activation_stats[name] = ActivationStats()
        
        # Performance tracking
        self.battles_survived = 0
        self.total_kills = 0
        self.folded_layer_count = 0
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode sensory input to shared representation + track activations"""
        # Pass through encoder
        encoding = self.encoder(x)
        
        # Track activations for pruning
        with torch.no_grad():
            for name, param in self.named_parameters():
                if 'weight' in name:
                    # Track which weights contributed to this forward pass
                    activation_mask = (param.abs() > 1e-6).float()
                    self.activation_stats[name].update(activation_mask)
        
        return encoding
        # Track activations for pruning
        for i, layer in enumerate(self.encoder):
            if isinstance(layer, nn.Linear):
                layer_name = f'encoder.{i}'
                if layer_name in self.activation_stats:
                    # Track post-activation values
                    with torch.no_grad():
                        activation = encoding if i == len(self.encoder) - 1 else self.encoder[:i+1](x)
                        self.activation_stats[layer_name].update(activation)
        
        return encoding
    
    def prune_weights(self, threshold: float = 0.01):
        """Remove weights that are rarely activated"""
        pruned_count = 0
        
        for name, param in self.named_parameters():
            if 'weight' in name and name in self.activation_stats:
                usage = self.activation_stats[name].get_usage_ratio()
                
                # Skip if no tracking data yet (scalar zero)
                if usage.dim() == 0:
                    continue
                
                # Create mask: keep weights used > threshold% of time
                mask = usage > threshold
                
                # Zero out rarely used weights
                with torch.no_grad():
                    param.data *= mask.float()
                
                pruned_count += (~mask).sum().item()
        
        return pruned_count
    
    def fold_soldier_layer(self, soldier_layer: 'SoldierLayer', performance_score: float):
        """
        Incorporate successful soldier layer into encoder
        
        High-performing soldiers contribute to Maw's evolution
        """
        if performance_score < 0.7:  # Only fold if soldier was effective
            return False
        
        # Blend soldier's output layer back into encoder's final layer
        # This is like Lamarckian evolution - acquired traits passed up
        with torch.no_grad():
            encoder_final_layer = self.encoder[-2]  # Last linear layer before ReLU
            soldier_output_layer = soldier_layer.output
            
            # Weighted blend: 90% encoder, 10% soldier (conservative folding)
            alpha = 0.1 * performance_score  # Scale by performance
            
            # Fold soldier weights into encoder
            encoder_final_layer.weight.data = (
                (1 - alpha) * encoder_final_layer.weight.data +
                alpha * soldier_output_layer.weight.data[:encoder_final_layer.out_features, :]
            )
            
            if encoder_final_layer.bias is not None and soldier_output_layer.bias is not None:
                encoder_final_layer.bias.data = (
                    (1 - alpha) * encoder_final_layer.bias.data +
                    alpha * soldier_output_layer.bias.data[:encoder_final_layer.out_features]
                )
        
        self.folded_layer_count += 1
        return True
    
    def mutate(self, mutation_rate: float = 0.05):
        """Slow Maw-level mutation (only when Maw survives)"""
        with torch.no_grad():
            for param in self.parameters():
                # Gaussian noise
                noise = torch.randn_like(param) * mutation_rate
                param.data += noise
                
                # Occasional structural mutation (10% chance)
                if np.random.random() < 0.1:
                    # Flip sign of random weights (polarity reversal)
                    mask = torch.rand_like(param) < 0.05
                    param.data[mask] *= -1


class SoldierLayer(nn.Module):
    """
    Individual soldier's output layer (fast evolution)
    
    Each soldier has its own layer that decides actions
    Soldiers mate when they encounter each other (combat or cooperation)
    """
    
    def __init__(self, encoding_dim: int = 32, action_dim: int = 7):
        super().__init__()
        
        # Single output layer (soldier's "personality")
        self.output = nn.Linear(encoding_dim, action_dim)
        
        # Performance tracking
        self.kills = 0
        self.damage_dealt = 0
        self.damage_taken = 0
        self.steps_alive = 0
        self.food_gathered = 0
        
        # Genetic lineage
        self.generation = 0
        self.parent_ids = []
    
    def forward(self, encoding: torch.Tensor) -> torch.Tensor:
        """Map shared encoding to action probabilities"""
        return torch.softmax(self.output(encoding), dim=-1)
    
    def get_performance_score(self) -> float:
        """Calculate soldier effectiveness (for folding decisions)"""
        if self.steps_alive == 0:
            return 0.0
        
        # Multi-factor fitness
        kill_score = self.kills * 0.4
        survival_score = (self.steps_alive / 100.0) * 0.3
        efficiency_score = (self.damage_dealt / max(1, self.damage_taken)) * 0.2
        gather_score = (self.food_gathered / 10.0) * 0.1
        
        return np.clip(kill_score + survival_score + efficiency_score + gather_score, 0.0, 1.0)
    
    def mate(self, other: 'SoldierLayer', mutation_rate: float = 0.15) -> 'SoldierLayer':
        """
        Sexual reproduction during combat encounters
        
        Creates offspring layer by blending parent weights
        """
        child = SoldierLayer(
            encoding_dim=self.output.in_features,
            action_dim=self.output.out_features
        )
        
        # Crossover: blend parent weights
        with torch.no_grad():
            # Uniform crossover mask
            mask = torch.rand_like(self.output.weight) > 0.5
            
            child.output.weight.data = torch.where(
                mask,
                self.output.weight.data,
                other.output.weight.data
            )
            
            if self.output.bias is not None:
                bias_mask = torch.rand_like(self.output.bias) > 0.5
                child.output.bias.data = torch.where(
                    bias_mask,
                    self.output.bias.data,
                    other.output.bias.data
                )
            
            # Mutation
            noise = torch.randn_like(child.output.weight) * mutation_rate
            child.output.weight.data += noise
            
            if child.output.bias is not None:
                bias_noise = torch.randn_like(child.output.bias) * mutation_rate
                child.output.bias.data += bias_noise
        
        # Genetic tracking
        child.generation = max(self.generation, other.generation) + 1
        child.parent_ids = [id(self), id(other)]
        
        return child
    
    def clone(self) -> 'SoldierLayer':
        """Asexual reproduction (for Maw spawning)"""
        child = SoldierLayer(
            encoding_dim=self.output.in_features,
            action_dim=self.output.out_features
        )
        
        with torch.no_grad():
            child.output.weight.data = self.output.weight.data.clone()
            if self.output.bias is not None:
                child.output.bias.data = self.output.bias.data.clone()
        
        child.generation = self.generation
        return child


def encode_soldier_state(unit, colony, world, enemy_positions) -> torch.Tensor:
    """
    Convert soldier's sensory input to neural network input
    
    Returns: [40] tensor with:
    - [0:3] Own position (normalized)
    - [3:6] Maw position relative
    - [6] Health %
    - [7] Retreating flag
    - [8:11] Nearest enemy direction
    - [11] Nearest enemy distance
    - [12:39] Local voxel neighborhood (3×3×3)
    - [39] Colony food level (normalized)
    """
    x, y, z = unit.position
    maw_x, maw_y, maw_z = colony.maw.position
    w, h, d = world.dimensions
    
    # Normalize positions
    pos = torch.tensor([x/w, y/h, z/d], dtype=torch.float32)
    maw_rel = torch.tensor([
        (maw_x - x)/w,
        (maw_y - y)/h,
        (maw_z - z)/d
    ], dtype=torch.float32)
    
    # Unit state
    health_pct = unit.health / unit.max_health
    retreating = float(unit.retreating)
    
    # Nearest enemy
    if enemy_positions:
        min_dist = float('inf')
        nearest_enemy = None
        for ex, ey, ez in enemy_positions:
            dist = ((x-ex)**2 + (y-ey)**2 + (z-ez)**2)**0.5
            if dist < min_dist:
                min_dist = dist
                nearest_enemy = (ex, ey, ez)
        
        if nearest_enemy:
            ex, ey, ez = nearest_enemy
            enemy_dir = torch.tensor([
                (ex - x)/w,
                (ey - y)/h,
                (ez - z)/h
            ], dtype=torch.float32)
            enemy_dist = min_dist / max(w, h, d)
        else:
            enemy_dir = torch.zeros(3)
            enemy_dist = 1.0
    else:
        enemy_dir = torch.zeros(3)
        enemy_dist = 1.0
    
    # Local voxel neighborhood (3×3×3 = 27 voxels + padding = 28)
    local_voxels = []
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                nx, ny, nz = x+dx, y+dy, z+dz
                if world.in_bounds(nx, ny, nz):
                    voxel = world.get_voxel(nx, ny, nz)
                    local_voxels.append(float(voxel.value))
                else:
                    local_voxels.append(0.0)
    
    # Pad to 28
    while len(local_voxels) < 28:
        local_voxels.append(0.0)
    
    # Colony food
    food_level = colony.maw.food_stored / 100.0  # Normalize
    
    # Concatenate all features
    state = torch.cat([
        pos,                                    # [0:3]
        maw_rel,                               # [3:6]
        torch.tensor([health_pct]),            # [6]
        torch.tensor([retreating]),            # [7]
        enemy_dir,                             # [8:11]
        torch.tensor([enemy_dist]),            # [11]
        torch.tensor(local_voxels[:28]),       # [12:40]
        torch.tensor([food_level])             # [40]
    ])
    
    return state


def decode_soldier_action(action_probs: torch.Tensor) -> Tuple[str, int]:
    """
    Convert neural output to game action
    
    Actions:
    0-5: Move [+x, -x, +y, -y, +z, -z]
    6: Attack nearest enemy
    """
    action_idx = action_probs.argmax().item()
    
    if action_idx < 6:
        directions = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        return 'move', directions[action_idx]
    else:
        return 'attack', None
