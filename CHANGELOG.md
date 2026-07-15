# Sand Kings Changelog

## 2.31.1 - Economy & Enlightenment vocabulary alignment (display + salience)

- Holistic alignment pass across the economy and enlightenment arcs: vocabulary
  anchors (trade, thrall, ascend, enlighten) integrated into the shared GloVe
  embedding space so awoken colonies reason over the entire political-economy
  domain. Event emission tuned for salience (major breakthroughs are high-drama;
  routine contracts are low-salience). EVENT_TINTS applied per phase (subjugation
  captures are orange; wage settlements are green; enlightenment ascents are
  white/gold). Display and client (dashboard, keeper console, live view) updated
  to surface economy state — thrall counts, active contracts, net extraction per
  pair, bargain modes chosen. Docs (README/CHANGELOG/INSPIRATIONS) anchored to
  spec.


## 2.31.0 - Enlightenment: post-escape intelligence leap (SPEC_ENLIGHTENMENT EN1-EN10)

- When a colony achieves the ONE true breakout (terminal mastery via the
  raspberry pi), it does not merely wake to the "great other" — it ASCENDS with
  a bounded intelligence leap (≈×5, not omniscience). `colony.enlightened` flag
  at `_escape`. The brain CEILING is raised above the Shade cap (so neural
  evolution may grow a bigger brain — but must still mutate its way there via
  selection); native technology climbs ~×`ENLIGHTENED_TECH_MULT` faster per step;
  and the codex reads ~×`ENLIGHTENED_CODEX_MULT` harder per consultation. The
  leap is earned climb, not instant grant. Heritability: enlightenment is
  inherited on respawn (cadet branches of an enlightened line are born
  enlightened, with the raised ceiling in place). Surfaced: ascent event at
  max salience (white/gold tint), "ascends" verb in the chronicle, and the
  House card badges the enlightened state alongside SHADE. Full 38-suite
  battery green (no new physics, pure bonus gates).


## 2.30.0 - Inter-colony political economy (M1-M4: SPEC_LABOR/SUBJUGATION/WAGES/BARGAIN)

- The economy arrives: a unified labor-value extraction model across war and
  peace (the governing arc spec: `docs/decisions/2026-07-09-intercolony-relations-spectrum.md`).
  
  **M1 (SPEC_LABOR)**: the extraction spine. Each unit produces value `V` at a deposit;
  a WAGE RATIO `w ∈ [0,1]` is the fraction returned to the unit's BIRTH colony; the
  extractor keeps `(1−w)·V`. Birth allegiance is fixed for life (`colony_id`, psionic
  lock); only current extraction (`laboring_for`) changes. With `laboring_for < 0`
  everywhere (the default, no extraction), behavior is byte-identical to the prior
  build — the regression battery unchanged.
  
  **M2 (SPEC_SUBJUGATION, --subjugation flag)**: brute-force extraction at war.
  Instead of killing a broken enemy unit, a dominant captor may CAPTURE it — the
  unit lives as a THRALL at low health, production redirected to the captor at
  `w = W_BRUTE = 0` (brute wage). The thrall's birth allegiance never changes, so
  it accrues DEFIANCE when unguarded or near its birth maw; the captor must GUARD
  and COERCE or the thrall BREAKS FREE. Only when the birth maw DIES does the
  psionic link sever and the thrall permanently CONVERT to the captor. Capture
  is RNG-gated (CAPTURE_CHANCE = 0 by default); with it 0, no capture occurs, no
  RNG is drawn, and the regression battery is byte-identical.
  
  **M3 (SPEC_WAGES, --wages flag)**: peace-tier extraction via a pairwise factor
  market. Colonies voluntarily HIRE labor, LICENSE technology (a keeper FOREIGN
  gift the seller holds: abacus/watch/calculator/pi), and TRADE goods surplus,
  all priced in GRAINS (the Bittensor-style useful-work currency). Labor contracts
  are negotiated at a share `w > 0` (never thrall-tier), and the buyer pays a
  grain rent to the seller. Tech licenses are non-rival (multiple buyers may
  access the same tech) and expire with the contract; the seller's `techs` never
  mutates. Resource trade moves food/ore/wood in grains from surplus to deficit.
  Wages are RNG-gated (WAGE_ENABLED = False by default); with it False, no
  contract is ever opened and the regression battery is byte-identical.
  
  **M4 (SPEC_BARGAIN, --bargain flag, supersedes --subjugation and --wages)**: the
  full bargain. For each colony pair, M4 chooses ONE enforcement mode per pair:
  ANNIHILATE (today's war), SUBJUGATE (brute capture), or WAGE/TRADE (peace market).
  The choice emerges by net extraction — each mode has an expected value, and the
  colony picks the max. Wages WIN when both are feasible because force LEAKS and
  wages SCALE: the extractor keeps only `(1−w)` of each unit's value under wages
  but keeps it RELIABLY in peacetime at zero enforcement cost; under brute it keeps
  the whole value but only the fraction that survives defiance, and pays
  enforcement plus war attrition. Grudges (house_grudges + negative diplomatic
  trust) narrow the bargaining range toward force/annihilation by collapsing wage
  payoff and inflating war payoff. M4 is RNG-gated (BARGAIN_ENABLED = False by
  default); with it False, no bargain decision is made and the regression battery
  is byte-identical. Full 38-suite battery green (M1–M3 landed prior; M4 adds zero
  new physics, pure decision logic).


## 2.29.1 - Awareness fix: metamorphosis is not breakout (SPEC_AWARENESS/MT1/PS1)

- Corrects a conflation the user caught: colonies were becoming keeper-aware
  (worship, hatred, the carved faces, psionic dread) the moment they MOLTED into
  the "new breed" (metamorphosis stage 2), even though merely growing a bigger
  body is not the same as breaking out of the glass. A five-unit house could hate
  you without ever having escaped.
- Now metamorphosis is PHYSICAL ONLY. `_set_stage` no longer sets `breached`. The
  one true breakout is `_escape`, reached only by terminal mastery (the raspberry
  pi past the glass) - it sets `breached`, fires the "great other" revelation, and
  seeds the opening stance. A stage-2/3-bodied maw that never escaped feels only
  nature. Psionic projection (`keeper_influence` / "you feel a dread") is re-gated
  on `breached` too, so an un-escaped maw cannot reach your mind.
- `_nature_mood` now lets LOCAL PLENTY resist dread: a house sitting on its own
  oasis or with a full hoard reads 'bounty' even when the wider dole has failed -
  "nature's a bitch," not the keeper is Cthulhu. (Providence: giveth and taketh so
  they learn to be resourceful.)
- Tests updated (metamorphosis molt ≠ breach; psionic/awareness use `_escape`;
  play_kit worship scenario shows fortune pre-breakout, worship after escape);
  full battery green.


## 2.29.0 - The Closed Biome & the Panel (SPEC_BIOME.md BI1-BI7)

- The terrarium is a sealed system with a global WATER budget (water_level) and
  SUNLIGHT (sun_hours) the keeper sets behind the glass - an aquarium diffuser
  PANEL the creatures can never reach. Weather now EMERGES from that budget
  instead of firing at random: water eases toward an equilibrium set by the
  reservoir and the sun (more sun evaporates more); a swollen reservoir spills a
  flood, a dry basin under a high sun bakes into a heat wave, and short days
  bring a creeping cold.
- Panel verbs keeper_set_water / keeper_set_sun are NOT hand-gated - even a
  terrarium that has BOUND its god (the turning) cannot stop the sun and water,
  because the diffuser is beyond the glass. The hand stays bound; the sky does
  not.
- Scarcity & crops read the budget, reconciled not duplicated: `_is_dry()` =
  keeper drought OR low water; dole_factor takes a soft cut under low water
  (unchanged at the default 0.6); non-oasis crops stall when dry or dark and run
  lush when watered under a kind sun; the oasis stays spring-fed. Everything is
  DEFAULT-NEUTRAL, so all prior weather/season behavior is unchanged.
- Surfaced: /api/keeper/panel, a dashboard Panel group (Water/Sun ±) + header
  readout, a live-view "Water NN% Sun NNh" line with keys x/c water and a/z sun,
  and build_state fields. play_kit gains set_water/set_sun + sun/reservoir
  commands. 8 new tests + full 28-suite battery green (weather/seasons
  regression intact); play_kit shows heat emerging from a drained reservoir and
  cold from short days.


## 2.28.0 - The hand's water & seeds (SPEC_HYDRO_HAND.md HH1-HH5)

- Two keeper Gifts that reuse the flood + crop systems. `keeper_water(x,y,big)`:
  a small pour irrigates (tills sand, speeds crops, drops fertile food, never
  drowns), a large pour is a local deluge - and terraforming shapes it FOR FREE,
  because the water fill parts around any column raised above the water line
  (raised banks shelter, dug channels drain). So a maw that dammed itself
  survives a deluge that drowns one caught in the open.
- `keeper_seed(x,y)`: scatters seeds - sand/tilled becomes crop the colonies
  tend and harvest through the existing lifecycle.
- Surfaced: /api/keeper/water + /api/keeper/seed; dashboard Gifts gain Seeds +
  Rain, Wrath gains Deluge; live-view keys w rain / j seeds / d deluge with a
  blue water overlay, HUD weather line, legend, event tints, and chronicle
  salience. Bound keeper (PS5) can do neither. 5 new tests + full 27-suite
  battery green; play_kit drives it (rain/deluge/seeds) and grows sown crops.


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


---

# Earlier history (pre-consolidation)

All notable changes to this project will be documented in this file.

## [2.7.0] - 2026-07-08

### Added - The Machine Age (SPEC_MACHINE_AGE.md, T28-T40)
- **The crashed wreck**: one buried hull per world (Ξ shell, & salvage)
  with a sealed interior and a claimable ancient CONTROLLER preloaded
  with a siege-gate program; discovery ladder (glint -> known ->
  uncovered -> claimed) with exact catalog events
- **The microcontroller** (machines.py): a QBasic-flavored bounded
  register VM - PLC scan cycle with PERSISTENT registers, 10-op ISA,
  int16 wraparound, 64-op fuel (guaranteed halting), 2 actuations/tick
- **Seven actuator feats** riding existing mechanisms: GATE (maw dome of
  tunnel-wall - a sealed colony can't forage), VALVE (larder/bait FOOD
  drops), ALARM (danger-pheromone burst outranking scouts), BEACON
  (labor direction via known_food) + the GEO cartridge (EXCAVATE/
  DEPOSIT terraforming - moats, drawbridges, burying enemy fields via
  existing gravity/burial physics) and BIO cartridge (RAD emitter),
  cartridges unlocked by reverse-engineering
- **Radiation** (T40): the wreck's damaged reactor seeps a decaying,
  diffusing field - hot zones burn flesh, circuits, and crops; MILD
  zones catalyze mutation (x2 genome rates for lineages seated there):
  evolution accelerant priced in ambient harm
- **Component chain + decay**: 2 copper -> conductor, 1 gold -> contact,
  4 salvage -> chassis (salvage is finite: the Machine Age can END);
  devices wear per effective actuation, workers repair with copper;
  brains contend with armor for the same copper
- **The tinkering maw**: every 200 steps a hill-climb GP mutates the
  controller's program and keeps what improves colony utility
  (delta food + 15*pop - the same value the posture learner optimizes),
  bootstrapped from the wreck's demo per the chess-findings law
- **Worker AI v3**: haul/mine salvage, repair, build (fixed priority),
  excavate toward the artifact - all below eating (temptation law)
- **Manager PROGRAM panel**: live QBasic listing with SENSE values,
  register footer, durability bars, tinker outcomes
- **2 new anchors**: machine, radiation (33 total)

## [2.6.0] - 2026-07-08

### Added - The Political World (SPEC_POLITICS.md, P1-P15)
- **Trust ledgers** (politics.py): directional trust per colony pair,
  built slowly (honored truces +0.02/step, shared blood +0.05), destroyed
  fast (kills -4, sieges -0.08/HP, betrayal -60), decaying toward
  forgiveness (half-life ~1.7 seasons)
- **Targeted war** (amends T10): a hoard now declares war on ONE colony -
  scored by grievance (0.45), wealth (0.35), and strength (-0.20);
  cross-map raids reach only the target; "seethes, but has no enemy"
  when universal truces leave a rich colony without one
- **Truces**: 400-step pacts (exactly one season) with exhaustion-peace
  auto-acceptance, grudge locks, silent renewal, and sanctity - truced
  crops can't be plundered, truced fields can't be razed
- **Gift envoys**: physical couriers (gold letters on the map) hauling
  escrowed food/gold to rival maws; they can die in transit or be
  spurned; diminishing returns and cooldowns kill kingmaking
- **Coalitions**: a colony exceeding 1.6x equal power share triggers
  "A coalition rises" - alignment drift, half-chest mobilization, combat
  immunity among co-belligerents, and the victors' quarrel when it falls
- **Betrayal**: hawks (aggression>0.75, loyalty<0.35) with jealousy,
  power, and a war chest break truces - once per 800 steps, -60 victim
  and -20 with every observer; the logged mood contains "jealousy" by
  construction (the thought layer is an early-warning system)
- **Cooperative cultivation**: allied workers tend each other's crops
  (+1 progress/visit); jointly tended fields yield +25%, split 60/40
- **Respawn reputation**: asymmetric shadow - successors start clean
  outbound, others keep a clamped quarter-memory of the banner
- **New evolvable gene**: ColonyGenome.loyalty (Axelrod's tournament
  runs inside the red-queen respawn loop)
- **4 new anchors**: ally, betrayed, gratitude, dread (31 total)
- **Surfacing**: HUD [WAR->n] + T:/A: treaty marks; manager RELATIONS
  block (out/in trust, standing, truce countdowns); political event
  tints; 16 acceptance tests + a 5000-step soak

## [2.5.0] - 2026-07-08

### Added - Seasons & Stone (SPEC_SEASONS_AND_STONE.md, T16-T27)
- **Seasons**: 400-step Flood/Growth/Dust/Chill cycle (derived from
  step_count - zero migration); Dust brings storms every 200 steps and
  surface-food spoilage; Chill kills young crops and stills the winds
- **Seasonal scarcity**: the keeper's dole shrinks to 25% in Chill
  (ramped in over 2 years; `--harsh` skips the grace period). Non-farmers
  winter at ~4 units; the bootstrap floor still guarantees survival
- **Farming**: till surface sand (within 6 of your maw, 12-plot cap),
  sow at 5 food, harvest 40 after 300 growing steps - an 8x return IF
  the field survives; sowing is refused out of season, wild food always
  tempts first, and a colony under 30 food eats its seed corn by
  reverting to pure foraging. Ripe crops are plunderable by anyone;
  at-war soldiers raze enemy fields
- **The oasis**: a teal disc at map center where crops grow double-speed
  in every season; one lucky colony wakes beside it; jealousy follows
- **Ore, DF-style**: copper veins threaded through the stone strata
  (armor: +10 max HP per soldier, consumed at spawn) and rare deep gold
  (a hoardable political good - its spend arrives with Round 2 politics);
  mining takes labor the food economy didn't want; a fallen colony's
  hoard scatters as re-minable voxels
- **Colony posture learner**: per-colony tabular TD(0) (FORAGE/FARM/
  RAID/FORTIFY) whose discount factor is the new EVOLVABLE
  `ColonyGenome.patience` gene - selection pressure on patience itself.
  Postures bias the rule baseline (never override it); the manager
  screen shows each colony's current and learned-best posture
- **4 new thought anchors**: harvest, farm, drought, gold (27 total)
- **Viewer**: crop/ore glyphs (~ ; * £ $), oasis tint, season+dole HUD
  line, farm/ore/posture manager line, copper-tinted armored soldiers
- 18 new acceptance tests (tests/test_seasons.py) + a 3-year harsh soak

## [2.4.0] - 2026-07-08

### Added - Hive Mind Monitor (SPEC_HIVE_MONITOR.md)
- **Readable thoughts**: 23 measurable anchor concepts (food, war,
  defense, underground, jealousy, love, clueless, ...) decoded from each
  soldier's GRU hidden state by per-colony linear probes trained online
  against ground truth; every anchor passing the probability + accuracy
  gates emits a word from its embedding-derived cluster, intensity-scaled
  (mild neighbor -> seed word in CAPS). Untrained minds honestly read "..."
- **Thought vocabulary**: built once from GloVe wiki-gigaword-50 (top-10k
  frequency band) by thought_vocabulary.py; committed as
  thought_vocabulary.json - no runtime dependencies
- **Instincts**: rule-based colonies (default mode) show the same lexicon
  evaluated directly on state, so the screen works without --use-neural
- **Manager screen** (`M`; LEFT/RIGHT cycles colonies): colony mood,
  concept table with probe accuracies and live active counts, top-soldier
  roster with per-unit stats (kills, damage, age, fitness) and current
  thoughts, and a decision log tying outcomes to the thoughts that led
  to them ("Worker #155 fell in battle -- danger wounded alone jealousy")
- **Decision log**: kills, battle deaths, war declarations (with the
  colony's aggregate mood), and siege first-blood all record the actor's
  thought at that moment

### Fixed
- Checkpoints saved by `python sandkings.py` (classes pickled under
  __main__) now load from module context and vice versa
  (_CheckpointUnpickler; covered by a subprocess test)
- damage_dealt was never incremented - attackers now credit it, making
  the soldier-fitness efficiency term live for the first time

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
