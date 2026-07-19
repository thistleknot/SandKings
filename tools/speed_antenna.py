"""Profile the antenna's compute cost — the SPEC_SKIRMISH_COMBAT gate I never ran: ms/step, antenna OFF vs ON.

OFF = the I1 position-index combat (already O(U), no antenna). ON = adds the per-pair antenna decision + friendly
fire + culling. Same world shape/seed each arm (ON diverges the RNG, so this is a cost comparison of two runs, not a
paired diff). Reports mean ms/step over a timed window after warmup. CPU only.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np
import sandkings as sk

WARM, TIMED = 40, 80


def run(antenna_on, seed):
    sk.SKIRMISH_ANTENNA_ENABLED = bool(antenna_on)
    np.random.seed(seed)
    import random as _r; _r.seed(seed)
    sim = sk.SandKingsSimulation(width=30, height=30, depth=20, num_colonies=5, dynamic_population=True)
    if sk.NEURAL_AVAILABLE:
        for c in sim.colonies:
            c.genome.use_neural = True
            if c.genome.brain is None:
                c.genome.brain = sk.HiveMindBrain()
    for _ in range(WARM):
        sim.step()
    t0 = time.time()
    for _ in range(TIMED):
        sim.step()
    dt = (time.time() - t0) / TIMED * 1000.0
    pop = sum(len(c.units) for c in sim.colonies)
    return dt, pop


SEEDS = [11, 23, 42, 77, 101]
offs, ons = [], []
for s in SEEDS:
    o, op = run(False, s); n, npp = run(True, s)
    offs.append(o); ons.append(n)
    print(f"seed {s:3d}: OFF {o:6.1f}  ON {n:6.1f} ms/step   ({100*(n-o)/o:+.0f}%)  pops {op}/{npp}")
off_ms, on_ms = float(np.mean(offs)), float(np.mean(ons))
print(f"\nMEAN over {len(SEEDS)} seeds: OFF {off_ms:.1f}  ON {on_ms:.1f} ms/step")
d = on_ms - off_ms
print(f"antenna delta {d:+.1f} ms/step  ({100*d/off_ms:+.0f}%)")
print("NOTE: OFF already includes the I1 O(U) position-index (the algorithmic win over the old O(26*U^2) scan). "
      "This delta is the antenna's ADDED cost on top of that — the intelligence is not free; the efficiency came "
      "from I1, the antenna spends some of it back for learned kin-recognition. Different pops confound it somewhat.")
