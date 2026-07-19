"""H1 falsifier: does the maw-RL (instinct + learning) beat its own warm-start baseline (instinct frozen, RL off)
on the objective it optimizes — final `snap` fitness = population + food/50 + territory/100 + survival — with the
same seed and every other subsystem identical? Reports the between-condition delta across seeds. Honest: prints
whatever it finds."""
import os, sys, random, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import numpy as np, torch, sandkings
from sandkings import SandKingsSimulation, UnitType
from neural_hive import HiveMindBrain, SoldierLayer

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 1700
SEEDS = [7, 11, 23]

def fitness(sim):
    v = [(len(c.units) + c.maw.food_stored/50.0 + len(getattr(c,'territory',()))/100.0
          + (2.0 if c.maw.alive else 0.0)) for c in sim.colonies]
    return float(np.mean(v)), sum(1 for c in sim.colonies if c.maw.alive), float(np.mean([c.maw.food_stored for c in sim.colonies]))

def run(seed, rl_on):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    sandkings.MAW_RL_ENABLED = rl_on
    sim = SandKingsSimulation(width=48, height=32, depth=12, num_colonies=4)
    for c in sim.colonies:
        c.genome.use_neural = True
        if c.genome.brain is None: c.genome.brain = HiveMindBrain()
        for u in c.units:
            if u.unit_type == UnitType.SOLDIER and getattr(u, 'brain_layer', None) is None:
                u.brain_layer = SoldierLayer(); u.brain_layer.steps_alive = 0
    for _ in range(STEPS): sim.step()
    return fitness(sim)

on_f, off_f = [], []
for s in SEEDS:
    on = run(s, True); off = run(s, False)
    on_f.append(on[0]); off_f.append(off[0])
    print(f"seed {s:2d}: RL-on {on[0]:6.2f} (alive {on[1]}, food {on[2]:5.0f})  RL-off {off[0]:6.2f} (alive {off[1]}, food {off[2]:5.0f})  d {on[0]-off[0]:+.2f}")
d = [o - f for o, f in zip(on_f, off_f)]
print(f"\nMEAN fitness  RL-on {statistics.mean(on_f):.2f}   RL-off {statistics.mean(off_f):.2f}   d {statistics.mean(d):+.2f}")
print(f"per-seed d {[round(x,2) for x in d]}   RL wins {sum(1 for x in d if x>0)}/{len(SEEDS)} seeds   (STEPS={STEPS})")
print("VERDICT: " + ("RL beats warm-start" if statistics.mean(d) > 0 and sum(1 for x in d if x>0) >= 3 else "NOT clearly beating warm-start — H1 unconfirmed"))
