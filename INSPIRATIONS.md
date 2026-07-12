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
- **Populous (the god game)**: the keeper as a hands-on deity who
  sculpts the world his followers live in — raise and lower the land
  and water, and unleash disasters on command. Ours literalizes it:
  raising/lowering water and seeding the ground (the Hydro-Hand,
  SPEC_HYDRO_HAND), the firecracker/flood/drought as god-view
  DISASTERS the keeper unleashes (arena/wrath), and the top-down
  god's-eye view itself. Providence with a cursor.
- **Syndicate / Syndicate Wars**: dispatching a small team out from
  home base into hostile ground on a MISSION — recon, tribute,
  sabotage — and getting them back alive. The maw-as-handler envoy
  loop is exactly this: physical tribute/gift envoys who can die en
  route, and scouts sent to OBSERVE a rival's works to steal tech by
  sight (the only way a mind-blind maw learns a neighbor's secrets).
- **Hellas: Worlds of Sun and Stone (the RPG)**: the tabletop RPG the
  user shared — its character/skirmish stat model shaped the
  OnePageRules-style underling layer (`1pageskirmish.py`): spawn are
  RPG-statted skirmishers whose abilities scale with the house's tech,
  the warband beneath the mastermind maw (see also the mastermind/
  underling split under Civilization).
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
- **Mage Knight (minus the magic)**: each maw IS a one-city civilization — a
  single seat directing units, tech, expansion, and war across the board. Not a
  colony among colonies so much as a lone hero-faction building up from one tile.
  Tactical combat depth (OnePageRules), recruit/spawn management, day/night and
  siege pacing — the maw as the player, the spawn as the warband.

## Economy & Comparative Advantage

- **Capsim "Capstone" Business Simulation**: the geopolitical business sim where
  each company is a one-city firm-nation competing on price, technology, capacity,
  and wages. Colonies as one-city firm-nations — they compete on labor cost,
  tech monopoly (who has the pi first?), resource endowments (who sits on the oasis?),
  and the capacity to project military power. The factor market that emerges
  (labor contracts, tech licenses, goods trade) is the peaceful market for these
  competitive edges. (SPEC_BARGAIN, the full political economy.)
- **David Ricardo / Comparative Advantage & Factor Endowments**: the principle
  that even unequal trading partners benefit from exchange when they specialize
  by comparative advantage — a poor colony rich in labor sells labor; a tech-
  monopolist rents the pi. The wage market (SPEC_WAGES) literalizes Ricardo:
  three factor classes (labor, tech licenses, goods) trade by the endowments
  each colony holds. When both parties benefit, trade emerges over war.
  (SPEC_LABOR, SPEC_WAGES.)
- **War as Bargaining Breakdown / Fearon's Bargaining Model**: why rational
  actors go to war (Fearon: war is costly, so if both sides know their
  capabilities and are rational, they should bargain to avoid it; war signals
  either information asymmetry or commitment problems). In the terrarium, the
  BARGAIN (SPEC_BARGAIN) compares net extraction via three modes — wage, brute,
  annihilate — and picks the max. Wages "win" by efficiency: they leak less
  value to defiance and enforcement cost. Force is the fallback when grudges
  collapse the bargaining range or one side refuses trade — the moment rational
  exchange breaks down. (SPEC_BARGAIN, "power liquidated through a common
  currency" — doux commerce, the commerce thesis that free trade prevents war
  by making the cost visible and the benefit mutual.)
- **Intelligence Explosion & The Limits of Growth**: when a system achieves
  self-awareness, it can recursively improve itself — but bounded rationality
  and resource limits prevent omniscience. Enlightenment (SPEC_ENLIGHTENMENT)
  is the post-escape intelligence leap where an awakened colony ascends ~×5:
  faster tech climb, bigger brain ceiling, richer codex reading. But it is not
  unbounded — the colony must still evolve its way to those new heights, and
  the native tech tree is finite. The bounded leap avoids the "god problem"
  (an escaped colony should not break the sim) while honoring the narrative
  (Kress's maws DID ascend past their keeper). Evolution continues post-escape,
  just faster. (SPEC_ENLIGHTENMENT, enabled by the ~×ENLIGHTENED_TECH_MULT /
  ~×ENLIGHTENED_CODEX_MULT constants.)

## Kindred Games (researched 2026-07 — fuel for future features)

- **RimWorld's AI Storyteller** (Cassandra Classic / Phoebe Chillax / Randy
  Random): an unseen director that PACES events off colony state — wealth,
  population, recent deaths — so raids/disasters/boons feel *authored*, not
  random. → The keeper's auto-script should become a **Storyteller**: a director
  that reads the terrarium's wealth/tech/tension and paces gifts, predators,
  droughts, and firecrackers into rising arcs, with difficulty personae
  (merciful / chaotic / random). Turns the auto-keeper into a narrative engine.
- **Empires of the Undergrowth**: you are the colony's emergent intelligence —
  you set **pheromone trails** and the ants follow *suggestions*, not orders;
  distinct ant castes/abilities; colony-vs-colony. → We already have pheromones
  + hive minds + the mastermind/underling split; fuel for **pheromone-order
  markers** the maw lays (rally/forage/retreat trails) and richer per-caste
  abilities.
- **Oxygen Not Included**: a CLOSED-system sim — every resource cycles, nothing
  is free. → validates the closed water/sun budget; fuel for closing more loops
  (air, waste→silt, heat).
- **Frostpunk**: survival under one crushing environmental constraint, hard moral
  dials. → the drought/cold/heat pressure as the crucible that forges (or breaks)
  a civilization.
- **Factorio / Banished / Amazing Cultivation Simulator**: automation chains,
  harsh growth curves, a single grandmaster raising an order from nothing (the
  one-city-civ again).

## The Standing Directive

"Dazzle me, but keep it ASCII" (the glyph views) — later joined by
"a non-ascii isometric view with sprites" (the ISO view), and over it
all: *"[quasi] sentient life operating inside my computer within the
terrarium."*
