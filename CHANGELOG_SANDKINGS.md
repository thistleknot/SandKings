# Sand Kings Changelog

## [1.0.0] - 2026-01-23

### Added - Foundation Release
- **VoxelWorld**: 3D terrarium with configurable dimensions (default 80×40×20)
  - 7 voxel types: AIR, SAND, STONE, GLASS, FOOD, CORPSE, TUNNEL_WALL
  - Gravity physics (sand falls every 5 steps)
  - Tunneling mechanics with ownership tracking
  - Fortification system (sand → reinforced walls)
  - Random terrain generation (glass walls, stone substrate, stone pillars, scattered food)

- **Colony System**: 4-player competitive colony management
  - Maw (queen) entity with food storage and spawning
  - ColonyGenome with 8 evolvable parameters
  - 3 unit types: Worker (dig/gather), Soldier (combat), Scout (explore)
  - Territory tracking via ownership array
  - Color-coded colonies: Red, White, Black, Orange

- **Entity AI**: Basic behavioral rules
  - Workers: Random tunneling based on genome.tunnel_preference, seek food within radius 2
  - Soldiers: Random patrol
  - Scouts: (Not yet implemented)

- **Pheromone System**: Chemical communication layer
  - 4 pheromone types: FOOD_TRAIL, DANGER, TERRITORY, RALLY
  - Per-colony per-type channels
  - 5% decay per step
  - Gradient-following (infrastructure, not yet used by AI)

- **Cellular Automata**: 3D Conway-inspired territory expansion
  - Birth rule: Empty space owned if 3+ adjacent owned cells
  - Death rule: Owned cell lost if <2 or >5 adjacent owned cells
  - Applied every 10 steps

- **Combat System**: Basic mutual damage resolution
  - Position-based collision detection
  - Mutual attack damage
  - Dead units → CORPSE voxels (future food source)

- **Visualization**: Dual rendering approach
  - 2D Z-slice cross-sections (PIL-based, fast)
    - Colony-colored owned territory (30% transparency)
    - Units as bright dots
    - Maws as yellow stars
    - Voxel type color mapping
  - 3D clustered voxel rendering (matplotlib-based)
    - Translucent outline cubes for stone/glass
    - Scatter plots for units/sand/food
    - Clustering to reduce point count (configurable cluster_size)
  - GIF export for both views

- **Performance Optimizations**
  - NumPy uint8 arrays for voxel storage (~128MB for 800×400×200)
  - Vectorized gravity physics (layer-by-layer sweep)
  - Position-based collision detection (dict grouping)
  - Periodic physics/CA updates (not every step)

### Technical Details
- **Dependencies**: numpy, matplotlib, pillow, tqdm
- **Python Version**: 3.10+
- **Simulation Speed**: ~1 step/sec for 80×40×20 with 20 units
- **Rendering Speed**: 2D ~50ms, 3D ~2sec per frame

### Known Limitations
- Scout units defined but not spawned
- Pheromone gradients not used by AI yet
- No LLM evolution (hardcoded genome parameters)
- No behavioral scripts (random unit decisions)
- No tactical combat depth (no cover, AP, special effects)
- No tournament/fitness evaluation
- Fixed simulation parameters (not CLI-configurable)

---

## [Unreleased] - Planned for v1.1

### To Be Added
- MapElites quality-diversity evolution framework
- LLM-generated behavioral scripts via Ollama
- Behavioral DSL (WHEN/THEN rules) with interpreter
- Enhanced combat system (cover bonuses, AP, criticals, poison)
- Tournament evaluation loop for fitness calculation
- Configurable simulation lengths (50, 100, 200, 500, 1000, 2000 steps)
- CLI argument parsing for world dimensions, step count, visualization options
- Archive visualization (coverage heatmaps)
- Checkpointing/resume functionality
