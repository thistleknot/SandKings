"""Live AI saga-watcher — narrate a running SandKings game's story-log as it progresses, WITHOUT touching the game.

Tails a `--log <path>.jsonl` chronicle that a live game is writing, and every N new turns asks a local Ollama model
to narrate what CHANGED (deaths, successions, wars declared, hegemon shifts, tech/enlightenment gains) as a short
dramatic chronicle. Appends to `<path>.saga.md` and prints to the console. Decoupled from the sim loop, so it never
stalls the game and needs no restart.

Usage:  py310 tools/saga_watcher.py <log.jsonl> [--every 40] [--model qwen3.5-oc:2b] [--host 127.0.0.1:11434]
"""
import argparse, json, os, sys, time, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")   # the model's prose may contain non-cp1252 glyphs (→, —, …)
except Exception:
    pass

STOP_SIGNS = ("<think>", "</think>")


def _standings(rec):
    out = []
    for c in rec.get("colonies", []):
        if not c.get("alive"):
            continue
        out.append(f"{c['house']}(gen{c['gen']}, {c['units']}u, maw{c['maw_hp']}, "
                   f"{'war->'+str(c.get('war_target')) if c.get('at_war') else 'peace'}, "
                   f"conf{c.get('confidence',0):.2f}{', enlightened' if c.get('enlightened') else ''})")
    return "; ".join(out)


def _delta(prev, cur):
    """Concrete events between two snapshots the model can narrate — the load-bearing 'what happened'."""
    ev = []
    pa = {c['id']: c for c in prev.get('colonies', [])}
    for c in cur.get('colonies', []):
        p = pa.get(c['id'])
        if not p:
            continue
        if p.get('alive') and not c.get('alive'):
            ev.append(f"{c['house']} FELL")
        if not p.get('alive') and c.get('alive'):
            ev.append(f"{c['house']} rose again (succession, gen{c['gen']})")
        if not p.get('enlightened') and c.get('enlightened'):
            ev.append(f"{c['house']} became ENLIGHTENED")
        if p.get('war_target') != c.get('war_target') and c.get('at_war'):
            ev.append(f"{c['house']} declared war on colony {c.get('war_target')}")
        if len(c.get('techs', [])) > len(p.get('techs', [])):
            new = set(c.get('techs', [])) - set(p.get('techs', []))
            ev.append(f"{c['house']} discovered {', '.join(new)}")
    if cur.get('hegemon') != prev.get('hegemon') and cur.get('hegemon') is not None:
        ev.append(f"colony {cur['hegemon']} rose to HEGEMON")
    if cur.get('season') != prev.get('season'):
        ev.append(f"the season turned to {cur.get('season')}")
    if cur.get('weather'):
        ev.append(f"weather: {cur.get('weather')}")
    return ev


def narrate(host, model, prev, cur, events):
    prompt = (
        "You are a live commentator for a MEDIEVAL terrarium of sentient insectoid colonies — think ant-hives with "
        "kings, priests, catapults, and tech (irrigation, gunpowder), sealed under glass. NO sci-fi, no space, no "
        "nebulas/stars. In 2-3 vivid sentences, call what just happened this era like a sportscaster: who struck, "
        "who fell, who rose. Concrete and dramatic; name the houses; ground it in the terrarium (sand, tunnels, "
        "granaries, the maw). Do not use lists.\n\n"
        f"Year {cur.get('year')}, {cur.get('season')} season, step {cur.get('step')}.\n"
        f"Events: {'; '.join(events) if events else 'an uneasy lull; the war grinds on'}.\n"
        f"Standings: {_standings(cur)}.\n"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "think": False,
                       "options": {"temperature": 0.8}}).encode()
    req = urllib.request.Request(f"http://{host}/api/generate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = json.loads(r.read())["response"]
    except Exception as e:
        return f"[saga model unavailable: {e}]"
    for s in STOP_SIGNS:                                 # strip any <think> blocks from reasoning models
        if s in txt:
            txt = txt.split(s)[-1] if s == "</think>" else txt.split(s)[0]
    return txt.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--every", type=int, default=40)
    ap.add_argument("--model", default="qwen3.5-oc:2b")
    ap.add_argument("--host", default="127.0.0.1:11434")
    a = ap.parse_args()
    saga = a.log.rsplit(".", 1)[0] + ".saga.md"
    print(f"[saga] watching {a.log} -> {saga}  (model {a.model}, every {a.every} turns)")
    seen = 0
    prev = None
    while True:
        if not os.path.exists(a.log):
            time.sleep(2); continue
        recs = [json.loads(l) for l in open(a.log, encoding="utf-8", errors="ignore") if l.strip()]
        if prev is None and recs:
            prev = recs[0]
        while len(recs) - seen >= a.every:
            window_end = recs[seen + a.every - 1]
            events = _delta(prev, window_end)
            line = narrate(a.host, a.model, prev, window_end, events)
            stamp = f"\n### Year {window_end.get('year')} · {window_end.get('season')} · step {window_end.get('step')}\n{line}\n"
            with open(saga, "a", encoding="utf-8") as fh:
                fh.write(stamp)
            print(stamp)
            prev = window_end
            seen += a.every
        time.sleep(3)


if __name__ == "__main__":
    main()
