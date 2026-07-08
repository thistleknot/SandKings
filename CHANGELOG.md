# Changelog

All notable changes to this project will be documented in this file.

## [2.3.0] - 2026-07-07

### Added - Dazzle & Drama
- **DF-style glyph renderer** (default; `R` toggles plain blocks): sand ░,
  stone ▓, glass #, food •, corpses %, tunnel walls ≡; units as
  colony-colored w/s/c letters (magenta when retreating); maws as
  double-size yellow Ω over depth-shaded dimmed terrain
- **Color-coded HUD**: colony lines in colony colors, tinted event feed,
  [███░░] health bars for damaged maws, [WAR] badges
- **Drama feed**: keeper feedings, siege first-blood, colony falls, and
  arrivals stream into the HUD (sim.events, last 4 shown)
- **Pheromone overlay**: `P` cycles FOOD_TRAIL / TERRITORY / DANGER as
  additive colony-colored glow
- **War parties**: a colony hoarding > 400 food goes to war - spawn mix
  flips soldier-heavy and its soldiers raid enemy Maws across the whole
  map (the long-run soak previously showed rich colonies hoarding
  unboundedly with zero combat)
- **Scouts live**: 15% of peacetime spawns (10% at war); fast air-only
  wanderers that report distant food into shared colony intel (workers
  pull it when their own scan fails) and raise DANGER pheromone alarms
  when enemies close within 5 - closing the v1.0 "scouts defined but
  not spawned" limitation

- **Sandstorms**: every ~600 steps a 25-step storm's prevailing wind
  transports surface sand downwind, reshaping dunes and burying food;
  the viewer renders a flickering sand haze while it blows
- **Pet mode** (`--persist [db]`): the terrarium lives between sessions -
  resumes from a sqlite checkpoint, autosaves on exit, `K` saves anytime
- **Soldier GRU memory**: per-soldier recurrent state between the shared
  Maw encoding and the action head; crossover/mutation cover memory
  weights; offspring start with blank memories
- **Outcome-based evolution fitness**: enemies_eliminated and survival
  dominate scoring; maw sieges now run inside evaluation sims where
  elimination is terminal (closes BATTLE_SYSTEM_V2 Next Step 4)
- **Maw migration**: below 40% HP with an enemy in range, a Maw crawls
  away from its attacker at 2 food per move ('The Maw flees!')

### Changed
- Vectorized the cellular-automata territory pass (~100x on large
  territories; 2 -> 20 steps/s at full population) with a parity test
- Console prints use ASCII markers (emoji crashed cp1252 pipes on Windows)
- numpy pin trued to installed 2.2.6

### Removed
- sandkings_v1.py (dead legacy monolith, superseded since v1.2)

## [2.2.0] - 2026-07-07

### Added - Perpetual Terrarium (SPEC_TERRARIUM_LIVENESS.md)
- **Keeper feeding**: every 100 steps food scatters onto the surface, sized to
  sustain ~18 units/colony; each living colony's reserve is floored at 10
- **Worker foraging AI**: workers scan their foraging range for food/corpses,
  cache a target, and walk/tunnel toward it (was: random radius-2 encounters)
- **Maw sieges**: soldiers with no enemy units in range besiege the nearest
  enemy Maw; adjacent units damage it (Maw HP 100 → 500, regens 0.5/step
  while unbesieged). Colonies can now actually fall
- **Colony collapse + arrival**: a fallen colony becomes a corpse feast
  (units + 3x3 burst), its territory and pheromones clear, and 300 steps
  later a new colony arrives in the same slot with a mutated survivor genome
- **Bootstrap revival**: a living colony with 0 units always fields a worker
  when it can afford one — the frozen dead state is gone
- **DF-style strata terrain**: 3-octave value-noise dune heightmap, stone
  strata bands, roof-cemented caverns, surface food patches + buried pockets;
  maws spawn on the surface; world is gravity-settled at generation
- **DF z-keys**: `<` rises / `>` descends (Shift or Ctrl + comma/period),
  HUD shows respawn countdowns for fallen colonies
- **Tests**: `tests/test_terrarium.py` (9 acceptance tests) + viewer key tests

### Changed
- Economy rebalance: maintenance 1.0 → 0.1 food/unit/step, starting food
  200 → 120, starvation capped at 2 deaths/colony/step, expansion_rate
  init bounded so spawn thresholds stay in [30, 100]

### Fixed
- Starvation could pick the same unit twice in one step (double salvage)

## [2.1.0] - 2026-07-07

### Added - Live Terrarium Viewer
- **Live mode**: `python sandkings.py --live` opens a real-time pygame window
  (per-colony HUD, pause/speed/z-level controls, optional GIF capture);
  `--live --steps N` auto-exits for scripted runs. Spec: SPEC_LIVE_VIEW.md
- **Dwarf-Fortress-style top-down view** (default, TAB toggles to flat slice):
  looks down the z axis through open space to the first terrain at or below
  the current z-level, shaded darker with depth; tunnels render as darker
  pits and UP/DOWN slices through the earth like DF elevations
- **Retreat visualization**: retreating units render dimmed with magenta border
  (BATTLE_SYSTEM_V2 Next Steps item 3)
- **Tests**: `tests/test_live_view.py`, `tests/test_neural_activation.py`

### Fixed
- **Neural pruning was vestigial**: `HiveMindBrain.forward` had unreachable code
  and tracked nonzero-weight masks instead of activations; now tracks per-neuron
  post-ReLU firing EMA with a warm-up guard, so `prune_weights` actually prunes.
  Spec: SPEC_NEURAL_ACTIVATION_TRACKING.md
- **`fold_soldier_layer` shape mismatch**: blending a 7x32 soldier layer into the
  32x64 encoder raised RuntimeError whenever a dying soldier scored >= 0.7; now
  blends the overlapping submatrix
- **Default-flag crash**: `--num-colonies 0` (the default) built a zero-size
  pheromone colony axis before the random 3-5 count was resolved, crashing on
  the first deposit; the count is now resolved in `SandKingsSimulation.__init__`
- **requirements.txt**: added torch, matplotlib, Pillow (imported but unpinned)

## [2.0.0] - 2026-01-24

### Added - Sand Kings 3D Colony Simulation

#### Core Simulation
- **GPU Acceleration**: PyTorch + CUDA implementation achieving 8-24 it/s (vs 1-2 it/s CPU)
- **Variable Colony Count**: Random 3-5 colonies per battle instead of fixed 4
- **Randomized Spawn Positions**: Minimum 10% diagonal separation, safe zones at 1/8 to 7/8 of map
- **Morale System**: Units retreat when health drops below 10% of max HP (ancient warfare model)
- **Retreat Behavior**: Wounded soldiers flee from enemies, cannot attack while retreating
- **CLI Arguments**: `--steps`, `--num-colonies`, `--width`, `--height`, `--depth` support

#### Combat & Balance (Aggression > Defense)
- **Increased Soldier Damage**: Base attack increased from 8 → 12 (+50%)
- **Reduced Soldier Health**: Max HP reduced from 25 → 20 (-20%)
- **Weakened Defense**: Resilience range reduced from 0-100% → 0-30%
- **Offensive Bias**: Aggression trait range 50-100% (favors aggressive strategies)
- **AoE Combat**: Radius-1 combat resolution with resilience application

#### Darwinian Pressure Mechanics
- **Food Scarcity**: Reduced food spawning by 5x (divisor 500 instead of 100)
- **Maintenance Cost**: 0.5 food per unit per step
- **Starvation Death**: Units randomly killed when colony food < 0
- **Cannibalism**: +2 food recovered per starved unit
- **Corpse Recycling**: Dead units become edible VoxelType.CORPSE
- **Enemy-Seeking Soldiers**: Move toward closest enemy within foraging range

#### Evolution & Visualization
- **MAP-Elites Evolution**: LLM-driven genome optimization
- **Incremental GIF Building**: 50-frame chunks prevent memory leaks
- **5000-frame Support**: Disk-based storage for long simulations
- **3D Visualization**: Matplotlib 3D scatter plots with cluster view
- **2D Cross-sections**: Z-slice view for performance

### Changed
- **Combat Philosophy**: Core War's shared memory (100% combat) adapted to 3D sparse space via morale collapse
- **Fitness Model**: Preparation for tournament-based scoring (currently time + population based)
- **Spawn Strategy**: From fixed 4 corners to randomized positions with minimum distance

### Technical Details
- **Files Modified**: `sandkings.py` (867 lines), `sandkings_gpu.py` (325 lines), `sandkings_evolution.py` (745 lines)
- **Dependencies**: PyTorch 2.8.0+cu128, matplotlib, numpy, PIL, tqdm
- **VRAM Usage**: 16GB GPU (tested on CUDA-capable devices)

### Design Philosophy
Adapted Core War's forced-combat mechanics to 3D terrarium:
- Core War: Shared memory = 100% combat probability
- Sand Kings: 3D space = sparse encounters → morale collapse creates decisive outcomes
- Ancient warfare model: ~10% casualties trigger retreat → clear victors without total annihilation

### Documentation
- `BATTLE_SYSTEM_V2.md` - Detailed mechanics and design rationale
- `README.md` - Updated with Sand Kings section and quick start guide
- `CHANGELOG.md` - Version history (this file)

---

## [1.0.0] - 2025-01-XX (Original DRQ Release)

### Added
- Digital Red Queen (DRQ) algorithm for adversarial program evolution
- Core War simulation environment integration
- LLM-driven warrior generation and mutation system
- MAP-Elites archive with behavioral characterization
- Multiprocessing support for parallel battle evaluation
- Human warrior dataset (100+ warriors in `human_warriors/`)
- Visualization tools for Core War battles

### Core Components
- `src/drq.py` - Main DRQ algorithm loop
- `src/eval_warriors.py` - Battle evaluation system
- `src/corewar_util.py` - Core War simulation wrapper
- `src/llm_corewar.py` - LLM integration for warrior generation
- `corewar/` - Original Core War implementation (from rodrigosetti/corewar)

### Prompts
- `src/prompts/system_prompt_0.txt` - Redcode specification and examples
- `src/prompts/new_prompt_0.txt` - New warrior generation prompt
- `src/prompts/mutate_prompt_0.txt` - Warrior mutation prompt

### Paper
- Kumar et al. (2025) - "Digital Red Queen: Adversarial Program Evolution in Core War with LLMs"
- Published results showing convergent evolution toward general-purpose strategies
- Demonstration of Red Queen dynamics in artificial systems
