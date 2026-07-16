"""God's-eye playtest of the inter-colony economy (M1-M4), enabled.

Runs the sim with the --bargain economy ON and logs what actually EMERGES:
mode distribution per pair, contracts by kind, thrall counts (forced vs
contracted), conversions, grain spread, and liveness. This is the empirical
ground for the god review.
"""
import random
import numpy as np

random.seed(7)
np.random.seed(7)

import sandkings as sk
from sandkings import SandKingsSimulation, TECH_FOREIGN

# --bargain equivalent: turn the whole arc on
sk.BARGAIN_ENABLED = True
sk.WAGE_ENABLED = True
sk.CAPTURE_CHANCE = sk.BARGAIN_CAPTURE_CHANCE

sim = SandKingsSimulation(width=80, height=48, depth=16, num_colonies=4)
sim.bargain_enabled = True
sim.keeper_auto = True  # let the god-script feed so colonies don't just starve

STEPS = 3000
SAMPLE = 250

# cumulative counters we can detect
prev_owner = {}   # unit_id -> colony_id, to detect conversions
conversions = 0
captures_seen = 0
max_forced = 0
max_contracted = 0
contract_kinds_ever = set()


def snapshot(step):
    global conversions, captures_seen, max_forced, max_contracted
    alive = [c for c in sim.colonies if c.is_alive()]
    # mode distribution
    modes = sim._bargain_modes() if hasattr(sim, '_bargain_modes') else {}
    mode_counts = {}
    for m in modes.values():
        mode_counts[m] = mode_counts.get(m, 0) + 1
    # contracts
    contracts = sim._wage_contracts() if hasattr(sim, '_wage_contracts') else []
    kinds = {}
    for c in contracts:
        if c.get('alive'):
            kinds[c['kind']] = kinds.get(c['kind'], 0) + 1
            contract_kinds_ever.add(c['kind'])
    # thralls: forced (wage_ratio<=0, laboring_for>=0) vs contracted (wage_ratio>0)
    forced = contracted = 0
    for c in sim.colonies:
        for u in c.units:
            lf = getattr(u, 'laboring_for', -1)
            if lf >= 0:
                if getattr(u, 'wage_ratio', 0.0) > 0.0:
                    contracted += 1
                else:
                    forced += 1
    max_forced = max(max_forced, forced)
    max_contracted = max(max_contracted, contracted)
    # grains spread
    grains = [round(getattr(c, 'currency', 0.0), 1) for c in alive]
    # who holds foreign gifts (monopoly asset)
    gifts = {}
    for c in alive:
        held = sorted(t for t in getattr(c, 'techs', set()) if t in TECH_FOREIGN)
        if held:
            gifts[c.colony_id] = held
    print(f"[{step:5d}] alive={len(alive)} modes={mode_counts} "
          f"contracts={kinds} forced_thralls={forced} contracted={contracted} "
          f"grains={grains} gifts={gifts}")


for step in range(STEPS):
    # detect conversions: a unit whose colony_id changed from a prior sighting
    for c in sim.colonies:
        for u in c.units:
            uid = getattr(u, 'unit_id', None)
            if uid is not None:
                if uid in prev_owner and prev_owner[uid] != c.colony_id:
                    conversions += 1
                prev_owner[uid] = c.colony_id
    sim.step()
    if step % SAMPLE == 0:
        snapshot(step)

snapshot(STEPS)
print("---- SUMMARY ----")
print(f"conversions(unit changed house) ~= {conversions}")
print(f"max forced thralls at once = {max_forced}; max contracted = {max_contracted}")
print(f"contract kinds ever opened = {sorted(contract_kinds_ever)}")
alive = [c for c in sim.colonies if c.is_alive()]
print(f"final alive colonies = {len(alive)}/{len(sim.colonies)}")
# sample recent economy-relevant events
evs = list(getattr(sim, 'events', []))[-16:]
print("recent events:")
for stp, m in evs:
    print(f"  [{stp}] {m}")
