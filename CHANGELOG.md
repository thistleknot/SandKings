# Changelog

All notable changes to this project will be documented in this file.

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
