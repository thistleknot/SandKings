# Sand Kings Simulation

A 3D voxel-based colony simulation inspired by George R.R. Martin's "Sandkings" novella, combining:
- **Core War's MapElites evolution** - Quality-diversity algorithm for genome optimization
- **1pageskirmish's tactical combat** - Unit-based warfare with terrain and special abilities
- **Cellular Automata** - Conway-inspired 3D territory expansion rules
- **Emergent AI** - Pheromone communication and swarm behaviors

## Features (v1.0)

### Core Systems
- **VoxelWorld**: 3D terrarium (configurable dimensions) with tunnelable sand, gravity physics, fortification
- **Colony Management**: 4 competing Maw queens, each commanding workers/soldiers/scouts
- **Genome Evolution**: 8 evolvable traits (aggression, tunnel_preference, fertility, etc.)
- **Pheromone Communication**: Chemical trails for food, danger, territory, rally points
- **Cellular Automata**: Territory spreads like Conway's Life (birth with 3+ neighbors, survival with 2-5)
- **Inter-Colony Political Economy**: Three-tier labor-value extraction spectrum — SUBJUGATION (capture-not-kill thralls with defiance under coercion), WAGES (pairwise factor market: labor contracts, tech licenses, resource trade, all priced in grains), BARGAIN (per-pair mode selection where wages emerge by net extraction: a rational maw chooses the highest-return extraction path, and force leaks while trade scales). The framework reuses the same labor-value split spine across all three tiers, unifying war and peace as points on the same economic continuum.
- **Enlightenment — Post-Escape Intelligence Leap**: When a colony achieves the ONE true breakout (terminal mastery), it ascends with a bounded ×5 intelligence leap (not omniscience). The brain ceiling rises above the Shade cap (faster neural evolution), native tech climbs ~×`ENLIGHTENED_TECH_MULT` faster, and the codex reads ~×`ENLIGHTENED_CODEX_MULT` harder per consultation. The leap is earned climb, not instant grant — evolution and learning must still traverse the expanded space.

### Entity Types
- **Maw (Queen)**: Colony heart with food storage and spawning capability
- **Worker**: Excavates tunnels, gathers food (HP: 10, ATK: 2)
- **Soldier**: Defends territory, attacks enemies (HP: 25, ATK: 8)  
- **Scout**: Fast exploration units (HP: 5, ATK: 1)

### Visualization
- **2D Cross-Sections**: Fast Z-slice views showing terrain, units, ownership
- **3D Clustered Rendering**: Voxel visualization with translucent terrain outlines
- **GIF Export**: Generates animated sequences for both 2D and 3D views

## Installation

```bash
# Python 3.10+ required
pip install numpy matplotlib pillow tqdm
```

## Usage

```bash
# Run basic simulation (20 steps, 80x40x20 world)
python sandkings.py

# Outputs:
# - sandkings_2d.gif (2D cross-section animation, 20 frames)
# - sandkings_3d.gif (3D visualization, 5 frames)

# LIVE MODE: watch the terrarium in a real-time pygame window
# (demo: sandkings_live.gif)
python sandkings.py --live                     # run until you quit
python sandkings.py --live --steps 500         # auto-exit after 500 steps
python sandkings.py --live --use-neural --sps 10

# ECONOMY MODES: inter-colony labor-value extraction spectrum
python sandkings.py --subjugation --steps 300  # thralls & coercion (capture-not-kill at war)
python sandkings.py --wages --steps 300        # factor market (labor/tech/goods priced in grains)
python sandkings.py --bargain --steps 300      # full bargain (each pair picks annihilate/subjugate/wage)

# Two views (TAB toggles):
#   TOPDOWN (default) - Dwarf Fortress style: look down through open space
#     to the first terrain below the current z-level, shaded darker with
#     depth; tunnels appear as darker pits. UP/DOWN slices through the
#     earth one z-level at a time.
#   SLICE - single-z cross-section (same colors as the GIF renderer).
#
# Live controls:
#   SPACE pause/resume   S single-step (paused)   +/- speed
#   < / > z-level (DF-style, Shift or Ctrl + , / .)   UP/DOWN also works
#   TAB view mode        R glyph/block style      P pheromone overlay
#   G toggle GIF capture ESC quit
# Rendering is DF-style glyphs by default: sand ░, stone ▓, glass #,
# food •, corpses %, maws Ω, units as colony-colored w/s/c letters
# (magenta when retreating). Damaged maws show health bars; the HUD is
# color-coded with a live event feed.
# Dead colonies show a respawn countdown in the HUD.

# The terrarium is perpetual: the keeper scatters food every 100 steps,
# workers forage toward it, scouts survey and raise alarms, sandstorms
# reshape the dunes, and colonies that hoard past 400 food march to war -
# soldier-heavy spawns, cross-map raids on enemy Maws. Fallen colonies
# become corpse feasts and a new colony arrives in the slot.

# SEASONS & SCARCITY (--harsh skips the 2-year grace ramp): the dole
# shrinks to 25% in Chill. Colonies must FARM to prosper - till, sow
# (5 food), wait 300 growing steps, harvest 40 - but only in Flood and
# Growth, only if the field survives raids and storms. One lucky colony
# wakes beside the central OASIS where crops grow double in any season.
# Copper veins (soldier armor) and deep gold (a hoardable prize) hide in
# the stone. Each colony's posture (forage/farm/raid/fortify) is chosen
# by a tiny reinforcement learner whose patience (discount factor) is an
# evolvable gene - watch it on the manager screen.

# MANAGER SCREEN (M key; LEFT/RIGHT cycles colonies): colony mood,
# per-unit stats, and READABLE THOUGHTS - 23 measurable concepts
# (food, war, defense, underground, jealousy, love, clueless, ...)
# decoded from each soldier's recurrent hidden state by linear probes
# whose accuracy is always displayed; words come from GloVe-derived
# clusters and scale with confidence ("anxiety" -> "JEALOUSY").
# Rule-based colonies show instincts (same lexicon, direct predicates).
# The decision log ties outcomes to the thoughts that led to them.

# POLITICS, MACHINES, TIMBER & MONSTERS: trust and truces, gift envoys,
# coalitions against the hegemon, betrayal under truce; a buried wreck
# with a programmable ancient controller (QBasic-flavored VM), devices,
# radiation that catalyzes mutation; trees to chop and fell (bridges!),
# bone-and-palm spears, palisades, battering rams, fire that spreads;
# and DF-invader fauna - one announced incursion at a time (spiders,
# snakes, birds, scorpions, anteaters...) trampling through the world.

# DYNASTIES & THE SAGA (H key; E exports terrarium_saga.txt): every maw
# belongs to a named house ("House Vex-Karn II, the Oath-Broken");
# respawns are cadet branches of surviving bloodlines; epithets are
# earned by a reign's deeds; betrayals become eternal blood feuds; and
# the chronicle writes the whole thing down, salience-pruned, as a
# readable history the terrarium narrates itself.

# THE SENTIENCE ARC (--use-neural): soldiers within earshot resonate -
# GRU hidden states blend, so alarm literally spreads mind-to-mind
# before line of sight (watch "resonance: 0.62 across 7 soldiers" on
# the manager). Lineages that drift too far apart speciate ("too
# strange to mingle"); plasticity (learning rate) is itself an
# evolvable gene; and through the Chill the maws dream - experience
# replay consolidates each colony's policy at zero food cost.

# PET MODE: the terrarium lives between sessions (sqlite checkpoint)
python sandkings.py --live --persist           # resumes terrarium.db if present,
                                               # autosaves on exit; K saves anytime
python sandkings.py --live --persist mytank.db # named tank
```

## Architecture

```
VoxelWorld (3D NumPy arrays)
├── voxels[x,y,z]: VoxelType (AIR, SAND, STONE, GLASS, FOOD, CORPSE, TUNNEL_WALL)
├── ownership[x,y,z]: Colony ID or -1
└── stability[x,y,z]: Structural integrity (future use)

Colony (genome + units)
├── Maw (queen with food storage)
├── SandKing[] (worker/soldier/scout units)
├── ColonyGenome (8 evolvable parameters)
└── territory: Set[position]

PheromoneLayer (chemical communication)
└── trails[x,y,z,colony_id,type]: 4 pheromone types per colony

CellularAutomata
└── Territory spread rules (3D Conway-inspired)

Visualizer
├── render_z_slice() → 2D PIL Image
└── generate_3d_frame() → 3D matplotlib voxel plot
```

## Genome Parameters

| Parameter | Range | Effect |
|-----------|-------|--------|
| `aggression` | 0.0-1.0 | Attack vs retreat tendency |
| `tunnel_preference` | 0.0-1.0 | Deep tunneling vs surface expansion |
| `expansion_rate` | 0.0-1.0 | Resource-to-spawn conversion ratio |
| `defense_investment` | 0.0-1.0 | Wall-building priority |
| `foraging_range` | 5-20 | Max distance for food seeking |
| `swarm_threshold` | 10-50 | Population for swarm attacks |
| `fertility` | 0.0-1.0 | Spawn rate modifier |
| `resilience` | 0.0-1.0 | Damage resistance (future use) |

## Voxel Types

- **AIR**: Empty space, traversable, claimable territory
- **SAND**: Tunnelable substrate, affected by gravity
- **STONE**: Immovable bedrock (bottom 20% of terrarium)
- **GLASS**: Terrarium walls (boundaries)
- **FOOD**: Resource nodes (green), +10 food when consumed
- **CORPSE**: Dead units become food (red)
- **TUNNEL_WALL**: Reinforced colony walls (brown)

## Simulation Rules

### Gravity (every 5 steps)
- Sand falls into AIR below
- Ownership preserved through fall

### Cellular Automata (every 10 steps)
- **Birth**: Empty space gains ownership if 3+ adjacent owned cells
- **Death**: Owned cell loses ownership if <2 or >5 adjacent owned cells

### Pheromone Decay
- All trails decay by 5% per step
- Diffusion (future enhancement)

### Unit AI (v1 - Random)
- **Workers**: Random tunneling, seek nearby food
- **Soldiers**: Random patrol
- **Scouts**: (Not yet implemented)

### Combat
- Units in same position with different colony IDs attack
- Mutual damage based on attack values
- Dead units become CORPSE voxels

## Performance

- **Memory**: ~128MB for 800×400×200 voxels (uint8 arrays)
- **Speed**: ~1 step/sec for 80×40×20 world with 20 units
- **Rendering**: 2D slices ~50ms, 3D frames ~2s (with clustering)

## Roadmap

### Done
- [x] MapElites quality-diversity evolution (v1.1, `sandkings_evolution.py`)
- [x] LLM-generated behavioral scripts (v1.1, Ollama via OpenAI-compat API)
- [x] Behavioral DSL interpreter (v1.1, WHEN/THEN rules)
- [x] Enhanced combat (v1.1 cover/criticals; v2 morale + retreat AI)
- [x] Configurable simulation lengths (v1.1, `--steps` / `--sim-steps`)
- [x] Morale/shaken mechanics (v2.0: retreat at 10% HP, retreat coloring)
- [x] Resource gathering strategies (v2.2-2.3: directed foraging, scout
      intel, keeper feedings, war-chest economics)
- [x] Maw migration (v2.3: wounded maws crawl away from attackers)
- [x] Outcome-based fitness (v2.3: eliminations/survival dominate scoring)
- [x] Live viewer, DF glyph rendering, sandstorms, pet-mode persistence,
      soldier GRU memory (v2.1-2.3, see CHANGELOG)
- [x] Inter-colony political economy (v2.30-2.31, M1-M4: labor-value
      extraction spine, subjugation thralls, wage factor market, bargain
      mode selection — `--subjugation`, `--wages`, `--bargain` flags)
- [x] Enlightenment: post-escape intelligence leap (v2.31, brain ceiling
      raise, ×N tech/codex climb, heritability on respawn)

### Explicitly out of scope (closed with rationale)
- Tournament evaluation loop — outcome-based fitness delivers decisive
  scoring; full round-robin over archived phenotypes is research tooling
  beyond the terrarium's product scope. Reopen if evolution research resumes.
- Multi-model wound tracking — units have 5-20 HP; per-limb wounds add
  bookkeeping without observable behavior change at this scale. Morale +
  retreat already express "wounded".
- Nested colonies — no design exists for what nesting means here; parked
  until one does.
- UMAP for 3D visualization — would add a dependency, and the live DF
  top-down view superseded the need it addressed.

### Open research directions (neural)
- Soldier-to-soldier communication, colony speciation, meta-learning,
  neural workers, GPU forward passes — see NEURAL_HIVE_IMPLEMENTATION.md
  Research Questions. The nearest-term item (temporal memory) shipped as
  the v2.3 GRU.

## Credits

- Inspired by George R.R. Martin's "Sandkings" novella
- Core War MARS simulation architecture
- 1pageskirmish tactical combat patterns
- MapElites algorithm (Mouret & Clune, 2015)
- The full lineage — SimAnt, Dwarf Fortress (+stonesense), NetHack,
  The Sims, SimCity, Factorio, Minecraft, Neopets, Framsticks, Game
  of Thrones, Axelrod/Waltz/Ostrom, Sutton & Barto, and more — is
  mapped to specific mechanics in [INSPIRATIONS.md](INSPIRATIONS.md)

## License

MIT License - See LICENSE file
