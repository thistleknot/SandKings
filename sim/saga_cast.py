"""Live AI commentary for SandKings (SPEC_STORY_LOG companion) — snapshot the sim, narrate the delta via a local
Ollama model, sportscaster-style. Shared by the in-viewer B-broadcast screen (`CasterThread`) and the standalone
`tools/saga_watcher.py` (log tailer). Fail-soft: no Ollama / any HTTP error → a quiet, empty feed; the game and the
viewer run identically without it. Pure reads only (story_log.snapshot consumes no RNG), so commentary never
perturbs the simulation.
"""
import json
import threading
import time
import urllib.request

DEFAULT_MODEL = "qwen3.5-oc:2b"       # fast NON-thinking model — the only viable live default. The 9b models here
#   are reasoning-thinking-256k types: a single call ran >120s (huge think pass), which would freeze the live game
#   for minutes per update. For richer prose without the freeze, pull a fast NON-thinking mid model (qwen2.5:7b,
#   llama3.1:8b) and set it here. Fail-soft if absent.
DEFAULT_HOST = "127.0.0.1:11434"
_STOP_SIGNS = ("<think>", "</think>")


def standings(rec):
    """Full per-house line so the chronicler can discuss ANY stat: population, granary (food), maw health, priests
    (worshippers), techs, comprehension, madness, faith, and war state."""
    out = []
    for c in rec.get("colonies", []):
        if not c.get("alive"):
            continue
        flags = []
        if c.get("enlightened"):
            flags.append("enlightened")
        if c.get("breached"):
            flags.append("breached")
        if c.get("madness", 0) > 0.5:
            flags.append("MAD")
        out.append(
            f"{c['house']}(gen{c['gen']}: {c['units']} units, granary {c.get('food', 0):.0f}, "
            f"maw-health {c['maw_hp']}, {c.get('priests', 0)} priests, {len(c.get('techs', []))} techs, "
            f"comprehension {c.get('confidence', 0):.2f}, faith {c.get('keeper', 0.5):.2f}, "
            f"{'at war' if c.get('at_war') else 'at peace'}"
            f"{'; ' + ', '.join(flags) if flags else ''})")
    return "; ".join(out)


def delta(prev, cur):
    """Concrete events between two snapshots — the load-bearing 'what happened' the model narrates."""
    ev = []
    pa = {c["id"]: c for c in prev.get("colonies", [])}
    for c in cur.get("colonies", []):
        p = pa.get(c["id"])
        if not p:
            continue
        if p.get("alive") and not c.get("alive"):
            ev.append(f"{c['house']} fell")
        if not p.get("alive") and c.get("alive"):
            ev.append(f"{c['house']} rose again through succession (gen {c['gen']})")
        if not p.get("enlightened") and c.get("enlightened"):
            ev.append(f"{c['house']} became enlightened")
        if p.get("war_target") != c.get("war_target") and c.get("at_war"):
            tgt = next((x["house"] for x in cur.get("colonies", []) if x["id"] == c.get("war_target")), "a rival")
            ev.append(f"{c['house']} declared war on {tgt}")
        if len(c.get("techs", [])) > len(p.get("techs", [])):
            new = set(c.get("techs", [])) - set(p.get("techs", []))
            ev.append(f"{c['house']} discovered {', '.join(sorted(new))}")
    if cur.get("hegemon") != prev.get("hegemon") and cur.get("hegemon") is not None:
        h = next((x["house"] for x in cur.get("colonies", []) if x["id"] == cur["hegemon"]), f"colony {cur['hegemon']}")
        ev.append(f"{h} rose to hegemon over the terrarium")
    if cur.get("season") != prev.get("season"):
        ev.append(f"the season turned to {cur.get('season')}")
    if cur.get("weather"):
        ev.append(f"the sky brought {', '.join(cur['weather'])}")
    return ev


def narrate(host, model, prev, cur, events, thoughts=""):
    """Return 2-4 sentences calling the ROLLING WINDOW between BEFORE and NOW, or '' on any failure (fail-soft).
    The LLM is shown both states and deciphers the movement itself — where the ball went, who leads/falls."""
    prompt = (
        "You chronicle the AGES of a MEDIEVAL terrarium of sentient insectoid colonies — ant-hives with kings, "
        "priests, catapults, tunnels, granaries, and tech (irrigation, gunpowder), sealed under glass. Each report "
        "covers ONE AGE (a span of steps). This is NOT sport — it is war and survival, life and death under glass. "
        "NO sci-fi, no space. HARD RULES: the glass NEVER breaks and no colony escapes; never claim otherwise. Do "
        "NOT invent deaths/victories not implied by the data. Never use sport words (ball/match/playoff/score).\n\n"
        "You are given the standings at the START of this age and NOW, the battles between, and what each house "
        "brooded on (its unspoken thoughts). Compare START vs NOW and chronicle how the BALANCE OF POWER moved this "
        "age, in 2-4 grim, vivid sentences: who gained ground, who is falling, what battles decided it, and what the "
        "houses were thinking. Concrete; name the houses; ground it in the terrarium (sand, tunnels, the maw). No lists.\n\n"
        f"THE AGE: Year {cur.get('year')}, {cur.get('season')} season, steps {prev.get('step')}->{cur.get('step')}.\n"
        f"START OF AGE: {standings(prev)}\n"
        f"NOW:          {standings(cur)}\n"
        f"BATTLES THIS AGE: {'; '.join(events) if events else 'an uneasy lull, no blood spilled'}.\n"
        f"THOUGHTS (what each house brooded on): {thoughts or 'inscrutable'}.\n"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "think": False,
                       "options": {"temperature": 0.8}}).encode()
    req = urllib.request.Request(f"http://{host}/api/generate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = json.loads(r.read())["response"]
    except Exception:
        return ""
    for s in _STOP_SIGNS:                       # strip <think> from reasoning models
        if s in txt:
            txt = txt.split(s)[-1] if s == "</think>" else txt.split(s)[0]
    return txt.strip()


class CasterThread(threading.Thread):
    """Daemon that narrates the live sim into a shared deque of (step, year, season, text). Every `interval` seconds
    it snapshots the sim (pure read), narrates the delta since the last snapshot, and appends any commentary. All
    errors are swallowed (fail-soft) — a missing Ollama just yields an empty feed, never a crash or a game stall."""

    def __init__(self, sim, out, model=DEFAULT_MODEL, host=DEFAULT_HOST, interval=20.0,
                 is_active=None, lock=None):
        super().__init__(daemon=True)
        self.sim, self.out = sim, out
        self.model, self.host, self.interval = model, host, float(interval)
        self.is_active = is_active            # callable -> only narrate when the B screen is open (else idle: zero
        self.lock = lock                      #   contention, so the sim never stutters unless you're watching)
        self._prev = None
        self._stop = False

    def stop(self):
        self._stop = True

    def _capture(self):
        """Snapshot the sim UNDER the stepper's lock (so it never races/steals GIL time mid-mutation — the cause of
        the step stutter), with `events` spanning the whole rolling window (since the last capture's step), plus each
        alive colony's J-lens thoughts. Returns (snapshot, thoughts_str). Pure read."""
        from story_log import snapshot
        since = self._prev.get("step") if self._prev else None

        def grab():
            snap = snapshot(self.sim, since_step=since)       # events over (since, now] = the window's battles
            return snap, self._gather_thoughts()

        if self.lock is not None:
            with self.lock:
                return grab()
        return grab()

    def _gather_thoughts(self):
        """Each alive colony's J-lens standout thoughts (the neural read-out — 'who was thinking what'). Fail-soft."""
        out = []
        try:
            for c in getattr(self.sim, "colonies", []):
                if not getattr(getattr(c, "maw", None), "alive", False):
                    continue
                words, treach = self.sim.colony_thoughts(c)
                if words:
                    out.append(f"{getattr(c, 'house', c.colony_id)}: {', '.join(w for w, _ in words[:4])}"
                               + (" (treacherous)" if treach > 0.5 else ""))
        except Exception:
            return ""
        return "; ".join(out)

    def run(self):
        # ASYNC by construction: this is a daemon thread. The game NEVER waits for a narration — the sim steps on its
        # own thread while an Ollama call is in flight (urllib releases the GIL during the socket wait), and each
        # result is appended to `out` STAMPED with its window (step/year/season) when it returns. The log always
        # accrues; the game runs at full speed.
        try:
            from story_log import snapshot  # noqa: F401 — import-guard only
        except Exception:
            return
        while not self._stop:
            time.sleep(self.interval)
            try:
                cur, thoughts = self._capture()
            except Exception:
                continue
            if self._prev is None:
                self._prev = cur
                continue
            events = delta(self._prev, cur) + list(cur.get("events", []))    # structural moves ++ the window's drama
            text = narrate(self.host, self.model, self._prev, cur, events, thoughts)
            if text:
                self.out.append((cur.get("step"), cur.get("year"), cur.get("season"), text))
            self._prev = cur
