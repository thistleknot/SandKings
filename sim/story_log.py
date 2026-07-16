"""Per-turn JSONL game chronicle + an optional local-LLM saga (SPEC_STORY_LOG).

The JSONL log is the source of truth: one compact JSON object per logged step (world + per-colony state + that
turn's drama events). An optional summarizer batches every N lines to a local Ollama model (e.g. qwen3:4b) for
a narrative recap written to `<log>.story.md`.

Design contracts:
- Purity: `snapshot(sim)` only READS sim state and consumes NO RNG, so logging never perturbs the simulation.
- Fail-soft: the summary path NEVER raises into the game — a missing/unreachable Ollama, an unknown model, or
  any HTTP error prints one skip notice and the JSONL log keeps writing. The game runs identically with or
  without Ollama installed.
- Safe: file append + one localhost POST; no eval/exec, no third-party host.
"""
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_MODEL = "qwen3:4b"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_PATH = "sandkings.jsonl"


def _colony_row(sim, colony, diplomacy) -> Dict[str, Any]:
    """A compact, JSON-safe snapshot of one colony (pure read, getattr-guarded for pre-feature pickles)."""
    epithet = ""
    try:
        epithet = sim._house_epithets().get(sim._house_name(colony), "")
    except Exception:
        epithet = ""
    wt = diplomacy.war_target.get(colony.colony_id) if diplomacy is not None else None
    return {
        "id": colony.colony_id,
        "house": getattr(colony, "house", "") or "",
        "epithet": epithet,
        "alive": bool(colony.is_alive()),
        "gen": int(getattr(colony, "generation", 1)),
        "units": len(colony.units),
        "food": round(float(colony.maw.food_stored), 1),
        "maw_hp": int(getattr(colony.maw, "health", 0)),
        "at_war": bool(getattr(colony, "at_war", False)),
        "war_target": wt,
        "keeper": round(float(getattr(colony, "keeper_sentiment", 0.5)), 2),
        "madness": round(float(getattr(colony, "madness", 0.0)), 2),
        "confidence": round(float(getattr(colony, "confidence", 0.5)), 2),
        "breached": bool(getattr(colony, "breached", False)),
        "enlightened": bool(getattr(colony, "enlightened", False)),
        "priests": sum(1 for u in colony.units if getattr(u, "is_priest", False)),
        "techs": sorted(getattr(colony, "techs", set()) or set()),
    }


def snapshot(sim, since_step: Optional[int] = None) -> Dict[str, Any]:
    """SL1: a compact per-turn snapshot of the whole game (pure read, no RNG).

    `events` covers (since_step, step]: at a cadence > 1 this captures the drama BETWEEN logged snapshots, not
    just the logged step's, so the chronicle stays complete (bounded by the sim's 50-deep event deque).
    """
    from sandkings import SEASONS
    step = sim.step_count
    lo = step - 1 if since_step is None else since_step
    d = getattr(sim, "diplomacy", None)
    weather = [name for name, active in (
        ("storm", getattr(sim, "storm_until", 0) > step),
        ("hail", getattr(sim, "hail_until", 0) > step),
        ("cold", getattr(sim, "cold_until", 0) > step),
        ("flood", getattr(sim, "flood_until", 0) > step),
        ("heat", getattr(sim, "arena_heat_until", 0) > step),
    ) if active]
    sky = getattr(sim, "sky_sign", None)
    return {
        "step": step,
        "year": sim.year(),
        "season": SEASONS[sim.season_index()],
        "hegemon": (d.hegemon if d is not None else None),
        "weather": weather,
        "pond": {"guppies": round(float(getattr(sim, "guppy_pop", 0.0) or 0.0)),
                 "algae": round(float(getattr(sim, "algae", 0.0) or 0.0))},
        "sign": (sky.get("kind") if isinstance(sky, dict) else None),
        "colonies": [_colony_row(sim, c, d) for c in sim.colonies],
        "events": [m for (s, m) in getattr(sim, "events", []) if lo < s <= step],
    }


def _build_prompt(rows: List[Dict[str, Any]]) -> str:
    """A bounded chronicler prompt: the season arc, the surviving houses' end-state, and the run of events."""
    a, b = rows[0], rows[-1]
    lines = [
        "You are the chronicler of Sand Kings, a terrarium of intelligent insectoid colonies ruled by",
        "stationary queens ('maws') under a keeper-god beyond the glass. Write a short, vivid saga",
        f"(120-180 words) of what happened between step {a['step']} and step {b['step']}. Name the houses;",
        "dwell on their wars, betrayals, madness, famines, and the keeper's signs. Prose only, no lists.",
        "",
        f"Season: {a['season']} -> {b['season']}.",
        "Surviving houses at the end:",
    ]
    for c in b["colonies"]:
        if c["alive"]:
            lines.append(
                f"  House {c['house']} {c['epithet']}: {c['units']} spawn, food {c['food']}, "
                f"{'AT WAR' if c['at_war'] else 'at peace'}, keeper-favor {c['keeper']}, "
                f"madness {c['madness']}{', priests' if c['priests'] else ''}"
                f"{', enlightened' if c['enlightened'] else ''}")
    fallen = [c for c in b["colonies"] if not c["alive"]]
    if fallen:
        lines.append(f"Fallen/empty slots: {len(fallen)}.")
    lines += ["", "Chronicle of events (step: what happened):"]
    events = [f"  {r['step']}: {e}" for r in rows for e in r["events"]]
    lines += events[:80] if events else ["  (a quiet interval — no notable drama)"]
    return "\n".join(lines)


def _ollama(host: str, model: str, prompt: str, timeout: float = 120.0) -> Optional[str]:
    """One local Ollama /api/generate call. Returns the text, or None on any failure (fail-soft)."""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = (data.get("response") or "").strip()
    return text or None


class StoryLog:
    """SL1-SL2: append a JSON line per logged step; optionally batch every `summarize_every` lines to a local
    Ollama model for a saga in `<log>.story.md`. Fail-soft on the summary path."""

    def __init__(self, path: str = DEFAULT_PATH, every: int = 1, summarize_every: int = 0,
                 model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.path = path
        self.every = max(1, int(every))
        self.summarize_every = max(0, int(summarize_every))
        self.model = model
        self.host = host.rstrip("/")
        self.summary_path = (path[:-6] if path.endswith(".jsonl") else path) + ".story.md"
        self._fh = open(path, "a", encoding="utf-8")
        self._buf: List[Dict[str, Any]] = []
        self._last_step: Optional[int] = None    # for the events-since-last-line window
        print(f"[STORY] logging each turn -> {path}"
              + (f"; saga every {self.summarize_every} via {self.model}"
                 if self.summarize_every else " (JSONL only; --summarize-every to add sagas)"))

    def record(self, sim) -> None:
        """Called at the end of sim.step(). Writes a JSONL line on the cadence; batches summaries."""
        if sim.step_count % self.every:
            return
        row = snapshot(sim, since_step=self._last_step)   # events since the previous logged line
        self._last_step = sim.step_count
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()
        if self.summarize_every:
            self._buf.append(row)
            if len(self._buf) >= self.summarize_every:
                self._summarize(self._buf)
                self._buf = []

    def _summarize(self, rows: List[Dict[str, Any]]) -> None:
        """Fail-soft: an unreachable/absent Ollama prints a skip notice; it never raises into the game."""
        lo, hi = rows[0]["step"], rows[-1]["step"]
        try:
            text = _ollama(self.host, self.model, _build_prompt(rows))
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            print(f"[STORY] steps {lo}-{hi}: Ollama unavailable ({type(exc).__name__}) — saga skipped, log intact")
            return
        if not text:
            print(f"[STORY] steps {lo}-{hi}: empty response — saga skipped")
            return
        with open(self.summary_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Steps {lo}–{hi} ({rows[0]['season']} → {rows[-1]['season']})\n\n{text}\n")
        print(f"[STORY] saga for steps {lo}-{hi} -> {self.summary_path}")

    def close(self) -> None:
        """Flush a final partial summary buffer, then close the file. Idempotent."""
        if getattr(self, "_fh", None) is None:
            return
        if self.summarize_every and self._buf:
            self._summarize(self._buf)
            self._buf = []
        self._fh.close()
        self._fh = None
