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

## The keeper & the great other (god layer)
- **SPEC_KEEPER.md** (K1–K7) — the keeper: the hand that feeds, the gift ladder, the terminal.
- **SPEC_FACES.md** (F1–F5) — "look to your faces": carved sentiment glyphs / nature moods.
- **SPEC_AWARENESS.md** (AW1–AW6) — nature until the great other: keeper-directed feeling gates on `breached` (the `_escape` breakout).
- **SPEC_BREAKOUT.md** (BRK-A/B/C) — making the breakout reachable, visible & grantable: opens VM actuator port 7 so organic breach is possible (root fix), a per-colony breakout-proximity gauge (`breakout_progress`), and the keeper `open_door` action (`_escape` by fiat) across all three clients.
- **SPEC_DISPOSITION.md** (DP1–DP12) — keeper-treatment → disposition: signed `favoritism` + boldness `confidence` + short-term `agitation`; modulates aggression, nudges `keeper_sentiment`, biases the bargain (default-neutral at neutral values).
- **SPEC_PSIONIC.md** (PS1–PS6) — the psionic maw & keeper-as-prey: the awakened reach back.

## Mind, growth & sentience
- **SPEC_SENTIENCE.md** (S1–S6) — the sentience arc: resonance, meta-learning.
- **SPEC_METAMORPHOSIS.md** (MT1–MT6) — the three physical stages (insectoid → new breed → Shade), size × cruelty.
- **SPEC_ENLIGHTENMENT.md** (EN1–EN10) — the post-escape intelligence leap: raised brain ceiling, faster tech/codex climb (hangs off `_escape`).
- **SPEC_HIVE_MONITOR.md** (M1–M15) — concept probes, thoughts, the manager screen, and the 42-anchor lexicon.
- **SPEC_NEURAL_ACTIVATION_TRACKING.md** — the neural hive: activation tracking, pruning, folding, soldier memory.
- **SPEC_EVOLUTION.md** (EV1–EV6) — the evolving engine: genome mutation, selection, respawn bloodlines.
- **SPEC_AUGMENTS.md** (AUG1–AUG5) — earned KV-cache memory augments (awakened only).

## Vocabulary & language (the shared embedding space)
- **SPEC_CODEX.md** (CX1–CX7) — the read-only corpus; a colony reads a LESSON that nudges its dispositions (incl. `commerce`/`enlightenment`).
- **SPEC_DIALOGUE.md** (DL1–DL7) — human ↔ awakened-colony conversation over the shared GloVe anchors (incl. the economy vocabulary).

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
- **SPEC_POPULATION.md** (POP-1–POP-4) — dynamic population & succession, **Phase 0** (inert scaffolding): a fixed pool of `MAX_COLONIES=8` slots each carrying a lifecycle `pop_state` (ACTIVE/SUCCESSION/DORMANT, inert at flag-off), the default-off `dynamic_population` flag (byte-identical to today), and the slot-scrub choke point `_deactivate_slot(cid)` (defined + tested, unwired) that centralizes all stale per-colony teardown (pheromones/ownership/politics/thralls/gifts/disposition). Emergent 2..8 population is later phases. NOTE: its governing decision record `docs/decisions/2026-07-11-dynamic-population-and-succession.md` is not yet committed.

## Interface, tooling & harness
- **SPEC_DASHBOARD.md** (DB1–DB8) — the Keeper's Console (web dashboard / API).
- **SPEC_LIVE_VIEW.md** — the live terrarium viewer (`live_view.py`): render, HUD, EVENT_TINTS, manager screen.
- **SPEC_PLAY_KIT.md** (PK1–PK6) — a headless client to drive & test the terrarium.
- **SPEC_SANDBOX.md** (SB1–SB5) — the sandking sandbox (the escaped-maw play space beyond the glass).
- **SPEC_FIT_CONSTANTS.md** (FC1–FC12) — learned demonstrator `fit_constants.py`: keep-if-improved search of the four semi-permeable knobs (`SUN_JITTER_SD`, `SUN_OSC_AMP`, `CAPTURE_TEMP`, `BARGAIN_TEMP`) against a healthy-ecology objective (liveness + mode-diversity + weather-variance); REPORTS fitted-vs-inert, never edits sandkings.py; sqlite load-if-exists checkpoint; Tier-2 grounding demonstrator.
- **SPEC_LAYOUT.md** — repository layout contract (hygiene 3/3): entrypoints at root, all sim modules in `sim/` (plain script dir, flat imports), root-relative artifact resolution rules, acceptance = full battery green.
