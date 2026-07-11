"""Targeted playtest: does tech-LICENSING emerge when one colony monopolizes a
keeper foreign gift? (The user's "weak civ rents the calculator" scenario.)"""
import random
import numpy as np

random.seed(11)
np.random.seed(11)

import sandkings as sk
from sandkings import SandKingsSimulation, TECH_FOREIGN

sk.BARGAIN_ENABLED = True
sk.WAGE_ENABLED = True
sk.CAPTURE_CHANCE = sk.BARGAIN_CAPTURE_CHANCE

sim = SandKingsSimulation(width=80, height=48, depth=16, num_colonies=4)
sim.bargain_enabled = True
sim.keeper_auto = True

# Monopolist: colony 0 HOLDS the calculator (a scarce, high-value keeper gift).
monopolist = sim.colonies[0]
monopolist.techs = set(getattr(monopolist, 'techs', set())) | {'calculator'}

license_ever = 0
license_pairs = set()
max_license_live = 0

for step in range(2500):
    sim.step()
    contracts = sim._wage_contracts() if hasattr(sim, '_wage_contracts') else []
    live_lic = [c for c in contracts if c.get('alive') and c['kind'] == 'license']
    max_license_live = max(max_license_live, len(live_lic))
    for c in live_lic:
        license_ever += 0  # counted via pairs below
        license_pairs.add((c['seller_id'], c['buyer_id'], c['factor']))
    if step % 500 == 0:
        holders = {c.colony_id: sorted(t for t in getattr(c, 'techs', set()) if t in TECH_FOREIGN)
                   for c in sim.colonies if c.is_alive()
                   and any(t in TECH_FOREIGN for t in getattr(c, 'techs', set()))}
        lic = [(c['seller_id'], c['buyer_id'], c['factor'], round(c['fee'], 1)) for c in live_lic]
        print(f"[{step:5d}] gift_holders={holders} live_licenses={lic}")

print("---- LICENSE SUMMARY ----")
print(f"max live license contracts at once = {max_license_live}")
print(f"distinct license (seller->buyer, gift) seen = {sorted(license_pairs)}")
# did anyone RENT calculator from the monopolist and pay for it?
print(f"monopolist(colony 0) still holds calculator: "
      f"{'calculator' in getattr(sim.colonies[0], 'techs', set())}")
alive = [c for c in sim.colonies if c.is_alive()]
print(f"grains: {[(c.colony_id, round(getattr(c,'currency',0.0),1)) for c in alive]}")
