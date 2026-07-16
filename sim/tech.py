"""
Technology & Civilization data (SPEC_TECH).

Pure data for the tech arc: the registry, the acquisition/capability/siege
constants, and the materials→crafting tables. No behaviour lives here — the
sim-bound methods (`_practice`, `_tech_tick`, `_catapult_tick`, `_plunder_techs`,
`_barter_tech`, `keeper_material`, `_caltrop_tick`, …) stay on the simulation in
`sandkings.py`, which re-exports every name below so `from sandkings import
TECH_REGISTRY` (etc.) keeps resolving for the test battery.

Adding a technology is a data edit: append a row to TECH_REGISTRY (and the
matching TECH_FOREIGN/TECH_NATIVE tuple); wire a recipe in CRAFT_RECIPES if a
dropped material should craft into it.
"""

# Technology & Civilization (SPEC_TECH TE2): foreign gifts + native techs.
# Adding a row is the only step to introduce a technology.
TECH_FOREIGN = ('abacus', 'watch', 'calculator', 'pi')
TECH_NATIVE = ('fire', 'farming', 'metallurgy', 'plow', 'masonry',
               'gunpowder', 'catapult',
               'irrigation', 'aqueduct', 'reservoir')  # HYDRO water-engineering tree
TECH_REGISTRY = {
    'abacus':     {'kind': 'foreign', 'desc': 'counting and quantity'},
    'watch':      {'kind': 'foreign', 'desc': 'time and periodicity'},
    'calculator': {'kind': 'foreign', 'desc': 'computation (a bounded machine)'},
    'pi':         {'kind': 'foreign', 'desc': 'the god-brain: terminal and escape'},
    'fire':       {'kind': 'native', 'desc': 'flame and the torch'},
    'farming':    {'kind': 'native', 'desc': 'the tended field'},
    'metallurgy': {'kind': 'native', 'desc': 'ore into weapons and picks'},
    'plow':       {'kind': 'native', 'desc': 'breaking the soil'},
    'masonry':    {'kind': 'native', 'desc': 'raised stone'},
    # T2c upper tree (prereqs are RESEARCHED once both are known - TE11)
    'gunpowder':  {'kind': 'native', 'desc': 'fire and metal: firepower',
                   'prereq': ('metallurgy', 'fire')},
    'catapult':   {'kind': 'native', 'desc': 'the engine that hurls shot',
                   'prereq': ('masonry', 'gunpowder')},
    # HYDRO water-engineering tree (prereqs RESEARCHED once known - TE11; also
    # learned faster by DOING via _practice inside the dig behaviors)
    'irrigation': {'kind': 'native', 'desc': 'ditches and dikes for the field',
                   'prereq': ('farming',)},
    'aqueduct':   {'kind': 'native', 'desc': 'channels that carry water across the land',
                   'prereq': ('irrigation',)},
    'reservoir':  {'kind': 'native', 'desc': 'the held lake - water stored against drought',
                   'prereq': ('aqueduct',)},
}
# T2a acquisition (SPEC_TECH TE7-TE9): practice + observe + grains -> proficiency
TECH_TICK = 20               # cadence of the observe/grains pass
TECH_PRACTICE_XP = 0.02      # proficiency gained per practiced action
TECH_LEARN_XP = 0.3          # xp at which a tech becomes KNOWN
TECH_OBSERVE_RANGE = 8       # Chebyshev maw-distance to learn by watching
TECH_OBSERVE_XP = 0.03       # xp gained per observe tick (× relationship)
TECH_GRAIN_COST = 8.0        # grains spent to buy research (the currency sink)
TECH_GRAIN_XP = 0.15         # xp bought per grain spend

# T2b bonuses (SPEC_TECH TE10): proficiency confers capability. DEFAULT-NEUTRAL
# at proficiency 0 (so every prior test/behaviour is unchanged).
FARM_YIELD_BONUS = 0.5       # farming: +50% harvest at mastery
METAL_WEAPON_BONUS = 0.6     # metallurgy: spear/weapon attack scaling
METAL_PICK_BONUS = 0.5       # metallurgy: mining speed (picks)
PLOW_COST_BONUS = 0.4        # plow: cheaper seed / faster sowing
MASON_WALL_BONUS = 1.0       # masonry: wall durability

# HYDRO water-engineering (flow sim + tech tree). DEFAULT-NEUTRAL: no colony knows
# these at start and the flow field is lazily allocated, so a neutral run never
# touches water. Sources/evaporation are additionally gated by HYDRO_SOURCES_ENABLED
# so the regression battery stays byte-identical until deliberately turned on.
HYDRO_SOURCES_ENABLED = False # master gate for oasis sources + evaporation (Phase 2/8)
HYDRO_TICK = 5               # steps between flow-sim updates (aligned with gravity)
HYDRO_CAP = 1.0             # max water depth a cell holds (float volume units)
HYDRO_FLOW_RATE = 0.25      # fraction of head-difference moved laterally per tick
HYDRO_SETTLE_MIN = 0.10     # min depth to render/mirror a cell as a WATER voxel
HYDRO_SOURCE_LEVEL = 0.9    # depth a source cell (oasis) is topped up to (Phase 2)
HYDRO_EVAP_RATE = 0.01      # fraction evaporated per tick, scaled by dryness (Phase 2)
HYDRO_IRRIG_GROWTH = 2      # extra crop growth-units for a CROP cell next to water (P5)
HYDRO_CHANNEL_LEN = 10      # base channel length; scales with aqueduct proficiency (P4)
HYDRO_RESERVOIR_RADIUS = 2  # base basin radius; scales with reservoir proficiency (P4)
HYDRO_RESERVOIR_DEPTH = 3   # base basin depth in voxels (P4)
HYDRO_RESERVOIR_ABSORB = 0.5  # flood volume a basin can absorb per cell (P6)

# T2c upper tree (SPEC_TECH TE11): gunpowder, the catapult, the shot across the board
TECH_RESEARCH_XP = 0.015     # xp/tick toward a tech whose prereqs are known
CATAPULT_RELOAD = 40         # steps between siege shots
CATAPULT_RANGE = 40          # how far a catapult can lob (whole-board)
CATAPULT_DAMAGE = 14         # maw damage per shot at mastery
CATAPULT_SPLASH = 2          # Chebyshev radius of the impact blast
GUNPOWDER_ATTACK = 6         # firearm punch added to a gunpowder soldier at spawn

# T2d materials -> crafting (SPEC_TECH TE13): the kid drops raw materials; a house
# with the enabling tech reshapes them into tools/weapons. Otherwise inert scrap.
MATERIALS = ('toothpick', 'string', 'lincoln_log', 'copper_pipe', 'tacks')
CRAFT_RECIPES = {          # (material, required tech) -> crafted item
    ('toothpick', 'metallurgy'): 'spear',
    ('toothpick', 'fire'):       'firespike',
    ('string', 'metallurgy'):    'bow',
    ('lincoln_log', 'masonry'):  'bastion',
    ('copper_pipe', 'metallurgy'): 'cannon',
}
CRAFTED_EFFECTS = {        # crafted item -> per-soldier spawn effect / tech grant
    'spear':     {'attack': 3},
    'firespike': {'defense': 6},
    'bow':       {'attack': 4},
    'bastion':   {'defense': 10},
    'cannon':    {'tech': 'catapult'},  # a copper-pipe cannon IS a siege engine
}
# tacks are NOT crafted - the hand scatters them as loose CALTROPS (area denial);
# they persist and can be repositioned (units crossing them are pricked)
CALTROP_COUNT = 10           # caltrops scattered per keeper_material('tacks')
CALTROP_DAMAGE = 2           # per step to a unit standing on a caltrop
