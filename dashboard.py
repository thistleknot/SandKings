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
    Colony, KEEPER_FAUNA, SEASONS, SandKingsSimulation, UnitType, VoxelType,
    load_checkpoint,
)

# AR2: the keeper's release whitelist IS the classified roster (no drift);
# cat and the arena temperatures have their own verbs
GARAGE_SPECIES = KEEPER_FAUNA

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
    VoxelType.CASTLE.value: (200, 195, 210),   # pale stone monument (K5)
    VoxelType.WATER.value: (40, 90, 200),      # standing water (HYDRO)
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
    from sandkings import WAGE_ENABLED
    season = sim.season_index()
    weather = [name for attr, name in (
        ("storm_until", "sandstorm"), ("hail_until", "hail"),
        ("flood_until", "flood"), ("cold_until", "cold snap"),
        ("arena_heat_until", "heat wave"),  # AR3: keeper's arena temperature
        ("arena_cold_until", "cold wave"))
        if getattr(sim, attr, 0) > sim.step_count]
    if getattr(sim, 'kw_until', 0) > sim.step_count:  # HH2: the hand's water
        weather.append("deluge" if getattr(sim, 'kw_big', False) else "rain")
    colonies: List[Dict] = []
    for colony in sim.colonies:
        castes = {t.name.lower(): 0 for t in UnitType}
        for unit in colony.units:
            castes[unit.unit_type.name.lower()] += 1
        utterance = ""
        if getattr(colony, 'breached', False) and colony.units:
            utterance = compose_utterance(colony.units[0], colony, sim)
        from sandkings import breakout_progress
        _bp_phase, _bp_frac, _bp_label = breakout_progress(colony)
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
            "enlightened": bool(getattr(colony, 'enlightened', False)),  # EN9
            "terminal_uses": int(getattr(colony, 'terminal_uses', 0)),  # BRK-B
            "breach_proximity": round(float(_bp_frac), 2),  # BRK-B: [0,1]
            "breach_phase": str(_bp_phase),  # BRK-B
            "confidence": round(float(getattr(colony, 'confidence', 0.5)), 2),  # DP9
            "favoritism": round(float(getattr(colony, 'favoritism', 0.0)), 2),  # DP9
            "agitation": round(float(getattr(colony, 'agitation', 0.0)), 2),    # DP9
            "stage": int(getattr(colony, 'stage', 1)),
            "augment": int(getattr(colony, 'memory_augment', 0)),
            "currency": round(float(getattr(colony, 'currency', 0.0)), 1),
            "sentiment": round(float(getattr(colony, 'keeper_sentiment', 0.5)), 2),
            # AW1: aware of the "great other" only post-breakout; before that a
            # nature mood, not a keeper sentiment
            "techs": sorted(getattr(colony, 'techs', set())),  # TE5
            "crafted": sorted(getattr(colony, 'crafted', set())),  # TE13
            "tech_xp": {t: round(float(x), 2)  # TE9 proficiency
                        for t, x in getattr(colony, 'tech_xp', {}).items()},
            "aware": bool(getattr(colony, 'breached', False)),
            "nature_mood": (sim._nature_mood(colony)
                            if not getattr(colony, 'breached', False)
                            and hasattr(sim, '_nature_mood') else ""),
            "utterance": str(utterance),
            "thralls_out": int(sum(1 for u in colony.units
                                   if getattr(u, 'laboring_for', -1) >= 0)),  # units forced to labor
            "thralls_in": int(sum(1 for other in sim.colonies
                                  for u in other.units
                                  if getattr(u, 'laboring_for', -1) == colony.colony_id)),  # units enslaved
        })
    saga = [text for _s, text, _sal in saga_rows(
        getattr(sim, 'chronicle', None) or [], min_salience=4, limit=14)]
    events = [f"[{step}] {sim._substitute_houses(m)}"
              if hasattr(sim, '_substitute_houses') else f"[{step}] {m}"
              for step, m in list(getattr(sim, 'events', []))[-10:]]

    # Economy: wage contracts (capped at ~20) and bargain modes
    contracts = []
    for c in getattr(sim, 'wage_contracts', [])[:20]:
        if c.get('alive'):
            contracts.append({
                'kind': c.get('kind', ''),
                'buyer': int(c.get('buyer_id', -1)),
                'seller': int(c.get('seller_id', -1)),
                'factor': c.get('factor', ''),
                'w': round(float(c.get('w', 0.0)), 2),
                'fee': round(float(c.get('fee', 0.0)), 2),
            })

    bargain_modes = []
    for pair, mode in getattr(sim, 'bargain_modes', {}).items():
        if mode != 'none':
            ids = list(pair)
            if len(ids) == 2:
                bargain_modes.append({
                    'a': int(ids[0]),
                    'b': int(ids[1]),
                    'mode': str(mode),
                })

    economy_on = bool(getattr(sim, 'bargain_enabled', False)) or WAGE_ENABLED

    return {
        "step": int(sim.step_count),
        "year": int(sim.year() + 1),
        "season": SEASONS[season],
        "dole_pct": int(round(sim.dole_factor() * 100)),
        "drought": bool(getattr(sim, 'drought', False)),
        "water_level": round(float(getattr(sim, 'water_level', 0.6)), 2),
        "water_target": round(float(getattr(sim, 'water_target', 0.6)), 2),
        "sun_hours": round(float(getattr(sim, 'sun_hours', 12)), 1),
        "keeper_influence": round(float(getattr(sim, 'keeper_influence', 0.0)), 2),
        "keeper_influence_word": (sim.keeper_influence_word()
                                  if hasattr(sim, 'keeper_influence_word') else ""),
        "keeper_bound": bool(getattr(sim, 'keeper_bound', False)),
        "keeper_bound_by": str(getattr(sim, 'keeper_bound_by', "")),
        "weather": weather,
        "grains_minted": round(float(getattr(sim, 'grains_minted', 0.0)), 1),
        "world": [int(sim.world.width), int(sim.world.height)],
        "colonies": colonies,
        "saga": saga,
        "events": events,
        "contracts": contracts,
        "bargain_modes": bargain_modes,
        "economy_on": economy_on,
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
    # X-RAY: reveal subsurface tunnels (owned carved AIR) from this top-down
    # surface projection, else the warren is invisible. Columns with a tunnel
    # get a dim ghost of the digging house's color.
    air = VoxelType.AIR.value
    tunnel3d = (vox == air) & (world.ownership >= 0)
    has_tunnel = tunnel3d.any(axis=2)
    if has_tunnel.any():
        z_top = (d - 1) - np.argmax(tunnel3d[:, :, ::-1], axis=2)   # topmost tunnel z
        owner = np.take_along_axis(world.ownership, z_top[:, :, None], axis=2)[:, :, 0]
        for colony in sim.colonies:
            m = has_tunnel & (owner == colony.colony_id)
            if m.any():
                ghost = np.array(colony.color, dtype=np.float32) * 0.5
                img[m] = (0.62 * img[m] + 0.38 * ghost).astype(np.uint8)
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
                img[ux, uy] = ((170, 110, 50) if getattr(unit, 'rafted', False)
                               else colony.color)   # rafted units ride a wood raft
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
        # U8: optional glyph-view mirror. The desktop window snapshots its
        # pygame surface into `glyph_png` only while `mirror` is on (a browser
        # toggle); the web /api/glyph.png serves the latest snapshot. Ref
        # swaps are atomic under the GIL, so no lock is needed for these.
        self.mirror = False
        self.glyph_png: Optional[bytes] = None

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
                self._step_once()
            delay = max(0.0, 1.0 / max(0.5, self.sps) - (time.time() - t0))
            time.sleep(delay)

    def _step_once(self):
        """One locked step + the autosave check. The single place stepping
        and periodic persistence happen (U1)."""
        with self.lock:
            self.sim.step()
        if (self.save_path and self.sim.step_count
                and self.sim.step_count % self.save_every == 0):
            self.save()

    def single_step(self):
        """U4: advance exactly one step while paused (the desktop S key)."""
        if self.paused:
            self._step_once()

    def step_owed(self, n: int) -> int:
        """U2: drive `n` steps synchronously (the standalone viewer loop's
        deterministic path). Returns the count stepped."""
        for _ in range(n):
            self._step_once()
        return n


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

    class TempBody(BaseModel):
        dir: str  # 'heat' | 'cold'

    class WaterBody(BaseModel):
        x: Optional[int] = None
        y: Optional[int] = None
        big: bool = False

    class SeedBody(BaseModel):
        x: Optional[int] = None
        y: Optional[int] = None

    class PanelBody(BaseModel):
        water: Optional[float] = None  # reservoir set point 0..1
        sun: Optional[float] = None    # daylight hours

    class MaterialBody(BaseModel):
        kind: str
        x: Optional[int] = None
        y: Optional[int] = None

    class SpeakBody(BaseModel):
        colony_id: int

    class OpenDoorBody(BaseModel):
        colony_id: int

    class ConverseBody(BaseModel):
        colony_id: int
        text: str

    class ControlBody(BaseModel):
        paused: Optional[bool] = None
        sps: Optional[float] = None
        mirror: Optional[bool] = None

    class StepBody(BaseModel):
        n: int = 1

    class EconomyBody(BaseModel):
        on: bool

    @app.get("/", response_class=HTMLResponse)
    def index():
        return CONSOLE_HTML

    @app.get("/api/glyph.png")
    def glyph():
        # U8: the latest desktop glyph-view snapshot (empty until the window
        # is running with mirror on). 204 when there is nothing to show.
        png = runner.glyph_png
        if not png:
            return Response(status_code=204)
        return Response(content=png, media_type="image/png")

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
    def gift(kind: Optional[str] = None):
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_gift(kind=kind)
            return build_state(runner.sim)

    @app.post("/api/keeper/opendoor")
    def opendoor(body: OpenDoorBody):
        with runner.lock:
            _disarm_auto()
            colony = runner.sim._colony_by_id(body.colony_id)
            if colony is not None:
                runner.sim.keeper_open_door(colony)
            return build_state(runner.sim)

    @app.post("/api/keeper/drought")
    def drought(body: DroughtBody):
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_drought(body.on)
            return build_state(runner.sim)

    @app.post("/api/keeper/economy")
    def economy(body: EconomyBody):
        import sandkings
        with runner.lock:
            if body.on:
                sandkings.BARGAIN_ENABLED = True
                sandkings.WAGE_ENABLED = True
                sandkings.CAPTURE_CHANCE = sandkings.BARGAIN_CAPTURE_CHANCE
                runner.sim.bargain_enabled = True
            else:
                sandkings.BARGAIN_ENABLED = False
                sandkings.WAGE_ENABLED = False
                sandkings.CAPTURE_CHANCE = 0.0
                runner.sim.bargain_enabled = False
            return build_state(runner.sim)

    @app.post("/api/keeper/temp")
    def temp(body: TempBody):
        # AR3: the arena temperature (uncomfortable, not lethal)
        if body.dir not in ("heat", "cold"):
            return JSONResponse({"error": "dir must be heat|cold"},
                                status_code=400)
        with runner.lock:
            _disarm_auto()
            runner.sim.keeper_temperature(body.dir)
            return build_state(runner.sim)

    @app.post("/api/keeper/material")
    def material(body: MaterialBody):
        with runner.lock:
            _disarm_auto()
            w, h = runner.sim.world.width, runner.sim.world.height
            x = w // 2 if body.x is None else max(1, min(w - 2, body.x))
            y = h // 2 if body.y is None else max(1, min(h - 2, body.y))
            runner.sim.keeper_material(body.kind, x, y)
            return build_state(runner.sim)

    @app.post("/api/keeper/ignite")
    def ignite(body: WaterBody):  # reuses {x,y}; big ignored
        with runner.lock:
            _disarm_auto()
            w, h = runner.sim.world.width, runner.sim.world.height
            x = w // 2 if body.x is None else max(1, min(w - 2, body.x))
            y = h // 2 if body.y is None else max(1, min(h - 2, body.y))
            runner.sim.keeper_ignite(x, y)
            return build_state(runner.sim)

    @app.post("/api/keeper/water")
    def water(body: WaterBody):
        with runner.lock:
            _disarm_auto()
            w, h = runner.sim.world.width, runner.sim.world.height
            x = w // 2 if body.x is None else max(1, min(w - 2, body.x))
            y = h // 2 if body.y is None else max(1, min(h - 2, body.y))
            runner.sim.keeper_water(x, y, big=body.big)
            return build_state(runner.sim)

    @app.post("/api/keeper/seed")
    def seed(body: SeedBody):
        with runner.lock:
            _disarm_auto()
            w, h = runner.sim.world.width, runner.sim.world.height
            x = w // 2 if body.x is None else max(1, min(w - 2, body.x))
            y = h // 2 if body.y is None else max(1, min(h - 2, body.y))
            runner.sim.keeper_seed(x, y)
            return build_state(runner.sim)

    @app.post("/api/keeper/panel")
    def panel(body: PanelBody):
        # BI2: the diffuser panel behind the glass - NOT auto-disarming and
        # not hand-gated (it works even when the terrarium has bound the god)
        with runner.lock:
            if body.water is not None:
                runner.sim.keeper_set_water(body.water)
            if body.sun is not None:
                runner.sim.keeper_set_sun(body.sun)
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
        if body.mirror is not None:
            runner.mirror = bool(body.mirror)  # U8: glyph-view mirror toggle
        return {"paused": runner.paused, "sps": runner.sps,
                "mirror": runner.mirror}

    @app.post("/api/step")
    def step_n(body: StepBody):
        # PK2: deterministic advance for the play kit / headless testing.
        # Localhost only; it just drives the sim this runner already owns.
        n = max(1, min(500, int(body.n)))
        runner.step_owed(n)
        return _state()

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
  <img id="glyph" alt="glyph view" style="display:none;max-width:100%;
       image-rendering:pixelated;border:1px solid var(--line)">
  <div class="rail" id="rail"></div>
</main>
<div class="saga"><h3>The Saga</h3><div id="saga"></div></div>
<div class="console"><div class="bar">
  <div class="grp"><span class="lab">Gifts</span>
    <button class="act" onclick="feed()">Feed</button>
    <button class="act" onclick="seed()">Seeds</button>
    <button class="act" onclick="water(false)">Rain</button>
    <button class="act" onclick="release('cricket')">Crickets</button>
    <button class="act" onclick="release('ant')">Ants</button>
    <button class="act" onclick="release('small_spider')">Small Spider</button>
    <button class="act" onclick="release('fly')">Flies</button>
    <span class="lab" id="techGiftLab">Tech Gift</span>
    <button class="act gold" id="giftAbacus" onclick="post('/api/keeper/gift?kind=abacus')">Abacus</button>
    <button class="act gold" id="giftWatch" onclick="post('/api/keeper/gift?kind=watch')">Watch</button>
    <button class="act gold" id="giftCalculator" onclick="post('/api/keeper/gift?kind=calculator')">Calculator</button>
    <button class="act gold" id="giftPi" onclick="post('/api/keeper/gift?kind=pi')">Raspberry Pi</button></div>
  <div class="grp"><span class="lab">Materials</span>
    <button class="act" onclick="mat('toothpick')">Toothpick</button>
    <button class="act" onclick="mat('string')">String</button>
    <button class="act" onclick="mat('lincoln_log')">Lincoln Log</button>
    <button class="act" onclick="mat('copper_pipe')">Copper Pipe</button>
    <button class="act" onclick="mat('tacks')">Tacks</button></div>
  <div class="grp"><span class="lab">Wrath</span>
    <button class="act wrath" onclick="post('/api/keeper/ignite')">Firecracker</button>
    <button class="act wrath" onclick="water(true)">Deluge</button>
    <button class="act wrath" onclick="release('spider')">Big Spider</button>
    <button class="act wrath" onclick="release('scorpion')">Scorpion</button>
    <button class="act wrath" onclick="release('snake')">Snake</button>
    <button class="act wrath" onclick="release('hornets')">Hornets</button>
    <button class="act wrath" onclick="temp('heat')">Heat</button>
    <button class="act wrath" onclick="temp('cold')">Cold</button>
    <button class="act wrath" id="droughtBtn" onclick="toggleDrought()">Withhold</button>
    <button class="act wrath" onclick="post('/api/keeper/cat')">The Cat</button></div>
  <div class="grp"><span class="lab">Neutral</span>
    <button class="act" onclick="release('squirrel')">Squirrel</button>
    <button class="act" onclick="release('rabbit')">Rabbit</button>
    <button class="act" onclick="release('mouse')">Mouse</button></div>
  <div class="grp"><span class="lab">Breakthrough</span>
    <button class="act breach" onclick="openDoor()">Open the Door</button></div>
  <div class="grp"><span class="lab">Panel (behind the glass)</span>
    <button class="act" onclick="panel('water',-0.1)">Water −</button>
    <button class="act" onclick="panel('water',0.1)">Water +</button>
    <button class="act" onclick="panel('sun',-2)">Sun −</button>
    <button class="act" onclick="panel('sun',2)">Sun +</button></div>
  <div class="grp"><span class="lab">Economy</span>
    <button class="act" id="econBtn" onclick="toggleEconomy()">Economy: Off</button></div>
  <div class="grp" style="margin-left:auto">
    <button class="act" id="mirrorBtn" onclick="toggleMirror()">Mirror View</button>
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
function temp(d){post('/api/keeper/temp',{dir:d});}
function water(big){post('/api/keeper/water',{big});}
function seed(){post('/api/keeper/seed',{});}
function mat(kind){post('/api/keeper/material',{kind});}
function openDoor(){if(selected==null){flash('select a house first');return;}post('/api/keeper/opendoor',{colony_id:selected});}
function panel(which,delta){if(!state)return;
  const cur=which==='water'?state.water_target:state.sun_hours;
  post('/api/keeper/panel',{[which]:cur+delta});}
function toggleDrought(){drought=!drought;post('/api/keeper/drought',{on:drought});}
function toggleEconomy(){post('/api/keeper/economy',{on:!(state&&state.economy_on)});}
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
function feed(){if(state)post('/api/keeper/food',{x:state.world[0]>>1,y:state.world[1]>>1});}
let mirror=false, mirrorTimer=null, mirrorWarned=false;
function toggleMirror(){
  mirror=!mirror;mirrorWarned=false;
  fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({mirror})});
  document.getElementById('mirrorBtn').textContent=mirror?'Hide View':'Mirror View';
  const img=document.getElementById('glyph');
  if(mirror){img.style.display='';
    if(!mirrorTimer)mirrorTimer=setInterval(()=>{img.src='/api/glyph.png?t='+Date.now();},1200);}
  else{if(mirrorTimer){clearInterval(mirrorTimer);mirrorTimer=null;}img.style.display='none';}}
document.getElementById('glyph').onerror=()=>{if(mirror&&!mirrorWarned){
  mirrorWarned=true;flash('no glyph view yet — is the desktop window running?');}};
function attClass(a){return a==='reverent'?'reverent':a==='wrathful'?'wrathful':'';}
function sentWord(s,att){if(att==='wrathful'||s<0.33)return'hateful';
  if(s>0.66&&att==='reverent')return'devout';return'wary';}
function sentColor(s){return s<0.33?'#e0554e':s>0.66?'#f2c14e':'#9aa0ac';}
function render(){
  if(!state)return; drought=state.drought;
  document.getElementById('droughtBtn').textContent=drought?'Relent':'Withhold';
  document.getElementById('econBtn').textContent=(state.economy_on?'Economy: On':'Economy: Off');
  const _given = (state.keeper&&state.keeper.gifts_given)||[];
  const _ladder = ['abacus','watch','calculator','pi'];
  const _ids = {abacus:'giftAbacus',watch:'giftWatch',calculator:'giftCalculator',pi:'giftPi'};
  const _unlock = {abacus:1,watch:3,calculator:7,pi:15};
  _ladder.forEach(function(k){
    const b = document.getElementById(_ids[k]); if(!b) return;
    const claimed = _given.indexOf(k)>=0;
    const locked = (state.year||0) < _unlock[k];
    b.disabled = claimed;
    b.title = claimed ? 'already given' : (locked ? ('unlocks year '+_unlock[k]) : 'available');
    b.style.opacity = (claimed||locked) ? 0.5 : 1.0;
  });
  // label the NEXT gift (first ungiven rung), with its unlock year / readiness
  const _names = {abacus:'Abacus',watch:'Watch',calculator:'Calculator',pi:'Raspberry Pi'};
  const _next = _ladder.find(function(k){ return _given.indexOf(k)<0; });
  const _giftLab = document.getElementById('techGiftLab');
  if(_giftLab){
    _giftLab.textContent = _next
      ? ('Tech Gift → '+_names[_next]+((state.year||0)<_unlock[_next]
          ? (' (yr '+_unlock[_next]+')') : ' (ready)'))
      : 'Tech Gift · all given';
  }
  const c=document.getElementById('chips');
  c.innerHTML=`<span class="chip"><b>Year ${state.year}</b> · ${state.season}</span>`+
    `<span class="chip">dole <b>${state.dole_pct}%</b></span>`+
    `<span class="chip">step <b>${state.step}</b></span>`+
    `<span class="chip">water <b>${Math.round(state.water_level*100)}%</b> · sun <b>${state.sun_hours}h</b></span>`+
    (state.grains_minted?`<span class="chip"><b>${state.grains_minted}</b> grains</span>`:'')+
    (state.drought?`<span class="chip warn">DROUGHT</span>`:'')+
    (state.keeper_bound?`<span class="chip warn">BOUND · House ${state.keeper_bound_by}</span>`
      :(state.keeper_influence_word?`<span class="chip warn">you feel ${state.keeper_influence_word}</span>`:''))+
    state.weather.map(w=>`<span class="chip wx">${w}</span>`).join('');
  // Preserve a focused chat input across the full re-render. The rail is rebuilt
  // on every state poll (innerHTML=''), which destroys the <input> and steals
  // focus — so clicking into "say something..." deselected a beat later. Capture
  // the focused say-input's id/value/caret now and restore it after the rebuild.
  const _act=document.activeElement;
  let _focus=null;
  if(_act&&_act.tagName==='INPUT'&&_act.id&&_act.id.indexOf('say')===0){
    _focus={id:_act.id,val:_act.value,ss:_act.selectionStart,se:_act.selectionEnd};
  }
  const rail=document.getElementById('rail');rail.innerHTML='';
  state.colonies.forEach(col=>{
    const d=document.createElement('div');
    d.className='card'+(col.alive?'':' dead')+(selected===col.id?' sel':'');
    d.onclick=(ev)=>{if(ev.target.tagName==='INPUT'||ev.target.tagName==='BUTTON')return;
      selected=selected===col.id?null:col.id;render();};
    let stageName=col.stage>=3?'SHADE':col.stage>=2?'new breed':'';
    let badges=(col.at_war?'<span class="badge war">war</span>':'')+
      (stageName?`<span class="badge breach">${stageName}</span>`:'')+(col.enlightened?'<span class="badge breach">enlightened</span>':'');  // EN9
    let inner=`<div class="name"><span class="dot ${attClass(col.attitude)}"></span>`+
      `<b>${col.house}</b>${badges}`+
      (col.augment?`<span class="badge breach">mem+${col.augment}</span>`:'')+
      `</div>`+
      `<div class="stats"><span>pop <b>${col.pop}</b></span>`+
      `<span>food <b>${col.food}</b></span><span>maw <b>${col.maw_hp}%</b></span>`+
      `<span>gen <b>${col.generation}</b></span>`+
      (col.currency?`<span>grains <b>${col.currency}</b></span>`:'')+
      (col.thralls_out||col.thralls_in?`<span>thralls <b>${col.thralls_out}↓/${col.thralls_in}↑</b></span>`:'')+
      (col.confidence!==undefined?`<span>disp <b>${col.confidence>0.62?'bold':col.confidence<0.38?'timid':'steady'}${col.favoritism>0.15?' ♥':col.favoritism<-0.15?' ✗':''}${col.agitation>0.3?' ⚡':''}</b></span>`:'')+
      (col.aware
        ? `<span>toward you <b style="color:${sentColor(col.sentiment)}">${sentWord(col.sentiment,col.attitude)}</b></span>`
        : `<span>feels <b>${col.nature_mood||'—'}</b> <i style="opacity:.6">(unexplained forces)</i></span>`)+`</div>`+
      (col.alive?`<div class="mood">${col.mood}</div>`:'');
    if(col.techs&&col.techs.length)inner+=`<div class="mood">tech: ${col.techs.map(t=>col.tech_xp&&col.tech_xp[t]!=null?`${t} ${Math.round(col.tech_xp[t]*100)}%`:t).join(', ')}</div>`;
    if(col.crafted&&col.crafted.length)inner+=`<div class="mood">crafted: ${col.crafted.join(', ')}</div>`;
    if(col.breached&&col.utterance)inner+=`<div class="says">says: "${col.utterance}"</div>`;
    if(selected===col.id&&col.breached&&col.alive){
      inner+=`<div class="speak"><input id="say${col.id}" placeholder="say something to House ${col.house}..." onkeydown="if(event.key==='Enter')converse(${col.id},'say${col.id}')">`+
        `<button onclick="converse(${col.id},'say${col.id}')">Say</button></div>`;
      if(replies[col.id])inner+=`<div class="says">House ${col.house}: "${replies[col.id]}"</div>`;}
    else if(selected===col.id&&!col.breached&&col.alive){
      inner+=`<div class="speak"><input id="say${col.id}" placeholder="(House ${col.house} is not yet awakened)" onkeydown="if(event.key==='Enter')converse(${col.id},'say${col.id}')">`+
        `<button onclick="converse(${col.id},'say${col.id}')">Say</button></div>`;}
    d.innerHTML=inner;rail.appendChild(d);});
  if(_focus){                          // restore the chat input the rebuild just replaced
    const _r=document.getElementById(_focus.id);
    if(_r){_r.value=_focus.val;_r.focus();
      try{_r.setSelectionRange(_focus.ss,_focus.se);}catch(e){}}
  }
  document.getElementById('saga').innerHTML=
    state.saga.slice().reverse().map(l=>`<div class="line">${l}</div>`).join('')
    ||'<div class="line" style="color:var(--dim)">The chronicle is yet unwritten.</div>';

  // Economy panel: bargain modes, contracts, status
  const econ=document.createElement('div');
  econ.className='saga';
  let econHtml='<h3>Economy</h3>';
  if(!state.economy_on){econHtml+='<div class="line" style="color:var(--dim)">— off —</div>';}
  else{
    if(state.bargain_modes&&state.bargain_modes.length){
      econHtml+='<div class="line" style="font-size:12px;margin-bottom:4px"><b>Bargains</b></div>';
      state.bargain_modes.forEach(bm=>{
        const mode_colors={'wage':'#f2c14e','subjugate':'#e0554e','annihilate':'#ff5555'};
        const col_a=state.colonies.find(c=>c.id===bm.a);const col_b=state.colonies.find(c=>c.id===bm.b);
        const arrow=bm.mode==='wage'?'→':bm.mode==='subjugate'?'⊳':bm.mode==='annihilate'?'✗':'?';
        const col=mode_colors[bm.mode]||'#9aa0ac';
        econHtml+=`<div class="line" style="font-size:11px;color:${col}">${col_a?col_a.house:'C'+bm.a} ${arrow} ${col_b?col_b.house:'C'+bm.b}</div>`;
      });
    }
    if(state.contracts&&state.contracts.length){
      econHtml+='<div class="line" style="font-size:12px;margin:6px 0 4px 0"><b>Contracts</b></div>';
      state.contracts.forEach(ct=>{
        const buyer=state.colonies.find(c=>c.id===ct.buyer);const seller=state.colonies.find(c=>c.id===ct.seller);
        const bname=buyer?buyer.house:'C'+ct.buyer;const sname=seller?seller.house:'C'+ct.seller;
        econHtml+=`<div class="line" style="font-size:11px">${ct.kind} ${bname}←${sname} w:${ct.w} fee:${ct.fee}</div>`;
      });
    }
  }
  econ.innerHTML=econHtml;
  document.getElementById('rail').appendChild(econ);
}
async function poll(){try{const r=await fetch('/api/state');if(r.ok){state=await r.json();render();}}
  catch(e){}}
setInterval(poll,500);
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
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="bind address. Default 127.0.0.1 (localhost "
                             "only). Inside the isolated container, console "
                             "mode passes 0.0.0.0 so the host's published "
                             "loopback port can reach it - safe because the "
                             "port is published ONLY to the host's 127.0.0.1.")
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=40)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--colonies", type=int, default=4)
    parser.add_argument("--canon", action="store_true",
                        help="seat the novella's four houses (CH1)")
    parser.add_argument("--dynamic", action="store_true",
                        help="dynamic population + Spartan succession (count breathes 2..8)")
    parser.add_argument("--hydro", action="store_true",
                        help="water engineering: oasis springs, water flows/pools, colonies "
                             "dig rivers/reservoirs/dikes, boats cross water (SPEC_HYDRO)")
    args = parser.parse_args()

    if getattr(args, 'hydro', False):
        import sandkings as _sk
        _sk.HYDRO_SOURCES_ENABLED = True
        print("[keeper] HYDRO enabled - the oasis springs and water engineering is live")

    sim = None
    if args.persist and not args.fresh:
        sim = load_checkpoint(args.persist)  # None if missing/incompatible
        if sim is not None:
            print(f"[keeper] resumed {args.persist} at step {sim.step_count}")
    if sim is None:
        sim = SandKingsSimulation(width=args.width, height=args.height,
                                  depth=args.depth, num_colonies=args.colonies,
                                  canon=args.canon,
                                  dynamic_population=getattr(args, 'dynamic', False))
    runner = TerrariumRunner(sim, sps=args.sps,
                             save_path=None if args.fresh else args.persist)
    app = create_app(runner)
    runner.start()
    import uvicorn
    print(f"[keeper] console live on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
