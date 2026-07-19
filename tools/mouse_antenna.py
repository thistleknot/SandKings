"""MOUSE — SPEC_SKIRMISH_COMBAT I2 antenna, RL-TUNED band + BOLTZMANN selection, in isolation (no game).

The corrected model (keeper, 2026-07-19): the antenna's discrimination band is NOT a hand-set geometric constant and
the error is NOT a uniform random miss (epsilon-greedy). Instead:
  - The antenna is learned weights w over a fixed N_PEGS quantile-pegged frequency comb -> a scalar logit z (foe-ness).
  - The strike/hold decision is a BOLTZMANN policy: P(strike) = sigmoid(z / T), temperature T annealed hot->cold
    (explore -> exploit). NOT epsilon-greedy.
  - The band is TUNED BY RL: REINFORCE from combat outcomes (struck a true foe = reward; struck kin = penalty; held vs
    a foe = missed-threat penalty; held vs kin = restraint reward). w starts at ZERO -> no innate band -> the
    discrimination must EMERGE from feedback. That is "must calibrate to learn."

This mouse proves the band self-organizes from reward and reports updates-to-competence (scale-invariant), so we can
judge whether in-game combat frequency supplies enough updates (unlike the update-starved maw, combat is frequent).
"""
import numpy as np

np.random.seed(0)
N_PEGS = 8
PEGS = np.linspace(0.0, 1.0, N_PEGS)
COMB_BAND = 0.14                                  # RBF width of the sensing comb (encoding, not the decision boundary)
SENSE_NOISE = 0.03                               # antenna read noise


def encode(freq):
    """Sensed frequency -> soft comb over the fixed pegs (the quantile-pegged linear features)."""
    return np.exp(-((float(freq) - PEGS) ** 2) / (2 * COMB_BAND ** 2))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def rl_antenna(kin_freq, foe_freqs, updates=800, lr=0.25, T0=2.0, Tmin=0.4):
    """Learn the antenna band from combat outcomes via REINFORCE over a Boltzmann strike policy. w starts at ZERO
    (no innate band). Returns (final strike-correctness, updates-to-0.9, learned w)."""
    w = np.zeros(N_PEGS); b = 0.0
    correct = []
    reached = None
    for t in range(updates):
        T = max(Tmin, T0 * (1.0 - t / updates))                     # Boltzmann temperature anneal (explore -> exploit)
        is_foe = np.random.random() < 0.5
        base = foe_freqs[np.random.randint(len(foe_freqs))] if is_foe else kin_freq
        x = encode(base + np.random.randn() * SENSE_NOISE)
        z = float(w @ x + b)
        p = sigmoid(z / T)                                          # BOLTZMANN prob of STRIKE (call foe)
        a = 1 if np.random.random() < p else 0                      # sample the action from the policy
        r = ((1.0 if is_foe else -1.0) if a == 1                    # struck: true foe +1 / kin -1 (friendly fire cost)
             else (-0.5 if is_foe else 0.5))                        # held:  vs foe -0.5 (miss) / vs kin +0.5 (restraint)
        g = (a - p) / T                                            # dlogP(a)/dz  (REINFORCE score)
        w += lr * r * g * x; b += lr * r * g                       # reward-weighted policy-gradient step -> tunes the band
        hit = int((a == 1) == is_foe)
        correct.append(hit)
        if reached is None and len(correct) >= 50 and np.mean(correct[-50:]) >= 0.9:
            reached = t
    return float(np.mean(correct[-100:])), reached, w


freqs = np.linspace(0.1, 0.9, 6)
print("MOUSE — RL-tuned antenna band, Boltzmann strike policy (w starts at ZERO — no innate band)")
accs, tos = [], []
for i, f in enumerate(freqs):
    acc, reached, _ = rl_antenna(f, [g for g in freqs if abs(g - f) > 1e-6])
    accs.append(acc); tos.append(reached)
    print(f"  house {i} (freq {f:.2f}): post-RL strike-correctness {acc:.2f}   updates->0.9: {reached}")
print(f"\nmean post-RL correctness {np.mean(accs):.2f}   median updates->0.9 {np.median([t for t in tos if t]):.0f}")

# ROOM FOR ERROR emerges from RL, not hand-injected: crowd the bands -> the tuned band stays confusable near the edge
acc_c, reached_c, _ = rl_antenna(0.50, [0.53, 0.56])
print(f"crowded bands (0.50 vs 0.53/0.56): post-RL correctness {acc_c:.2f}  (RL cannot fully separate near-band foes)")

# BOLTZMANN vs a fixed policy: temperature controls exploration. Hot T -> near-random; cold T -> sharp.
w_demo = rl_antenna(0.5, [0.1, 0.9])[2]
x_foe = encode(0.1); z = float(w_demo @ x_foe)
for T in (2.0, 0.8, 0.3):
    print(f"  Boltzmann P(strike|clear foe) at T={T}: {sigmoid(z / T):.2f}")

viable = np.mean(accs) > 0.85 and np.median([t for t in tos if t]) < 400
print("\nVERDICT: " + ("the band SELF-ORGANIZES from combat reward (Boltzmann selection, zero innate band) and reaches "
                       "competence in a few hundred updates -> in-game combat frequency (many engagements/game, not "
                       "the maw's ~4 updates) can supply this. Wire RL-tuned per-colony antennae into combat."
                       if viable else "band did not tune from reward fast enough -> revisit lr/temperature/encoding."))
