"""L1 (SPEC_LONGEVITY_FITNESS) — does the ANTENNA add survival value? A headless A/B on spawn lifespan.

The keeper's test: measure a feature in terms of LIFT on survival (how long spawns actually live). This runs the game
headless twice at the same seed/geometry — antenna OFF vs ON — and compares the living population's mean/median age
(`brain_layer.steps_alive`) as the survival proxy, plus population and the antenna's friendly-fire self-cost.

Caveat (honest): the antenna consumes RNG when ON, so the two worlds diverge — this is a DISTRIBUTIONAL comparison of
two populations, not a paired per-unit A/B. It answers "does the antenna-on world sustain longer-lived spawns than the
antenna-off world," which is the population-level lift question. CPU only; never touches the GPU.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np
import sandkings as sk

STEPS = 300


def run(antenna_on):
    sk.SKIRMISH_ANTENNA_ENABLED = bool(antenna_on)
    np.random.seed(7)                                   # same world seed both arms
    import random as _r; _r.seed(7)
    sim = sk.SandKingsSimulation(width=30, height=30, depth=20, num_colonies=5, dynamic_population=True)
    # enable neural like main() does (headless-constructed sims default rule-based -> no brain_layer/steps_alive)
    if sk.NEURAL_AVAILABLE:
        for colony in sim.colonies:
            colony.genome.use_neural = True
            if colony.genome.brain is None:
                colony.genome.brain = sk.HiveMindBrain()
    for _ in range(STEPS):
        sim.step()
    ages = [int(u.brain_layer.steps_alive) for c in sim.colonies for u in c.units
            if getattr(u, 'brain_layer', None) is not None and hasattr(u.brain_layer, 'steps_alive')]
    pop = sum(len(c.units) for c in sim.colonies)
    ff = getattr(sim, '_ff_culls', 0)
    return ages, pop, ff


off_ages, off_pop, _ = run(False)
on_ages, on_pop, on_ff = run(True)


def stat(a):
    return (float(np.mean(a)), float(np.median(a)), len(a)) if a else (0.0, 0.0, 0)


om, omed, on_n = stat(on_ages)
fm, fmed, off_n = stat(off_ages)
print(f"ANTENNA OFF: mean age {fm:.1f}  median {fmed:.1f}  (n={off_n} living, pop {off_pop})")
print(f"ANTENNA ON : mean age {om:.1f}  median {omed:.1f}  (n={on_n} living, pop {on_pop});  ff-culls {on_ff}")
lift = om - fm
print(f"\nSURVIVAL LIFT (mean age on - off): {lift:+.1f} steps  ({100*lift/max(1e-9,fm):+.0f}%)")
print("READ: " + ("the antenna-on world sustains LONGER-LIVED spawns -> the feature adds survival value despite its "
                  "friendly-fire self-cost." if lift > 0 else
                  "no positive survival lift here -> the antenna's friendly-fire cost may be outweighing its "
                  "foe-detection benefit at this scale/seed; probe other seeds + the calibrated-vs-defective contrast "
                  "before judging (one seed is not a verdict)."))
