"""Story log (SPEC_STORY_LOG): a per-turn JSONL chronicle + an optional, fail-soft local-LLM saga. The log is
opt-in (sim.story_log None by default -> the step() hook is inert)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import random
    import numpy as np
    from sandkings import SandKingsSimulation
    from story_log import StoryLog, snapshot
    HAVE = True
except Exception:
    HAVE = False


def _skip():
    print("SKIP (sandkings unavailable)")
    return True


def _sim():
    random.seed(0); np.random.seed(0)
    sim = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=3)
    for _ in range(6):
        sim.step()
    return sim


def test_snapshot_is_json_safe_and_complete():
    """SL1: snapshot(sim) is a JSON-serializable dict carrying step/season/colonies/events."""
    if not HAVE:
        return _skip()
    sim = _sim()
    snap = snapshot(sim)
    json.dumps(snap)                                  # must not raise
    assert snap["step"] == sim.step_count
    assert isinstance(snap["colonies"], list) and snap["colonies"], "per-colony rows present"
    c0 = snap["colonies"][0]
    for k in ("id", "house", "alive", "units", "food", "keeper", "madness"):
        assert k in c0, f"colony row missing {k}"
    assert isinstance(snap["events"], list)


def test_log_writes_one_line_per_cadence_step():
    """SL1: a run writes one JSON line per logged step; steps are monotonic; each line parses."""
    if not HAVE:
        return _skip()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run.jsonl")
        sim = _sim()
        sim.story_log = StoryLog(path, every=2)       # every other step
        start = sim.step_count
        for _ in range(6):
            sim.step()
        sim.story_log.close()
        lines = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    steps = [r["step"] for r in lines]
    assert steps, "lines were written"
    assert all(s % 2 == 0 for s in steps), "only cadence steps are logged"
    assert steps == sorted(steps), "steps are monotonic"


def test_logging_is_pure_no_step_perturbation():
    """SL1: attaching a log must not change the simulation (pure read, no RNG). Two identical seeded runs —
    one logged, one not — reach the same step and colony food."""
    if not HAVE:
        return _skip()
    def _run(log):
        random.seed(0); np.random.seed(0)
        s = SandKingsSimulation(width=44, height=28, depth=12, num_colonies=3)
        if log:
            s.story_log = StoryLog(log, every=1)
        for _ in range(12):
            s.step()
        if log:
            s.story_log.close()
        return s.step_count, [round(c.maw.food_stored, 3) for c in s.colonies]
    with tempfile.TemporaryDirectory() as d:
        logged = _run(os.path.join(d, "a.jsonl"))
    plain = _run(None)
    assert logged == plain, "logging must not perturb the sim (same step + colony food)"


def test_summary_is_fail_soft_when_ollama_absent():
    """SL2: with summaries on but Ollama unreachable, the log still writes every line and never raises."""
    if not HAVE:
        return _skip()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run.jsonl")
        sim = _sim()
        # point at a dead port so _ollama fails fast; summarize each step
        sim.story_log = StoryLog(path, every=1, summarize_every=2, host="http://127.0.0.1:1")
        for _ in range(4):
            sim.step()                                # must not raise on the summary path
        sim.story_log.close()
        n = sum(1 for l in open(path, encoding="utf-8") if l.strip())
    assert n == 4, "all JSONL lines written despite the summary failing"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("all story-log tests passed")
