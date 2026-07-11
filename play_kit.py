"""Play Kit (SPEC_PLAY_KIT.md PK1-PK6): a headless client to drive, test, and
PLAY the terrarium through the same API the browser uses - no pixels, no curl.

In-process by default (a non-started TerrariumRunner + FastAPI TestClient, so
stepping is deterministic and no socket is opened), or remote against a live
console via `Terrarium.connect(url)`. Ships scripted scenarios that exercise
the mechanics and narrate them, plus a REPL / `--do` command runner.

Preconditions: sandkings + dashboard import cleanly; fastapi for in-process,
httpx for remote. Stepping only ever happens through `/api/step` (PK2), the
single deterministic advance path. Failure modes: a remote console that is
down (httpx raises); an off-roster species (the API 400s, surfaced as an
error dict).
"""

import argparse
import random
from typing import Dict, List, Optional

import numpy as np


class Terrarium:
    """PK1: scriptable client over the console API."""

    def __init__(self, canon: bool = True, colonies: int = 4, width: int = 64,
                 height: int = 40, depth: int = 14, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        from fastapi.testclient import TestClient

        from dashboard import TerrariumRunner, create_app
        from sandkings import SandKingsSimulation
        self.sim = SandKingsSimulation(width=width, height=height, depth=depth,
                                       num_colonies=colonies, canon=canon)
        self._runner = TerrariumRunner(self.sim, sps=6.0)  # NOT started
        self._client = TestClient(create_app(self._runner))
        self._remote = None

    @classmethod
    def connect(cls, url: str) -> "Terrarium":
        """PK1 remote: observe/act on a live, autonomously-stepping console."""
        import httpx
        self = cls.__new__(cls)
        self.sim = None
        self._runner = None
        self._client = None
        self._remote = httpx.Client(base_url=url.rstrip("/"), timeout=10.0)
        return self

    # --- transport -------------------------------------------------------
    def _get(self, path: str) -> Dict:
        r = (self._remote or self._client).get(path)
        return r.json()

    def _post(self, path: str, body: Optional[Dict] = None) -> Dict:
        r = (self._remote or self._client).post(path, json=body or {})
        try:
            return r.json()
        except Exception:
            return {"status": r.status_code}

    # --- PK2 stepping ----------------------------------------------------
    def step(self, n: int = 1) -> Dict:
        return self._post("/api/step", {"n": int(n)})

    # --- PK3 actions -----------------------------------------------------
    def feed(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict:
        w, h = self.state()["world"]
        return self._post("/api/keeper/food",
                          {"x": w // 2 if x is None else int(x),
                           "y": h // 2 if y is None else int(y)})

    def gift(self) -> Dict:
        return self._post("/api/keeper/gift")

    def release(self, species: str) -> Dict:
        return self._post("/api/keeper/release", {"species": species})

    def cat(self) -> Dict:
        return self._post("/api/keeper/cat")

    def drought(self, on: bool = True) -> Dict:
        return self._post("/api/keeper/drought", {"on": bool(on)})

    def temp(self, direction: str) -> Dict:
        return self._post("/api/keeper/temp", {"dir": direction})

    def water(self, big: bool = False, x=None, y=None) -> Dict:
        return self._post("/api/keeper/water", {"x": x, "y": y, "big": big})

    def seed(self, x=None, y=None) -> Dict:
        return self._post("/api/keeper/seed", {"x": x, "y": y})

    def set_water(self, level: float) -> Dict:
        return self._post("/api/keeper/panel", {"water": level})

    def set_sun(self, hours: float) -> Dict:
        return self._post("/api/keeper/panel", {"sun": hours})

    def speak(self, colony_id: int) -> Dict:
        return self._post("/api/keeper/speak", {"colony_id": int(colony_id)})

    def say(self, colony_id: int, text: str) -> Dict:
        return self._post("/api/converse",
                          {"colony_id": int(colony_id), "text": text})

    def pause(self) -> Dict:
        return self._post("/api/control", {"paused": True})

    def resume(self) -> Dict:
        return self._post("/api/control", {"paused": False})

    def sps(self, v: float) -> Dict:
        return self._post("/api/control", {"sps": float(v)})

    def mirror(self, on: bool = True) -> Dict:
        return self._post("/api/control", {"mirror": bool(on)})

    # --- PK4 reads -------------------------------------------------------
    def state(self) -> Dict:
        return self._get("/api/state")

    def colonies(self) -> List[Dict]:
        return self.state().get("colonies", [])

    def colony(self, cid: int) -> Optional[Dict]:
        for c in self.colonies():
            if c["id"] == cid:
                return c
        return None

    def events(self, n: int = 10) -> List[str]:
        return self.state().get("events", [])[-n:]

    def summary(self) -> str:
        st = self.state()
        head = f"t={st['step']} {st['season']}"
        if st.get("drought"):
            head += " DROUGHT"
        if st.get("weather"):
            head += " [" + ", ".join(st["weather"]) + "]"
        if st.get("keeper_bound"):
            head += f" BOUND<{st.get('keeper_bound_by', '?')}>"
        elif st.get("keeper_influence_word"):
            head += f" ({st['keeper_influence_word']})"
        lines = [head]
        for c in st.get("colonies", []):
            if not c.get("alive"):
                lines.append(f"  {c.get('house', '?')}: DEAD")
                continue
            flags = []
            if c.get("worshipped"):
                flags.append("worship")
            stage = c.get("stage", 1)
            flags.append({1: "insectoid", 2: "newbreed", 3: "SHADE"}.get(stage))
            lines.append(
                f"  {c['house']}: pop{c['pop']} food{int(c['food'])} "
                f"sent{c.get('sentiment', 0.5):.2f} " + " ".join(f for f in flags if f))
        return "\n".join(lines)

    def aim(self, cid: int):
        """In-process helper: a colony's maw (x,y) for targeted feeding."""
        if self.sim is None:
            st = self.state()
            return (st["world"][0] // 2, st["world"][1] // 2)
        m = self.sim.colonies[cid].maw.position
        return (m[0], m[1])

    def close(self):
        if self._remote is not None:
            self._remote.close()


class ScenarioResult:
    def __init__(self, name: str, ok: bool, transcript: List[str]):
        self.name, self.ok, self.transcript = name, ok, transcript


# --- PK5 scenarios (in-process; use t.sim to reach states fast, act via API) --

def scenario_worship(t: Terrarium) -> ScenarioResult:
    # AW: worship of the keeper only exists AFTER the breakout (the great
    # other is known). Pre-breakout, bounty is just good fortune.
    log, cid = [], 0
    house = t.colony(cid)["house"]
    mx, my = t.aim(cid)
    for _ in range(3):
        t.feed(mx, my)
        t.step(15)
    pre = t.colony(cid).get("worshipped", False)
    log.append(f"pre-breakout: fed House {house} -> worshipped={pre} (fortune, not worship)")
    if t.sim is not None:
        t.sim._escape(t.sim.colonies[cid])  # the true breakout past the glass
    log.append(f"House {house} breaks out - and now knows the great other")
    for _ in range(6):
        t.feed(mx, my)
        t.step(15)
    post = t.colony(cid).get("worshipped", False)
    log.append(f"post-breakout: fed again -> worshipped={post}")
    ok = (not pre) and post
    log.append("it worships only once it knows the hand" if ok else "unexpected")
    return ScenarioResult("worship", ok, log)


def scenario_cruelty(t: Terrarium) -> ScenarioResult:
    log, cid = [], 0
    if t.sim is not None:
        t.sim._escape(t.sim.colonies[cid])  # AW: sentiment moves only post-breakout
    mx, my = t.aim(cid)
    for _ in range(6):
        t.feed(mx, my)
        t.step(15)
    before = t.colony(cid).get("sentiment", 0.5)
    log.append(f"sentiment after feeding: {before:.2f}")
    t.drought(True)
    for _ in range(8):
        t.step(20)
    after = t.colony(cid).get("sentiment", 0.5)
    log.append(f"sentiment after sustained drought: {after:.2f}")
    ok = after < before
    log.append("the god's cruelty soured them" if ok else "no souring")
    return ScenarioResult("cruelty", ok, log)


def scenario_metamorphosis(t: Terrarium) -> ScenarioResult:
    from sandkings import MOLT_FOOD
    log, cid = [], 0
    if t.sim is None:
        return ScenarioResult("metamorphosis", False, ["needs in-process sim"])
    t.sim.colonies[cid].maw.food_stored = MOLT_FOOD + 80  # a fat maw
    log.append(f"gorged House {t.colony(cid)['house']} to {MOLT_FOOD + 80} food")
    t.step(5)
    stage = t.colony(cid).get("stage", 1)
    log.append(f"stage after gorging: {stage}")
    return ScenarioResult("metamorphosis", stage >= 2, log)


def scenario_dialogue(t: Terrarium) -> ScenarioResult:
    log, cid = [], 0
    if t.sim is not None:
        t.sim.colonies[cid].breached = True  # wake it so it can hold speech
    reply = t.say(cid, "let us make peace")
    log.append(f"said 'let us make peace' -> heard={reply.get('heard')!r}"
               f" reply={reply.get('reply')!r}")
    ok = reply.get("understood") and reply.get("heard") == "ally"
    log.append("it understood peace as ally" if ok else "misheard")
    return ScenarioResult("dialogue", bool(ok), log)


def scenario_turning(t: Terrarium) -> ScenarioResult:
    log, cid = [], 0
    if t.sim is None:
        return ScenarioResult("turning", False, ["needs in-process sim"])
    c = t.sim.colonies[cid]
    c.stage = 3
    c.breached = True
    c.keeper_sentiment = 0.05  # a Shade that hates its god
    t.step(3)
    st = t.state()
    bound = st.get("keeper_bound")
    log.append(f"keeper_bound={bound} by {st.get('keeper_bound_by')!r}")
    # a bound god's feed is stayed
    fed = t.feed()
    log.append("feed after binding was stayed" if bound else "not bound")
    return ScenarioResult("turning", bool(bound), log)


SCENARIOS = {
    "worship": scenario_worship,
    "cruelty": scenario_cruelty,
    "metamorphosis": scenario_metamorphosis,
    "dialogue": scenario_dialogue,
    "turning": scenario_turning,
}

# short command aliases for the REPL / --do runner
_SPECIES = {"cricket", "ant", "small_spider", "spider", "scorpion", "snake",
            "squirrel", "rabbit"}


def dispatch(t: Terrarium, line: str) -> str:
    """PK6: run one REPL/--do command, return a line to print."""
    parts = line.strip().split()
    if not parts:
        return ""
    cmd, args = parts[0].lower(), parts[1:]
    if cmd in ("step", "s"):
        t.step(int(args[0]) if args else 1)
    elif cmd == "feed":
        t.feed(*(int(a) for a in args[:2])) if args else t.feed()
    elif cmd == "gift":
        t.gift()
    elif cmd in _SPECIES:
        t.release(cmd)
    elif cmd == "release" and args:
        t.release(args[0])
    elif cmd == "cat":
        t.cat()
    elif cmd == "drought":
        t.drought(not args or args[0] != "off")
    elif cmd in ("heat", "cold"):
        t.temp(cmd)
    elif cmd in ("rain", "water"):
        t.water(big=False)
    elif cmd == "deluge":
        t.water(big=True)
    elif cmd in ("seed", "seeds"):
        t.seed()
    elif cmd == "sun" and args:
        t.set_sun(float(args[0]))
    elif cmd == "reservoir" and args:
        t.set_water(float(args[0]))
    elif cmd == "say" and len(args) >= 2:
        r = t.say(int(args[0]), " ".join(args[1:]))
        return f"  it answers: {r.get('reply') or '(noise)'}"
    elif cmd == "speak" and args:
        t.speak(int(args[0]))
    elif cmd in ("state", "houses", "summary", ""):
        return t.summary()
    elif cmd == "events":
        return "\n".join(t.events(int(args[0]) if args else 10))
    else:
        return f"  ? unknown command: {line.strip()}"
    return t.summary()


def run_scenario(name: str, seed: int = 7, canon: bool = True) -> ScenarioResult:
    t = Terrarium(canon=canon, seed=seed)
    try:
        return SCENARIOS[name](t)
    finally:
        t.close()


def _main():
    p = argparse.ArgumentParser(description="Play Kit for the terrarium")
    p.add_argument("--scenario", help="scenario name or 'all'")
    p.add_argument("--do", help="run a ';'-separated command script then exit")
    p.add_argument("--repl", action="store_true", help="interactive REPL")
    p.add_argument("--url", help="remote console URL (else in-process)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-canon", action="store_true")
    args = p.parse_args()

    if args.scenario:
        names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
        all_ok = True
        for name in names:
            res = run_scenario(name, seed=args.seed, canon=not args.no_canon)
            mark = "PASS" if res.ok else "FAIL"
            print(f"[{mark}] {res.name}")
            for line in res.transcript:
                print(f"    {line}")
            all_ok = all_ok and res.ok
        raise SystemExit(0 if all_ok else 1)

    t = (Terrarium.connect(args.url) if args.url
         else Terrarium(canon=not args.no_canon, seed=args.seed))
    if args.do:
        for line in args.do.split(";"):
            out = dispatch(t, line)
            print(f">>> {line.strip()}")
            if out:
                print(out)
        t.close()
        return
    if args.repl:
        print(t.summary())
        print("commands: step [n] | feed | gift | cricket|ant|spider|... |"
              " cat | drought on|off | heat | cold | say <id> <text> |"
              " speak <id> | state | events | quit")
        while True:
            try:
                line = input("keeper> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if line in ("quit", "exit", "q"):
                break
            out = dispatch(t, line)
            if out:
                print(out)
        t.close()
        return
    print(t.summary())
    t.close()


if __name__ == "__main__":
    _main()
