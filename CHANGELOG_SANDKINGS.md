# Sand Kings Changelog

## 2.13.0 - Isometric Sprite View (SPEC_LIVE_VIEW R36)

- TAB now cycles THREE views: TOPDOWN -> SLICE -> ISO. The ISO view
  is a stonesense-style dimetric projection - sprites, not glyphs.
- The sprite forge (iso_sprites.py): every sprite is procedurally
  baked from the live palette at load - iso terrain cubes with
  per-material pixel detail (sand speckle, stone cracks, ore glints,
  wood rings, web strands, circuitry), colony-tinted bug sprites per
  caste (soldiers get mandibles), maw mounds, all eight beast
  species, translucent flood water, and flame. Zero external assets,
  zero licensing, and coverage of every voxel/species is asserted in
  tests - a new species can never be sprite-less.
- </> still slices the world isometrically; fires, floods, units,
  maws, and beasts all render at their true heights with painter's-
  order occlusion; the look cursor works in ISO (keyboard-driven).


## 2.12.0 - Desert Weather (SPEC_WEATHER.md W1-W6)

- The Nile inundation: in Flood season the oasis overflows - water
  spreads by real flood-fill hydrology from the basin. Dams part the
  water (palisades, DEPOSIT banks, piled sand); dug channels carry it
  past high ground - terraforming IS flood control, and the colonies
  already own the tools. The receding water drowns, extinguishes,
  and leaves the richest silt on the oasis ring.
- Hail: Growth/Dust storm rolls may come down as stones - exposed
  units battered, standing crops smashed to tilled soil.
- Cold snaps: the desert night's ambassador - killing frosts in
  Chill (and sometimes Dust) that harm only the exposed.
- One shared law: underground is shelter. Weather selects for
  colonies that dig.
- HUD weather line, hail/frost/flood overlays, weather events in the
  chronicle; the `storm` thought now reads any active weather.
- Perf: fixed a kin-check regression in hostile() (O(1) house map;
  24 -> 15 -> 18.7 sps across the dynasty rounds).


## 2.11.0 - Look, Inspect, Follow & Legend (SPEC_LIVE_VIEW R32-R34)

- Look cursor (I, or just click a cell): DF-style inspection - the
  panel names the voxel, its owner, whether it burns, and everyone
  standing in that column.
- Inspect (V/ENTER cycles targets): full unit sheets - HP, attack
  (spear flagged), armor/torch/poison/retreat flags, cargo, kills,
  and the unit's current decoded thought. Maw sheets show house,
  posture, and genome temperament; beasts show species and mood.
- Follow (F): leash the camera to a unit - the cursor and z-level
  track it every frame until it falls, DF follow-creature style.
- Legend (L): every terrain glyph, unit letter, beast letter, and
  color rule on one screen, enumerated from the live glyph tables so
  new voxels/species can never silently miss it.


## 2.10.0 - The Sentience Arc (SPEC_SENTIENCE.md S1-S6)

- Resonance (S1): soldiers of one colony within earshot blend GRU
  hidden states each tick - literal thought contagion. One soldier's
  alarm raises its squadmates' decoded p(danger) before they have
  line of sight. Conspecific allies cross-resonate, damped; hostile
  minds never mingle. The manager reports it: "resonance: 0.62
  across 7 soldiers" - how much the hive is of one mind.
- Speciation (S2): lineages whose genomes drift beyond a threshold
  can no longer interbreed (combat crossover bears no young) or
  share culture (no allied resonance). The first crossing is
  chronicled: "House X and House Y have grown too strange to mingle."
  Kin houses are conspecific by construction.
- Plasticity (S3): a new evolvable genome trait scales the colony
  learner's rate and exploration floor - selection now acts on HOW
  FAST minds adapt, not just what bodies do (the Baldwin experiment,
  made explicit).
- Dreams (S4): learners keep a replay memory; through the Chill the
  maws dream - offline TD consolidation at zero food cost. "The maws
  dream through the long frost."


## 2.9.0 - Dynasties & Chronicle (SPEC_DYNASTIES.md D1-D7)

- Houses: every maw belongs to a named dynasty ("House Vex-Karn").
  Respawns are cadet branches of the genome parent's house
  (generation numerals: Vex-Karn II). Kin never fight kin.
- Epithets: a house is judged at the death of its maw - the reign's
  weighted deeds earn "the Oath-Broken", "the Machine-Waker",
  "the Farmer-King", "the Beast-Slayer", "the Burned"...
- Blood feuds: betrayal is remembered between HOUSES, forever -
  it biases war-target choice across generations and announces
  "The blood feud between House X and House Y flares again!"
- The Chronicle: every event is scored for salience and written to
  a pruned, house-attributed historical record that survives
  checkpoints. Low drama fades; deaths, betrayals, and machine
  wakings are never forgotten.
- The Saga screen (H key): the terrarium narrates its own history -
  year by year, season by season, in the names of its houses.
- HUD roster and manager speak in houses; the manager shows the
  house's self-model: "House Vex-Karn broods on vengeance, pride."


## 2.8.0 - Timber, Bone & Flame (SPEC_TIMBER_AND_FLAME.md T41-T48)

- Trees: palm clusters by the oasis, scrub in the wastes (WOOD voxel,
  Flood-season regrowth to TREE_CAP). Workers chop when the woodpile
  runs short; felled crowns lay along the fall line - bridges happen.
- Bone economy: corpse grabs bank bone; wood + bone arms new soldiers
  with spears (+4 attack) that splinter after 400 steps. Organic
  stores rot (metal is forever - why ore stays precious).
- Palisades: FORTIFY colonies wall their maw with WOOD_WALL rings
  that rot back to sand; battering rams (3 wood, wartime) smash
  enemy walls and double maw-siege damage.
- Fire: thrown torches, Dust-storm lightning, and radiation hot
  zones ignite; fire spreads through crops/wood/webs, damages
  units, burns out to scarred sand. Firebreaks are emergent.
- Fauna bestiary (DF-invader rule - one incursion at a time, always
  announced, wanders off if unslain): spiders (webs snare), rabbits
  and squirrels (neutral, fight back; squirrels poach food and slip
  away unless pinned by two), birds (strike stragglers, wheel away),
  scorpions (poison DoT), snakes (swim through sand), rodents
  (corpse-scavengers), anteaters (apex). Slain beasts pay bounty
  corpses. Spawn odds double in Dust/Chill.
- Thought layer: +fire, +monster anchors (35 seeds, GloVe rebuilt);
  beasts flood DANGER pheromone for every colony.
- Viewer: WOOD/WOOD_WALL/WEB glyphs + palette, violet beast letters,
  orange fire carets, wood/bone/[RAM] on the manager screen, new
  event tints for fells/palisades/torch/wildfire/incursions.


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
