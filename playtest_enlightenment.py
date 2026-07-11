"""Quick confirmation: force one colony to break out and watch it ascend and
pull ahead (tech, brain ceiling, composite power) vs its un-escaped rivals."""
import random
import numpy as np

random.seed(3)
np.random.seed(3)

import sandkings as sk
from sandkings import SandKingsSimulation, TECH_FOREIGN, composite_power

sim = SandKingsSimulation(width=80, height=48, depth=16, num_colonies=4)
sim.keeper_auto = True

# Break out colony 0 immediately (the pi terminal-mastery event).
enl = sim.colonies[0]
sim._escape(enl)
ascend = [e for e in sim.events if "ascends" in str(e).lower()]
print(f"ascend event fired: {bool(ascend)}  -> {ascend[-1] if ascend else None}")
print(f"colony0 enlightened={getattr(enl,'enlightened',False)} "
      f"brain_ceiling={enl.genome.brain_ceiling}")


def line(step):
    row = []
    for c in sim.colonies:
        if not c.is_alive():
            row.append(f"c{c.colony_id}:dead")
            continue
        ntech = len(getattr(c, 'techs', set()))
        row.append(f"c{c.colony_id}{'*' if getattr(c,'enlightened',False) else ' '}:"
                   f"tech={ntech} pow={int(composite_power(c))}")
    print(f"[{step:5d}] " + "  ".join(row))


for step in range(2000):
    sim.step()
    if step % 400 == 0:
        line(step)
line(2000)
print("(* = enlightened)")
