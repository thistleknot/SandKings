"""MOUSE — SPEC_LONGEVITY_FITNESS L2/L3 architecture: online ACTOR-CRITIC with eligibility traces, per-subspecies
shared actor, two-timescale (slow critic / fast actor), on a pure LONGEVITY objective. In isolation, no game.

Validates the keeper's architecture before any game surgery:
  - SPAWN = ACTOR: a per-SUBSPECIES shared policy pi(a|s) over the linear features (reuse the PEFT readout, not a new
    net). Sharing pools every member's steps into ONE net -> many updates/step (escapes H2 update-starvation) and one
    batched update (cheap).
  - MAW = CRITIC: V(s) = expected longevity return; two-timescale — critic learns SLOW, actor FAST (the genetic-critic
    / local-actor split H2 demanded).
  - AC(λ): the critic TD error delta = r + gamma*V(s') - V(s) IS the actor's advantage; both carry eligibility traces.
  - Objective: survive. reward = +1 per step alive, episode ends on death. Longevity = steps survived.
  - Per-lineage decaying-cumulative-log-lifespan V_lin <- g*V_lin + log(1+lifespan) as the maw fitness (bounded).

Two subspecies have DIFFERENT survival niches, so a shared-per-subspecies (not global) actor is required — the mouse
shows each learns its own niche and lives longer. Compares AC(λ) vs actor-only (frozen zero critic) to show the critic
earns its place. CPU only.
"""
import numpy as np

np.random.seed(0)
ACTIONS = 3                     # 0=forage, 1=fight, 2=flee
FEAT = 3                        # phi(s) = [threat, resource, bias]
GAMMA = 0.9
LAMBDA = 0.8
A_ACTOR = 0.10                  # fast actor
A_CRITIC = 0.02                 # SLOW critic (two-timescale)
HORIZON = 50
EPISODES = 6000


def phi(threat, resource):
    return np.array([threat, resource, 1.0])


def phi_c(s, sub):
    """Critic features INCLUDE the subspecies: the maw is ONE critic but it conditions V on which subspecies it is
    valuing (they have different survival dynamics), so its baseline is unbiased for each."""
    return np.array([s[0], s[1], float(sub), 1.0])


def correct_action(subspecies, threat, resource):
    """Each subspecies' survival niche (state-dependent). Soldier fights threats; worker flees them; both forage when
    lean. A GLOBAL actor cannot serve both — hence per-subspecies sharing."""
    if threat >= 0.5:
        return 1 if subspecies == 0 else 2      # soldier fights, worker flees
    if resource <= 0.5:
        return 0                                # forage when lean
    return 2                                    # otherwise lie low


def step_env(subspecies, s, a):
    """Return (reward, next_state, done). Wrong action for the state sharply raises death probability."""
    threat, resource = s
    p_death = 0.02 if a == correct_action(subspecies, threat, resource) else 0.35
    if np.random.random() < p_death:
        return 1.0, None, True                  # credited the step it survived up to, then dies
    return 1.0, (np.random.random(), np.random.random()), False


def softmax(z):
    z = z - z.max(); e = np.exp(z); return e / e.sum()


def train(use_critic):
    """Per-subspecies actor W[sub] (ACTIONS x FEAT) + shared critic w_c (FEAT). Online AC(λ). Returns longevity curve
    per subspecies + the lineage aggregate + param count."""
    W = [np.zeros((ACTIONS, FEAT)) for _ in range(2)]
    w_c = np.zeros(4)                                        # subspecies-conditioned critic (see phi_c)
    V_lin = 0.0
    curve = {0: [], 1: []}
    for ep in range(EPISODES):
        sub = ep % 2                                        # alternate the two subspecies (shared nets accumulate)
        s = (np.random.random(), np.random.random())
        e_a = np.zeros((ACTIONS, FEAT)); e_c = np.zeros(4)
        life = 0
        for _ in range(HORIZON):
            x = phi(*s)
            p = softmax(W[sub] @ x)
            a = np.random.choice(ACTIONS, p=p)
            r, s2, done = step_env(sub, s, a)
            life += 1
            v = w_c @ phi_c(s, sub) if use_critic else 0.0
            v2 = (w_c @ phi_c(s2, sub)) if (use_critic and not done) else 0.0
            delta = r + GAMMA * v2 - v                      # TD error = the actor's advantage
            # critic trace + slow update
            if use_critic:
                e_c = GAMMA * LAMBDA * e_c + phi_c(s, sub)
                w_c += A_CRITIC * delta * e_c
            # actor trace: grad log pi(a|s) = (onehot(a) - p) outer x
            grad = -np.outer(p, x); grad[a] += x
            e_a = GAMMA * LAMBDA * e_a + grad
            W[sub] += A_ACTOR * delta * e_a
            if done:
                break
            s = s2
        V_lin = GAMMA * V_lin + np.log1p(life)              # per-lineage decaying cumulative of log-lifespans
        curve[sub].append(life)
    params = sum(w.size for w in W) + w_c.size
    return curve, V_lin, params


def windowed(xs, w=400):
    return [float(np.mean(xs[i:i + w])) for i in range(0, len(xs) - w, w)]


print("MOUSE — actor-critic(λ) longevity, per-subspecies shared actor, two-timescale (slow critic / fast actor)")
for label, use_c in (("AC(λ) full (maw critic)", True), ("actor-only (no critic baseline)", False)):
    curve, vlin, params = train(use_c)
    c0 = windowed(curve[0]); c1 = windowed(curve[1])
    print(f"\n{label}:  params {params}")
    print(f"  soldier longevity {c0[0]:.1f} -> {c0[-1]:.1f} steps   (learns to fight threats)")
    print(f"  worker  longevity {c1[0]:.1f} -> {c1[-1]:.1f} steps   (learns to flee threats)")
    print(f"  lineage aggregate V_lin (bounded fitness) = {vlin:.2f}")

print("\nVERDICT: if BOTH subspecies' longevity climbs (each learns its own niche via a SHARED per-subspecies actor) "
      "and the critic version climbs higher/faster than actor-only, the architecture holds: reuse the PEFT readout as "
      "a per-subspecies actor, the maw as a slow critic, AC(λ) for online longevity credit. Tiny params, one net/"
      "subspecies (batchable). Then integrate L2 (age-at-death reward) -> L3 (two-tier lineage fitness).")
