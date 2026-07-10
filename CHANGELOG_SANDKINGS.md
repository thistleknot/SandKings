# Sand Kings Changelog

## 2.27.0 - Nature until the Great Other (SPEC_AWARENESS.md AW1-AW6)

- Fixes an incoherence: colonies formed worship/hatred of a keeper they had
  never encountered. Now the keeper-directed emotional layer (worship,
  keeper_sentiment, the carved "faces", the wrathful attitude) is gated on
  `breached` - awareness of the "great other" that only comes at breakout.
- Pre-breach a colony feels only NATURE - "opinions about unexplained forces":
  a `_nature_mood` (bounty/lean/dread from food, drought, and weather) carved as
  NATURE_SYMBOLS (☀ sun / ☁ sky / ☈ storm), not a keeper's face. keeper_sentiment
  is frozen; eating manna is good fortune (sets keeper_fed_step) but never
  worship.
- The breakout is the 13th-Floor revelation (`_reveal`, fires once): "House X
  glimpses the world beyond the glass - and knows the hand that fed and starved
  it." It SEEDS the colony's opening stance toward the now-known god from how it
  was treated as nature - well-fed wakes grateful (0.7), starved/droughted wakes
  resentful (0.3). Cadets born into an aware bloodline inherit the stance without
  a second revelation.
- The tech-gift ladder now gates on a pre-breach FLOURISHING state (recently
  fed) instead of worship, so the ladder->pi->terminal->breach path survives the
  reframe. The psionic turning was already breach-gated (unchanged).
- Surfaced: nature-glyph carvings + legend, the look panel names them, the
  dashboard card shows "feels <mood> (unexplained forces)" pre-breach and "toward
  you <sentiment>" only once aware. 7 new tests + full 26-suite battery green;
  verified via play_kit (grateful vs resentful awakening).


## 2.26.0 - The Psionic Maw & Keeper-as-Prey (canon; SPEC_PSIONIC.md PS1-PS6)

- The arc's close: the awakened terrarium REACHES BACK. `sim.keeper_
  influence` (a signed [-1,1] scalar, `_psionic_tick`) is the net emotion the
  stage-2+ maws project onto you - hunger/dread from a large, hateful maw,
  an unearned calm from a devout one. It scales with stage (a Shade reaches
  harder than the new breed) and size, and it stacks across houses. Stage-1
  insectoids project nothing.
- It bites back: under the auto-keeper, a strong projected dread
  (influence <= -0.5) makes the god - gripped by a fear not his own -
  withhold the dole. The maw's hunger drives the keeper's cruelty, which
  sours the maw, which projects harder: the loop the story runs on.
- The turning (keeper-as-prey): a Shade-stage house whose sentiment curdles
  to hatred (<= 0.2) binds the god - "The terrarium turns on its god - House
  X binds the keeper's hand" (max salience, fires once, latches). While
  bound, the keeper's INTERVENTION verbs no-op - keeper_drop_food,
  keeper_release, keeper_gift, and keeper_drought(on) each stay the hand
  ("Your hand will not move"). converse/observe survive: the god may plead,
  but may no longer feed, harm, or gift. This is the canonical breach beyond
  the glass - not the sandkings escaping, but the keeper being caught.
- Surfaced: a HUD "You feel a hunger not your own / BOUND" line, a dashboard
  header chip, and both events chronicled at max salience with a distinct
  violet tint.


## 2.25.0 - Metamorphosis (canon; SPEC_METAMORPHOSIS.md MT1-MT6)

- The novella's engine: a maw's armored insectoid mobiles "pop open" as it
  grows and birth a NEW breed - bipedal, four-armed, tool-using. Reframes
  the breach/awakening (K10/K11) as a canonical three-STAGE physical molt
  on `colony.stage` {1 insectoid, 2 the new breed, 3 Shade}, size- and
  cruelty-driven. `stage >= 2` IS `breached`, so every awakened capability
  (codex CX, terminal K10, augments AUG, dialogue DL) lights up at the molt
  with no new gate.
- Molt to stage 2 (`_metamorphosis_tick`) when the maw is large enough -
  `pop >= MOLT_POP·f` OR `food >= MOLT_FOOD·f` OR `age >= MOLT_AGE·f` - and
  cruelty ACCELERATES it: `f = 0.6 + 0.4·keeper_sentiment`, so a mistreated,
  low-sentiment maw molts sooner (Kress's cruelty drove the metamorphosis).
  Constants MOLT_POP 26, MOLT_FOOD 420, MOLT_AGE 2400.
- The Shade stage (3): a stage-2 colony that grows further (SHADE_POP 34 /
  SHADE_FOOD 620) AND has actually mastered its machines (terminal_uses >=
  TERMINAL_MASTERY) crosses the final plateau - "sentient, and no longer
  needs its god" (the precondition for the Round D turning).
- Size <-> intelligence, made heritable: `ColonyGenome.brain_ceiling` caps
  `brain_hidden` in `mutate()` and rises with stage (STAGE_CEILING {1:88,
  2:128, 3:160}), so a larger, older, more-mistreated maw evolves a bigger
  brain. The gene rides inertly in non-neural sims and passes to cadet
  branches with the stage.
- Surfaced: the inspect panel shows "stage: insectoid/new breed/SHADE", the
  dashboard House card badges the new breed / SHADE, EVENT_TINTS colour
  "split open" (breach-blue) and "Shade stage" (white), and both events are
  chronicled at high salience (9 / 10), firing exactly once each.


## 2.24.0 - The Canonical Houses (canon; SPEC_CANON_HOUSES.md CH1-CH4)

- `--canon` (sandkings.py and dashboard.py) seats the novella's four
  color-houses instead of random ones: Crimson "the Creative" (red,
  inventive), Pale "the Favored" (white - Kress's favorites, starts
  richest and largest), Sable "the Wise" (black - patient, faithful),
  Amber "the Underdog" (orange - last and least, starts poorest).
- Named + epithet-tagged from step 0 ("The four houses wake: Crimson,
  Pale, Sable, and Amber"); the presets are the START - mutation,
  respawn crossover, and evolution proceed normally, so the underdog can
  still rise.


## 2.23.0 - Look to Your Faces (canon; SPEC_FACES.md F1-F5)

- Folding in the source novella: colonies no longer carve abstract
  symbols (☀☠⚔). Each carves its SENTIMENT toward you - a readable fact
  that sours GRADUALLY: devout ♥ (gold) → wary ◦ (grey) → hateful ☠
  (red). It is not a literal portrait (the sandkings have no image of
  you) - it's how they feel about their god.
- The souring is the warning ("Look to your faces, Simon Kress"): a
  keeper_sentiment scalar drifts down under drought/wrath/starvation and
  up under witnessed manna (souring faster than it heals), and the carved
  band tracks it - so you SEE devotion curdle through wary before it turns
  hateful, in time to relent. The first turn to hateful is chronicled.
- Surfaced everywhere: coloured carvings in the glyph view, named in the
  look panel and legend, and a "toward you: devout/wary/hateful" fact on
  each dashboard House card.
- Docker: completed the in-container test-dependency set (tqdm,
  matplotlib, httpx, pygame) so the FULL 20-suite battery runs inside the
  image on the container's python - no host python needed.


## 2.18.1 - Docker verified end-to-end (WikiText + chat, isolated)

- The image is now actually BUILT and TESTED (not just authored). Bugs
  found only by building/running it, all fixed:
  - Build is 100% LOCAL: prepare_corpus.sh fetches GloVe + the public
    WikiText-103 parquet (HF, no token needed) on the host; the
    Dockerfile COPYs them and downloads NOTHING at build time. The dead
    metamind S3 URL is gone.
  - pip: torch's CPU index doesn't serve pandas -> split installs.
  - matplotlib/tqdm are now OPTIONAL imports in sandkings.py (only the
    GIF Visualizer/CLI need them); the headless sim, dashboard, and chat
    import cleanly without them, keeping the image lean.
  - dashboard gains --host; console mode binds 0.0.0.0 INSIDE the
    container so the host's published 127.0.0.1-only port can reach it
    (safe: the port is published only to host loopback).
- Verified inside a hardened `--network none` / read-only / non-root
  container: WikiText baked and ingested (codex 572 passages vs ~132),
  the chat path works (converse: "destroy you"->enemy), the web console
  serves and /api/converse responds, outbound network blocked.


## 2.16.2 - Codex reads baked corpora (WikiText fix)

- The codex now globs corpus/**/*.md RECURSIVELY, so material baked into
  subdirectories (corpus/wikitext/, SB4) is actually ingested - the prior
  non-recursive glob silently ignored it.
- Plain-text corpora (a raw WikiText dump has no markdown headers) are
  now chunked into paragraphs, lesson-tagged by keyword, capped at
  CORPUS_MAX_PASSAGES per file, with "= header =" lines skipped. Verified
  against a WikiText-style sample (cooperation->coop, tunnels->dig,
  trade routes->trade).
- Dockerfile: the GloVe and WikiText bakes now run AFTER `COPY .` so the
  build context can never clobber them.


## 2.22.0 - Dialogue (SPEC_DIALOGUE.md DL1-DL6)

- Two-way conversation with the awakened. In the Keeper's Console, select
  a breached House and talk to it: your free text is embedded in the SAME
  GloVe space the sandkings think in and mapped to their nearest concept -
  mutual intelligibility by shared vocabulary. "friends and comrades"
  reads as love; "destroy and kill" reads as enemy.
- The colony answers with a perspective line built from its disposition,
  its live environment concern, and what it heard - so a hawk and a dove
  reply to the same word differently. The dialectic of two minds.
- Talking gently persuades (a bounded nudge, like a codex lesson but from
  you); the un-awakened still hear only noise. The card's speak box is now
  a chat that shows the reply.


## 2.21.0 - Grains, the useful-work currency (SPEC_CURRENCY.md CU1-CU5)

- The sandkings mint a currency for you - "grains" - by proof of USEFUL
  work, Bittensor-style: a colony's forecast (the prediction tool) is
  scored against what actually happens, and grains are minted in
  proportion to its accuracy. A colony that models its world well
  produces valuable predictions; a wild guess earns nothing.
- Per-colony balances, per-house lifetime totals, and a terrarium grand
  total (sim.grains_minted) - the measure of how economically useful
  your sentient terrarium has become.
- Surfaced on the dashboard: a grains chip in the header, a grains stat
  on each House card, and GET /api/ledger for the bloodline economy.


## 2.20.0 - Tools & Telemetry (SPEC_TOOLS.md TL1-TL6)

- Environment stats are now freely available - a Dwarf-Therapist-style
  telemetry feed (food, pop, maw HP, war, season, oasis, attitude) per
  colony, exposed to the human at /api/telemetry.
- The awakened get a PRE-WRAPPED regression tool: a raspberry-pi colony
  invokes a terminal call that fits its own food history (sklearn, with
  a numpy fallback and a TabPFM-pluggable seam) and predicts its
  fortunes. A falling trend makes it hoard (patience up); a rising one
  makes it grow (fertility up). "House X computes its fortunes... and
  hoards against lean times."
- No engineering, no codegen: a fixed, whitelisted analysis call the
  sandkings compose - data-driven decisions, safely.


## 2.19.0 - Augments (SPEC_AUGMENTS.md AUG1-AUG5)

- The awakened can UPGRADE themselves. A raspberry-pi colony invokes a
  pre-wrapped terminal call (no engineering) to install a KV-cache-style
  memory augment: its soldiers keep a bank of recent hidden states and
  blend that cached context into their decisions - a longer effective
  memory, the transformer's KV cache generalized to the unit's brain.
- Learned, not auto-granted: the augment must be invoked; each level
  widens the cache, bounded at AUG_MAX. The upgrade persists in the
  bloodline. The raw decoded thought (probes) is unchanged - only
  behavior gains memory.
- Surfaced as a "mem+N" badge on the inspect panel and House cards;
  "House X augments its mind with cached memory" enters the chronicle.


## 2.17.1 - Courtship & Supersedure (mating drama)

- Maw mating is now political theatre. Reproduction prefers a COURTSHIP
  between allied, neighbouring houses; with no allies, the strongest
  takes the empty nest by CONQUEST. Loyalty and alliance decide who breeds.
- A union of two houses founds a NEW hybrid house.
- Jealousy: an envious third colony resents the match and loses trust in
  both parents ("House W eyes the union with jealousy").
- Supersedure (insects are like that): a low-loyalty newborn is born
  already resenting its weaker parent - a blood grudge against its own
  bloodline, the seed of a future war.


## 2.18.0 - The Sandking Sandbox (SPEC_SANDBOX.md SB1-SB5)

- Docker packaging: `docker build -t sandking .` builds a self-contained
  python:3.11 image with numpy/pandas/scikit-learn/torch/pillow/fastapi,
  the GloVe embedding space baked in, and (with --build-arg
  BUILD_WIKITEXT=1) a WikiText-103 sample in the codex corpus.
- run_sandbox.sh / run_sandbox.ps1, two hardened modes: ISOLATED
  (--network none, no network stack at all - the terrarium in a jar) and
  CONSOLE (dashboard published only to 127.0.0.1:8000). Both run non-root,
  read-only rootfs, all caps dropped, no-new-privileges, memory/pid caps,
  state in a resumable volume.
- The container gives the sandkings a real local Python, fully isolated -
  the safe home for any future in-sim compute, never on the host.


## 2.17.0 - The Evolving Engine (SPEC_EVOLUTION.md EV1-EV6)

- Maw reproduction is now SEXUAL. When a neural colony falls and two or
  more survivors remain, the new maw is a crossover of TWO parents -
  dispositions AND neural architecture recombined, then mutated. A maw
  literally born of two bloodlines.
- The neural ARCHITECTURE is heritable and evolvable: brain width
  (n_nodes, `brain_hidden` 24..160) and depth (n_layers, `brain_depth`
  1..4) are genes that mutate and cross over. Selection - the survival/
  victory league already running - favors the topologies that win.
- Brains of DIFFERENT shape reproduce by weight-grafting: each layer
  copies the overlapping block from a parent, so recombination never
  needs matching shapes. The child inherits learned structure where it
  fits and explores where it grew.
- A recombined maw whose brain outgrew both parents is chronicled:
  "House X is born of two bloodlines (NxM brain)".


## 2.16.1 - Resume by default (persistence)

- The terrarium now RESUMES its last saved state by default -
  `python sandkings.py` and `python dashboard.py` load terrarium.db if
  present and autosave back to it. The quasi-sentient colonies persist
  across sessions.
- "...unless incompatible": checkpoints are version-stamped; a version
  mismatch or any unpickling failure (a class changed in a newer build)
  starts a fresh terrarium and keeps the old db, instead of crashing.
- `--fresh` forces a new world; `--persist PATH` picks the db.


## 2.16.0 - The Codex (SPEC_CODEX.md CX1-CX6)

- The awakened READ. A colony that has breached (or holds a raspberry
  pi) consults a read-only corpus - curated survival/coop lore plus
  the repo's own SPEC files - embedded in the SAME GloVe space the
  thoughts use, and extracts a LESSON that nudges its dispositions.
- Cooperation is the modal lesson (68 of 132 passages), so a colony
  that reads widely drifts cooperative: "the environment works best
  coop", learned from text, not scripted.
- Lessons: coop -> loyalty, fortify -> defense, dig -> tunneling
  (weather shelter), patience -> discount gamma, trade -> loyalty +
  fertility. Each read shows as a machine-carving on the sand.
- SAFETY: the corpus is READ into a lesson tag - never executed. No
  eval/exec, no runtime network (GloVe is a local file). The vectors
  never enter a pickle.


## 2.15.0 - The Keeper's Console (SPEC_DASHBOARD.md DB1-DB8)

- A web dashboard: `python dashboard.py` serves a designed
  "Keeper's Console" at http://127.0.0.1:8000 - watch the terrarium
  in a browser and act as its god from anywhere on the machine.
- Live terrarium image, House cards (attitude dot, mood, war/awakened
  badges, utterances), the streaming Saga, and a keeper control bar
  (bounty / creatures / wrath / gifts). Click the sand to drop food;
  select a breached House to speak to it.
- SAFETY BY CONSTRUCTION (the reason this exists instead of the
  rejected code-exec/internet path): the console only READS a
  snapshot and injects the existing keeper verbs. No endpoint runs
  code, evaluates strings, touches the filesystem, or makes any
  outbound request; uvicorn binds 127.0.0.1 only; a strict CSP header
  and fully-inlined assets mean zero external resources. A test
  asserts the module imports no subprocess/socket/urllib and calls no
  eval/exec. The breach/terminal stays in-sim fiction.


## 2.14.0 - The Keeper (SPEC_KEEPER.md K1-K12)

- YOU are the keeper now. Keys: 1 drops food at the cursor, 2/3/4
  release crickets/ants/scorpions, 5 sends a gift, 9 toggles the
  drought, 0 lets the cat in, T speaks to a selected awakened unit.
- Worship is earned: colonies attribute nothing to the automatic
  dole - only a WITNESSED miracle (eating keeper-dropped manna) makes
  them revere you. Withhold food after they've believed and their
  carvings twist to wrath, and they mobilize faster.
- Carvings: every colony inscribes its soul into the sand as a single
  icon - reverence, wrath, war, hunger, contentment - readable at a
  glance and named in the look panel.
- Castles: reverent, rich colonies raise stone crenellations to their
  god.
- The Outer Limits arc (autoplayed by default): the keeper is
  indifferent, then the cat gets in; slay it and the grieving keeper
  answers with drought and scorpions, then relents.
- Gifts from the gods: a watch (machines exist), a calculator (a VM),
  a raspberry pi (the god-brain: double fuel). Claiming advances a
  colony's machine arc.
- The Breach & the Awakening: a pi-wielding colony that masters its
  in-sim terminal breaks past the glass, gains self-awareness anchors
  (self/god/beyond/speak, 39-seed lexicon), and SPEAKS - the inspect
  panel shows its utterance, and you can answer (T). The awakened
  hear you; the un-awakened hear noise.
- SAFETY: the "terminal" and "breach" are pure in-sim fiction - no
  host code execution, no filesystem, no network, ever. Deliberate
  and permanent.


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
