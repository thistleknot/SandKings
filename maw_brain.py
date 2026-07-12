"""The maw's real-RL policy — the 85% tier of the 85:15 maw/spawn split.

Reframe (2026-07-12, see docs/decisions/2026-07-12-frozen-fm-router-feudal-brain.md
"UPDATE"): NO LLM, NO foundation model. A small **gradient-trained** policy sits on
top of the FROZEN encoder (HiveMindBrain: frozen ZCA+Kanerva buffers) and learns, by
REINFORCE against a survival/dominance reward, to emit a colony-level **directive** —
a vector of continuous "constants" (aggression, expansion, defense, ...) that condition
the spawn (the 15% tier's bounded residual reads it).

This is real deep-RL (gradients + reward), distinct from the evolutionary HiveMindBrain
(which trains under torch.no_grad). The frozen encoder is the "start-intelligent"
baseline; only this thin policy head + the spawn residual learn.

Contract:
  Require   - torch available; obs is a finite (obs_dim,) or (B,obs_dim) float tensor.
  Guarantee - act() returns a directive in (0,1)^directive_dim and a scalar log_prob;
              update() applies exactly one REINFORCE step and returns the loss.
  Maintain  - a running-mean reward baseline for variance reduction.
  Assert    - directive is finite and within (0,1); deterministic act() draws no noise.

Identity-at-neutral: MAW_RL_ENABLED defaults False; the sim never constructs or calls a
policy while the gate is off, so the regression battery stays byte-identical. The policy
is also pickle-safe (plain nn.Module + a float baseline), so it round-trips in the
whole-sim checkpoint.
"""
import torch
import torch.nn as nn

# --- identity-at-neutral gate (flip in the game entrypoint via globals()) ---
MAW_RL_ENABLED = False

# --- hyperparameters ---
MAW_DIRECTIVE_DIM = 6        # colony constants the spawn condition on
MAW_HIDDEN = 32
MAW_LR = 3e-3
MAW_LOG_STD_INIT = -0.5      # exp(-0.5) ~ 0.61 initial exploration std


class MawPolicy(nn.Module):
    """Gaussian policy head: obs -> directive in (0,1)^D, trained by REINFORCE.

    The pre-squash mean comes from a small MLP; a learned per-dim log_std sets
    exploration. Actions are sampled in raw space and squashed by sigmoid so the
    directive is bounded; log_prob is taken in raw space (the policy-gradient signal).
    """

    def __init__(self, obs_dim: int, directive_dim: int = MAW_DIRECTIVE_DIM,
                 hidden: int = MAW_HIDDEN):
        super().__init__()
        self.obs_dim = int(obs_dim)
        self.directive_dim = int(directive_dim)
        self.net = nn.Sequential(
            nn.Linear(self.obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, self.directive_dim),
        )
        self.log_std = nn.Parameter(torch.full((self.directive_dim,),
                                               float(MAW_LOG_STD_INIT)))

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        """Pre-squash mean of the policy. obs: (obs_dim,) or (B,obs_dim)."""
        return self.net(obs)

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
        """One batch-REINFORCE step over a batch of episodes (each = one maw directive
        and its reward), with a **batch-mean baseline** (standardized advantages).

        Subtracting the batch mean gives every episode a relative signal, so learning
        does not freeze the way a single-sample EMA baseline does once reward stabilizes.
        In the sim, a "batch" is K accumulated batch-cycles flushed together.

        log_probs: iterable of per-episode log_prob tensors (with grad).
        rewards:   iterable of per-episode scalar rewards.
        Returns the loss value.
        """
        lp = torch.stack(list(log_probs))
        r = torch.tensor([float(x) for x in rewards], dtype=lp.dtype, device=lp.device)
        adv = r - r.mean()
        std = float(adv.std()) if adv.numel() > 1 else 0.0
        if std > 1e-8:
            adv = adv / (std + 1e-8)                # whiten -> stable step size
        loss = -(lp * adv).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        return float(loss.detach())

    def make_optimizer(self, lr: float = MAW_LR) -> torch.optim.Optimizer:
        return torch.optim.Adam(self.parameters(), lr=lr)
