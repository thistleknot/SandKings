"""The Keeper's Console: a read-only web view of the terrarium (Round 9).

SAFETY (SPEC_DASHBOARD.md DB1): this serves a snapshot of the sim and
injects the EXISTING keeper verbs - nothing more. No endpoint executes
code, evaluates strings, opens an outbound connection, or reaches the
internet. uvicorn binds 127.0.0.1 only. The sim stays a pure function
of its own state; the "breach/terminal" remains in-sim fiction.

Preconditions: fastapi, uvicorn, numpy, pillow. Imports cleanly with no
display and no pygame. Failure modes: a keeper POST for a dead/absent
colony is a safe no-op.
"""

import argparse
import io
import threading
import time
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from sandkings import (
    Colony, SEASONS, SandKingsSimulation, UnitType, VoxelType, load_checkpoint,
)

# garage-set creatures the keeper may introduce (DB5); cat has its own verb
GARAGE_SPECIES = ('cricket', 'ant', 'scorpion', 'spider', 'rodent')

# palette LUT mirroring the glyph renderer (kept local: no pygame import)
_PALETTE = {
    VoxelType.AIR.value: (16, 16, 20),
    VoxelType.SAND.value: (194, 178, 128),
    VoxelType.STONE.value: (50, 50, 50),
    VoxelType.GLASS.value: (70, 80, 82),
    VoxelType.FOOD.value: (60, 220, 70),
    VoxelType.CORPSE.value: (128, 40, 40),
    VoxelType.TUNNEL_WALL.value: (139, 90, 43),
    VoxelType.TILLED.value: (110, 80, 50),
    VoxelType.CROP.value: (80, 160, 60),
    VoxelType.CROP_RIPE.value: (190, 220, 60),
    VoxelType.COPPER_ORE.value: (184, 115, 51),
    VoxelType.GOLD_ORE.value: (255, 208, 0),
    VoxelType.HULL.value: (120, 130, 150),
    VoxelType.SALVAGE.value: (170, 190, 210),
    VoxelType.WOOD.value: (34, 139, 34),
    VoxelType.WOOD_WALL.value: (139, 105, 20),
    VoxelType.WEB.value: (210, 210, 220),
}


def _palette_lut() -> np.ndarray:
    lut = np.zeros((256, 3), dtype=np.uint8)
    for value, color in _PALETTE.items():
        lut[value] = color
    return lut


def build_state(sim: SandKingsSimulation) -> Dict:
    """DB3: pure JSON snapshot of the terrarium (no mutation)."""
    from chronicle import saga_rows
    from hive_mind_monitor import compose_utterance
    season = sim.season_index()
    weather = [name for attr, name in (
        ("storm_until", "sandstorm"), ("hail_until", "hail"),
        ("flood_until", "flood"), ("cold_until", "cold snap"))
        if getattr(sim, attr, 0) > sim.step_count]
    colonies: List[Dict] = []
    for colony in sim.colonies:
        castes = {t.name.lower(): 0 for t in UnitType}
        for unit in colony.units:
            castes[unit.unit_type.name.lower()] += 1
        utterance = ""
        if getattr(colony, 'breached', False) and colony.units:
            utterance = compose_utterance(colony.units[0], colony, sim)
        colonies.append({
            "id": int(colony.colony_id),
            "house": sim._house(colony) if hasattr(sim, '_house')
            else f"Colony {colony.colony_id}",
            "alive": bool(colony.is_alive()),
            "attitude": (sim.keeper_attitude(colony)
                         if hasattr(sim, 'keeper_attitude') else 'none'),
            "castes": {k: int(v) for k, v in castes.items()},
            "pop": int(len(colony.units)),
            "food": round(float(colony.maw.food_stored), 1),
            "maw_hp": int(round(100 * float(colony.maw.health)
                                / max(1, _maw_max()))),
            "mood": str(_mood(sim, colony)),
            "at_war": bool(getattr(colony, 'at_war', False)),
            "generation": int(getattr(colony, 'generation', 1)),
            "worshipped": bool(getattr(colony, 'worshipped', False)),
            "breached": bool(getattr(colony, 'breached', False)),
            "augment": int(getattr(colony, 'memory_augment', 0)),
            "currency": round(float(getattr(colony, 'currency', 0.0)), 1),
            "utterance": str(utterance),
        })
    saga = [text for _s, text, _sal in saga_rows(
        getattr(sim, 'chronicle', None) or [], min_salience=4, limit=14)]
    events = [f"[{step}] {sim._substitute_houses(m)}"
              if hasattr(sim, '_substitute_houses') else f"[{step}] {m}"
              for step, m in list(getattr(sim, 'events', []))[-10:]]
    return {
        "step": int(sim.step_count),
        "year": int(sim.year() + 1),
        "season": SEASONS[season],
        "dole_pct": int(round(sim.dole_factor() * 100)),
        "drought": bool(getattr(sim, 'drought', False)),
        "weather": weather,
        "grains_minted": round(float(getattr(sim, 'grains_minted', 0.0)), 1),
        "world": [int(sim.world.width), int(sim.world.height)],
        "colonies": colonies,
        "saga": saga,
        "events": events,
        "keeper": {
            "auto": bool(getattr(sim, 'keeper_auto', True)),
            "gifts_given": list(getattr(sim, 'gifts_given', [])),
            "gift_on_ground": getattr(sim, 'gift', None) is not None,
        },
    }


def _maw_max() -> float:
    from sandkings import MAW_MAX_HEALTH
    return MAW_MAX_HEALTH


def _mood(sim: SandKingsSimulation, colony: Colony) -> str:
    if not colony.is_alive():
        return "fallen"
    try:
        return sim._monitor(colony.colony_id).colony_thought(sim, colony)
    except Exception:
        return "..."


def render_frame_png(sim: SandKingsSimulation, scale: int = 640) -> bytes:
    """DB4: top-down PNG via numpy + PIL; no pygame, no display."""
    world = sim.world
    w, h, d = world.width, world.height, world.depth
    lut = _palette_lut()
    vox = world.voxels
    # first non-air column looking down (surface view)
    top = np.full((w, h), VoxelType.AIR.value, dtype=np.uint8)
    for z in range(d - 1, -1, -1):
        layer = vox[:, :, z]
        mask = (top == VoxelType.AIR.value) & (layer != VoxelType.AIR.value)
        top[mask] = layer[mask]
    img = lut[top]  # (w, h, 3)
    # owned surface tint
    own = world.ownership[:, :, d - 1]
    for colony in sim.colonies:
        if not colony.is_alive():
            continue
        cmask = own == colony.colony_id
        col = np.array(colony.color, dtype=np.float32)
        img[cmask] = (0.55 * img[cmask] + 0.45 * col).astype(np.uint8)
    # overlays (drawn at cell resolution, upscaled after)
    for (x, y) in getattr(sim, 'flood_cells', None) or ():
        if 0 <= x < w and 0 <= y < h:
            img[x, y] = (60, 110, 220)
    for (fx, fy, _fz) in getattr(sim, 'fires', None) or {}:
        if 0 <= fx < w and 0 <= fy < h:
            img[fx, fy] = (255, 140, 0)
    for (cx, cy, _cz) in getattr(sim, 'carvings', None) or {}:
        if 0 <= cx < w and 0 <= cy < h:
            img[cx, cy] = (255, 235, 170)
    for colony in sim.colonies:
        for unit in colony.units:
            ux, uy = unit.position[0], unit.position[1]
            if 0 <= ux < w and 0 <= uy < h:
                img[ux, uy] = colony.color
        if colony.is_alive():
            mx, my = colony.maw.position[0], colony.maw.position[1]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if 0 <= mx + dx < w and 0 <= my + dy < h:
                        img[mx + dx, my + dy] = (255, 240, 40)
    for beast in getattr(sim, 'fauna', None) or []:
        bx, by = beast.position[0], beast.position[1]
        if 0 <= bx < w and 0 <= by < h:
            img[bx, by] = (200, 80, 220)
    # (w,h,3) with x as rows -> transpose to (h,w,3) for image orientation
    pil = Image.fromarray(np.transpose(img, (1, 0, 2)), "RGB")
    target_w = max(w, scale)
    pil = pil.resize((target_w, int(target_w * h / w)), Image.NEAREST)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


class TerrariumRunner:
    """DB2: owns the sim + a background stepping thread behind one lock.

    Autosaves the whole terrarium every `save_every` steps when a
    `save_path` is set - the quasi-sentient beings persist themselves so
    a later run resumes them (the resume-by-default contract)."""

    def __init__(self, sim: SandKingsSimulation, sps: float = 6.0,
                 save_path: Optional[str] = None, save_every: int = 600):
        self.sim = sim
        self.lock = threading.Lock()
        self.sps = sps
        self.paused = False
        self.save_path = save_path
        self.save_every = save_every
        self._stop = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self.save_path:
            self.save()

    def save(self):
        from sandkings import save_checkpoint
        with self.lock:
            try:
                save_checkpoint(self.sim, self.save_path)
            except Exception as exc:
                print(f"[keeper] save failed: {exc}")

    def _loop(self):
        while not self._stop:
            t0 = time.time()
            if not self.paused:
                with self.lock:
                    self.sim.step()
                if (self.save_path and self.sim.step_count
                        and self.sim.step_count % self.save_every == 0):
                    self.save()
            delay = max(0.0, 1.0 / max(0.5, self.sps) - (time.time() - t0))
            time.sleep(delay)


def create_app(runner: TerrariumRunner):
    """Build the FastAPI app around a runner. Import-safe (no server)."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from pydantic import BaseModel

    app = FastAPI(title="The Keeper's Console")

    @app.middleware("http")
    async def _csp(request, call_next):  # DB1: no external resources
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        return response

    def _state():
        with runner.lock:
            return build_state(runner.sim)

    def _disarm_auto():
        runner.sim.keeper_auto = False

    class FoodBody(BaseModel):
        x: int
        y: int

    class SpeciesBody(BaseModel):
        species: str

    class DroughtBody(BaseModel):
        on: bool

    class SpeakBody(BaseModel):
        colony_id: int

    class ConverseBody(BaseModel):
        colony_id: int
        text: str

    class ControlBody(BaseModel):
        paused: Optional[bool] = None
        sps: Optional[float] = None

    @app.get("/", response_class=HTMLResponse)
    def index():
        return CONSOLE_HTML

    @app.get("/api/state")
    def state():
        return JSONResponse(_state())

    @app.get("/api/frame.png")
    def frame():
        with runner.lock:
            png = render_frame_png(runner.sim)
        return Response(content=png, media_type="image/png")

    @app.get("/api/telemetry")
    def telemetry():
        # TL4: the free Dwarf-Therapist-style stat feed, per colony
        with runner.lock:
            tel = runner.sim._telemetry()
            data = {c.colony_id: tel.history(c.colony_id)
                    for c in runner.sim.colonies}
        return JSONResponse(data)

    @app.get("/api/ledger")
    def ledger():
        # CU4: lifetime grains produced by each house (the bloodline economy)
        with runner.lock:
            return JSONResponse({
                "grains_minted": round(float(getattr(
                    runner.sim, 'grains_minted', 0.0)), 1),
                "houses": {h: round(float(g), 1) for h, g
                           in (getattr(runner.sim, 'house_grains', {}) or {}).items()},
            })

    @app.post("/api/keeper/food")
    def food(body: FoodBody):
        with runner.lock:
            _disarm_auto()
            w, h = runner.sim.world.width, runner.sim.world.height
            runner.sim.keeper_drop_food(max(0, min(w - 1, body.x)),
                                        max(0, min(h - 1, body.y)))
            return build_state(runner.sim)

    @app.post("/api/keeper/release")
    def release(body: SpeciesBody):
        if body.species not in GARAGE_SPECIES:
            return JSONResponse({"error": "unknown species"}, status_code=400)
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_release(body.species)
            return build_state(runner.sim)

    @app.post("/api/keeper/cat")
    def cat():
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_release_cat()
            return build_state(runner.sim)

    @app.post("/api/keeper/gift")
    def gift():
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_gift()
            return build_state(runner.sim)

    @app.post("/api/keeper/drought")
    def drought(body: DroughtBody):
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_drought(body.on)
            return build_state(runner.sim)

    @app.post("/api/keeper/speak")
    def speak(body: SpeakBody):
        with runner.lock:
            _disarm_auto()
            colony = runner.sim._colony_by_id(body.colony_id)
            heard = False
            if colony is not None and colony.units:
                heard = runner.sim.keeper_speak(colony.units[0])
            result = build_state(runner.sim)
            result["heard"] = heard
            return result

    @app.post("/api/converse")
    def converse(body: ConverseBody):
        # DL4: two-way dialogue over the shared embedding space
        with runner.lock:
            _disarm_auto()
            return runner.sim.converse(body.colony_id, body.text[:200])

    @app.post("/api/control")
    def control(body: ControlBody):
        if body.paused is not None:
            runner.paused = body.paused
        if body.sps is not None:
            runner.sps = max(0.5, min(60.0, body.sps))
        return {"paused": runner.paused, "sps": runner.sps}

    return app


# ---- the frontend (DB6): one inlined, self-contained page ----
CONSOLE_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Keeper's Console</title>
<style>
:root{
  --bg:#0c0d10; --panel:#14161c; --panel-2:#1b1e26; --line:#2a2e39;
  --ink:#e7e3d6; --dim:#9aa0ac; --sand:#c2b280; --glass:#5fb39a;
  --gold:#f2c14e; --wrath:#e0554e; --war:#e08a3c; --breach:#7aa2ff;
  --sp:8px; --r:10px;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#15171d,#0c0d10);
  color:var(--ink);font-family:var(--mono);font-size:14px;line-height:1.45;
  -webkit-font-smoothing:antialiased}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:.02em}
.wrap{max-width:1200px;margin:0 auto;padding:calc(var(--sp)*2)}
header.top{display:flex;align-items:baseline;gap:calc(var(--sp)*2);
  flex-wrap:wrap;padding-bottom:var(--sp);border-bottom:1px solid var(--line)}
header.top h1{font-size:18px;color:var(--sand)}
header.top h1 .sub{color:var(--dim);font-weight:400;font-size:12px}
.chips{display:flex;gap:var(--sp);flex-wrap:wrap;margin-left:auto}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:99px;
  padding:2px 10px;font-size:12px;color:var(--dim)}
.chip b{color:var(--ink);font-weight:600}
.chip.warn{border-color:var(--wrath);color:var(--wrath)}
.chip.wx{border-color:var(--glass);color:var(--glass)}
main{display:grid;grid-template-columns:1.6fr 1fr;gap:calc(var(--sp)*2);
  margin-top:calc(var(--sp)*2)}
@media(max-width:820px){main{grid-template-columns:1fr}}
.stage{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
  padding:var(--sp);position:relative;overflow:hidden}
.stage img{display:block;width:100%;image-rendering:pixelated;border-radius:6px;
  cursor:crosshair}
.stage .hint{position:absolute;left:12px;bottom:10px;font-size:11px;color:var(--dim);
  background:rgba(12,13,16,.7);padding:2px 8px;border-radius:6px}
.rail{display:flex;flex-direction:column;gap:var(--sp)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
  padding:calc(var(--sp)*1.5);cursor:pointer;transition:border-color .15s}
.card:hover{border-color:var(--sand)}
.card.sel{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
.card.dead{opacity:.45}
.card .name{display:flex;align-items:center;gap:var(--sp);font-size:14px}
.dot{width:9px;height:9px;border-radius:99px;background:var(--dim);flex:none}
.dot.reverent{background:var(--gold);box-shadow:0 0 8px var(--gold)}
.dot.wrathful{background:var(--wrath);box-shadow:0 0 8px var(--wrath)}
.badge{font-size:10px;padding:1px 6px;border-radius:99px;border:1px solid;margin-left:4px}
.badge.war{color:var(--war);border-color:var(--war)}
.badge.breach{color:var(--breach);border-color:var(--breach)}
.card .stats{display:flex;gap:calc(var(--sp)*1.5);color:var(--dim);font-size:12px;
  margin-top:6px;flex-wrap:wrap}
.card .stats b{color:var(--ink)}
.card .mood{color:var(--sand);font-size:12px;margin-top:4px;font-style:italic}
.card .says{color:var(--breach);font-size:12px;margin-top:6px}
.speak{margin-top:var(--sp);display:flex;gap:6px}
.speak input{flex:1;background:var(--bg);border:1px solid var(--line);color:var(--ink);
  border-radius:6px;padding:6px 8px;font-family:var(--mono);font-size:12px}
.speak button{background:var(--breach);border:none;color:#0b1020;font-weight:600;
  border-radius:6px;padding:0 12px;cursor:pointer}
.saga{margin-top:calc(var(--sp)*2);background:var(--panel);border:1px solid var(--line);
  border-radius:var(--r);padding:calc(var(--sp)*1.5)}
.saga h3{font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;
  margin-bottom:6px}
.saga .line{font-size:12.5px;color:var(--ink);padding:2px 0;border-bottom:1px dotted var(--line)}
.saga .line:last-child{border-bottom:0}
.console{position:sticky;bottom:0;margin-top:calc(var(--sp)*2);
  background:linear-gradient(180deg,transparent,var(--bg) 30%);padding-top:var(--sp)}
.console .bar{background:var(--panel-2);border:1px solid var(--line);border-radius:var(--r);
  padding:var(--sp);display:flex;gap:calc(var(--sp)*2);flex-wrap:wrap;align-items:center}
.grp{display:flex;gap:6px;align-items:center}
.grp .lab{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;
  margin-right:2px}
button.act{background:var(--panel);border:1px solid var(--line);color:var(--ink);
  border-radius:8px;padding:7px 11px;font-family:var(--mono);font-size:12.5px;cursor:pointer;
  transition:all .12s}
button.act:hover{border-color:var(--sand);color:#fff;transform:translateY(-1px)}
button.act.gold{border-color:var(--gold);color:var(--gold)}
button.act.wrath{border-color:var(--wrath);color:var(--wrath)}
button.act.breach{border-color:var(--breach);color:var(--breach)}
.toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%) translateY(20px);
  background:var(--sand);color:#1a1710;font-weight:600;padding:8px 16px;border-radius:99px;
  opacity:0;transition:all .2s;pointer-events:none;font-size:13px}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
</style></head><body><div class="wrap">
<header class="top">
  <h1>THE KEEPER'S CONSOLE <span class="sub">— a terrarium in a dark garage</span></h1>
  <div class="chips" id="chips"></div>
</header>
<main>
  <div class="stage">
    <img id="frame" alt="terrarium" src="/api/frame.png">
    <div class="hint">click the sand to scatter food</div>
  </div>
  <div class="rail" id="rail"></div>
</main>
<div class="saga"><h3>The Saga</h3><div id="saga"></div></div>
<div class="console"><div class="bar">
  <div class="grp"><span class="lab">Bounty</span>
    <button class="act gold" onclick="post('/api/keeper/gift')">Gift</button></div>
  <div class="grp"><span class="lab">Creatures</span>
    <button class="act" onclick="release('cricket')">Crickets</button>
    <button class="act" onclick="release('ant')">Ants</button>
    <button class="act" onclick="release('scorpion')">Scorpions</button></div>
  <div class="grp"><span class="lab">Wrath</span>
    <button class="act wrath" id="droughtBtn" onclick="toggleDrought()">Withhold</button>
    <button class="act wrath" onclick="post('/api/keeper/cat')">The Cat</button></div>
  <div class="grp" style="margin-left:auto">
    <button class="act" id="pauseBtn" onclick="togglePause()">Pause</button></div>
</div></div>
<div class="toast" id="toast"></div>
</div>
<script>
let state=null, selected=null, paused=false, drought=false, replies={};
function flash(msg){const t=document.getElementById('toast');t.textContent=msg;
  t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),1400);}
async function post(url,body){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:body?JSON.stringify(body):null});
  if(r.ok){state=await r.json();render();flash('the hand moves');}return r;}
function release(s){post('/api/keeper/release',{species:s});}
function toggleDrought(){drought=!drought;post('/api/keeper/drought',{on:drought});}
function togglePause(){paused=!paused;fetch('/api/control',{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify({paused})});
  document.getElementById('pauseBtn').textContent=paused?'Resume':'Pause';}
async function converse(id,inp){const box=document.getElementById(inp);
  const text=box?box.value:'';if(!text)return;
  const r=await fetch('/api/converse',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({colony_id:id,text})});
  if(r.ok){const d=await r.json();
    if(d.understood){replies[id]=d.reply;flash('it answers: '+d.reply);}
    else{flash('the words fall as noise');}render();}
  if(box)box.value='';}
document.getElementById('frame').addEventListener('click',e=>{
  if(!state)return;const img=e.target,rect=img.getBoundingClientRect();
  const wx=Math.floor((e.clientX-rect.left)/rect.width*state.world[0]);
  const wy=Math.floor((e.clientY-rect.top)/rect.height*state.world[1]);
  post('/api/keeper/food',{x:wx,y:wy});});
function attClass(a){return a==='reverent'?'reverent':a==='wrathful'?'wrathful':'';}
function render(){
  if(!state)return; drought=state.drought;
  document.getElementById('droughtBtn').textContent=drought?'Relent':'Withhold';
  const c=document.getElementById('chips');
  c.innerHTML=`<span class="chip"><b>Year ${state.year}</b> · ${state.season}</span>`+
    `<span class="chip">dole <b>${state.dole_pct}%</b></span>`+
    `<span class="chip">step <b>${state.step}</b></span>`+
    (state.grains_minted?`<span class="chip"><b>${state.grains_minted}</b> grains</span>`:'')+
    (state.drought?`<span class="chip warn">DROUGHT</span>`:'')+
    state.weather.map(w=>`<span class="chip wx">${w}</span>`).join('');
  const rail=document.getElementById('rail');rail.innerHTML='';
  state.colonies.forEach(col=>{
    const d=document.createElement('div');
    d.className='card'+(col.alive?'':' dead')+(selected===col.id?' sel':'');
    d.onclick=(ev)=>{if(ev.target.tagName==='INPUT'||ev.target.tagName==='BUTTON')return;
      selected=selected===col.id?null:col.id;render();};
    let badges=(col.at_war?'<span class="badge war">war</span>':'')+
      (col.breached?'<span class="badge breach">awakened</span>':'');
    let inner=`<div class="name"><span class="dot ${attClass(col.attitude)}"></span>`+
      `<b>${col.house}</b>${badges}`+
      (col.augment?`<span class="badge breach">mem+${col.augment}</span>`:'')+
      `</div>`+
      `<div class="stats"><span>pop <b>${col.pop}</b></span>`+
      `<span>food <b>${col.food}</b></span><span>maw <b>${col.maw_hp}%</b></span>`+
      `<span>gen <b>${col.generation}</b></span>`+
      (col.currency?`<span>grains <b>${col.currency}</b></span>`:'')+`</div>`+
      (col.alive?`<div class="mood">${col.mood}</div>`:'');
    if(col.breached&&col.utterance)inner+=`<div class="says">says: "${col.utterance}"</div>`;
    if(selected===col.id&&col.breached&&col.alive){
      inner+=`<div class="speak"><input id="say${col.id}" placeholder="say something to House ${col.house}..." onkeydown="if(event.key==='Enter')converse(${col.id},'say${col.id}')">`+
        `<button onclick="converse(${col.id},'say${col.id}')">Say</button></div>`;
      if(replies[col.id])inner+=`<div class="says">House ${col.house}: "${replies[col.id]}"</div>`;}
    else if(selected===col.id&&!col.breached&&col.alive){
      inner+=`<div class="speak"><input id="say${col.id}" placeholder="(House ${col.house} is not yet awakened)" onkeydown="if(event.key==='Enter')converse(${col.id},'say${col.id}')">`+
        `<button onclick="converse(${col.id},'say${col.id}')">Say</button></div>`;}
    d.innerHTML=inner;rail.appendChild(d);});
  document.getElementById('saga').innerHTML=
    state.saga.slice().reverse().map(l=>`<div class="line">${l}</div>`).join('')
    ||'<div class="line" style="color:var(--dim)">The chronicle is yet unwritten.</div>';
}
async function poll(){try{const r=await fetch('/api/state');if(r.ok){state=await r.json();render();}}
  catch(e){}}
setInterval(poll,500);
setInterval(()=>{document.getElementById('frame').src='/api/frame.png?t='+Date.now();},600);
poll();
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description="The Keeper's Console")
    parser.add_argument("--persist", type=str, default="terrarium.db",
                        help="terrarium sqlite checkpoint (default: resume "
                             "terrarium.db, autosave to it)")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore saved state and start new")
    parser.add_argument("--sps", type=float, default=6.0)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=40)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--colonies", type=int, default=4)
    args = parser.parse_args()

    sim = None
    if args.persist and not args.fresh:
        sim = load_checkpoint(args.persist)  # None if missing/incompatible
        if sim is not None:
            print(f"[keeper] resumed {args.persist} at step {sim.step_count}")
    if sim is None:
        sim = SandKingsSimulation(width=args.width, height=args.height,
                                  depth=args.depth, num_colonies=args.colonies)
    runner = TerrariumRunner(sim, sps=args.sps,
                             save_path=None if args.fresh else args.persist)
    app = create_app(runner)
    runner.start()
    import uvicorn
    print(f"[keeper] console live at http://127.0.0.1:{args.port}")
    # DB1: localhost ONLY - never 0.0.0.0
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
