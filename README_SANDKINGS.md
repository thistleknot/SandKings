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
python sandkings.py --live                     # run until you quit
python sandkings.py --live --steps 500         # auto-exit after 500 steps
python sandkings.py --live --use-neural --sps 10

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
#   TAB view mode        G toggle GIF capture     ESC quit
# Retreating units render dimmed with a magenta border.
# Dead colonies show a respawn countdown in the HUD.

# The terrarium is perpetual: the keeper scatters food every 100 steps,
# workers forage toward it, soldiers besiege enemy Maws, fallen colonies
# become corpse feasts, and a new colony arrives in the empty slot.
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

### v1.1 (Next)
- [ ] MapElites quality-diversity evolution
- [ ] LLM-generated behavioral scripts (Ollama integration)
- [ ] Behavioral DSL interpreter (WHEN/THEN rules)
- [ ] Enhanced combat (cover, AP, criticals, poison)
- [ ] Tournament evaluation loop
- [ ] Configurable simulation lengths (50-2000 steps)

### v1.2 (Future)
- [ ] Multi-model wound tracking
- [ ] Morale/shaken mechanics
- [ ] Resource gathering strategies
- [ ] Maw migration
- [ ] Nested colonies
- [ ] UMAP dimensionality reduction for 3D visualization

## Credits

- Inspired by George R.R. Martin's "Sandkings" novella
- Core War MARS simulation architecture
- 1pageskirmish tactical combat patterns
- MapElites algorithm (Mouret & Clune, 2015)

## License

MIT License - See LICENSE file
