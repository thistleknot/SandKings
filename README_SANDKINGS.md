# Sand Kings — a quasi-sentient ASCII terrarium

> *"[quasi] sentient life operating inside my computer within the terrarium."*

Sand Kings is a perpetual, Dwarf-Fortress-styled artificial-life terrarium. Insectoid colonies —
each ruled by a stationary **maw** (queen) — tunnel, farm, fight, trade, and *learn* inside a glass
tank you tend as the keeper. It grew out of **DRQ** (Sakana AI's *Digital Red Queen*, this repo's
parent — see `README.md`): DRQ's self-play/red-queen dynamics became the colonies' adversarial
neuroevolution, and *"the epic rounds added the other half of RL — value learning within a lifetime."*
The fiction is George R.R. Martin's **"Sandkings"** novella; the lineage (SimAnt, Dwarf Fortress,
NetHack, The Sims, SimCity, Factorio, Neopets, Game of Thrones, Sutton & Barto, Axelrod/Ostrom, …) is
mapped mechanic-by-mechanic in [INSPIRATIONS.md](INSPIRATIONS.md).

Everything below is **baseline-ON** — a fresh run boots the full living system. Each subsystem has an
**opt-out** `--no-*` flag (used to isolate a controlled world for the regression battery).

---

## Quick start

```bash
# Windows: use the py310 interpreter (never a bare `python`).
C:/Users/user/py310/Scripts/python.exe sandkings.py --live --fresh

#  --live      real-time pygame window (omit for a headless GIF/soak run)
#  --fresh     ignore any saved tank and start a new world
#  --persist   the tank lives between sessions (sqlite autosave; resumes if present)
#  --steps N   run N steps then stop (headless) / auto-exit (live)
#  --num-colonies K, --width/--height/--depth   world shape
```

A fresh live run prints its active systems, e.g.:

```
[NEURAL]  hive minds active            [MAW-RL]  85:15 real-RL active
[REPR]    learned shared encoder basis [GUPPIES] the oasis pond lives
[CRICKETS] the dunes chirp             [SNARES]  webs and weirs catch the shoals
[CHAIN]   HYDRO — the oasis springs
```

**Opt-out flags:** `--no-neural` (rule-based minds), `--no-maw-rl`, `--no-learned-basis`, `--no-hydro`,
`--no-guppies`, `--no-crickets`, `--no-snares`. **Economy:** `--bargain` (full political economy) /
`--subjugation` / `--wages`. **Population:** `--dynamic` (colonies breathe 2–8 with succession).

---

## The living systems

### 🧠 The brain — real deep-RL, *under* the GA
Neural colonies think with a **frozen shared encoder → evolvable readout** (the maw's 85% brain), plus
a small per-soldier layer. On top sits a **real reinforcement learner** (REINFORCE/policy-gradient),
layered *under* the neuroevolution (the GA still mutates/mates/grafts genomes across generations; the
RL learns within a lifetime — the two-timescale split honours DRQ's "value learning within a lifetime"):

- **85 % maw tier** — a gradient-trained policy emits a colony **directive** (aggression · mobility ·
  verticality · forage-mode). Learns by **RLOO** (leave-one-out baseline) + an **entropy** term
  (so colonies keep diverging), **warm-started from the genome's instincts** (never tabula rasa),
  its learning-rate set by the evolved `plasticity` gene and its discount by the `patience` gene, and
  it **dreams** through the Chill (elite self-distillation replay).
- **15 % spawn tier** — a shared, bounded per-soldier residual ("play").
- **Learned encoder basis** — a k-means codebook fit to the real state manifold (≈28× better coverage
  than the old random one), shared/frozen so grafting stays intact.

The maw narrates its learning in the drama feed ("*House X beats the war-drums*") and you watch
colonies grow distinct personalities.

### 🐟 The food web — a weather-rotated RPS ecosystem
Three harvestable **guilds** whose abundance rotates with the seasons, so no single food is ever best
and colonies must **adapt their foraging** (which the maw *learns* via its forage-mode directive):

| guild | booms in | becomes food via |
|---|---|---|
| **Guppies** (+ algae) | Flood / Growth (wet) | catch → oasis FOOD |
| **Crickets** (land swarm) | Dust (dry) | land FOOD + fall into water |
| **Fauna bounty** | Dust / Chill (dark) | CORPSE on the kill |

Coupled into one web: crickets eat crops (a pest) → fall into the water (a guppy feast, flood-amplified)
→ fauna cull the swarm; guppies' diet spans algae + crickets + crop droppings. **Snares** — spider webs
and keeper string/toothpick weirs by the water — passively catch guppies and crickets. See
[SPEC_FOOD_WEB.md](SPEC_FOOD_WEB.md) and [SPEC_GUPPIES.md](SPEC_GUPPIES.md).

### 🌦️ World & weather
A closed **biome**: a water-level and sunlight budget you set behind the glass, from which weather
*emerges*. Four seasons (**Flood · Growth · Dust · Chill**, 400 steps each) scale the keeper's dole and
gate crop growth; storms, hail, floods (Nile-style silt), cold snaps and heat waves come and go. A
per-cell **HYDRO** flow-sim springs the oasis, floods and pools; colonies dig rivers, reservoirs and
dikes and raft across the water. (`SPEC_SEASONS_AND_STONE`, `SPEC_BIOME`, `SPEC_WEATHER`, `SPEC_HYDRO`.)

### 🕷️ Fauna, politics, economy, tech
- **Fauna** — DF-invader incursions (spiders, scorpions, snakes, anteaters, birds…), one wild pack at a
  time, doubled in the dark seasons; killed for a corpse-feast bounty.
- **Politics & economy** — trust, truces, gift envoys, coalitions against a hegemon, betrayal; and a
  three-tier labor-value spectrum (subjugation ↔ wages ↔ bargain) unifying war and peace on one economic
  continuum. (`SPEC_POLITICS`, `SPEC_BARGAIN`, `SPEC_WAGES`.)
- **Tech & machines** — native tech (fire, farming, metallurgy) the maws earn, foreign tech the keeper
  gifts (abacus → … → a raspberry pi), a buried wreck with a QBasic-flavored register VM, spears,
  palisades, rams, fire that spreads. (`SPEC_TECH`, `SPEC_MACHINE_AGE`.)
- **Dynasties & the saga** — every maw belongs to a named house that remembers; respawns are cadet
  branches, epithets are earned, betrayals become blood feuds, and the chronicle writes it all down
  (`H` key; `SPEC_DYNASTIES`).

---

## Live controls

`SPACE` pause · `S` single-step (paused) · `+/-` speed · `TAB` view (top-down / slice / iso) ·
`< >` (or `UP/DOWN`) z-level · `R` glyph/block · `P` pheromone overlay · `G` GIF capture ·
`M` manager screen · `H` saga · `I` look-cursor (then arrows to move; **Shift+arrow jumps 10, hold to
pan**) · `L` **legend (full key list)** · `ESC` quit.

**Keeper's hand:** `1` drop food · `w`/`d` irrigate / deluge · `j` sow seeds · `x`/`c` water level ·
`a`/`z` sunlight · `5` gift tech · `2-4`/`6-8`/`0` release fauna · `u` firecracker · `9` drought ·
`[`/`]` cold / heat wave. Press `L` in-game for the authoritative list.

The HUD shows the season, the `Pond:` and `Swarm:` abundance lines rising and falling with the weather,
and a color-coded live drama feed.

---

## The genome (evolvable genes)

`aggression`, `tunnel_preference`, `expansion_rate`, `defense_investment`, `fertility`, `resilience`,
**`patience`** (the RL discount / temperament), **`plasticity`** (the RL learning-rate; the Baldwin
effect), `loyalty`, plus `foraging_range`, `swarm_threshold`, and brain-size genes. The GA
mutates/mates/grafts these across generations; the RL warm-starts from and is tuned by them within a life.

---

## Project map

- `sandkings.py` — the simulation (world, colonies, food web, seasons, fauna, politics, keeper, entrypoint).
- `maw_brain.py` — the real-RL maw/spawn policies (RLOO, entropy, warm-start, dreaming, directives).
- `neural_hive.py` — the frozen encoder (ZCA + Kanerva codebook) + evolvable readout + soldier layers.
- `neuroevolution.py` — the GA (mutate/crossover/graft). `live_view.py` — the pygame viewer + HUD.
- `tools/` — `fit_learned_basis.py` (fits `learned_basis.npz`), `measure_objective.py` (RL metrics).
- `run_tests.py` — the single-process regression battery (`tests/test_*.py`).
- **Design docs** — `SPEC_*.md` (per-subsystem specs), `docs/decisions/` (accepted designs),
  `objective.md` / `progress.md` (tracked RL metrics over time), [INSPIRATIONS.md](INSPIRATIONS.md).

*Local research fork — not published. MIT (see LICENSE); inherits the DRQ paper attribution in `README.md`.*
