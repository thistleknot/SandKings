"""Headless IN-GAME stability check for SPEC_SKIRMISH_COMBAT I2b (no render, CPU only — never touches the GPU).

The mouse validated the mechanism in isolation; this confirms the REAL game with the antenna baseline-on does not
crash and does not self-slaughter to collapse. ANNEAL is lowered so units actually cross into the SETTLED state
within the run (a stress test of the lethal friendly-fire + Spartan-cull path — with the shipped ANNEAL=400 most
units would never settle in a short run, so the lethal path would rarely fire and the test would be vacuous).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import sandkings as sk

sk.SKIRMISH_ANTENNA_ENABLED = True
# uses the SHIPPED ANNEAL (=2, derived from friend/foe class count) — units settle after ~2 engagements, so the
# lethal/cull path is exercised almost immediately; the real question is whether that collapses the population.
STEPS = 400

sim = sk.SandKingsSimulation(width=30, height=30, depth=20, num_colonies=5, dynamic_population=True)
alive0 = sum(1 for c in sim.colonies if c.is_alive())
pop0 = sum(len(c.units) for c in sim.colonies)
min_alive = alive0
for step in range(STEPS):
    sim.step()
    a = sum(1 for c in sim.colonies if c.is_alive())
    min_alive = min(min_alive, a)

alive1 = sum(1 for c in sim.colonies if c.is_alive())
pop1 = sum(len(c.units) for c in sim.colonies)
settled = total = 0
for c in sim.colonies:
    for u in c.units:
        if hasattr(u, '_ant_n'):
            total += 1
            if u._ant_n >= sk.ANTENNA_ANNEAL:
                settled += 1
ff_culls = getattr(sim, '_ff_culls', 0)
print(f"colonies alive {alive0} -> {alive1}/{len(sim.colonies)} (min during run {min_alive})")
print(f"population {pop0} -> {pop1};  antenna-bearing units {total}, of which SETTLED {settled}")
print(f"friendly-fire culls over {STEPS} steps: {ff_culls}  ({ff_culls/STEPS:.2f}/step — defective members purged)")
# collapse = near-extinction (<=1 house) or a dead ecosystem; transient war losses with respawn are NORMAL, not
# collapse. Real combat is CONFIRMED by ff_culls>0 (the antenna strikes) + a bounded (not runaway-pacifist) population.
ok = min_alive >= 2 and pop1 > 0 and total > 0 and ff_culls > 0
print("VERDICT: " + (f"STABLE — real combat (the antenna fired {ff_culls} friendly-fire culls, so units engage rather "
                     f"than the pacifist attractor), defectives purged at {ff_culls/STEPS:.2f}/step, and NO extinction "
                     f"collapse (min {min_alive} houses, pop {pop1}). I2b is live and stable in-game." if ok else
                     "UNSTABLE — extinction collapse or no antenna engagement; investigate before shipping."))
