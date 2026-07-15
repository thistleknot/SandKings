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

# ZCA + Kanerva sparse-distributed encoder (the maw's 85% brain, kept TIGHT).
# input -> ZCA whiten -> Kanerva sparse code (k of M protos) -> linear readout.
# Prototypes + whitening are FROZEN buffers; only the readout evolves.
KANERVA_PROTOS = 256          # M fixed prototypes (the distributed memory)
KANERVA_ACTIVE = 16           # k nearest prototypes active per input (sparsity)
ZCA_WARMUP = 64               # observations before the first whitening fit
ZCA_REFRESH = 200             # observations between whitening-matrix refits
ZCA_EPS = 1e-3                # eigenvalue floor / covariance regulariser
ZCA_COV_DECAY = 0.99          # running-covariance EMA (tracks non-stationary state)
ZCA_OBSERVE_EVERY = 8         # fold ZCA stats every N forwards (throttle the O(dim^2)
#                               covariance update; whitening only needs a running estimate)

# LEARNED shared basis (SPEC_REPR / Bundle 5): the random Kanerva codebook covers the whitened
# state manifold ~28x worse than a learned one (half its prototypes are dead, distance^2~42 collapses
# the sparse code to near-uniform mush). When on, every fresh brain loads a SHARED frozen ZCA +
# k-means codebook (learned_basis.npz, fit by tools/fit_learned_basis.py); the readout still evolves and
# the codebook stays SHARED, so grafting/GA are untouched. Gate default False -> random basis (battery
# byte-identical); the game flips it on (opt-out --no-learned-basis).
LEARNED_BASIS_ENABLED = False
_LEARNED_BASIS = None          # cached (mean, W, protos) numpy arrays, loaded once


def _load_learned_basis():
    """Load and cache learned_basis.npz (next to this module). Returns (mean, W, protos) float32
    numpy arrays, or None if the file is missing/unreadable (falls back to the random basis)."""
    global _LEARNED_BASIS
    if _LEARNED_BASIS is not None:
        return _LEARNED_BASIS if _LEARNED_BASIS != () else None
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_basis.npz")
    try:
        import numpy as _np
        d = _np.load(path)
        _LEARNED_BASIS = (d["mean"], d["W"], d["protos"])
    except Exception:
        _LEARNED_BASIS = ()        # sentinel: tried, missing
        return None
    return _LEARNED_BASIS


class ZCAWhitener(nn.Module):
    """Running ZCA whitening of the input state (SPEC_REPR): decorrelate + scale so
    Euclidean distance in the whitened space is Mahalanobis in the raw space — the
    metric Kanerva prototype matching needs. mean / running covariance / whitening
    matrix W are BUFFERS (pickle with the module, never gradient-learned). W is the
    identity until ZCA_WARMUP samples, then refit every ZCA_REFRESH observations."""

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim
        self.n = 0
        self.register_buffer('mean', torch.zeros(dim))
        self.register_buffer('cov', torch.eye(dim))
        self.register_buffer('W', torch.eye(dim))

    @torch.no_grad()
    def observe(self, x: torch.Tensor):
        """Fold one raw input into the running mean + covariance; refit periodically. A learned,
        frozen ZCA (Bundle 5) skips this so its whitening stays matched to the learned codebook."""
        if getattr(self, '_frozen', False):
            return
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.cov.mul_(ZCA_COV_DECAY).add_((1 - ZCA_COV_DECAY) * torch.outer(delta, x - self.mean))
        if self.n >= ZCA_WARMUP and self.n % ZCA_REFRESH == 0:
            c = 0.5 * (self.cov + self.cov.t()) + ZCA_EPS * torch.eye(self.dim)
            evals, evecs = torch.linalg.eigh(c)
            self.W.copy_(evecs @ torch.diag(torch.clamp(evals, min=ZCA_EPS).rsqrt()) @ evecs.t())

    @torch.no_grad()
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x.to(self.W.dtype) - self.mean) @ self.W   # guard: never float64 @ float32


class KanervaEncoder(nn.Module):
    """Sparse distributed memory (SPEC_REPR): M fixed random prototypes in the
    whitened space; the k nearest fire with a Gaussian receptive-field weight (a
    normalized sparse code). Prototypes are a FROZEN buffer — never learned/evolved.
    Returns (active indices, activations) so the readout can gather only k columns."""

    def __init__(self, dim: int, n_protos: int = KANERVA_PROTOS, k: int = KANERVA_ACTIVE):
        super().__init__()
        self.n_protos = n_protos
        self.k = min(k, n_protos)
        # A SHARED, deterministic codebook: every brain gets the SAME prototypes so
        # a readout column means the same memory cell across colonies — that makes
        # grafting/crossover of readout weights meaningful. A private generator keeps
        # the global RNG stream untouched (determinism guardrail).
        g = torch.Generator().manual_seed(0x5A11D)
        protos = torch.randn(n_protos, dim, generator=g)
        self.register_buffer('protos', protos)
        self.register_buffer('proto_sq', (protos * protos).sum(dim=1))   # precomputed norms

    @torch.no_grad()
    def forward(self, xw: torch.Tensor):
        """xw: (B, dim) whitened -> (idx (B,k) long, acts (B,k) normalized).

        Distance by the matmul identity ||x-p||^2 = |x|^2 - 2 x.p + |p|^2 — one
        (B x dim)@(dim x M) matmul, NO (B, M, dim) broadcast intermediate. This is
        what keeps the sparse encoder tight."""
        xw_sq = (xw * xw).sum(dim=1, keepdim=True)                        # (B, 1)
        d2 = xw_sq - 2.0 * (xw @ self.protos.t()) + self.proto_sq         # (B, M)
        vals, idx = torch.topk(d2, self.k, dim=1, largest=False)          # (B, k)
        acts = torch.exp(-0.5 * vals.clamp(min=0.0))
        acts = acts / (acts.sum(dim=1, keepdim=True) + 1e-8)
        return idx, acts


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
    
    def __init__(self, input_dim: int = 40, hidden_dim: int = 64,
                 encoding_dim: int = 32, depth: int = 1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim   # kept for API compat; the SDM encoder ignores it
        self.encoding_dim = encoding_dim
        self.depth = max(1, int(depth))

        # The maw's 85% brain, kept TIGHT: ZCA whiten -> Kanerva sparse code ->
        # linear readout -> encoding. ZCA + prototypes are frozen buffers; ONLY the
        # readout (Kanerva memory -> encoding) is a Parameter, so mutate/mate touch
        # nothing else. SoldierLayer still consumes an encoding_dim vector unchanged.
        self.zca = ZCAWhitener(input_dim)
        self.kanerva = KanervaEncoder(input_dim, KANERVA_PROTOS, KANERVA_ACTIVE)
        self.readout = nn.Linear(KANERVA_PROTOS, encoding_dim)
        with torch.no_grad():
            self.readout.weight.normal_(std=0.05)
            self.readout.bias.zero_()

        # Bundle 5: overwrite the random ZCA + Kanerva codebook with the SHARED LEARNED basis when on.
        # Only the frozen buffers change; the readout stays evolvable and the codebook stays shared, so
        # mutate/mate/graft/prune are untouched. Falls back to the random basis if the file is missing.
        if LEARNED_BASIS_ENABLED:
            basis = _load_learned_basis()
            if basis is not None:
                mean, W, protos = basis
                with torch.no_grad():
                    self.zca.mean.copy_(torch.as_tensor(mean, dtype=self.zca.mean.dtype))
                    self.zca.W.copy_(torch.as_tensor(W, dtype=self.zca.W.dtype))
                    self.zca._frozen = True                      # keep whitening matched to the codebook
                    p = torch.as_tensor(protos, dtype=self.kanerva.protos.dtype)
                    self.kanerva.protos.copy_(p)
                    self.kanerva.proto_sq.copy_((p * p).sum(dim=1))

        # per-prototype win-frequency EMA, backing prototype pruning
        self.proto_usage = ActivationStats()
        self.folded_layer_count = 0

    @torch.no_grad()
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode sensory input to the shared representation via ZCA -> Kanerva ->
        sparse readout. Accepts (input_dim,) or (batch, input_dim). Records ZCA
        stats and per-prototype activation (for whitening refits and pruning)
        without altering the returned encoding. Evolution-only (no autograd)."""
        squeeze = x.dim() == 1
        h = x.unsqueeze(0) if squeeze else x            # (B, input_dim)

        # Fold ZCA stats in periodically (throttled) using the batch mean — the
        # per-forward covariance update is the bulk of the cost and whitening only
        # needs a running estimate.
        self._zca_ctr = getattr(self, '_zca_ctr', 0) + 1
        if self._zca_ctr % ZCA_OBSERVE_EVERY == 0:
            self.zca.observe(h.mean(dim=0))
        xw = self.zca(h)                                # (B, input_dim) whitened
        idx, acts = self.kanerva(xw)                    # (B, k), (B, k)

        # sparse readout: gather only the k active prototype columns per row.
        # readout.weight is (encoding, M); W[:, idx] -> (encoding, B, k).
        Wg = self.readout.weight[:, idx]                # advanced index -> (E, B, k)
        enc = torch.einsum('bk,ebk->be', acts, Wg) + self.readout.bias
        enc = torch.relu(enc)                           # (B, encoding)

        # prototype-usage EMA: fraction of the batch each prototype won
        fired = torch.zeros(self.kanerva.n_protos)
        fired.scatter_add_(0, idx.reshape(-1),
                           torch.ones(idx.numel()) / max(1, h.shape[0]))
        self.proto_usage.update(fired)

        return enc.squeeze(0) if squeeze else enc

    def prune_weights(self, threshold: float = 0.01):
        """Zero the readout columns of prototypes that (almost) never win — the
        sparse code's dead memory cells. Skipped until PRUNE_WARMUP_PASSES forwards
        so early noise can't prune live prototypes. Returns newly-zeroed count."""
        if self.proto_usage.total_forward_passes < PRUNE_WARMUP_PASSES:
            return 0
        usage = self.proto_usage.get_usage_ratio()
        if usage.dim() == 0:
            return 0
        dead = usage <= threshold            # (M,) per-prototype
        if not dead.any():
            return 0
        with torch.no_grad():
            newly_zeroed = (self.readout.weight.data[:, dead] != 0).sum().item()
            self.readout.weight.data[:, dead] = 0.0
        return newly_zeroed

    def fold_soldier_layer(self, soldier_layer: 'SoldierLayer', performance_score: float):
        """Lamarckian fold: a high-performing soldier nudges the maw's readout
        (acquired traits passed up). Shapes differ (soldier output action×encoding
        vs readout encoding×M), so only the overlapping submatrix is blended (N9)."""
        if performance_score < 0.7:  # Only fold if soldier was effective
            return False
        with torch.no_grad():
            alpha = 0.1 * performance_score
            rows = min(soldier_layer.output.out_features, self.readout.out_features)
            cols = min(soldier_layer.output.in_features, self.readout.in_features)
            self.readout.weight.data[:rows, :cols] = (
                (1 - alpha) * self.readout.weight.data[:rows, :cols] +
                alpha * soldier_layer.output.weight.data[:rows, :cols])
            if self.readout.bias is not None and soldier_layer.output.bias is not None:
                self.readout.bias.data[:rows] = (
                    (1 - alpha) * self.readout.bias.data[:rows] +
                    alpha * soldier_layer.output.bias.data[:rows])
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
    
    AUG_BLEND = 0.3  # weight of the cached-context summary (SPEC_AUGMENTS)

    def __init__(self, encoding_dim: int = 32, action_dim: int = 7):
        super().__init__()

        # Recurrent memory: temporal patterns within one soldier's life (N10)
        self.memory = nn.GRUCell(encoding_dim, encoding_dim)
        self.hidden: Optional[torch.Tensor] = None  # runtime state, not a Parameter

        # Single output layer (soldier's "personality")
        self.output = nn.Linear(encoding_dim, action_dim)

        # KV-cache-style memory extension (AUG1): cache_len 0 = off, so a
        # default layer is byte-for-byte unchanged. The bank holds recent
        # hidden states; forward blends their mean into the action state.
        self.cache_len = 0
        self.mem_bank: List[torch.Tensor] = []

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
        detached each step so no autograd graph accumulates. With a memory
        augment (cache_len > 0), a summary of cached past states extends
        the effective context feeding the action head (AUG1); the raw
        hidden the probes read is unchanged.
        """
        squeeze = encoding.dim() == 1
        h_in = encoding.unsqueeze(0) if squeeze else encoding
        if self.hidden is None or self.hidden.shape != h_in.shape:
            self.hidden = torch.zeros_like(h_in)
            self.mem_bank = []
        self.hidden = self.memory(h_in, self.hidden).detach()

        effective = self.hidden
        cache_len = getattr(self, 'cache_len', 0)
        if cache_len > 0:
            bank = getattr(self, 'mem_bank', None)
            if bank is None:
                bank = self.mem_bank = []
            if bank:
                ctx = torch.stack(bank, dim=0).mean(dim=0)
                effective = self.hidden + self.AUG_BLEND * ctx
            bank.append(self.hidden)
            if len(bank) > cache_len:
                bank.pop(0)

        logits = self.output(effective)
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
                (ez - z)/d
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
        torch.tensor([health_pct], dtype=torch.float32),   # [6] = 1 feature
        torch.tensor([retreating], dtype=torch.float32),   # [7] = 1 feature
        enemy_dir,                             # [8:11] = 3 features
        torch.tensor([enemy_dist], dtype=torch.float32),   # [11] = 1 feature
        torch.tensor(local_voxels, dtype=torch.float32),   # [12:39] = 27 features
        torch.tensor([food_level], dtype=torch.float32)    # [39] = 1 feature
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
