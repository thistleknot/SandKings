"""The maw's real-RL policy — the 85% tier of the 85:15 maw/spawn split.

Reframe (2026-07-12, see docs/decisions/2026-07-12-frozen-fm-router-feudal-brain.md):
NO LLM, NO foundation model. A small **gradient-trained** policy sits on top of the FROZEN
encoder (HiveMindBrain: frozen ZCA+Kanerva buffers) and learns, by REINFORCE against a
survival/dominance reward, to emit a colony-level **directive** — a vector of continuous
"constants" (aggression, mobility, verticality) that condition the spawn (the 15% tier's
bounded residual reads it).

v2 upgrade (2026-07-13, same decision doc "v2 RL upgrade"): the estimator and the GA↔RL
coupling are brought to SOTA + the INSPIRATIONS design laws:
  * RLOO leave-one-out baseline (unbiased, S&B §13.4; best in the small-group K=8 regime).
  * Entropy bonus (anti-collapse; AEPO 2510.08141) so colonies keep diverging over a long game.
  * Warm-start from the colony's genome instinct ("never tabula rasa", chess RL_FINDINGS):
    the untrained directive EQUALS the genome's aggression/expansion/tunnel instincts.
  * The evolved `plasticity` gene sets the RL learning rate (the Baldwin effect made literal).
  * A 3rd directive lever (verticality) + a kills term in the reward.

This is real deep-RL (gradients + reward), distinct from the evolutionary HiveMindBrain
(which trains under torch.no_grad). The frozen encoder is the "start-intelligent" baseline;
only this thin policy head + the spawn residual learn.

Contract:
  Require   - torch available; obs is a finite (obs_dim,) or (B,obs_dim) float tensor.
  Guarantee - act() returns a directive in (0,1)^directive_dim and a scalar log_prob;
              update() applies exactly one REINFORCE step and returns the loss.
  Maintain  - a batch rollout buffer; RLOO/mean baseline for variance reduction.
  Assert    - directive is finite and within (0,1); deterministic act() draws no noise.

Identity-at-neutral: MAW_RL_ENABLED defaults False; the sim never constructs or calls a
policy while the gate is off, so the regression battery stays byte-identical. The policy
is also pickle-safe (plain nn.Module + plain lists), so it round-trips in the whole-sim
checkpoint.
"""
import math

import torch
import torch.nn as nn

# --- identity-at-neutral gate (flip in the game entrypoint via globals()) ---
MAW_RL_ENABLED = False

# --- hyperparameters ---
MAW_DIRECTIVE_DIM = 3        # colony constants the spawn condition on: aggression, mobility, verticality
MAW_HIDDEN = 32
MAW_LR = 3e-3
MAW_LOG_STD_INIT = -0.5      # exp(-0.5) ~ 0.61 initial exploration std
MAW_GRAD_CLIP = 1.0          # clip the noisy REINFORCE gradient norm (between-batch stability)
MAW_SIGN_SGD = False         # opt-in: quantize the gradient to its sign (signSGD; robust to noise)
MAW_RLOO = True              # RLOO leave-one-out baseline (unbiased, small-group; S&B §13.4) vs mean+whiten
MAW_ENTROPY_COEF = 0.01      # entropy bonus: sustain exploration, resist premature collapse (AEPO)
MAW_UPDATE_EVERY = 8         # flush a maw batch-REINFORCE update every K batch-cycles
SPAWN_UPDATE_EVERY = 32      # flush a spawn-residual update every K accumulated spawn-steps
MAW_DIRECTIVE_STRENGTH = 0.5  # bounds how far a directive can tilt an action (neutral at 0.5)
MAW_RESIDUAL_CLIP = 0.15     # 15% tier "play": max |additive residual| on a spawn action logit
MAW_GAMMA_LO = 0.80          # patience gene -> discount band (interior; chess-deep-q λ≈0.9 sweet spot)
MAW_GAMMA_HI = 0.97          # never 0 or 1 — the bias-variance middle beats both endpoints
MAW_DREAM_ENABLED = True     # Chill-season elite replay (Lin 1992 "the maws dream"; baseline-on)
MAW_DREAM_BUFFER = 64        # ring buffer of (obs, directive, reward) lifetime memories
MAW_DREAM_TOPK = 8           # elites (highest-reward memories) replayed per dream
MAW_DREAM_EPOCHS = 3         # supervised imitation passes over the elites
MAW_DREAM_LR = 1e-3          # behavior-cloning lr — self-distillation toward own best (chess: distill > self-play)

_HALF_LOG_2PIE = 0.5 * math.log(2.0 * math.pi * math.e)   # per-dim Gaussian entropy constant


def patience_to_gamma(patience: float) -> float:
    """Map the evolved `patience` gene (0..1) to a discount γ in the interior band
    [MAW_GAMMA_LO, MAW_GAMMA_HI] — never 0 or 1. Sutton&Barto: γ is the temperament knob (long- vs
    short-horizon); chess-deep-q found the interior λ≈0.9 the sweet spot (TD-Gammon-style bootstrapped
    returns beat both TD(0) and MC endpoints). Patient colonies weight long-horizon reward more."""
    p = min(1.0, max(0.0, float(patience)))
    return MAW_GAMMA_LO + (MAW_GAMMA_HI - MAW_GAMMA_LO) * p


def _discounted_returns(rewards, gamma: float):
    """Backward discounted return G_t = r_t + γ·r_{t+1} + γ²·r_{t+2} + ... over the rollout buffer
    (S&B §13.4: the REINFORCE return carries γ). Returns a plain list, same length as rewards."""
    out = [0.0] * len(rewards)
    g = 0.0
    for t in range(len(rewards) - 1, -1, -1):
        g = float(rewards[t]) + gamma * g
        out[t] = g
    return out


def _gaussian_entropy(log_std: torch.Tensor) -> torch.Tensor:
    """Differential entropy of a diagonal Gaussian: sum_i (log_std_i + 0.5*log(2*pi*e)).

    A function of log_std ONLY (independent of the sampled action), so it can be added to the
    loss straight from the policy's parameter. Maximizing it lifts log_std → sustained
    exploration (the anti-collapse term)."""
    return (log_std + _HALF_LOG_2PIE).sum()


def _reinforce_update(log_probs, rewards, optimizer, entropy=None,
                      clip=None, sign=None, rloo=None) -> float:
    """Batch-REINFORCE with a variance-reducing baseline. Shared by the maw policy (85%) and the
    spawn residual policy (15%). Returns the loss value.

    Baseline (S&B §13.4 — any action-independent baseline is unbiased, only variance changes):
      * RLOO (default, MAW_RLOO): advantage_i = r_i - mean(r_{j != i}), the leave-one-out mean.
        Unbiased and lowest-variance in the small-group regime (our maw K=8). [Ahmadian et al.]
      * else: mean-baseline with std whitening (the K<=1 / opt-out fallback).

    Entropy (AEPO / entropy-collapse): if `entropy` (a grad-carrying scalar from the policy's
    log_std) is given, subtract MAW_ENTROPY_COEF * entropy so the update also lifts exploration.

    The between-batch update is STABILIZED (REINFORCE is high-variance): the gradient is either
    sign-quantized (signSGD, robust to heavy-tailed noise) or norm-clipped. Both, and the RLOO
    switch, are read from the module globals at call time so a run can flip them; pass
    clip/sign/rloo explicitly to override."""
    clip = MAW_GRAD_CLIP if clip is None else clip
    sign = MAW_SIGN_SGD if sign is None else sign
    rloo = MAW_RLOO if rloo is None else rloo
    lp = torch.stack(list(log_probs))
    r = torch.tensor([float(x) for x in rewards], dtype=lp.dtype, device=lp.device)
    k = r.numel()
    if rloo and k > 1:
        baseline = (r.sum() - r) / (k - 1)        # leave-one-out mean (independent of sample i)
        adv = r - baseline
    else:                                          # fallback: mean baseline + std whitening
        adv = r - r.mean()
        std = float(adv.std()) if k > 1 else 0.0
        if std > 1e-8:
            adv = adv / (std + 1e-8)
    loss = -(lp * adv).mean()
    if entropy is not None and MAW_ENTROPY_COEF > 0:
        loss = loss - MAW_ENTROPY_COEF * entropy   # maximize entropy => resist collapse
    optimizer.zero_grad()
    loss.backward()
    if sign:                                          # signSGD: quantize gradient to its sign
        for group in optimizer.param_groups:
            for p in group['params']:
                if p.grad is not None:
                    p.grad.sign_()
    elif clip and clip > 0:                           # otherwise clip the gradient norm
        for group in optimizer.param_groups:
            params = [p for p in group['params'] if p.grad is not None]
            if params:
                torch.nn.utils.clip_grad_norm_(params, clip)
    optimizer.step()
    return float(loss.detach())


def apply_directive(action_probs, directive, strength: float = MAW_DIRECTIVE_STRENGTH):
    """Tilt a soldier's action distribution by the colony directive (the 85% tier's output).

    IDENTITY at directive==0.5 on every dim — the neutral value the untrained policy centers on
    (or the genome instinct, post warm-start) — so turning the maw on does not jolt behaviour
    until it has learned. The 7 actions are 0-5 move [+x,-x,+y,-y,+z,-z] and 6 attack. Levers:
      d0 aggression  -> ATTACK (idx 6)
      d1 mobility    -> all MOVE actions (idx 0-5)
      d2 verticality -> the VERTICAL moves (idx 4,5 = +z,-z) vs planar (tunnel-down vs hold-surface)
    Each factor is exp(strength*2*(d-0.5)) (==1 at 0.5); bounded and reversible; renormalized.
    action_probs: (7,) or (B,7); directive: (>=1,)."""
    probs = action_probs.clone()
    d = directive.reshape(-1)
    f_attack = torch.exp(strength * 2.0 * (d[0] - 0.5))                    # d0 aggression -> attack
    f_move = torch.exp(strength * 2.0 * (d[1] - 0.5)) if d.numel() > 1 else torch.ones(())
    f_vert = torch.exp(strength * 2.0 * (d[2] - 0.5)) if d.numel() > 2 else torch.ones(())
    if probs.dim() == 1:
        probs[6] = probs[6] * f_attack
        probs[:6] = probs[:6] * f_move
        probs[4:6] = probs[4:6] * f_vert                                  # +z,-z vertical moves
        return probs / probs.sum()
    probs[:, 6] = probs[:, 6] * f_attack
    probs[:, :6] = probs[:, :6] * f_move
    probs[:, 4:6] = probs[:, 4:6] * f_vert
    return probs / probs.sum(-1, keepdim=True)


class MawPolicy(nn.Module):
    """Gaussian policy head: obs -> directive in (0,1)^D, trained by REINFORCE.

    The pre-squash mean comes from a small MLP; a learned per-dim log_std sets exploration.
    Actions are sampled in raw space and squashed by sigmoid so the directive is bounded;
    log_prob is taken in raw space (the policy-gradient signal).

    Warm-start ("never tabula rasa"): if `warm_start` (a directive in (0,1)^D) is given, the
    final layer is zero-weights + bias=logit(warm_start), so the untrained deterministic
    directive equals warm_start regardless of obs — the colony expresses its genome instinct
    from step 1, and the policy learns to modulate around it (the zero final weights still
    receive a nonzero gradient through the obs, so learning proceeds normally).
    """

    def __init__(self, obs_dim: int, directive_dim: int = MAW_DIRECTIVE_DIM,
                 hidden: int = MAW_HIDDEN, warm_start: torch.Tensor = None):
        super().__init__()
        self.obs_dim = int(obs_dim)
        self.directive_dim = int(directive_dim)
        self.net = nn.Sequential(
            nn.Linear(self.obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, self.directive_dim),
        )
        if warm_start is not None:
            ws = torch.as_tensor(warm_start, dtype=torch.float32).reshape(-1)[:self.directive_dim]
            ws = ws.clamp(0.05, 0.95)                       # keep logit finite
            with torch.no_grad():
                nn.init.zeros_(self.net[-1].weight)         # directive starts obs-independent...
                self.net[-1].bias.copy_(torch.log(ws / (1.0 - ws)))   # ...= logit(instinct)
        self.log_std = nn.Parameter(torch.full((self.directive_dim,),
                                               float(MAW_LOG_STD_INIT)))

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        """Pre-squash mean of the policy. obs: (obs_dim,) or (B,obs_dim)."""
        return self.net(obs)

    def entropy(self) -> torch.Tensor:
        """Grad-carrying scalar entropy of the policy (for the anti-collapse bonus)."""
        return _gaussian_entropy(self.log_std)

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        """Sample a directive. Returns (directive in (0,1)^D, log_prob scalar tensor).

        deterministic=True returns sigmoid(mean) and a zero log_prob, drawing NO noise
        (used for eval and for identity-at-neutral behaviour).
        """
        mean = self.net(obs)
        if deterministic:
            return torch.sigmoid(mean), torch.zeros((), device=mean.device)
        std = torch.exp(self.log_std)
        dist = torch.distributions.Normal(mean, std)
        raw = dist.sample()                       # detached action (REINFORCE, not reparam)
        log_prob = dist.log_prob(raw).sum(-1)     # grad flows through the policy params
        directive = torch.sigmoid(raw)
        return directive, log_prob

    def update(self, log_probs, rewards, optimizer: torch.optim.Optimizer) -> float:
        """One batch-REINFORCE step over a batch of episodes (each = one maw directive and its
        reward), with the RLOO leave-one-out baseline (S&B §13.4) and the entropy bonus.

        The leave-one-out baseline gives every episode an unbiased relative signal, so learning
        does not freeze the way a single-sample EMA baseline does once reward stabilizes; the
        entropy term keeps exploration alive. In the sim, a "batch" is K accumulated
        batch-cycles flushed together.

        log_probs: iterable of per-episode log_prob tensors (with grad).
        rewards:   iterable of per-episode scalar rewards.
        Returns the loss value.
        """
        return _reinforce_update(log_probs, rewards, optimizer, entropy=self.entropy())

    def make_optimizer(self, lr: float = MAW_LR) -> torch.optim.Optimizer:
        return torch.optim.Adam(self.parameters(), lr=lr)


class ColonyMawRL:
    """Per-colony wrapper around MawPolicy: the two-timescale bookkeeping.

    Each batch-cycle the sim calls `observe_reward(r)` (the reward realized since the LAST
    directive) then `act(obs)` (emit a new directive). Pairs (log_prob_t, reward_t) accumulate
    in a rollout buffer that flushes a batch-REINFORCE update every `update_every` cycles.
    Pickle-safe (MawPolicy + Adam + plain lists), so it rides the whole-sim checkpoint; pending
    grad tensors are dropped on pickling via __getstate__.

    v2: `warm_start` seeds the policy to the colony's genome instinct ("never tabula rasa");
    `lr` is set from the evolved `plasticity` gene by the caller (the Baldwin effect)."""

    def __init__(self, obs_dim: int, update_every: int = MAW_UPDATE_EVERY,
                 directive_dim: int = MAW_DIRECTIVE_DIM, warm_start: torch.Tensor = None,
                 lr: float = MAW_LR, gamma: float = None):
        self.policy = MawPolicy(obs_dim=obs_dim, directive_dim=directive_dim,
                                warm_start=warm_start)
        self.opt = self.policy.make_optimizer(lr=lr)
        self.update_every = int(update_every)
        self.gamma = float(gamma) if gamma is not None else patience_to_gamma(0.5)
        self._log_probs = []          # per-episode log_prob tensors (grad) — transient
        self._rewards = []            # per-episode scalar rewards
        self._pending_lp = None       # log_prob of the action awaiting its reward
        self.last_directive = None    # detached directive tensor (spawn read this)
        self.last_loss = None
        self.updates = 0
        self._mem = []                # (obs, directive, reward) elite-replay memories (ring buffer)
        self._pending_mem = None      # (obs, directive) awaiting its reward
        self.dreams = 0
        self.last_dream_loss = None

    def act(self, obs: torch.Tensor) -> torch.Tensor:
        """Emit a directive for this cycle; remember its log_prob (for the next reward) and the
        (obs, directive) pair (for Chill-season dreaming)."""
        directive, log_prob = self.policy.act(obs)
        self._pending_lp = log_prob
        self.last_directive = directive.detach()
        self._pending_mem = (obs.detach().clone(), self.last_directive.clone())
        return self.last_directive

    def observe_reward(self, reward: float) -> None:
        """Book the reward for the previous directive; bank the memory; flush an update every K cycles."""
        if self._pending_lp is None:
            return                    # first cycle: nothing acted yet
        self._log_probs.append(self._pending_lp)
        self._rewards.append(float(reward))
        self._pending_lp = None
        if self._pending_mem is not None:                 # bank the memory for dreaming
            o, d = self._pending_mem
            self._mem.append((o, d, float(reward)))
            if len(self._mem) > MAW_DREAM_BUFFER:
                self._mem.pop(0)
            self._pending_mem = None
        if len(self._rewards) >= self.update_every:
            # credit each directive by its γ-discounted downstream return (patience temperament),
            # then RLOO-baseline the returns in policy.update.
            returns = _discounted_returns(self._rewards, self.gamma)
            self.last_loss = self.policy.update(self._log_probs, returns, self.opt)
            self._log_probs, self._rewards = [], []
            self.updates += 1

    def dream(self) -> float:
        """Chill-season offline consolidation (Lin 1992 / INSPIRATIONS S4). ELITE SELF-DISTILLATION:
        replay the highest-reward (obs -> directive) memories and supervised-imitate them — behavior
        cloning on the policy MEAN only (log_std untouched, so exploration survives). This is
        distillation toward the colony's OWN best past, not stale on-policy replay: chess-deep-q found
        distillation > self-play, and it also pulls the policy back toward its successful region (a soft
        anti-erosion consolidation). No-op until MAW_DREAM_TOPK memories exist. Returns the BC loss."""
        if not MAW_DREAM_ENABLED or len(self._mem) < MAW_DREAM_TOPK:
            return None
        # BC mutates the policy weights inplace; any pending on-policy PG log_probs were sampled under
        # the PRE-dream weights, so their autograd graph is now stale (and the actions off-policy). Drop
        # the partial PG batch before dreaming (mirrors the spawn stale-pending fix) — a few seasonal-
        # boundary cycles of PG data is negligible, and mixing a weight mutation into a live batch is a bug.
        self._log_probs, self._rewards = [], []
        self._pending_lp = None
        elites = sorted(self._mem, key=lambda m: m[2], reverse=True)[:MAW_DREAM_TOPK]
        obs = torch.stack([m[0] for m in elites])
        tgt = torch.stack([m[1] for m in elites])
        dopt = torch.optim.Adam(self.policy.net.parameters(), lr=MAW_DREAM_LR)
        loss_v = None
        for _ in range(MAW_DREAM_EPOCHS):
            pred = torch.sigmoid(self.policy.net(obs))
            loss = torch.mean((pred - tgt) ** 2)
            dopt.zero_grad(); loss.backward(); dopt.step()
            loss_v = float(loss.detach())
        self.dreams += 1
        self.last_dream_loss = loss_v
        return loss_v

    def __getstate__(self):
        # Drop transient grad-carrying tensors so the checkpoint pickles cleanly.
        s = self.__dict__.copy()
        s["_log_probs"] = []
        s["_rewards"] = []
        s["_pending_lp"] = None
        s["_pending_mem"] = None
        return s


def apply_residual(action_probs, residual):
    """Add a spawn's bounded residual to the action LOGITS and renormalize. IDENTITY when
    residual == 0 (the zero-init deterministic value). action_probs: (7,) or (B,7);
    residual: same shape, each entry in ±MAW_RESIDUAL_CLIP."""
    logits = torch.log(action_probs.clamp_min(1e-8)) + residual
    return torch.softmax(logits, dim=-1)


class SpawnResidualPolicy(nn.Module):
    """The 15% tier: a SHARED (per-colony) spawn residual policy — a small Gaussian policy
    mapping a spawn's frozen encoding -> a BOUNDED additive action-logit residual (±clip,
    the "play"). Each spawn reacts to its own local state on top of the maw's directive.

    Shared weights => batchable (distinction lives in the per-spawn encoding, NOT in weights),
    consistent with the design rule. Trained by batch-REINFORCE on each spawn's LOCAL
    performance (SoldierLayer.get_performance_score). The last layer inits to zero so the
    deterministic residual starts at exactly identity — turning the 15% on does not jolt
    behaviour until it has learned.
    """

    def __init__(self, enc_dim: int = 32, action_dim: int = 7, hidden: int = MAW_HIDDEN,
                 clip: float = MAW_RESIDUAL_CLIP):
        super().__init__()
        self.action_dim = int(action_dim)
        self.clip = float(clip)
        self.net = nn.Sequential(
            nn.Linear(int(enc_dim), hidden), nn.Tanh(),
            nn.Linear(hidden, self.action_dim),
        )
        nn.init.zeros_(self.net[-1].weight)          # residual starts at 0 -> identity
        nn.init.zeros_(self.net[-1].bias)
        self.log_std = nn.Parameter(torch.full((self.action_dim,), -1.0))

    def entropy(self) -> torch.Tensor:
        """Grad-carrying scalar entropy (anti-collapse bonus; keeps the spawn 'play' alive)."""
        return _gaussian_entropy(self.log_std)

    def act(self, enc: torch.Tensor, deterministic: bool = False):
        """Return (residual in ±clip, log_prob). deterministic => tanh(mean)*clip, 0 log_prob."""
        mean = self.net(enc)
        if deterministic:
            return torch.tanh(mean) * self.clip, torch.zeros((), device=mean.device)
        std = torch.exp(self.log_std)
        dist = torch.distributions.Normal(mean, std)
        raw = dist.sample()
        log_prob = dist.log_prob(raw).sum(-1)
        return torch.tanh(raw) * self.clip, log_prob    # tanh -> bounded to ±clip

    def update(self, log_probs, rewards, optimizer) -> float:
        return _reinforce_update(log_probs, rewards, optimizer, entropy=self.entropy())

    def make_optimizer(self, lr: float = MAW_LR) -> torch.optim.Optimizer:
        return torch.optim.Adam(self.parameters(), lr=lr)


class ColonySpawnRL:
    """Per-colony wrapper for the SHARED spawn residual (15%). Applies a bounded residual to
    each spawn's action, books each spawn's LOCAL performance delta as its reward, and flushes
    a batch-REINFORCE update every SPAWN_UPDATE_EVERY accumulated spawn-steps. One shared
    policy for the whole colony (batchable; spawn individuated by their encoding). Pickle-safe
    (transient grad tensors dropped in __getstate__)."""

    def __init__(self, enc_dim: int = 32, update_every: int = SPAWN_UPDATE_EVERY):
        self.policy = SpawnResidualPolicy(enc_dim=enc_dim)
        self.opt = self.policy.make_optimizer()
        self.update_every = int(update_every)
        self._log_probs = []
        self._rewards = []
        self._pending = {}          # id(unit) -> (log_prob, perf_snapshot) awaiting its reward
        self.updates = 0
        self.last_loss = None

    def act(self, unit, enc, perf: float):
        """Return a bounded residual for this spawn; book the PREVIOUS action's reward
        (this spawn's local performance delta since it last acted)."""
        residual, log_prob = self.policy.act(enc)
        prev = self._pending.get(id(unit))
        if prev is not None:
            plp, pperf = prev
            self._log_probs.append(plp)
            self._rewards.append(float(perf) - float(pperf))
        self._pending[id(unit)] = (log_prob, float(perf))
        if len(self._rewards) >= self.update_every:
            self.last_loss = self.policy.update(self._log_probs, self._rewards, self.opt)
            self._log_probs, self._rewards = [], []
            self._pending = {}          # drop stale pending log_probs (params just stepped)
            self.updates += 1
        return residual

    def __getstate__(self):
        s = self.__dict__.copy()
        s["_log_probs"] = []
        s["_rewards"] = []
        s["_pending"] = {}
        return s
