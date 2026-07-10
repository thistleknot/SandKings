"""Acceptance tests for SPEC_PLAY_KIT.md (PK1-PK6).

The in-process client drives the terrarium through the API only. Failure
modes covered: /api/step not advancing or not clamping, actions not mutating,
`say` not reaching a breached house, summary empty, and scenarios regressing.
No socket is opened (TestClient in-process).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from play_kit import SCENARIOS, Terrarium, dispatch, run_scenario


def test_step_advances_and_clamps():
    t = Terrarium(seed=1)
    assert t.state()["step"] == 0
    t.step(10)
    assert t.state()["step"] == 10, "/api/step advances deterministically"
    st = t.step(9999)  # PK2 clamp: at most 500 per call
    assert st["step"] == 10 + 500, "step is clamped to 500"


def test_actions_mutate_and_disarm_auto():
    t = Terrarium(seed=2)
    t.sim.keeper_auto = True
    t.feed()
    assert t.sim.keeper_auto is False, "a keeper action disarms auto"
    before = len(t.sim._fauna())
    t.release("small_spider")
    assert len(t.sim._fauna()) > before, "a gift spawns beasts"
    t.temp("heat")
    assert getattr(t.sim, "arena_heat_until", 0) > 0, "arena heat set via API"
    t.drought(True)
    assert t.sim.drought is True


def test_say_reaches_a_breached_house():
    t = Terrarium(seed=3)
    t.sim.colonies[0].breached = True
    reply = t.say(0, "let us have peace")
    assert reply["understood"] and reply["heard"] == "ally"
    assert reply["reply"], "the awakened answer"


def test_summary_names_a_house():
    t = Terrarium(seed=4, canon=True)
    s = t.summary()
    assert isinstance(s, str) and "Crimson" in s and "t=0" in s


def test_dispatch_runs_commands():
    t = Terrarium(seed=5)
    out = dispatch(t, "step 12")
    assert "t=12" in out
    r = dispatch(t, "cricket")  # bare species alias releases
    assert "t=12" in r  # summary after action
    assert dispatch(t, "gibberish").startswith("  ? unknown")


def test_core_scenarios_pass():
    for name in ("worship", "dialogue", "metamorphosis"):
        res = run_scenario(name, seed=7)
        assert res.ok, f"{name} scenario failed: {res.transcript}"
    assert set(SCENARIOS) >= {"worship", "cruelty", "metamorphosis",
                              "dialogue", "turning"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all play kit tests passed")
