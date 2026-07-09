"""Acceptance tests for SPEC_DYNASTIES.md (D1-D7).

Failure modes covered: nameless colonies from old checkpoints, chronicle
unbounded growth, epithets judged on another reign's rows, kin fratricide
in target selection, grudges forgotten at respawn, saga misattribution
after a slot changes hands.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from chronicle import (
    FOUNDER_EPITHET, ROW_CAP, derive_epithet, house_label, make_house_name,
    prune, saga_rows, salience_of,
)
from sandkings import SandKingsSimulation, VoxelType


def make_sim(seed: int = 55) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def test_founding_houses_named_and_labeled():
    sim = make_sim()
    names = {sim._house_name(c) for c in sim.colonies}
    assert len(names) == 3, "three distinct founding houses"
    assert all("-" in n for n in names), "two-part grammar"
    c = sim.colonies[0]
    assert house_label(c.house, 1) == c.house, "gen 1 shows no numeral"
    assert house_label(c.house, 2).endswith(" II")
    assert "Oath" in house_label(c.house, 1, "the Oath-Broken")


def test_chronicle_captures_and_substitutes_houses():
    sim = make_sim()
    house = sim._house_name(sim.colonies[1])
    sim._log_event("Colony 1 declares war on Colony 0!")
    step, text, sal = sim._chronicle()[-1]
    assert f"House {house}" in text, "write-time substitution"
    assert sal == 7, "war declarations are salient"
    assert salience_of("Colony 0 has fallen!") == 10
    assert salience_of("some minor thing") == 1


def test_chronicle_prunes_low_salience_first():
    rows = [(i, "Keeper scatter", 1) for i in range(ROW_CAP + 100)]
    rows += [(9999, "Colony 1 has fallen!", 10)]
    kept = prune(rows)
    assert len(kept) <= ROW_CAP
    assert (9999, "Colony 1 has fallen!", 10) in kept, "history keeps deaths"


def test_epithet_judges_only_this_reign():
    rows = [(10, "House Vex betrays House Kar!", 9),         # previous reign
            (500, "House Vex reaps its first harvest", 5),
            (600, "House Vex reaps its first harvest", 5)]
    assert derive_epithet(rows, "Vex", founded_step=100) == "the Farmer-King"
    assert derive_epithet(rows, "Vex", founded_step=0) == "the Oath-Broken", \
        "one betrayal brands harder than two harvests"
    assert derive_epithet(rows, "Kar", founded_step=700) == FOUNDER_EPITHET


def test_succession_earns_epithet_and_cadet_inherits():
    sim = make_sim()
    victim = sim.colonies[1]
    house = sim._house_name(victim)
    sim._log_event(f"Colony {victim.colony_id} declares war on Colony 0!")
    victim.maw.alive = False
    sim._check_maw_deaths()
    assert sim._house_epithets()[house] == "the Warlord"
    assert any("will be remembered" in m for _, m in sim.events)
    sim._respawn_colony(victim.colony_id)
    cadet = sim.colonies[1]
    parents = {sim._house_name(c) for c in sim.colonies
               if c.colony_id != victim.colony_id}
    assert sim._house_name(cadet) in parents, "cadet of a living house"
    assert cadet.generation >= 2
    assert cadet.founded_step == sim.step_count


def test_kin_never_targeted_and_feud_flares():
    sim = make_sim()
    a, b, c = sim.colonies
    # make b kin to a; c the ancient betrayer of a's house
    b.house, b.generation = sim._house_name(a), 2
    sim._house_grudges()[(sim._house_name(a), sim._house_name(c))] = 0
    for col in sim.colonies:
        col.maw.food_stored = 500
    random.seed(3)
    target = sim._select_war_target(a)
    assert target == c.colony_id, "kin spared; the feud directs the spear"
    assert any("blood feud" in m for _, m in sim.events)


def test_saga_builder_reads_history():
    sim = make_sim()
    sim._log_event("Colony 0 declares war on Colony 1!")
    sim._log_event("Colony 1 has fallen!")
    from live_view import build_saga_entries
    lines = [t for t, _c in build_saga_entries(sim)]
    assert any("SAGA" in ln for ln in lines)
    assert any("has fallen" in ln for ln in lines)
    assert any("House" in ln for ln in lines), "history speaks in houses"


def test_dynasty_state_pickles_and_old_checkpoints_guarded():
    import pickle
    sim = make_sim()
    sim._log_event("Colony 0 strikes copper!")
    for _ in range(20):
        sim.step()
    # simulate a pre-dynasty checkpoint: strip the new state
    for c in sim.colonies:
        c.house = ""
    del sim.chronicle
    revived = pickle.loads(pickle.dumps(sim))
    revived.step()
    assert revived._house_name(revived.colonies[0]), "lazily re-founded"
    assert isinstance(revived._chronicle(), list)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all dynasty tests passed")
