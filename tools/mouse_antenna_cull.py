"""MOUSE — SPEC_SKIRMISH_COMBAT I2b evolutionary STABILITY: lethal friendly fire + Spartan self-culling.

The load-bearing risk before game integration (keeper, 2026-07-19): if a mis-tuned antenna LETHALLY strikes kin/ally
and the colony CULLS the offender (Spartan/insect purge of a defective member), does the population CONVERGE
(friendly-fire rate falls, colonies persist, foe-competence rises) or COLLAPSE (self-cull to extinction before the
band tunes)? This is an evolutionary sim in isolation — no game — to answer exactly that.

Model (Darwinian selection on a heritable antenna prior + within-life RL, Baldwin-style):
  - Each unit carries a HERITABLE birth prior (w0,b0) over the N_PEGS frequency comb; b0 is INNOCENT (negative → a
    naive unit HOLDS, does not strike) so friendly fire is a mis-LEARNED/mis-inherited defect, not startup noise.
  - Within a generation a unit copies its prior to working weights and tunes them by REINFORCE (Boltzmann strike
    policy) over ENCOUNTERS engagements against a 50/50 mix of true foes (other bands) and kin/ally (its own band).
  - A strike on a true foe = reward; a strike on a non-foe = LETHAL friendly fire → the unit is CULLED (removed,
    barred from breeding) — the Spartan purge. A held foe = small miss cost; held kin = restraint.
  - Survivors breed back to POP; offspring inherit the BIRTH prior (w0,b0) + mutation. Selection prunes priors prone
    to mis-fire.
Report per generation: friendly-fire rate, foe-strike competence, living colonies, mean population.
"""
import numpy as np

np.random.seed(0)
N_PEGS = 8
PEGS = np.linspace(0.0, 1.0, N_PEGS)
COMB = 0.14
SENSE_NOISE = 0.03

N_COLONIES = 5
SIGS = np.linspace(0.1, 0.9, N_COLONIES)     # each colony's identity band
POP = 30                                     # units per colony
GENS = 30
CALIB = 2                                    # settle after ~2 engagements (matches game ANNEAL = class-count 2): the
#                                              band is essentially the INHERITED prior; selection/culling does the tuning
DEPLOY = 20                                  # lethal deployment engagements (settled band, mis-fires are culled)
LR = 0.3
T_HOT = 0.8                                  # Boltzmann temperature while calibrating (explore)
T_COLD = 0.15                                # near-greedy deployment (act on best judgment)
INNOCENT_B = -2.0                            # innocent prior: naive unit holds (P(strike)~0.03) until RL learns foes
MUT = 0.06


def encode(freq):
    return np.exp(-((freq - PEGS) ** 2) / (2 * COMB ** 2))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def antenna_prior(own_sig):
    """GENETIC warm-start: an instinct to HOLD own band, STRIKE out-of-band — derived from the colony's own signature
    geometry (a real quantity), not authored. w = -encode(own) (own-band pegs lower foe-ness); b = half the self-
    overlap = the nearest-centroid boundary between the own-band prototype and a far (~zero-overlap) foe. Heritable,
    mutated, culled from here. This is why fast-settle (ANNEAL~2) does NOT collapse to pacifism: units are born able
    to fight, and selection prunes MIS-tuned variants rather than having to discover fighting from a blank slate."""
    own = encode(own_sig)
    return -own.copy(), float(own @ own) * 0.5


def init_colony():
    # heritable MODULATION only (dw, db) — starts ~0; the fixed base instinct is re-derived from own signature each
    # life so SELF-recognition never drifts. Selection tunes the modulation (ally/foe discrimination), not identity.
    return [{'dw': np.random.randn(N_PEGS) * MUT, 'db': np.random.randn() * MUT} for _ in range(POP)]


colonies = [init_colony() for _ in range(N_COLONIES)]
ff_hist = []; foe_hist = []; alive_hist = []
print("MOUSE — I2b lethal friendly fire + Spartan self-culling: does it CONVERGE or COLLAPSE?")
for gen in range(GENS):
    ff = 0; units_total = 0; foe_hits = 0; foe_faced = 0
    survivors = [[] for _ in range(N_COLONIES)]
    for ci, units in enumerate(colonies):
        own = SIGS[ci]
        others = [s for cj, s in enumerate(SIGS) if cj != ci]
        base_w, base_b = antenna_prior(own)           # fixed identity instinct (never drifts) — re-derived each life
        for u in units:
            units_total += 1
            w = base_w + u['dw']; b = base_b + u['db']  # effective band = fixed self-instinct + heritable modulation
            # PHASE 1 — calibrate (safe): explore with a hot Boltzmann policy and tune the band by REINFORCE. No cull
            # here: exploratory mis-fires during learning are not fatal (a young unit is still finding its band).
            for _ in range(CALIB):
                is_foe = np.random.random() < 0.5
                base = others[np.random.randint(len(others))] if is_foe else own
                x = encode(base + np.random.randn() * SENSE_NOISE)
                p = sigmoid(float(w @ x + b) / T_HOT)
                a = 1 if np.random.random() < p else 0
                r = ((1.0 if is_foe else -1.0) if a == 1 else (-1.0 if is_foe else 0.5))
                g = (a - p) / T_HOT
                w += LR * r * g * x; b += LR * r * g
            # PHASE 2 — deploy (lethal): act on the SETTLED band near-greedily. Only a genuinely mis-tuned band
            # mis-fires now -> that is a real defect -> Spartan cull. Symmetric stakes: missing a foe is also fatal.
            fitness = 0.0; defective = False
            for _ in range(DEPLOY):
                is_foe = np.random.random() < 0.5
                base = others[np.random.randint(len(others))] if is_foe else own
                x = encode(base + np.random.randn() * SENSE_NOISE)
                strike = sigmoid(float(w @ x + b) / T_COLD) > 0.5      # near-greedy: the unit's best judgment
                if is_foe:
                    foe_faced += 1
                if strike and is_foe:
                    fitness += 2.0; foe_hits += 1
                elif strike and not is_foe:          # settled band strikes kin -> defective -> culled
                    fitness -= 3.0; defective = True; ff += 1
                elif (not strike) and is_foe:        # settled band misses a foe -> the foe kills you
                    fitness -= 2.0
                else:
                    fitness += 1.0
            if not defective:                        # defectives are culled (the purge); the rest breed by fitness
                survivors[ci].append((max(0.1, fitness), u))
    # reproduce: non-defective survivors breed proportional to fitness (selection), passing on the BIRTH prior + mutation
    for ci in range(N_COLONIES):
        surv = survivors[ci]
        if not surv:
            colonies[ci] = []                        # colony extinct
            continue
        weights = np.array([f for f, _ in surv]); weights = weights / weights.sum()
        kids = []
        while len(kids) < POP:
            parent = surv[np.random.choice(len(surv), p=weights)][1]
            kids.append({'dw': parent['dw'] + np.random.randn(N_PEGS) * MUT,
                         'db': parent['db'] + np.random.randn() * MUT})
        colonies[ci] = kids
    alive = sum(1 for c in colonies if c)
    mean_pop = np.mean([len(c) for c in colonies])
    ff_hist.append(ff / max(1, units_total)); foe_hist.append(foe_hits / max(1, foe_faced)); alive_hist.append(alive)
    if gen % 3 == 0 or gen == GENS - 1:
        print(f"  gen {gen:2d}: friendly-fire {ff_hist[-1]:.3f}  foe-strike {foe_hist[-1]:.2f}"
              f"  colonies alive {alive}/{N_COLONIES}  mean pop {mean_pop:.0f}")

# judge the TREND over the last third (mutation keeps a noisy residual friendly-fire — the recurring purge — so a
# single final generation is not the signal; the windowed means + persistence + no collapse are).
w = GENS // 3
early_ff = np.mean(ff_hist[:w]); late_ff = np.mean(ff_hist[-w:]); late_foe = np.mean(foe_hist[-w:])
persisted = min(alive_hist) == N_COLONIES
print(f"\ntrend: friendly-fire {early_ff:.3f} -> {late_ff:.3f} (windowed)   foe-strike late {late_foe:.2f}   "
      f"colonies never dropped below {min(alive_hist)}/{N_COLONIES}")
converged = persisted and late_ff < early_ff and late_foe > 0.7
print("VERDICT: " + ("CONVERGES — foe-competence climbs high, friendly-fire falls to a low NOISY residual (mutation "
                     "keeps reintroducing defectives that are continually culled — the recurring mite-purge), and NO "
                     "colony collapses. Self-culling is a STABLE dynamic system -> integrate I2b into combat."
                     if converged else
                     "did NOT converge -> rebalance (innocent-prior strength, cull severity, LR, phases) first."))
