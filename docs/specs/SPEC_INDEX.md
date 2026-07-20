# SPEC Index — the Sand Kings terrarium

Catalog of every `SPEC_*.md` in the repo, grouped by arc, one line each. The
spec is the source of truth for design-before-build (see the spec-driven-dev
contract). Governing decision records live under `docs/decisions/`.

## Ecology & world (the closed terrarium)
- **SPEC_TERRARIUM_LIVENESS.md** — feeding, foraging, maw combat, respawn, strata terrain (the base sim).
- **SPEC_BIOME.md** (BI1–BI7) — the closed biome & the panel (Phase 3): the sealed world and its glass.
- **SPEC_SEASONS_AND_STONE.md** — seasons, scarcity, farming, the oasis, ore, colony learning.
- **SPEC_WEATHER.md** (W1–W6) — desert weather: storm, hail, cold, flood.
- **SPEC_STORY_LOG.md** (SL1–SL3) — per-turn JSONL game chronicle (`--log`) + an optional, fail-soft local-LLM saga (`--summarize-every` via Ollama qwen). Opt-in, byte-identical off.
- **SPEC_FLOOD_REFUGEE.md** (FR1–FR4, DRAFT) — water's double edge: irrigated crops immune to heat swells (FR1), the flood-refugee state (cut off from tunnels → surface-forage) (FR2), overthrow of the devastated (FR3), and ICE — a hard freeze turns a defensive moat/lake into a walkable bridge, the winter assault opportunity (FR4). Catalogs the already-emergent flood/irrigation mechanics; specs the four gaps.
- **SPEC_SEMIPERMEABLE.md** (SP1–SP8) — semi-permeable params: a reusable soft-param primitive (distributional scalar `jitter` + logistic `soft_gate`) with the daylight tracer (`sun_effective` drawn per biome-day); identity at neutral (`SUN_JITTER_SD=0`).
- **SPEC_TIMBER_AND_FLAME.md** — timber, bone & flame: fortifications, organic weapons, decay, fire.
- **SPEC_HYDRO_HAND.md** (HH1–HH5) — the hand's water & seeds (Phase 2 / Hydro-Hand).
- **SPEC_ARENA.md** (AR1–AR7) — arena mode: the keeper's gifts, wrath, and neutrals.
- **SPEC_FAUNA_ECOLOGY.md** (FE1–FE3) — a world alive: visible fish/boats, new fauna (beetle/guppy), and an overgrown shoal that turns predatory.
- **SPEC_DOMESTICATION.md** (DM1–DM2c; DM3/DM4 deferred) — taming wild beasts: danger-scaled ownership, friend-or-foe; upkeep + labor/war/livestock roles to come.
- **SPEC_FOOD_WEB.md** — the weather-rotated RPS ecosystem: three harvestable guilds (guppies/crickets/fauna) whose abundance rotates with the seasons so no food is ever best.
- **SPEC_GUPPIES.md** — the oasis pond ecosystem: algae-grazing guppies, catchable food, overgrowth turns predatory.
- **SPEC_FLORA.md** — forageable flora: fishing + perennial berry shrubs as reliable early food.
- **SPEC_WINTER.md** — seasonal planning: winter bites, the maw learns to hoard ahead of the Chill.
- **SPEC_INCURSION.md** — invaders manifest inside the sealed terrarium and never leave.
- **SPEC_MITE_STORM.md** — a contagious infestation: mites get under the skin and spread host-to-host; quarantine/cure/cull triage. Increment 1 shipped.

## The keeper & the great other (god layer)
- **SPEC_KEEPER.md** (K1–K7) — the keeper: the hand that feeds, the gift ladder, the terminal.
- **SPEC_FACES.md** (F1–F5) — "look to your faces": carved sentiment glyphs / nature moods.
- **SPEC_AWARENESS.md** (AW1–AW6) — nature until the great other: keeper-directed feeling gates on `breached` (the `_escape` breakout).
- **SPEC_BREAKOUT.md** (BRK-A/B/C) — making the breakout reachable, visible & grantable: opens VM actuator port 7 so organic breach is possible (root fix), a per-colony breakout-proximity gauge (`breakout_progress`), and the keeper `open_door` action (`_escape` by fiat) across all three clients.
- **SPEC_DISPOSITION.md** (DP1–DP12) — keeper-treatment → disposition: signed `favoritism` + boldness `confidence` + short-term `agitation`; modulates aggression, nudges `keeper_sentiment`, biases the bargain (default-neutral at neutral values).
- **SPEC_PSIONIC.md** (PS1–PS6) — the psionic maw & keeper-as-prey: the awakened reach back.
- **SPEC_REVELATION.md** (R1–R4) — revelation & the priesthood: signs beyond the glass, per-house literacy, mad prophets & soothsayers, Aztec sacrifice, holy war. Shipped.

## Mind, growth & sentience
- **SPEC_SENTIENCE.md** (S1–S6) — the sentience arc: resonance, meta-learning.
- **SPEC_METAMORPHOSIS.md** (MT1–MT6) — the three physical stages (insectoid → new breed → Shade), size × cruelty.
- **SPEC_ENLIGHTENMENT.md** (EN1–EN10) — the post-escape intelligence leap: raised brain ceiling, faster tech/codex climb (hangs off `_escape`).
- **SPEC_HIVE_MONITOR.md** (M1–M15) — concept probes, thoughts, the manager screen, and the 42-anchor lexicon.
- **SPEC_NEURAL_ACTIVATION_TRACKING.md** — the neural hive: activation tracking, pruning, folding, soldier memory.
- **SPEC_EVOLUTION.md** (EV1–EV6) — the evolving engine: genome mutation, selection, respawn bloodlines.
- **SPEC_AUGMENTS.md** (AUG1–AUG5) — earned KV-cache memory augments (awakened only).
- **SPEC_SKIRMISH_COMBAT.md** (I1–I2b) — learned antenna-frequency kin-recognition combat + Spartan self-culling; Boltzmann strike over a heritable genetic instinct. I1+I2 shipped, baseline-ON.
- **SPEC_COMPREHENSION_RL.md** — the Tongue catalyzes the maw's survival objective (comprehension → farm/cooperate/economize → technology). I1+I2(reduced) shipped, baseline-ON.
- **SPEC_LONGEVITY_FITNESS.md** — online longevity fitness via eligibility traces + two-tier survival objective + feature-lift measurement; recasts the PEFT stack as actor-critic. DESIGNED, not yet built (L1→L3).
- **SPEC_NEAT.md** — NEAT evolves the readout adapter's connectivity topology, RL learns the weights. Increment 1 shipped, baseline-ON; Increment 2 (add_node / speciation) pending.
- **SPEC_JLENS.md** — the colony J-lens: read (and steer) a colony's unspoken thoughts. Shipped, baseline-ON.
- **SPEC_BREATH.md** — the breathing net: evolvable capacity as a floating, semi-permeable, log-scaled, annealed quantity. Shipped, baseline-ON.
- **SPEC_SELECTION.md** — Evolution Proper Phase 1: a fitness-weighted tournament seeds each new arrival (survival of the fittest). Shipped, baseline-ON.
- **SPEC_AFFORDANCES.md** (AF1–AF5) — Evolution Proper Phase 2: heritable behavioral repertoire (scorched-earth/granaries/livestock as genome-liability affordances). Shipped, baseline-ON.

## Vocabulary & language (the shared embedding space)
- **SPEC_CODEX.md** (CX1–CX7) — the read-only corpus; a colony reads a LESSON that nudges its dispositions (incl. `commerce`/`enlightenment`).
- **SPEC_DIALOGUE.md** (DL1–DL7) — human ↔ awakened-colony conversation over the shared GloVe anchors (incl. the economy vocabulary).
- **SPEC_TONGUE.md** (TG1–TG9) — the Tongue: masked-prediction comprehension of language + world, plus a two-way keeper dialogue. Shipped, baseline-ON.
- **SPEC_FOL_TONGUE.md** — the FOL Tongue: communication as subject–predicate–object triplets + logic qualifiers. Increment 1 shipped; Increment 2 (quantifiers ∀/∃/∧/∨) pending.
- **SPEC_ENSEMBLE_EMBED.md** — ensemble embeddings for the Tongue: a learned universal-geometry mixture (6-model, relative-representation aligned).
- **SPEC_VOCAB_EXTEND.md** — extending the represented vocabulary: growing the anchors' concept cloud.

## Technology & machines
- **SPEC_TECH.md** (TE1–TE13) — foreign (keeper-gift) vs native tech: acquisition, bonuses, the tree, diffusion, crafting.
- **SPEC_MACHINE_AGE.md** — wrecks, the microcontroller VM, devices, the tinkerer.
- **SPEC_TOOLS.md** (TL1–TL6) — tools & telemetry: the Dwarf-Therapist feed + the pre-wrapped regression/predict tool.

## Economy — the inter-colony political economy
Governing scope record: `docs/decisions/2026-07-09-intercolony-relations-spectrum.md`
(the unified wage/force labor-extraction model). Build order M1 → (M2 ‖ M3) → M4.
- **SPEC_CURRENCY.md** (CU1–CU5) — grains: the useful-work (Bittensor-style) currency; the economy's transferable medium.
- **SPEC_LABOR.md** (M1, LV1–LV7) — labor-value & the extractor's surplus: the `_credit_labor` split spine + `composite_power`.
- **SPEC_SUBJUGATION.md** (M2, SJ1–SJ8) — the BRUTE tier: capture, coercion, defiance, conversion (`w = W_BRUTE`).
- **SPEC_WAGES.md** (M3, WG1–WG13) — the WAGE tier: the pairwise factor market (labor / license / goods), priced in grains.
- **SPEC_BARGAIN.md** (M4, BG1–BG12) — mode selection by net extraction: annihilate / subjugate / wage, per pair (wages win when force leaks).

## Politics, houses & history
- **SPEC_POLITICS.md** — the political world: trust, gifts, truces, coalitions, betrayal.
- **SPEC_SCARCITY_WAR.md** (SW1–SW3) — dog-eat-dog: the starving raid to eat, plunder moves food, the fallen are cannibalized.
- **SPEC_SUZERAIN.md** (SZ1–SZ4) — the Aztec/Cortés new order: a power imposes tributary vassalage, a Pax stills vassal wars, tribute + revolt.
- **SPEC_REPRESSION.md** (RR1–RR4) — the two-sided order: vassal sabotage vs the overlord's iron fist, krypteia memory, emergent turnover.
- **SPEC_DIFFUSE_RESISTANCE.md** (WW1–WW3) — wage vs whip: an aggressive overlord rules by the whip (fast revolt), a peaceable one by the wage (durable, foot-dragged); the wage outlasts the whip.
- **SPEC_DYNASTIES.md** (D1–D12) — dynasties & the salience-scored chronicle; house names, epithets, saga.
- **SPEC_CANON_HOUSES.md** (CH1–CH4) — the canonical houses (Round B / Canon).
- **SPEC_MADNESS.md** (MAD-1–MAD-6) — madness & extinction: a house can go extinct (fresh unrelated house at respawn, name kept as a disgraced gravestone) via the `colony.madness` sustained-neglect accumulator (shameful "the Mad") or conflict (honorable, deferred); extinction changes only the respawn IDENTITY — the T5/T6 slot-refill liveness spine is untouched.
- **SPEC_POPULATION.md** (POP-1–POP-4) — dynamic population & succession, **Phase 0** (inert scaffolding): a fixed pool of `MAX_COLONIES=8` slots each carrying a lifecycle `pop_state` (ACTIVE/SUCCESSION/DORMANT, inert at flag-off), the default-off `dynamic_population` flag (byte-identical to today), and the slot-scrub choke point `_deactivate_slot(cid)` (defined + tested, unwired) that centralizes all stale per-colony teardown (pheromones/ownership/politics/thralls/gifts/disposition). Emergent 2..8 population is later phases. NOTE: its governing decision record `docs/decisions/2026-07-11-dynamic-population-and-succession.md` is not yet committed. STATUS UPDATE (2026-07-20): shipped through Phase 6, baseline-ON in the live game (entrypoint constructs `dynamic_population=True`); battery stays byte-identical at the module default.
- **SPEC_SCARCITY_WAR.md** already listed above; the war train continues:
- **SPEC_SIEGE.md** (SE1–SE2) — the medieval siege train: catapults (area splash + fire), ballista bolts, a mobile siege tower that breaches palisades. Shipped, baseline-ON.
- **SPEC_CHEMICAL_WAR.md** (CW1–CW3) — chemical & Cortés-style deception warfare: poison bombs that bloom a decaying cloud + covert false pheromone trails that lure enemy foragers. Shipped, baseline-ON.

## Interface, tooling & harness
- **SPEC_DASHBOARD.md** (DB1–DB8) — the Keeper's Console (web dashboard / API).
- **SPEC_LIVE_VIEW.md** — the live terrarium viewer (`live_view.py`): render, HUD, EVENT_TINTS, manager screen.
- **SPEC_PLAY_KIT.md** (PK1–PK6) — a headless client to drive & test the terrarium.
- **SPEC_SANDBOX.md** (SB1–SB5) — the sandking sandbox (the escaped-maw play space beyond the glass).
- **SPEC_FIT_CONSTANTS.md** (FC1–FC12) — learned demonstrator `fit_constants.py`: keep-if-improved search of the four semi-permeable knobs (`SUN_JITTER_SD`, `SUN_OSC_AMP`, `CAPTURE_TEMP`, `BARGAIN_TEMP`) against a healthy-ecology objective (liveness + mode-diversity + weather-variance); REPORTS fitted-vs-inert, never edits sandkings.py; sqlite load-if-exists checkpoint; Tier-2 grounding demonstrator.
- **SPEC_LAYOUT.md** — repository layout contract (hygiene 3/3): entrypoints at root, all sim modules in `sim/` (plain script dir, flat imports), root-relative artifact resolution rules, acceptance = full battery green.
- **SPEC_GRAPHICS.md** — terrarium graphics: the legibility redesign (glyph/tile render, palette, HUD readability).
