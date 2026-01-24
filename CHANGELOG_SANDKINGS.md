# Sand Kings Changelog

## [1.2.1] - 2026-01-23

### Added
- 3D scatter visualization now available in evolution demo mode
- Generates both 2D slice (`sandkings_demo_2d.gif`) and 3D scatter (`sandkings_demo_3d.gif`)
- 3D frames captured every 5 steps (configurable)

## [1.2.0] - 2026-01-23

### Changed - Simplified 3D Visualization
- **Replaced clustering with direct scatter plots** (inspired by 3D Conway's Life)
- Uses `np.argwhere()` to plot all voxels without sampling
- **Depth-based coloring**: Stone (grayscale), Sand (YlOrBr colormap)
- Reduced code complexity: removed 40+ lines of clustering logic
- Faster rendering for small grids, more accurate representation
- Colony-owned air shown with semi-transparent colored points

### Removed
- `_draw_cube_outline()` method (no longer needed)
- `cluster_size` parameter from `generate_3d_frame()`

## [1.1.1] - 2026-01-23

### Fixed
- **behavior_context initialization**: Added hasattr guard in `_update_unit_context()`
- **colony.metrics initialization**: Initialize dict in `EnhancedSandKingsSimulation.__init__()`
- **np.random.choice on tuples**: Replaced with `randint` + list indexing (3 locations)

### Tested
- Evolution mode: 3 rounds × 5 iterations, coverage 11.1%, fitness 110→114
- Demo mode: 50 steps (2s), 200 steps (82s), all colonies survived

## [1.1.0] - 2026-01-23

### Added - Evolution & LLM Integration
- **MapElites quality-diversity algorithm**
  - 6×6 behavioral characterization grid (territory × aggression)
  - Fitness = survival×1.0 + population×0.1 + territory×0.01 + kills×0.5
  - Archive checkpoint saving every 5 rounds

- **Ollama LLM integration**
  - OllamaGPT wrapper for AsyncOpenAI (http://localhost:11434/v1)
  - Model: granite-4.0-h-1b (configurable)
  - Behavioral script generation and mutation

- **Behavioral DSL interpreter**
  - WHEN/THEN conditional rules with priority
  - Conditions: near_food, near_enemy, low_health, carrying_food, in_territory, near_maw
  - Actions: dig, attack, flee, return_food, patrol, fortify
  - Supports AND/NOT operators

- **Enhanced combat system**
  - Cover bonuses from TUNNEL_WALL terrain
  - Action Points from genome.aggression × 3
  - Critical hits (2× damage on roll=6)
  - Enemy kills tracking

- **CLI interface**
  - `--mode demo/evolve`: Single simulation or MapElites loop
  - `--sim-steps [50,100,200,500,1000,2000]`: Configurable simulation length
  - `--use-llm`: Enable LLM behavioral script generation
  - `--rounds`, `--iterations`: Evolution parameters

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
