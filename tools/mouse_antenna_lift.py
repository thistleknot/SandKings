"""MOUSE — SPEC_LONGEVITY_FITNESS L1: the antenna's SURVIVAL LIFT, in isolation (no game).

The L1 question (keeper, 2026-07-19/20): does a well-CALIBRATED antenna actually EXTEND survival — and by how
much versus a DEFECTIVE (mis-inherited) band and versus the OMNISCIENT ceiling the old hostile() gave for free?
This is the feature-lift measurement that must precede any fitness rewrite: if the antenna can't show survival
lift over a defective band, it isn't earning its compute.

Mouse-model discipline ([[mouse-model-testing]]): the FULL GAME is never the test loop. This harness instantiates
ONLY the real antenna component — the same encode / genetic-prior / Boltzmann-decide logic as
`sandkings.py::_antenna_decide` (constants mirrored below) — and runs units through a controlled stream of lethal
friend/foe encounters. It does NOT construct SandKingsSimulation.

Survival model (the scale-INVARIANT quantity, independent of game cadence):
  - Each encounter is a true-foe or kin/ally (50/50). Correct call = survive; wrong call = a LETHAL event:
      * a foe you DON'T strike kills you (missed threat), at any age;
      * striking KIN while SETTLED is lethal friendly fire -> the colony CULLS you (I2b). While still calibrating
        (n < ANNEAL) an exploratory mis-fire is NOT yet lethal (a young unit is still finding its band).
  - A unit lives until its first lethal event. Report the FRACTION still alive after a fixed N encounters
    (a survival curve), which translates to macro without depending on steps/sec.

Three arms, so the lift is falsifiable both ways:
  - OMNISCIENT  — perfect friend/foe oracle (the pre-antenna hostile() ceiling): strike iff foe. Upper bound.
  - CALIBRATED  — the real genetic-instinct prior (w=-encode(own), b=1/2||own||^2) + Boltzmann REINFORCE.
  - DEFECTIVE   — an INVERTED instinct (w=+encode(own)): born to strike its own band. The mis-inherited variant
                  that selection/culling exists to purge. Its survival floor is the lift's lower anchor.

LIFT = mean survival(CALIBRATED) - mean survival(DEFECTIVE)  (must be clearly > 0);
COST = mean survival(OMNISCIENT) - mean survival(CALIBRATED)  (the realism price — small = the antenna is cheap).
Reported across >=3 varied conditions (seed x foe-crowding), never one case.
"""
import numpy as np

# --- constants mirrored from sandkings.py (SPEC_SKIRMISH_COMBAT I2) ---
SIGNATURE_PEGS = 8
_PEGS = np.linspace(0.0, 1.0, SIGNATURE_PEGS)
ANTENNA_COMB = 1.0 / (SIGNATURE_PEGS - 1)          # peg spacing (structural, not authored)
ANTENNA_LR = 0.25
ANTENNA_T0 = 2.0
ANTENNA_TMIN = 0.4
ANTENNA_CLASSES = 2
ANTENNA_ANNEAL = float(ANTENNA_CLASSES)            # settle after ~2 engagements (met both classes)
SENSE_NOISE = 0.03

N_COLONIES = 5
SIGS = np.linspace(0.1, 0.9, N_COLONIES)
POP = 400                                          # units per arm (survival is a fraction -> want a smooth curve)
N_ENC = 24                                         # lethal encounters per life (fixed horizon; scale-invariant)


def encode(freq):
    return np.exp(-((float(freq) - _PEGS) ** 2) / (2.0 * ANTENNA_COMB ** 2))


def prior(own_sig, defective=False):
    """Genetic instinct. CALIBRATED: hold own band (w=-encode(own)), nearest-centroid boundary b. DEFECTIVE:
    inverted (w=+encode(own)) -> born striking its own kin, the variant culling purges."""
    own = encode(own_sig)
    b = float(own @ own) * 0.5
    return (own.copy() if defective else -own.copy()), (-b if defective else b)


CALIB = int(ANTENNA_ANNEAL)                          # non-lethal warm-up encounters (young unit still finding its band)


def survives_life(own_sig, foes, arm, rng):
    """Run ONE unit: a NON-LETHAL calibration warm-up (tune the band, matching the game's pre-settle exploration and
    mouse_antenna_cull's PHASE 1), THEN N_ENC lethal DEPLOYED encounters on the settled band. Return the deployed
    encounter index of death (or N_ENC if it survives all). This isolates what the SETTLED band is worth — a young
    unit's exploratory mis-fire is not the feature's fault (it's protected while learning), so calibration deaths must
    not swamp the settled-discrimination signal the lift is measuring.
    `arm` in {'omniscient','calibrated','defective'} selects the discriminator; the antenna arms mirror
    _antenna_decide exactly (encode enemy sig, Boltzmann sample/greedy by settle, REINFORCE update)."""
    if arm != 'omniscient':
        w, b = prior(own_sig, defective=(arm == 'defective'))

    def draw():
        is_foe = rng.random() < 0.5
        base = foes[rng.integers(len(foes))] if is_foe else own_sig
        return is_foe, encode(base + rng.normal() * SENSE_NOISE)

    # PHASE 1 — calibrate (safe): explore hot, tune the band by REINFORCE, no death.
    if arm != 'omniscient':
        for n in range(CALIB):
            is_foe, x = draw()
            T = max(ANTENNA_TMIN, ANTENNA_T0 * (1.0 - n / ANTENNA_ANNEAL))
            p = 1.0 / (1.0 + np.exp(-float(w @ x + b) / T))
            a = 1 if rng.random() < p else 0
            r = ((1.0 if is_foe else -1.0) if a == 1 else (-1.0 if is_foe else 0.5))
            g = (a - p) / T
            w = w + ANTENNA_LR * r * g * x; b = b + ANTENNA_LR * r * g

    # PHASE 2 — deploy (lethal): act on the SETTLED band near-greedily; mis-calls now kill.
    for t in range(N_ENC):
        is_foe, x = draw()
        if arm == 'omniscient':
            strike = is_foe                                   # perfect oracle (the pre-antenna ceiling)
        else:
            p = 1.0 / (1.0 + np.exp(-float(w @ x + b) / ANTENNA_TMIN))
            strike = p > 0.5                                  # settled -> greedy best judgment
        if is_foe and not strike:
            return t                                          # missed a foe -> killed
        if (not is_foe) and strike:
            return t                                          # struck kin on the settled band -> friendly-fire cull
    return N_ENC


def mean_survival(arm, own_sig, foes, seed):
    """Scale-invariant survival = mean ENCOUNTERS-TO-DEATH, normalized to [0,1] by the horizon N_ENC. Chosen over
    fraction-alive-at-N because the latter SATURATES to ~0 for any realistic per-encounter accuracy over a long
    lethal horizon (0.9^24 ~ 0.08), so it cannot separate a good band from a mediocre one; encounters-to-death does."""
    rng = np.random.default_rng(seed)
    deaths = np.array([survives_life(own_sig, foes, arm, rng) for _ in range(POP)])
    return float(np.mean(deaths) / N_ENC)


def run_battery(verbose=True):
    """The permutation battery: >=3 varied conditions (seed x foe-crowding), never one case. Returns (lift, cost)."""
    own = SIGS[2]                                            # 0.5, a central band (worst case: foes on both sides)
    conditions = [
        ("seed A, spread foes",  [s for s in SIGS if s != own],          1),
        ("seed B, spread foes",  [s for s in SIGS if s != own],          7),
        ("seed C, CROWDED foes", [own - 0.06, own + 0.06, own + 0.12],  13),   # near-band foes: the hard case
    ]
    if verbose:
        print("MOUSE — L1 antenna SURVIVAL LIFT (mean encounters-to-death / %d; 3 arms x 3 conditions)\n" % N_ENC)
        print("  %-22s %10s %10s %10s" % ("condition", "OMNISCIENT", "CALIBRATED", "DEFECTIVE"))
    lifts, costs = [], []
    for name, foes, seed in conditions:
        o = mean_survival('omniscient', own, foes, seed)
        c = mean_survival('calibrated', own, foes, seed)
        d = mean_survival('defective',  own, foes, seed)
        lifts.append(c - d); costs.append(o - c)
        if verbose:
            print("  %-22s %9.2f  %9.2f  %9.2f   (lift %+.2f, cost %+.2f)" % (name, o, c, d, c - d, o - c))
    lift = float(np.mean(lifts)); cost = float(np.mean(costs))
    if verbose:
        print("\n  mean LIFT (calibrated - defective) = %+.2f   mean COST (omniscient - calibrated) = %+.2f"
              % (lift, cost))
    return lift, cost, lifts


if __name__ == "__main__":
    lift, cost, lifts = run_battery(verbose=True)
    ok = lift > 0.15 and all(l > 0 for l in lifts)
    print("\nVERDICT: " + (
        "the calibrated antenna EXTENDS survival (mean encounters-to-death) over a defective band in EVERY "
        "condition (lift > 0 all 3, mean %+.2f), at a realism cost %+.2f below the omniscient ceiling. The feature "
        "earns its compute -> L1 passes; proceed to L2 (per-unit survival eligibility trace)." % (lift, cost)
        if ok else
        "lift is not robustly positive across conditions -> the antenna does not clear the survival bar as-is; "
        "revisit prior strength / anneal / cull rule before L2."))
