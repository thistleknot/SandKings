# Inspirations

Every system in the Sand Kings terrarium traces to something we loved.
This is the lineage, mapped to the specs and mechanics each one shaped.

## The Origin

- **"Sandkings" — George R.R. Martin (1979 novella)**: the whole
  premise. Maws as the sentient queen-organisms, insectoid castes
  fighting wars in a glass terrarium, a keeper who feeds them and
  watches drama unfold. The keeper's dole (T1), the glass walls, the
  castle-building war-making colonies — all of it is the novella's
  terrarium given a physics engine. (Martin appears twice on this
  list; see Game of Thrones.)
- **DRQ (SakanaAI)**: the substrate repo. A self-play algorithm — each
  round evolves a best response to the population of past opponents —
  which is why the sim's red-queen respawn (mutated survivor genomes)
  and adversarial fitness ARE a self-play league. The epic rounds
  added the other half of RL: value learning within a lifetime.
- **Core War**: the origin repo's MARS-style program-vs-program
  arena DNA — echoed again in the machine age's bounded register VM.
- **MAP-Elites (Mouret & Clune, 2015)**: quality-diversity search in
  the origin repo's evolution machinery.

## Games

- **SimAnt**: colonies, castes, pheromone trails, the yellow-vs-red
  war for the yard. The pheromone layer (FOOD_TRAIL / DANGER /
  TERRITORY / RALLY) and caste economy are pure SimAnt.
- **Dwarf Fortress**: the deepest well, drawn from repeatedly —
  - the top-down z-sliced view and `<`/`>` keys (R12, R8a);
  - strata, ore veins and clusters mined straight from the DF raws
    grammar (GROWDUR seasons for crops, ENVIRONMENT/VEIN/CLUSTER for
    minerals — SPEC_SEASONS_AND_STONE);
  - entity VALUE/PROGRESS_TRIGGER dispositions -> the political
    genome and prosperity-triggered coalitions (SPEC_POLITICS);
  - invaders and megabeasts -> the fauna bestiary's one-incursion
    rule ("significant events trampling through an otherwise
    carefully constructed environment", SPEC_TIMBER T48);
  - forgotten beasts / legendary items -> the ancient controller's
    discovery arc that "falls silent" but never dies (T34);
  - levers and waterways -> the composable machine actuators (GATE/
    VALVE/ALARM/BEACON cascades, SPEC_MACHINE_AGE);
  - `k`/`v` look-and-inspect, follow-creature, and the legend
    (R32-R34); losing is fun -> heat death was declared a bug and
    perpetual drama a requirement (SPEC_TERRARIUM_LIVENESS).
- **Stonesense (DFHack)**: the isometric sprite view (R36) — TAB to a
  dimetric projection rendered from purpose-built sprites, exactly
  what stonesense was to DF's glyphs. Ours are procedurally baked
  (iso_sprites.py) so every species always has a sprite.
- **NetHack**: the maw as a stationary mastermind with a deep verb
  list — it never moves, but it chooses postures, programs machines,
  dispatches envoys, builds rams, judges truces. "A player who leads
  a hive."
- **The Sims**: readable inner lives. Needs and moods became the
  thought layer — decoded, English-word thoughts above every unit's
  head and a colony mood line (SPEC_HIVE_MONITOR).
- **SimCity**: the economy-as-city framing — farms, mines, timber,
  granary doles, infrastructure (palisades, dams, channels) — a city
  simulator where the citizens are insects.
- **Tower defense (the genre)**: fauna incursions against your walls
  and gates; palisade rings, the siege-gate demo program, and the
  battering rams that answer them.
- **Factorio**: the crashed-spaceship tech arc — salvage, circuits,
  logic-gated devices, the dream of automation rising from a wreck
  (SPEC_MACHINE_AGE). Terraform cascades (EXCAVATE/DEPOSIT) are the
  factory-game instinct applied to sand.
- **Minecraft**: "keep building simple" — blocky, single-voxel
  construction (chop wood, place wall) with long-term DF ambitions;
  and mobs — monsters that own the dark seasons (fauna spawn odds
  double in Dust/Chill).
- **Neopets**: pet mode. The terrarium as a persistent creature you
  check in on across days — `--live --persist` autosaves the whole
  world to sqlite so your colonies age, feud, and remember while
  you're away (T13). The saga screen is the pet's diary.
- **StarCraft's Zerg / Starship Troopers**: the aesthetic north star
  for the insect swarm — a hive that reads as one organism with
  teeth. Resonance (S1) literalizes it: the hive hums as one mind.
- **Chess (the user's chess-deep-q repo)**: the RL_FINDINGS became
  design law — bootstrap from the heuristic, never tabula rasa; keep
  learned components small and inspectable; judge the agent by
  outcomes, not loss curves (T26, SPEC_SENTIENCE).

## Books, Theory & Science

- **Game of Thrones — George R.R. Martin (again)**: politics
  happening to NAMED HOUSES WHO REMEMBER. Dynasties, cadet branches,
  earned epithets ("the Oath-Broken"), blood feuds that outlive
  generations, oathbreaking as the unforgivable crime, and a
  chronicle that writes it all down (SPEC_DYNASTIES).
- **Sutton & Barto, *Reinforcement Learning***: TD(0) colony
  learners; the discount factor as temperament — gamma IS the
  evolvable `patience` gene, so long-term-vs-short-term thinking is
  under selection (T26).
- **Axelrod, *The Evolution of Cooperation***: reciprocity, costly
  signals (physical gift envoys who can die en route), forgiveness
  via trust decay, and the tournament run on the `loyalty` gene.
- **Waltz (structural realism)**: power balancing — coalitions rise
  against the hegemon because of the DISTRIBUTION of power, not its
  character (P7/P8).
- **Ostrom, *Governing the Commons***: cooperative cultivation —
  allied crop-tending with shared yields, safe passage, and the
  honesty table of which principles mapped and which didn't (P10).
- **The Baldwin effect**: learning shapes selection — made explicit
  when `plasticity` (the learning rate itself) became an evolvable
  gene (S3).
- **Lin 1992 / DQN experience replay**: the maws dream — Chill-season
  offline consolidation of the year's transitions (S4).
- **word2vec / GloVe**: the thought vocabulary — anchor concepts
  expanded through embedding neighborhoods into the words the units
  think with (SPEC_HIVE_MONITOR M9).
- **Framsticks**: the artificial-life benchmark to surpass — it
  evolves bodies; this evolves biographies. Named in the project's
  goal statement.
- **QBasic**: the flavor of the machine age — an evolved maw gets "a
  calculator and QBasic," not a computer: a bounded register VM with
  10 opcodes and a fuel limit (T30).
- **textgrad**: the maw-as-programmer loop — propose a program edit,
  keep it if utility improves; the GP tinkerer's interface is sized
  for a future LLM proposer (T35).
- **Pathfinder (feats)**: capability composability — cartridges and
  actuators as feats that combine into builds (GEO + BIO + MATH).
- **The Nile**: inundation agriculture — the oasis overflows, the
  flood that drowns you leaves the silt that feeds you, and dams and
  runoff channels are how a civilization answers (SPEC_WEATHER W1).

## Civilization & the Tech Tree

- **Sid Meier's Civilization**: technology as a tree. Two classes here —
  FOREIGN tech the keeper gifts (abacus → watch → calculator → raspberry pi,
  a "10,000-year sprint," Aristotle handed a calculator; the pi is the escape
  key), and NATIVE tech the maws earn (fire, farming, metallurgy, plow,
  masonry). Tech confers real capability: metallurgy → weapons + picks,
  farming → yield. (SPEC_TECH.)
- **Dwarf Fortress skills**: per-house proficiency; a spawn's role bonus scales
  with the house's skill. The maw is the mastermind (a private psionic mind,
  blind to other maws' minds); the spawn are OnePageRules-style skirmish
  underlings whose stats scale with the house's tech (see `1pageskirmish.py`,
  Hellas). Because a maw can't READ a rival's mind, tech spreads only by
  OBSERVING the underlings' works, BARTERING for it, or taking it by CONQUEST.
- **The kid with a terrarium of warrior ants**: the keeper is a child playing
  god. Gift raw MATERIALS (a toothpick) and watch them learn to craft spikes,
  spears, arrows. Drop in food and prey (wingless flies, a mouse). And — the
  thing every kid actually does — **start a fire / light a firecracker**: fire
  as a SimCity-style DISASTER the keeper unleashes (arena/wrath), not just a
  season's dry-lightning. Providence: giveth and taketh so they learn to be
  resourceful — agile, improvise, adapt, overcome.
- **The Bittensor economy gets a sink**: grains, minted for accurate forecasts,
  are finally SPENT — to research native technology.

## The Standing Directive

"Dazzle me, but keep it ASCII" (the glyph views) — later joined by
"a non-ascii isometric view with sprites" (the ISO view), and over it
all: *"[quasi] sentient life operating inside my computer within the
terrarium."*
