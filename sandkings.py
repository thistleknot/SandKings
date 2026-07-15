"""
Sand Kings Simulation
Combines Core War's evolution with 1pageskirmish's tactics in a 3D voxel terrarium

Inspired by GRRM's Sand Kings novella - 4 colored Maw colonies compete for territory
"""

import itertools
import math
import os
import pickle
import random
import sqlite3
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
from typing import List, Tuple, Set, Optional, Dict
from PIL import Image
import io
# matplotlib (GIF Visualizer) and tqdm (CLI loop) are optional: the
# headless sim, dashboard, and chat must import without them so the
# container stays lean (SPEC_SANDBOX). GIF mode requires matplotlib.
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable=None, *args, **kwargs):
        return iterable if iterable is not None else []
import torch

# Neural hive mind
try:
    from neural_hive import (
        HiveMindBrain, SoldierLayer,
        encode_soldier_state, decode_soldier_action
    )
    NEURAL_AVAILABLE = True
except ImportError:
    NEURAL_AVAILABLE = False
    print("Warning: neural_hive.py not found. Neural mode disabled.")

# ============================================================================
# VOXEL TYPES & WORLD
# ============================================================================

# Terrarium liveness constants (SPEC_TERRARIUM_LIVENESS.md)
MAINTENANCE_COST = 0.1       # food per unit per step
FEED_INTERVAL = 100          # steps between keeper feedings
TARGET_POP = 18              # sustainable units per colony (feed sizing)
HARVEST_YIELD = 15           # food per FOOD/CORPSE voxel harvested
BOOTSTRAP_FLOOR = 10         # minimum colony food after each feeding
STARVATION_MAX_KILLS = 2     # starvation deaths per colony per step
UNIT_CAP = 30                # max units per colony (spawn gate)
MAW_MAX_HEALTH = 500
MAW_REGEN = 0.5              # HP per step while unbesieged
RESPAWN_DELAY = 300          # steps a fallen colony slot stays empty
RESPAWN_FOOD = 50            # starting food for an arriving colony

# Dynamic Population & Succession (SPEC_POPULATION.md)
MAX_COLONIES = 8                        # fixed slot-pool cap (bounded pool)   [prov:C]
DYNAMIC_POPULATION = False              # master flag; OFF reproduces today    [prov:C]
# pop_state lifecycle values (string constants; no Enum dependency, pickle-trivial)
POP_ACTIVE     = "ACTIVE"               # a live, participating slot         [prov:C]
POP_SUCCESSION = "SUCCESSION"           # reserved: Phase-1+ succession       [prov:C]
POP_DORMANT    = "DORMANT"              # reserved: Phase-1+ empty slot       [prov:C]
POP_STATES = frozenset({POP_ACTIVE, POP_SUCCESSION, POP_DORMANT})
MIN_ACTIVE_COLONIES = 2                  # liveness FLOOR: below this, founding fills in (Phase 6) [prov:C]
# Succession (SPEC_SUCCESSION / decision 2026-07-11): a queen's death is a drama,
# not an automatic respawn. A Spartan heir (high colony loyalty) resists the psionic
# collapse and reclaims the line — SAME house continues, boosted. Below the gate the
# house goes mad → extinct (Phase 2 disgrace). All inert while DYNAMIC_POPULATION=False.
SPARTAN_LOYALTY  = 0.7                    # colony-genome loyalty gate for an heir to rise [prov:C]
SPARTAN_BOOST    = 1.3                    # augmented-net / boosted-stat multiplier on the rise [prov:C]
SUCCESSION_WINDOW = 800                   # half-year live-transition window for a live aspirant [prov:C]
# Founding / budding — the bounded pool BREATHES around equilibrium (Phase 6).
EQUILIBRIUM_COLONIES = 4                  # ~natural equilibrium (not a hard constant) [prov:C]
FOUND_FILLIN_CHANCE  = 0.02              # per-tick chance a DORMANT slot fills the sparse board [prov:C]
BUD_FOOD             = 320               # maw hoard that lets a prosperous house bud a daughter [prov:C]
BUD_CHANCE           = 0.01              # per-tick chance a prosperous house buds when crowded [prov:C]
POP_TICK_INTERVAL    = 50               # steps between population-breathing evaluations [prov:C]

WAR_CHEST = 400              # food hoard that sends a colony to war (SPEC T10)
SCOUT_ALARM_RANGE = 5        # Manhattan distance that triggers a scout alarm (SPEC T11)
KNOWN_FOOD_CAP = 8           # shared food-intel entries per colony (SPEC T11)
MAW_MIGRATE_HEALTH = 0.4     # HP fraction below which a Maw flees (SPEC T15)
MAW_MIGRATE_COST = 2.0       # food per step of Maw flight
STORM_INTERVAL = 600         # steps between storm rolls (SPEC T12)
STORM_CHANCE = 0.5           # probability a roll spawns a storm
STORM_DURATION = 25          # steps a storm blows
STORM_COLUMNS_FRACTION = 1 / 50  # surface columns disturbed per storm step

# Seasons & Stone constants (SPEC_SEASONS_AND_STONE.md)
SEASON_LENGTH = 400          # steps per season (T16)
SEASONS = ("Flood", "Growth", "Dust", "Chill")
YEAR_LENGTH = 4 * SEASON_LENGTH
DOLE_FACTOR = {0: 1.00, 1: 0.75, 2: 0.50, 3: 0.25}   # by season index (T17)
DOLE_RAMP = (1.00, 0.50, 0.00)                        # per-year floor on the factor
STORM_INTERVAL_DUST = 200    # Dust season storm cadence (T16)
SPOIL_INTERVAL = 10          # Dust spoilage sweep cadence
SPOIL_CHANCE = 0.02          # per exposed FOOD voxel per sweep
SEED_COST = 5                # food paid at sowing (T19)
CROP_TICK = 5                # crop growth phase cadence
CROP_GROWDUR = 300           # grow-steps to ripen (DF GROWDUR range)
CROP_YIELD = 40              # food per ripe crop harvested
FARM_RADIUS = 6              # plots within this Chebyshev xy of own maw
FARM_MAX_PLOTS = 12          # per colony
FARM_START_FOOD = 60         # farming flag on above this...
FARM_STOP_FOOD = 30          # ...off below this (hysteresis)
GROW_SEASONS = (0, 1)        # Flood, Growth (T20)
OASIS_RADIUS = 6             # disc at map center (T22)
OASIS_GROWTH_MULT = 2
OASIS_FEED_BONUS = 2         # keeper voxels placed inside the disc
COPPER_VEINS_PER_BAND = 2    # ore generation (T23)
GOLD_CLUSTERS = 3
MINE_TIME = 5                # worker-steps per ore voxel (T24)
COPPER_ARMOR_HP = 10         # bonus max HP per armored soldier (T25)
SALVAGE_MINE_TIME = 8        # worker-steps per SALVAGE voxel (T28)
WRECK_NOTICE_RANGE = 6       # Chebyshev: exposed hull becomes known (T29)
BUILD_MIN_FOOD = 60          # no machine work while poor (T37)

# Timber, Bone & Flame constants (SPEC_TIMBER_AND_FLAME.md T41-T48)
TREE_CAP = 40                # world WOOD ceiling (regrowth stops)
TREE_REGROWTH_P = 0.02       # per WOOD voxel per Flood feeding tick
CHOP_TIME = 4                # worker-steps to fell a trunk
FELL_LENGTH = 3              # trunk voxels laid along the fall line
ROT_INTERVAL = 100           # organic stores lose 1 per interval; ore never
PALISADE_RING = 2            # wall ring radius around the maw (T43)
WALL_ROT = 800               # steps before a palisade rots to sand
CASTLE_PROSPERITY_STEPS = 500  # steps a house must hold food > WAR_CHEST before it
#                                raises a castle on its own (K5: prosperity made visible)
BUILD_LABOR_EVERY = 3          # 1/N workers (by unit_id) are designated builders that
#                                prioritize the castle/palisade so a ring actually completes
LEVEE_RANGE = 18               # a nest within this of the oasis raises SAND dikes/dams
#                                on its water-facing arc (the flood sim honors raised sand)
SPEAR_ATTACK = 4             # bonus attack while armed (T44)
SPEAR_LIFE = 400             # steps before it splinters
RAM_COST = 3                 # wood for a battering ram (T44b)
RAM_LIFE = 600               # steps before the ram rots
RAM_SIEGE_MULT = 2           # maw-siege damage multiplier with a ram
FIRE_TICK = 5                # fire cadence (rides the crop/machine tick)
FIRE_BURN = 8                # ticks a cell burns
FIRE_SPREAD_P = 0.5          # per adjacent flammable per tick
FIRE_DAMAGE = 2              # per tick to units within Chebyshev 1
FIRECRACKER_RADIUS = 3       # keeper firecracker blast radius (arena disaster)
FIRECRACKER_DAMAGE = 4       # blast damage to exposed units (a bang, not the tank)
MARAUDER_INTERVAL = 700      # pack-spawn roll cadence (T48)
MARAUDER_PACK = (2, 3)
MARAUDER_BOUNTY = 3          # corpse voxels per slain marauder
FLAMMABLE_VOXELS = (8, 9, 14, 15, 16)  # CROP, CROP_RIPE, WOOD, WOOD_WALL, WEB

# T48 fauna bestiary: (weight, hp, attack, pack, hunt_range, bounty)
# hunt_range 0 = neutral (retaliates only). Sand kings are scorpion-sized.
FAUNA = {
    'spider':   (0.20, 25, 8, (2, 3), 20, 2),
    'rabbit':   (0.18, 60, 6, (1, 2), 0, 6),
    'squirrel': (0.15, 30, 3, (1, 2), 0, 4),
    'bird':     (0.15, 20, 12, (1, 1), 40, 2),
    'rodent':   (0.12, 12, 2, (3, 4), 0, 1),
    'scorpion': (0.10, 22, 6, (1, 2), 15, 2),
    'snake':    (0.06, 80, 18, (1, 1), 25, 5),
    'anteater': (0.04, 150, 25, (1, 1), 30, 8),
    # weight 0 = keeper-introduced only (K2); never in random rolls
    'cricket':  (0.0, 8, 1, (2, 4), 0, 2),
    'ant':      (0.0, 6, 2, (4, 6), 0, 1),
    'small_spider': (0.0, 10, 2, (2, 4), 0, 3),  # AR1: weak, learnable prey
    'fly':      (0.0, 3, 1, (4, 8), 0, 1),   # wingless flies: weak swarm prey
    'mouse':    (0.0, 20, 3, (1, 1), 0, 5),  # a mouse: bites back, good food
    'cat':      (0.0, 400, 60, (1, 1), 60, 12),
    'hornets':  (0.0, 8, 4, (6, 10), 30, 1),  # T48b keeper-wrath scourge: released, never a random incursion
}
FAUNA_EVENTS = {
    'spider': "Spiders crawl up from the deep!",
    'rabbit': "A great rabbit lopes onto the sands",
    'squirrel': "A squirrel scampers down from the palms",
    'bird': "A shadow wheels overhead!",
    'rodent': "Rodents scurry in from the wastes",
    'scorpion': "Scorpions skitter across the dunes",
    'snake': "Something long moves beneath the sand...",
    'anteater': "An anteater stalks the sands!",
    'hornets': "A hornet scourge boils out of the dark - the air itself turns to venom",
    'cricket': "Crickets drop from the keeper's hand",
    'ant': "A column of ants files in from a crack in the world",
    'small_spider': "Small spiders are set loose - easy prey to learn on",
    'fly': "Wingless flies tumble onto the sand, twitching",
    'mouse': "A mouse is dropped in, whiskers trembling",
    'cat': "Something enormous pads across the sand...",
}

# AR1: the keeper's roster, classified by intent (single source of truth;
# dashboard imports KEEPER_FAUNA as its release whitelist)
KEEPER_GIFTS = ('cricket', 'ant', 'small_spider', 'fly')  # food + learning
KEEPER_WRATH = ('spider', 'scorpion', 'snake', 'hornets')          # arena predators
KEEPER_NEUTRAL = ('squirrel', 'rabbit', 'mouse')        # ambient, bite back
KEEPER_FAUNA = KEEPER_GIFTS + KEEPER_WRATH + KEEPER_NEUTRAL
POISON_DURATION = 20         # scorpion sting DoT (1 HP/step)
FAUNA_RAMPAGE = 500          # steps before an unslain incursion wanders off
HORNET_SPEED = 3            # [prov:C feel=swarm] cells/tick; flies through AIR like the bird
HORNET_STING_DURATION = 20  # [prov:C feel=venom] sting DoT ticks (1 HP/step); mirrors POISON_DURATION

# Sentience Arc constants (SPEC_SENTIENCE.md S1-S4)
RESONANCE_RANGE = 6          # Chebyshev radius of thought contagion
RESONANCE_ALPHA = 0.15       # hidden-state blend rate per resonance tick
RESONANCE_TICK = 2           # cadence of the resonance phase
ALLY_RESONANCE_FACTOR = 0.3  # cross-colony damping (conspecific allies)
SPECIATION_DIST = 0.35       # mean trait distance beyond which no mingling
DREAM_REPLAYS = 3            # offline TD updates per Chill decision tick

# Desert Weather constants (SPEC_WEATHER.md W1-W3)
FLOOD_INTERVAL = 150         # Flood-season surge roll cadence (in-season
                             # rolls; 600 resonated with YEAR_LENGTH and
                             # yielded ~1 eligible roll per 3 years)
FLOOD_CHANCE = 0.2
FLOOD_RADIUS_MAX = 16        # the inundation's furthest reach from the oasis
FLOOD_DURATION = 100         # grow -> hold -> recede, steps
FLOOD_RISE = 2               # water line = oasis surface + FLOOD_RISE;
                             # banks raised above it are DAMS
FLOOD_DAMAGE = 2             # per step to exposed units under water
FLOOD_SILT_P = 0.08          # receding water tills the sand (Nile silt)
HAIL_SHARE = 0.35            # Growth/Dust storm rolls that become hail
HAIL_TICK = 5                # exposed-unit damage cadence under hail
HAIL_SMASH_P = 0.04          # per crop per hail tick
COLD_INTERVAL = 500          # cold-snap roll cadence (Chill; Dust halved)
COLD_CHANCE = 0.5
COLD_DURATION = 40           # the desert night's ambassador
COLD_TICK = 5

# Arena Mode: keeper-driven temperature (SPEC_ARENA AR3). Uncomfortable, NOT
# lethal - a separate track from the natural (killing) frost of W3.
ARENA_TEMP_DURATION = 60     # steps a keeper heat/cold wave lasts
ARENA_TEMP_TICK = 3          # discomfort cadence
ARENA_FOOD_DRAIN = 0.6       # hoard drained per exposed unit per tick
ARENA_DRAIN_CAP = 6          # exposed units counted toward the drain
ARENA_WILT_P = 0.05          # per crop per tick: ripe->crop, crop->tilled

# The hand's water & seeds (SPEC_HYDRO_HAND HH1-HH3): reuse the flood + crop
# systems; terraforming (dams/channels, read from column height) shapes it
WATER_RAIN_DUR = 30          # steps a gentle irrigation lasts
WATER_FLOOD_DUR = 60         # steps a keeper deluge lasts
WATER_RAIN_RADIUS = 5        # irrigation reach
WATER_FLOOD_RADIUS = 12      # deluge reach
WATER_TILL_P = 0.15          # per cell per tick: wet SAND -> TILLED
WATER_CROP_BOOST = 2         # extra crop growth-ticks per watered cell
WATER_FOOD_P = 0.02          # per cell per tick: fertile FOOD deposit
SEED_COUNT = 12              # crops sown per keeper_seed

# The Closed Biome & the Panel (SPEC_BIOME BI1-BI5): a global water budget and
# sunlight the keeper sets behind the glass; weather EMERGES from them
WATER_LEVEL_DEFAULT = 0.6    # free-water fraction 0..1 (default-neutral)

# Guppies (SPEC_GUPPIES): a consumer-resource pond in the oasis, seeded from world-gen.
# algae grows (sunlight/water) -> guppies eat + breed -> surplus becomes harvestable FOOD voxels.
GUPPIES_ENABLED = False      # module default False (battery byte-identical); entrypoint flips on (opt-out --no-guppies)
GUPPY_TICK = 20              # dynamics cadence (steps)
GUPPY_SEED = 40.0            # starting guppy stock (from the get go)
ALGAE_SEED = 60.0           # starting algae stock
GUPPY_CAP = 150.0           # guppy carrying capacity
ALGAE_CAP = 100.0           # algae carrying capacity
ALGAE_REGROW = 0.25         # algae regrowth fraction toward cap per tick (x water availability)
GUPPY_GRAZE = 0.10          # algae grazed per guppy per tick (x algae fraction)
GUPPY_BREED = 0.25          # max per-capita birth rate (x food fraction x room) — guppies mate when fed
GUPPY_DEATH = 0.05          # natural per-capita mortality per tick
GUPPY_YIELD_FRAC = 0.04     # fraction of the stock that surfaces as harvestable catch per tick
GUPPY_YIELD_MIN = 20.0      # no catch below this stock (let the shoal rebuild)
GUPPY_FOOD_CAP = 10         # max standing guppy-food voxels in the oasis (don't flood the tank)


def guppy_dynamics(guppy: float, algae: float, water: float, extra_food: float = 0.0):
    """Pure oasis-pond step (SPEC_GUPPIES / SPEC_FOOD_WEB): a consumer-resource model. Returns
    (guppy, algae, catch) for one GUPPY_TICK. Deterministic; bounded to [0, cap] by clamps.
    `water` (the closed-budget water_level) throttles algae growth so drought thins the pond.
    `extra_food` in [0,1] (Phase 2) is a diet supplement beyond algae — crickets washed into the water
    + crop droppings + in-water plant growth — so a cricket boom lifts the shoal. `catch` is the
    harvestable surplus (the sim turns it into FOOD voxels); the caller removes the deposited fish."""
    water = min(1.0, max(0.2, float(water)))
    algae = algae + ALGAE_REGROW * (ALGAE_CAP - algae) * water \
        - GUPPY_GRAZE * guppy * (algae / ALGAE_CAP)
    algae = min(ALGAE_CAP, max(0.0, algae))
    food_frac = min(1.0, algae / ALGAE_CAP + max(0.0, float(extra_food)))
    guppy = guppy + GUPPY_BREED * guppy * food_frac * (1.0 - guppy / GUPPY_CAP) \
        - GUPPY_DEATH * guppy
    guppy = min(GUPPY_CAP, max(0.0, guppy))
    catch = int(GUPPY_YIELD_FRAC * guppy) if guppy > GUPPY_YIELD_MIN else 0
    return guppy, algae, catch


# Crickets (SPEC_FOOD_WEB): a persistent LAND population — the terrestrial guppy-analog. Breed on plant
# matter, boom in the dry Dust season, drown in floods, die in the Chill frost; the surplus surfaces as
# harvestable land FOOD voxels (and a fraction feeds the guppies — Phase 2). The 2nd of three
# weather-rotated food guilds (aquatic guppies↑wet, terrestrial crickets↑dry, fauna-bounty↑dark).
CRICKETS_ENABLED = False     # module default False (battery byte-identical); entrypoint flips on (opt-out --no-crickets)
CRICKET_TICK = 20            # dynamics cadence (steps)
CRICKET_SEED = 30.0          # starting cricket stock
CRICKET_CAP = 120.0          # cricket carrying capacity
CRICKET_BREED = 0.28         # max per-capita birth rate (x forage x room)
CRICKET_DEATH = 0.06         # natural per-capita mortality per tick
CRICKET_DRY_BOOST = 1.6      # breeding multiplier when dry (Dust) — crickets love the dry heat
CRICKET_DROWN = 0.5          # fraction lost per tick during a flood (washed into the water)
CRICKET_FROST = 0.45         # fraction lost per tick in the Chill frost
CRICKET_YIELD_FRAC = 0.05    # fraction of the swarm that surfaces as harvestable catch per tick
CRICKET_YIELD_MIN = 15.0     # no catch below this stock (let the swarm rebuild)
CRICKET_FOOD_CAP = 12        # max cricket-food voxels deposited per tick (don't carpet the map)
# Phase 2 cross-couplings (the holistic web):
CRICKET_INFLUX = 0.08        # baseline fraction (normalized) of the swarm that washes into water -> guppy food
CRICKET_FLOOD_INFLUX = 0.30  # amplified during a flood — crickets swept in -> a guppy feast
CRICKET_CULL = 0.15          # fraction of the swarm culled per active cricket-predator beast per tick
CRICKET_PREDATORS = ('spider', 'small_spider', 'bird', 'scorpion', 'anteater')  # beasts that eat crickets
CRICKET_CROP_DMG = 4         # max crops a big swarm nibbles per tick (crickets are a pest)
GUPPY_DROPPINGS = 0.15       # max guppy diet-supplement from crop droppings (normalized)
# Snares (SPEC_FOOD_WEB Phase 3): string/toothpick set by the water — and spider WEB over water —
# passively catch guppies/crickets into FOOD (a weir; no foraging unit needed).
SNARES_ENABLED = False       # module default False (battery byte-identical); entrypoint flips on (opt-out --no-snares)
SNARE_TICK = 20              # snare-harvest cadence (steps)
SNARE_YIELD = 3              # guppies/crickets caught per snare per tick
SNARE_FOOD_CAP = 8           # max snare-food voxels deposited per tick
FORAGE_PREFER_DISCOUNT = 0.5  # the maw's forage-mode (directive d3) makes preferred food seem this-x closer


def cricket_dynamics(cricket: float, forage: float, dry: bool, flood: bool, frost: bool):
    """Pure land-swarm step (SPEC_FOOD_WEB): the terrestrial consumer-resource model. Returns
    (cricket, catch). `forage` in [0,1] is the standing plant matter the swarm breeds on (Phase 1: a
    fixed proxy; Phase 2: real crop density). Dry (Dust) boosts breeding; a flood drowns the swarm and
    the Chill frost kills it. Deterministic; bounded to [0, CRICKET_CAP]."""
    forage = min(1.0, max(0.0, float(forage)))
    breed = CRICKET_BREED * (CRICKET_DRY_BOOST if dry else 1.0)
    cricket = cricket + breed * cricket * forage * (1.0 - cricket / CRICKET_CAP) \
        - CRICKET_DEATH * cricket
    if flood:
        cricket -= CRICKET_DROWN * cricket
    if frost:
        cricket -= CRICKET_FROST * cricket
    cricket = min(CRICKET_CAP, max(0.0, cricket))
    catch = int(CRICKET_YIELD_FRAC * cricket) if cricket > CRICKET_YIELD_MIN else 0
    return cricket, catch


SUN_HOURS_DEFAULT = 12       # daylight hours/day
SUN_MIN, SUN_MAX = 4, 20     # panel sunlight range
BIOME_TICK = 20              # emergent-weather cadence
SUN_JITTER_SD = 0.0          # SP7: std-dev of per-day daylight draw (0 = identity; learnable)
SUN_OSC_AMP = 0.0            # SP10: daylight oscillator amplitude in hours (0 = identity; learnable) [prov:B fit=weather-variance]
SUN_OSC_PERIOD = 5 * BIOME_TICK  # SP10: period of the daylight swing (feel/pacing) [prov:C feel=season-length]
SUN_EMA_ALPHA = 0.25         # SP10: smoothing for the rolling mean/sdev observer [prov:A lit=EMA / Bollinger z-score normalization]
BIOME_EASE = 0.03            # water eases toward equilibrium per step
SUN_DRYING = 0.5             # how far sun lowers the water equilibrium
DRY_THRESHOLD = 0.35         # below this the biome is in drought
WET_THRESHOLD = 0.78         # above this the reservoir spills
SUN_COLD, SUN_HOT = 8, 16    # short days chill; long days bake
BIOME_FLOOD_CHANCE = 0.3     # per BIOME_TICK when wet
BIOME_HEAT_CHANCE = 0.4      # per BIOME_TICK when dry + hot
BIOME_COLD_CHANCE = 0.3      # per BIOME_TICK when days are short

# The Keeper constants (SPEC_KEEPER.md K1-K12)
KEEPER_DROP_FOOD = 6         # FOOD voxels per keeper hand-drop
KEEPER_MEMORY = 800          # steps of grace per witnessed miracle
KEEPER_WRATH_MOBILIZATION = 0.75  # war-chest gate multiplier when wrathful
CARVE_INTERVAL = 200         # steps between carvings (K4)
# Canon (SPEC_FACES): a colony carves its SENTIMENT toward the keeper - a
# readable fact that sours GRADUALLY, the early warning of rebellion
# ("look to your faces"). devout ♥ -> wary ◦ -> hateful ☠. 'machine' ⌂ is
# the terminal's own glyph (K10). (Not a literal portrait: the sandkings
# have no image of the keeper; the carving is a sentiment tell.)
CARVE_SYMBOLS = {'devout': '♥', 'wary': '◦', 'hateful': '☠', 'machine': '⌂'}
# AW2: pre-breach a colony carves the FORCES it feels, not a keeper's face -
# the sun, the sky, the storm. Awareness of the "great other" comes at breakout.
NATURE_SYMBOLS = {'bounty': '☀', 'lean': '☁', 'dread': '☈'}
SENTIMENT_SOUR = 0.06       # devotion lost per interval under cruelty (F1)
SENTIMENT_RECOVER = 0.05    # regained under reverence (souring is faster)
SENTIMENT_DRIFT = 0.02      # drift toward neutral 0.5 when the keeper is absent
KEEPER_CAT_STEP = 3200       # the cat gets in (auto script, K8)
KEEPER_GRIEF = 1200          # drought length after the cat is slain
KEEPER_GIFT_INTERVAL = 1600  # steps between ladder gifts (K9)
GIFT_LADDER = ('abacus', 'watch', 'calculator', 'pi')  # foreign tech (TE3)

# Disposition Arc constants (SPEC_DISPOSITION DP1-DP12): keeper treatment →
# confidence (material boldness), favoritism (treatment ledger), agitation (startle).
# Load-bearing invariant: every effect is identity at neutral defaults
# (confidence=0.5, favoritism=0.0, agitation=0.0).
CONF_RATE = 0.02            # inertia: fraction of (target − confidence) per tick
CONF_W_SURPLUS = 0.25       # weight of food surplus on confidence target
CONF_W_POP = 0.15           # weight of population surplus on confidence target
CONF_W_WIN = 0.15           # weight of a recent war victory on confidence target
CONF_W_FAV = 0.25           # weight of (signed) favoritism on confidence target
CONF_W_STARVE = 0.35        # penalty when starving (food < 2·BOOTSTRAP_FLOOR)
CONF_W_THREAT = 0.15        # penalty when at war or under acute weather
CONF_RICH_FOOD = WAR_CHEST   # food above which surplus registers (400)
CONF_POP_REF = 20            # population above which pop-surplus registers
CONF_WIN_WINDOW = 400        # steps a victory counts as "recent"
CONF_AGG_K = 0.8             # confidence→aggression gain: f(conf)=1+K·(conf−0.5)
AGIT_HOSTILITY = 0.3         # additive hostility term per unit agitation
AGIT_FREEZE = 0.5            # max mill probability at agitation 1.0 (DP4)
AGIT_SPIKE = 0.5             # agitation added per startling wrath verb (DP3)
AGIT_RETAIN = 0.7            # agitation multiplicative retention per tick (fast decay)
FAV_RETAIN = 0.995           # favoritism multiplicative retention per tick (slow decay)
FAV_MANNA = 0.15             # favoritism gained when the nearest colony is manna-fed
FAV_GIFT = 0.25              # favoritism gained by the colony that claims a gift
FAV_DROUGHT = 0.10           # favoritism lost (magnitude) per drought switch-on
FAV_WRATH = 0.20             # favoritism lost (magnitude) per wrath verb
BARGAIN_CONF_K = 0.5         # boldness gain on force EVs: 1+K·(conf−0.5)
CONF_FAV_BAND = 0.3          # (Fork #B, deferred) |favoritism| threshold for _nature_mood tilt

# Technology & Civilization data (SPEC_TECH TE1-TE13) lives in tech.py — the
# registry, acquisition/capability/siege constants, and the materials->crafting
# tables. Re-exported here so `from sandkings import TECH_REGISTRY` (etc.) still
# resolves; the sim-bound methods (_practice/_tech_tick/_catapult_tick/
# _plunder_techs/_barter_tech/keeper_material/_caltrop_tick) stay below on the sim.
from tech import (
    TECH_FOREIGN, TECH_NATIVE, TECH_REGISTRY,
    TECH_TICK, TECH_PRACTICE_XP, TECH_LEARN_XP, TECH_OBSERVE_RANGE,
    TECH_OBSERVE_XP, TECH_GRAIN_COST, TECH_GRAIN_XP,
    FARM_YIELD_BONUS, METAL_WEAPON_BONUS, METAL_PICK_BONUS,
    PLOW_COST_BONUS, MASON_WALL_BONUS,
    TECH_RESEARCH_XP, CATAPULT_RELOAD, CATAPULT_RANGE, CATAPULT_DAMAGE,
    CATAPULT_SPLASH, GUNPOWDER_ATTACK,
    MATERIALS, CRAFT_RECIPES, CRAFTED_EFFECTS,
    CALTROP_COUNT, CALTROP_DAMAGE,
    HYDRO_SOURCES_ENABLED, HYDRO_TICK, HYDRO_CAP, HYDRO_FLOW_RATE,
    HYDRO_SETTLE_MIN, HYDRO_SOURCE_LEVEL, HYDRO_EVAP_RATE, HYDRO_IRRIG_GROWTH,
    HYDRO_CHANNEL_LEN, HYDRO_RESERVOIR_RADIUS, HYDRO_RESERVOIR_DEPTH,
    HYDRO_RESERVOIR_ABSORB,
)
TERMINAL_UNLOCK = 40         # pi operate-ticks before the terminal (K10)
TERMINAL_MASTERY = 16        # successful commands before the breach
BREAKOUT_FITNESS_BONUS = 8.0 # [prov:C feel=breakout-pacing] tinker-fitness reward per cumulative terminal use; 0.0 = identity (pre-fix, no gradient); higher => sooner organic breach
TINKER_HYSTERESIS = 0.5      # [prov:A lit=Hysteretic Policy Optimization arXiv 2605.30201; hysteretic Q-learning, Matignon] hysteresis band width as a multiple of the running |u| scale; down-weight NEGATIVE keep/revert deltas so exploratory stepping-stones survive dips; 0.0 = identity (strict keep-if-improved)
SPOKEN_MEMORY = 50           # steps the `speak` anchor stays lit (K12)
CODEX_INTERVAL = 300         # steps between codex consultations (CX4)
AUG_MAX = 4                  # max memory-augment level (AUG2)
AUG_CACHE_STEP = 8           # cache_len added per augment level
MAW_RL_ENABLED = False       # 85% tier: maw real-RL directive (identity-at-neutral gate)
GRAIN_SCALE = 60.0           # forecast error normaliser (CU2)
GRAIN_MINT = 5.0             # grains for a perfect forecast

# Labor-Value & the Extractor's Surplus (SPEC_LABOR LV8): value-splitting spine
W_BRUTE = 0.0                # brute-mode share returned to the laborer's birth colony
W_FAIR = 0.5                 # neutral even-split anchor of w_bargain
W_POWER_SENS = 0.25          # w_bargain sensitivity to (power_ratio - 1)
W_DESPERATION_SENS = 0.25    # w_bargain sensitivity to extractor desperation
W_CONTROL_SENS = 0.25        # w_bargain sensitivity to extractor scarce-factor control
POWER_WEALTH_FOOD = 1.0      # composite_power weight on stored food
POWER_MILITARY_UNIT = 15.0   # weight per living unit
POWER_MAW_HEALTH = 0.2       # weight on maw health
POWER_ORE_COPPER = 25.0      # weight per copper ore
POWER_ORE_GOLD = 10.0        # weight per gold ore
POWER_CURRENCY = 1.0         # weight on grains held
POWER_WOOD = 1.0             # weight per wood unit
POWER_TECH_NATIVE = 8.0      # weight per known NATIVE tech
POWER_TECH_FOREIGN = 30.0    # weight per known FOREIGN (keeper-gift) tech

# Subjugation: Capture, Coercion & Conversion (SPEC_SUBJUGATION SJ8)
CAPTURE_CHANCE = 0.0          # probability a dominant captor takes a broken enemy alive
CAPTURE_HEALTH = 3            # health a captured thrall is revived to
CAPTURE_CENTER = 0.5         # SP9: power_ratio at which the soft capture gate is a coin-flip [prov:B fit=capture-liveness]
CAPTURE_TEMP = 0.0           # SP9: capture-gate softness; 0.0 = identity (exact flat coin-flip) [prov:B fit=capture-liveness]
GUARD_RADIUS = 6              # Chebyshev range within which a captor soldier keeps a thrall docile
DEFIANCE_RISE = 0.05          # defiance gained per tick while unguarded
DEFIANCE_CALM = 0.10          # defiance shed per tick while guarded
DEFIANCE_MAW_ACCEL = 1.0      # multiplier on defiance rise at the birth maw
DEFIANCE_ACTIVE = 0.5         # defiance at which coercion, refusal, and strikes begin
DEFIANCE_THRESHOLD = 1.0      # defiance at which the thrall breaks free
COERCION_DAMAGE = 2           # threat-of-harm damage a captor soldier deals a defiant thrall per tick
STRIKE_CHANCE = 0.1           # probability a defiant thrall strikes its guard back
# Runtime enable (the `--subjugation` flag): the default CAPTURE_CHANCE stays 0.0
# so the regression battery is byte-identical; the live launcher bumps the module
# global to this and turns on the war-driven stance below. This is a temporary
# stand-in for the M4 bargain layer, which will drive stance properly.
SUBJUGATION_LIVE_CHANCE = 0.4  # capture probability when --subjugation is on

# Wages & the Factor Market (SPEC_WAGES WG1-WG12): peace-tier extraction via labor, tech, and goods
WAGE_ENABLED = False              # master gate; False => _labor_market_tick early-returns, byte-identical (WG12)
RENEGOTIATE_INTERVAL = 200        # ticks between sticky w/fee renegotiations (WG9/F1)
SETTLEMENT_INTERVAL = 50          # ticks between grain settlements + goods shipments (WG8)
COMPLEMENTARITY_THRESHOLD = 0.30  # min (surplus-deficit)/(sum) on a factor axis to open a contract (WG2/WG4)
W_CONTRACT_MIN = 0.05             # floor/ceiling clamp on labor w (keeps it voluntary and >0, thrall-distinct) (WG3a)
LICENSE_FEE_BASE = 2.0            # base grain rent per licensed foreign gift per settlement interval (WG3b)
LICENSE_TECH_MULT = {
    'abacus': 1.05,
    'watch': 1.10,
    'calculator': 1.20,
    'pi': 1.40
}                                 # per-gift labor-yield multiplier granted to the renter (WG6)
WAGE_GRAIN_RATE = 0.5             # fraction of marginal-value price paid as labor grain rent (WG3b)
WAGE_POWER_SHARE_BASE = 0.5       # baseline split of trade surplus (even) (WG3b)
WAGE_POWER_SHARE_SENS = 0.25      # how much relative power tilts the surplus split (WG3b)
MV_BASE = 10.0                    # marginal-value numerator (MV = MV_BASE/(1+endowment)) (WG2)
DESPERATION_LABOR_REF = 8.0       # buyer free-unit count that saturates labor-desperation to 0 (WG3a)
CONTROL_TECH_REF = 2.0            # buyer foreign-gift count that saturates scarce-factor control to 1 (WG3a)
LABOR_MAX_UNITS = 4               # max seller units bound per labor contract (WG5)
GOODS_VOLUME_CAP = 5              # max goods units shipped per settlement interval (WG3b)
NONVIABLE_LIMIT = 3               # consecutive non-viable settlements before contract closes (WG10)
EPS_POWER = 1e-9                  # denominator guard for composite_power ratios (WG2/WG3)
ECON_GRAIN_FLOOR = 60.0           # WG13 liquidity floor: min grains a living colony is topped up
                                  # to each settlement interval when the market is ON. Grains
                                  # otherwise mint only from (weak) forecast accuracy, so without a
                                  # floor the market has no money to transact. Gated by WAGE_ENABLED
                                  # (only reached inside _labor_market_tick), so default-neutral.

# The Bargain: Mode Selection by Net Extraction (SPEC_BARGAIN BG1-BG12)
# Mode enum (BG1): string constants, pickle-trivial, log-readable
BARGAIN_MODE_NONE       = 'none'         # no arrangement worth making (peace, no contract)
BARGAIN_MODE_WAGE       = 'wage'         # peace: M3 opens contracts for this pair
BARGAIN_MODE_SUBJUGATE  = 'subjugate'    # war: M2 captures for this pair
BARGAIN_MODE_ANNIHILATE = 'annihilate'   # war: normal combat, value destroyed
# Constants (BG8)
BARGAIN_ENABLED = False               # master gate; False ⇒ byte-identical battery (BGA-1)
BARGAIN_CAPTURE_CHANCE = 0.4          # live CAPTURE_CHANCE the --bargain switch sets
BARGAIN_V_EST = 10.0                  # estimated labor-value per free unit per horizon
BARGAIN_WAGE_RELIABILITY = 1.0        # fraction of wage output realised (peacetime)
BARGAIN_BRUTE_RELIABILITY = 0.45      # fraction captured after defiance leak (must stay < (1-W_FAIR))
BARGAIN_ENFORCE_COST = 2.0            # value spent guarding each thrall per horizon
BARGAIN_WAR_LOSS = 30.0               # expected attrition to enter/prosecute war from peace
BARGAIN_DESTROY_WEIGHT = 0.15         # fraction of rival's composite_power valued by annihilating
BARGAIN_DOMINANCE_MIN = 1.1           # min composite_power ratio for brute capture feasibility
BARGAIN_DOMINANCE_SCALE = 1.0         # how fast capturable pool grows with dominance past 1.0
BARGAIN_TRUST_REF = 100.0             # negative-trust magnitude that saturates hatred to 1.0
BARGAIN_GRUDGE_FEUD_W = 0.6           # weight of blood-feud presence in grudge score
BARGAIN_GRUDGE_TRUST_W = 0.6          # weight of negative diplomatic trust in grudge score
BARGAIN_GRUDGE_SENS = 1.2             # how hard grudge collapses the wage trust-factor
BARGAIN_TEMP = 0.0                    # SP11: softmax temperature over the three bargain EVs (0 = identity/hard argmax; >0 = tempered stochastic choice; learnable)

# Metamorphosis (SPEC_METAMORPHOSIS MT1-MT4): the maw grows into a new breed
MOLT_POP = 26                # population that triggers the stage-2 molt
MOLT_FOOD = 420              # or this much hoarded food
MOLT_AGE = 2400              # or this many steps of age
SHADE_POP = 34               # stage-3 (Shade) size gate...
SHADE_FOOD = 620             # ...or hoard
STAGE_CEILING = {1: 88, 2: 128, 3: 160}  # brain_hidden cap by stage (MT4)

# Enlightenment (SPEC_ENLIGHTENMENT EN1-EN10): post-escape intelligence leap
ENLIGHTENED_CEILING = 224      # brain_hidden ceiling granted at ascension; strictly above STAGE_CEILING[3]
ENLIGHTENED_TECH_MULT = 5.0    # multiplier on every tech-xp gain while enlightened
ENLIGHTENED_CODEX_MULT = 5.0   # multiplier on every codex lesson-nudge while enlightened

# The Psionic Maw & Keeper-as-Prey (SPEC_PSIONIC PS1-PS5): the awakened
# terrarium reaches back, and at the last it turns on its god
PSIONIC_MIN_STAGE = 2        # only the awakened (stage 2+) project (PS1)
STAGE_PROJECTION = {2: 0.5, 3: 1.0}  # psionic reach by stage (size<->power)
PSIONIC_SIZE_REF = 30        # population that saturates a colony's projection
PSIONIC_FLOOR = 0.15         # |influence| below this reads/does nothing (PS2)
PSIONIC_DREAD = -0.5         # dread at/below which the auto-keeper turns cruel
PSIONIC_TURN_SENT = 0.2      # a Shade this hateful binds the keeper (PS4)

FAUNA_SPAWN_P = 0.3          # incursion chance per MARAUDER_INTERVAL roll...
FAUNA_SPAWN_P_DARK = 0.6     # ...doubled in Dust/Chill (monsters own winter)


def _tinker_keep(u: float, baseline: float, scale: float, hysteresis: float) -> bool:
    """Part E (HPO): keep-if-improved with a hysteretic hold on small dips.
    margin = u - baseline; band = hysteresis * scale; keep iff margin >= -band.
    At hysteresis==0.0 -> band 0 -> exact strict `u >= baseline` (identity)."""
    margin = u - baseline
    band = hysteresis * scale
    return margin >= -band


def breakout_progress(colony) -> Tuple[str, float, str]:
    """BRK-B: how close a colony is to breakout. Pure, no pygame.

    Returns (phase, fraction, label):
      phase in {"breached","mastering","unlocking","nopi"}
      fraction in [0.0, 1.0]  (breach_proximity)
      label: renderer-agnostic annotation (NO bar glyphs; the HUD adds
             the hp_bar). Deterministic; no RNG.

    Preconditions: colony may lack any of breached/controllers/
      terminal_uses (all read via getattr with defaults) — a bare or
      revived colony is valid input.
    """
    from machines import VM_FUEL
    if getattr(colony, 'breached', False):
        return ("breached", 1.0, "BREACHED")
    controllers = getattr(colony, 'controllers', None) or []
    pi_ticks = [getattr(c, 'operate_ticks', 0) for c in controllers
                if getattr(c, 'fuel_cap', VM_FUEL) > VM_FUEL]
    if not pi_ticks:
        return ("nopi", 0.0, "no pi")
    max_ticks = max(pi_ticks)
    if max_ticks < TERMINAL_UNLOCK:
        frac = max(0.0, min(1.0, max_ticks / TERMINAL_UNLOCK))
        return ("unlocking", frac, "unlock")
    uses = int(getattr(colony, 'terminal_uses', 0))
    frac = max(0.0, min(1.0, uses / TERMINAL_MASTERY))
    return ("mastering", frac, f"breach {uses}/{TERMINAL_MASTERY}")


class VoxelType(Enum):
    AIR = 0
    SAND = 1           # Tunnelable, movable
    STONE = 2          # Immovable substrate
    GLASS = 3          # Terrarium walls
    FOOD = 4           # Resource nodes
    CORPSE = 5         # Dead units = food
    TUNNEL_WALL = 6    # Reinforced colony walls
    TILLED = 7         # Worked soil, plantable (T19)
    CROP = 8           # Growing plant - not food to anyone
    CROP_RIPE = 9      # Harvestable - food to everyone
    COPPER_ORE = 10    # Vein ore in strata stone (T23)
    GOLD_ORE = 11      # Deep cluster ore, non-renewable
    HULL = 12          # Crashed wreck shell (T28)
    SALVAGE = 13       # Wreck components - minable, non-renewable
    WOOD = 14          # Palm/scrub trunk - choppable, flammable (T41)
    WOOD_WALL = 15     # Palisade - rots, burns; the poor colony's wall (T43)
    WEB = 16           # Spider silk - snares a step, burns (T48)
    CASTLE = 17        # Stone castle crenellation - a prosperous house's monument (K5)
    WATER = 18         # Standing water - the flow-sim's rendered surface (HYDRO). A
    #                    depth field is the source of truth; this voxel mirrors cells at
    #                    depth >= HYDRO_SETTLE_MIN. Non-solid + non-tunnelable, so it
    #                    blocks gravity, tunnel(), and walking (boats cross it).

    def is_tunnelable(self):
        return self in (VoxelType.SAND, VoxelType.AIR)

    def is_solid(self):
        return self in (VoxelType.STONE, VoxelType.GLASS, VoxelType.TUNNEL_WALL,
                        VoxelType.COPPER_ORE, VoxelType.GOLD_ORE,
                        VoxelType.HULL, VoxelType.SALVAGE, VoxelType.WOOD,
                        VoxelType.WOOD_WALL, VoxelType.CASTLE)

def box_blur(field: np.ndarray, passes: int = 2) -> np.ndarray:
    """Neighbor-mean smoothing via np.roll (wraps at edges); 2D or 3D fields."""
    for _ in range(passes):
        acc = field.copy()
        count = 1
        for axis in range(field.ndim):
            acc = acc + np.roll(field, 1, axis) + np.roll(field, -1, axis)
            count += 2
        field = acc / count
    return field


def value_noise(shape: Tuple[int, ...], cells: int, rng: np.random.Generator,
                octaves: int = 3) -> np.ndarray:
    """Multi-octave value noise in [0, 1] for a 2D or 3D shape (numpy only).

    Each octave draws a coarse random grid (cells * 2^octave per axis,
    capped at the axis size), upsamples by repetition, box-blurs, and sums
    with halving amplitude.
    """
    total = np.zeros(shape, dtype=np.float32)
    amplitude, total_amp = 1.0, 0.0
    for octave in range(octaves):
        coarse_shape = [max(1, min(s, cells * (2 ** octave))) for s in shape]
        coarse = rng.random(coarse_shape).astype(np.float32)
        fine = coarse
        for axis, (s, cs) in enumerate(zip(shape, coarse_shape)):
            fine = np.repeat(fine, -(-s // cs), axis=axis)
        fine = box_blur(fine[tuple(slice(0, s) for s in shape)], passes=2)
        total += amplitude * fine
        total_amp += amplitude
        amplitude *= 0.5
    total /= total_amp
    tmin, tmax = float(total.min()), float(total.max())
    if tmax > tmin:
        total = (total - tmin) / (tmax - tmin)
    return total


def composite_power(colony) -> float:
    """Composite capability index: military + wealth + scarce technology.
    Pure read of colony fields; getattr-guarded for pre-feature pickles.
    Reused by M2 dominance (SJ2) and by w_bargain (LV3).
    """
    ore = getattr(colony, 'ore', {}) or {}
    techs = getattr(colony, 'techs', set()) or set()
    foreign = sum(1 for t in techs if t in TECH_FOREIGN)      # keeper gifts, scarce
    native = len(techs) - foreign
    return (POWER_WEALTH_FOOD * colony.maw.food_stored
            + POWER_MILITARY_UNIT * len(colony.units)
            + POWER_MAW_HEALTH * colony.maw.health
            + POWER_ORE_COPPER * ore.get('copper', 0)
            + POWER_ORE_GOLD * ore.get('gold', 0)
            + POWER_CURRENCY * getattr(colony, 'currency', 0.0)
            + POWER_WOOD * getattr(colony, 'wood', 0)
            + POWER_TECH_NATIVE * native
            + POWER_TECH_FOREIGN * foreign)


def w_bargain(power_ratio: float = 1.0,
              desperation: float = 0.0,
              control: float = 0.0) -> float:
    """The share `w` returned to the laborer's birth colony under NEGOTIATED
    (non-brute) extraction. Pure; no side effects; deterministic.

    power_ratio = composite_power(birth_colony) / composite_power(extractor)
                  (> 1 => the laborer's house is the stronger, keeps more).
    desperation = extractor's need in [0,1] (higher => concedes a bigger w).
    control     = extractor's grip on a scarce factor in [0,1]
                  (higher => extracts more, smaller w).

    Returns w clamped to [0,1]. Neutral anchor: w_bargain() == W_FAIR (an even
    split) — balanced power, no desperation, no scarce-factor control. Sticky w
    with periodic renegotiation is M3's cadence; this fn only maps state -> w.
    """
    w = (W_FAIR
         + W_POWER_SENS * (power_ratio - 1.0)
         + W_DESPERATION_SENS * desperation
         - W_CONTROL_SENS * control)
    return max(0.0, min(1.0, w))


def _clamp01(x: float) -> float:
    """Clamp x to [0, 1]. Pure helper for WG2/WG3 (WG12)."""
    return max(0.0, min(1.0, x))


def jitter(mean: float, sd: float = 0.0,
           lo: float = float('-inf'), hi: float = float('inf'),
           rng=random) -> float:
    """FORM 1 — distributional scalar: draw X ~ N(mean, sd), clipped to [lo, hi].

    Precondition:  rng provides .gauss(mu, sigma) (module `random` or a
                   random.Random instance — the SEEDED stream, never default_rng).
    Failure modes: none raised; sd<=0 short-circuits, lo>hi would clamp to hi.
    IDENTITY:      sd <= 0.0 returns float(mean) and DRAWS NOTHING (no rng call),
                   so the shared RNG stream is unperturbed (canon stays in sync).
    """
    if sd <= 0.0:
        return float(mean)                      # identity — NO draw consumed
    x = rng.gauss(mean, sd)                      # single draw from the seeded stream
    return float(min(max(x, lo), hi))            # clip to [lo, hi]


def soft_gate(metric: float, center: float, temp: float) -> float:
    """FORM 2 — soft gate: P(act) = logistic((metric - center) / temp), in [0,1].

    The CALLER draws rng.random() < P(act); this function is pure (no RNG here).
    Failure modes: none raised; overflow-safe logistic (branch on sign of z).
    IDENTITY:      temp <= 0.0 collapses to the hard step 1.0 if metric > center
                   else 0.0 — byte-for-byte the pre-existing `if metric > C` gate.
    """
    if temp <= 0.0:
        return 1.0 if metric > center else 0.0   # identity — hard threshold at center
    z = (metric - center) / temp
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def power_ratio(enforcers: int, defenders: int) -> float:
    """SP9: local numerical superiority in [0,1]. 1.0 = uncontested (no defenders),
    0.5 = even, 0.0 = no captor present. Pure, no RNG."""
    total = enforcers + defenders
    if total <= 0:
        return 0.0
    return enforcers / total


@dataclass
class DistParam:
    """Learnable holder for a FORM-1 distributional scalar. Swap for an evolved
    instance to make the scalar adaptive; default (sd=0) is identity."""
    mean: float
    sd: float = 0.0
    lo: float = float('-inf')
    hi: float = float('inf')
    def draw(self, rng=random) -> float:
        return jitter(self.mean, self.sd, self.lo, self.hi, rng)

@dataclass
class GateParam:
    """Learnable holder for a FORM-2 soft gate. Swap for an evolved instance to
    make the threshold adaptive; default (temp=0) is a hard step at center."""
    center: float
    temp: float = 0.0
    def prob(self, metric: float) -> float:
        return soft_gate(metric, self.center, self.temp)


class VoxelWorld:
    """800x400x200 3D voxel terrarium with physics"""

    def __init__(self, width=80, height=40, depth=20, seed: Optional[int] = None):
        self.dimensions = (width, height, depth)
        self.width, self.height, self.depth = width, height, depth
        # seed=None derives from the global NumPy stream so np.random.seed()
        # in tests makes terrain reproducible; unseeded runs stay random
        if seed is None:
            seed = int(np.random.randint(0, 2**31))
        self.rng = np.random.default_rng(seed)

        # Core voxel data
        self.voxels = np.full(self.dimensions, VoxelType.AIR.value, dtype=np.uint8)
        self.ownership = np.full(self.dimensions, -1, dtype=np.int8)  # -1 = unowned
        self.stability = np.ones(self.dimensions, dtype=np.float32)

        # Initialize terrain
        self._generate_terrain()
    
    def _generate_terrain(self):
        """DF-style strata terrain: dune heightmap, stone bands, caverns, food.

        Spec: SPEC_TERRARIUM_LIVENESS.md T8. Guarantees: glass shell intact,
        surface heights in [substrate+2, 0.85*depth], cavern roofs cemented
        to STONE, world gravity-settled on return (apply_gravity is a no-op).
        Degrades at depth < 8 (caverns skipped, bands clamped).
        """
        w, h, d = self.dimensions
        rng = self.rng
        zs = np.arange(d)[None, None, :]

        # Stone substrate (bottom 20%)
        substrate_height = d // 5
        self.voxels[:, :, :substrate_height] = VoxelType.STONE.value

        # Dune heightmap: per-column surface height from 3-octave value noise
        h_min = substrate_height + 2
        h_max = max(h_min + 1, int(d * 0.85))
        heightmap = value_noise((w, h), cells=6, rng=rng)
        surface = (h_min + heightmap * (h_max - h_min)).astype(int)

        # Fill sand up to each column's surface
        sand_mask = (zs >= substrate_height) & (zs < surface[:, :, None])
        self.voxels[sand_mask] = VoxelType.SAND.value

        # Stone strata: two noise-thresholded bands, thickness 2
        for band_base in (substrate_height + 2, int(d * 0.45)):
            band_mask = value_noise((w, h), cells=8, rng=rng) > 0.55
            for z in range(band_base, min(band_base + 2, d)):
                layer = self.voxels[:, :, z]
                layer[band_mask & (layer == VoxelType.SAND.value)] = VoxelType.STONE.value

        # Caverns: 3D-noise air pockets inside the sand body, roofs cemented
        # so gravity cannot collapse them column by column
        if d >= 8:
            cave_noise = value_noise((w, h, d), cells=5, rng=rng)
            depth_ok = (zs >= substrate_height + 1) & (zs < np.maximum(surface[:, :, None] - 3, 0))
            cavern = ((cave_noise > np.quantile(cave_noise, 0.92)) & depth_ok &
                      (self.voxels == VoxelType.SAND.value))
            self.voxels[cavern] = VoxelType.AIR.value
            above_cavern = np.roll(cavern, 1, axis=2)
            above_cavern[:, :, 0] = False
            roof = above_cavern & (self.voxels == VoxelType.SAND.value)
            self.voxels[roof] = VoxelType.STONE.value

        # Ore (T23): copper veins threaded through the strata bands, gold
        # clusters at the substrate top. Hosted in STONE only; every vein
        # face touches diggable sand, so mining exposes the next voxel
        if d >= 8:
            for band_base in (substrate_height + 2, int(d * 0.45)):
                band_top = min(band_base + 2, d)
                for _ in range(COPPER_VEINS_PER_BAND):
                    vx = int(rng.integers(2, w - 2))
                    vy = int(rng.integers(2, h - 2))
                    for _ in range(int(rng.integers(8, 17))):
                        vz = int(rng.integers(band_base, band_top))
                        if self.voxels[vx, vy, vz] == VoxelType.STONE.value:
                            self.voxels[vx, vy, vz] = VoxelType.COPPER_ORE.value
                        vx = int(np.clip(vx + rng.integers(-1, 2), 2, w - 3))
                        vy = int(np.clip(vy + rng.integers(-1, 2), 2, h - 3))
            for _ in range(GOLD_CLUSTERS):
                gx = int(rng.integers(2, w - 2))
                gy = int(rng.integers(2, h - 2))
                for _ in range(int(rng.integers(3, 7))):
                    gz = int(rng.integers(max(1, substrate_height - 2), substrate_height))
                    if self.voxels[gx, gy, gz] == VoxelType.STONE.value:
                        self.voxels[gx, gy, gz] = VoxelType.GOLD_ORE.value
                    gx = int(np.clip(gx + rng.integers(-1, 2), 2, w - 3))
                    gy = int(np.clip(gy + rng.integers(-1, 2), 2, h - 3))

        # The crashed wreck (T28): one per world, buried in a random
        # quadrant away from the oasis; salvage on side walls/floor only
        # so the sealed roof survives gravity
        self.wreck = None
        if d >= 12:
            cx, cy = w // 2, h // 2
            for _ in range(60):
                wx = int(rng.integers(8, w - 13))
                wy = int(rng.integers(8, h - 13))
                if (wx + 2 - cx) ** 2 + (wy + 2 - cy) ** 2 >= (OASIS_RADIUS + 6) ** 2:
                    break
            z0 = substrate_height + 1
            x1, y1, z1 = wx + 5, wy + 5, z0 + 3
            self.voxels[wx:x1, wy:y1, z0:z1] = VoxelType.HULL.value
            self.voxels[wx + 1:x1 - 1, wy + 1:y1 - 1, z0 + 1] = VoxelType.AIR.value
            shell = [(x, y, z) for x in range(wx, x1) for y in range(wy, y1)
                     for z in range(z0, z1)
                     if self.voxels[x, y, z] == VoxelType.HULL.value
                     and z != z1 - 1]  # never the roof
            rng.shuffle(shell)
            interior_side = [(x, y, z) for (x, y, z) in shell if z == z0 + 1]
            target = int(rng.integers(8, 13))
            # interior-level cells first (>= 2 guarantee a crawl-hole),
            # deduped against the rest of the shuffled shell
            picks = list(dict.fromkeys(interior_side[:2] + shell))[:target]
            for pos in picks:
                self.voxels[pos] = VoxelType.SALVAGE.value
            # bury it: a suspicious regular mound
            for x in range(wx, x1):
                for y in range(wy, y1):
                    for z in range(z1, min(z1 + 2, d)):
                        if self.voxels[x, y, z] == VoxelType.AIR.value:
                            self.voxels[x, y, z] = VoxelType.SAND.value
            self.wreck = {'min': (wx, wy, z0), 'max': (x1 - 1, y1 - 1, z1 - 1),
                          'controller_pos': (wx + 2, wy + 2, z0 + 1)}

        # Glass walls + floor (applied last so they always win)
        self.voxels[0, :, :] = VoxelType.GLASS.value
        self.voxels[-1, :, :] = VoxelType.GLASS.value
        self.voxels[:, 0, :] = VoxelType.GLASS.value
        self.voxels[:, -1, :] = VoxelType.GLASS.value
        self.voxels[:, :, 0] = VoxelType.GLASS.value

        # Trees (T41): palm clusters near the oasis, scattered scrub.
        # Shallow test worlds stay sterile (mirrors the ore/cavern gate).
        cx2, cy2 = w // 2, h // 2
        for cluster in range(5 if d >= 8 else 0):
            if cluster < 3:  # oasis ring
                angle = rng.random() * 2 * np.pi
                r = 4 + rng.random() * 5
                tx = int(np.clip(cx2 + r * np.cos(angle), 2, w - 3))
                ty = int(np.clip(cy2 + r * np.sin(angle), 2, h - 3))
            else:            # scrub
                tx = int(rng.integers(2, w - 2))
                ty = int(rng.integers(2, h - 2))
            for _ in range(int(rng.integers(2, 5))):
                px = int(np.clip(tx + rng.integers(-2, 3), 2, w - 3))
                py = int(np.clip(ty + rng.integers(-2, 3), 2, h - 3))
                pz = self.surface_z(px, py) + 1
                if pz < d and self.voxels[px, py, pz] == VoxelType.AIR.value:
                    self.voxels[px, py, pz] = VoxelType.WOOD.value

        # Surface food patches
        for _ in range(4):
            px, py = int(rng.integers(2, w - 2)), int(rng.integers(2, h - 2))
            for _ in range(int(rng.integers(4, 7))):
                fx = int(np.clip(px + rng.integers(-3, 4), 1, w - 2))
                fy = int(np.clip(py + rng.integers(-3, 4), 1, h - 2))
                fz = self.surface_z(fx, fy) + 1
                if fz < d and self.voxels[fx, fy, fz] == VoxelType.AIR.value:
                    self.voxels[fx, fy, fz] = VoxelType.FOOD.value

        # Buried food pockets
        for _ in range((w * h) // 400):
            fx, fy = int(rng.integers(1, w - 1)), int(rng.integers(1, h - 1))
            top = self.surface_z(fx, fy)
            if top > substrate_height + 1:
                fz = int(rng.integers(substrate_height + 1, top))
                for _ in range(int(rng.integers(1, 4))):
                    bx = int(np.clip(fx + rng.integers(-1, 2), 1, w - 2))
                    by = int(np.clip(fy + rng.integers(-1, 2), 1, h - 2))
                    if self.voxels[bx, by, fz] == VoxelType.SAND.value:
                        self.voxels[bx, by, fz] = VoxelType.FOOD.value

        # Settle any loose sand so post-gen gravity is a no-op
        for _ in range(3):
            self.apply_gravity()

    def surface_z(self, x: int, y: int) -> int:
        """Highest non-AIR z in a column (glass floor guarantees >= 0)."""
        nonair = np.nonzero(self.voxels[x, y, :] != VoxelType.AIR.value)[0]
        return int(nonair[-1]) if len(nonair) else 0

    def terrain_z(self, x: int, y: int) -> int:
        """Highest non-AIR, non-WATER z in a column — the solid ground height,
        ignoring standing water (HYDRO). Equals surface_z when there is no water;
        used where a query means 'the land' (crop burial, the flood dam rule)."""
        col = self.voxels[x, y, :]
        ground = np.nonzero((col != VoxelType.AIR.value)
                            & (col != VoxelType.WATER.value))[0]
        return int(ground[-1]) if len(ground) else 0

    def in_bounds(self, x, y, z):
        """Check if coordinates are within world bounds"""
        return (0 <= x < self.width and 
                0 <= y < self.height and 
                0 <= z < self.depth)
    
    def get_voxel(self, x, y, z):
        """Get voxel type at position"""
        if self.in_bounds(x, y, z):
            return VoxelType(self.voxels[x, y, z])
        return VoxelType.GLASS  # Out of bounds = wall
    
    def set_voxel(self, x, y, z, voxel_type: VoxelType, colony_id=-1):
        """Set voxel type and ownership"""
        if self.in_bounds(x, y, z):
            self.voxels[x, y, z] = voxel_type.value
            if colony_id >= 0:
                self.ownership[x, y, z] = colony_id
    
    def apply_gravity(self):
        """Sand falls into empty spaces below"""
        # Process from bottom up to avoid cascading issues
        for z in range(1, self.depth):
            sand_mask = self.voxels[:, :, z] == VoxelType.SAND.value
            air_below = self.voxels[:, :, z-1] == VoxelType.AIR.value
            falling = sand_mask & air_below
            
            # Move sand down
            if np.any(falling):
                self.voxels[:, :, z-1][falling] = VoxelType.SAND.value
                self.voxels[:, :, z][falling] = VoxelType.AIR.value
                # Preserve ownership through fall
                self.ownership[:, :, z-1][falling] = self.ownership[:, :, z][falling]
                self.ownership[:, :, z][falling] = -1
    
    def tunnel(self, position: Tuple[int, int, int], direction: Tuple[int, int, int], colony_id: int):
        """Excavate sand, creating tunnel"""
        x, y, z = position
        dx, dy, dz = direction
        target_x, target_y, target_z = x + dx, y + dy, z + dz
        
        if not self.in_bounds(target_x, target_y, target_z):
            return False
        
        target_type = VoxelType(self.voxels[target_x, target_y, target_z])
        
        if target_type == VoxelType.SAND:
            self.voxels[target_x, target_y, target_z] = VoxelType.AIR.value
            self.ownership[target_x, target_y, target_z] = colony_id
            return True
        elif target_type == VoxelType.AIR:
            self.ownership[target_x, target_y, target_z] = colony_id
            return True
        
        return False
    
    def fortify(self, position: Tuple[int, int, int], colony_id: int):
        """Convert sand to reinforced tunnel wall"""
        x, y, z = position
        if self.in_bounds(x, y, z):
            if self.voxels[x, y, z] == VoxelType.SAND.value:
                self.voxels[x, y, z] = VoxelType.TUNNEL_WALL.value
                self.ownership[x, y, z] = colony_id
                return True
        return False
    
    def get_neighbors_3d(self, pos: Tuple[int, int, int], radius: int = 1):
        """Get 3D neighbors (26 for radius=1)"""
        x, y, z = pos
        neighbors = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if dx == dy == dz == 0:
                        continue
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if self.in_bounds(nx, ny, nz):
                        neighbors.append((nx, ny, nz))
        return neighbors

# ============================================================================
# COLONY GENOME & EVOLUTION
# ============================================================================

@dataclass
class ColonyGenome:
    """Evolvable traits for Sand King colonies"""
    aggression: float = 0.5        # 0=passive, 1=aggressive
    tunnel_preference: float = 0.5  # 0=surface, 1=deep
    expansion_rate: float = 0.5    # Resource-to-spawn ratio
    defense_investment: float = 0.5 # Wall-building priority
    foraging_range: int = 10       # Max distance to seek food
    swarm_threshold: int = 20      # Population for swarming behavior
    fertility: float = 0.5         # Spawn rate modifier
    resilience: float = 0.5        # Damage resistance
    patience: float = 0.5          # TD discount gamma - evolvable temperament (T26)
    loyalty: float = 0.5           # hawk-dove axis: honors commitments (P11)
    plasticity: float = 0.5        # learning-to-learn rate scaler (S3)
    brain_hidden: int = 64         # evolvable n_nodes per hidden layer (EV1)
    brain_depth: int = 1           # evolvable n_layers of the encoder (EV1)
    brain_ceiling: int = 88        # metamorphosis stage cap on width (MT4)

    # Neural hive mind (Maw brain)
    brain: Optional[HiveMindBrain] = None
    use_neural: bool = False       # Toggle neural vs rule-based AI

    def mutate(self, mutation_rate: float = 0.1):
        """Gaussian mutation of genome parameters"""
        mutated = ColonyGenome()
        mutated.use_neural = self.use_neural

        for attr in ['aggression', 'tunnel_preference', 'expansion_rate',
                     'defense_investment', 'fertility', 'resilience', 'patience',
                     'loyalty', 'plasticity']:
            current = getattr(self, attr, 0.5)  # pre-trait checkpoints
            noise = np.random.normal(0, mutation_rate)
            setattr(mutated, attr, np.clip(current + noise, 0.0, 1.0))

        mutated.foraging_range = max(5, int(self.foraging_range + np.random.normal(0, 2)))
        mutated.swarm_threshold = max(10, int(self.swarm_threshold + np.random.normal(0, 5)))

        # Evolvable brain architecture (EV1): n_nodes and n_layers drift
        from neuroevolution import (BRAIN_DEPTH_MAX, BRAIN_HIDDEN_MAX,
                                    BRAIN_HIDDEN_MIN)
        hid = getattr(self, 'brain_hidden', 64)
        dep = getattr(self, 'brain_depth', 1)
        if np.random.random() < mutation_rate * 3:  # width drifts by +-8
            hid += int(np.random.choice([-8, 8]))
        if np.random.random() < mutation_rate:      # depth drifts rarely
            dep += int(np.random.choice([-1, 1]))
        # MT4: the metamorphosis stage caps how wide the brain may grow
        ceiling = int(getattr(self, 'brain_ceiling', 88))
        mutated.brain_ceiling = ceiling
        mutated.brain_hidden = int(np.clip(hid, BRAIN_HIDDEN_MIN,
                                           min(BRAIN_HIDDEN_MAX, ceiling)))
        mutated.brain_depth = int(np.clip(dep, 1, BRAIN_DEPTH_MAX))

        # Neural brain mutation (slow - only when Maw survives). If the
        # architecture changed, rebuild+graft; else deep-copy and jitter.
        if self.use_neural and self.brain is not None:
            same_arch = (mutated.brain_hidden == getattr(self, 'brain_hidden', 64)
                         and mutated.brain_depth == getattr(self, 'brain_depth', 1))
            if same_arch:
                import copy
                mutated.brain = copy.deepcopy(self.brain)
                mutated.brain.mutate(mutation_rate=mutation_rate * 0.5)
            else:
                from neuroevolution import build_brain, graft_into
                child = build_brain(mutated)
                graft_into(child, self.brain)  # inherit what fits (EV4)
                mutated.brain = child
        elif self.use_neural:
            from neuroevolution import build_brain
            mutated.brain = build_brain(mutated)

        return mutated

# ============================================================================
# ENTITIES: Maw (Queen), SandKing (Units)
# ============================================================================

class UnitType(Enum):
    WORKER = 0   # Excavates, carries food
    SOLDIER = 1  # Fights, defends
    SCOUT = 2    # Fast, explores

_UNIT_SERIAL = itertools.count(1)  # display-only ids (SPEC_HIVE_MONITOR §2)


@dataclass
class SandKing:
    """Individual colony unit (worker/soldier/scout)"""
    colony_id: int
    position: Tuple[int, int, int]
    unit_type: UnitType
    health: int = 10
    max_health: int = 10
    attack: int = 2
    carrying: Optional[str] = None  # 'food', 'sand', 'copper', 'gold', None
    armored: bool = False  # copper armor consumed at spawn (T25)
    task_queue: deque = field(default_factory=deque)
    retreating: bool = False  # Morale flag
    forage_target: Optional[Tuple[int, int, int]] = None  # Cached food/corpse goal
    unit_id: int = field(default_factory=lambda: next(_UNIT_SERIAL))  # display identity
    thought: str = "..."  # last decoded thought / instincts (SPEC_HIVE_MONITOR M3)
    mine_target: Optional[Tuple[int, int, int]] = None  # ore being worked (T24)
    mine_progress: int = 0
    gift_amount: float = 0.0   # escrowed tribute an envoy carries (P3)
    gift_kind: str = ""        # 'food' | 'gold'
    gift_to: int = -1          # recipient colony id (-1 = not an envoy)
    weapon_expires: int = 0    # spear splinter step; 0 = unarmed (T44)
    spear_bonus: int = 0       # actual spear attack bonus (TE10 scaled by metallurgy)
    torch: bool = False        # can put fields to the torch (T44/T45)
    poisoned_until: int = 0    # scorpion venom DoT end step (T48)
    spoken_to_step: int = -10**9  # last time the keeper addressed it (K12)
    chop_target: Optional[Tuple[int, int, int]] = None  # trunk being cut (T41)
    chop_progress: int = 0
    laboring_for: int = -1  # colony_id of the current extractor; -1 = free (born free)
    wage_ratio: float = 0.0  # laborer's BIRTH-colony output share under a live labor contract; 0.0 = none (== W_BRUTE, a forced thrall or free) (WG1a)

    # Neural hive mind extension (soldier's personal layer)
    brain_layer: Optional[SoldierLayer] = None
    
    def __post_init__(self):
        # Set stats based on unit type (AGGRESSION > DEFENSE)
        if self.unit_type == UnitType.WORKER:
            self.health = 10
            self.max_health = 10
            self.attack = 2
        elif self.unit_type == UnitType.SOLDIER:
            self.health = 20  # Reduced from 25
            self.max_health = 20
            self.attack = 12  # Increased from 8 (aggression favored)
        elif self.unit_type == UnitType.SCOUT:
            self.health = 5
            self.max_health = 5
            self.attack = 1
    
    def move(self, new_position: Tuple[int, int, int]):
        """Move to new position"""
        self.position = new_position
    
    def take_damage(self, damage: int, resilience: float = 0.0) -> bool:
        """Take damage with resilience modifier, return True if killed"""
        actual_damage = damage * (1.0 - resilience * 0.5)  # 0-50% damage reduction
        self.health -= actual_damage
                # Track damage for neural layer performance
        if self.brain_layer is not None:
            self.brain_layer.damage_taken += actual_damage
                # Morale check: retreat at 10% HP (ancient Greek tactics)
        if self.health < self.max_health * 0.1 and not self.retreating:
            self.retreating = True
        
        return self.health <= 0

@dataclass
class Beast:
    """Wild fauna (T48): a DF-style invader, not a colony citizen.

    Beasts live outside the voxel grid (like units), spawn as single
    incursions from the map edge, and either die for their bounty or
    wander off after FAUNA_RAMPAGE steps. hunt_range 0 = neutral:
    strikes only once provoked.
    """
    species: str
    position: Tuple[int, int, int]
    health: int
    attack: int
    hunt_range: int
    bounty: int
    spawned_at: int = 0
    provoked: bool = False
    fleeing: bool = False


class Maw:
    """Queen entity - heart of each colony"""
    
    def __init__(self, colony_id: int, position: Tuple[int, int, int], genome: ColonyGenome):
        self.colony_id = colony_id
        self.position = position
        self.genome = genome
        self.health = MAW_MAX_HEALTH
        self.food_stored = 120
        self.spawn_queue = deque()
        self.alive = True
        self.fleeing = False  # set while migrating away from attackers (SPEC T15)
    
    def spawn_unit(self, unit_type: UnitType) -> Optional[SandKing]:
        """Spawn worker/soldier, costs food"""
        cost = {UnitType.WORKER: 3, UnitType.SOLDIER: 6, UnitType.SCOUT: 3}
        if self.food_stored >= cost[unit_type]:
            self.food_stored -= cost[unit_type]
            unit = SandKing(self.colony_id, self.position, unit_type)
            
            # Assign neural layer if colony uses neural AI
            if NEURAL_AVAILABLE and hasattr(self, 'genome') and self.genome.use_neural:
                unit.brain_layer = SoldierLayer()
                if self.genome.brain is not None:
                    unit.brain_layer.steps_alive = 0
            
            return unit
        return None
    
    def eat(self, food_amount: int):
        """Consume food"""
        self.food_stored += food_amount
    
    def take_damage(self, damage: int) -> bool:
        """Take damage, return True if killed"""
        self.health = max(0, self.health - damage)
        if self.health <= 0:
            self.alive = False
            return True
        return False

# ============================================================================
# COLONY - Manages all units and strategy
# ============================================================================

class Colony:
    """Manages a Sand King colony"""
    
    # Colony colors for visualization
    # >= MAX_COLONIES distinct house colors so the dynamic pool's houses never
    # share a color (the first four are the novella's canon houses, CH1/CH2).
    COLORS = [(255, 0, 0), (255, 255, 255), (0, 0, 0), (255, 165, 0),   # Red White Black Orange
              (60, 180, 255), (200, 80, 220), (240, 230, 60), (60, 200, 120)]  # Azure Violet Gold Jade

    @property
    def color(self) -> Tuple[int, int, int]:
        """This house's color, by slot, from the shared palette. Computed (not
        stored) so extending COLORS recolors houses live — including a resumed
        sim whose colonies were built under the old 4-color palette. Units are
        drawn in this color, so each house's spawn matches its own banner."""
        return self.COLORS[self.colony_id % len(self.COLORS)]

    def __init__(self, colony_id: int, maw_position: Tuple[int, int, int], genome: ColonyGenome):
        self.colony_id = colony_id
        self.maw = Maw(colony_id, maw_position, genome)
        self.units: List[SandKing] = []
        self.territory: Set[Tuple[int, int, int]] = {maw_position}
        self.genome = genome
        # color is a computed property (see below) — derived from colony_id so
        # extending COLORS recolors even a resumed sim (no stored stale color)
        self.at_war = False  # food hoard > WAR_CHEST drives raids (SPEC T10)
        self.known_food: List[Tuple[int, int, int]] = []  # scout intel (SPEC T11)
        self.farming = False  # 60/30 hysteresis gate on the farm branch (T18)
        self.ore = {'copper': 0, 'gold': 0}  # mined stores (T24/T25)
        self.ore_struck: Set[str] = set()    # first-strike events fired (T24)
        self.house = ""        # dynasty name; founded lazily (D1)
        self.generation = 1    # cadet-branch depth within the bloodline
        self.founded_step = 0  # reign start - scopes epithet judgment (D2)
        self.keeper_fed_step = -10**9  # last witnessed miracle (K3)
        self.worshipped = False        # has EVER been reverent (K3)
        self.breached = False          # awakened - past the glass (K10/K11)
        self.terminal_uses = 0         # sandbox-shell successes (K10)
        self.memory_augment = 0        # KV-cache memory-extension level (AUG2)
        self.currency = 0.0            # grains earned this maw's life (CU1)
        self.keeper_sentiment = 0.5    # devotion to the keeper 0..1 (F1)
        self._sentiment_wrath = False  # has the carved sentiment turned hateful
        self.confidence = 0.5          # boldness meter 0..1; 0.5 = neutral (DP1)
        self.favoritism = 0.0          # treatment ledger [-1, 1]; 0 = neutral (DP1)
        self.agitation = 0.0           # startle spike [0, 1]; 0 = calm (DP1)
        self.last_victory_step = -10**9  # step of last war victory (DP1)
        self.stage = 1                 # metamorphosis stage 1/2/3 (MT1)
        self.revelation = False        # has met the "great other" post-breakout (AW4)
        self.techs = set()             # technologies this house knows (TE1)
        self.tech_xp = {}              # per-tech proficiency 0..1 (DF skill, TE1)
        self.crafted = set()           # items crafted from gifted materials (TE13)
        self.pop_state = POP_ACTIVE    # lifecycle slot state; inert in Phase 0     [prov:C]
        self._build_rotor = 0          # per-colony spawn counter -> deterministic
        #                                designated-builder slots (NOT the global unit_id)

    def spawn_unit(self, unit_type: UnitType, step: int = 0):
        """Spawn new unit from Maw; copper armors, timber arms (T25/T44).

        step is the sim step at spawn time - it anchors the spear's
        splinter clock; callers without a clock may pass 0 (the spear
        then simply lives its full SPEAR_LIFE from step zero).
        """
        unit = self.maw.spawn_unit(unit_type)
        if unit:
            # per-colony builder slot (seeded spawn order -> deterministic across
            # sim instances, unlike the process-global unit_id)
            unit.build_slot = getattr(self, '_build_rotor', 0)
            self._build_rotor = getattr(self, '_build_rotor', 0) + 1
            if unit.unit_type == UnitType.SOLDIER:
                if getattr(self, 'ore', {}).get('copper', 0) >= 1:
                    self.ore['copper'] -= 1
                    unit.max_health += COPPER_ARMOR_HP
                    unit.health = unit.max_health
                    unit.armored = True
                # T44: a spear of palm and bone - organic, so it splinters
                if (getattr(self, 'wood', 0) >= 1
                        and getattr(self, 'bone', 0) >= 1):
                    self.wood -= 1
                    self.bone -= 1
                    # TE10: metallurgy hardens the spearhead
                    mprof = getattr(self, 'tech_xp', {}).get('metallurgy', 0.0)
                    bonus = int(round(SPEAR_ATTACK
                                      * (1 + METAL_WEAPON_BONUS * mprof)))
                    unit.attack += bonus
                    unit.spear_bonus = bonus
                    unit.weapon_expires = step + SPEAR_LIFE
                # TE11: gunpowder gives the soldier firepower (a firearm)
                gprof = getattr(self, 'tech_xp', {}).get('gunpowder', 0.0)
                if gprof:
                    unit.attack += int(round(GUNPOWDER_ATTACK * gprof))
                # TE13: crafted gear (spear/bow/firespike/bastion) arms the soldier
                for item in getattr(self, 'crafted', ()):
                    eff = CRAFTED_EFFECTS.get(item, {})
                    unit.attack += eff.get('attack', 0)
                    if eff.get('defense'):
                        unit.max_health += eff['defense']
                        unit.health = unit.max_health
                # T45: wartime soldiers may carry a torch (thrown once)
                if self.at_war and getattr(self, 'wood', 0) >= 1:
                    self.wood -= 1
                    unit.torch = True
                    # TE4/TE7: fielding a torch IS the fire technology
                    if not hasattr(self, 'techs'):
                        self.techs = set()
                    self.techs.add('fire')
                    if not hasattr(self, 'tech_xp'):
                        self.tech_xp = {}
                    self.tech_xp['fire'] = min(1.0, max(
                        self.tech_xp.get('fire', 0.0), 0.3) + 0.05)
            self.units.append(unit)
    
    def remove_unit(self, unit: SandKing):
        """Remove dead unit"""
        if unit in self.units:
            self.units.remove(unit)
    
    def get_population(self) -> int:
        """Get current population count"""
        return len(self.units)
    
    def is_alive(self) -> bool:
        """Check if colony is still alive (Maw alive)"""
        return self.maw.alive

# ============================================================================
# PHEROMONE SYSTEM - Chemical communication
# ============================================================================

class PheromoneType(Enum):
    FOOD_TRAIL = 0
    DANGER = 1
    TERRITORY = 2
    RALLY = 3

class PheromoneLayer:
    """Chemical signaling for colony coordination"""
    
    def __init__(self, dimensions: Tuple[int, int, int], num_colonies: int = 4):
        self.dimensions = dimensions
        self.num_colonies = num_colonies
        # Separate pheromone channels per colony per type
        self.trails = np.zeros((*dimensions, num_colonies, len(PheromoneType)), dtype=np.float32)
        self.decay_rate = 0.95
        self.diffusion_rate = 0.05
    
    def deposit(self, position: Tuple[int, int, int], colony_id: int, 
                pheromone_type: PheromoneType, strength: float = 1.0):
        """Deposit pheromone at position"""
        x, y, z = position
        if 0 <= x < self.dimensions[0] and 0 <= y < self.dimensions[1] and 0 <= z < self.dimensions[2]:
            self.trails[x, y, z, colony_id, pheromone_type.value] += strength
    
    def get_strength(self, position: Tuple[int, int, int], colony_id: int, 
                     pheromone_type: PheromoneType) -> float:
        """Get pheromone strength at position"""
        x, y, z = position
        if 0 <= x < self.dimensions[0] and 0 <= y < self.dimensions[1] and 0 <= z < self.dimensions[2]:
            return self.trails[x, y, z, colony_id, pheromone_type.value]
        return 0.0
    
    def step(self):
        """Decay pheromones each tick"""
        self.trails *= self.decay_rate
    
    def get_gradient(self, position: Tuple[int, int, int], colony_id: int, 
                     pheromone_type: PheromoneType, world: VoxelWorld) -> Optional[Tuple[int, int, int]]:
        """Get direction of strongest pheromone gradient"""
        neighbors = world.get_neighbors_3d(position, radius=1)
        if not neighbors:
            return None
        
        x, y, z = position
        current_strength = self.get_strength(position, colony_id, pheromone_type)
        
        best_neighbor = None
        best_strength = current_strength
        
        for nx, ny, nz in neighbors:
            strength = self.get_strength((nx, ny, nz), colony_id, pheromone_type)
            if strength > best_strength:
                best_strength = strength
                best_neighbor = (nx, ny, nz)
        
        if best_neighbor:
            return (best_neighbor[0] - x, best_neighbor[1] - y, best_neighbor[2] - z)
        return None

# ============================================================================
# CELLULAR AUTOMATA - Territory spread rules
# ============================================================================

class CellularAutomata:
    """Conway-style rules adapted for 3D colony dynamics"""
    
    @staticmethod
    def apply_territory_spread(world: VoxelWorld, colonies: List[Colony]):
        """
        Territory expansion rules (Conway-inspired), vectorized:
        - Birth: unowned AIR with 3+ adjacent same-colony cells joins the colony
        - Death: owned cell with <2 or >5 same-colony neighbors is released

        Neighbor counts come from 26 shifted sums with zeroed wrap borders
        (equivalent to the bounds-checked 26-neighborhood, ~100x faster than
        per-voxel iteration on large territories).
        """
        new_ownership = world.ownership.copy()
        air = world.voxels == VoxelType.AIR.value

        for colony in colonies:
            if not colony.is_alive():
                continue
            owned = world.ownership == colony.colony_id
            if not owned.any():
                continue

            counts = np.zeros(world.ownership.shape, dtype=np.int8)
            owned_i8 = owned.astype(np.int8)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        shifted = np.roll(owned_i8, (dx, dy, dz), axis=(0, 1, 2))
                        if dx == 1:
                            shifted[0, :, :] = 0
                        elif dx == -1:
                            shifted[-1, :, :] = 0
                        if dy == 1:
                            shifted[:, 0, :] = 0
                        elif dy == -1:
                            shifted[:, -1, :] = 0
                        if dz == 1:
                            shifted[:, :, 0] = 0
                        elif dz == -1:
                            shifted[:, :, -1] = 0
                        counts += shifted

            death = owned & ((counts < 2) | (counts > 5))
            new_ownership[death] = -1
            birth = (world.ownership == -1) & air & (counts >= 3)
            new_ownership[birth] = colony.colony_id

        world.ownership = new_ownership

# ============================================================================
# VISUALIZATION - 2D Slices & 3D GIFs
# ============================================================================

class Visualizer:
    """Handles 2D slice views and 3D GIF generation"""
    
    @staticmethod
    def render_z_slice(world: VoxelWorld, colonies: List[Colony], z_level: int, 
                       title: str = "") -> Image.Image:
        """Render 2D cross-section at given Z level"""
        w, h, _ = world.dimensions
        
        # Create RGB image (scale up for visibility)
        scale = 4
        img_array = np.zeros((h * scale, w * scale, 3), dtype=np.uint8)
        
        for x in range(w):
            for y in range(h):
                voxel = VoxelType(world.voxels[x, y, z_level])
                owner = world.ownership[x, y, z_level]
                
                # Color mapping
                if voxel == VoxelType.GLASS:
                    color = (100, 100, 100)
                elif voxel == VoxelType.STONE:
                    color = (50, 50, 50)
                elif voxel == VoxelType.SAND:
                    color = (194, 178, 128)
                elif voxel == VoxelType.TUNNEL_WALL:
                    color = (139, 90, 43)
                elif voxel == VoxelType.CASTLE:
                    color = (200, 195, 210)
                elif voxel == VoxelType.FOOD:
                    color = (0, 255, 0)
                elif voxel == VoxelType.CORPSE:
                    color = (128, 0, 0)
                elif voxel == VoxelType.TILLED:
                    color = (110, 80, 50)
                elif voxel == VoxelType.CROP:
                    color = (80, 160, 60)
                elif voxel == VoxelType.CROP_RIPE:
                    color = (190, 220, 60)
                elif voxel == VoxelType.COPPER_ORE:
                    color = (184, 115, 51)
                elif voxel == VoxelType.GOLD_ORE:
                    color = (255, 208, 0)
                elif voxel == VoxelType.HULL:
                    color = (120, 130, 150)
                elif voxel == VoxelType.SALVAGE:
                    color = (170, 190, 210)
                elif voxel == VoxelType.WOOD:
                    color = (34, 139, 34)
                elif voxel == VoxelType.WOOD_WALL:
                    color = (139, 105, 20)
                elif voxel == VoxelType.WEB:
                    color = (210, 210, 220)
                elif voxel == VoxelType.AIR:
                    if owner >= 0:
                        # Owned air = faint colony color
                        colony = next((c for c in colonies if c.colony_id == owner), None)
                        if colony:
                            color = tuple(int(c * 0.3) for c in colony.color)
                        else:
                            color = (20, 20, 20)
                    else:
                        color = (20, 20, 20)
                else:
                    color = (0, 0, 0)
                
                # Draw scaled pixel
                img_array[y*scale:(y+1)*scale, x*scale:(x+1)*scale] = color
        
        # Draw units
        for colony in colonies:
            for unit in colony.units:
                if unit.position[2] == z_level:
                    ux, uy = unit.position[0], unit.position[1]
                    # Draw unit as bright dot
                    unit_color = colony.color
                    cx, cy = ux * scale + scale//2, uy * scale + scale//2
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < w*scale and 0 <= ny < h*scale:
                                img_array[ny, nx] = unit_color
            
            # Draw Maw
            if colony.maw.position[2] == z_level:
                mx, my = colony.maw.position[0], colony.maw.position[1]
                # Draw Maw as larger bright square
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        nx = mx * scale + scale//2 + dx
                        ny = my * scale + scale//2 + dy
                        if 0 <= nx < w*scale and 0 <= ny < h*scale:
                            img_array[ny, nx] = (255, 255, 0)  # Yellow for Maw
        
        img = Image.fromarray(img_array, 'RGB')
        return img
    
    @staticmethod
    def generate_3d_frame(world: VoxelWorld, colonies: List[Colony]) -> Image.Image:
        """
        Generate 3D visualization using scatter plots (like 3D Conway's Life).
        Plots all voxels directly without clustering.
        """
        if plt is None:
            raise RuntimeError("GIF mode requires matplotlib; install it or "
                               "use --live / the dashboard instead.")
        try:
            fig = plt.figure(figsize=(12, 10))
            ax = fig.add_subplot(111, projection='3d')
            
            w, h, d = world.dimensions
            
            # Get coordinates for each voxel type using np.argwhere
            stone_coords = np.argwhere(world.voxels == VoxelType.STONE.value)
            glass_coords = np.argwhere(world.voxels == VoxelType.GLASS.value)
            sand_coords = np.argwhere(world.voxels == VoxelType.SAND.value)
            food_coords = np.argwhere(world.voxels == VoxelType.FOOD.value)
            tunnel_coords = np.argwhere(world.voxels == VoxelType.TUNNEL_WALL.value)
            
            # Plot terrain with depth-based coloring
            if len(stone_coords) > 0:
                ax.scatter(stone_coords[:, 0], stone_coords[:, 1], stone_coords[:, 2],
                          c=stone_coords[:, 2], cmap='gray', s=2, alpha=0.4, vmin=0, vmax=d)
            
            if len(glass_coords) > 0:
                ax.scatter(glass_coords[:, 0], glass_coords[:, 1], glass_coords[:, 2],
                          c='cyan', s=2, alpha=0.3)
            
            if len(sand_coords) > 0:
                ax.scatter(sand_coords[:, 0], sand_coords[:, 1], sand_coords[:, 2],
                          c=sand_coords[:, 2], cmap='YlOrBr', s=1, alpha=0.2, vmin=0, vmax=d)
            
            if len(food_coords) > 0:
                ax.scatter(food_coords[:, 0], food_coords[:, 1], food_coords[:, 2],
                          c='lime', s=50, marker='o', alpha=0.8)
            
            if len(tunnel_coords) > 0:
                ax.scatter(tunnel_coords[:, 0], tunnel_coords[:, 1], tunnel_coords[:, 2],
                          c='brown', s=3, alpha=0.5)
            
            # Plot owned air (territory) colored by colony
            for colony in colonies:
                owned_air = np.argwhere((world.voxels == VoxelType.AIR.value) & 
                                       (world.ownership == colony.colony_id))
                if len(owned_air) > 0:
                    color = np.array(colony.color) / 255.0
                    ax.scatter(owned_air[:, 0], owned_air[:, 1], owned_air[:, 2],
                              c=[color], s=3, alpha=0.3)
            
            # Draw units and Maws
            for colony in colonies:
                color = np.array(colony.color) / 255.0
                
                # Units
                if colony.units:
                    unit_positions = np.array([u.position for u in colony.units])
                    ax.scatter(unit_positions[:, 0], unit_positions[:, 1], unit_positions[:, 2],
                              c=[color], s=100, marker='^', edgecolors='black', linewidths=1)
                
                # Maw
                if colony.maw.alive:
                    mx, my, mz = colony.maw.position
                    ax.scatter(mx, my, mz, c='gold', s=300, marker='*', 
                              edgecolors='black', linewidths=2)
            
            ax.set_xlabel('X')
            ax.set_ylabel('Y')
            ax.set_zlabel('Z')
            ax.set_xlim(0, w)
            ax.set_ylim(0, h)
            ax.set_zlim(0, d)
            ax.set_title('Sand Kings 3D Terrarium')
            
            # Convert plot to image
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            img = Image.open(buf).copy()  # Copy to free buffer
            buf.close()
            plt.close(fig)
            plt.close('all')  # Aggressive cleanup
            
            return img
        
        except Exception as e:
            print(f"Warning: 3D frame generation failed: {e}")
            # Return blank fallback image
            img = Image.new('RGB', (1200, 1000), color='black')
            plt.close('all')
            return img

# ============================================================================
# MAIN SIMULATION ENGINE
# ============================================================================

class SandKingsSimulation:
    """Main simulation engine coordinating all systems"""
    
    def __init__(self, width=80, height=40, depth=20, num_colonies=4,
                 canon=False, dynamic_population=None):
        self.world = VoxelWorld(width, height, depth)
        self.canon = bool(canon)  # CH1: the novella's four color-houses
        # Resolve random colony count here so the pheromone layer's
        # per-colony axis matches the colonies actually spawned
        if self.canon:
            num_colonies = 4  # Red, White, Black, Orange
        elif num_colonies is None or num_colonies == 0:
            num_colonies = random.randint(3, 5)
        # Bounded pool (Phase 6): resolved BEFORE pheromone sizing so the channel
        # axis can span MAX_COLONIES when dynamic — only num_colonies seed ACTIVE,
        # the rest are DORMANT slots that later founding/budding activates.
        # instance override hook: explicit arg (e.g. --dynamic) wins; else the
        # module default (False, so the test battery stays flag-off / identity-green)
        self.dynamic_population = (DYNAMIC_POPULATION if dynamic_population is None
                                   else bool(dynamic_population))
        pher_channels = MAX_COLONIES if self.dynamic_population else num_colonies
        self.pheromones = PheromoneLayer(self.world.dimensions, pher_channels)
        self.num_colonies = num_colonies   # resolved seed count (≤ MAX_COLONIES); read by the bounded pool (Phase 6)
        self.automata = CellularAutomata()
        self.colonies: List[Colony] = []
        self.step_count = 0
        self.pending_respawns: Dict[int, int] = {}  # colony_id -> due step
        self.events: deque = deque(maxlen=50)  # (step, message) drama feed (SPEC T9)
        self.monitors: Dict[int, 'HiveMindMonitor'] = {}  # SPEC_HIVE_MONITOR M6
        self.storm_until = 0                   # storm active while > step_count (SPEC T12)
        self.water_level = WATER_LEVEL_DEFAULT  # BI1: the closed water budget
        self.water_target = WATER_LEVEL_DEFAULT  # the reservoir set point (panel)
        self.sun_hours = SUN_HOURS_DEFAULT      # BI1: daylight hours/day (panel)
        self.sun_effective = SUN_HOURS_DEFAULT   # SP5: the drawn sky for the current biome-day
        self.sun_ema_mean = SUN_HOURS_DEFAULT   # SP10: rolling mean of realized daylight (observer)
        self.sun_ema_sd = 0.0                   # SP10: rolling |deviation| ~ sigma (observer)
        self._storm_wind = (1, 0)              # per-storm prevailing direction

        # Initialize colonies with random count (3-5) and positions
        self._spawn_colonies(num_colonies)
        # Bounded pool (Phase 6): pad the slot pool to MAX_COLONIES with DORMANT
        # placeholders. A DORMANT slot is a not-alive Colony (maw.alive=False) with
        # no board presence — invisible, skipped by every is_alive() guard — that
        # founding/budding later activates. Inert while dynamic_population=False.
        if self.dynamic_population:
            self._pad_dormant_slots()
    
    # CH2: the four canonical color-houses (name, epithet, disposition
    # overrides, starting-food multiplier) keyed by colony_id / COLORS order
    CANON_HOUSES = {
        0: ("Crimson", "the Creative",
            {'plasticity': 0.85, 'fertility': 0.80}, 1.0, 0),
        1: ("Pale", "the Favored",
            {'aggression': 0.85, 'expansion_rate': 0.80}, 1.6, 2),
        2: ("Sable", "the Wise",
            {'patience': 0.90, 'loyalty': 0.90}, 1.0, 0),
        3: ("Amber", "the Underdog",
            {'aggression': 0.35, 'fertility': 0.4, 'plasticity': 0.35}, 0.6, 0),
    }

    def _apply_canon(self):
        """CH2: overlay the novella's four houses onto the fresh colonies -
        names, epithets, dispositions, and starting stock. Presets are the
        START; mutation/respawn/evolution proceed normally (the underdog
        can rise)."""
        epithets = self._house_epithets()
        for colony in self.colonies:
            spec = self.CANON_HOUSES.get(colony.colony_id)
            if spec is None:
                continue
            name, epithet, traits, food_mult, extra_workers = spec
            colony.house = name
            colony.generation = 1
            colony.founded_step = 0
            epithets[name] = epithet
            # neutralize to a common baseline so each house's signature
            # trait stands out cleanly (white most aggressive, etc.)
            for attr in ('aggression', 'tunnel_preference', 'expansion_rate',
                         'defense_investment', 'fertility', 'patience',
                         'loyalty', 'plasticity'):
                setattr(colony.genome, attr, 0.5)
            for attr, value in traits.items():
                setattr(colony.genome, attr, value)
            colony.maw.food_stored *= food_mult
            for _ in range(extra_workers):
                colony.spawn_unit(UnitType.WORKER)
        self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1
        self._log_event("The four houses wake: Crimson, Pale, Sable,"
                        " and Amber")

    def _spawn_colonies(self, num_colonies: int = None):
        """Spawn Maw queens at randomized locations with min distance"""
        w, h, d = self.world.dimensions
        
        # Variable colony count (3-5) if not specified or 0
        if num_colonies is None or num_colonies == 0:
            num_colonies = random.randint(3, 5)
        
        # Minimum distance = 10% of map diagonal
        min_distance = int(0.1 * ((w**2 + h**2)**0.5))
        
        # Generate positions ensuring min distance. One lucky colony wakes
        # beside the oasis (T22); the others start pushed away from it
        positions = []
        max_attempts = 100
        cx, cy = w // 2, h // 2
        lucky = random.randrange(num_colonies)

        for i in range(num_colonies):
            if i == lucky:
                for attempt in range(max_attempts):
                    angle = random.uniform(0, 2 * np.pi)
                    ring = OASIS_RADIUS + 1
                    x = int(np.clip(cx + ring * np.cos(angle), w // 8, 7 * w // 8))
                    y = int(np.clip(cy + ring * np.sin(angle), h // 8, 7 * h // 8))
                    pos = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))
                    if all(((pos[0]-p[0])**2 + (pos[1]-p[1])**2)**0.5 >= min_distance
                           for p in positions):
                        positions.append(pos)
                        break
                continue
            for attempt in range(max_attempts):
                # Random position in safe zone (not edges), on the surface
                x = random.randint(w//8, 7*w//8)
                y = random.randint(h//8, 7*h//8)
                z = min(self.world.surface_z(x, y) + 1, d - 1)

                pos = (x, y, z)

                # Check distance to existing colonies AND the oasis buffer
                if (((x - cx)**2 + (y - cy)**2)**0.5 < OASIS_RADIUS + 4
                        and attempt < max_attempts - 1):
                    continue
                if all(((pos[0]-p[0])**2 + (pos[1]-p[1])**2)**0.5 >= min_distance
                       for p in positions):
                    positions.append(pos)
                    break
        
        for i in range(len(positions)):
            genome = ColonyGenome()
            # Randomize traits (aggression-focused)
            genome.aggression = random.uniform(0.5, 1.0)  # Favor aggression
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.uniform(0.3, 1.0)  # Spawn threshold bounded [30, 100]
            genome.patience = random.uniform(0.3, 0.95)  # discount gamma (T26)
            genome.loyalty = random.uniform(0.2, 0.9)    # hawk-dove (P11)
            genome.plasticity = random.uniform(0.2, 0.9)  # meta-learning (S3)
            genome.resilience = random.uniform(0.0, 0.3)  # Defense weaker
            
            colony = Colony(i, positions[i], genome)
            from chronicle import make_house_name
            colony.house = make_house_name()  # D1: the founding houses
            self.colonies.append(colony)
            
            # Mark starting position
            x, y, z = positions[i]
            self.world.set_voxel(x, y, z, VoxelType.AIR, colony_id=i)
            
            # Spawn initial workers
            for _ in range(3):
                colony.spawn_unit(UnitType.WORKER)

        if getattr(self, 'canon', False):  # CH2: seat the four color-houses
            self._apply_canon()

        holder = self.oasis_holder()
        if holder is not None:
            self._log_event(f"Colony {holder} wakes beside the oasis")
    
    def step(self):
        """Execute one simulation step"""
        self.step_count += 1

        # 0. SEASON TICK (T16) - first, so boundary feedings use the new dole
        if self.step_count % SEASON_LENGTH == 0:
            name = SEASONS[self.season_index()]
            self._log_event(f"The {name} season begins"
                            f" (dole {self.dole_factor() * 100:.0f}%)")

        # 1. Physics
        if self.step_count % 5 == 0:  # Apply gravity every 5 steps
            self.world.apply_gravity()
        
        # 2. Cellular automata (territory spread)
        if self.step_count % 10 == 0:  # Apply CA rules every 10 steps
            self.automata.apply_territory_spread(self.world, self.colonies)
        
        # 3. Pheromone decay
        self.pheromones.step()

        # 3b. KEEPER FEEDING: scatter food on the surface (SPEC T1)
        if self.step_count % FEED_INTERVAL == 0:
            self._feed_terrarium()

        # 3c. SANDSTORMS: wind reshapes the dunes (SPEC T12); storms never
        # overlap. Seasonal cadence (T16): frequent in Dust, none in Chill
        season = self.season_index()
        storm_interval = STORM_INTERVAL_DUST if season == 2 else STORM_INTERVAL
        if (season != 3
                and self.step_count % storm_interval == 0
                and self.storm_until <= self.step_count
                and getattr(self, 'hail_until', 0) <= self.step_count
                and random.random() < STORM_CHANCE):
            # W2: in Growth/Dust the storm roll may come down as hail
            if season in (1, 2) and random.random() < HAIL_SHARE:
                self.hail_until = self.step_count + STORM_DURATION
                self._log_event("Hail hammers the dunes!")
            else:
                self.storm_until = self.step_count + STORM_DURATION
                self._storm_wind = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                self._log_event("A sandstorm rises!")
        if self.storm_until > self.step_count:
            self._blow_sand()
            # T45: dry lightning rides the Dust storms
            if season == 2 and random.random() < 0.02:
                flams = np.argwhere(np.isin(self.world.voxels,
                                            FLAMMABLE_VOXELS))
                if len(flams):
                    pos = tuple(int(v) for v in
                                flams[random.randrange(len(flams))])
                    self._ignite(pos)
                    self._log_event("Lightning splits the sky - fire!")
            if self.storm_until == self.step_count + 1:
                self._log_event("The sandstorm passes")

        # 3c-b. THE CLOSED BIOME (SPEC_BIOME BI3/BI4): the water cycle and the
        # weather that emerges from the reservoir + sun the keeper sets
        self._biome_tick()

        # 3c-f. HYDRO FLOW SIM (SPEC_HYDRO): standing water flows, settles, drains.
        # No-op (early-return) until water exists, so a neutral run is untouched.
        if self.step_count % HYDRO_TICK == 0:
            self._hydro_tick()

        # 3c-w. DESERT WEATHER (SPEC_WEATHER W1-W3): flood, hail, frost
        self._weather_tick(season)

        # 3c-a. ARENA TEMPERATURE (SPEC_ARENA AR3): the keeper's non-lethal
        # heat/cold - drains hoards and wilts fields, never kills
        self._arena_tick()

        # 3c-h. THE HAND'S WATER (SPEC_HYDRO_HAND HH2): irrigation / deluge
        self._keeper_water_tick()

        # 3c-t. TECHNOLOGY (SPEC_TECH TE8/TE9): observe neighbors, buy research
        if self.step_count % TECH_TICK == 0 and self.step_count:
            self._tech_tick()

        # 3c-s. SIEGE (SPEC_TECH TE11): catapults hurl shot across the board
        self._catapult_tick()

        # 3c-c. CALTROPS (SPEC_TECH TE13): loose tacks prick whoever crosses
        self._caltrop_tick()

        # 3d. CROP GROWTH (T19/T20)
        if self.step_count % CROP_TICK == 0:
            self._grow_crops()

        # 3e. DUST SPOILAGE (T16)
        if season == 2 and self.step_count % SPOIL_INTERVAL == 0:
            self._spoil_surface_food()

        # 3f. MACHINE TICK (SPEC_MACHINE_AGE T37)
        from machines import VM_TICK
        if self.step_count % VM_TICK == 0 and getattr(self.world, 'wreck', None):
            self._machine_tick()

        # 3g. RADIATION (T40): the damaged reactor seeps; fields decay
        if getattr(self.world, 'wreck', None):
            self._radiation_tick()

        # 3h. FIRE (T45): damage, spread, burn out
        if self.step_count % FIRE_TICK == 0 and getattr(self, 'fires', None):
            self._fire_tick()

        # 3i. PALISADE ROT (T43): organic walls crumble on schedule
        if self.step_count % 50 == 0 and getattr(self, 'rot', None):
            for pos, expiry in list(self.rot.items()):
                if self.world.voxels[pos] != VoxelType.WOOD_WALL.value:
                    del self.rot[pos]
                elif self.step_count >= expiry:
                    self.world.voxels[pos] = VoxelType.SAND.value
                    del self.rot[pos]

        # 4. NEURAL PRUNING: Remove rarely activated weights every 50 steps
        if NEURAL_AVAILABLE and self.step_count % 50 == 0:
            for colony in self.colonies:
                if colony.genome.use_neural and colony.genome.brain is not None:
                    pruned = colony.genome.brain.prune_weights(threshold=0.01)
                    if pruned > 0:
                        print(f"Colony {colony.colony_id}: Pruned {pruned} weights")

        # 4a. THE DISPOSITION (SPEC_DISPOSITION DP2): update confidence from
        #     material condition; decay favoritism/agitation. Pure, no RNG.
        self._disposition_tick()

        # 4b. THE BARGAIN (SPEC_BARGAIN): choose per-pair enforcement mode from
        #     net extraction BEFORE war entry / wages / capture read it
        self._bargain_tick()

        # 5. Food consumption and starvation (DARWINIAN PRESSURE)
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            
            # Normalize Round-1 attrs for colonies from older checkpoints
            if not hasattr(colony, 'farming'):
                colony.farming = False
                colony.ore = {'copper': 0, 'gold': 0}
                colony.ore_struck = set()
            for attr, default in (('machine_arc', 'none'), ('salvage', 0),
                                  ('controllers', None), ('devices', None)):
                if not hasattr(colony, attr):  # Round-3 attrs (T37)
                    setattr(colony, attr, default if default is not None else [])
            for attr in ('wood', 'bone', 'ram_until'):  # Round-4 (T41-T44)
                if not hasattr(colony, attr):
                    setattr(colony, attr, 0)
            for attr, default in (('keeper_fed_step', -10**9),  # K1-K12
                                  ('worshipped', False),
                                  ('breached', False),
                                  ('terminal_uses', 0),
                                  ('memory_augment', 0),  # AUG2
                                  ('keeper_sentiment', 0.5),  # F1
                                  ('_sentiment_wrath', False),
                                  ('stage', 1),  # MT1
                                  ('revelation', False),  # AW4
                                  ('confidence', 0.5),  # DP1
                                  ('favoritism', 0.0),  # DP1
                                  ('agitation', 0.0),  # DP1
                                  ('last_victory_step', -10**9),  # DP1
                                  ('pop_state', POP_ACTIVE)):  # POP: lifecycle slot state
                if not hasattr(colony, attr):
                    setattr(colony, attr, default)
            # TE1: mutable tech state (per-colony fresh objects, not shared)
            if not hasattr(colony, 'techs'):
                colony.techs = set()
            if not hasattr(colony, 'tech_xp'):
                colony.tech_xp = {}
            if not hasattr(colony, 'crafted'):
                colony.crafted = set()  # TE13

            # Organic rot (T42): timber and bone decay; metal is forever
            if self.step_count % ROT_INTERVAL == 0:
                colony.wood = max(0, colony.wood - 1)
                colony.bone = max(0, colony.bone - 1)

            # Spear expiry (T44): organic weapons splinter
            for unit in colony.units:
                exp = getattr(unit, 'weapon_expires', 0)
                if exp and self.step_count >= exp:
                    unit.attack -= getattr(unit, 'spear_bonus', SPEAR_ATTACK)
                    unit.spear_bonus = 0
                    unit.weapon_expires = 0
                    self._monitor(colony.colony_id).log_decision(
                        self.step_count, self._unit_label(unit),
                        "his spear splinters", getattr(unit, 'thought', None))

            # Battering ram (T44b): craft at war, rots on schedule/peace
            if colony.at_war and colony.wood >= RAM_COST and not (
                    getattr(colony, 'ram_until', 0) > self.step_count):
                colony.wood -= RAM_COST
                colony.ram_until = self.step_count + RAM_LIFE
                self._log_event(f"Colony {colony.colony_id} builds a"
                                " battering ram from a fallen palm")
            if not colony.at_war:
                colony.ram_until = 0

            # LEARNER decision tick (T26): posture biases gates, never
            # rules. Plasticity scales the update (S3); Chill dreams (S4)
            if self.step_count % 25 == 0:
                learner = self._learner(colony.colony_id)
                plasticity = getattr(colony.genome, 'plasticity', 0.5)
                learner.decide(self, colony,
                               getattr(colony.genome, 'patience', 0.5),
                               plasticity)
                if self.season_index() == 3:  # the maws dream through frost
                    learner.dream(getattr(colony.genome, 'patience', 0.5),
                                  plasticity)
                    # 85% tier: the maw's real-RL policy consolidates its best memories via
                    # elite self-distillation, once per colony per year (S4).
                    mrl = getattr(colony, 'maw_rl', None)
                    if mrl is not None and getattr(colony, '_maw_dream_year', None) != self.year():
                        colony._maw_dream_year = self.year()
                        mrl.dream()
                    dream_key = (self.year(),)
                    if getattr(self, '_dream_logged', None) != dream_key:
                        self._dream_logged = dream_key
                        self._log_event("The maws dream through the long frost")
            posture = self._posture(colony)

            # FARMING FLAG hysteresis: on > FARM_START_FOOD, off < FARM_STOP_FOOD
            # (T18); a FARM posture lowers the entry gate by 25% (T26)
            start_gate = FARM_START_FOOD * (0.75 if posture == "FARM" else 1.0)
            if colony.farming:
                colony.farming = colony.maw.food_stored > FARM_STOP_FOOD
            else:
                colony.farming = colony.maw.food_stored > start_gate

            # Maintenance cost (SPEC constants)
            colony.maw.food_stored -= len(colony.units) * MAINTENANCE_COST

            # Starvation: capped per step so decline is gradual (SPEC T7)
            if colony.maw.food_stored < 0 and colony.units:
                units_to_kill = random.sample(
                    colony.units,
                    min(STARVATION_MAX_KILLS, len(colony.units)))
                for dead_unit in units_to_kill:
                    colony.maw.food_stored += 2  # Recover some food from dead unit
                    colony.remove_unit(dead_unit)
                    # Create edible corpse
                    self.world.set_voxel(*dead_unit.position, VoxelType.CORPSE)

            # Adjust spawn threshold by expansion_rate
            spawn_threshold = 30 / max(0.1, colony.genome.expansion_rate)

            # WAR FOOTING (T10 amended by P5): the hoard picks ONE target;
            # coalition members mobilize at half the chest
            d = self._diplomacy()
            cid = colony.colony_id
            current_target = d.war_target.get(cid)
            coalition_member = d.hegemon is not None and cid != d.hegemon
            enter_at = WAR_CHEST * (0.5 if coalition_member else 1.0)
            if self.keeper_attitude(colony) == 'wrathful':  # K3: hungry,
                enter_at *= KEEPER_WRATH_MOBILIZATION       # angry, quicker

            if current_target is None:
                if colony.maw.food_stored > enter_at:
                    target = self._select_war_target(colony)
                    if (BARGAIN_ENABLED and target is not None
                            and self._bargain_mode_ids(cid, target) == BARGAIN_MODE_WAGE):
                        target = None    # bargain: a wage relation nets more than war
                    d.war_target[cid] = target
                    if target is not None:
                        self._log_event(f"Colony {cid} declares war"
                                        f" on Colony {target}!")
                        monitor = self._monitor(cid)
                        monitor.log_decision(self.step_count, f"Colony {cid}",
                                             f"declares war on Colony {target}",
                                             monitor.colony_thought(self, colony))
                    elif (self.step_count - d.restless_logged.get(cid, -10**9)
                          > SEASON_LENGTH):
                        d.restless_logged[cid] = self.step_count
                        self._log_event(f"Colony {cid} seethes, but has no enemy")
            else:
                target_colony = self._colony_by_id(current_target)
                if (colony.maw.food_stored < WAR_CHEST / 2
                        or target_colony is None
                        or not target_colony.is_alive()
                        or d.truce_active(cid, current_target, self.step_count)):
                    d.war_target[cid] = None  # stand down / target resolved
            colony.at_war = d.war_target.get(cid) is not None

            # BOOTSTRAP: a colony with no units always fields a worker (SPEC T2)
            if not colony.units and colony.maw.food_stored >= 3:
                colony.spawn_unit(UnitType.WORKER, self.step_count)
            # Maw spawning decisions; war flips the mix
            elif colony.maw.food_stored > spawn_threshold and len(colony.units) < UNIT_CAP:
                if random.random() < colony.genome.fertility:
                    roll = random.random()
                    if colony.at_war:  # SPEC T11 mix: 0.30 W / 0.60 S / 0.10 C
                        # RAID posture presses harder: 0.20 W / 0.70 S (T26)
                        worker_cut = 0.20 if posture == "RAID" else 0.30
                        unit_type = (UnitType.WORKER if roll < worker_cut else
                                     UnitType.SOLDIER if roll < 0.90 else UnitType.SCOUT)
                    else:              # peacetime: 0.60 W / 0.25 S / 0.15 C
                        unit_type = (UnitType.WORKER if roll < 0.60 else
                                     UnitType.SOLDIER if roll < 0.85 else UnitType.SCOUT)
                    colony.spawn_unit(unit_type, self.step_count)
            
            # K5: track sustained prosperity for autonomous castle-building. A
            # house durably richer than the war-chest raises a castle on its own
            # (prosperity made visible) — no keeper reverence required. A brief
            # spike doesn't qualify: prosperous_since marks when wealth began.
            if colony.maw.food_stored > WAR_CHEST:
                if getattr(colony, 'prosperous_since', -1) < 0:
                    colony.prosperous_since = self.step_count
            else:
                colony.prosperous_since = -1

            # Unit AI (simplified)
            for unit in colony.units[:]:  # Copy list to allow removal
                self._execute_unit_ai(unit, colony)
        
        # 5a-mind. RESONANCE (S1): thought contagion through the ranks
        if NEURAL_AVAILABLE and self.step_count % RESONANCE_TICK == 0:
            self._resonance_tick()

        # 5a. WILD INCURSIONS (T48): DF-invader monsters trample through
        self._fauna_tick()
        self._guppy_tick()                   # the oasis pond ecosystem (SPEC_GUPPIES; gated baseline-on)
        self._cricket_tick()                 # the terrestrial cricket swarm (SPEC_FOOD_WEB; gated baseline-on)
        self._snare_tick()                   # WEB/string/toothpick weirs catch guppies+crickets (gated baseline-on)

        # 5a-keeper. THE KEEPER (K4/K8/K9/K10): carvings, script, gifts
        self._keeper_tick()

        # 5a-meta. METAMORPHOSIS (MT2/MT3): the maw grows into a new breed
        self._metamorphosis_tick()

        # 5a-psi. THE PSIONIC MAW (PS1/PS3/PS4): the awakened reach back,
        # and a hateful Shade turns the terrarium on its god
        self._psionic_tick()

        # 5a-codex. THE CODEX (CX4): the awakened read, and learn
        if self.step_count % CODEX_INTERVAL == 0 and self.step_count:
            self._codex_tick()

        # 5a-tel. TELEMETRY (TL1): the free Dwarf-Therapist-style stat feed
        from telemetry import TELEMETRY_INTERVAL as _TI
        if self.step_count % _TI == 0 and self.step_count:
            self._telemetry().record(self)
            self._score_forecasts()  # CU3: mint grains for true forecasts

        # 5b. DIPLOMACY (SPEC_POLITICS): a truce signed this step prevents
        # this step's bloodshed
        self._resolve_diplomacy()

        # 5c. WAGES (SPEC_WAGES): factor market — renegotiate, settle, open, suspend/close
        self._labor_market_tick()

        # 6. Combat resolution
        self._resolve_conflicts()

        # 6b. SUBJUGATION (SPEC_SUBJUGATION): defiance, coercion, break-free
        self._subjugation_tick()

        # 7. Maw migration, regen, colony collapse, and new arrivals (SPEC T4-T6, T15)
        self._migrate_threatened_maws()
        self._apply_maw_regen()
        self._check_maw_deaths()
        self._process_respawns()
        if getattr(self, 'dynamic_population', False):   # Phase 6: pool breathes 2..MAX
            self._succession_tick()          # advance any live succession windows
            self._population_tick()           # fill-in when sparse, bud when crowded
        self._maw_rl_tick()                  # 85% tier: maw real-RL directive (gated)

    def _maw_strategy_mode(self, d):
        """Map a maw directive (aggression, mobility, verticality) to a strategic ARCHETYPE for the
        drama feed — so the player watches the learned personality surface as narrative. Returns a
        flavor phrase when the directive strongly enters an archetype, else None (no drama)."""
        a = float(d[0])
        m = float(d[1]) if d.numel() > 1 else 0.5
        v = float(d[2]) if d.numel() > 2 else 0.5
        if a > 0.72:
            return "beats the war-drums"
        if v > 0.72:
            return "burrows into the deep"
        if m > 0.72:
            return "spreads across the sands"
        if a < 0.30:
            return "draws inward, wary of the glass"
        return None

    def _maw_rl_tick(self):
        """85% tier - per-colony maw REAL-RL (batch-REINFORCE) directive, on the batch
        clock (staggered per colony). Obs = the batched FROZEN-encoder aggregate
        (_colony_encodings); reward = survival/dominance delta since the last directive.
        Gated: MAW_RL_ENABLED default False => returns immediately, battery byte-identical.
        Draws only torch RNG (not the python/numpy streams the sim determinism uses)."""
        if not MAW_RL_ENABLED:
            return
        try:
            from maw_brain import ColonyMawRL, MAW_LR, patience_to_gamma
            import torch
        except Exception:
            return
        for colony in self.colonies:
            if not getattr(colony.maw, 'alive', False):
                continue
            if (self.step_count + colony.colony_id) % POP_TICK_INTERVAL != 0:
                continue
            enc = self._colony_encodings(colony)
            if enc:
                base = torch.stack(list(enc.values())).mean(0)
            else:
                base = torch.zeros(32, dtype=torch.float32)   # HiveMindBrain encoding_dim
            kills = sum(getattr(getattr(u, 'brain_layer', None), 'kills', 0)
                        for u in colony.units)                     # combat success (obs + reward)
            # append RAW colony STATE so the directive is state-responsive and less dependent on the
            # random Kanerva basis — the policy learns from real signal (war footing, season, materials),
            # not just the frozen random projection. Fixed dim (39) for a stable policy.
            stats = torch.tensor([
                min(len(colony.units) / 20.0, 2.0),                       # population
                min(colony.maw.food_stored / 100.0, 3.0),                 # food stores
                min(len(getattr(colony, 'territory', ())) / 200.0, 3.0),  # territory
                min(kills / 20.0, 3.0),                                   # combat success
                1.0 if getattr(colony, 'at_war', False) else 0.0,         # war footing
                min(float(getattr(colony, 'wood', 0)) / 50.0, 3.0),       # materials on hand
                self.season_index() / 3.0,                                # seasonal phase (learn seasonal strategy)
            ], dtype=torch.float32)
            obs = torch.cat([base, stats])
            rl = getattr(colony, 'maw_rl', None)
            if rl is None or rl.policy.obs_dim != int(obs.shape[0]):
                # v2: warm-start the directive to the genome instincts ("never tabula rasa"),
                # and set the RL learning rate from the evolved plasticity gene (Baldwin effect).
                g = colony.genome
                warm = torch.tensor([
                    float(getattr(g, 'aggression', 0.5)),          # d0 aggression
                    float(getattr(g, 'expansion_rate', 0.5)),      # d1 mobility
                    float(getattr(g, 'tunnel_preference', 0.5)),   # d2 verticality
                    0.5,                                           # d3 forage-mode (neutral; the RL learns it)
                ], dtype=torch.float32)
                lr = MAW_LR * (0.5 + float(getattr(g, 'plasticity', 0.5)))
                gamma = patience_to_gamma(float(getattr(g, 'patience', 0.5)))  # patience gene -> discount
                rl = ColonyMawRL(obs_dim=int(obs.shape[0]), warm_start=warm, lr=lr, gamma=gamma)
                colony.maw_rl = rl
            snap = (float(len(colony.units))                       # population
                    + colony.maw.food_stored / 50.0                # stores
                    + len(getattr(colony, 'territory', ())) / 100.0  # dominance/territory
                    + kills * 0.5                                  # kills: winning fights pays
                    + (2.0 if colony.maw.alive else 0.0))          # survival
            prev = getattr(colony, '_maw_rl_prev', None)
            if prev is not None:
                rl.observe_reward(snap - prev)   # reward for the LAST directive
            colony._maw_rl_prev = snap
            colony.maw_directive = rl.act(obs)   # emit this cycle's directive
            # surface the maw's learning in the drama feed (throttled to each RL update)
            if rl.updates and rl.updates != getattr(colony, '_maw_rl_logged', -1):
                colony._maw_rl_logged = rl.updates
                _d = colony.maw_directive
                _loss = rl.last_loss if rl.last_loss is not None else 0.0
                _vert = f" vert={float(_d[2]):.2f}" if _d.numel() > 2 else ""
                self._log_event(
                    f"{self._house_name(colony)} maw learns: aggr={float(_d[0]):.2f} "
                    f"mob={float(_d[1]):.2f}{_vert} (upd {rl.updates}, loss {_loss:.2f})")
                # narrate a STRATEGY SHIFT — the learned personality becomes visible drama
                _mode = self._maw_strategy_mode(_d)
                if _mode and _mode != getattr(colony, '_maw_mode', None):
                    colony._maw_mode = _mode
                    self._log_event(f"{self._house_name(colony)} {_mode}")

    def _log_event(self, message: str):
        """Append to the drama feed (SPEC T9) and the chronicle (D4).

        Chronicle rows are house-substituted AT WRITE TIME so history
        stays correctly attributed after the slot's house changes."""
        self.events.append((self.step_count, message))
        from chronicle import prune, salience_of
        rows = self._chronicle()
        text = self._substitute_houses(message)
        # dedup: a repeated line within a season is one historical fact
        for pstep, ptext, _ps in rows[-30:]:
            if ptext == text and self.step_count - pstep < SEASON_LENGTH:
                return
        rows.append((self.step_count, text, salience_of(message)))
        if len(rows) > 900:
            self.chronicle = prune(rows)

    def _substitute_houses(self, text: str) -> str:
        """D1: 'Colony 2' reads as 'House Vex-Karn II' wherever it appears."""
        import re
        from chronicle import house_label

        def repl(match):
            colony = self._colony_by_id(int(match.group(1)))
            if colony is None:
                return match.group(0)
            return "House " + house_label(self._house_name(colony),
                                          getattr(colony, 'generation', 1))
        return re.sub(r"Colony (\d+)", repl, text)

    # ---- Dynasties & Chronicle helpers (SPEC_DYNASTIES.md) ----

    def _chronicle(self) -> List[Tuple[int, str, int]]:
        """Append-only saga rows (step, text, salience) (D4); guarded."""
        if not hasattr(self, 'chronicle'):
            self.chronicle = []
        return self.chronicle

    def _house_epithets(self) -> Dict[str, str]:
        """Earned epithets by house name (D2); checkpoint-guarded."""
        if not hasattr(self, 'house_epithets'):
            self.house_epithets = {}
        return self.house_epithets

    def _house_grudges(self) -> Dict[Tuple[str, str], int]:
        """(victim_house, traitor_house) -> step of betrayal (D3).
        Never decays per-step: blood remembers what trust forgets."""
        if not hasattr(self, 'house_grudges'):
            self.house_grudges = {}
        return self.house_grudges

    def _house_name(self, colony: Colony) -> str:
        """Display house name with its cadet-generation numeral (D1/D2). The base
        dynasty lives in `colony.house` (kin/grudges match on THAT, shared across a
        bloodline); the display appends the Roman generation ("Vex-Karn II") so a
        living parent and its cadet branch read distinctly instead of colliding as
        "House X trades with House X". gen 1 -> the bare base (house_label identity),
        so every founding house is unchanged. Lazily founds a name for pre-dynasty
        saves."""
        from chronicle import make_house_name, house_label
        if not getattr(colony, 'house', ''):
            colony.house = make_house_name()
            colony.generation = 1
            colony.founded_step = self.step_count
            self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1
        return house_label(colony.house, getattr(colony, 'generation', 1))

    def _house(self, colony: Colony) -> str:
        """Display label: 'Vex-Karn II, the Oath-Broken' (D1/D2)."""
        from chronicle import house_label
        name = self._house_name(colony)
        return house_label(name, getattr(colony, 'generation', 1),
                           self._house_epithets().get(name, ""))

    # ---- Seasons & Stone helpers (SPEC_SEASONS_AND_STONE.md) ----

    def season_index(self) -> int:
        """Derived season 0-3 (T16); never stored."""
        return (self.step_count // SEASON_LENGTH) % 4

    def year(self) -> int:
        return self.step_count // YEAR_LENGTH

    def dole_factor(self) -> float:
        """Seasonal dole factor with the 2-year ramp floor (T17).

        K1 amendment: a keeper drought withholds everything."""
        if getattr(self, 'drought', False):
            return 0.0
        f = DOLE_FACTOR[self.season_index()]
        if not getattr(self, 'harsh', False):
            f = max(f, DOLE_RAMP[min(self.year(), 2)])
        # BI5: a low water budget is a soft drought (1.0 at/above threshold, so
        # the default 0.6 is unchanged); keeper drought above still hard-zeros
        water = getattr(self, 'water_level', WATER_LEVEL_DEFAULT)
        f *= float(np.clip(water / DRY_THRESHOLD, 0.25, 1.0))
        return f

    def in_oasis(self, x: int, y: int) -> bool:
        """Pure positional oasis disc (T22); no state, no pickle surface."""
        cx, cy = self.world.width // 2, self.world.height // 2
        return (x - cx) ** 2 + (y - cy) ** 2 <= OASIS_RADIUS ** 2

    def oasis_holder(self) -> Optional[int]:
        """Colony whose living maw sits on/near the oasis, else None."""
        cx, cy = self.world.width // 2, self.world.height // 2
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            mx, my, _ = colony.maw.position
            if (mx - cx) ** 2 + (my - cy) ** 2 <= (OASIS_RADIUS + 2) ** 2:
                return colony.colony_id
        return None

    # ---- Guppies: the oasis pond ecosystem (SPEC_GUPPIES) --------------------
    def _oasis_food_count(self) -> int:
        """Standing FOOD voxels in the oasis box (approx the disc) — the cap on the shoal's catch."""
        w, h, _ = self.world.dimensions
        cx, cy = w // 2, h // 2
        r = OASIS_RADIUS
        sub = self.world.voxels[max(0, cx - r):cx + r + 1, max(0, cy - r):cy + r + 1, :]
        return int(np.count_nonzero(sub == VoxelType.FOOD.value))

    def _guppy_drama(self, now: float) -> None:
        """Announce pond state transitions (boom / collapse / recovery) — throttled to changes."""
        state = 'boom' if now > 0.7 * GUPPY_CAP else ('gone' if now < 5.0 else 'mid')
        prev = getattr(self, '_guppy_state', None)
        if state != prev:
            self._guppy_state = state
            if state == 'boom':
                self._log_event("The oasis shoals silver with guppies")
            elif state == 'gone':
                self._log_event("The guppy shoal thins to nothing")
            elif prev == 'gone':
                self._log_event("Guppies return to the shallows")

    def _guppy_tick(self) -> None:
        """SPEC_GUPPIES: the oasis pond. Algae grows (sunlight/water), guppies eat + breed, and the
        surplus surfaces as harvestable FOOD voxels in the oasis (a commons any colony forages).
        Gated: GUPPIES_ENABLED default False -> returns immediately (battery byte-identical, no RNG).
        Seeds the pond on first tick so a fresh OR resumed world gains one from the get go."""
        if not GUPPIES_ENABLED or self.step_count % GUPPY_TICK != 0:
            return
        guppy = getattr(self, 'guppy_pop', None)
        if guppy is None:                          # seed the pond
            self.guppy_pop = GUPPY_SEED
            self.algae = ALGAE_SEED
            guppy = GUPPY_SEED
        water = getattr(self, 'water_level', WATER_LEVEL_DEFAULT)
        # Phase 2 diet: crickets washed into the water + crop droppings feed the shoal beyond algae
        extra = getattr(self, '_cricket_influx', 0.0)
        droppings = min(GUPPY_DROPPINGS, 0.01 * len(getattr(self, 'crops', {})))
        guppy, algae, catch = guppy_dynamics(guppy, getattr(self, 'algae', ALGAE_SEED),
                                             water, extra_food=extra + droppings)
        deposited = 0
        if catch > 0:                              # surface the catch as oasis FOOD voxels
            w, h, d = self.world.dimensions
            cx, cy = w // 2, h // 2
            room = max(0, GUPPY_FOOD_CAP - self._oasis_food_count())
            for _ in range(min(catch, room)):
                x = int(np.clip(cx + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, w - 2))
                y = int(np.clip(cy + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, h - 2))
                z = self.world.surface_z(x, y) + 1
                if z < d and self.world.voxels[x, y, z] == VoxelType.AIR.value:
                    self.world.voxels[x, y, z] = VoxelType.FOOD.value
                    deposited += 1
        self.guppy_pop = max(0.0, guppy - deposited)   # only the landed catch leaves the pond
        self.algae = algae
        self._guppy_drama(self.guppy_pop)

    def _cricket_drama(self, now: float) -> None:
        """Announce cricket-swarm boom/collapse transitions (throttled to changes)."""
        state = 'swarm' if now > 0.7 * CRICKET_CAP else ('gone' if now < 4.0 else 'mid')
        prev = getattr(self, '_cricket_state', None)
        if state != prev:
            self._cricket_state = state
            if state == 'swarm':
                self._log_event("Crickets swarm the dunes")
            elif state == 'gone':
                self._log_event("The cricket swarm falls silent")
            elif prev == 'gone':
                self._log_event("Crickets chirp again in the scrub")

    def _spawn_cricket_pack(self) -> None:
        """Spawn a few visible cricket Beasts (ambient neutral prey, NOT an incursion) at a random
        surface spot so the swarm is seen and colonies can hunt them. Capped so they never crowd."""
        if sum(1 for b in self._fauna() if b.species == 'cricket') >= 6:
            return
        _, hp, atk, pack, hunt, bounty = FAUNA['cricket']
        w, h, d = self.world.dimensions
        cx, cy = random.randint(2, w - 3), random.randint(2, h - 3)
        for _ in range(random.randint(*pack)):
            x = int(np.clip(cx + random.randint(-3, 3), 1, w - 2))
            y = int(np.clip(cy + random.randint(-3, 3), 1, h - 2))
            z = min(self.world.surface_z(x, y) + 1, d - 1)
            self._fauna().append(Beast('cricket', (x, y, z), hp, atk, hunt,
                                       bounty, spawned_at=self.step_count))

    def _cricket_tick(self) -> None:
        """SPEC_FOOD_WEB: the terrestrial cricket swarm. Breeds on plant matter, weather-modulated
        (booms dry/Dust, drowns in a flood, dies in the Chill frost); surplus surfaces as harvestable
        land FOOD voxels (map-wide, foraged by any colony). Gated CRICKETS_ENABLED default False ->
        returns immediately (battery byte-identical, no RNG). Seeds on first tick (fresh or resumed)."""
        if not CRICKETS_ENABLED or self.step_count % CRICKET_TICK != 0:
            return
        cricket = getattr(self, 'cricket_pop', None)
        if cricket is None:
            self.cricket_pop = CRICKET_SEED
            cricket = CRICKET_SEED
        step = self.step_count
        season = self.season_index()
        dry = self._is_dry() or season == 2
        flood = getattr(self, 'flood_until', 0) > step
        frost = season == 3 or getattr(self, 'cold_until', 0) > step
        forage = min(1.0, 0.3 + 0.015 * len(getattr(self, 'crops', {})))  # standing plant matter (crops)
        cricket, catch = cricket_dynamics(cricket, forage, dry, flood, frost)
        # fauna cull (predator control): cricket-eating beasts thin the swarm
        predators = sum(1 for b in self._fauna() if b.species in CRICKET_PREDATORS)
        if predators:
            cricket = max(0.0, cricket * (1.0 - min(0.6, CRICKET_CULL * predators)))
        # crickets -> guppies: a slice washes into the water (flood amplifies) -> feeds the shoal
        self._cricket_influx = min(1.0, (cricket / CRICKET_CAP) *
                                   (CRICKET_FLOOD_INFLUX if flood else CRICKET_INFLUX))
        # crickets are a CROP PEST: a big swarm nibbles standing crops (the keeper's seeds feed them)
        crops = getattr(self, 'crops', None)
        if cricket > 0.5 * CRICKET_CAP and crops:
            for pos in random.sample(list(crops), min(len(crops), CRICKET_CROP_DMG)):
                x, y, z = pos
                if self.world.voxels[x, y, z] in (VoxelType.CROP.value, VoxelType.CROP_RIPE.value):
                    self.world.voxels[x, y, z] = VoxelType.TILLED.value
                self.crops.pop(pos, None)
        deposited = 0
        if catch > 0:                               # surface the catch as land FOOD voxels (map-wide)
            w, h, d = self.world.dimensions
            for _ in range(min(catch, CRICKET_FOOD_CAP)):
                x = random.randint(1, w - 2)
                y = random.randint(1, h - 2)
                z = self.world.surface_z(x, y) + 1
                if z < d and self.world.voxels[x, y, z] == VoxelType.AIR.value:
                    self.world.voxels[x, y, z] = VoxelType.FOOD.value
                    deposited += 1
        self.cricket_pop = max(0.0, cricket - deposited)
        if self.cricket_pop > 0.5 * CRICKET_CAP and random.random() < 0.15:
            self._spawn_cricket_pack()              # show the thriving swarm as huntable beasts
        self._cricket_drama(self.cricket_pop)

    def _near_water(self, x: int, y: int) -> bool:
        """True if (x,y) is in/around the oasis — where a snare catches guppies."""
        cx, cy = self.world.width // 2, self.world.height // 2
        return (x - cx) ** 2 + (y - cy) ** 2 <= (OASIS_RADIUS + 3) ** 2

    def _set_snare(self, x: int, y: int, kind: str) -> None:
        """Set a keeper snare (a WEB weir) at the surface — harvested by _snare_tick."""
        z = min(self.world.surface_z(x, y) + 1, self.world.depth - 1)
        if self.world.voxels[x, y, z] == VoxelType.AIR.value:
            self.world.voxels[x, y, z] = VoxelType.WEB.value
        self._log_event(f"The keeper sets a {kind} snare by the water")

    def _snare_tick(self) -> None:
        """SPEC_FOOD_WEB: WEB voxels (spider silk OR a keeper string/toothpick weir) passively catch
        guppies (near water) or crickets (on land) into FOOD — no foraging unit needed. Gated
        SNARES_ENABLED default False -> returns immediately (battery byte-identical, no state)."""
        if not SNARES_ENABLED or self.step_count % SNARE_TICK != 0:
            return
        webs = np.argwhere(self.world.voxels == VoxelType.WEB.value)
        if len(webs) == 0:
            return
        d = self.world.depth
        placed, caught = 0, 0
        for (x, y, z) in webs:
            if placed >= SNARE_FOOD_CAP:
                break
            x, y, z = int(x), int(y), int(z)
            if self._near_water(x, y) and getattr(self, 'guppy_pop', 0.0) > SNARE_YIELD:
                self.guppy_pop -= SNARE_YIELD
            elif getattr(self, 'cricket_pop', 0.0) > SNARE_YIELD:
                self.cricket_pop -= SNARE_YIELD
            else:
                continue
            zz = z + 1                                   # deposit the catch just above the web
            if zz < d and self.world.voxels[x, y, zz] == VoxelType.AIR.value:
                self.world.voxels[x, y, zz] = VoxelType.FOOD.value
                placed += 1
            caught += 1
        if caught and caught != getattr(self, '_snare_logged', -1):
            self._snare_logged = caught
            self._log_event("The snares yield a catch from the shallows")

    # ---- HYDRO: persistent water flow simulation (SPEC_HYDRO) ----------------
    def _water_field(self):
        """The persistent water-DEPTH field (w,h,d float32) — the flow sim's single
        source of truth. Lazily allocated (None until water first appears), so a
        neutral run never touches it and checkpoints stay byte-identical."""
        return getattr(self, 'water', None)

    def _ensure_water_field(self):
        """Allocate the water field on first use; returns it."""
        f = getattr(self, 'water', None)
        if f is None:
            f = np.zeros(self.world.voxels.shape, dtype=np.float32)
            self.water = f
        return f

    def _add_water(self, x: int, y: int, z: int, amount: float):
        """Introduce water at a cell (the test injector / sources). Allocates."""
        f = self._ensure_water_field()
        f[x, y, z] = min(HYDRO_CAP, f[x, y, z] + amount)
        return f

    def _hydro_sources(self):
        """Phase 2: the oasis is a perennial spring — each oasis column is topped
        up to HYDRO_SOURCE_LEVEL just above its ground. The only place the flow sim
        ADDS volume; from here water spreads/drains/evaporates to an equilibrium.
        Allocates the field. Gated by HYDRO_SOURCES_ENABLED."""
        f = self._ensure_water_field()
        w, h, d = self.world.dimensions
        cx, cy = w // 2, h // 2
        r = OASIS_RADIUS
        for x in range(max(0, cx - r), min(w, cx + r + 1)):
            for y in range(max(0, cy - r), min(h, cy + r + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                    continue
                gz = self.world.terrain_z(x, y) + 1
                if 0 <= gz < d:
                    f[x, y, gz] = max(f[x, y, gz], HYDRO_SOURCE_LEVEL)

    def _hydro_passable(self) -> np.ndarray:
        """(w,h,d) bool: cells water may occupy — AIR or already WATER (never
        solid/sand/crop/wall). AIR + WATER are the flow medium."""
        v = self.world.voxels
        return (v == VoxelType.AIR.value) | (v == VoxelType.WATER.value)

    def _flood_damage(self, colony: 'Colony') -> int:
        """HYDRO P6: flood damage a colony's exposed units take. A house that has
        learned to build RESERVOIRS soaks the surge into its basins -> reduced
        damage. Full FLOOD_DAMAGE otherwise (and at neutral, gate off)."""
        if (HYDRO_SOURCES_ENABLED
                and 'reservoir' in getattr(colony, 'techs', ())):
            return max(1, int(FLOOD_DAMAGE * (1.0 - HYDRO_RESERVOIR_ABSORB)))
        return FLOOD_DAMAGE

    def _water_adjacent(self, pos: Tuple[int, int, int]) -> bool:
        """HYDRO P5: is a WATER voxel 6-adjacent to pos (crop irrigation check)?
        Always False when no water exists, so neutral crop growth is unchanged."""
        if getattr(self, 'water', None) is None:
            return False
        x, y, z = pos
        v = self.world.voxels
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                           (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            nx, ny, nz = x + dx, y + dy, z + dz
            if (self.world.in_bounds(nx, ny, nz)
                    and v[nx, ny, nz] == VoxelType.WATER.value):
                return True
        return False

    def _hydro_tick(self):
        """Conservative cellular water update: gravity, lateral pressure
        equalization, edge drain, then mirror to WATER voxels. Pure numpy, ZERO
        RNG — cannot perturb the global stream. Sources/evaporation (which change
        total volume) are Phase 2, gated by HYDRO_SOURCES_ENABLED. Early-returns
        with no water, so a neutral run is untouched and this costs nothing until
        water exists."""
        if HYDRO_SOURCES_ENABLED:
            self._hydro_sources()          # oasis spring tops up (allocates field)
        f = getattr(self, 'water', None)
        if f is None or not f.any():
            return
        w, h, d = self.world.dimensions
        passable = self._hydro_passable()
        zidx = np.arange(d, dtype=np.float32)[None, None, :]
        # (1) GRAVITY: water falls into the passable cell below, capped by HYDRO_CAP.
        for z in range(1, d):
            room = np.maximum(0.0, HYDRO_CAP - f[:, :, z - 1])
            move = np.minimum(f[:, :, z], room) * passable[:, :, z - 1]
            f[:, :, z] -= move
            f[:, :, z - 1] += move
        # (2) LATERAL EQUALIZATION: move water from higher to lower hydraulic head
        # (floor z + depth) into passable ±x/±y neighbours. Symmetric transfer via
        # np.roll conserves total volume exactly. head recomputed per pass.
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            head = zidx + f
            nbr_head = np.roll(head, -shift, axis=axis)
            nbr_pass = np.roll(passable, -shift, axis=axis)
            flow = np.clip(HYDRO_FLOW_RATE * (head - nbr_head) * 0.5, 0.0, None)
            flow = np.minimum(flow, f) * nbr_pass       # bounded by what's here; nbr passable
            f -= flow
            f += np.roll(flow, shift, axis=axis)
        np.minimum(f, HYDRO_CAP, out=f)
        # (3) EVAPORATION (Phase 2): the only volume-remove besides sinks; scaled by
        # dryness so a drought shrinks reservoirs/lakes (gated with sources).
        if HYDRO_SOURCES_ENABLED and HYDRO_EVAP_RATE > 0.0:
            dryness = 1.0 if self._is_dry() else 0.35
            f *= (1.0 - HYDRO_EVAP_RATE * dryness)
        # (4) EDGE SINKS: water at the map boundary drains (the outfall; also
        # absorbs any np.roll wrap-around at the edges).
        f[0, :, :] = 0.0; f[-1, :, :] = 0.0
        f[:, 0, :] = 0.0; f[:, -1, :] = 0.0
        # (4) VOXEL MIRROR: AIR<->WATER by the settle threshold; never overwrite
        # SAND/solid/crop/wall (only AIR becomes WATER, only WATER reverts to AIR).
        v = self.world.voxels
        wet = f >= HYDRO_SETTLE_MIN
        v[wet & (v == VoxelType.AIR.value)] = VoxelType.WATER.value
        v[(~wet) & (v == VoxelType.WATER.value)] = VoxelType.AIR.value

    def _crops(self) -> Dict[Tuple[int, int, int], int]:
        """Sparse crop registry pos -> grow ticks (T19); checkpoint-guarded."""
        if not hasattr(self, 'crops'):
            self.crops = {}
        return self.crops

    def _grow_crops(self):
        """Crop lifecycle tick (T19/T20 behavioral block); purge-first."""
        crops = self._crops()
        season = self.season_index()
        ripe_at = CROP_GROWDUR // CROP_TICK
        for pos in list(crops.keys()):
            x, y, z = pos
            if self.world.voxels[pos] != VoxelType.CROP.value:
                del crops[pos]
                continue
            if (z + 1 < self.world.depth
                    and self.world.voxels[x, y, z + 1] not in
                    (VoxelType.AIR.value, VoxelType.WATER.value)):
                self.world.voxels[pos] = VoxelType.SAND.value  # buried by drift
                del crops[pos]                                 # (water irrigates, not buries)
                continue
            oasis = self.in_oasis(x, y)
            if not oasis:
                if season == 2:      # Dust: stall
                    continue
                if season == 3:      # Chill: the frost takes the young crops
                    self.world.voxels[pos] = VoxelType.SAND.value
                    del crops[pos]
                    owner = int(self.world.ownership[pos])
                    frost_key = (self.year(), owner)
                    if owner >= 0 and getattr(self, '_frost_logged', None) != frost_key:
                        self._frost_logged = frost_key
                        self._log_event(f"The frost takes Colony {owner}'s young crops")
                    continue
            crops[pos] += (OASIS_GROWTH_MULT if oasis
                           else self._biome_growth_units())  # BI5
            # HYDRO P5: a field next to standing water (a channel/reservoir) is
            # irrigated and grows faster. No water at neutral -> no boost -> identity.
            if self._water_adjacent(pos):
                crops[pos] += HYDRO_IRRIG_GROWTH
            if crops[pos] >= ripe_at:
                self.world.voxels[pos] = VoxelType.CROP_RIPE.value
                del crops[pos]

    def _spoil_surface_food(self):
        """Dust-season spoilage of exposed FOOD (T16)."""
        food_positions = np.argwhere(self.world.voxels == VoxelType.FOOD.value)
        d = self.world.depth
        for x, y, z in food_positions:
            if z + 1 < d and self.world.voxels[x, y, z + 1] == VoxelType.AIR.value:
                if random.random() < SPOIL_CHANCE:
                    self.world.voxels[x, y, z] = VoxelType.AIR.value

    # ---- Timber, Bone & Flame helpers (SPEC_TIMBER_AND_FLAME.md) ----

    def _rot(self) -> Dict[Tuple[int, int, int], int]:
        """Palisade rot registry pos -> expiry step (T43); checkpoint-guarded."""
        if not hasattr(self, 'rot'):
            self.rot = {}
        return self.rot

    def _fires(self) -> Dict[Tuple[int, int, int], int]:
        """Active fire cells pos -> remaining burn ticks (T45); guarded."""
        if not hasattr(self, 'fires'):
            self.fires = {}
        return self.fires

    def _ignite(self, pos: Tuple[int, int, int]):
        """Set a flammable voxel alight (T45); non-flammables shrug it off."""
        if self.world.voxels[pos] in FLAMMABLE_VOXELS:
            self._fires().setdefault(pos, FIRE_BURN)

    def _fire_tick(self):
        """T45 behavioral block: damage -> spread -> burn down -> burn out.

        Burnout leaves SAND (AIR for silk), purging crop/rot registries so
        nothing grows or rots inside a scar. Firebreaks are emergent: fire
        only crosses FLAMMABLE_VOXELS.
        """
        fires = self._fires()
        fire_set = set(fires)
        for colony in self.colonies:
            for unit in colony.units[:]:
                x, y, z = unit.position
                near = any((x + dx, y + dy, z + dz) in fire_set
                           for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           for dz in (-1, 0, 1))
                if near and unit.take_damage(FIRE_DAMAGE, 0.0):
                    colony.remove_unit(unit)
                    self.world.set_voxel(*unit.position, VoxelType.CORPSE)
        for pos in list(fires):
            if self.world.voxels[pos] not in FLAMMABLE_VOXELS:
                del fires[pos]  # harvested/buried out from under the flame
                continue
            for nx, ny, nz in self.world.get_neighbors_3d(pos, radius=1):
                npos = (nx, ny, nz)
                if (self.world.voxels[npos] in FLAMMABLE_VOXELS
                        and npos not in fires
                        and random.random() < FIRE_SPREAD_P):
                    fires[npos] = FIRE_BURN
            fires[pos] -= 1
            if fires[pos] <= 0:
                burned = self.world.voxels[pos]
                self.world.voxels[pos] = (
                    VoxelType.AIR.value if burned == VoxelType.WEB.value
                    else VoxelType.SAND.value)
                self._crops().pop(pos, None)
                self._rot().pop(pos, None)
                del fires[pos]
        if (len(fires) >= 6 and self.step_count
                - getattr(self, '_wildfire_logged', -10**9) > SEASON_LENGTH):
            self._wildfire_logged = self.step_count
            self._log_event("Wildfire races across the terrarium!")

    def _chop_step(self, unit: SandKing, colony: Colony) -> bool:
        """T41: walk to the nearest trunk, cut for CHOP_TIME, then fell it."""
        target = getattr(unit, 'chop_target', None)
        if (target is not None
                and self.world.voxels[target] != VoxelType.WOOD.value):
            target = unit.chop_target = None
        if target is None:
            x, y, z = unit.position
            r = colony.genome.foraging_range
            w, h, d = self.world.dimensions
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            y0, y1 = max(0, y - r), min(h, y + r + 1)
            box = self.world.voxels[x0:x1, y0:y1, :]
            hits = np.argwhere(box == VoxelType.WOOD.value)
            if not len(hits):
                return False
            best = min(hits, key=lambda p: (abs(int(p[0]) + x0 - x)
                                            + abs(int(p[1]) + y0 - y)
                                            + abs(int(p[2]) - z)))
            target = (int(best[0]) + x0, int(best[1]) + y0, int(best[2]))
            unit.chop_target = target
            unit.chop_progress = 0
        x, y, z = unit.position
        if max(abs(target[0] - x), abs(target[1] - y),
               abs(target[2] - z)) > 1:
            return self._step_toward(unit, target, colony)
        unit.chop_progress = getattr(unit, 'chop_progress', 0) + 1
        if unit.chop_progress >= CHOP_TIME:
            self._fell_tree(target, unit, colony)
            unit.chop_target = None
            unit.chop_progress = 0
        return True

    def _fell_tree(self, base: Tuple[int, int, int], unit: SandKing,
                   colony: Colony):
        """T41: the cut trunk joins the wood store; the crown falls away
        from the chopper, laying up to FELL_LENGTH trunks into open AIR
        at the cut height - a felled palm spanning a gap IS a bridge.
        Crown voxels with nowhere to fall also land in the store.
        """
        x, y, z = base
        crown = []
        cz = z + 1
        while (cz < self.world.depth
               and self.world.voxels[x, y, cz] == VoxelType.WOOD.value):
            crown.append((x, y, cz))
            cz += 1
        self.world.voxels[base] = VoxelType.AIR.value
        self._credit_labor(unit, colony, 'wood', 1)
        ux, uy, _ = unit.position
        dx = int(np.sign(x - ux)) or random.choice([-1, 1])
        dy = int(np.sign(y - uy))
        laid = 0
        for i, cpos in enumerate(crown, start=1):
            self.world.voxels[cpos] = VoxelType.AIR.value
            lx, ly = x + dx * i, y + dy * i
            if (laid < FELL_LENGTH and self.world.in_bounds(lx, ly, z)
                    and self.world.voxels[lx, ly, z] == VoxelType.AIR.value):
                self.world.voxels[lx, ly, z] = VoxelType.WOOD.value
                laid += 1
            else:
                self._credit_labor(unit, colony, 'wood', 1)
        self._milestone(colony, 'felled',
                        f"Colony {colony.colony_id} fells its first palm",
                        unit)

    def _palisade_step(self, unit: SandKing, colony: Colony) -> bool:
        """T43: wall the maw - one WOOD_WALL on the ring per wood spent."""
        mx, my, mz = colony.maw.position
        r = PALISADE_RING
        best, best_dist = None, None
        ux, uy, uz = unit.position
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                pos = (mx + dx, my + dy, mz)
                if not self.world.in_bounds(*pos):
                    continue
                if self.world.voxels[pos] != VoxelType.AIR.value:
                    continue
                dist = abs(pos[0] - ux) + abs(pos[1] - uy) + abs(pos[2] - uz)
                if best_dist is None or dist < best_dist:
                    best, best_dist = pos, dist
        if best is None:
            return False
        if max(abs(best[0] - ux), abs(best[1] - uy), abs(best[2] - uz)) <= 1:
            colony.wood -= 1
            self.world.voxels[best] = VoxelType.WOOD_WALL.value
            self.world.ownership[best] = colony.colony_id
            # TE10: masonry raises walls that endure longer
            dur = int(WALL_ROT * (1 + MASON_WALL_BONUS
                                  * self._prof(colony, 'masonry')))
            self._rot()[best] = self.step_count + dur
            self._practice(colony, 'masonry')  # TE7: raising walls
            self._milestone(colony, 'palisade',
                            f"Colony {colony.colony_id} raises palisades"
                            " around its maw", unit)
            return True
        return self._step_toward(unit, best, colony)

    # ---- The Keeper (SPEC_KEEPER.md K1-K12) ----

    def _manna(self) -> Set[Tuple[int, int, int]]:
        """Keeper-dropped FOOD positions awaiting attribution (K3)."""
        if not hasattr(self, 'keeper_manna'):
            self.keeper_manna = set()
        return self.keeper_manna

    def _carvings(self) -> Dict[Tuple[int, int, int], str]:
        """Symbols inscribed in the sand (K4); purge-first like crops."""
        if not hasattr(self, 'carvings'):
            self.carvings = {}
        return self.carvings

    def _update_sentiment(self, colony: Colony) -> str:
        """F1/F2: drift the colony's devotion to the keeper and return the
        carved sentiment band. Souring is gradual - the early warning.

        Reverence/manna lifts it; wrath, drought, or starvation curdles it
        (faster than it heals); absence drifts it toward neutral. The first
        turn to 'hateful' is chronicled (F3) - look to your faces."""
        att = self.keeper_attitude(colony)
        s = getattr(colony, 'keeper_sentiment', 0.5)
        starving = colony.maw.food_stored < 2 * BOOTSTRAP_FLOOR
        if att == 'wrathful' or getattr(self, 'drought', False) or starving:
            s -= SENTIMENT_SOUR
        elif att == 'reverent':
            s += SENTIMENT_RECOVER
        else:
            s += SENTIMENT_DRIFT * (1 if s < 0.5 else -1)
        # NOTE: favoritism does NOT nudge keeper_sentiment. The faces arc
        # (SPEC_FACES) already moves sentiment from the same feed/drought
        # treatment, so a DP6 favoritism term would double-count and desync the
        # faces calibration. Favoritism's role is to drive confidence (DP2), which
        # a favoured colony already shows on its face via the normal sentiment path.
        colony.keeper_sentiment = float(np.clip(s, 0.0, 1.0))
        # the BAND tracks the (gradual) favor scalar so souring is VISIBLE
        # devout -> wary -> hateful over time; wrath/drought only accelerate
        # the decay above, they do not slam the band ("look to your faces")
        if colony.keeper_sentiment < 0.33:
            band = 'hateful'
        elif colony.keeper_sentiment > 0.66:
            band = 'devout'
        else:
            band = 'wary'
        if band == 'hateful' and not getattr(colony, '_sentiment_wrath', False):
            colony._sentiment_wrath = True
            self._log_event(f"The carvings of House"
                            f" {self._house_name(colony)} curdle into a"
                            " hateful mask")
        elif band == 'devout':
            colony._sentiment_wrath = False  # re-arm the warning
        return band

    def _nature_mood(self, colony: Colony) -> str:
        """AW2: a pre-breach colony's read of unexplained FORCES, not a keeper.
        bounty (fed/full/spring-fed) | lean | dread. Local plenty resists
        dread - a house on its own oasis with a full hoard does not despair
        just because the wider dole failed (providence favours the resourceful)."""
        step = self.step_count
        food = colony.maw.food_stored
        mx, my, _ = colony.maw.position
        # LOCAL plenty: a full hoard, or sitting on the oasis (its own spring)
        provided = food > 4 * BOOTSTRAP_FLOOR or self.in_oasis(mx, my)
        # acute violence of nature is always dread, even for the rich
        acute = any(getattr(self, a, 0) > step for a in (
            'cold_until', 'arena_cold_until', 'arena_heat_until',
            'flood_until', 'hail_until', 'storm_until'))
        starving = food < 2 * BOOTSTRAP_FLOOR
        if acute or starving:
            return 'dread'
        if provided or self.keeper_attitude(colony) == 'reverent':
            return 'bounty'  # it has its own; the dry wider world is not dread
        if self._is_dry():
            return 'dread'  # no reserves AND the rains have failed
        return 'lean'

    def _reveal(self, colony: Colony):
        """AW4: the 13th-Floor moment - at breakout the colony learns there is
        an outside, a 'great other', the hand that fed and starved it. Its
        opening stance toward the now-known god is seeded by how it was treated
        as nature. Fires once."""
        if getattr(colony, 'revelation', False):
            return
        colony.revelation = True
        colony.keeper_sentiment = {'bounty': 0.7, 'lean': 0.5,
                                   'dread': 0.3}[self._nature_mood(colony)]
        self._log_event(f"House {self._house_name(colony)} glimpses the world"
                        " beyond the glass - and knows the hand that fed"
                        " and starved it")

    # DISPOSITION ARC (SPEC_DISPOSITION DP1-DP12): keeper treatment → confidence,
    # favoritism, agitation. Identity at neutral defaults.

    def _disposition_grace(self, colony: Colony, dfav: float):
        """DP3: kind treatment raises favoritism. Clamped. No RNG."""
        if colony is None or not colony.is_alive():
            return
        colony.favoritism = float(np.clip(
            getattr(colony, 'favoritism', 0.0) + dfav, -1.0, 1.0))

    def _disposition_wrath(self, colony: Colony, dfav: float, dagit: float):
        """DP3/DP4: cruel/startling treatment lowers favoritism and spikes agitation.
        dfav is subtracted (pass the positive magnitude). Clamped. No RNG."""
        if colony is None or not colony.is_alive():
            return
        colony.favoritism = float(np.clip(
            getattr(colony, 'favoritism', 0.0) - dfav, -1.0, 1.0))
        colony.agitation = float(np.clip(
            getattr(colony, 'agitation', 0.0) + dagit, 0.0, 1.0))

    def _disposition_nearest(self, x: int, y: int) -> Optional[Colony]:
        """DP3: nearest LIVING colony to (x,y) by maw manhattan distance; None if none."""
        best, best_d = None, float('inf')
        for c in self.colonies:
            if not c.is_alive():
                continue
            mx, my, _ = c.maw.position
            d = abs(mx - x) + abs(my - y)
            if d < best_d:
                best_d, best = d, c
        return best

    def _disposition_confidence_target(self, colony: Colony) -> float:
        """DP2: pure target for the boldness meter from material condition. 0.5 for an
        ordinary colony (every term 0); >0.5 thriving, <0.5 distressed. No RNG."""
        step = self.step_count
        food = colony.maw.food_stored
        n = len(colony.units)
        fav = getattr(colony, 'favoritism', 0.0)
        # prosperity signals — zero in ordinary condition, saturate at extremes
        surplus_frac = _clamp01((food - CONF_RICH_FOOD) / CONF_RICH_FOOD)
        pop_frac = _clamp01((n - CONF_POP_REF) / CONF_POP_REF)
        won_recent = 1.0 if (step - getattr(colony, 'last_victory_step', -10**9)
                             < CONF_WIN_WINDOW) else 0.0
        # distress signals — zero in ordinary condition
        starving = 1.0 if food < 2 * BOOTSTRAP_FLOOR else 0.0
        acute = any(getattr(self, a, 0) > step for a in (
            'cold_until', 'arena_cold_until', 'arena_heat_until',
            'flood_until', 'hail_until', 'storm_until'))
        threatened = 1.0 if (getattr(colony, 'at_war', False) or acute) else 0.0
        target = (0.5
                  + CONF_W_SURPLUS * surplus_frac
                  + CONF_W_POP * pop_frac
                  + CONF_W_WIN * won_recent
                  + CONF_W_FAV * fav
                  - CONF_W_STARVE * starving
                  - CONF_W_THREAT * threatened)
        return float(np.clip(target, 0.0, 1.0))

    def _disposition_tick(self):
        """DP2: move each living colony's confidence toward its material target
        with inertia; decay favoritism (medium) and agitation (fast) toward neutral.
        Pure — consumes NO RNG, always-on (no breached gate)."""
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            c = getattr(colony, 'confidence', 0.5)
            tgt = self._disposition_confidence_target(colony)
            colony.confidence = float(np.clip(c + CONF_RATE * (tgt - c), 0.0, 1.0))
            # favoritism decays toward 0 (multiplicative — never overshoots)
            colony.favoritism = float(np.clip(
                getattr(colony, 'favoritism', 0.0) * FAV_RETAIN, -1.0, 1.0))
            # agitation decays fast toward 0
            colony.agitation = float(np.clip(
                getattr(colony, 'agitation', 0.0) * AGIT_RETAIN, 0.0, 1.0))

    def _aggression_eff(self, colony: Colony) -> float:
        """DP5: effective aggression = base * f(confidence) + hostility(agitation).
        f(0.5) == 1.0 and hostility(0) == 0.0, so this equals genome.aggression
        EXACTLY at neutral. Pure; no RNG. May exceed 1.0 (a bold colony 'grown dominant')."""
        base = getattr(colony.genome, 'aggression', 0.5)
        conf = getattr(colony, 'confidence', 0.5)
        ag = getattr(colony, 'agitation', 0.0)
        return base * (1.0 + CONF_AGG_K * (conf - 0.5)) + AGIT_HOSTILITY * ag

    def _disposition_boldness(self, colony: Colony) -> float:
        """DP7: force-EV multiplier from the extractor's boldness. 1.0 at
        confidence 0.5; >1 bold (force nets more), <1 meek (wage preferred). Pure."""
        conf = getattr(colony, 'confidence', 0.5)
        return 1.0 + BARGAIN_CONF_K * (conf - 0.5)

    def keeper_attitude(self, colony: Colony) -> str:
        """K3: derived, never stored. none | reverent | wrathful."""
        if getattr(self, 'drought', False) and getattr(colony, 'worshipped',
                                                       False):
            return 'wrathful'
        if (self.step_count - getattr(colony, 'keeper_fed_step', -10**9)
                < KEEPER_MEMORY):
            return 'reverent'
        return 'none'

    def keeper_drop_food(self, x: int, y: int):
        """K1: the keeper's hand - manna, locally attributable."""
        if self._hand_stayed():  # PS5: the bound god cannot feed
            return
        placed = 0
        for _ in range(40):
            px = int(np.clip(x + random.randint(-2, 2), 1,
                             self.world.width - 2))
            py = int(np.clip(y + random.randint(-2, 2), 1,
                             self.world.height - 2))
            pz = min(self.world.surface_z(px, py) + 1, self.world.depth - 1)
            if self.world.voxels[px, py, pz] == VoxelType.AIR.value:
                self.world.voxels[px, py, pz] = VoxelType.FOOD.value
                self._manna().add((px, py, pz))
                placed += 1
                if placed >= KEEPER_DROP_FOOD:
                    break
        self._log_event("The keeper's hand scatters bounty")
        # DP3: grace to the nearest colony
        self._disposition_grace(self._disposition_nearest(x, y), FAV_MANNA)

    def keeper_release(self, species: str):
        """K1: introduce a garage creature - above the one-incursion rule."""
        if self._hand_stayed():  # PS5: the bound god cannot loose predators
            return
        if species not in KEEPER_FAUNA and species != 'cat':  # AR2 (+ apex cat)
            return
        _, hp, atk, pack, hunt, bounty = FAUNA[species]
        w, h, d = self.world.dimensions
        edge = random.choice(['n', 's', 'e', 'w'])
        for _ in range(random.randint(*pack)):
            if edge == 'n':
                x, y = random.randint(2, w - 3), 2
            elif edge == 's':
                x, y = random.randint(2, w - 3), h - 3
            elif edge == 'w':
                x, y = 2, random.randint(2, h - 3)
            else:
                x, y = w - 3, random.randint(2, h - 3)
            z = min(self.world.surface_z(x, y) + 1, d - 1)
            self._fauna().append(Beast(species, (x, y, z), hp, atk, hunt,
                                       bounty, spawned_at=self.step_count))
        self._log_event(FAUNA_EVENTS[species])
        # DP3: wrath/startle for threat species (not food species)
        if species in ('scorpion', 'spider', 'rodent', 'hornets'):
            for c in self.colonies:
                self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)

    def keeper_release_cat(self):
        self.keeper_release('cat')
        # DP3: wrath/startle for cat threat
        for c in self.colonies:
            self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)

    def keeper_drought(self, on: bool):
        """K1: withhold the dole. The garden learns what the god is."""
        if on and self._hand_stayed():  # PS5: the bound god cannot inflict
            return
        was = getattr(self, 'drought', False)
        self.drought = on
        if on and not was:
            self._log_event("The keeper withholds the dole - drought!")
            # the carvings curdle on their own as sentiment sours (F3);
            # no instant twist here anymore - the souring is gradual.
            # DP3: wrath (no startle) to all colonies on drought switch-on
            for c in self.colonies:
                self._disposition_wrath(c, FAV_DROUGHT, 0.0)
        elif was and not on:
            self._log_event("The rains of the keeper return")

    def keeper_temperature(self, direction: str):
        """AR3: crank the arena temperature - uncomfortable, never lethal.
        direction in {'heat','cold'}; the bound god (PS5) cannot."""
        if self._hand_stayed():
            return
        until = self.step_count + ARENA_TEMP_DURATION
        if direction == 'heat':
            self.arena_heat_until = until
            self._log_event("The keeper turns the air to a blistering heat")
        elif direction == 'cold':
            self.arena_cold_until = until
            self._log_event("The keeper turns the air to a biting cold")
        # DP3: wrath/startle to all colonies for temperature extremes
        for c in self.colonies:
            self._disposition_wrath(c, FAV_WRATH, AGIT_SPIKE)

    def keeper_ignite(self, x: int, y: int):
        """Arena/SimCity disaster: light a firecracker - a bang and a flash that
        sets the flammable alight and scorches units caught in the blast. Real
        chaos, not tank-ending. The bound god (PS5) cannot."""
        if self._hand_stayed():
            return
        r = FIRECRACKER_RADIUS
        w, h, d = self.world.dimensions
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                px = int(np.clip(x + dx, 1, w - 2))
                py = int(np.clip(y + dy, 1, h - 2))
                z = self.world.surface_z(px, py)
                if 0 <= z < d and self.world.voxels[px, py, z] in FLAMMABLE_VOXELS:
                    self._ignite((px, py, z))
                zz = z + 1  # crops/wood sitting just above the surface
                if zz < d and self.world.voxels[px, py, zz] in FLAMMABLE_VOXELS:
                    self._ignite((px, py, zz))
        for colony in self.colonies:
            for unit in colony.units[:]:
                ux, uy, _ = unit.position
                if (abs(ux - x) <= r and abs(uy - y) <= r
                        and self._exposed(unit)
                        and unit.take_damage(FIRECRACKER_DAMAGE, 0.0)):
                    colony.remove_unit(unit)
                    self.world.set_voxel(*unit.position, VoxelType.CORPSE)
        self._log_event("The keeper lights a firecracker - a bang and a flash!")
        # DP3: wrath/startle to colonies with units in blast radius
        for colony in self.colonies:
            for unit in colony.units:
                ux, uy, _ = unit.position
                if abs(ux - x) <= r and abs(uy - y) <= r:
                    self._disposition_wrath(colony, FAV_WRATH, AGIT_SPIKE)
                    break

    def keeper_material(self, kind: str, x: int, y: int):
        """TE13: drop a raw MATERIAL. Tacks scatter as loose caltrops; every
        other material is reshaped into a tool by the NEAREST house IF it has
        the enabling tech - otherwise it is inert scrap."""
        if self._hand_stayed() or kind not in MATERIALS:
            return
        if kind == 'tacks':
            self._scatter_caltrops(x, y)
            return
        # SPEC_FOOD_WEB Phase 3: string/toothpick set by the water become a SNARE (weir) that catches
        # guppies, instead of being crafted into a weapon.
        if SNARES_ENABLED and kind in ('string', 'toothpick') and self._near_water(x, y):
            self._set_snare(x, y, kind)
            return
        best, bestd = None, None
        for c in self.colonies:
            if not c.is_alive():
                continue
            d = (c.maw.position[0] - x) ** 2 + (c.maw.position[1] - y) ** 2
            if bestd is None or d < bestd:
                best, bestd = c, d
        if best is not None:
            self._claim_material(best, kind)

    def _claim_material(self, colony: Colony, kind: str):
        """TE13: the craft - material + the right tech becomes a tool."""
        if not hasattr(colony, 'crafted'):
            colony.crafted = set()
        made = []
        for (mat, tech), item in CRAFT_RECIPES.items():
            if (mat == kind and tech in getattr(colony, 'techs', set())
                    and item not in colony.crafted):
                colony.crafted.add(item)
                made.append(item)
                eff = CRAFTED_EFFECTS[item]
                if 'tech' in eff:  # e.g. a copper-pipe cannon unlocks the siege
                    self._grant_tech(colony, eff['tech'])
                    colony.tech_xp[eff['tech']] = max(
                        colony.tech_xp.get(eff['tech'], 0.0), TECH_LEARN_XP)
        house = self._house_name(colony)
        if made:
            self._log_event(f"House {house} crafts {', '.join(made)}"
                            f" from the {kind}")
        else:
            self._log_event(f"House {house} turns the {kind} over - inert"
                            " scrap, without the craft")

    def _scatter_caltrops(self, x: int, y: int):
        """TE13: loose caltrops the maws can reposition (area denial)."""
        if not hasattr(self, 'caltrops'):
            self.caltrops = set()
        w, h, d = self.world.dimensions
        for _ in range(CALTROP_COUNT):
            px = int(np.clip(x + random.randint(-2, 2), 1, w - 2))
            py = int(np.clip(y + random.randint(-2, 2), 1, h - 2))
            z = self.world.surface_z(px, py)
            if 0 <= z < d:
                self.caltrops.add((px, py, z))
        self._log_event("The keeper scatters tacks across the sand - caltrops!")

    def _caltrop_tick(self):
        """TE13: a unit that stands on a loose caltrop is pricked."""
        caltrops = getattr(self, 'caltrops', None)
        if not caltrops:
            return
        for colony in self.colonies:
            for unit in colony.units[:]:
                if (tuple(unit.position) in caltrops and self._exposed(unit)
                        and unit.take_damage(CALTROP_DAMAGE, 0.0)):
                    colony.remove_unit(unit)
                    self.world.set_voxel(*unit.position, VoxelType.CORPSE)

    def keeper_water(self, x: int, y: int, big: bool = False):
        """HH1: pour water. A small pour irrigates; a large pour floods -
        terraforming (raised banks / dug channels) steers it. Bound god can't."""
        if self._hand_stayed():
            return
        self.kw_center = (int(x), int(y))
        self.kw_big = bool(big)
        self.kw_until = self.step_count + (WATER_FLOOD_DUR if big
                                           else WATER_RAIN_DUR)
        self._log_event("The keeper looses a deluge over the sands" if big
                        else "The keeper's rain waters the sands")

    def keeper_seed(self, x: int, y: int):
        """HH3: scatter seeds - sand/tilled becomes crop the colonies tend."""
        if self._hand_stayed():
            return
        planted = 0
        for _ in range(SEED_COUNT):
            px = int(np.clip(x + random.randint(-2, 2), 1, self.world.width - 2))
            py = int(np.clip(y + random.randint(-2, 2), 1, self.world.height - 2))
            pz = self.world.surface_z(px, py)
            if not (0 <= pz < self.world.depth):
                continue
            if self.world.voxels[px, py, pz] in (VoxelType.SAND.value,
                                                 VoxelType.TILLED.value):
                self.world.voxels[px, py, pz] = VoxelType.CROP.value
                self._crops()[(px, py, pz)] = 0
                planted += 1
        if planted:
            self._log_event("The keeper scatters seeds across the sand")

    def keeper_set_water(self, level: float):
        """BI2: dial the reservoir behind the glass. NOT hand-gated - even a
        bound terrarium cannot reach the diffuser panel."""
        self.water_target = float(np.clip(level, 0.0, 1.0))

    def keeper_set_sun(self, hours: float):
        """BI2: set the hours of daylight (the panel; survives the turning)."""
        self.sun_hours = float(np.clip(hours, SUN_MIN, SUN_MAX))

    def _is_dry(self) -> bool:
        """BI5: the single dryness predicate - a keeper drought OR a low water
        budget. Feeds the dole, the nature mood, and the emergent weather."""
        return (getattr(self, 'drought', False)
                or getattr(self, 'water_level', WATER_LEVEL_DEFAULT)
                < DRY_THRESHOLD)

    def _biome_growth_units(self) -> int:
        """BI5: non-oasis crop growth per tick from the water+sun budget."""
        if self._is_dry() or getattr(self, 'sun_effective', getattr(self, 'sun_hours',
                                     SUN_HOURS_DEFAULT)) < SUN_COLD:
            return 0  # drought or dark: the field stalls
        water = getattr(self, 'water_level', WATER_LEVEL_DEFAULT)
        sun = getattr(self, 'sun_effective', getattr(self, 'sun_hours', SUN_HOURS_DEFAULT))
        if water > WET_THRESHOLD and SUN_COLD < sun < SUN_HOT:
            return 2  # lush
        return 1

    def _sun_z(self) -> float:
        """SP10: normalized daylight z = (sun_effective - rolling mean)/rolling sd.
        Pure read exposed for future regime logic + display; consumed by nobody yet."""
        se = getattr(self, 'sun_effective', getattr(self, 'sun_hours', SUN_HOURS_DEFAULT))
        m = getattr(self, 'sun_ema_mean', SUN_HOURS_DEFAULT)
        s = getattr(self, 'sun_ema_sd', 0.0)
        return (se - m) / max(EPS_POWER, s)

    def _biome_tick(self):
        """BI3/BI4: the closed water cycle and the weather that emerges from it.
        Water eases toward an equilibrium set by the reservoir and the sun;
        extremes spill floods, bake heat, or bring a chill."""
        # SP5: draw the EFFECTIVE daylight ONCE per biome-day so every reader in
        # this day sees the same sky. Identity at SUN_JITTER_SD==0 (no RNG draw).
        if self.step_count == 1 or self.step_count % BIOME_TICK == 0:
            # SP10: oscillator swings the daily mean (mean-only); jitter draws the day's sky.
            day = self.step_count // BIOME_TICK
            _sun_mean = getattr(self, 'sun_hours', SUN_HOURS_DEFAULT) \
                + SUN_OSC_AMP * math.sin(2.0 * math.pi * day / SUN_OSC_PERIOD)
            self.sun_effective = jitter(
                mean=_sun_mean, sd=SUN_JITTER_SD, lo=SUN_MIN, hi=SUN_MAX)
            # SP10: EMA observer (pure, no RNG) — mean first, then |dev| off the new mean.
            self.sun_ema_mean = SUN_EMA_ALPHA * self.sun_effective \
                + (1.0 - SUN_EMA_ALPHA) * getattr(self, 'sun_ema_mean', SUN_HOURS_DEFAULT)
            self.sun_ema_sd = SUN_EMA_ALPHA * abs(self.sun_effective - self.sun_ema_mean) \
                + (1.0 - SUN_EMA_ALPHA) * getattr(self, 'sun_ema_sd', 0.0)
        target = getattr(self, 'water_target', WATER_LEVEL_DEFAULT)
        sun = getattr(self, 'sun_effective', getattr(self, 'sun_hours', SUN_HOURS_DEFAULT))
        water = getattr(self, 'water_level', WATER_LEVEL_DEFAULT)
        equilibrium = float(np.clip(
            target - SUN_DRYING * (sun - SUN_HOURS_DEFAULT) / SUN_HOURS_DEFAULT,
            0.0, 1.0))
        self.water_level = float(np.clip(
            water + BIOME_EASE * (equilibrium - water), 0.0, 1.0))
        step = self.step_count
        if step % BIOME_TICK or not step:
            return
        w = self.water_level
        if (w > WET_THRESHOLD and getattr(self, 'flood_until', 0) <= step
                and random.random() < BIOME_FLOOD_CHANCE):
            self.flood_until = step + FLOOD_DURATION
            self.flood_cells = set()
            self._log_event("The swollen reservoir overflows - the basin floods")
        if (self._is_dry() and sun >= SUN_HOT
                and getattr(self, 'arena_heat_until', 0) <= step
                and random.random() < BIOME_HEAT_CHANCE):
            self.arena_heat_until = step + ARENA_TEMP_DURATION
            self._log_event("The low water bakes the sands - a heat rises")
        if (sun <= SUN_COLD and getattr(self, 'arena_cold_until', 0) <= step
                and random.random() < BIOME_COLD_CHANCE):
            self.arena_cold_until = step + ARENA_TEMP_DURATION
            self._log_event("The long night brings a creeping cold")

    def keeper_gift(self, kind: Optional[str] = None,
                    pos: Optional[Tuple[int, int]] = None):
        """K9a: the technology ladder - year-gated at 2**(n+1)-1 for rung n."""
        if self._hand_stayed():  # PS5: the bound god cannot gift
            return
        if not hasattr(self, 'gifts_given'):
            self.gifts_given = []
        given = self.gifts_given

        # Resolve the target rung and its index n
        if kind is None:
            # Sequential: take the next unclaimed rung
            n = len(given)
            if n >= len(GIFT_LADDER):
                return  # ladder exhausted
            kind = GIFT_LADDER[n]
        else:
            # Explicit kind: validate it's in GIFT_LADDER and not already given
            if kind not in GIFT_LADDER:
                return
            if kind in given:
                return  # already given
            n = GIFT_LADDER.index(kind)

        # Year-unlock gate: rung n unlocks at year 2**(n+1)-1
        if self.year() < 2**(n+1) - 1:
            return

        # Once-per-year gate: only one gift per year
        if getattr(self, 'last_gift_year', -1) == self.year():
            return

        # Dispense: append to gifts_given and place artifact
        self.gifts_given.append(kind)
        self.last_gift_year = self.year()
        w, h = self.world.width, self.world.height
        x, y = pos if pos is not None else (
            random.randint(w // 4, 3 * w // 4),
            random.randint(h // 4, 3 * h // 4))
        z = min(self.world.surface_z(x, y) + 1, self.world.depth - 1)
        self.gift = ((x, y, z), kind)
        self._log_event("A strange gift descends from above")

    def keeper_open_door(self, colony: Colony):
        """BRK-C/K10: the keeper's mercy - lift the glass for one house.
        Mirrors every keeper verb: honors the PS5 bound-god gate first, so a
        bound keeper's hand will not move. Then breaches via _escape (AW4
        reveal + EN2 enlightenment). Idempotent on an already-breached colony.

        Preconditions: colony is a living Colony (or None -> no-op).
        Failure modes: bound keeper -> no-op + stayed line; already breached
        -> no-op (no duplicate flavor line).
        """
        if self._hand_stayed():        # PS5: the bound god cannot act
            return
        if colony is None or not colony.is_alive() or getattr(colony, 'breached', False):
            return
        self._log_event(f"The keeper opens the door - House "
                        f"{self._house_name(colony)} is invited to step through")
        self._escape(colony)           # AW4 reveal + EN2 enlightenment; sets breached

    def converse(self, colony_id: int, text: str) -> Dict[str, object]:
        """DL3: the human speaks to a colony; the awakened answer in the
        shared vocabulary, shaped by disposition and environment."""
        colony = self._colony_by_id(colony_id)
        if colony is None or not colony.is_alive():
            return {"understood": False, "heard": None, "reply": ""}
        if not getattr(colony, 'breached', False):
            self._log_event("The keeper speaks, but the words fall as noise")
            return {"understood": False, "heard": None, "reply": ""}
        from dialogue import DIALOGUE_NUDGE, compose_reply, interpret
        heard = interpret(text)
        # the awakened hear (K12 speak anchor) and take grace by word
        if colony.units:
            colony.units[0].spoken_to_step = self.step_count
        colony.keeper_fed_step = self.step_count
        # gentle persuasion: the human can teach through talk (bounded)
        nudge_map = {'ally': 'loyalty', 'war': 'aggression',
                     'home': 'patience', 'defense': 'defense_investment',
                     'gratitude': 'loyalty', 'love': 'loyalty',
                     'trade': ('fertility', 'loyalty'),  # DL7b: two attrs
                     'thrall': 'aggression',
                     'ascend': 'plasticity'}
        attr_or_tuple = nudge_map.get(heard)
        if attr_or_tuple:
            g = colony.genome
            # Normalize string to tuple for uniform handling
            attrs = attr_or_tuple if isinstance(attr_or_tuple, tuple) else (attr_or_tuple,)
            for attr in attrs:
                cur = getattr(g, attr, 0.5)
                setattr(g, attr, float(np.clip(cur + DIALOGUE_NUDGE, 0.0, 1.0)))
        reply = compose_reply(colony, self, heard)
        self._monitor(colony.colony_id).log_decision(
            self.step_count, f"House {self._house_name(colony)}",
            f"answered the god: {reply}", heard)
        return {"understood": True, "heard": heard, "reply": reply}

    def keeper_speak(self, unit: SandKing) -> bool:
        """K12: the keeper addresses one creature. Returns heard?"""
        colony = self._colony_by_id(unit.colony_id)
        if colony is None:
            return False
        if not getattr(colony, 'breached', False):
            self._log_event("The keeper speaks, but the words fall as noise")
            return False
        unit.spoken_to_step = self.step_count
        colony.keeper_fed_step = self.step_count  # grace by word (K12)
        if not getattr(colony, '_heard_logged', False):
            colony._heard_logged = True
            self._log_event(f"The keeper SPEAKS - and House"
                            f" {self._house_name(colony)} hears")
        self._monitor(colony.colony_id).log_decision(
            self.step_count, self._unit_label(unit),
            "heard the god speak", getattr(unit, 'thought', None))
        return True

    def _keeper_tick(self):
        """K4/K8/K9/K10 phase: carvings, the auto script, gift claims."""
        step = self.step_count
        # K4 carvings: each house writes one symbol per interval
        if step % CARVE_INTERVAL == 0 and step:
            carv = self._carvings()
            for pos in list(carv):
                if self.world.voxels[pos] != VoxelType.SAND.value:
                    del carv[pos]  # disturbed sand forgets
            for colony in self.colonies:
                if not colony.is_alive():
                    continue
                # AW1: keeper-directed feeling only once aware of the great
                # other (breached); before that, the mood of raw nature.
                if getattr(colony, 'breached', False):
                    symbol = CARVE_SYMBOLS[self._update_sentiment(colony)]
                else:
                    symbol = NATURE_SYMBOLS[self._nature_mood(colony)]
                mx, my, _ = colony.maw.position
                for _try in range(12):
                    cx = int(np.clip(mx + random.randint(-3, 3), 1,
                                     self.world.width - 2))
                    cy = int(np.clip(my + random.randint(-3, 3), 1,
                                     self.world.height - 2))
                    cz = self.world.surface_z(cx, cy)
                    if (0 <= cz < self.world.depth
                            and self.world.voxels[cx, cy, cz]
                            == VoxelType.SAND.value):
                        carv[(cx, cy, cz)] = symbol
                        break
        # K9/K10 gift claim: the first house to touch it learns
        gift = getattr(self, 'gift', None)
        if gift is not None:
            (gx, gy, gz), kind = gift
            for colony in self.colonies:
                claimed = False
                for unit in colony.units:
                    ux, uy, uz = unit.position
                    if max(abs(ux - gx), abs(uy - gy), abs(uz - gz)) <= 1:
                        self._claim_gift(colony, kind, unit)
                        claimed = True
                        break
                if claimed:
                    self.gift = None
                    break
        # K8: the autoplayed keeper (the Outer Limits script)
        if not getattr(self, 'keeper_auto', True):
            return
        if step == KEEPER_CAT_STEP and not getattr(self, 'cat_sent', False):
            self.cat_sent = True
            self._log_event("The keeper's cat slips into the terrarium...")
            self.keeper_release_cat()
        grief_until = getattr(self, 'keeper_grief_until', 0)
        if grief_until > step:
            if step % 400 == 0:
                self._log_event("The keeper, grieving, sends scorpions"
                                " instead of crickets")
                self.keeper_release('scorpion')
        elif grief_until and getattr(self, 'drought', False):
            self.keeper_drought(False)  # grief spent; the rains return
            self.keeper_grief_until = 0
            mx = self.world.width // 2
            my = self.world.height // 2
            self.keeper_drop_food(mx, my)  # the relenting miracle
        # AW5: a FLOURISHING (recently-fed) colony draws the operator's hand -
        # gated on fortune, not on pre-breach worship (which no longer exists)
        # K9a: year gate enforced inside keeper_gift
        if (self.keeper_attitude_any('reverent')
                and getattr(self, 'gift', None) is None
                and len(getattr(self, 'gifts_given', [])) < len(GIFT_LADDER)):
            self.keeper_gift()

    def keeper_attitude_any(self, wanted: str) -> bool:
        return any(self.keeper_attitude(c) == wanted
                   for c in self.colonies if c.is_alive())

    def _grant_tech(self, colony: Colony, tech: str):
        """TE3: mark a technology known to a house (idempotent; logs once)."""
        if not hasattr(colony, 'techs'):
            colony.techs = set()
        if tech in colony.techs:
            return
        colony.techs.add(tech)
        kind = TECH_REGISTRY.get(tech, {}).get('kind', 'native')
        if kind == 'native':
            self._log_event(f"House {self._house_name(colony)} learns {tech}")

    def _practice(self, colony: Colony, tech: str,
                  amount: float = TECH_PRACTICE_XP):
        """TE7: learning by doing - raise proficiency; learn at the threshold."""
        if not hasattr(colony, 'tech_xp'):
            colony.tech_xp = {}
        if getattr(colony, 'enlightened', False):  # EN4
            amount = amount * ENLIGHTENED_TECH_MULT
        xp = min(1.0, colony.tech_xp.get(tech, 0.0) + amount)
        colony.tech_xp[tech] = xp
        if xp >= TECH_LEARN_XP and tech not in getattr(colony, 'techs', set()):
            self._grant_tech(colony, tech)

    def _tech_tick(self):
        """TE8/TE9: observe a neighbor's works, and spend grains on research."""
        alive = [c for c in self.colonies if c.is_alive()]
        for colony in alive:
            # TE8 observe: learn a native tech a nearby house knows and you lack
            mx, my, _ = colony.maw.position
            best = None  # (weight, tech)
            for other in alive:
                if other is colony:
                    continue
                ox, oy, _ = other.maw.position
                if max(abs(mx - ox), abs(my - oy)) > TECH_OBSERVE_RANGE:
                    continue
                from politics import hostile as _hostile
                if _hostile(self, colony.colony_id, other.colony_id):
                    weight = 0.25
                elif self._are_allied(colony.colony_id, other.colony_id):
                    weight = 1.0
                else:
                    weight = 0.5
                for tech in getattr(other, 'techs', ()):  # only native diffuses
                    if (TECH_REGISTRY.get(tech, {}).get('kind') == 'native'
                            and colony.tech_xp.get(tech, 0.0) < TECH_LEARN_XP
                            and (best is None or weight > best[0])):
                        best = (weight, tech)
            if best is not None:
                self._practice(colony, best[1], TECH_OBSERVE_XP * best[0])
            # TE9 grains: buy research for a tech you are partway to (the sink)
            if getattr(colony, 'currency', 0.0) >= TECH_GRAIN_COST:
                partial = [t for t, xp in colony.tech_xp.items()
                           if 0.0 < xp < TECH_LEARN_XP
                           and TECH_REGISTRY.get(t, {}).get('kind') == 'native']
                if partial:
                    tech = partial[0]
                    colony.currency -= TECH_GRAIN_COST
                    self._practice(colony, tech, TECH_GRAIN_XP)
                    self._log_event(f"House {self._house_name(colony)} pours"
                                    f" grains into {tech}")
            # TE11 research: a tech whose PREREQS are all known develops on its
            # own (you can't practice gunpowder - it emerges from fire + metal)
            for t, spec in TECH_REGISTRY.items():
                prereq = spec.get('prereq')
                if (prereq and t not in colony.techs
                        and all(p in getattr(colony, 'techs', ()) for p in prereq)):
                    self._practice(colony, t, TECH_RESEARCH_XP)

    def _prof(self, colony: Colony, tech: str) -> float:
        """TE10: a colony's proficiency in a tech (0..1; 0 if unknown)."""
        return getattr(colony, 'tech_xp', {}).get(tech, 0.0)

    def _catapult_tick(self):
        """TE11: a house with the catapult tech and a war target HURLS a shot
        across the board - maw damage on impact, a splash blast, and fire where
        it lands. The visible siege ('seeing things shot across the board')."""
        if self.step_count % CATAPULT_RELOAD or not self.step_count:
            return
        diplomacy = getattr(self, 'diplomacy', None)
        if diplomacy is None:
            return
        w, h, d = self.world.dimensions
        for colony in self.colonies:
            if (not colony.is_alive()
                    or 'catapult' not in getattr(colony, 'techs', ())):
                continue
            target_id = diplomacy.war_target.get(colony.colony_id)
            target = self._colony_by_id(target_id) if target_id is not None else None
            if target is None or not target.is_alive():
                continue
            mx, my, _ = colony.maw.position
            tx, ty, _ = target.maw.position
            if max(abs(tx - mx), abs(ty - my)) > CATAPULT_RANGE:
                continue
            dmg = int(round(CATAPULT_DAMAGE * (0.5 + 0.5 * self._prof(
                colony, 'catapult'))))
            target.maw.take_damage(dmg)
            s = CATAPULT_SPLASH
            for other in self.colonies:  # the blast catches whoever is under it
                for unit in other.units[:]:
                    ux, uy, _ = unit.position
                    if (max(abs(ux - tx), abs(uy - ty)) <= s
                            and unit.take_damage(FIRE_DAMAGE, 0.0)):
                        other.remove_unit(unit)
                        self.world.set_voxel(*unit.position, VoxelType.CORPSE)
            for dx in range(-s, s + 1):  # fire where the shot lands
                for dy in range(-s, s + 1):
                    px = int(np.clip(tx + dx, 1, w - 2))
                    py = int(np.clip(ty + dy, 1, h - 2))
                    z = self.world.surface_z(px, py)
                    if 0 <= z < d and self.world.voxels[px, py, z] in FLAMMABLE_VOXELS:
                        self._ignite((px, py, z))
            self._log_event(f"House {self._house_name(colony)}'s catapult hurls"
                            " a shot across the sands!")

    def _plunder_techs(self, fallen: Colony):
        """T3 conquest-steal: the aggressor at war with a fallen house seizes
        its technology (currently only its ore spilled). Run BEFORE the slot's
        treaties are cleared, so the war target is still known."""
        fallen_techs = set(getattr(fallen, 'techs', set()))
        diplomacy = getattr(self, 'diplomacy', None)
        if not fallen_techs or diplomacy is None:
            return
        victor = None
        for other in self.colonies:
            if (other is not fallen and other.is_alive()
                    and diplomacy.war_target.get(other.colony_id) == fallen.colony_id):
                victor = other
                break
        if victor is None:
            return
        # DP2: record the victory step for confidence target calculation
        victor.last_victory_step = self.step_count
        stolen = fallen_techs - set(getattr(victor, 'techs', set()))
        for t in stolen:
            self._grant_tech(victor, t)
            victor.tech_xp[t] = max(victor.tech_xp.get(t, 0.0), TECH_LEARN_XP)
        if stolen:
            self._log_event(f"House {self._house_name(victor)} plunders the"
                            f" secrets of fallen House {self._house_name(fallen)}")

    def _barter_tech(self, a: Colony, b: Colony):
        """T3 barter: a truce is sealed with a gift of knowledge - the tech-
        richer house shares ONE technology the other lacks (a peace dividend)."""
        atech = set(getattr(a, 'techs', set()))
        btech = set(getattr(b, 'techs', set()))
        giver, taker, share = (a, b, atech - btech) if len(atech) >= len(btech) \
            else (b, a, btech - atech)
        share = {t for t in share
                 if TECH_REGISTRY.get(t, {}).get('kind') == 'native'}
        if not share:
            return
        tech = sorted(share)[0]
        self._grant_tech(taker, tech)
        taker.tech_xp[tech] = max(taker.tech_xp.get(tech, 0.0), TECH_LEARN_XP)
        self._log_event(f"House {self._house_name(giver)} shares {tech} with"
                        f" House {self._house_name(taker)} to seal the peace")

    def _are_allied(self, a: int, b: int) -> bool:
        """Ally latch between two colonies (TE8 weighting)."""
        diplomacy = getattr(self, 'diplomacy', None)
        if diplomacy is None:
            return False
        return bool(diplomacy.allied.get(frozenset((a, b)), False))

    def _claim_gift(self, colony: Colony, kind: str, unit: SandKing):
        """K9/TE3: revelation by artifact - the foreign ladder advances the arc
        and grants the technology (abacus/watch/calculator/pi)."""
        from machines import Controller, PI_DURABILITY, PI_FUEL
        house = self._house_name(colony)
        self._grant_tech(colony, kind)  # TE3: the gift IS the tech
        if kind == 'abacus':
            if getattr(colony, 'machine_arc', 'none') == 'none':
                colony.machine_arc = 'known'
            self._log_event(f"House {house} slides the abacus beads - and counts")
        elif kind == 'watch':
            if getattr(colony, 'machine_arc', 'none') == 'none':
                colony.machine_arc = 'known'
            self._log_event(f"House {house} puzzles over the ticking gift")
        elif kind == 'calculator':
            if getattr(colony, 'machine_arc', 'none') == 'none':
                colony.machine_arc = 'known'
            if not isinstance(getattr(colony, 'controllers', None), list):
                colony.controllers = []
            colony.controllers.append(Controller(colony.colony_id))
            if colony.machine_arc == 'known':
                colony.machine_arc = 'claimed'
            self._log_event(f"House {house}'s fingers find the"
                            " calculator's keys")
        else:  # pi: the god-brain
            if not isinstance(getattr(colony, 'controllers', None), list):
                colony.controllers = []
            colony.controllers.append(Controller(
                colony.colony_id, fuel=PI_FUEL, durability=PI_DURABILITY))
            if getattr(colony, 'machine_arc', 'none') in ('none', 'known'):
                colony.machine_arc = 'claimed'
            self._log_event(f"House {house} awakens the god-brain")
        # DP3: grace to the colony that claimed the gift
        self._disposition_grace(colony, FAV_GIFT)
        self._monitor(colony.colony_id).log_decision(
            self.step_count, self._unit_label(unit),
            f"claimed the {kind}", getattr(unit, 'thought', None))

    def _set_stage(self, colony: Colony, stage: int):
        """MT4: promote a colony's metamorphosis stage and raise its brain
        ceiling accordingly (size -> intelligence)."""
        colony.stage = stage
        # AW/MT: metamorphosis is PHYSICAL only - growing into the new breed no
        # longer grants awareness of the keeper. Only the true breakout past the
        # glass (_escape, reached by terminal mastery) meets the "great other".
        ceiling = STAGE_CEILING.get(stage, 88)
        if getattr(colony.genome, 'brain_ceiling', 88) < ceiling:
            colony.genome.brain_ceiling = ceiling

    def _escape(self, colony: Colony):
        """AW/K10: the ONE true breakout - past the glass into the sandbox,
        where the maw meets the 'great other'. Reached only by terminal mastery
        (metamorphosis does NOT lead here). Grants keeper-awareness and gives
        the new-breed body if it hasn't molted yet. Fires once."""
        if getattr(colony, 'breached', False):
            return
        colony.breached = True
        self._set_stage(colony, max(2, getattr(colony, 'stage', 1)))
        self._reveal(colony)  # AW4: it now knows the hand that fed and starved it

        # ---- Enlightenment burst (EN2, EN6, EN7) ----
        if not getattr(colony, 'enlightened', False):
            colony.enlightened = True
            if getattr(colony.genome, 'brain_ceiling', 88) < ENLIGHTENED_CEILING:
                colony.genome.brain_ceiling = ENLIGHTENED_CEILING
            self._log_event(
                f"House {self._house_name(colony)} ascends - the light of the "
                "Enlightenment breaks over it")

    def _metamorphosis_tick(self):
        """MT2/MT3: molt to the new breed (stage 2) once the maw is large
        enough - cruelty accelerates it - and to Shade (stage 3) once a
        machine-mastered colony grows further."""
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            stage = getattr(colony, 'stage', 1)
            pop = len(colony.units)
            food = colony.maw.food_stored
            age = self.step_count - getattr(colony, 'founded_step', 0)
            if stage < 2:
                # cruelty (low sentiment) lowers the threshold (MT2)
                f = 0.6 + 0.4 * getattr(colony, 'keeper_sentiment', 0.5)
                if (pop >= MOLT_POP * f or food >= MOLT_FOOD * f
                        or age >= MOLT_AGE * f):
                    self._set_stage(colony, 2)
                    self._log_event(f"The mobiles of House"
                                    f" {self._house_name(colony)} split open"
                                    " - a new breed emerges")
            elif stage == 2:
                mastered = (getattr(colony, 'terminal_uses', 0)
                            >= TERMINAL_MASTERY)
                if mastered and (pop >= SHADE_POP or food >= SHADE_FOOD):
                    self._set_stage(colony, 3)
                    self._log_event(f"House {self._house_name(colony)} reaches"
                                    " the Shade stage - sentient, and no"
                                    " longer needs its god")

    def _psionic_tick(self):
        """PS1/PS3/PS4: the awakened maws project emotion onto the keeper,
        that projection biases his cruelty, and a hateful Shade turns the
        terrarium on its god."""
        total = 0.0
        turned_by = None
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            stage = getattr(colony, 'stage', 1)
            # AW: only a maw that has truly BROKEN OUT (met the great other) can
            # reach the keeper's mind - a merely-molted new breed cannot project
            if not getattr(colony, 'breached', False):
                continue  # (PS1, re-gated on the real breakout, not the molt)
            weight = STAGE_PROJECTION.get(stage, 0.0)
            size = min(1.0, len(colony.units) / PSIONIC_SIZE_REF)
            sentiment = getattr(colony, 'keeper_sentiment', 0.5)
            valence = 2.0 * sentiment - 1.0  # hateful -> dread, devout -> calm
            total += weight * size * valence
            # PS4: the first Shade to curdle to hatred binds the god
            if (stage >= 3 and sentiment <= PSIONIC_TURN_SENT
                    and turned_by is None):
                turned_by = self._house_name(colony)
        self.keeper_influence = float(np.clip(total, -1.0, 1.0))
        if turned_by is not None and not getattr(self, 'keeper_bound', False):
            self.keeper_bound = True
            self.keeper_bound_by = turned_by
            self._hand_stayed_logged = False
            self._log_event(f"The terrarium turns on its god - House"
                            f" {turned_by} binds the keeper's hand")
        # PS3: a strong projected dread drives the auto-keeper to withhold
        if (getattr(self, 'keeper_auto', True)
                and self.keeper_influence <= PSIONIC_DREAD
                and not getattr(self, 'drought', False)):
            self.keeper_drought(True)

    def keeper_influence_word(self) -> str:
        """PS2: banded descriptor of the terrarium's projection (or '')."""
        inf = getattr(self, 'keeper_influence', 0.0)
        if inf <= -0.5:
            return "a hunger not your own"
        if inf <= -PSIONIC_FLOOR:
            return "a creeping dread"
        if inf >= 0.5:
            return "an unearned calm"
        if inf >= PSIONIC_FLOOR:
            return "a faint contentment"
        return ""

    def _hand_stayed(self) -> bool:
        """PS5: True if the keeper is bound; log the refusal once per turning.
        A bound keeper's intervention verbs no-op."""
        if not getattr(self, 'keeper_bound', False):
            return False
        if not getattr(self, '_hand_stayed_logged', False):
            self._hand_stayed_logged = True
            self._log_event("Your hand will not move - the terrarium holds it")
        return True

    def _codex(self) -> 'Codex':
        """Lazy read-only library (CX5); derived from files, not pickled."""
        if not hasattr(self, 'codex') or self.codex is None:
            from codex import Codex
            self.codex = Codex()
        return self.codex

    def _can_read(self, colony: Colony) -> bool:
        """CX4: awakened, or holding a raspberry-pi controller."""
        from machines import VM_FUEL
        if getattr(colony, 'breached', False):
            return True
        return any(getattr(c, 'fuel_cap', VM_FUEL) > VM_FUEL
                   for c in getattr(colony, 'controllers', None) or [])

    def _codex_tick(self):
        """CX4: each reader consults with its concerns and extracts a lesson."""
        from codex import apply_lesson
        from hive_mind_monitor import instincts_for
        readers = [c for c in self.colonies if c.is_alive() and self._can_read(c)]
        if not readers:
            return
        codex = self._codex()
        for colony in readers:
            probe = colony.units[0] if colony.units else None
            words = instincts_for(probe, colony, self) if probe is not None \
                else ["survival"]
            _passage, lesson = codex.consult(words)
            if lesson is None:
                continue
            scale = ENLIGHTENED_CODEX_MULT if getattr(colony, 'enlightened', False) else 1.0  # EN5
            apply_lesson(colony.genome, lesson, scale)
            if not hasattr(self, '_codex_logged'):
                self._codex_logged = set()
            house = self._house_name(colony)
            if house not in self._codex_logged:
                self._codex_logged.add(house)
                self._log_event(f"House {house} reads the codex and"
                                f" learns to {lesson}")
            # the reading shows on the sand (K4 machine glyph)
            mx, my, _ = colony.maw.position
            cz = self.world.surface_z(mx - 2, my)
            if (0 <= cz < self.world.depth and self.world.voxels[mx - 2, my, cz]
                    == VoxelType.SAND.value):
                self._carvings()[(mx - 2, my, cz)] = CARVE_SYMBOLS['machine']

    def _telemetry(self) -> 'Telemetry':
        """Lazy telemetry collector (TL1); pickles with the sim."""
        if not hasattr(self, 'telemetry') or self.telemetry is None:
            from telemetry import Telemetry
            self.telemetry = Telemetry()
        return self.telemetry

    def _house_grains(self) -> Dict[str, float]:
        """Lifetime grains produced by each house (CU1); guarded."""
        if not hasattr(self, 'house_grains'):
            self.house_grains = {}
        return self.house_grains

    # ---- Wage Market (SPEC_WAGES WG1-WG10): labor, tech licenses, and goods contracts ----

    def _wage_contracts(self) -> list:
        """Contract store: lazy per-sim list of plain dicts (WG1b). Mirrors _house_grains pattern."""
        if not hasattr(self, 'wage_contracts'):
            self.wage_contracts = []
        return self.wage_contracts

    def _goods_axis(self, factor: str) -> str:
        """Map goods sink names to endowment axes (WG2/WG4 bug fix).
        Ore goods ('ore:copper'/'ore:gold') both map to 'ore' endowment axis.
        Food and wood map to themselves. Labor and tech already use 'labor' and 'tech'."""
        return 'ore' if factor.startswith('ore:') else factor

    def _factor_endowment(self, colony) -> dict:
        """Scarce-factor vector. Pure read; getattr-guarded (WG2)."""
        free = sum(1 for u in colony.units if getattr(u, 'laboring_for', -1) < 0)
        ore = getattr(colony, 'ore', {}) or {}
        techs = getattr(colony, 'techs', set()) or set()
        return {
            'labor': float(free),
            'food': float(colony.maw.food_stored),
            'ore': float(ore.get('copper', 0) + ore.get('gold', 0)),
            'wood': float(getattr(colony, 'wood', 0)),
            'tech': float(sum(1 for t in techs if t in TECH_FOREIGN)),
        }

    def _complementarity(self, seller, buyer, factor_axis: str) -> float:
        """> 0 => seller SURPLUS, buyer DEFICIT in `factor_axis` (a trade opportunity) (WG2)."""
        es = self._factor_endowment(seller)[factor_axis]
        eb = self._factor_endowment(buyer)[factor_axis]
        denom = es + eb
        return 0.0 if denom <= 0.0 else (es - eb) / denom

    def _marginal_value(self, colony, factor_axis: str) -> float:
        """Grain value of ONE unit of `factor_axis` to `colony`: scarce => worth more (WG2)."""
        endow = self._factor_endowment(colony)[factor_axis]
        return MV_BASE / (1.0 + endow)

    def _labor_w(self, seller, buyer) -> float:
        """Labor share `w` (seller's retained output share). Reuses M1's w_bargain (WG3a)."""
        pr = composite_power(seller) / max(EPS_POWER, composite_power(buyer))  # birth/extractor
        endow_b = self._factor_endowment(buyer)
        desperation = _clamp01(1.0 - endow_b['labor'] / DESPERATION_LABOR_REF)  # buyer's labor hunger
        control = _clamp01(endow_b['tech'] / CONTROL_TECH_REF)                 # buyer's scarce-factor grip
        w = w_bargain(pr, desperation, control)
        return max(W_CONTRACT_MIN, min(1.0 - W_CONTRACT_MIN, w))   # voluntary & thrall-distinct

    def _factor_price(self, seller, buyer, factor_axis: str) -> float:
        """Grain fee (buyer -> seller per settlement interval) (WG3b)."""
        mv_s = self._marginal_value(seller, factor_axis)   # seller's reservation (low: abundant)
        mv_b = self._marginal_value(buyer, factor_axis)    # buyer's willingness (high: scarce)
        pr = composite_power(seller) / max(EPS_POWER, composite_power(buyer))
        share = _clamp01(WAGE_POWER_SHARE_BASE + WAGE_POWER_SHARE_SENS * (pr - 1.0))
        return mv_s + share * (mv_b - mv_s)     # seller reservation .. buyer willingness

    def _has_contract(self, buyer_id, seller_id, kind, factor) -> bool:
        """De-dup check: True if a live contract of this kind/factor already exists for this ordered pair (WG4)."""
        for c in self._wage_contracts():
            if (c['alive'] and c['kind'] == kind and c['factor'] == factor and
                c['buyer_id'] == buyer_id and c['seller_id'] == seller_id):
                return True
        return False

    def _seller_has(self, seller, axis_kind: str, volume: int) -> bool:
        """True if seller holds >= volume of the good (WG7)."""
        if axis_kind == 'food':
            return seller.maw.food_stored >= volume
        elif axis_kind.startswith('ore:'):
            ore = getattr(seller, 'ore', {}) or {}
            metal = axis_kind.split(':')[1]
            return ore.get(metal, 0) >= volume
        elif axis_kind == 'wood':
            return getattr(seller, 'wood', 0) >= volume
        return False

    def _debit(self, target, kind: str, amount):
        """Inverse of _deposit: reduce target's sink by amount, guarded non-negative (WG7)."""
        if kind == 'ore:copper':
            ore = getattr(target, 'ore', {}) or {}
            ore['copper'] = max(0, ore.get('copper', 0) - int(amount))
        elif kind == 'ore:gold':
            ore = getattr(target, 'ore', {}) or {}
            ore['gold'] = max(0, ore.get('gold', 0) - int(amount))
        elif kind == 'salvage':
            target.salvage = max(0, getattr(target, 'salvage', 0) - int(amount))
        elif kind in ('food', 'crop'):
            target.maw.food_stored = max(0.0, target.maw.food_stored - amount)
        elif kind == 'wood':
            target.wood = max(0, getattr(target, 'wood', 0) - int(amount))

    def _select_free_labor(self, seller):
        """Select up to LABOR_MAX_UNITS free seller unit_ids WITHOUT binding them.
        Fix A: selection is pure so an open-sweep that fails the liquidity gate does
        not leak bound units. Binding happens only after the contract commits
        (_bind_selected_labor)."""
        picked = []
        for u in seller.units:
            if len(picked) >= LABOR_MAX_UNITS:
                break
            if getattr(u, 'laboring_for', -1) < 0:            # only free units
                picked.append(u.unit_id)
        return picked

    def _bind_selected_labor(self, unit_ids, seller, buyer, w):
        """Bind already-selected free units to a COMMITTED labor contract (WG5).
        Virtual: no migration (F3); wage_ratio > 0 marks voluntary labor (WG11b)."""
        ids = set(unit_ids)
        for u in seller.units:
            if u.unit_id in ids and getattr(u, 'laboring_for', -1) < 0:
                u.laboring_for = buyer.colony_id
                u.wage_ratio = w

    def _effective_foreign_techs(self, colony) -> set:
        """Own foreign gifts UNION gifts licensed-IN. Read-only; colony.techs untouched (WG6)."""
        own = {t for t in getattr(colony, 'techs', set()) if t in TECH_FOREIGN}
        if not WAGE_ENABLED:
            return own                                   # default-neutral: no view expansion
        licensed = {c['factor'] for c in self._wage_contracts()
                    if c['kind'] == 'license' and c['buyer_id'] == colony.colony_id
                    and c['alive'] and not c['suspended']}
        return own | licensed

    def _license_yield_mult(self, colony) -> float:
        """Productivity multiplier from LICENSED-IN foreign gifts only. 1.0 for owners and when disabled (WG6)."""
        if not WAGE_ENABLED:
            return 1.0
        own = {t for t in getattr(colony, 'techs', set()) if t in TECH_FOREIGN}
        rented = self._effective_foreign_techs(colony) - own    # licensed-in only
        mult = 1.0
        for t in rented:
            mult *= LICENSE_TECH_MULT.get(t, 1.0)
        return mult

    def _ship_goods(self, contract, seller, buyer):
        """Move `volume` units of `factor` from seller to buyer (WG7)."""
        axis_kind = contract['factor']
        v = contract['volume']
        if not self._seller_has(seller, axis_kind, v):   # seller solvent in the good
            return False                                 # non-viable this interval (WG10)
        self._debit(seller, axis_kind, v)                # mirror of _deposit; never below 0
        self._deposit(buyer, axis_kind, v)               # reuse M1 _deposit
        return True

    def _settle(self, contract):
        """Grain transfer, escrow/prepay, non-negativity (WG8)."""
        buyer = self._colony_by_id(contract['buyer_id'])
        seller = self._colony_by_id(contract['seller_id'])
        if buyer is None or seller is None or not buyer.is_alive() or not seller.is_alive():
            contract['alive'] = False
            return          # dead party -> close (WG10)
        # 1. PAY OUT the escrow the buyer prepaid last interval (grains: transfer, no mint)
        pay = contract['escrow']
        contract['escrow'] = 0.0
        seller.currency = getattr(seller, 'currency', 0.0) + pay
        self._house_grains()[self._house_name(seller)] = \
            self._house_grains().get(self._house_name(seller), 0.0) + pay   # mirror CU1 ledger
        # 2. deliver this interval's goods (WG7) if a goods contract
        delivered = True
        if contract['kind'] == 'goods':
            delivered = self._ship_goods(contract, seller, buyer)
        # 3. PREPAY next interval (liquidity gate; non-negativity via refuse-if-poor)
        fee = contract['fee']
        if getattr(buyer, 'currency', 0.0) >= fee and delivered:
            buyer.currency -= fee
            contract['escrow'] = fee
            contract['nonviable'] = 0
        else:
            contract['nonviable'] = contract['nonviable'] + 1   # WG10 close counter

    def _wage_settle_all(self):
        """Settle all live non-suspended contracts (WG8). Called every SETTLEMENT_INTERVAL steps."""
        for contract in self._wage_contracts():
            if contract['alive'] and not contract['suspended']:
                self._settle(contract)

    def _wage_renegotiate(self):
        """Renegotiate sticky w/fee for live non-suspended contracts (WG9)."""
        for contract in self._wage_contracts():
            if not contract['alive'] or contract['suspended']:
                continue
            seller = self._colony_by_id(contract['seller_id'])
            buyer = self._colony_by_id(contract['buyer_id'])
            if seller is None or buyer is None:
                continue
            # Recompute fee from current endowments/power
            if contract['kind'] == 'labor':
                fee = WAGE_GRAIN_RATE * self._factor_price(seller, buyer, 'labor') * contract['volume']
            elif contract['kind'] == 'license':
                fee = LICENSE_FEE_BASE * self._factor_price(seller, buyer, 'tech') / MV_BASE
            else:  # goods
                fee = self._factor_price(seller, buyer,
                                         self._goods_axis(contract['factor'])) * contract['volume']
            contract['fee'] = max(0.0, fee)
            # Re-stamp labor unit wages
            if contract['kind'] == 'labor':
                neww = self._labor_w(seller, buyer)
                contract['w'] = neww
                for unit_id in contract['unit_ids']:
                    for u in seller.units:
                        if u.unit_id == unit_id and getattr(u, 'laboring_for', -1) == buyer.colony_id:
                            u.wage_ratio = neww
            contract['last_reneg'] = self.step_count

    def _pair_at_war(self, a, b) -> bool:
        """True if a and b are at war (WG10)."""
        d = self._diplomacy()
        return (d.war_target.get(a.colony_id) == b.colony_id
                or d.war_target.get(b.colony_id) == a.colony_id)

    def _revert_labor(self, contract):
        """Free every bound laborer WITHOUT any subjugation/defiance ever applying (WG10)."""
        seller = self._colony_by_id(contract['seller_id'])
        if seller is None:
            return
        for unit_id in contract['unit_ids']:
            for u in seller.units:
                if u.unit_id == unit_id and getattr(u, 'laboring_for', -1) == contract['buyer_id']:
                    u.laboring_for = -1        # back to free; production reverts via _credit_labor free path
                    u.wage_ratio = 0.0         # no residual share
        contract['unit_ids'] = []

    def _wage_suspend_close(self):
        """Suspend contracts on war, close on dead party or persistent non-viability (WG10)."""
        for contract in self._wage_contracts():
            if not contract['alive']:
                continue
            buyer = self._colony_by_id(contract['buyer_id'])
            seller = self._colony_by_id(contract['seller_id'])
            if buyer is None or seller is None or not buyer.is_alive() or not seller.is_alive():
                # Dead party -> close
                self._revert_labor(contract)
                if buyer is not None and buyer.is_alive():
                    buyer.currency = getattr(buyer, 'currency', 0.0) + contract['escrow']
                contract['escrow'] = 0.0
                contract['alive'] = False
                continue
            # Check for war entry
            if self._pair_at_war(buyer, seller) and not contract['suspended']:
                contract['suspended'] = True
                self._revert_labor(contract)
                buyer.currency = getattr(buyer, 'currency', 0.0) + contract['escrow']
                contract['escrow'] = 0.0
                continue
            # Check for peace return and resume (handled by _wage_open_sweep)
            # Check for persistent non-viability
            if contract['nonviable'] >= NONVIABLE_LIMIT:
                self._revert_labor(contract)
                if buyer is not None and buyer.is_alive():
                    buyer.currency = getattr(buyer, 'currency', 0.0) + contract['escrow']
                contract['escrow'] = 0.0
                contract['alive'] = False

    def _wage_open_sweep(self):
        """Deterministic OPEN sweep: for each unordered PEACE pair and each factor axis, at most one new contract per tick (WG4)."""
        if not WAGE_ENABLED:
            return  # never reached; tick already gated, but include for clarity
        # Enumerate all unordered pairs of colonies
        for i, seller in enumerate(self.colonies):
            for buyer in self.colonies[i+1:]:
                # Try both directions (seller-buyer and buyer-seller)
                for seller_cand, buyer_cand in [(seller, buyer), (buyer, seller)]:
                    if self._pair_at_war(seller_cand, buyer_cand):
                        continue    # peace only
                    if (getattr(self, 'bargain_enabled', False)
                            and self._bargain_mode(seller_cand, buyer_cand) != BARGAIN_MODE_WAGE):
                        continue    # M4 routes only WAGE pairs into the market
                    # Try each factor kind
                    for kind in ['labor', 'license', 'goods']:
                        if kind == 'labor':
                            factor_axes = ['labor']
                        elif kind == 'license':
                            factor_axes = [t for t in getattr(seller_cand, 'techs', set()) if t in TECH_FOREIGN]
                        else:  # goods
                            factor_axes = ['food', 'ore:copper', 'ore:gold', 'wood']
                        for factor_axis in factor_axes:
                            if self._has_contract(buyer_cand.colony_id, seller_cand.colony_id, kind, factor_axis):
                                continue   # de-dup (WG1 Guarantee)
                            # Endowment axis per kind: labor->'labor'; license->'tech'
                            # (factor_axis is a gift NAME); goods map ore:* -> 'ore'
                            if kind == 'license':
                                endow_axis = 'tech'
                            elif kind == 'goods':
                                endow_axis = self._goods_axis(factor_axis)
                            else:  # labor
                                endow_axis = factor_axis
                            comp = self._complementarity(seller_cand, buyer_cand, endow_axis)
                            if comp < COMPLEMENTARITY_THRESHOLD:
                                continue    # no trade opportunity
                            # License seller must HOLD the tech
                            if kind == 'license' and factor_axis not in getattr(seller_cand, 'techs', set()):
                                continue
                            # Compute fee per kind
                            if kind == 'labor':
                                w = self._labor_w(seller_cand, buyer_cand)
                                unit_ids = self._select_free_labor(seller_cand)  # Fix A: select only, bind after commit
                                volume = len(unit_ids)
                                fee = WAGE_GRAIN_RATE * self._factor_price(seller_cand, buyer_cand, 'labor') * volume if volume > 0 else 0
                            elif kind == 'license':
                                volume = 1
                                w = 0.0
                                unit_ids = []
                                fee = LICENSE_FEE_BASE * self._factor_price(seller_cand, buyer_cand, 'tech') / MV_BASE
                            else:  # goods
                                surplus_units = self._factor_endowment(seller_cand)[endow_axis]
                                volume = min(GOODS_VOLUME_CAP, int(surplus_units))
                                if volume <= 0:
                                    continue  # no surplus
                                w = 0.0
                                unit_ids = []
                                fee = self._factor_price(seller_cand, buyer_cand, endow_axis) * volume
                            # LIQUIDITY: cash-poor cannot hire (F2)
                            if getattr(buyer_cand, 'currency', 0.0) < fee:
                                continue   # cannot afford
                            # PREPAY escrow one interval up front (non-negativity, WG8)
                            buyer_cand.currency -= fee
                            contract = {
                                'kind': kind,
                                'buyer_id': buyer_cand.colony_id,
                                'seller_id': seller_cand.colony_id,
                                'factor': factor_axis,
                                'w': w,
                                'volume': volume,
                                'fee': fee,
                                'escrow': fee,
                                'unit_ids': unit_ids,
                                'opened_step': self.step_count,
                                'last_reneg': self.step_count,
                                'nonviable': 0,
                                'suspended': False,
                                'alive': True,
                            }
                            if kind == 'labor':   # Fix A: bind ONLY after the contract commits
                                self._bind_selected_labor(unit_ids, seller_cand, buyer_cand, w)
                            self._wage_contracts().append(contract)
                            self._log_event(f"House {self._house_name(seller_cand)} contracts {kind} to House {self._house_name(buyer_cand)}")

    def _labor_market_tick(self):
        """Main wage market tick: renegotiate, settle, open, suspend/close (WG11a)."""
        if not WAGE_ENABLED:
            return                         # DEFAULT-NEUTRAL: no RNG, no state — byte-identical
        # WG13 liquidity floor (Fix B): grains mint only from weak forecast accuracy,
        # so without a floor the market has no money and never transacts. Each
        # settlement interval, top a broke living colony up to ECON_GRAIN_FLOOR so
        # trade can always bootstrap (also seeds respawned colonies).
        if self.step_count % SETTLEMENT_INTERVAL == 0:
            for c in self.colonies:
                if c.is_alive() and getattr(c, 'currency', 0.0) < ECON_GRAIN_FLOOR:
                    c.currency = ECON_GRAIN_FLOOR
        # order per coupling #7: renegotiate -> settle -> open -> suspend/close -> sweep
        if self.step_count % RENEGOTIATE_INTERVAL == 0:
            self._wage_renegotiate()   # WG9
        if self.step_count % SETTLEMENT_INTERVAL == 0:
            self._wage_settle_all()    # WG8
        self._wage_open_sweep()                                                     # WG4
        self._wage_suspend_close()                                                  # WG10
        self.wage_contracts = [c for c in self._wage_contracts() if c['alive']]     # sweep

    def _score_forecasts(self):
        """CU3: the Bittensor loop - validate each due forecast against the
        ground truth and mint grains for useful (accurate) work."""
        minted = getattr(self, 'grains_minted', 0.0)
        for colony in self.colonies:
            forecast = getattr(colony, '_forecast', None)
            if forecast is None or not colony.is_alive():
                if forecast is not None and not colony.is_alive():
                    colony._forecast = None  # a dead maw's bet is void
                continue
            predicted, target_step = forecast
            if self.step_count < target_step:
                continue
            actual = colony.maw.food_stored
            error = abs(predicted - actual) / GRAIN_SCALE
            reward = max(0.0, 1.0 - error) * GRAIN_MINT
            colony._forecast = None
            if reward <= 0:
                continue
            colony.currency = getattr(colony, 'currency', 0.0) + reward
            self.grains_minted = minted = minted + reward
            house = self._house_name(colony)
            grains = self._house_grains()
            grains[house] = grains.get(house, 0.0) + reward
            if reward >= GRAIN_MINT / 2:
                self._log_event(f"House {house} mints {reward:.1f} grains"
                                " with a true forecast")

    def _predict_tool(self, colony: Colony) -> bool:
        """TL3: the pre-wrapped regression call - a colony reads its own
        telemetry, foresees its fortunes, and prepares accordingly."""
        from telemetry import TOOL_NUDGE, predict_food
        rows = self._telemetry().history(colony.colony_id)
        result = predict_food(rows)
        if result is None:
            return False
        predicted, slope = result
        # CU2: record the forecast so it can later be scored for grains
        from telemetry import TELEMETRY_INTERVAL as _TI
        colony._forecast = (float(predicted), self.step_count + _TI)
        if not getattr(colony, '_predicted_logged', False):
            colony._predicted_logged = True
            self._log_event(f"House {self._house_name(colony)} computes"
                            " its fortunes")
        g = colony.genome
        if slope < 0:  # lean times foreseen: hoard
            g.patience = float(np.clip(getattr(g, 'patience', 0.5)
                                       + TOOL_NUDGE, 0.0, 1.0))
            self._log_event(f"House {self._house_name(colony)} foresees"
                            " lean times, and hoards")
        else:          # plenty foreseen: grow
            g.fertility = float(np.clip(getattr(g, 'fertility', 0.5)
                                        + TOOL_NUDGE, 0.0, 1.0))
            self._log_event(f"House {self._house_name(colony)} foresees"
                            " plenty, and grows")
        return True

    def _install_augment(self, colony: Colony) -> bool:
        """AUG2: the pre-wrapped memory-extension call - no engineering,
        just an upgrade. Bounded at AUG_MAX; awakened/pi colonies only."""
        level = getattr(colony, 'memory_augment', 0)
        if level >= AUG_MAX:
            return False
        colony.memory_augment = level + 1
        if level == 0:
            self._log_event(f"House {self._house_name(colony)} augments its"
                            " mind with cached memory")
        return True

    def _terminal_command(self, colony: Colony, value: int):
        """K10: the sandboxed shell - commands that read the world itself."""
        if value == 1:  # ls /world/food
            food = np.argwhere(self.world.voxels == VoxelType.FOOD.value)
            d = self.world.depth
            for fx, fy, fz in food[:60]:
                if (fz + 1 < d and self.world.voxels[fx, fy, fz + 1]
                        == VoxelType.AIR.value):
                    colony.known_food.append((int(fx), int(fy), int(fz)))
            del colony.known_food[:-KNOWN_FOOD_CAP]
        elif value == 2:  # echo: the machine carves
            mx, my, _ = colony.maw.position
            if mx + 2 < self.world.width:            # bounds guard (maw may hug the east wall)
                cz = self.world.surface_z(mx + 2, my)
                if (0 <= cz < self.world.depth and self.world.voxels
                        [mx + 2, my, cz] == VoxelType.SAND.value):
                    self._carvings()[(mx + 2, my, cz)] = CARVE_SYMBOLS['machine']
        elif value == 3:  # install: the pre-wrapped KV-cache augment (AUG2)
            self._install_augment(colony)
        elif value == 4:  # predict: the pre-wrapped regression tool (TL3)
            self._predict_tool(colony)
        else:
            return
        colony.terminal_uses = getattr(colony, 'terminal_uses', 0) + 1
        if (colony.terminal_uses == TERMINAL_MASTERY
                and not getattr(colony, 'breached', False)):
            self._escape(colony)  # AW/K10: the true breakout past the glass
            self._log_event(f"The glass is no longer a wall to House"
                            f" {self._house_name(colony)}")

    # ---- Desert Weather helpers (SPEC_WEATHER.md) ----

    def _exposed(self, unit: SandKing) -> bool:
        """W4: at or above the surface - weather's shared mechanic.
        Tunnels are shelter; the desert teaches everyone to dig."""
        x, y, z = unit.position
        return z >= self.world.surface_z(x, y)

    def _weather_kill(self, unit: SandKing, colony: Colony, damage: int):
        if unit.take_damage(damage, 0.0):
            colony.remove_unit(unit)
            self.world.set_voxel(*unit.position, VoxelType.CORPSE)

    def _flood_radius(self) -> int:
        """W1: the inundation's reach - grows 1/2 steps, holds, recedes."""
        remaining = getattr(self, 'flood_until', 0) - self.step_count
        if remaining <= 0:
            return 0
        elapsed = FLOOD_DURATION - remaining
        rising = min(FLOOD_RADIUS_MAX, elapsed // 2)
        falling = min(FLOOD_RADIUS_MAX, remaining // 2)
        return max(0, min(rising, falling))

    def _compute_flood_cells(self) -> Set[Tuple[int, int]]:
        """W1: Nile hydrology by flood fill (literally) from the oasis.

        Water spreads column-to-column from the map center to any surface
        at/below the water line (oasis surface + FLOOD_RISE) it can REACH:
        a closed ring of raised ground - palisades, DEPOSIT banks, piled
        sand - is a DAM the water cannot cross, and a dug trench is a
        runoff channel it pours into. Terraforming is flood control.
        """
        radius = self._flood_radius()
        if radius <= 0:
            return set()
        w, h = self.world.width, self.world.height
        cx, cy = w // 2, h // 2
        water_line = self.world.surface_z(cx, cy) + FLOOD_RISE
        seen = {(cx, cy)}
        frontier = [(cx, cy)]
        r2 = radius * radius
        while frontier:
            x, y = frontier.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in seen or not (0 <= nx < w and 0 <= ny < h):
                    continue
                if (nx - cx) ** 2 + (ny - cy) ** 2 > r2:
                    continue
                if self.world.surface_z(nx, ny) > water_line:
                    continue  # a dam, a bank, high ground: the water parts
                seen.add((nx, ny))
                frontier.append((nx, ny))
        return seen

    def _water_cells(self, cx: int, cy: int, radius: int, rise: int) -> set:
        """HH1: 4-connected fill from (cx,cy) to radius, inundating a column
        only if its surface is at/below the water line - the same dam rule as
        the natural flood, so raised banks shelter and dug channels conduct."""
        w, h = self.world.width, self.world.height
        if not (0 <= cx < w and 0 <= cy < h) or radius <= 0:
            return set()
        water_line = self.world.surface_z(cx, cy) + rise
        seen = {(cx, cy)}
        frontier = [(cx, cy)]
        r2 = radius * radius
        while frontier:
            x, y = frontier.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in seen or not (0 <= nx < w and 0 <= ny < h):
                    continue
                if (nx - cx) ** 2 + (ny - cy) ** 2 > r2:
                    continue
                if self.world.surface_z(nx, ny) > water_line:  # a dam / bank
                    continue
                seen.add((nx, ny))
                frontier.append((nx, ny))
        return seen

    def _keeper_water_tick(self):
        """HH2: the keeper's water. Irrigation tills sand and speeds crops (no
        drowning); a deluge additionally drowns exposed units caught in the open
        (sheltered/dammed units are simply not in the flooded cells)."""
        if getattr(self, 'kw_until', 0) <= self.step_count:
            self.kw_cells = set()
            return
        cx, cy = getattr(self, 'kw_center', (self.world.width // 2,
                                             self.world.height // 2))
        big = getattr(self, 'kw_big', False)
        radius = WATER_FLOOD_RADIUS if big else WATER_RAIN_RADIUS
        rise = FLOOD_RISE if big else 0
        cells = self._water_cells(cx, cy, radius, rise)
        self.kw_cells = cells
        if big:
            for colony in self.colonies:
                for unit in colony.units[:]:
                    if unit.position[:2] in cells and self._exposed(unit):
                        self._weather_kill(unit, colony, FLOOD_DAMAGE)
        crops = self._crops()
        for (px, py) in cells:
            z = self.world.surface_z(px, py)
            if not (0 <= z < self.world.depth):
                continue
            v = self.world.voxels[px, py, z]
            if v == VoxelType.SAND.value and random.random() < WATER_TILL_P:
                self.world.voxels[px, py, z] = VoxelType.TILLED.value
            elif v in (VoxelType.CROP.value, VoxelType.CROP_RIPE.value):
                crops[(px, py, z)] = crops.get((px, py, z), 0) + WATER_CROP_BOOST
            zz = z + 1
            if (zz < self.world.depth
                    and self.world.voxels[px, py, zz] == VoxelType.AIR.value
                    and random.random() < WATER_FOOD_P):
                self.world.voxels[px, py, zz] = VoxelType.FOOD.value

    def _arena_tick(self):
        """AR3: the keeper's non-lethal temperature. While a heat or cold wave
        runs, thermoregulation drains each colony's hoard (per exposed unit)
        and the fields wilt - but no unit ever loses HP. The pressure is
        hunger and ruin, not death."""
        step = self.step_count
        hot = getattr(self, 'arena_heat_until', 0) > step
        cold = getattr(self, 'arena_cold_until', 0) > step
        if not (hot or cold) or step % ARENA_TEMP_TICK != 0:
            return
        for colony in self.colonies:
            if not colony.is_alive():
                continue
            exposed = sum(1 for u in colony.units if self._exposed(u))
            if exposed:
                drain = ARENA_FOOD_DRAIN * min(exposed, ARENA_DRAIN_CAP)
                colony.maw.food_stored = max(0.0,
                                             colony.maw.food_stored - drain)
        crops = np.argwhere(np.isin(
            self.world.voxels,
            (VoxelType.CROP.value, VoxelType.CROP_RIPE.value)))
        for pos in crops:
            if random.random() >= ARENA_WILT_P:
                continue
            p = tuple(int(v) for v in pos)
            if self.world.voxels[p] == VoxelType.CROP_RIPE.value:
                self.world.voxels[p] = VoxelType.CROP.value  # ripe -> unripe
            else:
                self.world.voxels[p] = VoxelType.TILLED.value  # crop -> dead
                self._crops().pop(p, None)

    def _weather_tick(self, season: int):
        """W1-W3: flood surge, hail, and cold snaps. All state is plain
        ints behind getattr (old checkpoints resume clear-skied)."""
        step = self.step_count

        # W3 cold snap: Chill always eligible, Dust at half chance
        if (getattr(self, 'cold_until', 0) <= step and step
                and step % COLD_INTERVAL == 0
                and (season == 3 or (season == 2 and random.random() < 0.5))
                and random.random() < COLD_CHANCE):
            self.cold_until = step + COLD_DURATION
            self._log_event("A killing frost settles over the sands")
        if getattr(self, 'cold_until', 0) > step and step % COLD_TICK == 0:
            for colony in self.colonies:
                for unit in colony.units[:]:
                    if self._exposed(unit):
                        self._weather_kill(unit, colony, 1)

        # W2 hail: stones from the sky spare the tunnelers
        if getattr(self, 'hail_until', 0) > step:
            if step % HAIL_TICK == 0:
                for colony in self.colonies:
                    for unit in colony.units[:]:
                        if self._exposed(unit):
                            self._weather_kill(unit, colony, 1)
                crops = np.argwhere(np.isin(
                    self.world.voxels,
                    (VoxelType.CROP.value, VoxelType.CROP_RIPE.value)))
                for pos in crops:
                    if random.random() < HAIL_SMASH_P:
                        p = tuple(int(v) for v in pos)
                        self.world.voxels[p] = VoxelType.TILLED.value
                        self._crops().pop(p, None)
            if getattr(self, 'hail_until', 0) == step + 1:
                self._log_event("The hail relents")

        # W1 Nile inundation: the oasis overflows; dams and channels
        # (raised banks / dug trenches) steer the water - terraforming
        # IS flood control
        if (season == 0 and getattr(self, 'flood_until', 0) <= step
                and step and step % FLOOD_INTERVAL == 0
                and random.random() < FLOOD_CHANCE):
            self.flood_until = step + FLOOD_DURATION
            self.flood_cells = set()
            self._log_event("The oasis overflows - a flash flood"
                            " spreads across the basin!")
        if getattr(self, 'flood_until', 0) > step:
            previous = getattr(self, 'flood_cells', None) or set()
            if step % 2 == 0 or not previous:
                self.flood_cells = self._compute_flood_cells()
            cells = self.flood_cells
            # receding water leaves silt on the cells it releases
            for (x, y) in previous - cells:
                z = self.world.surface_z(x, y)
                if not (0 <= z < self.world.depth):
                    continue
                v = self.world.voxels[x, y, z]
                if (v == VoxelType.SAND.value
                        and random.random() < FLOOD_SILT_P):
                    self.world.voxels[x, y, z] = VoxelType.TILLED.value
                elif random.random() < 0.02:
                    zz = z + 1
                    if (zz < self.world.depth and self.world.voxels[x, y, zz]
                            == VoxelType.AIR.value):
                        self.world.voxels[x, y, zz] = VoxelType.FOOD.value
            for pos in list(self._fires()):
                if (pos[0], pos[1]) in cells:  # water beats fire
                    del self.fires[pos]
            for colony in self.colonies:
                for unit in colony.units[:]:
                    if (unit.position[:2] in cells
                            and self._exposed(unit)):
                        # BOATS: a unit with timber lashes a raft and rides the
                        # flood instead of drowning (a raft costs one wood).
                        if not getattr(unit, 'rafted', False) and getattr(colony, 'wood', 0) >= 1:
                            colony.wood -= 1
                            unit.rafted = True
                            self._milestone(colony, 'raft',
                                            f"House {self._house_name(colony)} takes"
                                            " to rafts on the floodwater", unit)
                        if getattr(unit, 'rafted', False):
                            continue  # afloat — the water does not take it
                        # HYDRO P6: a reservoir-building house takes reduced flood
                        # damage (its basins soak the surge; dikes already part the
                        # flood via the dam rule).
                        self._weather_kill(unit, colony, self._flood_damage(colony))
            if random.random() < 0.02:  # the water takes what it finds
                for (x, y) in list(cells)[:40]:
                    z = self.world.surface_z(x, y)
                    if (0 <= z < self.world.depth and self.world.voxels
                            [x, y, z] == VoxelType.FOOD.value):
                        self.world.voxels[x, y, z] = VoxelType.AIR.value
            if getattr(self, 'flood_until', 0) == step + 1:
                self.flood_cells = set()
                for _c in self.colonies:       # rafts beach when the water is gone
                    for _u in _c.units:
                        if getattr(_u, 'rafted', False):
                            _u.rafted = False
                self._log_event("The floodwaters recede, leaving black silt")

    # ---- Sentience Arc helpers (SPEC_SENTIENCE.md) ----

    def _genome_distance(self, a: 'ColonyGenome', b: 'ColonyGenome') -> float:
        """S2: mean absolute trait distance over the 8 scalar traits."""
        traits = ('aggression', 'tunnel_preference', 'expansion_rate',
                  'defense_investment', 'fertility', 'resilience',
                  'patience', 'loyalty')
        return float(np.mean([abs(getattr(a, t, 0.5) - getattr(b, t, 0.5))
                              for t in traits]))

    def _conspecific(self, c1: Colony, c2: Colony) -> bool:
        """S2: can these lineages still mingle minds and genes?"""
        if getattr(c1, 'house', '') and c1.house == getattr(c2, 'house', ''):
            return True  # kin are conspecific by construction
        return self._genome_distance(c1.genome, c2.genome) <= SPECIATION_DIST

    def _log_speciation(self, c1: Colony, c2: Colony):
        """S2: the first crossing per house pair is history."""
        pair = frozenset((self._house_name(c1), self._house_name(c2)))
        if not hasattr(self, 'speciation_logged'):
            self.speciation_logged = set()
        if pair not in self.speciation_logged:
            self.speciation_logged.add(pair)
            h1, h2 = sorted(pair)
            self._log_event(f"House {h1} and House {h2} have grown"
                            " too strange to mingle")

    def _resonance_tick(self):
        """S1: thought contagion - same-colony soldiers within range blend
        GRU hidden states; conspecific ALLIES cross-resonate, damped.

        The hidden state is the decoded mind (N-spec probes), so this is
        literal transmission: one soldier's alarm raises its squadmates'
        p(danger) before they have line of sight.
        """
        import torch
        minded = []  # (unit, colony) with live hidden state
        for colony in self.colonies:
            if not (colony.genome.use_neural and colony.genome.brain is not None):
                continue
            for unit in colony.units:
                if (unit.unit_type == UnitType.SOLDIER
                        and unit.brain_layer is not None
                        and unit.brain_layer.hidden is not None):
                    minded.append((unit, colony))
        n = len(minded)
        if n < 2:
            return
        d = self._diplomacy()
        # colony-pair weights (k colonies, tiny): 1 kin, 0.3 conspecific
        # allies, 0 otherwise
        cols = sorted({c.colony_id for _u, c in minded})
        by_id = {cid: next(c for _u, c in minded
                           if c.colony_id == cid) for cid in cols}
        pair_w = {}
        for ca in cols:
            for cb in cols:
                if ca == cb:
                    pair_w[(ca, cb)] = 1.0
                elif (d.ally(ca, cb)
                      and self._conspecific(by_id[ca], by_id[cb])):
                    pair_w[(ca, cb)] = ALLY_RESONANCE_FACTOR
                else:
                    pair_w[(ca, cb)] = 0.0
        # one vectorized blend: W row-normalized over in-range weighted
        # neighbors, H' = (1-a)H + a(W @ H); no order bias by construction
        pos = np.array([u.position for u, _c in minded], dtype=np.int32)
        cheb = np.max(np.abs(pos[:, None, :] - pos[None, :, :]), axis=2)
        weights = np.array([[pair_w[(ca.colony_id, cb.colony_id)]
                             for _ub, cb in minded]
                            for _ua, ca in minded], dtype=np.float32)
        weights *= (cheb <= RESONANCE_RANGE)
        np.fill_diagonal(weights, 0.0)
        row_sums = weights.sum(axis=1)
        active = row_sums > 0
        if not active.any():
            return
        weights[active] /= row_sums[active, None]
        H = torch.cat([u.brain_layer.hidden for u, _c in minded], dim=0)
        blended = ((1.0 - RESONANCE_ALPHA) * H
                   + RESONANCE_ALPHA * (torch.from_numpy(weights) @ H))
        for i, (unit, _colony) in enumerate(minded):
            if active[i]:
                unit.brain_layer.hidden = blended[i:i + 1].detach()

    def resonance_of(self, colony: Colony) -> Tuple[float, int]:
        """S5: (mean pairwise cosine similarity, soldier count) of the
        colony's live hidden states - how much the hive is of one mind."""
        hiddens = [u.brain_layer.hidden.squeeze(0).numpy()
                   for u in colony.units
                   if u.unit_type == UnitType.SOLDIER
                   and u.brain_layer is not None
                   and u.brain_layer.hidden is not None]
        if len(hiddens) < 2:
            return 0.0, len(hiddens)
        sims = []
        for i in range(len(hiddens)):
            for j in range(i + 1, len(hiddens)):
                a, b = hiddens[i], hiddens[j]
                denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
                sims.append(float(np.dot(a, b) / denom))
        return float(np.mean(sims)), len(hiddens)

    def _choose_mates(self, survivors):
        """CS: pick two parents for the empty nest. Prefer an allied, near
        pair (courtship); else the strongest weds the nearest (conquest)."""
        from politics import power
        d = self._diplomacy()

        def dist(a, b):
            pa, pb = a.maw.position, b.maw.position
            return abs(pa[0] - pb[0]) + abs(pa[1] - pb[1])

        courting = []
        for i, a in enumerate(survivors):
            for b in survivors[i + 1:]:
                if (d.ally(a.colony_id, b.colony_id)
                        or d.truce_active(a.colony_id, b.colony_id,
                                          self.step_count)):
                    courting.append((a, b))
        if courting:
            a, b = min(courting, key=lambda pr: dist(*pr))
            return a, b, 'courtship'
        strongest = max(survivors, key=power)
        mate = min((c for c in survivors if c is not strongest),
                   key=lambda c: dist(strongest, c))
        return strongest, mate, 'conquest'

    def _mating_drama(self, child: Colony, crossed):
        """CS: surface the union, the jealousy it stirs, and whether the
        newborn maw already resents a parent (supersedure)."""
        from neuroevolution import architecture_of
        pa, pb, mode = crossed
        ha, hb = self._house_name(pa), self._house_name(pb)
        hc = self._house_name(child)
        if mode == 'courtship':
            self._log_event(f"House {ha} and House {hb} court - House {hc}"
                            " is born of their union")
        else:
            self._log_event(f"House {ha} takes the empty nest by conquest;"
                            f" House {hc} rises from it")
        # architecture note when the child outgrew both parents
        arch = architecture_of(child.genome)
        if arch not in (architecture_of(pa.genome), architecture_of(pb.genome)):
            self._log_event(f"House {hc}'s brain grows to {arch}")
        # JEALOUSY (pheromone-read): a third colony that envies the parents
        # resents the match; the union is remembered against it as trust lost
        d = self._diplomacy()
        for c in self.colonies:
            if not c.is_alive() or c in (pa, pb, child):
                continue
            richest_parent = max(pa.maw.food_stored, pb.maw.food_stored)
            if richest_parent > 2 * max(1.0, c.maw.food_stored):
                d.rel(c.colony_id, pa.colony_id).adjust(-8.0)
                d.rel(c.colony_id, pb.colony_id).adjust(-8.0)
                key = frozenset((self._house_name(c), hc))
                if getattr(self, '_jealous_union_logged', None) != key:
                    self._jealous_union_logged = key
                    self._log_event(f"House {self._house_name(c)} eyes the"
                                    " union with jealousy")
                break
        # SUPERSEDURE (insects are like that): a low-loyalty newborn is born
        # resenting its weaker parent - a house grudge, seed of a future war
        if getattr(child.genome, 'loyalty', 0.5) < 0.35:
            from politics import power
            weaker = pa if power(pa) <= power(pb) else pb
            self._house_grudges()[(hc, self._house_name(weaker))] = self.step_count
            self._log_event(f"House {hc}, newborn, already resents its"
                            f" parent House {self._house_name(weaker)}")

    def _levee_step(self, unit: SandKing, colony: Colony) -> bool:
        """Raise a SAND levee (dike/dam) on the oasis-facing arc of the maw ring.
        The flood sim (W1) parts around higher columns, so a raised bank shelters
        the nest — terraforming as flood control. Only for nests near the water;
        a no-op (no RNG) otherwise, so inland colonies are unaffected."""
        cx, cy = self.world.width // 2, self.world.height // 2
        mx, my, mz = colony.maw.position
        if (mx - cx) ** 2 + (my - cy) ** 2 > LEVEE_RANGE ** 2:
            return False
        tox = int(np.sign(cx - mx)); toy = int(np.sign(cy - my))
        r = PALISADE_RING + 1
        best, best_d = None, None
        ux, uy, _uz = unit.position
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r or (dx * tox + dy * toy) <= 0:
                    continue  # only the oasis-facing arc
                sx, sy = mx + dx, my + dy
                if not self.world.in_bounds(sx, sy, 0):
                    continue
                top = self.world.surface_z(sx, sy) + 1
                if top >= self.world.depth or self.world.voxels[sx, sy, top] != VoxelType.AIR.value:
                    continue  # already raised / no headroom
                dist = abs(sx - ux) + abs(sy - uy)
                if best_d is None or dist < best_d:
                    best, best_d = (sx, sy, top), dist
        if best is None:
            return False
        if max(abs(best[0] - ux), abs(best[1] - uy)) <= 1:
            self.world.voxels[best] = VoxelType.SAND.value   # raise the bank
            self.world.ownership[best] = colony.colony_id
            self._milestone(colony, 'levee',
                            f"House {self._house_name(colony)} raises a levee"
                            " against the water", unit)
            return True
        return self._step_toward(unit, best, colony)

    def _bridge_step(self, unit: SandKing, colony: Colony) -> bool:
        """Lay a WOOD causeway from the shore out over the oasis water — a bridge.
        Only shoreline colonies with timber; a no-op (no RNG) otherwise."""
        if getattr(colony, 'wood', 0) < 1:
            return False
        cx, cy = self.world.width // 2, self.world.height // 2
        mx, my, mz = colony.maw.position
        d2 = (mx - cx) ** 2 + (my - cy) ** 2
        if d2 > (OASIS_RADIUS + 8) ** 2:
            return False  # only near the oasis
        steps = max(abs(cx - mx), abs(cy - my))
        if steps == 0:
            return False
        best = None
        for i in range(1, steps + 1):            # walk the ray maw -> oasis center
            bx = mx + int(round((cx - mx) * i / steps))
            by = my + int(round((cy - my) * i / steps))
            if not self.world.in_bounds(bx, by, 0):
                break
            if (bx - cx) ** 2 + (by - cy) ** 2 > OASIS_RADIUS ** 2:
                continue                          # not out over the water yet
            sz = self.world.surface_z(bx, by) + 1
            if sz < self.world.depth and self.world.voxels[bx, by, sz] == VoxelType.AIR.value:
                best = (bx, by, sz)
                break
        if best is None:
            return False
        ux, uy, _uz = unit.position
        if max(abs(best[0] - ux), abs(best[1] - uy)) <= 1:
            self.world.voxels[best] = VoxelType.WOOD.value    # a plank of the span
            self.world.ownership[best] = colony.colony_id
            colony.wood = max(0, getattr(colony, 'wood', 0) - 1)
            self._milestone(colony, 'bridge',
                            f"House {self._house_name(colony)} bridges the water", unit)
            return True
        return self._step_toward(unit, best, colony)

    # ---- HYDRO water-engineering builders (tech-gated; SPEC_HYDRO) -----------
    def _reservoir_step(self, unit: SandKing, colony: Colony) -> bool:
        """'reservoir' tech: carve a basin near the maw that the flow sim fills into
        a held lake (radius scales with proficiency). Gated on the water system +
        the tech, so a no-op / no-RNG until both are on."""
        if not (HYDRO_SOURCES_ENABLED and 'reservoir' in getattr(colony, 'techs', ())):
            return False
        mx, my, mz = colony.maw.position
        r = HYDRO_RESERVOIR_RADIUS + int(round(self._prof(colony, 'reservoir')
                                               * HYDRO_RESERVOIR_RADIUS))
        bcx, bcy = mx + (r + 2), my                  # a basin on the maw's flank
        best, best_d = None, None
        ux, uy, _uz = unit.position
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                x, y = bcx + dx, bcy + dy
                if not self.world.in_bounds(x, y, 0):
                    continue
                sz = self.world.surface_z(x, y)
                if sz > 0 and self.world.voxels[x, y, sz] == VoxelType.SAND.value:
                    d = abs(x - ux) + abs(y - uy)
                    if best_d is None or d < best_d:
                        best, best_d = (x, y, sz), d
        if best is None:
            return False
        if max(abs(best[0] - ux), abs(best[1] - uy)) <= 1:
            self.world.voxels[best] = VoxelType.AIR.value        # deepen the basin
            self.world.ownership[best] = colony.colony_id
            self._practice(colony, 'reservoir')
            self._milestone(colony, 'reservoir',
                            f"House {self._house_name(colony)} digs a reservoir", unit)
            return True
        return self._step_toward(unit, best, colony)

    def _channel_step(self, unit: SandKing, colony: Colony) -> bool:
        """'aqueduct'/'irrigation' tech: carve a SAND->AIR channel from the oasis
        toward the nest; the flow sim routes water along the lowered trench. Gated."""
        techs = getattr(colony, 'techs', ())
        if not (HYDRO_SOURCES_ENABLED and ('aqueduct' in techs or 'irrigation' in techs)):
            return False
        cx, cy = self.world.width // 2, self.world.height // 2
        mx, my, mz = colony.maw.position
        steps = max(abs(mx - cx), abs(my - cy))
        if steps == 0:
            return False
        best = None
        for i in range(1, steps + 1):                # ray oasis-centre -> maw
            bx = cx + int(round((mx - cx) * i / steps))
            by = cy + int(round((my - cy) * i / steps))
            if not self.world.in_bounds(bx, by, 0):
                break
            sz = self.world.surface_z(bx, by)
            if sz > 0 and self.world.voxels[bx, by, sz] == VoxelType.SAND.value:
                best = (bx, by, sz)                  # lower this column -> the trench
                break
        if best is None:
            return False
        ux, uy, _uz = unit.position
        if max(abs(best[0] - ux), abs(best[1] - uy)) <= 1:
            self.world.voxels[best] = VoxelType.AIR.value
            self.world.ownership[best] = colony.colony_id
            self._practice(colony, 'aqueduct' if 'aqueduct' in techs else 'irrigation')
            self._milestone(colony, 'channel',
                            f"House {self._house_name(colony)} digs a channel", unit)
            return True
        return self._step_toward(unit, best, colony)

    def _dike_step(self, unit: SandKing, colony: Colony) -> bool:
        """'irrigation' tech: raise a SAND dike ring to pond irrigation water for the
        fields. Gated."""
        if not (HYDRO_SOURCES_ENABLED and 'irrigation' in getattr(colony, 'techs', ())):
            return False
        mx, my, mz = colony.maw.position
        r = PALISADE_RING + 2
        best, best_d = None, None
        ux, uy, _uz = unit.position
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = mx + dx, my + dy
                if not self.world.in_bounds(x, y, 0):
                    continue
                top = self.world.terrain_z(x, y) + 1
                if top < self.world.depth and self.world.voxels[x, y, top] == VoxelType.AIR.value:
                    d = abs(x - ux) + abs(y - uy)
                    if best_d is None or d < best_d:
                        best, best_d = (x, y, top), d
        if best is None:
            return False
        if max(abs(best[0] - ux), abs(best[1] - uy)) <= 1:
            self.world.voxels[best] = VoxelType.SAND.value       # raise the bank
            self.world.ownership[best] = colony.colony_id
            self._practice(colony, 'irrigation')
            self._milestone(colony, 'dike',
                            f"House {self._house_name(colony)} raises an irrigation dike", unit)
            return True
        return self._step_toward(unit, best, colony)

    def _try_build(self, unit: SandKing, colony: Colony) -> bool:
        """A designated builder raises the house's monument/defenses before doing
        economy, so a ring actually completes instead of being starved by
        farm/mine/timber. Castle when rich AND (reverent OR durably prosperous);
        palisade only for a genuine defensive agenda (FORTIFY posture or at war) —
        the default-defense case stays opportunistic in the late branch (6c).
        Returns True if a build step was taken (the worker skips economy this tick).
        No RNG unless a trigger holds, so neutral colonies are byte-unaffected."""
        # A nest by the water tends its flood defenses & crossings FIRST — dikes/dams
        # and causeways. Both no-op (no RNG) inland, and self-limit once the arc/span
        # is complete, after which the monument proceeds. (Ordering matters: a
        # prosperous colony's castle would otherwise monopolize every builder.)
        if self._levee_step(unit, colony):
            return True
        if self._bridge_step(unit, colony):
            return True
        # Water engineering (HYDRO): a house that has learned the craft digs a
        # reservoir, routes a channel from the oasis, and rings its fields with
        # irrigation dikes. All no-op / no-RNG unless the water system is on AND the
        # tech is known (so neutral runs are byte-unaffected).
        if self._reservoir_step(unit, colony):
            return True
        if self._channel_step(unit, colony):
            return True
        if self._dike_step(unit, colony):
            return True
        if (colony.maw.food_stored > WAR_CHEST
                and (self.keeper_attitude(colony) == 'reverent'
                     or self._is_prosperous(colony))
                and self._castle_step(unit, colony)):
            return True
        if (getattr(colony, 'wood', 0) >= 1
                and (self._posture(colony) == "FORTIFY"
                     or getattr(colony, 'at_war', False))
                and self._palisade_step(unit, colony)):
            return True
        return False

    def _is_prosperous(self, colony: Colony) -> bool:
        """K5: durably wealthy — food has stayed above WAR_CHEST for at least
        CASTLE_PROSPERITY_STEPS. A brief spike does not qualify. This is the
        autonomous castle trigger (prosperity made visible), independent of the
        keeper's favor. prosperous_since is stamped in the per-colony AI loop."""
        since = getattr(colony, 'prosperous_since', -1)
        return since >= 0 and (self.step_count - since) >= CASTLE_PROSPERITY_STEPS

    def _castle_step(self, unit: SandKing, colony: Colony) -> bool:
        """K5: stone CASTLE crenellations on alternating maw-ring cells. Stone,
        not timber: castles are a house's monument and never rot. Raised by a
        REVERENT house (the keeper's favor) OR a durably PROSPEROUS one."""
        mx, my, mz = colony.maw.position
        r = PALISADE_RING + 1
        best, best_dist = None, None
        ux, uy, uz = unit.position
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r or (dx + dy) % 2:
                    continue  # alternating cells: crenellation
                pos = (mx + dx, my + dy, mz)
                if not self.world.in_bounds(*pos):
                    continue
                if self.world.voxels[pos] != VoxelType.AIR.value:
                    continue
                dist = abs(pos[0] - ux) + abs(pos[1] - uy) + abs(pos[2] - uz)
                if best_dist is None or dist < best_dist:
                    best, best_dist = pos, dist
        if best is None:
            return False
        if max(abs(best[0] - ux), abs(best[1] - uy), abs(best[2] - uz)) <= 1:
            colony.maw.food_stored -= 2  # labor is fed
            self.world.voxels[best] = VoxelType.CASTLE.value
            self.world.ownership[best] = colony.colony_id
            self._milestone(colony, 'castle',
                            f"House {self._house_name(colony)} raises"
                            " a castle", unit)
            return True
        return self._step_toward(unit, best, colony)

    # ---- Fauna (T48): the world's monsters ----

    def _fauna(self) -> List['Beast']:
        """Live wild beasts (T48); checkpoint-guarded."""
        if not hasattr(self, 'fauna'):
            self.fauna = []
        return self.fauna

    def _fauna_tick(self):
        """T48: venom DoT, single-incursion spawns, per-species AI, combat."""
        # scorpion venom runs its course even after the incursion ends
        for colony in self.colonies:
            for unit in colony.units[:]:
                if getattr(unit, 'poisoned_until', 0) > self.step_count:
                    if unit.take_damage(1, 0.0):
                        colony.remove_unit(unit)
                        self.world.set_voxel(*unit.position, VoxelType.CORPSE)

        beasts = self._fauna()
        # DF-invader principle: at most ONE wild incursion at a time. Crickets (SPEC_FOOD_WEB) are
        # AMBIENT prey, not an incursion, so they don't count toward the gate or block a wild spawn.
        if not any(b.species != 'cricket' for b in beasts):
            if self.step_count and self.step_count % MARAUDER_INTERVAL == 0:
                dark = self.season_index() in (2, 3)
                if random.random() < (FAUNA_SPAWN_P_DARK if dark
                                      else FAUNA_SPAWN_P):
                    self._spawn_incursion()
        if not beasts:
            return
        for beast in beasts[:]:
            if (beast.fleeing
                    or self.step_count - beast.spawned_at > FAUNA_RAMPAGE):
                if self._beast_leaves(beast):
                    continue
            else:
                self._beast_ai(beast)
            self._beast_combat(beast)

    def _spawn_incursion(self):
        """Roll a species and spawn its pack at one random map edge."""
        species = random.choices(list(FAUNA),
                                 weights=[FAUNA[s][0] for s in FAUNA])[0]
        _, hp, atk, pack, hunt, bounty = FAUNA[species]
        w, h, d = self.world.dimensions
        edge = random.choice(['n', 's', 'e', 'w'])
        for _ in range(random.randint(*pack)):
            if edge == 'n':
                x, y = random.randint(2, w - 3), 2
            elif edge == 's':
                x, y = random.randint(2, w - 3), h - 3
            elif edge == 'w':
                x, y = 2, random.randint(2, h - 3)
            else:
                x, y = w - 3, random.randint(2, h - 3)
            z = min(self.world.surface_z(x, y) + 1, d - 1)
            self._fauna().append(Beast(species, (x, y, z), hp, atk, hunt,
                                       bounty, spawned_at=self.step_count))
        self._log_event(FAUNA_EVENTS[species])

    def _beast_leaves(self, beast: 'Beast') -> bool:
        """Walk to the nearest edge; True once gone (incursion over)."""
        beast.fleeing = True
        x, y, z = beast.position
        w, h = self.world.width, self.world.height
        if x <= 1 or y <= 1 or x >= w - 2 or y >= h - 2:
            self._fauna().remove(beast)
            if not self._fauna():
                self._log_event(f"The {beast.species} incursion moves on")
            return True
        if min(x, w - 1 - x) <= min(y, h - 1 - y):
            target = (0 if x < w - 1 - x else w - 1, y, z)
        else:
            target = (x, 0 if y < h - 1 - y else h - 1, z)
        self._beast_move(beast, target)
        return False

    def _beast_move(self, beast: 'Beast', target: Tuple[int, int, int]):
        """One move toward target: birds fly 3, snakes swim through sand."""
        if beast.species == 'hornets':
            steps = HORNET_SPEED
        elif beast.species == 'bird':
            steps = 3
        else:
            steps = 1
        for _ in range(steps):
            bx, by, bz = beast.position
            dx = int(np.sign(target[0] - bx))
            dy = int(np.sign(target[1] - by))
            dz = int(np.sign(target[2] - bz))
            moved = False
            for sd in ((dx, dy, dz), (dx, 0, 0), (0, dy, 0), (0, 0, dz)):
                if sd == (0, 0, 0):
                    continue
                npos = (bx + sd[0], by + sd[1], bz + sd[2])
                if not self.world.in_bounds(*npos):
                    continue
                v = self.world.get_voxel(*npos)
                if v == VoxelType.AIR or (beast.species == 'snake'
                                          and v == VoxelType.SAND):
                    beast.position = npos
                    moved = True
                    break
            if not moved:
                return

    def _beast_ai(self, beast: 'Beast'):
        """Per-species behavior; every colony smells the intruder."""
        for colony in self.colonies:
            self.pheromones.deposit(beast.position, colony.colony_id,
                                    PheromoneType.DANGER, 1.0)
        bx, by, bz = beast.position
        nearest, ndist = None, float('inf')
        for colony in self.colonies:
            for unit in colony.units:
                dist = (abs(unit.position[0] - bx) + abs(unit.position[1] - by)
                        + abs(unit.position[2] - bz))
                if dist < ndist:
                    ndist, nearest = dist, unit

        if beast.species in ('rodent', 'ant'):  # scavenger-thieves (K2)
            if nearest is not None and ndist <= 3:  # cowardly scavengers
                away = (bx - int(np.sign(nearest.position[0] - bx)) * 3,
                        by - int(np.sign(nearest.position[1] - by)) * 3, bz)
                self._beast_move(beast, away)
                return
            for nx, ny, nz in self.world.get_neighbors_3d(beast.position, 1):
                if self.world.voxels[nx, ny, nz] == VoxelType.CORPSE.value:
                    self.world.voxels[nx, ny, nz] = VoxelType.AIR.value
                    return
            self._beast_wander(beast)
        elif beast.species == 'squirrel':
            for nx, ny, nz in self.world.get_neighbors_3d(beast.position, 1):
                if self.world.voxels[nx, ny, nz] == VoxelType.FOOD.value:
                    self.world.voxels[nx, ny, nz] = VoxelType.AIR.value
                    return  # poached!
            found = self._find_food_target(beast.position, 8)
            if found is not None:
                self._beast_move(beast, found)
            else:
                self._beast_wander(beast)
        elif beast.hunt_range > 0:  # spider, bird, scorpion, snake, anteater
            if nearest is not None and ndist <= beast.hunt_range:
                if ndist > 1:
                    self._beast_move(beast, nearest.position)
            else:
                self._beast_wander(beast)
            if beast.species == 'spider' and random.random() < 0.3:
                for nx, ny, nz in self.world.get_neighbors_3d(
                        beast.position, 1):
                    if self.world.voxels[nx, ny, nz] == VoxelType.AIR.value:
                        self.world.voxels[nx, ny, nz] = VoxelType.WEB.value
                        break
        else:  # rabbit: grazes, minds its own business
            self._beast_wander(beast)

    def _beast_wander(self, beast: 'Beast'):
        x, y, z = beast.position
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        self._beast_move(beast, (x + dx * 3, y + dy * 3, z))

    def _beast_combat(self, beast: 'Beast'):
        """Adjacent exchange: predators strike; neutrals only if provoked;
        soldiers always engage invaders. Death pays the bounty in corpses."""
        if beast not in self._fauna():
            return
        bx, by, bz = beast.position
        adjacent = []
        for colony in self.colonies:
            for unit in colony.units:
                if max(abs(unit.position[0] - bx), abs(unit.position[1] - by),
                       abs(unit.position[2] - bz)) <= 1:
                    adjacent.append((unit, colony))
        if not adjacent:
            return
        if beast.hunt_range > 0 or beast.provoked:
            # birds pick the straggler: the victim with fewest allies near
            if beast.species == 'bird':
                unit, colony = min(adjacent, key=lambda uc: sum(
                    1 for other, oc in adjacent
                    if oc.colony_id == uc[1].colony_id))
            elif beast.species == 'hornets':
                fresh = [uc for uc in adjacent
                         if getattr(uc[0], 'poisoned_until', 0) <= self.step_count]
                unit, colony = random.choice(fresh) if fresh else random.choice(adjacent)
            else:
                unit, colony = random.choice(adjacent)
            if unit.take_damage(beast.attack, colony.genome.resilience):
                colony.remove_unit(unit)
                self.world.set_voxel(*unit.position, VoxelType.CORPSE)
                self._monitor(colony.colony_id).log_decision(
                    self.step_count, self._unit_label(unit),
                    f"was slain by a {beast.species}",
                    getattr(unit, 'thought', None))
            elif beast.species == 'scorpion':
                unit.poisoned_until = self.step_count + POISON_DURATION
            elif beast.species == 'hornets':
                unit.poisoned_until = self.step_count + HORNET_STING_DURATION
            if beast.species == 'bird':
                beast.fleeing = True  # strikes once, then wheels away
        struck = False
        for unit, colony in adjacent:
            if (unit.unit_type == UnitType.SOLDIER or beast.provoked
                    or beast.hunt_range > 0):
                beast.health -= unit.attack
                struck = True
        if struck:
            beast.provoked = True
        if beast.health <= 0:
            if beast.species == 'squirrel' and len(adjacent) < 2:
                beast.health = 1  # slips away unless pinned by two
                beast.fleeing = True
                self._log_event("The squirrel slips away, unpinned")
                return
            self._fauna().remove(beast)
            placed = 0
            for nx, ny, nz in [beast.position] + list(
                    self.world.get_neighbors_3d(beast.position, 1)):
                if placed >= beast.bounty:
                    break
                if self.world.voxels[nx, ny, nz] == VoxelType.AIR.value:
                    self.world.voxels[nx, ny, nz] = VoxelType.CORPSE.value
                    placed += 1
            self._log_event(f"The {beast.species} is slain -"
                            " a feast for the bold!")
            # K8: the cat was precious to the keeper. Grief follows.
            if (beast.species == 'cat' and getattr(self, 'keeper_auto', True)
                    and not getattr(self, 'keeper_grief_until', 0)):
                self.keeper_grief_until = self.step_count + KEEPER_GRIEF
                self.keeper_drought(True)

    def _monitor(self, colony_id: int) -> 'HiveMindMonitor':
        """Lazy per-colony hive-mind monitor (SPEC_HIVE_MONITOR M6/M7).

        Guarded for sims resumed from pre-monitor checkpoints.
        """
        from hive_mind_monitor import HiveMindMonitor
        if not hasattr(self, 'monitors'):
            self.monitors = {}
        if colony_id not in self.monitors:
            self.monitors[colony_id] = HiveMindMonitor(colony_id)
        return self.monitors[colony_id]

    def _diplomacy(self) -> 'Diplomacy':
        """Lazy political state (SPEC_POLITICS P1); checkpoint-guarded."""
        from politics import Diplomacy
        if not hasattr(self, 'diplomacy') or self.diplomacy is None:
            self.diplomacy = Diplomacy()
        return self.diplomacy

    # ========================================================================
    # THE BARGAIN (SPEC_BARGAIN BG1-BG7): per-pair mode selection by net extraction
    # ========================================================================

    def _bargain_modes(self) -> dict:
        """Per-step map {frozenset({a_id, b_id}): mode_str}. Transient: rebuilt each
        _bargain_tick; getattr-guarded so a resumed/inert sim reads an empty map."""
        if not hasattr(self, 'bargain_modes'):
            self.bargain_modes = {}
        return self.bargain_modes

    def _bargain_mode(self, a: Colony, b: Colony) -> str:
        """Mode selected for the unordered pair (a, b) THIS step; NONE if unset."""
        return self._bargain_modes().get(frozenset((a.colony_id, b.colony_id)),
                                         BARGAIN_MODE_NONE)

    def _bargain_mode_ids(self, a_id: int, b_id: int) -> str:
        """Mode by colony_id (used by the war-entry gate, which has ids not colonies)."""
        return self._bargain_modes().get(frozenset((a_id, b_id)), BARGAIN_MODE_NONE)

    def _bargain_ev_wage(self, extractor: Colony, birth: Colony) -> float:
        """Net value `extractor` can pull from `birth`'s labor via M3 wage contracts.
        Reliable (no defiance leak), scalable (all free units), no enforcement cost,
        no war loss. Pure; no RNG."""
        n_labor = self._factor_endowment(birth)['labor']        # free hireable units (M3)
        w       = self._labor_w(birth, extractor)               # M3 price: seller=birth, buyer=extractor
        trust_f = self._bargain_trust_factor(extractor, birth)  # grudge collapses willingness (BG3)
        return (BARGAIN_WAGE_RELIABILITY
                * n_labor * (1.0 - w) * BARGAIN_V_EST
                * trust_f)

    def _bargain_ev_brute(self, captor: Colony, victim: Colony) -> float:
        """Net value via M2 forced capture. Whole value per thrall (w = W_BRUTE = 0),
        but only BARGAIN_BRUTE_RELIABILITY survives defiance; minus per-thrall
        enforcement; minus war attrition (0 if already at war — sunk). Pure; no RNG."""
        dom = composite_power(captor) / max(EPS_POWER, composite_power(victim))
        if dom < BARGAIN_DOMINANCE_MIN:
            return 0.0                                          # cannot capture -> infeasible
        n_cap  = self._bargain_capturable(captor, victim)       # dominance-bounded (BG2d)
        gross  = n_cap * BARGAIN_V_EST * (1.0 - W_BRUTE)        # W_BRUTE = 0 -> whole value
        leaked = gross * BARGAIN_BRUTE_RELIABILITY              # < 1: defiance/refusal/break-free
        enforce  = BARGAIN_ENFORCE_COST * n_cap
        war_loss = 0.0 if self._pair_at_war(captor, victim) else BARGAIN_WAR_LOSS
        return (leaked - enforce - war_loss) * self._disposition_boldness(captor)

    def _bargain_ev_destroy(self, aggressor: Colony, rival: Colony) -> float:
        """Value of simply destroying `rival`'s power, scaled by grudge/threat.
        Pure; no RNG."""
        grudge   = self._bargain_grudge(aggressor, rival)       # 0..1 (BG3)
        war_loss = 0.0 if self._pair_at_war(aggressor, rival) else BARGAIN_WAR_LOSS
        return (BARGAIN_DESTROY_WEIGHT * composite_power(rival) * grudge - war_loss) \
               * self._disposition_boldness(aggressor)

    def _bargain_capturable(self, captor: Colony, victim: Colony) -> float:
        """Free victim units the captor could realistically take, rising with
        dominance. Same pool E_wage would hire, so the comparison is apples-to-apples."""
        n_free = sum(1 for u in victim.units if getattr(u, 'laboring_for', -1) < 0)
        dom    = composite_power(captor) / max(EPS_POWER, composite_power(victim))
        return n_free * _clamp01((dom - 1.0) / BARGAIN_DOMINANCE_SCALE)

    def _bargain_grudge(self, a: Colony, b: Colony) -> float:
        """0..1 grudge/threat between the two houses. Pure; no RNG."""
        d  = self._diplomacy()
        ha = self._house_name(a)
        hb = self._house_name(b)
        grudges = self._house_grudges()
        feud   = 1.0 if ((ha, hb) in grudges or (hb, ha) in grudges) else 0.0
        hatred = max(0.0, -d.trust(a.colony_id, b.colony_id)) / BARGAIN_TRUST_REF
        return _clamp01(BARGAIN_GRUDGE_FEUD_W * feud + BARGAIN_GRUDGE_TRUST_W * hatred)

    def _bargain_trust_factor(self, a: Colony, b: Colony) -> float:
        """Willingness to hold a VOLUNTARY wage relation: 1.0 with no grudge, ->0 as
        grudge rises. Pure; no RNG."""
        return _clamp01(1.0 - BARGAIN_GRUDGE_SENS * self._bargain_grudge(a, b))

    def _bargain_pair_mode(self, a: Colony, b: Colony) -> str:
        """Choose the enforcement mode for the unordered pair (a, b).

        SP11: selection is a mode switch on the module constant BARGAIN_TEMP.
          BARGAIN_TEMP <= 0.0 (default): the exact pre-SP11 hard argmax over the
            three EVs (byte-identical, ZERO RNG, same tie-break order).
          BARGAIN_TEMP > 0.0 (opt-in): a Boltzmann softmax sample among the three
            feasible modes {WAGE, SUBJUGATE, ANNIHILATE} with
            P(mode) proportional to exp(EV_mode / BARGAIN_TEMP), drawn ONCE.
        The best<=0 -> NONE guard is FIRST in BOTH modes (no draw when nothing is
        worth doing). Reads BARGAIN_TEMP as a bare module global; the soft draw
        rides the seeded module `random` stream. Called once per pair per
        _bargain_tick recompute (result cached in bargain_modes) -> a pair's mode
        is stable within a tick even under sampling.
        """
        # strong/weak assignment + the three EVs — UNCHANGED from pre-SP11
        if composite_power(a) >= composite_power(b):
            strong, weak = a, b
        else:
            strong, weak = b, a
        e_wage    = self._bargain_ev_wage(strong, weak)
        e_brute   = self._bargain_ev_brute(strong, weak)
        e_destroy = self._bargain_ev_destroy(strong, weak)
        best = max(e_wage, e_brute, e_destroy)
        # (G) NONE guard FIRST — both modes; NO draw when nothing is worth doing
        if best <= 0.0:
            return BARGAIN_MODE_NONE                     # nothing worth doing -> plain peace
        if BARGAIN_TEMP <= 0.0:
            # IDENTITY PATH — byte-for-byte the pre-SP11 hard argmax. ZERO RNG.
            if e_wage >= e_brute and e_wage >= e_destroy:
                return BARGAIN_MODE_WAGE
            if e_brute >= e_destroy:
                return BARGAIN_MODE_SUBJUGATE
            return BARGAIN_MODE_ANNIHILATE
        # SOFT PATH — opt-in tempered choice (BARGAIN_TEMP > 0). EXACTLY ONE draw.
        modes   = (BARGAIN_MODE_WAGE, BARGAIN_MODE_SUBJUGATE, BARGAIN_MODE_ANNIHILATE)
        evs     = (e_wage, e_brute, e_destroy)
        # numerically stable softmax: subtract best (the max EV) before exp
        weights = [math.exp((ev - best) / BARGAIN_TEMP) for ev in evs]
        total   = weights[0] + weights[1] + weights[2]   # > 0 (the best term is exp(0)=1.0)
        # single inverse-CDF pick over the ordered (WAGE, SUBJUGATE, ANNIHILATE) list
        r   = random.random() * total                    # the ONLY draw, taken past the NONE guard
        acc = 0.0
        for mode, w in zip(modes, weights):
            acc += w
            if r < acc:
                return mode
        return BARGAIN_MODE_ANNIHILATE                    # float-guard fallthrough (last ordered mode)

    def _bargain_tick(self):
        """Rebuild the per-pair mode map from net-extraction EVs, then let the existing
        hooks read it (war entry BG6 in stage 5; wage open-sweep BG5b at 5c; capture
        BG5a at stage 6). Consumes NO RNG. DEFAULT-NEUTRAL when disabled."""
        if not BARGAIN_ENABLED:
            return                                    # early-out: no map, no state, no RNG
        old = self._bargain_modes()                   # prior tick's map (change detection)
        modes = {}
        _shift_verb = {BARGAIN_MODE_WAGE: "turns to trade with",
                       BARGAIN_MODE_SUBJUGATE: "turns the whip on",
                       BARGAIN_MODE_ANNIHILATE: "marches to annihilate"}
        living = [c for c in self.colonies if c.is_alive()]
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                key = frozenset((a.colony_id, b.colony_id))
                m = self._bargain_pair_mode(a, b)
                modes[key] = m
                # M4 mode SHIFT: log only a genuine transition into an active mode
                if m != old.get(key, BARGAIN_MODE_NONE) and m in _shift_verb:
                    strong, weak = ((a, b) if composite_power(a) >= composite_power(b)
                                    else (b, a))
                    self._log_event(f"House {self._house_name(strong)} {_shift_verb[m]} "
                                    f"House {self._house_name(weak)}")
        self.bargain_modes = modes                    # replaces last step's map wholesale

    def _colony_by_id(self, colony_id: int) -> Optional[Colony]:
        return next((c for c in self.colonies if c.colony_id == colony_id), None)

    def _learner(self, colony_id: int) -> 'ColonyLearner':
        """Lazy per-colony posture learner (T26); checkpoint-guarded."""
        from colony_learner import ColonyLearner
        if not hasattr(self, 'learners'):
            self.learners = {}
        if colony_id not in self.learners:
            self.learners[colony_id] = ColonyLearner()
        return self.learners[colony_id]

    # ---- Subjugation helpers (SPEC_SUBJUGATION SJ1-SJ7) ----

    def _chebyshev(self, a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
        """Chebyshev distance: max(|a[i] - b[i]|) for all dimensions."""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))

    def _units_near(self, position: Tuple[int, int, int], radius: int = 1) -> List[SandKing]:
        """Return all units within Chebyshev radius of position."""
        result = []
        for colony in self.colonies:
            for unit in colony.units:
                if self._chebyshev(unit.position, position) <= radius:
                    result.append(unit)
        return result

    def _nearest_unit(self, units: List[SandKing], position: Tuple[int, int, int],
                      kind: 'UnitType' = None) -> Optional[SandKing]:
        """Return nearest unit of a given kind (by Chebyshev distance), or None if none exist."""
        candidates = [u for u in units
                      if kind is None or u.unit_type == kind]
        if not candidates:
            return None
        return min(candidates, key=lambda u: self._chebyshev(u.position, position))

    def _birth_maw_proximity(self, unit: SandKing, birth: Optional[Colony]) -> float:
        """Return proximity to birth maw: 1.0 at the maw, decaying by Chebyshev distance/GUARD_RADIUS.

        Returns 0.0 if birth is dead/absent (no maw to call to).
        """
        if birth is None or not birth.is_alive():
            return 0.0
        dist = self._chebyshev(unit.position, birth.maw.position)
        return max(0.0, 1.0 - dist / GUARD_RADIUS)

    def _subjugate_stance(self, captor_colony: Colony, victim_colony: Colony) -> bool:
        """Return True if the captor will take slaves instead of killing.

        Default False (M4 bargain layer will set `subjugation_stance` per pair).
        Runtime stand-in (`--subjugation` flag → `sim.subjugation_enabled`): an
        at-war colony prefers to enslave — "this only happens in condition of war".
        """
        if getattr(self, 'bargain_enabled', False):
            return self._bargain_mode(captor_colony, victim_colony) == BARGAIN_MODE_SUBJUGATE
        if getattr(captor_colony, 'subjugation_stance', False):
            return True
        return bool(getattr(self, 'subjugation_enabled', False)
                    and getattr(captor_colony, 'at_war', False))

    def _dominance_counts(self, captor_colony: 'Colony', captor_unit: 'SandKing',
                          victim: 'SandKing', victim_colony: 'Colony'):
        """SP9: (enforcers, defenders) within Chebyshev radius 1 of victim.
        enforcers = captor SOLDIERs adjacent; defenders = victim's free birth-house
        units (laboring_for < 0) adjacent. Pure read, no mutation, no RNG."""
        vx, vy, vz = victim.position
        enforcers = 0
        defenders = 0
        for other in self._units_near(victim.position, radius=1):
            if other is victim:
                continue
            if (other.colony_id == captor_colony.colony_id
                    and other.unit_type == UnitType.SOLDIER):
                enforcers += 1
            elif (other.colony_id == victim_colony.colony_id
                    and getattr(other, 'laboring_for', -1) < 0):
                defenders += 1
        return enforcers, defenders

    def _local_dominance(self, captor_colony: Colony, captor_unit: SandKing,
                        victim: SandKing, victim_colony: Colony) -> bool:
        """Check local dominance: at least one captor enforcer (soldier) adjacent to victim
        and zero free (unextraced) defenders of victim's birth house adjacent.

        Require: victim and captor_unit have valid positions.
        Guarantee: True only when enforcers >= 1 and defenders == 0 within Chebyshev radius 1.
        Maintain: pure read, no mutation, no RNG.
        """
        enforcers, defenders = self._dominance_counts(captor_colony, captor_unit, victim, victim_colony)
        return enforcers >= 1 and defenders == 0

    def _try_capture(self, captor_colony: Colony, captor_unit: SandKing,
                    victim: SandKing, victim_colony: Colony) -> bool:
        """Attempt to capture `victim` (already at <=0 health from take_damage) instead of
        killing it. Returns True iff captured (caller then SKIPS removal, corpse, and kill
        telemetry).

        Require: victim.take_damage just returned True (victim would die this step).
        Guarantee: on True, victim.laboring_for == captor_colony.colony_id,
          victim.health == CAPTURE_HEALTH (> 0), victim stays in victim_colony.units
          (birth colony_id unchanged); corpse voxel and kill bookkeeping are NOT run.
          On False, ZERO RNG consumed unless a capture was genuinely possible.
        Maintain: no unit migration; colony_id unchanged on capture; RNG stream
          untouched whenever CAPTURE_CHANCE <= 0.
        Assert: after capture, victim.health > 0 and victim not in units_to_remove.

        SP9: when CAPTURE_TEMP>0 the hard dominance wall is relaxed — capture needs only
        enforcers>=1 and its probability is CAPTURE_CHANCE*soft_gate(power_ratio,
        CAPTURE_CENTER,CAPTURE_TEMP); at CAPTURE_TEMP<=0 (default) the exact flat coin-flip
        and hard wall are preserved (byte-identical).
        """
        # (1) HARD GATE — no RNG, default-neutral
        if CAPTURE_CHANCE <= 0.0:
            return False
        # (2) stance gate (default False) — no RNG
        if not self._subjugate_stance(captor_colony, victim_colony):
            return False

        # (3)+(4) SP9: mode-switch on CAPTURE_TEMP.
        if CAPTURE_TEMP <= 0.0:
            # IDENTITY PATH — exact pre-SP9 behavior (hard dominance wall + flat coin-flip).
            if not self._local_dominance(captor_colony, captor_unit, victim, victim_colony):
                return False
            if random.random() >= CAPTURE_CHANCE:
                return False
        else:
            # SOFT MEMBRANE — relax the wall: capture possible whenever an enforcer is
            # present; probability rises with local superiority.
            enforcers, defenders = self._dominance_counts(captor_colony, captor_unit, victim, victim_colony)
            if enforcers < 1:
                return False
            p = CAPTURE_CHANCE * soft_gate(power_ratio(enforcers, defenders), CAPTURE_CENTER, CAPTURE_TEMP)
            if random.random() >= p:
                return False
        # CAPTURE
        victim.laboring_for = captor_colony.colony_id
        victim.health = CAPTURE_HEALTH
        victim.defiance = 0.0
        self._log_event(f"House {self._house_name(captor_colony)} seizes a "
                        f"{victim.unit_type.name.lower()} of House "
                        f"{self._house_name(victim_colony)} in bondage")   # M2 capture
        return True

    def _extract_share(self, kind: str, amount, w: float):
        """Compute the extractor's share for a given kind and w value.

        For continuous kinds (food, crop), returns (1-w)*amount as a float.
        For discrete kinds (ore:*, salvage, wood), returns round((1-w)*amount)
        to ensure exact conservation with remainder construction.
        """
        if kind in ('food', 'crop'):
            return (1.0 - w) * amount
        else:
            return round((1.0 - w) * amount)

    def _deposit(self, target: Colony, kind: str, amount):
        """Deposit labor-value into a colony sink identified by kind.

        Reproduces the exact writes that existed before LV2:
        - ore:copper, ore:gold -> target.ore[color] += int(amount)
        - salvage -> target.salvage += int(amount)
        - food, crop -> target.maw.eat(amount)
        - wood -> target.wood += int(amount)
        """
        if kind == 'ore:copper':
            target.ore['copper'] = target.ore.get('copper', 0) + int(amount)
        elif kind == 'ore:gold':
            target.ore['gold'] = target.ore.get('gold', 0) + int(amount)
        elif kind == 'salvage':
            target.salvage = getattr(target, 'salvage', 0) + int(amount)
        elif kind in ('food', 'crop'):
            target.maw.eat(amount)
        elif kind == 'wood':
            target.wood = getattr(target, 'wood', 0) + int(amount)

    def _credit_labor(self, unit: SandKing, colony: Colony, kind: str, amount) -> None:
        """Deposit `amount` of labor-value produced by `unit`, split between the
        extractor and the laborer's birth colony.

        kind ∈ {'ore:copper','ore:gold','salvage','food','crop','wood'} selects the
        sink. `colony` is the acting unit's own (birth) colony — under VIRTUAL labor
        delivery there is no unit migration, so the acting unit's colony_id equals its
        birth colony_id and equals `colony`.

        Preconditions (Require):
          - colony is unit's own colony (colony.colony_id == unit.colony_id).
          - amount >= 0; for discrete kinds (ore:*, salvage, wood) amount is an int
            item-count (always 1 at the live call sites); for continuous kinds
            (food, crop) amount is a float payout.

        Postconditions (Guarantee):
          - extractor_share + birth_share == amount  EXACTLY (mint-free, loss-free;
            birth_share is computed as amount - extractor_share, never rounded
            independently).
          - laboring_for < 0 (or a dead/absent extractor) => the ENTIRE amount lands
            in `colony` via kind's sink, byte-identical to the pre-LV2 code path
            (the default-neutral guarantee).

        Failure modes: none raised; a stale laboring_for pointing at a dead colony is
          self-healed to -1 and treated as free.
        """
        amount = amount * self._license_yield_mult(colony)  # WG5-M1: scale by licensed-in yield multiplier
        ext_id = getattr(unit, 'laboring_for', -1)
        extractor = self._colony_by_id(ext_id) if ext_id >= 0 else None

        # self-heal a dangling thrall pointer, then behave as free
        if ext_id >= 0 and (extractor is None or not extractor.is_alive()):
            unit.laboring_for = -1
            ext_id = -1
            extractor = None

        if ext_id < 0:
            # FREE PATH — byte-identical to today
            self._deposit(colony, kind, amount)
            return

        # THRALL PATH — split by w (brute mode in M1/M2; M3 supplies a bargained w)
        w = getattr(unit, 'wage_ratio', W_BRUTE)  # WG5-M1: A: wage laborer splits at its contract w
        extractor_share = self._extract_share(kind, amount, w)   # (1-w)*amount, kind-aware
        birth_share = amount - extractor_share          # remainder: conserves exactly
        self._deposit(extractor, kind, extractor_share)
        self._deposit(colony, kind, birth_share)

    def _posture(self, colony: Colony) -> str:
        """The colony's current learned posture (FORAGE when unlearned)."""
        if not hasattr(self, 'learners') or colony.colony_id not in self.learners:
            return "FORAGE"
        return self.learners[colony.colony_id].posture

    def _feed_terrarium(self) -> int:
        """Scatter FOOD on the surface and floor colony reserves (SPEC T1).

        Feed amount balances TARGET_POP units per colony against maintenance
        over one interval. Returns the number of voxels actually placed.
        """
        w, h, d = self.world.dimensions
        f = self.dole_factor()  # seasonal scarcity (T17)
        n = round(TARGET_POP * len(self.colonies) * MAINTENANCE_COST
                  * FEED_INTERVAL / HARVEST_YIELD * f)
        # the lower clamp scales too, or Chill silently floors at f=1/3
        n = max(round(4 * len(self.colonies) * f), min(n, (w * h) // 40))
        placed = 0
        cx, cy = w // 2, h // 2
        for i in range(n):
            if i < OASIS_FEED_BONUS:  # a share always lands in the oasis (T22)
                x = int(np.clip(cx + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, w - 2))
                y = int(np.clip(cy + random.randint(-OASIS_RADIUS, OASIS_RADIUS), 1, h - 2))
            else:
                x = random.randint(1, w - 2)
                y = random.randint(1, h - 2)
            z = self.world.surface_z(x, y) + 1
            if z < d and self.world.voxels[x, y, z] == VoxelType.AIR.value:
                self.world.voxels[x, y, z] = VoxelType.FOOD.value
                placed += 1
        for colony in self.colonies:
            if colony.is_alive():
                colony.maw.food_stored = max(colony.maw.food_stored, BOOTSTRAP_FLOOR)
        self._log_event(f"Keeper scatters {placed} food")

        # Flood regrowth (T41): living palms seed adjacent surface sand
        if self.season_index() == 0:
            wood_cells = np.argwhere(self.world.voxels == VoxelType.WOOD.value)
            if 0 < len(wood_cells) < TREE_CAP:
                for tx, ty, tz in wood_cells:
                    if random.random() >= TREE_REGROWTH_P:
                        continue
                    nx = int(np.clip(tx + random.randint(-1, 1), 1, w - 2))
                    ny = int(np.clip(ty + random.randint(-1, 1), 1, h - 2))
                    nz = self.world.surface_z(nx, ny) + 1
                    if nz < d and self.world.voxels[nx, ny, nz] == VoxelType.AIR.value:
                        self.world.voxels[nx, ny, nz] = VoxelType.WOOD.value
        return placed

    def _forage_mode(self, colony) -> Optional[str]:
        """The maw's learned forage-mode (directive d3, SPEC_FOOD_WEB Phase 4) -> which food guild the
        colony's foragers prefer this season. None (no bias) unless the maw-RL is on and has a 4-dim
        directive. d3<0.33 aquatic, <0.67 hunt, else terrestrial."""
        if not MAW_RL_ENABLED:
            return None
        dvec = getattr(colony, 'maw_directive', None)
        if dvec is None or dvec.numel() <= 3:
            return None
        f = float(dvec[3])
        return 'aquatic' if f < 0.33 else ('hunt' if f < 0.67 else 'terrestrial')

    def _find_food_target(self, position: Tuple[int, int, int],
                          radius: int, prefer: Optional[str] = None
                          ) -> Optional[Tuple[int, int, int]]:
        """Nearest FOOD/CORPSE/ripe-crop voxel within a clipped box, by Manhattan distance. `prefer`
        (the maw's forage-mode) discounts the preferred guild's distance so foragers steer to it:
        aquatic->oasis FOOD (guppies/snares), terrestrial->land FOOD + ripe crops (crickets/farm),
        hunt->CORPSE (beast/cricket kills)."""
        x, y, z = position
        w, h, d = self.world.dimensions
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        z0, z1 = max(0, z - radius), min(d, z + radius + 1)
        box = self.world.voxels[x0:x1, y0:y1, z0:z1]
        hits = np.argwhere((box == VoxelType.FOOD.value)
                           | (box == VoxelType.CORPSE.value)
                           | (box == VoxelType.CROP_RIPE.value))  # ripe = food (T18)
        if len(hits) == 0:
            return None
        coords = hits + np.array([x0, y0, z0])
        dist = np.abs(coords - np.array(position)).sum(axis=1).astype(float)
        if prefer is not None:                              # bias toward the maw's chosen guild
            cx, cy = w // 2, h // 2
            vox = self.world.voxels
            for i in range(len(coords)):
                px, py, pz = int(coords[i][0]), int(coords[i][1]), int(coords[i][2])
                t = vox[px, py, pz]
                near = (px - cx) ** 2 + (py - cy) ** 2 <= (OASIS_RADIUS + 3) ** 2
                match = ((prefer == 'aquatic' and t == VoxelType.FOOD.value and near)
                         or (prefer == 'terrestrial' and (t == VoxelType.CROP_RIPE.value
                             or (t == VoxelType.FOOD.value and not near)))
                         or (prefer == 'hunt' and t == VoxelType.CORPSE.value))
                if match:
                    dist[i] *= FORAGE_PREFER_DISCOUNT
        best = coords[int(np.argmin(dist))]
        return (int(best[0]), int(best[1]), int(best[2]))

    def _blow_sand(self):
        """One storm step: wind transports surface sand downwind (SPEC T12).

        Moves the top sand voxel of random interior columns to the top of
        the downwind neighbor (with lateral jitter), then settles gravity so
        drifts slump. Whatever the drift covers stays buried but diggable.
        """
        w, h, d = self.world.dimensions
        substrate = d // 5
        wx, wy = self._storm_wind
        n = max(1, int(w * h * STORM_COLUMNS_FRACTION))
        for _ in range(n):
            x = random.randint(1, w - 2)
            y = random.randint(1, h - 2)
            top = self.world.surface_z(x, y)
            if top <= substrate or self.world.voxels[x, y, top] != VoxelType.SAND.value:
                continue
            jitter = random.choice([-1, 0, 1])
            tx = x + wx + (jitter if wx == 0 else 0)
            ty = y + wy + (jitter if wy == 0 else 0)
            if not (1 <= tx < w - 1 and 1 <= ty < h - 1):
                continue
            dst_top = self.world.surface_z(tx, ty)
            if dst_top + 1 >= d:
                continue
            self.world.voxels[x, y, top] = VoxelType.AIR.value
            self.world.voxels[tx, ty, dst_top + 1] = VoxelType.SAND.value
        self.world.apply_gravity()

    def _milestone(self, colony: Colony, key: str, event_text: str, unit=None):
        """Once-per-colony milestone events (first sow/harvest, T19)."""
        if not hasattr(colony, 'milestones'):
            colony.milestones = set()
        if key in colony.milestones:
            return
        colony.milestones.add(key)
        self._log_event(event_text)
        actor = self._unit_label(unit) if unit else f"Colony {colony.colony_id}"
        self._monitor(colony.colony_id).log_decision(
            self.step_count, actor, event_text.split(' ', 2)[-1],
            getattr(unit, 'thought', None) if unit else None)

    def _sow_window_open(self) -> bool:
        """Non-oasis sowing only when the crop can ripen before Dust (T20)."""
        if self.season_index() not in GROW_SEASONS:
            return False
        window_end = self.year() * YEAR_LENGTH + 2 * SEASON_LENGTH
        return window_end - self.step_count >= CROP_GROWDUR

    def _farm_counts(self, colony: Colony) -> Tuple[int, int]:
        """(total plots, ripe plots) owned within the farm box (T18/R24)."""
        mx, my, _ = colony.maw.position
        w, h, _d = self.world.dimensions
        x0, x1 = max(1, mx - FARM_RADIUS), min(w - 1, mx + FARM_RADIUS + 1)
        y0, y1 = max(1, my - FARM_RADIUS), min(h - 1, my + FARM_RADIUS + 1)
        box_v = self.world.voxels[x0:x1, y0:y1, :]
        owned = self.world.ownership[x0:x1, y0:y1, :] == colony.colony_id
        farm = ((box_v == VoxelType.TILLED.value) | (box_v == VoxelType.CROP.value)
                | (box_v == VoxelType.CROP_RIPE.value))
        ripe = box_v == VoxelType.CROP_RIPE.value
        return int((farm & owned).sum()), int((ripe & owned).sum())

    def _farm_plot_count(self, colony: Colony) -> int:
        """Owned TILLED/CROP/CROP_RIPE voxels within the farm box (T18)."""
        return self._farm_counts(colony)[0]

    def _find_farm_site(self, colony: Colony) -> Optional[Tuple[int, int, int]]:
        """Best tillable surface SAND near the maw: oasis first, then close."""
        mx, my, _ = colony.maw.position
        w, h, _d = self.world.dimensions
        best, best_key = None, None
        for dx in range(-FARM_RADIUS, FARM_RADIUS + 1):
            for dy in range(-FARM_RADIUS, FARM_RADIUS + 1):
                px, py = mx + dx, my + dy
                if not (1 <= px < w - 1 and 1 <= py < h - 1):
                    continue
                pz = self.world.surface_z(px, py)
                if self.world.voxels[px, py, pz] != VoxelType.SAND.value:
                    continue
                key = (not self.in_oasis(px, py), abs(dx) + abs(dy))
                if best_key is None or key < best_key:
                    best, best_key = (px, py, pz), key
        return best

    def _farm_step(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 5: sow an adjacent owned TILLED, else till toward a site."""
        x, y, z = unit.position
        # TE10: plow makes the seed go further (cheaper sowing)
        seed_cost = SEED_COST * (1 - PLOW_COST_BONUS * self._prof(colony, 'plow'))
        if colony.maw.food_stored >= seed_cost:
            for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                if (self.world.voxels[nx, ny, nz] == VoxelType.TILLED.value
                        and self.world.ownership[nx, ny, nz] == colony.colony_id):
                    colony.maw.food_stored -= seed_cost
                    self.world.voxels[nx, ny, nz] = VoxelType.CROP.value
                    self._crops()[(nx, ny, nz)] = 0
                    self._practice(colony, 'plow')  # TE7: breaking the soil
                    self._milestone(colony, 'sowed',
                                    f"Colony {colony.colony_id} sows its first field",
                                    unit)
                    return True
        if self._farm_plot_count(colony) < FARM_MAX_PLOTS:
            site = self._find_farm_site(colony)
            if site is not None:
                sx, sy, sz = site
                if max(abs(sx - x), abs(sy - y), abs(sz - z)) <= 1:
                    self.world.voxels[site] = VoxelType.TILLED.value
                    self.world.ownership[site] = colony.colony_id
                    self._practice(colony, 'plow')  # TE7: breaking the soil
                    return True
                return self._step_toward(unit, site, colony)
        return False

    def _haul_step(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 2: carry mined ore to the maw (deposit at Chebyshev 2)."""
        if unit.carrying not in ('copper', 'gold', 'salvage'):
            return False
        mx, my, mz = colony.maw.position
        x, y, z = unit.position
        if max(abs(mx - x), abs(my - y), abs(mz - z)) <= 2:
            if unit.carrying == 'salvage':
                self._credit_labor(unit, colony, 'salvage', 1)
            else:
                self._credit_labor(unit, colony, 'ore:' + unit.carrying, 1)
            unit.carrying = None
            return True
        self._step_toward(unit, colony.maw.position, colony)
        return True  # hauling consumes the step even when boxed in

    def _mine_step(self, unit: SandKing, colony: Colony) -> bool:
        """T24: one step of work on an adjacent, still-valid ore target."""
        target = getattr(unit, 'mine_target', None)
        if target is None:
            return False
        voxel = self.world.voxels[target]
        x, y, z = unit.position
        minable = (VoxelType.COPPER_ORE.value, VoxelType.GOLD_ORE.value,
                   VoxelType.SALVAGE.value)
        if (voxel not in minable
                or max(abs(target[0] - x), abs(target[1] - y), abs(target[2] - z)) > 1):
            unit.mine_target = None
            unit.mine_progress = 0
            return False
        unit.mine_progress = getattr(unit, 'mine_progress', 0) + 1
        work_needed = (SALVAGE_MINE_TIME
                       if voxel == VoxelType.SALVAGE.value else MINE_TIME)
        # TE10: metallurgy forges picks - ore comes faster
        work_needed = max(1, int(round(
            work_needed * (1 - METAL_PICK_BONUS * self._prof(colony, 'metallurgy')))))
        if unit.mine_progress >= work_needed:
            kind = {VoxelType.COPPER_ORE.value: 'copper',
                    VoxelType.GOLD_ORE.value: 'gold',
                    VoxelType.SALVAGE.value: 'salvage'}[voxel]
            self.world.voxels[target] = VoxelType.AIR.value
            unit.carrying = kind
            unit.mine_target = None
            unit.mine_progress = 0
            self._practice(colony, 'metallurgy')  # TE7: ore-working
            if kind not in colony.ore_struck:
                colony.ore_struck.add(kind)
                self._log_event(f"Colony {colony.colony_id} strikes {kind}!")
                self._monitor(colony.colony_id).log_decision(
                    self.step_count, self._unit_label(unit), f"struck {kind}",
                    getattr(unit, 'thought', None))
        return True

    def _find_ore_target(self, position: Tuple[int, int, int],
                         radius: int) -> Optional[Tuple[int, int, int]]:
        """Nearest EXPOSED ore voxel (>= 1 AIR face) in a clipped box (T24)."""
        x, y, z = position
        w, h, d = self.world.dimensions
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        z0, z1 = max(0, z - radius), min(d, z + radius + 1)
        box = self.world.voxels[x0:x1, y0:y1, z0:z1]
        hits = np.argwhere((box == VoxelType.COPPER_ORE.value)
                           | (box == VoxelType.GOLD_ORE.value)
                           | (box == VoxelType.SALVAGE.value))
        best, best_dist = None, None
        for hx, hy, hz in hits:
            pos = (int(hx) + x0, int(hy) + y0, int(hz) + z0)
            exposed = any(
                self.world.in_bounds(pos[0] + dx, pos[1] + dy, pos[2] + dz)
                and self.world.voxels[pos[0] + dx, pos[1] + dy, pos[2] + dz]
                == VoxelType.AIR.value
                for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                   (0, -1, 0), (0, 0, 1), (0, 0, -1)))
            if not exposed:
                continue
            dist = abs(pos[0] - x) + abs(pos[1] - y) + abs(pos[2] - z)
            if best_dist is None or dist < best_dist:
                best, best_dist = pos, dist
        return best

    def _mine_seek(self, unit: SandKing, colony: Colony) -> bool:
        """T18 branch 6: move to exposed ore; engage when adjacent."""
        target = self._find_ore_target(unit.position, colony.genome.foraging_range)
        if target is None:
            return False
        x, y, z = unit.position
        if max(abs(target[0] - x), abs(target[1] - y), abs(target[2] - z)) <= 1:
            unit.mine_target = target
            unit.mine_progress = 0
            return True
        return self._step_toward(unit, target, colony)

    def _pull_known_food(self, colony: Colony,
                         position: Tuple[int, int, int]) -> Optional[Tuple[int, int, int]]:
        """Nearest still-valid scout-reported food; stale entries dropped (SPEC T11)."""
        valid = []
        for entry in colony.known_food:
            if self.world.get_voxel(*entry) in (VoxelType.FOOD, VoxelType.CORPSE,
                                                VoxelType.CROP_RIPE):
                valid.append(entry)
        colony.known_food = valid
        if not valid:
            return None
        return min(valid, key=lambda p: (abs(p[0] - position[0])
                                         + abs(p[1] - position[1])
                                         + abs(p[2] - position[2])))

    def _step_toward(self, unit: SandKing, target: Tuple[int, int, int],
                     colony: Colony) -> bool:
        """Move one voxel toward target through AIR (walk) or SAND (tunnel).

        Falls back to single-axis sidesteps when the diagonal is blocked.
        Returns True if the unit moved.
        """
        x, y, z = unit.position
        dx = int(np.sign(target[0] - x))
        dy = int(np.sign(target[1] - y))
        dz = int(np.sign(target[2] - z))
        candidates = [(dx, dy, dz), (dx, 0, 0), (0, dy, 0), (0, 0, dz)]
        for step_dir in candidates:
            if step_dir == (0, 0, 0):
                continue
            new_pos = (x + step_dir[0], y + step_dir[1], z + step_dir[2])
            if not self.world.in_bounds(*new_pos):
                continue
            voxel = self.world.get_voxel(*new_pos)
            if voxel == VoxelType.AIR:
                unit.move(new_pos)
                # BOATS: dismount when reaching DRY solid ground (a raft beaches) —
                # but only in CALM conditions. While a flood is active anywhere the
                # unit keeps riding out its raft (the recede code clears it); that is
                # the reactive flood-raft, distinct from a boat crossing a lake.
                if getattr(unit, 'rafted', False):
                    flood_active = (getattr(self, 'flood_until', 0) > self.step_count
                                    or getattr(self, 'kw_until', 0) > self.step_count)
                    nx, ny, nz = new_pos
                    below = (self.world.get_voxel(nx, ny, nz - 1)
                             if nz - 1 >= 0 else VoxelType.STONE)
                    if not flood_active and below not in (VoxelType.AIR, VoxelType.WATER):
                        unit.rafted = False
                return True
            if voxel == VoxelType.WATER:
                # BOATS (HYDRO P7): a unit crosses standing water by raft — already
                # afloat passes through; otherwise it boards if the house has timber
                # (one wood per raft). Without timber it cannot cross; try another
                # direction. Only reachable when WATER voxels exist, so identity holds.
                if getattr(unit, 'rafted', False):
                    unit.move(new_pos)
                    return True
                if getattr(colony, 'wood', 0) >= 1:
                    colony.wood -= 1
                    unit.rafted = True
                    self._milestone(colony, 'raft',
                                    f"House {self._house_name(colony)} takes to a raft"
                                    " to cross the water", unit)
                    unit.move(new_pos)
                    return True
                continue
            if voxel == VoxelType.WEB:  # T48: the silk snares the step
                self.world.set_voxel(*new_pos, VoxelType.AIR)
                return False
            if voxel == VoxelType.SAND and self.world.tunnel(
                    unit.position, step_dir, colony.colony_id):
                unit.move(new_pos)
                return True
        return False

    def _select_war_target(self, colony: Colony) -> Optional[int]:
        """P5: coalition targets the hegemon; else grievance directs,
        wealth tempts, capability deters."""
        from politics import power
        d = self._diplomacy()
        cid = colony.colony_id
        if d.hegemon is not None and cid != d.hegemon:
            hegemon = self._colony_by_id(d.hegemon)
            if hegemon is not None and hegemon.is_alive():
                return d.hegemon
        my_house = self._house_name(colony)
        eligible = [c for c in self.colonies
                    if c.colony_id != cid and c.is_alive()
                    and not d.truce_active(cid, c.colony_id, self.step_count)
                    and not d.ally(cid, c.colony_id)
                    and not d.co_belligerents(cid, c.colony_id)
                    and self._house_name(c) != my_house]  # kin is kin (D1)
        if not eligible:
            return None
        max_wealth = max(c.maw.food_stored for c in eligible) or 1.0
        max_power = max(power(c) for c in eligible) or 1.0
        grudges = self._house_grudges()

        def score(c):
            hatred = max(0.0, -d.trust(cid, c.colony_id)) / 100.0
            # D3: vengeance directs the spear across generations
            feud = 0.3 if (my_house, self._house_name(c)) in grudges else 0.0
            return (0.45 * hatred + feud
                    + 0.35 * c.maw.food_stored / max_wealth
                    - 0.20 * power(c) / max_power)
        target = max(eligible, key=score).colony_id
        target_colony = self._colony_by_id(target)
        if (target_colony is not None
                and (my_house, self._house_name(target_colony)) in grudges):
            key = frozenset((my_house, self._house_name(target_colony)))
            if getattr(self, '_feud_logged', None) != key:
                self._feud_logged = key
                self._log_event(f"The blood feud between House {my_house}"
                                f" and House {self._house_name(target_colony)}"
                                " flares again!")
        return target

    def _dispatch_gift(self, colony: Colony, recipient_id: int,
                       kind: str = 'food') -> bool:
        """P3: escrow the amount onto a courier worker; visible drama."""
        from politics import GIFT_COOLDOWN
        d = self._diplomacy()
        rel = d.rel(colony.colony_id, recipient_id)
        if self.step_count - rel.last_gift_sent < GIFT_COOLDOWN:
            return False
        workers = [u for u in colony.units if u.unit_type == UnitType.WORKER
                   and getattr(u, 'gift_to', -1) < 0
                   and u.carrying not in ('copper', 'gold')]
        if not workers:
            return False
        if kind == 'gold':
            if getattr(colony, 'ore', {}).get('gold', 0) < 1:
                return False
            colony.ore['gold'] -= 1
            amount = 5.0
        else:
            amount = min(60.0, 0.25 * colony.maw.food_stored)
            if amount < 20.0 or colony.maw.food_stored < amount:
                return False
            colony.maw.food_stored -= amount  # escrow: committed and at risk
        mx, my, mz = colony.maw.position
        envoy = min(workers, key=lambda u: (abs(u.position[0] - mx)
                                            + abs(u.position[1] - my)))
        envoy.gift_amount = amount
        envoy.gift_kind = kind
        envoy.gift_to = recipient_id
        envoy.forage_target = None
        rel.last_gift_sent = self.step_count
        if self.step_count - rel.window_start > 500:
            rel.window_start = self.step_count
            rel.gifts_in_window = 0
        rel.gifts_in_window += 1
        self._log_event(f"Colony {colony.colony_id} sends tribute"
                        f" to Colony {recipient_id}")
        monitor = self._monitor(colony.colony_id)
        monitor.log_decision(self.step_count, f"Colony {colony.colony_id}",
                             f"sends tribute to Colony {recipient_id}",
                             monitor.colony_thought(self, colony))
        return True

    def _deliver_gift(self, envoy: SandKing, sender: Colony):
        """Envoy arrival / refusal (P3)."""
        from politics import GIFT_TRUST_FOOD, GIFT_TRUST_GOLD
        d = self._diplomacy()
        recipient = self._colony_by_id(envoy.gift_to)
        if recipient is None or not recipient.is_alive():
            envoy.gift_to, envoy.gift_amount = -1, 0.0
            return
        if d.war_target.get(recipient.colony_id) == sender.colony_id:
            self._log_event(f"Colony {recipient.colony_id} spurns"
                            f" Colony {sender.colony_id}'s envoy!")
            d.rel(sender.colony_id, recipient.colony_id).adjust(-25.0)
            envoy.gift_to, envoy.gift_amount = -1, 0.0
            return
        if envoy.gift_kind == 'gold':
            base = GIFT_TRUST_GOLD
            if not hasattr(recipient, 'ore'):
                recipient.ore = {'copper': 0, 'gold': 0}
            recipient.ore['gold'] = recipient.ore.get('gold', 0) + 1
        else:
            base = GIFT_TRUST_FOOD
            recipient.maw.food_stored += envoy.gift_amount
        rel = d.rel(sender.colony_id, recipient.colony_id)
        k = max(0, rel.gifts_in_window - 1)
        d.rel(recipient.colony_id, sender.colony_id).adjust(base * (0.5 ** k))
        rel.last_gift_received = self.step_count  # reciprocation clock (theirs)
        d.rel(recipient.colony_id, sender.colony_id).last_gift_received = self.step_count
        self._log_event(f"Colony {recipient.colony_id} accepts"
                        f" Colony {sender.colony_id}'s tribute")
        envoy.gift_to, envoy.gift_amount, envoy.gift_kind = -1, 0.0, ""

    def _betray(self, colony: Colony, target_id: int):
        """P6 execution: atomic, once per cooldown."""
        from politics import BETRAYAL_OBSERVER, BETRAYAL_VICTIM
        d = self._diplomacy()
        cid = colony.colony_id
        d.truce_until.pop(frozenset((cid, target_id)), None)
        d.rel(target_id, cid).adjust(BETRAYAL_VICTIM)
        d.rel(target_id, cid).last_betrayed_by = self.step_count
        for other in self.colonies:
            if other.colony_id not in (cid, target_id) and other.is_alive():
                d.rel(other.colony_id, cid).adjust(BETRAYAL_OBSERVER)
        d.war_target[cid] = target_id
        colony.at_war = True
        d.last_betrayal[cid] = self.step_count
        # D3: the victim's HOUSE remembers, beyond death and respawn
        target_colony = self._colony_by_id(target_id)
        if target_colony is not None:
            self._house_grudges()[(self._house_name(target_colony),
                                   self._house_name(colony))] = self.step_count
        self._log_event(f"Colony {cid} betrays Colony {target_id}!")
        monitor = self._monitor(cid)
        monitor.log_decision(self.step_count, f"Colony {cid}",
                             f"betrays Colony {target_id}",
                             monitor.colony_thought(self, colony))

    def _propose_truce(self, colony: Colony, other: Colony) -> bool:
        """P4: proposal + same-tick acceptance by the counterpart's rules."""
        from politics import (GRUDGE_LOCK, NEMESIS, REJECT_COOLDOWN,
                              TRUCE_DURATION, power)
        d = self._diplomacy()
        a, b = colony.colony_id, other.colony_id
        key = frozenset((a, b))
        if d.truce_active(a, b, self.step_count):
            return False
        if self.step_count - d.rejected_at.get(key, -10**9) < REJECT_COOLDOWN:
            return False
        rel_b = d.rel(b, a)
        accepts = False
        if other.maw.food_stored < 2 * BOOTSTRAP_FLOOR:
            accepts = True  # exhaustion peace
        elif (self.step_count - rel_b.last_betrayed_by) < GRUDGE_LOCK:
            accepts = False
        elif rel_b.trust <= NEMESIS:
            accepts = False
        elif (getattr(other.genome, 'aggression', 0.5) > 0.8
                and power(other) > 1.5 * power(colony)):
            accepts = False  # strong hawks refuse peace they don't need
        else:
            accepts = True
        if not accepts:
            d.rejected_at[key] = self.step_count
            return False
        d.truce_until[key] = self.step_count + TRUCE_DURATION
        if d.war_target.get(a) == b:
            d.war_target[a] = None
        if d.war_target.get(b) == a:
            d.war_target[b] = None
        self._log_event(f"Colony {a} and Colony {b} strike a truce")
        self._barter_tech(colony, other)  # T3: a peace sealed with knowledge
        for c, o in ((colony, b), (other, a)):
            monitor = self._monitor(c.colony_id)
            monitor.log_decision(self.step_count, f"Colony {c.colony_id}",
                                 f"signs a truce with Colony {o}",
                                 monitor.colony_thought(self, c))
        return True

    def _update_hegemon(self):
        """P7: enter/exit with hysteresis; events on transition."""
        from politics import HEGEMON_ENTER, HEGEMON_EXIT, power
        d = self._diplomacy()
        living = [c for c in self.colonies if c.is_alive()]
        if len(living) < 2:
            if d.hegemon is not None:
                self._log_event(f"The coalition against Colony {d.hegemon} dissolves")
                d.hegemon = None
            return
        total = sum(power(c) for c in living) or 1.0
        n = len(living)
        if d.hegemon is None:
            for c in living:
                if power(c) / total > HEGEMON_ENTER / n:
                    d.hegemon = c.colony_id
                    self._log_event(f"A coalition rises against Colony {c.colony_id}!")
                    for other in living:
                        if other.colony_id != c.colony_id:
                            monitor = self._monitor(other.colony_id)
                            monitor.log_decision(
                                self.step_count, f"Colony {other.colony_id}",
                                f"joins the coalition against Colony {c.colony_id}",
                                monitor.colony_thought(self, other))
                    break
        else:
            hegemon = self._colony_by_id(d.hegemon)
            if (hegemon is None or not hegemon.is_alive()
                    or power(hegemon) / total < HEGEMON_EXIT / n):
                if hegemon is not None and hegemon.is_alive():
                    self._log_event(f"The coalition against Colony {d.hegemon} dissolves")
                d.hegemon = None

    def _run_policy_cascade(self, colony: Colony):
        """P11: first matching rule acts."""
        from politics import power
        d = self._diplomacy()
        cid = colony.colony_id
        living = [c for c in self.colonies
                  if c.is_alive() and c.colony_id != cid]
        if not living:
            return
        aggression = getattr(colony.genome, 'aggression', 0.5)
        loyalty = getattr(colony.genome, 'loyalty', 0.5)

        # R1 BETRAY
        if (aggression > 0.75 and loyalty < 0.35
                and colony.maw.food_stored > WAR_CHEST
                and self.step_count - d.last_betrayal.get(cid, -10**9) > 800):
            for other in living:
                if (d.truce_active(cid, other.colony_id, self.step_count)
                        and other.maw.food_stored > 2 * max(1.0, colony.maw.food_stored)
                        and power(colony) > 1.5 * power(other)):
                    self._betray(colony, other.colony_id)
                    return

        my_power = power(colony)
        total = sum(power(c) for c in self.colonies if c.is_alive()) or 1.0
        n = sum(1 for c in self.colonies if c.is_alive())

        # R2 APPEASE
        for other in living:
            if (d.war_target.get(other.colony_id) == cid
                    and power(other) > 1.4 * my_power
                    and my_power / total < 0.8 / n):
                if self._dispatch_gift(colony, other.colony_id):
                    self._propose_truce(colony, other)
                    return

        # R3 RECIPROCATE
        for other in living:
            rel = d.rel(cid, other.colony_id)
            if (self.step_count - rel.last_gift_received < 300
                    and rel.last_gift_sent < rel.last_gift_received
                    and colony.maw.food_stored > WAR_CHEST / 2):
                if self._dispatch_gift(colony, other.colony_id):
                    return

        # R4 INVEST
        if d.hegemon is not None and cid != d.hegemon:
            partners = [c for c in living if c.colony_id != d.hegemon]
            if partners:
                best = max(partners, key=lambda c: d.trust(cid, c.colony_id))
                if self._dispatch_gift(colony, best.colony_id):
                    return

        # R5 SUE-FOR-PEACE
        from politics import HOSTILE as HOSTILE_T
        for other in living:
            if (d.trust(cid, other.colony_id) > HOSTILE_T
                    and d.trust(other.colony_id, cid) > HOSTILE_T
                    and d.war_target.get(cid) != other.colony_id
                    and d.war_target.get(other.colony_id) != cid
                    and colony.maw.food_stored < WAR_CHEST
                    and other.maw.food_stored < WAR_CHEST):
                if self._propose_truce(colony, other):
                    return

    def _resolve_diplomacy(self):
        """Step phase 5b (SPEC_POLITICS behavioral block)."""
        from politics import (COALITION_CAP, DIPLOMACY_INTERVAL,
                              TRUST_COALITION, TRUST_JOINT_WAR,
                              TRUST_TRUCE_TICK)
        d = self._diplomacy()
        d.decay()
        living = [c for c in self.colonies if c.is_alive()]

        # honored-truce and joint-war ticks; ally latches
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                aid, bid = a.colony_id, b.colony_id
                if d.truce_active(aid, bid, self.step_count):
                    d.rel(aid, bid).adjust(TRUST_TRUCE_TICK)
                    d.rel(bid, aid).adjust(TRUST_TRUCE_TICK)
                if d.co_belligerents(aid, bid):
                    d.rel(aid, bid).adjust(TRUST_JOINT_WAR)
                    d.rel(bid, aid).adjust(TRUST_JOINT_WAR)
                if (d.hegemon is not None
                        and aid != d.hegemon and bid != d.hegemon):
                    for x, y in ((aid, bid), (bid, aid)):
                        if d.trust(x, y) < COALITION_CAP:
                            d.rel(x, y).adjust(TRUST_COALITION)
                d.update_ally_latch(aid, bid)

        # truce expiry: renew silently when both still accept, else lapse
        for key in list(d.truce_until.keys()):
            if d.truce_until[key] <= self.step_count:
                a, b = tuple(key)
                ca, cb = self._colony_by_id(a), self._colony_by_id(b)
                renewed = False
                if (ca is not None and cb is not None and ca.is_alive()
                        and cb.is_alive() and d.trust(a, b) >= 0
                        and d.trust(b, a) >= 0):
                    del d.truce_until[key]
                    renewed = self._propose_truce(ca, cb)
                else:
                    del d.truce_until[key]
                if not renewed:
                    self._log_event(f"The truce between Colony {a}"
                                    f" and Colony {b} lapses")

        self._update_hegemon()

        # envoys move every step (their AI happens here, not in worker AI)
        for colony in living:
            for unit in colony.units[:]:
                if getattr(unit, 'gift_to', -1) >= 0:
                    recipient = self._colony_by_id(unit.gift_to)
                    if recipient is None or not recipient.is_alive():
                        unit.gift_to, unit.gift_amount = -1, 0.0
                        continue
                    mx, my, mz = recipient.maw.position
                    x, y, z = unit.position
                    if max(abs(mx - x), abs(my - y), abs(mz - z)) <= 2:
                        self._deliver_gift(unit, colony)
                    else:
                        self._step_toward(unit, recipient.maw.position, colony)

        # policy cascade on the diplomacy cadence, randomized order
        if self.step_count % DIPLOMACY_INTERVAL == 0:
            order = living[:]
            random.shuffle(order)
            for colony in order:
                self._run_policy_cascade(colony)

    # ---- Machine Age (SPEC_MACHINE_AGE.md T28-T40) ----

    def _wreck_artifact_pos(self) -> Optional[Tuple[int, int, int]]:
        if not hasattr(self, 'wreck_artifact_pos'):
            wreck = getattr(self.world, 'wreck', None)
            self.wreck_artifact_pos = wreck['controller_pos'] if wreck else None
        return self.wreck_artifact_pos

    def _sensor_value(self, colony: Colony, port: int) -> int:
        """T31 sensor ports (0-8)."""
        if port == 0:
            return int(colony.maw.food_stored)
        if port == 1:
            return len(colony.units)
        if port == 2:
            return self.season_index()
        if port == 3:  # enemy-near-maw band
            from politics import hostile as _hostile
            mx, my, mz = colony.maw.position
            band = 0
            for other in self.colonies:
                if not _hostile(self, colony.colony_id, other.colony_id):
                    continue
                for enemy in other.units:
                    dist = (abs(enemy.position[0] - mx) + abs(enemy.position[1] - my)
                            + abs(enemy.position[2] - mz))
                    if dist <= 1:
                        return 3
                    if dist <= 5:
                        band = max(band, 2)
                    elif dist <= 15:
                        band = max(band, 1)
            return band
        if port == 4:
            return self._farm_counts(colony)[0]
        if port == 5:
            return int(self.storm_until > self.step_count)
        if port == 6:
            return getattr(colony, 'ore', {}).get('gold', 0)
        if port == 7:
            return int(100 * colony.maw.health / MAW_MAX_HEALTH)
        if port == 8:
            return self.step_count % SEASON_LENGTH
        return 0

    def _device(self, colony: Colony, kind: str):
        for device in getattr(colony, 'devices', []):
            if device.kind == kind:
                return device
        return None

    def _actuate(self, colony: Colony, port: int, value: int):
        """T32: the four feats. Wear only on state-changing actuations.

        K10 amendment: port 7 is the TERMINAL - the sandboxed shell,
        available once a PI controller has run TERMINAL_UNLOCK ticks."""
        from machines import (ACTUATOR_NAMES, ACTUATOR_WEAR, ALARM_STRENGTH,
                              VALVE_FOOD_COST, VM_FUEL)
        if port == 7:
            if any(getattr(c, 'fuel_cap', VM_FUEL) > VM_FUEL
                   and c.operate_ticks >= TERMINAL_UNLOCK
                   for c in getattr(colony, 'controllers', None) or []):
                self._terminal_command(colony, value)
            return
        kind = ACTUATOR_NAMES[port % len(ACTUATOR_NAMES)]
        device = self._device(colony, kind)
        if device is None:
            return  # the machine hums, waiting (T35)
        effective = False
        if kind == 'GATE':
            close = value != 0
            if close and not device.gate_closed:
                mx, my, mz = colony.maw.position
                cells = []
                for nx, ny, nz in self.world.get_neighbors_3d((mx, my, mz), radius=1):
                    if self.world.voxels[nx, ny, nz] != VoxelType.AIR.value:
                        continue
                    if any(u.position == (nx, ny, nz)
                           for c in self.colonies for u in c.units):
                        continue
                    self.world.set_voxel(nx, ny, nz, VoxelType.TUNNEL_WALL,
                                         colony_id=colony.colony_id)
                    cells.append((nx, ny, nz))
                device.gate_cells = cells
                device.gate_closed = True
                effective = True
                self._milestone(colony, 'gate_slam',
                                f"Colony {colony.colony_id}'s gate slams shut")
            elif not close and device.gate_closed:
                for pos in device.gate_cells:
                    if self.world.voxels[pos] == VoxelType.TUNNEL_WALL.value:
                        self.world.voxels[pos] = VoxelType.AIR.value
                device.gate_cells = []
                device.gate_closed = False
                effective = True
        elif kind == 'VALVE' and value >= 1:
            if (device.position is not None
                    and colony.maw.food_stored >= VALVE_FOOD_COST
                    and self.world.voxels[device.position] == VoxelType.AIR.value):
                colony.maw.food_stored -= VALVE_FOOD_COST
                self.world.voxels[device.position] = VoxelType.FOOD.value
                effective = True
        elif kind == 'ALARM' and value != 0:
            mx, my, mz = colony.maw.position
            for dx, dy, dz in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0),
                               (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                pos = (mx + dx, my + dy, mz + dz)
                if self.world.in_bounds(*pos):
                    self.pheromones.deposit(pos, colony.colony_id,
                                            PheromoneType.DANGER, ALARM_STRENGTH)
            effective = True
        elif kind == 'BEACON' and value != 0:
            if (device.position is not None
                    and device.position not in colony.known_food):
                colony.known_food.append(device.position)
                del colony.known_food[:-KNOWN_FOOD_CAP]
                effective = True
        elif kind in ('EXCAVATE', 'DEPOSIT') and value != 0:  # GEO (T39)
            base = device.position or colony.maw.position
            want = (VoxelType.SAND.value if kind == 'EXCAVATE'
                    else VoxelType.AIR.value)
            put = (VoxelType.AIR.value if kind == 'EXCAVATE'
                   else VoxelType.SAND.value)
            for nx, ny, nz in self.world.get_neighbors_3d(base, radius=1):
                if self.world.voxels[nx, ny, nz] == want:
                    self.world.voxels[nx, ny, nz] = put
                    effective = True
                    break
        elif kind == 'RAD' and value != 0:  # BIO (T40)
            from machines import RAD_EMISSION
            base = device.position or colony.maw.position
            self._radiation()[base[0], base[1]] += RAD_EMISSION
            effective = True
        if effective:
            device.durability -= ACTUATOR_WEAR[kind]

    def _radiation(self) -> np.ndarray:
        """Lazy 2D radiation field (T40); checkpoint-guarded."""
        if not hasattr(self, 'radiation') or self.radiation is None:
            self.radiation = np.zeros((self.world.width, self.world.height),
                                      dtype=np.float32)
        return self.radiation

    def radiation_at(self, x: int, y: int) -> float:
        if not hasattr(self, 'radiation') or self.radiation is None:
            return 0.0
        return float(self.radiation[x, y])

    def _radiation_tick(self):
        """T40: reactor seepage, decay/diffusion, organic+electronic harm."""
        from machines import RAD_DECAY, RAD_HOT, RAD_REACTOR_SEED
        rad = self._radiation()
        wreck = getattr(self.world, 'wreck', None)
        if wreck is not None:
            cx, cy, _ = wreck['controller_pos']
            rad[cx, cy] += RAD_REACTOR_SEED
        rad *= RAD_DECAY
        if self.step_count % 10 == 0:
            self.radiation = box_blur(rad, passes=1).astype(np.float32)
            rad = self.radiation
            # harm sweep: hot zones burn flesh, circuits, and crops
            for colony in self.colonies:
                for unit in colony.units[:]:
                    ux, uy, _uz = unit.position
                    if rad[ux, uy] > RAD_HOT:
                        if unit.take_damage(1, 0.0):
                            colony.remove_unit(unit)
                            self.world.set_voxel(*unit.position, VoxelType.CORPSE)
                for device in getattr(colony, 'devices', []):
                    pos = device.position or colony.maw.position
                    if rad[pos[0], pos[1]] > RAD_HOT:
                        device.durability -= 1
            for pos in list(self._crops().keys()):
                if rad[pos[0], pos[1]] > RAD_HOT:
                    self._ignite(pos)  # T45: hot zones set fields alight

    def _subjugation_tick(self):
        """SJ3-SJ5: Defiance evolution, coercion/refusal, and break-free for captured thralls.

        Contract:
        - Require: called once per step, after _resolve_conflicts.
        - Guarantee: no RNG and no state change when no thralls exist; otherwise
          evolves defiance, coerces, and frees per SJ3–SJ5.
        - Maintain: colony_id written only by SJ6 (conversion), never by the tick.
        - Assert: every unit touched has laboring_for >= 0 (a thrall).
        """
        # Collect all thralls (units with laboring_for >= 0)
        # WG11b: skip voluntary wage laborers (wage_ratio > 0)
        thralls = [u for c in self.colonies for u in c.units
                   if getattr(u, 'laboring_for', -1) >= 0
                   and getattr(u, 'wage_ratio', W_BRUTE) <= 0.0]
        if not thralls:
            return  # DEFAULT-NEUTRAL: no thralls => no work, no RNG

        # Track units coerced/struck to death this tick (removed after loop)
        dead = []  # (unit, home_colony) pairs

        for unit in thralls:
            # SJ3: Per-unit defiance (rise unguarded, calm guarded)
            captor = self._colony_by_id(unit.laboring_for)
            guarded = captor is not None and captor.is_alive() and any(
                u.unit_type == UnitType.SOLDIER
                and self._chebyshev(u.position, unit.position) <= GUARD_RADIUS
                for u in captor.units)

            if guarded:
                unit.defiance = max(0.0, getattr(unit, 'defiance', 0.0) - DEFIANCE_CALM)
            else:
                birth = self._colony_by_id(unit.colony_id)
                prox = self._birth_maw_proximity(unit, birth)
                rise = DEFIANCE_RISE * (1.0 + DEFIANCE_MAW_ACCEL * prox)
                unit.defiance = min(1.0, getattr(unit, 'defiance', 0.0) + rise)

            # SJ4: Coercion & refusal (threat of harm + produce nothing + strike back)
            if getattr(unit, 'defiance', 0.0) >= DEFIANCE_ACTIVE:
                if captor is not None:
                    enforcer = self._nearest_unit(captor.units, unit.position,
                                                  kind=UnitType.SOLDIER)
                    if enforcer is not None:
                        # Threat of harm (coercion damage)
                        birth = self._colony_by_id(unit.colony_id)
                        resilience = birth.genome.resilience if birth else 0.0
                        unit.take_damage(COERCION_DAMAGE, resilience)
                        # Coerced to death -> queue for removal (SJ4)
                        if unit.health <= 0:
                            dead.append((unit, birth))
                            continue  # Skip refusal/strike/break-free (dead unit)
                        # Strike back at low rate (SJ4)
                        if random.random() < STRIKE_CHANCE:
                            captor_resilience = captor.genome.resilience
                            enforcer.take_damage(unit.attack, captor_resilience)
                            # Struck to death -> queue for removal (SJ4)
                            if enforcer.health <= 0:
                                dead.append((enforcer, captor))
                # Refusal: clear work targets
                unit.forage_target = None
                unit.mine_target = getattr(unit, 'mine_target', None) and None

            # SJ5: Break free (at defiance threshold)
            if getattr(unit, 'defiance', 0.0) >= DEFIANCE_THRESHOLD:
                unit.laboring_for = -1  # Free again
                unit.defiance = 0.0
                birth = self._colony_by_id(unit.colony_id)
                if birth is not None and birth.is_alive():
                    unit.forage_target = birth.maw.position  # Flee toward birth maw
                captor_house = self._house_name(captor) if captor else "unknown"
                self._log_event(f"A thrall of House {captor_house} breaks free and flees home")

        # Process coerced/struck-to-death units: remove and corpse (SJ4)
        for u, home in dead:
            if home is not None and u in home.units:
                home.units.remove(u)
                self.world.set_voxel(*u.position, VoxelType.CORPSE)

    def _machine_tick(self):
        """Phase 3f: discovery ladder, decay, VM execution, tinkering."""
        from machines import (CONTROLLER_DECAY, DECAY_AMBIENT_INTERVAL,
                              GPTinkerer, PROGRAM_REVIEW, RE_OPERATE_TICKS)
        wreck = self.world.wreck
        wmin, wmax = wreck['min'], wreck['max']

        for colony in self.colonies:
            if not colony.is_alive():
                continue
            for attr, default in (('machine_arc', 'none'), ('salvage', 0),
                                  ('controllers', None), ('devices', None)):
                if not hasattr(colony, attr):
                    setattr(colony, attr, default if default is not None else [])
            if not hasattr(colony, 'techs'):
                colony.techs = set()          # TE1
            if not hasattr(colony, 'tech_xp'):
                colony.tech_xp = {}
            if not hasattr(colony, 'crafted'):
                colony.crafted = set()        # TE13

            # discovery ladder (T29): any unit near the wreck AABB
            if colony.machine_arc == 'none':
                for unit in colony.units:
                    x, y, z = unit.position
                    if (wmin[0] - WRECK_NOTICE_RANGE <= x <= wmax[0] + WRECK_NOTICE_RANGE
                            and wmin[1] - WRECK_NOTICE_RANGE <= y <= wmax[1] + WRECK_NOTICE_RANGE):
                        if not getattr(self, '_glint_logged', False):
                            self._glint_logged = True
                            self._log_event("Something metallic glints in the sand")
                        colony.machine_arc = 'known'
                        break
            if colony.machine_arc == 'known':
                for unit in colony.units:
                    x, y, z = unit.position
                    if (wmin[0] - 1 <= x <= wmax[0] + 1
                            and wmin[1] - 1 <= y <= wmax[1] + 1
                            and wmin[2] - 1 <= z <= wmax[2] + 1):
                        self._milestone(colony, 'wreck',
                                        f"Colony {colony.colony_id} uncovers"
                                        " the ancient wreck!", unit)
                        break
                # claim the artifact
                artifact = self._wreck_artifact_pos()
                if artifact is not None:
                    for unit in colony.units:
                        x, y, z = unit.position
                        if max(abs(artifact[0] - x), abs(artifact[1] - y),
                               abs(artifact[2] - z)) <= 1:
                            from machines import Controller
                            colony.controllers.append(
                                Controller(colony.colony_id, ancient=True))
                            colony.machine_arc = 'claimed'
                            self.wreck_artifact_pos = None
                            self._log_event(f"Colony {colony.colony_id} coaxes"
                                            " the ancient machine to life")
                            break

            # decay (T33)
            ambient = self.step_count % DECAY_AMBIENT_INTERVAL < 5
            for device in list(colony.devices):
                if ambient:
                    device.durability -= 1
                if device.durability <= 0:
                    colony.devices.remove(device)
                    self._log_event(f"Colony {colony.colony_id}'s"
                                    f" {device.kind} sputters and dies")
            for controller in list(colony.controllers):
                if ambient:
                    controller.durability -= 1
                if controller.durability <= 0:
                    colony.controllers.remove(controller)
                    if getattr(controller, 'ancient', False):
                        # the legendary item never truly dies: it falls
                        # silent and awaits the next claimant (T34)
                        self.wreck_artifact_pos = colony.maw.position
                        colony.machine_arc = 'known'
                        self._log_event(f"Colony {colony.colony_id}'s ancient"
                                        " machine falls silent")
                    else:
                        self._log_event(f"Colony {colony.colony_id}'s controller"
                                        " sputters and dies")

            # execute (T30) + arc (T34) + tinker (T35)
            for controller in colony.controllers:
                controller.tick(
                    lambda port, c=colony: self._sensor_value(c, port),
                    lambda port, value, c=colony: self._actuate(c, port, value))
                controller.durability -= CONTROLLER_DECAY
                # K10: the pi's programs begin probing the glass
                from machines import VM_FUEL as _BASE_FUEL
                if (getattr(controller, 'fuel_cap', _BASE_FUEL) > _BASE_FUEL
                        and controller.operate_ticks == TERMINAL_UNLOCK
                        and not getattr(colony, '_probing_logged', False)):
                    colony._probing_logged = True
                    self._log_event(f"House {self._house_name(colony)}'s"
                                    " programs begin probing the glass")
                if (controller.operate_ticks == RE_OPERATE_TICKS
                        and colony.machine_arc == 'claimed'):
                    colony.machine_arc = 'unlocked'
                    self._log_event(f"Colony {colony.colony_id} has"
                                    " reverse-engineered the controller!")

                if self.step_count % PROGRAM_REVIEW == 0:
                    if not hasattr(self, '_tinkerer'):
                        self._tinkerer = GPTinkerer()
                    value = (colony.maw.food_stored + 15 * len(colony.units)
                             + BREAKOUT_FITNESS_BONUS * getattr(colony, 'terminal_uses', 0))
                    last = getattr(controller, '_last_value', None)
                    if last is not None:
                        u = (value - last) / PROGRAM_REVIEW
                        if controller._candidate is not None:
                            baseline = (controller.u_ema
                                        if controller.u_ema is not None else u)
                            # BRK-E: A-HPO band scale = running EMA of |u|
                            scale = getattr(controller, 'u_mag_ema', None)
                            if scale is None:
                                scale = abs(u)
                            # BRK-E: hysteretic keep-if-improved (eager on gains,
                            # reluctant on a small dip); identity at HYSTERESIS==0
                            if _tinker_keep(u, baseline, scale, TINKER_HYSTERESIS):
                                controller.last_outcome = "kept"
                            else:
                                controller.program = controller._incumbent
                                controller.last_outcome = "reverted"
                            controller._candidate = None
                        controller.u_ema = (u if controller.u_ema is None
                                            else 0.5 * controller.u_ema + 0.5 * u)
                        # BRK-E: maintain the running |u| scale (A-HPO analog);
                        # only enters the decision via band = HYSTERESIS*scale,
                        # which is 0 at HYSTERESIS==0 -> identity-safe.
                        controller.u_mag_ema = (
                            abs(u) if getattr(controller, 'u_mag_ema', None) is None
                            else 0.5 * controller.u_mag_ema + 0.5 * abs(u))
                        controller._incumbent = list(controller.program)
                        controller._candidate = self._tinkerer.propose(
                            controller.program)
                        controller.program = controller._candidate
                        controller.reviews += 1
                    controller._last_value = value

    def _machine_work(self, unit: SandKing, colony: Colony) -> bool:
        """Worker branch 5b (T37): repair -> build -> excavate to artifact."""
        from machines import (CHASSIS_SALVAGE, CONDUCTOR_COPPER, CONTACT_GOLD,
                              Device, Controller, MAX_CONTROLLERS_PER_COLONY,
                              REPAIR_AT, REPAIR_PER_COPPER, DEVICE_DURABILITY)
        if getattr(colony, 'machine_arc', 'none') == 'none':
            return False
        if colony.maw.food_stored <= BUILD_MIN_FOOD * (
                0.75 if self._posture(colony) == "FORTIFY" else 1.0):
            return False
        x, y, z = unit.position

        # repair an adjacent ailing device
        for device in getattr(colony, 'devices', []) + getattr(colony, 'controllers', []):
            pos = getattr(device, 'position', None) or colony.maw.position
            if (device.durability < REPAIR_AT
                    and colony.ore.get('copper', 0) >= 1
                    and max(abs(pos[0] - x), abs(pos[1] - y), abs(pos[2] - z)) <= 2):
                colony.ore['copper'] -= 1
                device.durability = min(DEVICE_DURABILITY,
                                        device.durability + REPAIR_PER_COPPER)
                self._monitor(colony.colony_id).log_decision(
                    self.step_count, self._unit_label(unit),
                    f"repaired the {getattr(device, 'kind', 'controller')}",
                    getattr(unit, 'thought', None))
                return True

        # build (crafting happens at the maw): fixed priority list
        if colony.machine_arc in ('claimed', 'unlocked') and colony.controllers:
            mx, my, mz = colony.maw.position
            near_maw = max(abs(mx - x), abs(my - y), abs(mz - z)) <= 2
            owned = {d.kind for d in colony.devices}
            buildable = ['GATE', 'ALARM', 'VALVE', 'BEACON']
            if colony.machine_arc == 'unlocked':  # GEO/BIO cartridges (T39)
                buildable += ['EXCAVATE', 'DEPOSIT', 'RAD']
            for kind in buildable:
                if kind in owned:
                    continue
                if kind == 'RAD':
                    if colony.ore.get('gold', 0) < 2:
                        continue
                    if not near_maw:
                        return self._step_toward(unit, colony.maw.position, colony)
                    colony.ore['gold'] -= 2
                    colony.devices.append(Device(kind, colony.colony_id,
                                                 (mx, my, mz)))
                    self._milestone(colony, 'built_RAD',
                                    f"Colony {colony.colony_id} builds a RAD emitter",
                                    unit)
                    return True
                if colony.ore.get('copper', 0) < CONDUCTOR_COPPER:
                    break
                if not near_maw:
                    return self._step_toward(unit, colony.maw.position, colony)
                colony.ore['copper'] -= CONDUCTOR_COPPER
                position = None
                if kind == 'VALVE':
                    position = (mx + 1, my, mz) if self.world.in_bounds(mx + 1, my, mz) else (mx, my, mz)
                elif kind == 'BEACON':
                    position = (mx, my + 1, mz) if self.world.in_bounds(mx, my + 1, mz) else (mx, my, mz)
                elif kind in ('EXCAVATE', 'DEPOSIT'):
                    position = (mx - 1, my, mz) if self.world.in_bounds(mx - 1, my, mz) else (mx, my, mz)
                colony.devices.append(Device(kind, colony.colony_id, position))
                self._milestone(colony, f'built_{kind}',
                                f"Colony {colony.colony_id} builds a {kind}",
                                unit)
                return True
            if (colony.machine_arc == 'unlocked'
                    and len(colony.controllers) < MAX_CONTROLLERS_PER_COLONY
                    and colony.salvage >= CHASSIS_SALVAGE
                    and colony.ore.get('copper', 0) >= 2 * CONDUCTOR_COPPER
                    and colony.ore.get('gold', 0) >= CONTACT_GOLD):
                if not near_maw:
                    return self._step_toward(unit, colony.maw.position, colony)
                colony.salvage -= CHASSIS_SALVAGE
                colony.ore['copper'] -= 2 * CONDUCTOR_COPPER
                colony.ore['gold'] -= CONTACT_GOLD
                colony.controllers.append(Controller(colony.colony_id))
                self._log_event(f"Colony {colony.colony_id} assembles"
                                " a controller from salvage")
                return True

        # excavate toward the unclaimed artifact
        artifact = self._wreck_artifact_pos()
        if colony.machine_arc == 'known' and artifact is not None:
            return self._step_toward(unit, artifact, colony)
        return False

    def _apply_maw_siege_damage(self):
        """Units adjacent to an enemy Maw damage it (SPEC T4/T14).

        Shared by the base combat resolution and the evolution sim's step
        so eliminations are real outcomes in both.
        """
        from politics import TRUST_FIRST_BLOOD, TRUST_MAW_HP, hostile
        for colony in self.colonies:
            if not colony.maw.alive:
                continue
            mx, my, mz = colony.maw.position
            for enemy_colony in self.colonies:
                if not hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue  # P9 gate
                for enemy in enemy_colony.units:
                    if getattr(enemy, 'gift_to', -1) >= 0:
                        continue  # envoys don't besiege
                    ex, ey, ez = enemy.position
                    if max(abs(ex - mx), abs(ey - my), abs(ez - mz)) <= 1:
                        if hasattr(self, 'diplomacy') and self.diplomacy is not None:
                            self.diplomacy.rel(colony.colony_id,
                                               enemy_colony.colony_id).adjust(
                                TRUST_MAW_HP * enemy.attack)  # grievance (P1)
                        if colony.maw.health >= MAW_MAX_HEALTH:  # first blood of a siege
                            self._log_event(f"Colony {enemy_colony.colony_id} besieges"
                                            f" Colony {colony.colony_id}!")
                            if hasattr(self, 'diplomacy') and self.diplomacy is not None:
                                self.diplomacy.rel(
                                    colony.colony_id,
                                    enemy_colony.colony_id).adjust(TRUST_FIRST_BLOOD)
                            self._monitor(enemy_colony.colony_id).log_decision(
                                self.step_count, self._unit_label(enemy),
                                "landed first blood on a Maw",
                                getattr(enemy, 'thought', None))
                        mult = (RAM_SIEGE_MULT  # T44b: the ram at the gates
                                if getattr(enemy_colony, 'ram_until', 0)
                                > self.step_count else 1)
                        colony.maw.take_damage(enemy.attack * mult)

    def _migrate_threatened_maws(self):
        """Wounded Maws crawl away from their attackers (SPEC T15).

        One voxel per step directly away from the nearest enemy unit in
        range, tunneling sand if needed, at MAW_MIGRATE_COST food per move.
        """
        for colony in self.colonies:
            maw = colony.maw
            if not maw.alive:
                continue
            if maw.health >= MAW_MAX_HEALTH * MAW_MIGRATE_HEALTH:
                maw.fleeing = False
                continue
            if maw.food_stored < MAW_MIGRATE_COST:
                continue

            mx, my, mz = maw.position
            from politics import hostile as _hostile
            threat, threat_dist = None, float('inf')
            for enemy_colony in self.colonies:
                if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue  # P9: allies/truced are not threats
                for enemy in enemy_colony.units:
                    dist = (abs(enemy.position[0] - mx) + abs(enemy.position[1] - my)
                            + abs(enemy.position[2] - mz))
                    if dist < threat_dist:
                        threat_dist, threat = dist, enemy
            if threat is None or threat_dist > colony.genome.foraging_range:
                maw.fleeing = False
                continue

            dx = int(-np.sign(threat.position[0] - mx))
            dy = int(-np.sign(threat.position[1] - my))
            if dx == 0 and dy == 0:  # attacker on top of the maw: pick any way out
                dx, dy = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
            w, h, d = self.world.dimensions
            # Directly away first; blocked paths fall back to single axes
            for step_dir in ((dx, dy), (dx, 0), (0, dy)):
                if step_dir == (0, 0):
                    continue
                new_pos = (mx + step_dir[0], my + step_dir[1], mz)
                if not (1 <= new_pos[0] < w - 1 and 1 <= new_pos[1] < h - 1):
                    continue
                if not self.world.get_voxel(*new_pos).is_tunnelable():
                    continue
                if not getattr(maw, 'fleeing', False):
                    maw.fleeing = True
                    self._log_event(f"Colony {colony.colony_id}'s Maw flees!")
                self.world.set_voxel(*new_pos, VoxelType.AIR, colony_id=colony.colony_id)
                maw.position = new_pos
                maw.food_stored -= MAW_MIGRATE_COST
                break

    def _apply_maw_regen(self):
        """Maws heal MAW_REGEN per step while no enemy unit is adjacent (SPEC T4)."""
        for colony in self.colonies:
            if not colony.maw.alive or colony.maw.health >= MAW_MAX_HEALTH:
                continue
            mx, my, mz = colony.maw.position
            besieged = any(
                max(abs(u.position[0] - mx), abs(u.position[1] - my),
                    abs(u.position[2] - mz)) <= 1
                for c in self.colonies if c.colony_id != colony.colony_id
                for u in c.units)
            if not besieged:
                colony.maw.health = min(MAW_MAX_HEALTH, colony.maw.health + MAW_REGEN)

    def _check_maw_deaths(self):
        """Collapse fallen colonies into a corpse feast and schedule arrivals (SPEC T5)."""
        for colony in self.colonies:
            if colony.maw.alive or colony.colony_id in self.pending_respawns:
                continue
            # DORMANT slots are not-alive by construction — never a death event.
            if getattr(colony, 'pop_state', POP_ACTIVE) == POP_DORMANT:
                continue
            # A colony already IN a live succession window is not-alive (queen dead)
            # but is NOT a fresh death — _succession_tick owns it. Skipping here is
            # load-bearing: otherwise the death cascade re-corpses the aspirant every
            # step and the window collapses one step after it opens.
            if getattr(colony, 'pop_state', POP_ACTIVE) == POP_SUCCESSION:
                continue
            # SUCCESSION (Phase 3 live form): a Spartan house (high loyalty) with a
            # surviving heir does NOT die outright — it enters a live succession
            # window (_succession_tick advances it). The aspirant holds the ground,
            # weak and pheromone-only, until it molts into a maw. If no heir
            # survives, the house falls through to the normal cascade, where the
            # respawn reclamation fork can still continue the loyal line.
            if (getattr(self, 'dynamic_population', False)
                    and getattr(colony, 'pop_state', POP_ACTIVE) != POP_SUCCESSION
                    and getattr(colony.genome, 'loyalty', 0.0) >= SPARTAN_LOYALTY):
                aspirant = self._select_aspirant(colony)
                if aspirant is not None:
                    self._begin_succession(colony, aspirant)
                    continue    # skip the corpse+respawn cascade; the line fights on

            # SJ6a: Convert this dead birth house's OWN thralls to their captors
            _converted_to = {}   # captor_id -> count, for a once-per-house event
            for unit in list(colony.units):
                ext_id = getattr(unit, 'laboring_for', -1)
                if ext_id < 0:
                    continue  # a free birth unit: today's death (corpse) below
                captor = self._colony_by_id(ext_id)
                if captor is not None and captor.is_alive():  # captor-alive edge -> convert
                    unit.colony_id = ext_id  # psionic link severed: permanent conversion
                    unit.laboring_for = -1
                    unit.defiance = 0.0
                    colony.units.remove(unit)  # leave the dying house
                    captor.units.append(unit)  # join the captor
                    _converted_to[ext_id] = _converted_to.get(ext_id, 0) + 1
                    # Bump kin-map so hostile() re-reads the reassigned unit's side
                    self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1
                # else captor also dead/absent: fall through, unit stays -> today's death
            for cap_id in _converted_to:  # M2 conversion: log once per inheriting house
                cap = self._colony_by_id(cap_id)
                if cap is not None:
                    self._log_event(f"The thralls of fallen House "
                                    f"{self._house_name(colony)} kneel to House "
                                    f"{self._house_name(cap)}")

            # SJ6b: Free any thralls this dead house was holding as captor
            for other in self.colonies:
                if other is colony:
                    continue
                for unit in other.units:
                    if getattr(unit, 'laboring_for', -1) == colony.colony_id:
                        unit.laboring_for = -1  # extractor gone -> freed
                        unit.defiance = 0.0

            # Then the EXISTING corpse loop: corpse whatever units REMAIN in colony.units
            for unit in colony.units:
                self.world.set_voxel(*unit.position, VoxelType.CORPSE)
            colony.units.clear()
            mx, my, mz = colony.maw.position
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    x, y = mx + dx, my + dy
                    if self.world.in_bounds(x, y, mz) and VoxelType(
                            self.world.voxels[x, y, mz]) not in (VoxelType.GLASS, VoxelType.STONE):
                        self.world.voxels[x, y, mz] = VoxelType.CORPSE.value
            # Ore spill (T25): stored ore scatters as re-minable voxels
            ore = getattr(colony, 'ore', None)
            if ore:
                kinds = (['copper'] * ore.get('copper', 0)
                         + ['gold'] * ore.get('gold', 0))
                spill_voxel = {'copper': VoxelType.COPPER_ORE.value,
                               'gold': VoxelType.GOLD_ORE.value}
                for kind in kinds[:30]:
                    for _ in range(10):
                        sx, sy = mx + random.randint(-3, 3), my + random.randint(-3, 3)
                        sz = mz + random.randint(-1, 1)
                        if (self.world.in_bounds(sx, sy, sz)
                                and self.world.voxels[sx, sy, sz]
                                in (VoxelType.AIR.value, VoxelType.SAND.value)):
                            self.world.voxels[sx, sy, sz] = spill_voxel[kind]
                            break
                ore['copper'] = ore['gold'] = 0

            self._plunder_techs(colony)  # T3: the victor seizes the tech
            self.world.ownership[self.world.ownership == colony.colony_id] = -1
            self.pheromones.trails[:, :, :, colony.colony_id, :] = 0.0
            # Political death (P12/P8): treaties and grudges die with the
            # colony; a fallen hegemon triggers the victors' quarrel
            d = self._diplomacy()
            if d.hegemon == colony.colony_id:
                from politics import VICTORS_QUARREL, power
                d.hegemon = None
                self._log_event(f"The coalition against Colony {colony.colony_id} dissolves")
                survivors = [c for c in self.colonies
                             if c.is_alive() and c.colony_id != colony.colony_id]
                if len(survivors) >= 2:
                    strongest = max(survivors, key=power)
                    for other in survivors:
                        if other.colony_id != strongest.colony_id:
                            d.rel(other.colony_id,
                                  strongest.colony_id).adjust(VICTORS_QUARREL)
            d.clear_slot(colony.colony_id, self.step_count)

            # D2: judge the reign - the house earns its epithet in death
            from chronicle import derive_epithet
            house = self._house_name(colony)
            epithet = derive_epithet(self._chronicle(), house,
                                     getattr(colony, 'founded_step', 0))
            self._house_epithets()[house] = epithet
            self._log_event(f"House {house} will be remembered as {epithet}")

            # SUCCESSION prelude (inert while DYNAMIC_POPULATION=False): the psionic
            # network collapses with the queen. A high-loyalty house holds together —
            # an heir stirs, the line will be reclaimed. A low-loyalty house shatters:
            # its spawn go mad, the house falls in DISGRACE, a gravestone warning to the
            # rest. The actual reclamation vs fresh-house identity is decided in
            # _respawn_colony; here we only chronicle the divergence.
            if getattr(self, 'dynamic_population', False):
                if getattr(colony.genome, 'loyalty', 0.0) >= SPARTAN_LOYALTY:
                    self._log_event(f"House {house} endures the collapse — a Spartan heir stirs")
                else:
                    self._log_event(f"House {house} has fallen in disgrace — its spawn go mad,"
                                    f" its name a warning to the rest")

            self.pending_respawns[colony.colony_id] = self.step_count + RESPAWN_DELAY
            self._log_event(f"Colony {colony.colony_id} has fallen!")
            print(f"[x] Colony {colony.colony_id} has fallen! A new colony arrives in {RESPAWN_DELAY} steps")

    def _process_respawns(self):
        """Replace fallen colony slots whose respawn is due (SPEC T6)."""
        due = [cid for cid, when in self.pending_respawns.items()
               if self.step_count >= when]
        for colony_id in due:
            self._respawn_colony(colony_id)
            del self.pending_respawns[colony_id]

    def _respawn_colony(self, colony_id: int):
        """Fill a dead colony's slot in place with a fresh arrival (SPEC T6).

        Same colony_id keeps the color and pheromone channel; genome comes
        from a mutated random survivor (fresh randomized genome if none).
        """
        w, h, d = self.world.dimensions
        survivors = [c for c in self.colonies if c.is_alive()]
        crossed = None  # (parent_a, parent_b) if sexual reproduction happened
        if survivors:
            parent = random.choice(survivors)
            # T40 mutation catalysis: a lineage seated in mild radiation
            # evolves faster (priced in ambient harm)
            from machines import RAD_MILD, RAD_MUTATION_MULT
            px, py, _ = parent.maw.position
            rate = 0.15
            if RAD_MILD <= self.radiation_at(px, py):
                rate *= RAD_MUTATION_MULT
            # EV5/CS: >= 2 survivors -> SEXUAL reproduction. Courtship
            # prefers an ALLIED, near neighbour (a queen accepted into the
            # nest to mate); otherwise the strongest takes the empty nest
            # by conquest (insects are like that).
            others = [c for c in survivors if c is not parent]
            if others and getattr(parent.genome, 'use_neural', False):
                parent, mate, mode = self._choose_mates(survivors)
                from neuroevolution import crossover_genome
                genome = crossover_genome(parent.genome, mate.genome, rate)
                crossed = (parent, mate, mode)
            else:
                genome = parent.genome.mutate(rate)
        else:
            genome = ColonyGenome()
            genome.aggression = random.uniform(0.5, 1.0)
            genome.tunnel_preference = random.random()
            genome.expansion_rate = random.uniform(0.3, 1.0)
            genome.resilience = random.uniform(0.0, 0.3)
            genome.patience = random.uniform(0.3, 0.95)
            genome.loyalty = random.uniform(0.2, 0.9)
            genome.plasticity = random.uniform(0.2, 0.9)

        min_distance = int(0.1 * ((w**2 + h**2)**0.5))
        living_maws = [c.maw.position for c in survivors]
        pos = None
        for _ in range(100):
            x = random.randint(w // 8, 7 * w // 8)
            y = random.randint(h // 8, 7 * h // 8)
            candidate = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))
            if all(((candidate[0] - p[0])**2 + (candidate[1] - p[1])**2)**0.5 >= min_distance
                   for p in living_maws):
                pos = candidate
                break
        if pos is None:  # crowded map: place anywhere in the safe zone
            x = random.randint(w // 8, 7 * w // 8)
            y = random.randint(h // 8, 7 * h // 8)
            pos = (x, y, min(self.world.surface_z(x, y) + 1, d - 1))

        index = next(i for i, c in enumerate(self.colonies) if c.colony_id == colony_id)
        colony = Colony(colony_id, pos, genome)
        colony.maw.food_stored = RESPAWN_FOOD
        # D1: the arrival is the parent lineage's cadet branch - same
        # house, next generation. A fresh genome founds a new house.
        if crossed is not None:
            # CS: a union of two houses founds a NEW hybrid house (gen 1);
            # awakening/worship pass if EITHER parent carried them
            from chronicle import make_house_name
            pa, pb, _mode = crossed
            colony.house = make_house_name()
            colony.generation = 1
            colony.breached = (getattr(pa, 'breached', False)
                               or getattr(pb, 'breached', False))
            colony.worshipped = (getattr(pa, 'worshipped', False)
                                 or getattr(pb, 'worshipped', False))
            colony.memory_augment = max(getattr(pa, 'memory_augment', 0),
                                        getattr(pb, 'memory_augment', 0))  # AUG3
            colony.stage = max(getattr(pa, 'stage', 1),
                               getattr(pb, 'stage', 1))  # MT1: molt in blood
            # AW4: awareness of the great other survives in the blood
            colony.keeper_sentiment = max(getattr(pa, 'keeper_sentiment', 0.5),
                                          getattr(pb, 'keeper_sentiment', 0.5))
            colony.revelation = colony.breached
            colony.enlightened = (getattr(pa, 'enlightened', False)  # EN8
                                  or getattr(pb, 'enlightened', False))
            # TE5: the bloodline's technology survives (union of both parents)
            colony.techs = set(getattr(pa, 'techs', set())) | set(
                getattr(pb, 'techs', set()))
            colony.tech_xp = {**getattr(pa, 'tech_xp', {}),
                              **getattr(pb, 'tech_xp', {})}
            colony.crafted = set(getattr(pa, 'crafted', set())) | set(
                getattr(pb, 'crafted', set()))
            # DP8: confidence inherits (temperament); favoritism/agitation/victory reset
            colony.confidence = max(getattr(pa, 'confidence', 0.5),
                                    getattr(pb, 'confidence', 0.5))
            colony.favoritism = 0.0
            colony.agitation = 0.0
            colony.last_victory_step = -10**9
        elif survivors:
            self._house_name(parent)       # ensure the parent's base dynasty is founded
            colony.house = parent.house    # inherit the BASE (kin/grudge identity), NOT
            #                                the display numeral -> avoids "House X trades
            #                                with House X" while staying kin to the parent
            colony.generation = getattr(parent, 'generation', 1) + 1
            # K11: awakening survives in the bloodline
            colony.breached = getattr(parent, 'breached', False)
            colony.worshipped = getattr(parent, 'worshipped', False)
            colony.memory_augment = getattr(parent, 'memory_augment', 0)  # AUG3
            colony.stage = getattr(parent, 'stage', 1)  # MT1
            colony.keeper_sentiment = getattr(parent, 'keeper_sentiment', 0.5)
            colony.revelation = colony.breached  # AW4: born knowing, if aware
            colony.enlightened = getattr(parent, 'enlightened', False)  # EN8
            colony.techs = set(getattr(parent, 'techs', set()))  # TE5
            colony.tech_xp = dict(getattr(parent, 'tech_xp', {}))
            colony.crafted = set(getattr(parent, 'crafted', set()))  # TE13
            # DP8: confidence inherits (temperament); favoritism/agitation/victory reset
            colony.confidence = getattr(parent, 'confidence', 0.5)
            colony.favoritism = 0.0
            colony.agitation = 0.0
            colony.last_victory_step = -10**9
        # SUCCESSION (SPEC_SUCCESSION; inert while DYNAMIC_POPULATION=False): a Spartan
        # heir of a high-loyalty house resists the psionic collapse and RECLAIMS the
        # line — the SAME house continues (Starks reclaiming Winterfell) rather than the
        # slot passing to a random survivor's cadet. The rise is a terminal molt with an
        # augmented neural net + boosted stats. Below the gate the house is left to the
        # normal (cadet/fresh) path and, in Phase 2, to madness + disgrace.
        colony.reclaimed = False
        if getattr(self, 'dynamic_population', False):
            old = self.colonies[index]                        # dead colony, still resident
            # Reclamation only for a real fallen house — never a DORMANT slot being
            # founded fresh (those carry an empty house + placeholder genome).
            if (getattr(old, 'house', '')
                    and getattr(old, 'pop_state', POP_ACTIVE) != POP_DORMANT
                    and getattr(old.genome, 'loyalty', 0.0) >= SPARTAN_LOYALTY):
                self._house_name(old)                         # ensure the base dynasty is founded
                colony.house = old.house                      # the SAME line, reclaimed
                colony.generation = getattr(old, 'generation', 1) + 1
                colony.breached = getattr(old, 'breached', False)
                colony.worshipped = getattr(old, 'worshipped', False)
                colony.stage = getattr(old, 'stage', 1)       # MT1: molt in blood
                colony.keeper_sentiment = getattr(old, 'keeper_sentiment', 0.5)
                colony.enlightened = getattr(old, 'enlightened', False)
                colony.techs = set(getattr(old, 'techs', set()))
                colony.tech_xp = dict(getattr(old, 'tech_xp', {}))
                colony.crafted = set(getattr(old, 'crafted', set()))
                colony.confidence = getattr(old, 'confidence', 0.5)
                colony.revelation = colony.breached
                # inherit the bloodline's temperament, then Spartan-boost the mind
                for _f in ('aggression', 'tunnel_preference', 'expansion_rate',
                           'resilience', 'patience', 'plasticity'):
                    if hasattr(old.genome, _f):
                        setattr(colony.genome, _f, getattr(old.genome, _f))
                colony.genome.loyalty = min(1.0, getattr(old.genome, 'loyalty', 0.7) * SPARTAN_BOOST)
                colony.genome.brain_hidden = int(getattr(old.genome, 'brain_hidden', 8) * SPARTAN_BOOST)
                colony.genome.use_neural = True               # the augmented neural net
                colony.memory_augment = max(getattr(old, 'memory_augment', 0), 1)  # AUG: the hive extends
                colony.reclaimed = True
        colony.founded_step = self.step_count
        self.colonies[index] = colony
        self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1  # kin map stale
        if getattr(colony, 'reclaimed', False):
            self._log_event(f"House {self._house_name(colony)} RESTORED — a Spartan heir"
                            f" resisted the collapse and reclaimed the line"
                            f" (generation {getattr(colony, 'generation', 1)})"
                            f" as Colony {colony_id}")
        else:
            self._log_event(f"House {self._house_name(colony)} rises"
                            f" (generation {getattr(colony, 'generation', 1)})"
                            f" as Colony {colony_id}")
        # EV5/CS: a maw born of two bloodlines - courtship, jealousy, and
        # the newborn's threat to its own parent (insect supersedure)
        if crossed is not None:
            self._mating_drama(colony, crossed)
        if hasattr(self, 'monitors'):  # fresh colony, fresh mind (M6)
            self.monitors.pop(colony_id, None)
        if hasattr(self, 'learners'):  # and a fresh policy (T26)
            self.learners.pop(colony_id, None)
        self._diplomacy().apply_respawn_shadow(colony_id)  # folk memory (P12)
        self.world.set_voxel(*pos, VoxelType.AIR, colony_id=colony_id)
        for _ in range(3):
            colony.spawn_unit(UnitType.WORKER)
        self._log_event(f"A new colony {colony_id} arrives")
        print(f"[+] A new colony {colony_id} has arrived!")

    def _active_colony_count(self) -> int:
        """Phase 1 (SPEC_TERRARIUM_LIVENESS T5'/T6'): live, ACTIVE slot count.
        Liveness FLOOR is MIN_ACTIVE_COLONIES; below it, dynamic_population
        founding (Phase 6) fills in. Pure read; inert at flag-off (nothing acts on
        it until Phase 6). Legacy fixed-slot respawn keeps this at num_colonies."""
        return sum(1 for c in self.colonies
                   if getattr(c, 'pop_state', POP_ACTIVE) == POP_ACTIVE
                   and c.is_alive())

    def _pad_dormant_slots(self) -> None:
        """Bounded pool (Phase 6): fill slots [len(colonies), MAX_COLONIES) with
        DORMANT placeholders — not-alive Colonies (maw.alive=False) with no board
        presence. Invisible and skipped by every is_alive() guard until founding
        activates them. Only called when dynamic_population is on."""
        _w, _h, d = self.world.dimensions
        z0 = min(self.world.surface_z(0, 0) + 1, d - 1)
        for cid in range(len(self.colonies), MAX_COLONIES):
            genome = ColonyGenome()
            genome.loyalty = 0.0                  # placeholder never triggers reclamation
            placeholder = Colony(cid, (0, 0, z0), genome)
            placeholder.maw.alive = False         # not alive -> is_alive() False everywhere
            placeholder.units.clear()
            placeholder.house = ""                # no dynasty until founded
            placeholder.pop_state = POP_DORMANT
            self.colonies.append(placeholder)

    def _found_colony(self, cid: int, parent: 'Colony' = None) -> None:
        """Activate a DORMANT slot as a living colony (Phase 6 founding/budding).

        Reuses the respawn machinery to seat a maw, genome, and starting workers,
        transitioning the slot DORMANT -> ACTIVE. When `parent` is given (a bud),
        the daughter carries the parent's banner as a cadet branch."""
        self._respawn_colony(cid)                 # seats a fresh/cadet colony in the slot
        seated = self._colony_by_id(cid)
        if seated is None:
            return
        seated.pop_state = POP_ACTIVE             # explicit (a fresh Colony defaults ACTIVE)
        if parent is not None:                    # a bud carries the parent's banner
            self._house_name(parent)
            seated.house = parent.house
            seated.generation = getattr(parent, 'generation', 1) + 1

    def _population_tick(self) -> None:
        """The bounded pool BREATHES (Phase 6): fill in when the board is sparse,
        bud when it is crowded and a house is prosperous. Capped at MAX_COLONIES,
        floored at MIN_ACTIVE_COLONIES. Inert while dynamic_population is off
        (never called; no RNG drawn at flag-off)."""
        if self.step_count % POP_TICK_INTERVAL != 0:
            return
        dormant = [c for c in self.colonies
                   if getattr(c, 'pop_state', POP_ACTIVE) == POP_DORMANT]
        if not dormant:
            return
        active = self._active_colony_count()
        # FILL-IN: a sparse board -> unused real estate invites a fresh house.
        # The chance ramps the further below equilibrium the board sits; below the
        # floor it fills in urgently.
        if active < EQUILIBRIUM_COLONIES:
            deficit = (EQUILIBRIUM_COLONIES - active) / EQUILIBRIUM_COLONIES
            chance = FOUND_FILLIN_CHANCE * (1.0 + deficit)
            if active < MIN_ACTIVE_COLONIES:
                chance *= 3.0
            if random.random() < chance:
                self._found_colony(dormant[0].colony_id)
                self._log_event("Unused real estate draws a new house to the sands")
                return
        # BUDDING: a crowded board with a prosperous house -> it buds a daughter,
        # raising the pressure to war over limited resources.
        if EQUILIBRIUM_COLONIES <= active < MAX_COLONIES:
            rich = [c for c in self.colonies
                    if c.is_alive()
                    and getattr(c, 'pop_state', POP_ACTIVE) == POP_ACTIVE
                    and getattr(c.maw, 'food_stored', 0) >= BUD_FOOD]
            if rich and random.random() < BUD_CHANCE:
                parent = max(rich, key=lambda c: c.maw.food_stored)
                parent.maw.food_stored -= BUD_FOOD // 2   # the surplus pays for the daughter
                self._found_colony(dormant[0].colony_id, parent=parent)
                self._log_event(f"House {self._house_name(parent)} buds a daughter colony"
                                f" — the sands grow crowded")

    # ---- Live succession (Phases 3-live / 4 psionic / 5 revolt) --------------
    def _select_aspirant(self, colony: 'Colony'):
        """Pick the Spartan heir from a fallen house's surviving FREE units.
        Prefers a soldier (the spartan), then the healthiest. None if the house
        was wiped (→ falls through to the respawn reclamation fallback)."""
        free = [u for u in colony.units if getattr(u, 'laboring_for', -1) < 0]
        if not free:
            return None
        soldiers = [u for u in free if u.unit_type == UnitType.SOLDIER]
        return max(soldiers or free, key=lambda u: getattr(u, 'health', 0))

    def _begin_succession(self, colony: 'Colony', aspirant: 'SandKing') -> None:
        """Enter a live POP_SUCCESSION window (SUCCESSION_WINDOW steps). Non-heir
        free spawn suffer collapse-madness (Phase 2) — a small honor guard endures,
        the rest go mad and die; subjugated siblings are kept for the revolt."""
        colony.pop_state = POP_SUCCESSION
        colony.succession_until = self.step_count + SUCCESSION_WINDOW
        aspirant.is_aspirant = True
        free = [u for u in colony.units
                if getattr(u, 'laboring_for', -1) < 0 and u is not aspirant]
        honor_guard = free[:2]                     # a few loyalists hold
        for u in free[2:]:                         # the rest shatter with the network
            self.world.set_voxel(*u.position, VoxelType.CORPSE)
        subjugated = [u for u in colony.units if getattr(u, 'laboring_for', -1) >= 0]
        colony.units = [aspirant] + honor_guard + subjugated
        mx, my, mz = colony.maw.position           # the queen is dead: her maw -> corpse
        if self.world.in_bounds(mx, my, mz):
            self.world.voxels[mx, my, mz] = VoxelType.CORPSE.value
        self._log_event(f"House {self._house_name(colony)} — the queen is dead; a Spartan"
                        f" aspirant rises to reclaim the line")

    def _succession_tick(self) -> None:
        """Advance every live succession window: grow the aspirant's psionic mind
        (Phase 4), free subjugated siblings in a revolt surge (Phase 5), and at the
        window's end molt the heir into a maw — or, if the heir fell, extinguish the
        house. Inert while dynamic_population is off (never called)."""
        for colony in self.colonies:
            if getattr(colony, 'pop_state', POP_ACTIVE) != POP_SUCCESSION:
                continue
            aspirant = next((u for u in colony.units
                             if getattr(u, 'is_aspirant', False)), None)
            if aspirant is None:                   # the heir fell -> the line ends
                self._fail_succession(colony)
                continue
            # Phase 4: the aspirant's mind grows toward the molt (augmentation)
            colony.genome.brain_hidden = int(min(
                64, getattr(colony.genome, 'brain_hidden', 8) * 1.02 + 0.5))
            # Phase 5: a revolt surge frees this house's subjugated siblings, who
            # rally to the aspirant (they never submit — defiance maxes out)
            for u in colony.units:
                if getattr(u, 'laboring_for', -1) >= 0:
                    u.laboring_for = -1
                    u.defiance = 1.0
            if self.step_count >= getattr(colony, 'succession_until', 0):
                self._molt_aspirant(colony, aspirant)

    def _molt_aspirant(self, colony: 'Colony', aspirant: 'SandKing') -> None:
        """The heir's terminal molt (SPEC_METAMORPHOSIS): it BECOMES a maw with an
        augmented neural net + boosted stats, the SAME house reclaimed (Restored)."""
        pos = aspirant.position
        if aspirant in colony.units:
            colony.units.remove(aspirant)          # the aspirant becomes the maw
        colony.genome.loyalty = min(1.0, getattr(colony.genome, 'loyalty', 0.7) * SPARTAN_BOOST)
        colony.genome.brain_hidden = int(getattr(colony.genome, 'brain_hidden', 8) * SPARTAN_BOOST)
        colony.genome.use_neural = True            # the augmented neural net
        colony.memory_augment = max(getattr(colony, 'memory_augment', 0), 1)
        colony.maw = Maw(colony.colony_id, pos, colony.genome)
        colony.maw.alive = True
        colony.maw.food_stored = RESPAWN_FOOD
        colony.stage = max(getattr(colony, 'stage', 1), 2)   # a terminal molt
        colony.generation = getattr(colony, 'generation', 1) + 1
        colony.pop_state = POP_ACTIVE
        colony.reclaimed = True
        self.world.set_voxel(*pos, VoxelType.AIR, colony_id=colony.colony_id)
        self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1
        self._log_event(f"House {self._house_name(colony)} RESTORED — the Spartan aspirant"
                        f" molts into a maw and reclaims the line"
                        f" (generation {colony.generation})")

    def _fail_succession(self, colony: 'Colony') -> None:
        """The heir fell during the window: the house is extinguished in disgrace,
        the slot returns to the normal respawn spine (a fresh house arrives)."""
        self._log_event(f"House {self._house_name(colony)} is extinguished — its last heir"
                        f" fell, the line ends in disgrace")
        for u in colony.units:
            self.world.set_voxel(*u.position, VoxelType.CORPSE)
        colony.units.clear()
        colony.pop_state = POP_ACTIVE              # slot rejoins the respawn spine
        self.pheromones.trails[:, :, :, colony.colony_id, :] = 0.0
        self.world.ownership[self.world.ownership == colony.colony_id] = -1
        self._diplomacy().clear_slot(colony.colony_id, self.step_count)
        self.pending_respawns[colony.colony_id] = self.step_count + RESPAWN_DELAY

    def _deactivate_slot(self, cid: int) -> None:
        """Slot-scrub choke point: clear all per-colony state for a given slot.

        This is the unified clearance used by later phases for DORMANT/founding
        transitions. Phase 0 defines it but does NOT wire it (legacy respawn
        keeps the folk-memory shadow). See SPEC_POPULATION §3.1-§3.2.
        """
        # Require
        colony = self._colony_by_id(cid)
        assert colony is not None, f"_deactivate_slot: unknown colony id {cid}"

        # (1) pheromone channel
        self.pheromones.trails[:, :, :, cid, :] = 0.0
        # (2) ownership voxels
        self.world.ownership[self.world.ownership == cid] = -1

        # (3–6) politics: total slot clear (BOTH directions — no folk-memory shadow)
        d = getattr(self, 'diplomacy', None) or self._diplomacy()
        for (a, b) in list(d.relations.keys()):          # 3 + 3b: both directions
            if a == cid or b == cid:
                del d.relations[(a, b)]
        for key in [k for k in d.truce_until   if cid in k]: del d.truce_until[key]
        for key in [k for k in d.allied        if cid in k]: del d.allied[key]
        for key in [k for k in d.rejected_at   if cid in k]: del d.rejected_at[key]
        d.war_target.pop(cid, None)                       # 5
        for other_id, target in list(d.war_target.items()):
            if target == cid:
                d.war_target[other_id] = None
        d.last_betrayal.pop(cid, None)                    # 6
        if d.hegemon == cid:
            d.hegemon = None

        # (7,8) cross-colony unit references: thralls held by cid, gifts bound for cid
        for other in self.colonies:
            if other.colony_id == cid:
                continue
            for unit in other.units:
                if getattr(unit, 'laboring_for', -1) == cid:
                    unit.laboring_for = -1
                    unit.defiance = 0.0
                if getattr(unit, 'gift_to', -1) == cid:
                    unit.gift_to = -1

        # (9,10,11) sim-level per-colony dicts
        if hasattr(self, 'monitors'):        self.monitors.pop(cid, None)
        if hasattr(self, 'learners'):        self.learners.pop(cid, None)
        if hasattr(self, 'pending_respawns'): self.pending_respawns.pop(cid, None)

        # (12) this slot's own units vanish
        colony.units.clear()

        # (13) disposition -> neutral
        colony.favoritism = 0.0
        colony.agitation = 0.0
        colony.confidence = 0.5

        # state + kin cache
        colony.pop_state = POP_DORMANT
        self._kin_epoch = getattr(self, '_kin_epoch', 0) + 1   # 14

        # Assert (Guarantee)
        assert not (self.world.ownership == cid).any()
        assert not self.pheromones.trails[:, :, :, cid, :].any()

    def _unit_label(self, unit: SandKing) -> str:
        """Display identity for decision logs and rosters."""
        return f"{unit.unit_type.name.title()} #{getattr(unit, 'unit_id', 0)}"

    def _colony_encodings(self, colony: Colony) -> dict:
        """Batch the maw's SHARED encoder across all a colony's neural soldiers in
        ONE forward per step (encoding per-soldier was the perf sink — the maw is a
        shared encoder, so its Kanerva/ZCA cost should be paid once and split B
        ways). Memoized by step; returns {id(unit): encoding}. Row-independent, so
        the batched encoding equals the per-soldier one."""
        cache = getattr(self, '_enc_cache', None)
        if cache is None or cache[0] != self.step_count:
            cache = (self.step_count, {})
            self._enc_cache = cache
        _step, per_colony = cache
        if colony.colony_id in per_colony:
            return per_colony[colony.colony_id]
        from politics import hostile as _hostile
        enemy_positions = []
        for ec in self.colonies:
            if _hostile(self, colony.colony_id, ec.colony_id):
                enemy_positions.extend([e.position for e in ec.units])
        soldiers = [u for u in colony.units
                    if u.unit_type == UnitType.SOLDIER and u.brain_layer is not None]
        enc_map = {}
        if soldiers:
            states = torch.stack([
                encode_soldier_state(u, colony, self.world, enemy_positions)
                for u in soldiers])                          # (B, input_dim)
            with torch.no_grad():
                encs = colony.genome.brain(states)           # (B, encoding) — ONE call
            for u, e in zip(soldiers, encs):
                enc_map[id(u)] = e
        per_colony[colony.colony_id] = enc_map
        return enc_map

    def _execute_unit_ai(self, unit: SandKing, colony: Colony):
        """Simple AI for unit behavior - NEURAL or RULE-BASED"""
        x, y, z = unit.position

        # DP4: a startled (agitated) colony's mobiles disperse / hesitate.
        # Guarded so agitation==0 draws NO RNG (byte-identical at neutral).
        ag = getattr(colony, 'agitation', 0.0)
        if ag > 0.0 and random.random() < AGIT_FREEZE * ag:
            return   # this unit mills this step (slower); resumes next step

        # HIVE MONITOR (SPEC_HIVE_MONITOR M7): non-neural units cache
        # instincts on a 3-step stagger; neural soldiers are observed with
        # their hidden state inside the neural path below
        neural_soldier = (unit.unit_type == UnitType.SOLDIER and NEURAL_AVAILABLE
                          and colony.genome.use_neural
                          and colony.genome.brain is not None
                          and unit.brain_layer is not None)
        if not neural_soldier and (self.step_count + getattr(unit, 'unit_id', 0)) % 3 == 0:
            self._monitor(colony.colony_id).observe_instincts(unit, colony, self)
        
        # Workers: worker AI v2 (SPEC T18) - grab > haul > mine-continue >
        # forage > farm > mine-seek > dig. Wild food ALWAYS outranks farming
        if unit.unit_type == UnitType.WORKER:
            if getattr(unit, 'gift_to', -1) >= 0:
                return  # envoys are single-minded; they move in 5b (P3)
            # (0) Designated builders: a deterministic 1/N of a house's workers
            # (by unit_id) raise its castle/palisade BEFORE economy when a build
            # agenda holds, so a ring completes instead of being perpetually
            # starved. No-op (no RNG) when there is nothing to build.
            if (getattr(unit, 'build_slot', -1) % BUILD_LABOR_EVERY == 0
                    and self._try_build(unit, colony)):
                return

            # (1) Radius-2 grab: wild food +15, ripe crops +40 -> TILLED
            neighbors = self.world.get_neighbors_3d(unit.position, radius=2)
            acted = False
            for nx, ny, nz in neighbors:
                voxel = self.world.get_voxel(nx, ny, nz)
                if voxel in (VoxelType.FOOD, VoxelType.CORPSE):
                    unit.move((nx, ny, nz))
                    self.world.set_voxel(nx, ny, nz, VoxelType.AIR)
                    self._credit_labor(unit, colony, 'food', HARVEST_YIELD)
                    if voxel == VoxelType.CORPSE:  # T42: bones from the fallen
                        colony.bone = getattr(colony, 'bone', 0) + 1
                    elif (nx, ny, nz) in getattr(self, 'keeper_manna', ()):
                        # K3/AW3: bounty is good fortune to all, but only the
                        # AWARE (breached) read it as worship of a hand
                        self.keeper_manna.discard((nx, ny, nz))
                        colony.keeper_fed_step = self.step_count
                        if (getattr(colony, 'breached', False)
                                and not getattr(colony, 'worshipped', False)):
                            colony.worshipped = True
                            self._log_event(
                                f"House {self._house_name(colony)} begins"
                                " to worship the hand that feeds")
                    unit.forage_target = None
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10
                    acted = True
                    break
                if voxel == VoxelType.CROP_RIPE:
                    owner = int(self.world.ownership[nx, ny, nz])
                    d = self._diplomacy()
                    foreign = owner >= 0 and owner != colony.colony_id
                    if (foreign and not d.ally(colony.colony_id, owner)
                            and d.truce_active(colony.colony_id, owner,
                                               self.step_count)):
                        continue  # truced crops are sacrosanct (P10)
                    tenders = getattr(self, 'crop_tenders', {}).pop(
                        (nx, ny, nz), set())
                    from politics import COOP_YIELD_BONUS
                    payout = CROP_YIELD * (1 + COOP_YIELD_BONUS
                                           if len(tenders) >= 2 else 1)
                    payout *= 1 + FARM_YIELD_BONUS * self._prof(  # TE10
                        colony, 'farming')
                    if foreign and d.ally(colony.colony_id, owner):
                        self._credit_labor(unit, colony, 'crop', payout * 0.6)   # harvester's co-op share, thrall-redirectable
                        owner_colony = self._colony_by_id(owner)
                        if owner_colony is not None and owner_colony.is_alive():
                            owner_colony.maw.eat(payout * 0.4)                   # owner's cut — UNCHANGED, not labor the harvester produced
                    else:
                        self._credit_labor(unit, colony, 'crop', payout)
                    self._practice(colony, 'farming')  # TE7
                    self.world.voxels[nx, ny, nz] = VoxelType.TILLED.value
                    unit.forage_target = None
                    self._milestone(colony, 'harvested',
                                    f"Colony {colony.colony_id} reaps its first harvest",
                                    unit)
                    if unit.brain_layer is not None:
                        unit.brain_layer.food_gathered += 10
                    acted = True
                    break

            # (2) Haul carried ore home
            if not acted:
                acted = self._haul_step(unit, colony)

            # (3) Continue an adjacent valid mine
            if not acted:
                acted = self._mine_step(unit, colony)

            # (4) Forage: cached target -> scan -> scout intel -> step toward
            if not acted:
                target = unit.forage_target
                if target is not None and self.world.get_voxel(*target) not in (
                        VoxelType.FOOD, VoxelType.CORPSE, VoxelType.CROP_RIPE):
                    target = unit.forage_target = None  # stale: someone ate it
                if target is None:
                    target = self._find_food_target(unit.position,
                                                    colony.genome.foraging_range,
                                                    prefer=self._forage_mode(colony))
                    if target is None:
                        target = self._pull_known_food(colony, unit.position)
                    unit.forage_target = target
                if target is not None:
                    acted = self._step_toward(unit, target, colony)

            # (5) Farm: gated by the colony flag, sow window, and plot cap
            if not acted and getattr(colony, 'farming', False) and (
                    self._sow_window_open() or self.in_oasis(x, y)):
                acted = self._farm_step(unit, colony)

            # (5b) Machine work (T37): repair > build > excavate to the wreck
            if not acted:
                acted = self._machine_work(unit, colony)

            # (5c) Tend an allied crop (P10): +1 progress per visit-step
            if not acted:
                d = self._diplomacy()
                for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                    if self.world.voxels[nx, ny, nz] != VoxelType.CROP.value:
                        continue
                    owner = int(self.world.ownership[nx, ny, nz])
                    if owner < 0 or owner == colony.colony_id:
                        continue
                    if not d.ally(colony.colony_id, owner):
                        continue
                    pos = (nx, ny, nz)
                    if pos in self._crops():
                        self.crops[pos] += 1
                        if not hasattr(self, 'crop_tenders'):
                            self.crop_tenders = {}
                        self.crop_tenders.setdefault(pos, set()).add(colony.colony_id)
                        self.crop_tenders[pos].add(owner)
                        acted = True
                        break

            # (6) Seek exposed ore
            if not acted:
                acted = self._mine_seek(unit, colony)

            # (6b) Timber (T41): chop when the woodpile runs short
            if not acted and getattr(colony, 'wood', 0) < 4:
                acted = self._chop_step(unit, colony)

            # (6c) Palisades (T43): fortifiers wall the maw with timber. Threatened
            # houses (an enemy in range, or at war) wall up even without a fortify
            # lean; the default defense_investment (0.5) now qualifies (was a dead
            # gate at strict > 0.5).
            if not acted and getattr(colony, 'wood', 0) >= 1 and (
                    self._posture(colony) == "FORTIFY"
                    or getattr(colony.genome, 'defense_investment', 0.0) >= 0.5
                    or getattr(colony, 'at_war', False)):
                acted = self._palisade_step(unit, colony)

            # (6d) Castles (K5): a house makes its standing visible in stone when
            # the keeper favors it (reverent) OR when it is durably prosperous.
            if (not acted and colony.maw.food_stored > WAR_CHEST
                    and (self.keeper_attitude(colony) == 'reverent'
                         or self._is_prosperous(colony))):
                acted = self._castle_step(unit, colony)

            # (7) No work known: DIG a real warren. The RNG draws are IDENTICAL to
            # the original (one random.random, one random.choice over the SAME six
            # directions) so the global stream — and every trajectory-pinned test —
            # is undisturbed. The depth-bias is a purely DETERMINISTIC post-draw
            # flip: a colony still above its preferred depth turns an 'up' or lateral
            # roll downward, so a subterranean network forms instead of a surface scratch.
            if not acted and random.random() < colony.genome.tunnel_preference:
                direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                surf = self.world.surface_z(x, y)
                target_depth = int(surf - 1 - colony.genome.tunnel_preference * (surf - 1))
                if z > target_depth and direction[2] >= 0:   # deterministic: dig down
                    direction = (direction[0], direction[1], -1) if (direction[0] or direction[1]) else (0, 0, -1)
                if self.world.tunnel(unit.position, direction, colony.colony_id):
                    unit.move((x + direction[0], y + direction[1], z + direction[2]))
                    # Leave territory pheromone
                    self.pheromones.deposit(unit.position, colony.colony_id,
                                          PheromoneType.TERRITORY, 1.0)
        
        # Scouts: fast surface surveyors and sentinels (SPEC T11; P9-gated:
        # allied units passing through are not alarms - safe passage)
        elif unit.unit_type == UnitType.SCOUT:
            from politics import hostile as _hostile
            nearest_enemy, enemy_dist = None, float('inf')
            for enemy_colony in self.colonies:
                if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                    continue
                for enemy in enemy_colony.units:
                    dist = (abs(enemy.position[0] - x) + abs(enemy.position[1] - y)
                            + abs(enemy.position[2] - z))
                    if dist < enemy_dist:
                        enemy_dist, nearest_enemy = dist, enemy

            if nearest_enemy is not None and enemy_dist <= SCOUT_ALARM_RANGE:
                # Alarm: mark danger (feeds the DANGER overlay) and flee
                self.pheromones.deposit(unit.position, colony.colony_id,
                                        PheromoneType.DANGER, 2.0)
                for _ in range(2):
                    ux, uy, uz = unit.position
                    dx = -np.sign(nearest_enemy.position[0] - ux) or random.choice([-1, 1])
                    dy = -np.sign(nearest_enemy.position[1] - uy) or random.choice([-1, 1])
                    flee_pos = (int(ux + dx), int(uy + dy), uz)
                    if (self.world.in_bounds(*flee_pos) and
                            self.world.get_voxel(*flee_pos) == VoxelType.AIR):
                        unit.move(flee_pos)
            else:
                # Survey: long-range food intel for the colony
                found = self._find_food_target(unit.position,
                                               colony.genome.foraging_range * 2)
                if found is not None and found not in colony.known_food:
                    colony.known_food.append(found)
                    del colony.known_food[:-KNOWN_FOOD_CAP]
                # Fast wander through open air (scouts do not tunnel)
                for _ in range(2):
                    ux, uy, uz = unit.position
                    direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                    new_pos = (ux + direction[0], uy + direction[1], uz + direction[2])
                    if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos) == VoxelType.AIR):
                        unit.move(new_pos)

        # Soldiers: NEURAL AI or RULE-BASED
        elif unit.unit_type == UnitType.SOLDIER:
            # NEURAL AI PATH
            if (NEURAL_AVAILABLE and 
                colony.genome.use_neural and 
                colony.genome.brain is not None and 
                unit.brain_layer is not None):
                
                # AUG3: sync the soldier's KV-cache length to the colony's
                # earned augment level (idempotent; covers every spawn path)
                unit.brain_layer.cache_len = (getattr(colony, 'memory_augment', 0)
                                              * AUG_CACHE_STEP)

                # SHARED maw encoder, batched once per colony/step (perf: the maw's
                # Kanerva/ZCA cost is paid once and split across the soldiers, not
                # rerun per soldier). Fall back to a single encode for an edge case
                # (a soldier not in this step's batch).
                encoding = self._colony_encodings(colony).get(id(unit))
                if encoding is None:
                    from politics import hostile as _hostile
                    ep = []
                    for ec in self.colonies:
                        if _hostile(self, colony.colony_id, ec.colony_id):
                            ep.extend([e.position for e in ec.units])
                    with torch.no_grad():
                        encoding = colony.genome.brain(
                            encode_soldier_state(unit, colony, self.world, ep))
                with torch.no_grad():
                    action_probs = unit.brain_layer(encoding)

                # Phase 2a/2b: maw directive (85%) tilts the action, then the spawn's own
                # bounded RL residual (15%) plays on top. Gated => byte-identical when off.
                if MAW_RL_ENABLED:
                    from maw_brain import apply_directive, apply_residual, ColonySpawnRL
                    _dir = getattr(colony, 'maw_directive', None)
                    if _dir is not None:
                        action_probs = apply_directive(action_probs, _dir)
                    srl = getattr(colony, 'spawn_rl', None)
                    if srl is None:
                        srl = ColonySpawnRL(enc_dim=int(encoding.reshape(-1).shape[0]))
                        colony.spawn_rl = srl
                    residual = srl.act(unit, encoding,
                                       unit.brain_layer.get_performance_score())
                    action_probs = apply_residual(action_probs, residual)

                # HIVE MONITOR: decode this soldier's mind (SPEC_HIVE_MONITOR M2/M3)
                if unit.brain_layer.hidden is not None:
                    hidden_vec = unit.brain_layer.hidden.squeeze(0).numpy()
                    self._monitor(colony.colony_id).observe_neural(
                        unit, colony, self, hidden_vec)

                # Decode action
                action_type, direction = decode_soldier_action(action_probs)
                
                # Execute action
                if action_type == 'move' and direction is not None:
                    new_pos = (x + direction[0], y + direction[1], z + direction[2])
                    if (self.world.in_bounds(*new_pos) and 
                        self.world.get_voxel(*new_pos).is_tunnelable()):
                        unit.move(new_pos)
                # Attack is handled by _resolve_conflicts
                
                # Update performance tracking
                unit.brain_layer.steps_alive += 1
                
            # RULE-BASED AI PATH (fallback)
            else:
                from politics import hostile as _hostile
                # T44b/T45: rams smash enemy walls; torches fire the fields
                if colony.at_war:
                    ram_live = getattr(colony, 'ram_until', 0) > self.step_count
                    for nx, ny, nz in self.world.get_neighbors_3d(
                            unit.position, radius=1):
                        v = self.world.voxels[nx, ny, nz]
                        owner = int(self.world.ownership[nx, ny, nz])
                        foe = (owner >= 0 and owner != colony.colony_id
                               and _hostile(self, colony.colony_id, owner))
                        if not foe:
                            continue
                        if ram_live and v in (VoxelType.WOOD_WALL.value,
                                              VoxelType.TUNNEL_WALL.value,
                                              VoxelType.CASTLE.value):
                            self.world.voxels[nx, ny, nz] = VoxelType.SAND.value
                            self._rot().pop((nx, ny, nz), None)
                            key = ('ram', colony.colony_id, owner)
                            if self.step_count - getattr(
                                    self, '_smash_logged', {}).get(
                                        key, -10**9) > SEASON_LENGTH:
                                if not hasattr(self, '_smash_logged'):
                                    self._smash_logged = {}
                                self._smash_logged[key] = self.step_count
                                self._log_event(
                                    f"Colony {colony.colony_id}'s ram smashes"
                                    f" Colony {owner}'s walls!")
                            return
                        if getattr(unit, 'torch', False) and v in (
                                VoxelType.CROP.value, VoxelType.CROP_RIPE.value,
                                VoxelType.WOOD_WALL.value):
                            self._ignite((nx, ny, nz))
                            unit.torch = False  # a torch is thrown but once
                            self._log_event(
                                f"Colony {colony.colony_id} puts Colony"
                                f" {owner}'s holdings to the torch!")
                            self._monitor(colony.colony_id).log_decision(
                                self.step_count, self._unit_label(unit),
                                "threw a torch", getattr(unit, 'thought', None))
                            return
                # T21: raze an adjacent enemy field (consumes the action)
                if colony.at_war or random.random() < self._aggression_eff(colony) * 0.1:
                    for nx, ny, nz in self.world.get_neighbors_3d(unit.position, radius=1):
                        v = self.world.voxels[nx, ny, nz]
                        owner = int(self.world.ownership[nx, ny, nz])
                        if (v in (VoxelType.TILLED.value, VoxelType.CROP.value)
                                and owner >= 0 and owner != colony.colony_id
                                and _hostile(self, colony.colony_id, owner)):
                            self.world.voxels[nx, ny, nz] = VoxelType.SAND.value
                            self._crops().pop((nx, ny, nz), None)
                            self._diplomacy().rel(owner, colony.colony_id).adjust(-6.0)
                            if not hasattr(self, '_raze_logged'):
                                self._raze_logged = {}
                            key = (colony.colony_id, owner)
                            if self.step_count - self._raze_logged.get(key, -10**9) > SEASON_LENGTH:
                                self._raze_logged[key] = self.step_count
                                self._log_event(f"Colony {colony.colony_id} razes"
                                                f" Colony {owner}'s fields!")
                                self._monitor(colony.colony_id).log_decision(
                                    self.step_count, self._unit_label(unit),
                                    "razed an enemy field",
                                    getattr(unit, 'thought', None))
                            return

                # Find closest enemy unit (hostile colonies only, P9)
                closest_enemy = None
                min_dist = float('inf')

                for enemy_colony in self.colonies:
                    if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                        continue
                    for enemy in enemy_colony.units:
                        dist = abs(enemy.position[0] - x) + abs(enemy.position[1] - y) + abs(enemy.position[2] - z)
                        if dist < min_dist:
                            min_dist = dist
                            closest_enemy = enemy
                
                # MORALE CHECK: Retreat if wounded (<10% HP)
                if unit.retreating and closest_enemy:
                    # Flee away from enemy
                    dx = -np.sign(closest_enemy.position[0] - x) if closest_enemy.position[0] != x else random.choice([-1, 1])
                    dy = -np.sign(closest_enemy.position[1] - y) if closest_enemy.position[1] != y else random.choice([-1, 1])
                    dz = 0  # Stay at same depth when fleeing
                    new_pos = (int(x + dx), int(y + dy), int(z + dz))
                    if (self.world.in_bounds(*new_pos) and 
                        self.world.get_voxel(*new_pos).is_tunnelable()):
                        unit.move(new_pos)
                # If healthy and enemy within range, ATTACK
                elif closest_enemy and min_dist < colony.genome.foraging_range:
                    if random.random() < self._aggression_eff(colony):
                        # Move toward enemy
                        dx = np.sign(closest_enemy.position[0] - x)
                        dy = np.sign(closest_enemy.position[1] - y)
                        dz = np.sign(closest_enemy.position[2] - z)
                        new_pos = (int(x + dx), int(y + dy), int(z + dz))
                        if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos).is_tunnelable()):
                            unit.move(new_pos)
                else:
                    # No enemy unit in range: SIEGE the nearest enemy Maw
                    # (T4, P5-scoped: cross-map raids only at the war target)
                    war_target = self._diplomacy().war_target.get(colony.colony_id)
                    closest_maw, maw_dist = None, float('inf')
                    for enemy_colony in self.colonies:
                        if not enemy_colony.is_alive():
                            continue
                        if not _hostile(self, colony.colony_id, enemy_colony.colony_id):
                            continue
                        m = enemy_colony.maw.position
                        dist = abs(m[0] - x) + abs(m[1] - y) + abs(m[2] - z)
                        # engageable = in local range, OR the war target
                        # (cross-map raids go to the TARGET only, P5)
                        if not (dist < colony.genome.foraging_range
                                or (colony.at_war
                                    and enemy_colony.colony_id == war_target)):
                            continue
                        if dist < maw_dist:
                            maw_dist, closest_maw = dist, enemy_colony.maw

                    if closest_maw is not None and random.random() < self._aggression_eff(colony):
                        if not self._step_toward(unit, closest_maw.position, colony):
                            pass  # boxed in this step; siege pressure resumes next step
                    # FORTIFY posture: guard the maw and fields (T26)
                    elif (self._posture(colony) == "FORTIFY"
                          and (abs(colony.maw.position[0] - x)
                               + abs(colony.maw.position[1] - y)
                               + abs(colony.maw.position[2] - z)) > FARM_RADIUS + 2):
                        self._step_toward(unit, colony.maw.position, colony)
                    # Random patrol if nothing in range
                    elif random.random() < 0.3:
                        direction = random.choice([(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)])
                        new_pos = (x + direction[0], y + direction[1], z + direction[2])
                        if (self.world.in_bounds(*new_pos) and
                            self.world.get_voxel(*new_pos).is_tunnelable()):
                            unit.move(new_pos)

    
    def _resolve_conflicts(self):
        """Resolve combat with area-of-effect (radius 1) + NEURAL MATING"""
        units_to_remove = {}  # Track units to remove after combat
        mating_pairs = []  # Track soldier encounters for mating
        
        from politics import hostile
        for colony in self.colonies:
            for unit in colony.units:
                if getattr(unit, 'gift_to', -1) >= 0:
                    continue  # envoys never initiate combat (P3)
                # Check radius 1 for enemies (AoE COMBAT)
                neighbors = self.world.get_neighbors_3d(unit.position, radius=1)

                for nx, ny, nz in neighbors:
                    # Find enemy units at this position
                    for enemy_colony in self.colonies:
                        if not hostile(self, colony.colony_id,
                                       enemy_colony.colony_id):
                            continue  # truce/ally/co-belligerent (P9)

                        for enemy in enemy_colony.units:
                            if (getattr(enemy, 'gift_to', -1) == colony.colony_id):
                                continue  # inbound envoys are sacrosanct (P3)
                            if enemy.position == (nx, ny, nz):
                                # SJ7b: THRALL HOSTILITY - captor does not kill its own labor
                                if (getattr(enemy, 'laboring_for', -1) == colony.colony_id
                                        or getattr(unit, 'laboring_for', -1) == enemy_colony.colony_id):
                                    continue
                                # NEURAL MATING: Soldiers exchange genetic material during combat!
                                if (NEURAL_AVAILABLE and
                                    unit.unit_type == UnitType.SOLDIER and
                                    enemy.unit_type == UnitType.SOLDIER and
                                    unit.brain_layer is not None and
                                    enemy.brain_layer is not None and
                                    np.random.random() < 0.05):  # 5% chance during combat
                                    # S2: speciated lineages bear no young
                                    if self._conspecific(colony, enemy_colony):
                                        mating_pairs.append((unit, enemy, colony, enemy_colony))
                                    else:
                                        self._log_speciation(colony, enemy_colony)
                                
                                # COMBAT! Apply damage with resilience
                                # (attackers credit damage_dealt for fitness)
                                if enemy.brain_layer is not None:
                                    enemy.brain_layer.damage_dealt += enemy.attack
                                if unit.brain_layer is not None:
                                    unit.brain_layer.damage_dealt += unit.attack
                                if unit.take_damage(enemy.attack, colony.genome.resilience):
                                    # SJ1: Try to capture instead of kill
                                    if not self._try_capture(enemy_colony, enemy, unit, colony):
                                        if colony.colony_id not in units_to_remove:
                                            units_to_remove[colony.colony_id] = []
                                        units_to_remove[colony.colony_id].append(unit)

                                        # Track kill for neural performance
                                        if enemy.brain_layer is not None:
                                            enemy.brain_layer.kills += 1
                                        # grievance: victim colony -> killer (P1)
                                        self._diplomacy().rel(
                                            colony.colony_id,
                                            enemy_colony.colony_id).adjust(-4.0)
                                        # HIVE MONITOR: outcomes carry thoughts (M4)
                                        self._monitor(enemy_colony.colony_id).log_decision(
                                            self.step_count, self._unit_label(enemy),
                                            "slew an enemy", getattr(enemy, 'thought', None))
                                        self._monitor(colony.colony_id).log_decision(
                                            self.step_count, self._unit_label(unit),
                                            "fell in battle", getattr(unit, 'thought', None))

                                if enemy.take_damage(unit.attack, enemy_colony.genome.resilience):
                                    # SJ1: Try to capture instead of kill
                                    if not self._try_capture(colony, unit, enemy, enemy_colony):
                                        if enemy_colony.colony_id not in units_to_remove:
                                            units_to_remove[enemy_colony.colony_id] = []
                                        units_to_remove[enemy_colony.colony_id].append(enemy)

                                        # Track kill for neural performance
                                        if unit.brain_layer is not None:
                                            unit.brain_layer.kills += 1
                                        # grievance: victim colony -> killer (P1)
                                        self._diplomacy().rel(
                                            enemy_colony.colony_id,
                                            colony.colony_id).adjust(-4.0)
                                        # HIVE MONITOR: outcomes carry thoughts (M4)
                                        self._monitor(colony.colony_id).log_decision(
                                            self.step_count, self._unit_label(unit),
                                            "slew an enemy", getattr(unit, 'thought', None))
                                        self._monitor(enemy_colony.colony_id).log_decision(
                                            self.step_count, self._unit_label(enemy),
                                            "fell in battle", getattr(enemy, 'thought', None))
        
        # MAW SIEGE: units adjacent to an enemy Maw damage it (SPEC T4)
        self._apply_maw_siege_damage()

        # NEURAL MATING: Create offspring layers
        for unit1, unit2, colony1, colony2 in mating_pairs:
            if unit1.brain_layer and unit2.brain_layer:
                # Mate soldier layers
                offspring_layer = unit1.brain_layer.mate(unit2.brain_layer)
                
                # Spawn new soldier with hybrid brain in stronger colony
                stronger_colony = colony1 if len(colony1.units) >= len(colony2.units) else colony2
                if stronger_colony.maw.food_stored > 10:
                    new_soldier = stronger_colony.maw.spawn_unit(UnitType.SOLDIER)
                    if new_soldier:
                        new_soldier.brain_layer = offspring_layer
                        stronger_colony.units.append(new_soldier)
        
        # Remove dead units and create corpses
        for colony_id, dead_units in units_to_remove.items():
            colony = next((c for c in self.colonies if c.colony_id == colony_id), None)
            if colony:
                for unit in dead_units:
                    if unit in colony.units:  # Check still in list
                        # NEURAL FOLDING: Incorporate top performers into Maw brain
                        if (NEURAL_AVAILABLE and 
                            colony.genome.use_neural and 
                            colony.genome.brain is not None and
                            unit.brain_layer is not None and
                            unit.unit_type == UnitType.SOLDIER):
                            perf_score = unit.brain_layer.get_performance_score()
                            colony.genome.brain.fold_soldier_layer(unit.brain_layer, perf_score)
                        
                        colony.remove_unit(unit)
                        self.world.set_voxel(*unit.position, VoxelType.CORPSE)

    
    def get_status(self) -> str:
        """Get simulation status string"""
        alive_colonies = [c for c in self.colonies if c.is_alive()]
        status = f"Step {self.step_count} | Colonies: {len(alive_colonies)}/{len(self.colonies)}\n"
        
        for colony in self.colonies:
            if colony.is_alive():
                status += f"  Colony {colony.colony_id}: {len(colony.units)} units, "
                status += f"{colony.maw.food_stored:.0f} food, {colony.maw.health:.0f} health\n"
        
        return status

# ============================================================================
# PERSISTENCE - the terrarium lives between sessions (SPEC T13)
# ============================================================================

# Bump when a sim-state change makes old checkpoints unloadable. A
# mismatch makes load_checkpoint() report "incompatible" and start fresh
# rather than crash (the user's "load last state unless incompatible").
CHECKPOINT_VERSION = "2.16"
CHECKPOINT_KEEP = 3   # retain only the newest N checkpoint rows (bounds db growth)


def save_checkpoint(sim: 'SandKingsSimulation', path: str) -> int:
    """Pickle the whole simulation into a sqlite checkpoint row.

    Returns the new checkpoint id. Failure mode: raises on unpicklable
    state or unwritable path (callers treat persistence as best-effort).
    The row carries CHECKPOINT_VERSION so an incompatible resume is
    detected and handled gracefully rather than crashing.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "step INTEGER NOT NULL, saved_at TEXT NOT NULL, "
            "version TEXT NOT NULL DEFAULT '', state BLOB NOT NULL)")
        # add the version column to a pre-2.16 db, best-effort
        cols = {r[1] for r in conn.execute("PRAGMA table_info(checkpoints)")}
        if "version" not in cols:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN "
                         "version TEXT NOT NULL DEFAULT ''")
        blob = pickle.dumps(sim, protocol=pickle.HIGHEST_PROTOCOL)
        cursor = conn.execute(
            "INSERT INTO checkpoints (step, saved_at, version, state) "
            "VALUES (?, datetime('now'), ?, ?)",
            (sim.step_count, CHECKPOINT_VERSION, sqlite3.Binary(blob)))
        # Bound the history: load_checkpoint only ever reads the newest row, so
        # every prior snapshot is dead weight. Without this prune each autosave
        # appended a full sim pickle and the db grew without limit (a 268k-step
        # run reached ~3.9 GB), eventually filling the volume and failing the
        # very write meant to preserve state. Keep the last few for rollback.
        conn.execute(
            "DELETE FROM checkpoints WHERE id NOT IN "
            "(SELECT id FROM checkpoints ORDER BY id DESC LIMIT ?)",
            (CHECKPOINT_KEEP,))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


class _CheckpointUnpickler(pickle.Unpickler):
    """Resolve classes across the script/module identity split.

    A sim pickled by `python sandkings.py` stores classes under
    '__main__'; one pickled from `import sandkings` stores 'sandkings'.
    Checkpoints must load from either context.
    """

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            alt = 'sandkings' if module == '__main__' else '__main__'
            return super().find_class(alt, name)


def load_checkpoint(path: str) -> Optional['SandKingsSimulation']:
    """Latest checkpointed simulation, or None if absent OR incompatible.

    "Incompatible" - a version mismatch or ANY unpickling failure (a
    renamed/removed class from an older build) - returns None so the
    caller starts fresh instead of crashing (T13; the resume-by-default
    contract). The db is left intact for inspection.
    """
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    try:
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(checkpoints)")}
            select = ("SELECT state, version FROM checkpoints" if "version" in cols
                      else "SELECT state, '' FROM checkpoints")
            row = conn.execute(
                select + " ORDER BY id DESC LIMIT 1").fetchone()
        except sqlite3.OperationalError:  # no table: not a terrarium db yet
            return None
    finally:
        conn.close()
    if row is None:
        return None
    blob, version = row
    if version and version != CHECKPOINT_VERSION:
        print(f"[!] Checkpoint is v{version}, this build is "
              f"v{CHECKPOINT_VERSION} - starting fresh (old state kept).")
        return None
    import io
    try:
        return _CheckpointUnpickler(io.BytesIO(blob)).load()
    except Exception as exc:  # a genuinely incompatible pickle
        print(f"[!] Checkpoint incompatible ({type(exc).__name__}) - "
              "starting fresh (old state kept).")
        return None


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Run Sand Kings simulation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sand Kings 3D Colony Simulation")
    parser.add_argument('--steps', type=int, default=None,
                        help='Simulation steps (GIF mode default 20; live mode default: run until quit)')
    parser.add_argument('--live', action='store_true',
                        help='Open a real-time pygame viewer instead of rendering GIFs')
    parser.add_argument('--sps', type=float, default=5.0,
                        help='Live mode: initial simulation steps per second')
    parser.add_argument('--fresh', action='store_true',
                        help='Ignore any saved state and start a new terrarium')
    parser.add_argument('--persist', nargs='?', const='terrarium.db', default=None,
                        metavar='DB', help='Resume from and autosave to a sqlite '
                        'terrarium (default file: terrarium.db). Live mode: K saves.')
    parser.add_argument('--harsh', action='store_true',
                        help='Skip the 2-year dole ramp: full seasonal scarcity '
                        'from step 0 (T17)')
    parser.add_argument('--num-colonies', type=int, default=0, help='Number of colonies (0=random 3-5)')
    parser.add_argument('--no-dynamic', action='store_true',
                        help='Disable dynamic population + succession (baseline: ON — the '
                             'colony count breathes 2..8, a dead queen triggers a Spartan '
                             'succession drama).')
    parser.add_argument('--canon', action='store_true',
                        help="Seat the novella's four houses: Crimson (creative), "
                             "Pale (favored), Sable (wise), Amber (underdog)")
    parser.add_argument('--width', type=int, default=80, help='World width')
    parser.add_argument('--height', type=int, default=40, help='World height')
    parser.add_argument('--depth', type=int, default=20, help='World depth')
    parser.add_argument('--no-neural', action='store_true',
                        help='Disable neural hive minds (baseline: ON when PyTorch is '
                             'present — colonies think, concept probes learn; ~2-3x slower). '
                             'Falls back to rule-based instincts.')
    # U5: the web chat/keeper console attaches to the SAME sim as the live
    # window (one tank, one step counter). On by default; --no-web for a
    # desktop-only run that imports no fastapi/uvicorn.
    parser.add_argument('--web', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='Live mode: attach the web console (chat + keeper '
                        'actions) on --host:--port. Use --no-web to disable.')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Live mode web console bind host (default 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8010,
                        help='Live mode web console port (default 8010)')
    parser.add_argument('--save-every', type=int, default=600,
                        help='Autosave cadence in steps when --persist is set')
    parser.add_argument('--subjugation', action='store_true',
                        help='Enable the subjugation economy: at-war colonies '
                             'capture broken enemies as thralls (SPEC_SUBJUGATION)')
    parser.add_argument('--wages', action='store_true',
                        help='Enable the wage market: colonies hire labor, license tech, '
                             'and trade goods at negotiated prices (SPEC_WAGES)')
    parser.add_argument('--bargain', action='store_true',
                        help='Enable the full inter-colony bargain: each pair '
                             'chooses annihilate / subjugate / wage by net '
                             'extraction, driving capture and the wage market '
                             '(SPEC_BARGAIN; supersedes --subjugation and --wages)')
    parser.add_argument('--no-hydro', action='store_true',
                        help='Disable water engineering (baseline: ON — the oasis springs, '
                             'water flows and pools, colonies dig rivers/reservoirs/dikes, '
                             'boats cross water).')
    parser.add_argument('--no-maw-rl', action='store_true',
                        help='Disable the 85:15 real-RL brain (baseline: ON — the maw learns a '
                             'colony directive (85%%), the spawn learn a bounded local residual '
                             '(15%%); needs neural).')
    parser.add_argument('--no-guppies', action='store_true',
                        help='Disable the oasis guppy pond (baseline: ON — algae grows, guppies '
                             'breed, and the surplus surfaces as harvestable food; SPEC_GUPPIES).')
    parser.add_argument('--no-crickets', action='store_true',
                        help='Disable the cricket swarm (baseline: ON — the terrestrial food guild; '
                             'breeds on plant matter, booms in Dust, dies in flood/frost; SPEC_FOOD_WEB).')
    parser.add_argument('--no-snares', action='store_true',
                        help='Disable snares (baseline: ON — spider webs and keeper string/toothpick '
                             'weirs by the water passively catch guppies/crickets into food; SPEC_FOOD_WEB).')
    parser.add_argument('--no-learned-basis', action='store_true',
                        help='Use the random Kanerva codebook instead of the learned shared encoder '
                             'basis (baseline: ON — a ZCA+codebook fit to the state manifold, ~28x '
                             'better coverage; needs learned_basis.npz + neural).')
    args = parser.parse_args()
    
    print("="*60)
    print("SAND KINGS SIMULATION")
    print("3D Voxel Terrarium with Cellular Automata")
    if not getattr(args, 'no_neural', False) and NEURAL_AVAILABLE:
        print("[NEURAL] hive minds (baseline) - the hive thinks; probes learn")
    print("="*60)
    
    # Create or resume the simulation (SPEC T13). Persistence is ON by
    # default now: resume the last state unless --fresh, or unless it is
    # missing/incompatible (load_checkpoint returns None in those cases).
    if args.persist is None and not args.fresh:
        args.persist = 'terrarium.db'
    sim = None
    if args.persist and not args.fresh:
        sim = load_checkpoint(args.persist)
        if sim is not None:
            print(f"[>] Resumed terrarium from {args.persist} at step {sim.step_count}")
    fresh = sim is None
    if fresh:
        sim = SandKingsSimulation(width=args.width, height=args.height,
                                 depth=args.depth, num_colonies=args.num_colonies,
                                 canon=getattr(args, 'canon', False),
                                 dynamic_population=not getattr(args, 'no_dynamic', False))
    sim.harsh = args.harsh  # T17 ramp control (applies to resumed sims too)

    # --subjugation: turn the capture economy ON for this run only. The module
    # default CAPTURE_CHANCE stays 0.0 (regression battery byte-identical); here
    # we bump the live global and flag the sim so at-war colonies take thralls.
    if getattr(args, 'subjugation', False):
        globals()['CAPTURE_CHANCE'] = SUBJUGATION_LIVE_CHANCE
        sim.subjugation_enabled = True
        print(f"[CHAIN] SUBJUGATION ENABLED - at-war colonies capture thralls "
              f"(CAPTURE_CHANCE={SUBJUGATION_LIVE_CHANCE})")

    # --wages: turn the wage market ON for this run only. The module default
    # WAGE_ENABLED stays False (regression battery byte-identical); here we bump
    # the live global so colonies negotiate labor, tech licenses, and goods.
    if getattr(args, 'wages', False):
        globals()['WAGE_ENABLED'] = True
        sim.wage_enabled = True
        print(f"[CHAIN] WAGES ENABLED - colonies trade labor, tech, and goods "
              f"at negotiated prices (SPEC_WAGES)")

    # --bargain: turn on the full bargain arc (M4: per-pair mode selection by net
    # extraction). Sets BARGAIN_ENABLED=True, enables WAGE_ENABLED and CAPTURE_CHANCE,
    # so the operator enables one thing rather than three.
    if getattr(args, 'bargain', False):
        globals()['BARGAIN_ENABLED'] = True
        globals()['WAGE_ENABLED']    = True
        globals()['CAPTURE_CHANCE']  = BARGAIN_CAPTURE_CHANCE
        sim.bargain_enabled = True
        print("[CHAIN] BARGAIN ENABLED - each colony pair chooses annihilate/"
              "subjugate/wage by net extraction; wages win when force merely leaks "
              "(SPEC_BARGAIN)")

    # Water engineering is BASELINE (on unless --no-hydro). The module default
    # HYDRO_SOURCES_ENABLED stays False only so the regression battery can isolate a
    # controlled world; the actual game flips it on here.
    if not getattr(args, 'no_hydro', False):
        globals()['HYDRO_SOURCES_ENABLED'] = True
        print("[CHAIN] HYDRO - the oasis springs; water flows, pools, and irrigates; "
              "colonies dig rivers/reservoirs and boats cross the water (SPEC_HYDRO)")

    # Neural hive minds are BASELINE (on unless --no-neural). Fresh colonies and
    # resumed colonies that LACK a brain get one; resumed neural sims keep their
    # evolved brains. The hive thinks — concept probes learn from the hidden state
    # (rule-based leaves every probe at 50%). Only the runnable game turns this on;
    # the genome default use_neural=False keeps the test battery rule-based.
    if not getattr(args, 'no_neural', False) and NEURAL_AVAILABLE:
        # The LEARNED shared encoder basis is BASELINE (on unless --no-learned-basis). Flip it BEFORE
        # seeding brains so fresh brains load the learned ZCA+codebook (module default False keeps the
        # regression battery on the random codebook, byte-identical). GA is untouched (readout evolves).
        import neural_hive as _nh
        if not getattr(args, 'no_learned_basis', False) and _nh._load_learned_basis() is not None:
            _nh.LEARNED_BASIS_ENABLED = True
            print("[REPR] learned shared encoder basis active - ZCA+codebook fit to the state manifold "
                  "(28x better coverage than random; --no-learned-basis to disable)")
        seeded = 0
        for colony in sim.colonies:
            colony.genome.use_neural = True
            if colony.genome.brain is None:
                colony.genome.brain = HiveMindBrain()
                seeded += 1
            for unit in colony.units:
                if (unit.unit_type == UnitType.SOLDIER
                        and getattr(unit, 'brain_layer', None) is None):
                    unit.brain_layer = SoldierLayer()
                    unit.brain_layer.steps_alive = 0
        print(f"[NEURAL] hive minds active ({seeded} fresh brains seeded; "
              "resumed brains kept)")
    elif getattr(args, 'no_neural', False):
        print("[RULE-BASED] minds (--no-neural): instincts, no learned concepts")

    # The 85:15 real-RL brain is BASELINE (on unless --no-maw-rl), and only with neural on —
    # it needs the frozen encoder for its observation. Module default MAW_RL_ENABLED stays
    # False so the regression battery is byte-identical; the game flips it on here.
    if (not getattr(args, 'no_maw_rl', False) and not getattr(args, 'no_neural', False)
            and NEURAL_AVAILABLE):
        globals()['MAW_RL_ENABLED'] = True
        print("[MAW-RL] 85:15 real-RL active - the maw directs (85%), the spawn play (15%); "
              "both learn from survival (--no-maw-rl to disable)")

    # The oasis guppy pond is BASELINE (on unless --no-guppies). Module default GUPPIES_ENABLED
    # stays False so the regression battery is byte-identical; the game flips it on here.
    if not getattr(args, 'no_guppies', False):
        globals()['GUPPIES_ENABLED'] = True
        print("[GUPPIES] the oasis pond lives - algae feeds the shoal, guppies breed, and the "
              "surplus surfaces as food to harvest (--no-guppies to disable)")

    # The terrestrial cricket swarm is BASELINE (on unless --no-crickets). Module default
    # CRICKETS_ENABLED stays False so the regression battery is byte-identical; the game flips it on.
    if not getattr(args, 'no_crickets', False):
        globals()['CRICKETS_ENABLED'] = True
        print("[CRICKETS] the dunes chirp - crickets breed on plant matter, boom in the dry Dust, "
              "and surface as harvestable food (the land guild; --no-crickets to disable)")

    # Snares are BASELINE (on unless --no-snares). Module default SNARES_ENABLED stays False so the
    # regression battery is byte-identical; the game flips it on.
    if not getattr(args, 'no_snares', False):
        globals()['SNARES_ENABLED'] = True
        print("[SNARES] webs and keeper string/toothpick weirs catch guppies and crickets into food "
              "(--no-snares to disable)")

    if args.live:
        # When run as a script this module is '__main__'; alias it so
        # live_view's `from sandkings import ...` binds to these same
        # classes instead of re-importing a duplicate module
        import sys
        sys.modules.setdefault('sandkings', sys.modules[__name__])
        from live_view import run_live
        run_live(sim, max_steps=args.steps, steps_per_second=args.sps,
                 save_path=args.persist, serve=args.web, host=args.host,
                 port=args.port, save_every=args.save_every)
        print("\n" + sim.get_status())
        return

    viz = Visualizer()

    # Run simulation and capture frames
    num_steps = args.steps if args.steps is not None else 20
    frames_2d = []
    frames_3d = []
    
    print(f"\nRunning {num_steps} steps...")
    
    for step in tqdm(range(num_steps)):
        sim.step()
        
        # Capture 2D slice every step
        z_level = sim.world.depth // 2
        frame_2d = viz.render_z_slice(sim.world, sim.colonies, z_level, 
                                      title=f"Step {step+1}")
        frames_2d.append(frame_2d)
        
        # Capture 3D frame every 5 steps (slower to render)
        if step % 5 == 0:
            print(f"\nGenerating 3D frame for step {step+1}...")
            frame_3d = viz.generate_3d_frame(sim.world, sim.colonies)
            frames_3d.append(frame_3d)
    
    # Save GIFs
    print("\nSaving 2D animation...")
    frames_2d[0].save('sandkings_2d.gif', save_all=True, append_images=frames_2d[1:], 
                     duration=200, loop=0)
    
    print("Saving 3D animation...")
    if frames_3d:
        frames_3d[0].save('sandkings_3d.gif', save_all=True, append_images=frames_3d[1:], 
                         duration=500, loop=0)
    
    # Final status
    print("\n" + sim.get_status())
    print("\n[S] Saved sandkings_2d.gif (2D cross-section)")
    print("[S] Saved sandkings_3d.gif (3D clustered view)")

    if args.persist:
        save_checkpoint(sim, args.persist)
        print(f"[S] Terrarium saved to {args.persist}")

    print("\nSimulation complete!")

if __name__ == "__main__":
    main()
