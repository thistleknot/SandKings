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


ACTIVATION_EMA_DECAY = 0.99   # ~100-pass smoothing horizon
PRUNE_WARMUP_PASSES = 100     # no pruning until this many forwards recorded


@dataclass
class ActivationStats:
    """Per-neuron firing-frequency EMA backing weight pruning.

    update() expects a 1D per-neuron fired-fraction (batch mean of
    post-ReLU activation > 0). get_usage_ratio() returns the EMA, or a
    0-dim zero tensor before any data (callers treat dim()==0 as no-data).
    """
    ema: torch.Tensor = None
    total_forward_passes: int = 0

    def update(self, fired_fraction: torch.Tensor):
        """Fold one forward pass's per-neuron firing fraction into the EMA"""
        if self.ema is None:
            self.ema = torch.zeros_like(fired_fraction)
        self.ema = ACTIVATION_EMA_DECAY * self.ema + (1 - ACTIVATION_EMA_DECAY) * fired_fraction
        self.total_forward_passes += 1

    def get_usage_ratio(self) -> torch.Tensor:
        """Per-neuron firing EMA in [0, 1]"""
        if self.ema is None or self.total_forward_passes == 0:
            return torch.tensor(0.0)  # Return scalar zero if no data
        return self.ema


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
        
        # Track activation patterns for pruning, keyed per Linear layer
        self.activation_stats = {
            f'encoder.{i}': ActivationStats()
            for i, layer in enumerate(self.encoder)
            if isinstance(layer, nn.Linear)
        }
        
        # Performance tracking
        self.folded_layer_count = 0
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode sensory input to shared representation + track activations.

        Accepts (input_dim,) or (batch, input_dim); records per-neuron
        post-ReLU firing fractions into activation_stats without altering
        the returned encoding.
        """
        squeeze = x.dim() == 1
        h = x.unsqueeze(0) if squeeze else x

        for i, layer in enumerate(self.encoder):
            h = layer(h)
            if isinstance(layer, nn.ReLU):
                # h is the post-ReLU output of the Linear at encoder[i-1]
                with torch.no_grad():
                    fired = (h > 0).float().mean(dim=0)
                    self.activation_stats[f'encoder.{i-1}'].update(fired)

        return h.squeeze(0) if squeeze else h

    def prune_weights(self, threshold: float = 0.01):
        """Zero the weight rows and biases of neurons that rarely fire.

        A neuron is dead when its firing EMA <= threshold. Layers with fewer
        than PRUNE_WARMUP_PASSES recorded forwards are skipped so early EMA
        noise cannot prune live neurons. Returns the count of newly zeroed
        weight elements.
        """
        pruned_count = 0

        for i, layer in enumerate(self.encoder):
            if not isinstance(layer, nn.Linear):
                continue
            stats = self.activation_stats[f'encoder.{i}']
            if stats.total_forward_passes < PRUNE_WARMUP_PASSES:
                continue
            usage = stats.get_usage_ratio()
            if usage.dim() == 0:
                continue

            dead = usage <= threshold  # per-output-neuron mask
            if not dead.any():
                continue

            with torch.no_grad():
                newly_zeroed = (layer.weight.data[dead] != 0).sum().item()
                layer.weight.data[dead] = 0.0
                if layer.bias is not None:
                    layer.bias.data[dead] = 0.0
            pruned_count += newly_zeroed

        return pruned_count
    
    def fold_soldier_layer(self, soldier_layer: 'SoldierLayer', performance_score: float):
        """
        Incorporate successful soldier layer into encoder
        
        High-performing soldiers contribute to Maw's evolution
        """
        if performance_score < 0.7:  # Only fold if soldier was effective
            return False
        
        # Blend soldier's output layer back into encoder's final layer
        # This is like Lamarckian evolution - acquired traits passed up.
        # Shapes differ (soldier 7x32 vs encoder 32x64), so only the
        # overlapping submatrix is blended (spec N9).
        with torch.no_grad():
            encoder_final_layer = self.encoder[-2]  # Last linear layer before ReLU
            soldier_output_layer = soldier_layer.output

            # Weighted blend: 90% encoder, 10% soldier (conservative folding)
            alpha = 0.1 * performance_score  # Scale by performance

            rows = min(soldier_output_layer.out_features, encoder_final_layer.out_features)
            cols = min(soldier_output_layer.in_features, encoder_final_layer.in_features)

            # Fold soldier weights into the overlapping region of the encoder
            encoder_final_layer.weight.data[:rows, :cols] = (
                (1 - alpha) * encoder_final_layer.weight.data[:rows, :cols] +
                alpha * soldier_output_layer.weight.data[:rows, :cols]
            )

            if encoder_final_layer.bias is not None and soldier_output_layer.bias is not None:
                encoder_final_layer.bias.data[:rows] = (
                    (1 - alpha) * encoder_final_layer.bias.data[:rows] +
                    alpha * soldier_output_layer.bias.data[:rows]
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

        # Recurrent memory: temporal patterns within one soldier's life (N10)
        self.memory = nn.GRUCell(encoding_dim, encoding_dim)
        self.hidden: Optional[torch.Tensor] = None  # runtime state, not a Parameter

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
        """Map shared encoding through recurrent memory to action probabilities.

        Hidden state persists across calls (one soldier's life) and is
        detached each step so no autograd graph accumulates.
        """
        squeeze = encoding.dim() == 1
        h_in = encoding.unsqueeze(0) if squeeze else encoding
        if self.hidden is None or self.hidden.shape != h_in.shape:
            self.hidden = torch.zeros_like(h_in)
        self.hidden = self.memory(h_in, self.hidden).detach()
        logits = self.output(self.hidden)
        probs = torch.softmax(logits, dim=-1)
        return probs.squeeze(0) if squeeze else probs
    
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
        
        # Crossover: uniform mask + Gaussian mutation over ALL parameters
        # (memory and output alike, spec N10). zip() relies on identical
        # parameter registration order across instances; guard the count so
        # a future architecture divergence fails loudly, not silently.
        self_params = list(self.named_parameters())
        other_params = list(other.named_parameters())
        assert len(self_params) == len(other_params), \
            "mate() requires structurally identical SoldierLayers"
        with torch.no_grad():
            for (_, child_p), (_, self_p), (_, other_p) in zip(
                    child.named_parameters(), self_params, other_params):
                mask = torch.rand_like(self_p) > 0.5
                child_p.data = torch.where(mask, self_p.data, other_p.data)
                child_p.data += torch.randn_like(child_p) * mutation_rate

        # Genetic tracking; memory starts blank (hidden = None from __init__)
        child.generation = max(self.generation, other.generation) + 1
        child.parent_ids = [id(self), id(other)]

        return child

    def clone(self) -> 'SoldierLayer':
        """Asexual reproduction (for Maw spawning); memory starts blank"""
        child = SoldierLayer(
            encoding_dim=self.output.in_features,
            action_dim=self.output.out_features
        )
        child.load_state_dict(self.state_dict())
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
    
    # Local voxel neighborhood (3×3×3 = 27 voxels exactly)
    local_voxels = []
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                nx, ny, nz = x+dx, y+dy, z+dz
                if world.in_bounds(nx, ny, nz):
                    voxel = world.get_voxel(nx, ny, nz)
                    local_voxels.append(float(voxel.value))
                else:
                    local_voxels.append(0.0)  # Out of bounds = solid
    
    # Colony food
    food_level = colony.maw.food_stored / 100.0  # Normalize
    
    # Concatenate all features (should be exactly 40)
    state = torch.cat([
        pos,                                    # [0:3] = 3 features
        maw_rel,                               # [3:6] = 3 features
        torch.tensor([health_pct]),            # [6] = 1 feature
        torch.tensor([retreating]),            # [7] = 1 feature
        enemy_dir,                             # [8:11] = 3 features
        torch.tensor([enemy_dist]),            # [11] = 1 feature
        torch.tensor(local_voxels),            # [12:39] = 27 features
        torch.tensor([food_level])             # [39] = 1 feature
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
