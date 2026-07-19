# ALife Harvest — what to take for SandKings (and what to leave)

Curated from Framsticks (history.xml + the `framspy/evolalg` checkout, read in full) and the wider ALife field
(Karl Sims EVC, Evolution Gym, The Bibites, biosim4, Polyworld, Lenia, ALIEN, Spore, Thrive). "Take what works,
leave the rest."

## The filter (why some sources don't transfer)

SandKings' axis is **fixed-body neuroevolution inside an ecosystem**: the voxel colony/units are the body (not
evolved); what evolves is the **maw brain** (frozen Kanerva SDM + evolvable readout, `brain_hidden`/`read_reach`
breathing) under a **fitness-tournament GA** (`FITNESS_SELECTION_ENABLED`), amid food/war/weather/fauna/the Tongue.

- **LEAVE — body+brain morphology evolution:** Karl Sims EVC, Evolution Gym, Robogen, VoxCAD. Their whole point is
  evolving the *shape*; our body is fixed voxel colonies. (The one echo we already have: colonies evolve dug
  structures/affordances — that's our "morphology," and it's enough.)
- **LEAVE — paradigm mismatches:** Lenia (continuous CA, no genomes), ALIEN (GPU particle chemistry), Spore
  (cosmetic, not real evolution). NEAT *topology* mutation (Bibites) conflicts with our design law (never mutate the
  pickled/frozen net — only the readout evolves), so take NEAT's *speciation* idea, not its topology growth.

## TAKE — ranked by leverage for "is anything actually evolving / waking up?"

| # | Harvest | Source | Maps onto | Leverage |
|---|---------|--------|-----------|----------|
| 1 | **Novelty search & niching** — `fitness = dissimilarity` (novelty) or `rawfitness × mean_dissimilarity` (niching); reward colonies for being FIT *and* DIFFERENT so the population stops collapsing onto one brain | Framsticks `experiment_niching_abc.py` (in hand) | the `FITNESS_SELECTION` reseed tournament | **Highest** — directly attacks convergence, the thing that makes a sim look "dead." Needs a colony *behavior descriptor* + dissimilarity (below). |
| 2 | **Novelty archive + Hall of Fame reseed** — keep an archive of the most novel/fit ancestors; reseed a fallen house partly from the archive, not only the current best | Framsticks `hall_of_fame.py`, archive in niching | `_respawn_colony` fitness reseed | High — preserves lost innovation; a dead lineage's ideas can return. Small, self-contained. |
| 3 | **Behavior descriptor + dissimilarity measure** — a small vector per colony (aggression, food strategy, tech breadth, territory, `read_reach`, `brain_hidden`, affordance mix) and a distance over it | Framsticks `DissimMethod`, `dissimilarity/` | prerequisite for #1/#2; also a saga metric | High — it's the enabling primitive, and it doubles as an observability signal. |
| 4 | **Lineage / phylogeny + diversity curve** — track house genealogy, per-generation genetic diversity, and a neural-complexity metric; plot it | Framsticks phylo trees; biosim4 diversity log; Polyworld "Complexity" | the saga/story log + web dashboard | High *narrative* value — turns "have they reached sentience?" into a **measurable curve** you can watch, not a vibe. Pure observability, no gameplay risk. |
| 5 | **Island / deme model + migration** — semi-isolated regional subpopulations that evolve apart, with periodic migration events | Framsticks `experiment_islands_model_abc.py` (in hand); Thrive patch-map | the world is already spatial → treat regions as demes | Medium — boosts diversity structurally; more involved (regional bookkeeping). |
| 6 | **Speciation / reproductive isolation** — houses as protected "species": mates/reseeds prefer genetic kin, shielding young innovations from being averaged away | The Bibites (NEAT speciation) | genome compatibility in reseed/crossover | Medium — complements #1; guards novelty long enough to mature. |
| 7 | **Aging → rising metabolism (senescence)** + assimilation/idle-metabolism economy | Framsticks energy model | maw upkeep / food economy | Medium — an old, sprawling house pays more to exist → turnover pressure, a natural clock. |
| 8 | **Environmental selection challenge** — a per-epoch survival criterion the world imposes (e.g. "only those who stockpiled / held territory / crossed the Chill seed the next cohort") | biosim4 per-generation spatial criterion | already partly in scarcity-war/winter; make it an explicit selection gate | Medium — sharpens what selection actually rewards. |

## Recommended next build (smallest high-leverage slice)

**#3 → #1 → #4 as one arc:** add a per-colony **behavior descriptor** + dissimilarity, wire a **novelty/niching
term** into the existing fitness-tournament reseed (baseline-on, gated so the battery stays byte-identical), and
surface the **diversity/complexity curve** in the saga + dashboard. That is the Framsticks core, it's the highest
leverage against convergence, the code pattern is already sitting in `framspy/evolalg`, and #4 gives you the
live readout to actually *see* whether diversity is climbing or flat-lining.

Leave #5–#8 as a backlog; pick up island-model or senescence only if the diversity curve says the single
population is still collapsing after #1.

## Notes
- `framspy/` (svn) and `neopets/` are reference checkouts only — now gitignored, never committed. The Neopets repo
  itself is just a name/image API wrapper (no game mechanics); its only value is the *pet-care concept*
  (hunger/mood/health/disease/currency), which we already cover via food/madness/economy — nothing to take.
- Everything here is harvest/design, not yet built. The diversity work is spec-worthy (SPEC_NOVELTY) before code.
