"""Acceptance tests for SPEC_DASHBOARD.md (DB1-DB8).

Uses FastAPI's TestClient (in-process, no real socket). Failure modes
covered: GET mutating the sim, the frame renderer needing pygame,
keeper endpoints not disarming auto, speak crashing on empty colonies,
missing CSP header, and any code-exec/network import sneaking in.
"""

import ast
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from dashboard import (
    GARAGE_SPECIES, TerrariumRunner, build_state, create_app,
    render_frame_png,
)
from sandkings import SandKingsSimulation


def make_sim(seed: int = 12) -> SandKingsSimulation:
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.harsh = True
    return sim


def client_for(sim):
    from fastapi.testclient import TestClient
    runner = TerrariumRunner(sim, sps=6.0)  # not started: no background steps
    return TestClient(create_app(runner)), runner


def test_build_state_is_pure_and_shaped():
    sim = make_sim()
    before = sim.step_count
    state = build_state(sim)
    assert sim.step_count == before, "reading state must not step the sim"
    # DB3: must be JSON-serializable AFTER stepping (numpy scalars creep in)
    import json
    for _ in range(120):
        sim.step()
    json.dumps(build_state(sim))  # raises if a numpy scalar leaked through
    assert {"step", "year", "season", "colonies", "saga",
            "keeper", "world"} <= state.keys()
    assert len(state["colonies"]) == 3
    col = state["colonies"][0]
    assert {"house", "attitude", "pop", "food",
            "breached", "utterance"} <= col.keys()
    assert col["attitude"] in ("none", "reverent", "wrathful")


def test_frame_png_renders_without_pygame():
    assert "pygame" not in sys.modules, "dashboard must import pygame-free"
    png = render_frame_png(make_sim(), scale=320)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "a valid PNG signature"
    assert len(png) > 100


def test_state_endpoint_and_csp_header():
    sim = make_sim()
    for _ in range(120):  # advance so numpy scalars would surface
        sim.step()
    client, _ = client_for(sim)
    r = client.get("/api/state")
    assert r.status_code == 200 and "colonies" in r.json()
    assert "default-src 'self'" in r.headers.get("content-security-policy", "")
    assert client.get("/").status_code == 200  # the console page
    assert client.get("/api/frame.png").headers["content-type"] == "image/png"


def test_keeper_food_mutates_and_disarms_auto():
    sim = make_sim()
    client, runner = client_for(sim)
    assert getattr(sim, "keeper_auto", True) is True
    r = client.post("/api/keeper/food", json={"x": 20, "y": 18})
    assert r.status_code == 200
    assert sim.keeper_auto is False, "the human took the wand"
    assert sim.keeper_manna, "manna was placed"


def test_keeper_release_validates_species():
    sim = make_sim()
    client, _ = client_for(sim)
    for sp in GARAGE_SPECIES:
        n = len(getattr(sim, "fauna", []) or [])
        assert client.post("/api/keeper/release", json={"species": sp}).status_code == 200
        assert len(sim.fauna) > n
    assert client.post("/api/keeper/release",
                       json={"species": "dragon"}).status_code == 400


def test_keeper_drought_gift_cat():
    sim = make_sim()
    client, _ = client_for(sim)
    client.post("/api/keeper/drought", json={"on": True})
    assert sim.drought and sim.dole_factor() == 0.0
    client.post("/api/keeper/gift")
    assert sim.gifts_given == ["watch"]
    client.post("/api/keeper/cat")
    assert any(b.species == "cat" for b in sim.fauna)


def test_speak_is_404_safe_and_gated():
    sim = make_sim()
    client, _ = client_for(sim)
    # a colony with no units: safe no-op, not a crash
    sim.colonies[0].units.clear()
    r = client.post("/api/keeper/speak", json={"colony_id": sim.colonies[0].colony_id})
    assert r.status_code == 200 and r.json()["heard"] is False
    # an unknown colony id: also safe
    assert client.post("/api/keeper/speak", json={"colony_id": 999}).status_code == 200


def test_control_pacing():
    client, runner = client_for(make_sim())
    client.post("/api/control", json={"paused": True, "sps": 20})
    assert runner.paused is True and runner.sps == 20.0


def test_glyph_mirror_endpoint_and_toggle():
    """U8: /api/glyph.png is 204 until the desktop window posts a snapshot;
    the control toggle flips runner.mirror; a set snapshot serves as PNG."""
    client, runner = client_for(make_sim())
    assert client.get("/api/glyph.png").status_code == 204, "empty until mirrored"
    assert runner.mirror is False, "mirror off by default"
    body = client.post("/api/control", json={"mirror": True}).json()
    assert body["mirror"] is True and runner.mirror is True
    runner.glyph_png = b"\x89PNG\r\n\x1a\nfake-frame"
    resp = client.get("/api/glyph.png")
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"
    assert client.post("/api/control", json={"mirror": False}).json()["mirror"] is False


def test_no_dangerous_imports():
    """DB1/DB8: the dashboard never reaches the shell or the network."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "dashboard.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    banned = {"subprocess", "socket", "requests", "urllib", "os.system"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("eval", "exec", "compile"), \
                "no code execution in the dashboard"
    assert not (banned & imported), f"banned imports: {banned & imported}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all dashboard tests passed")
