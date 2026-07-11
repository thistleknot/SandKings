# SPEC Index — the Sand Kings terrarium

Catalog of every `SPEC_*.md` in the repo, grouped by arc, one line each. The
spec is the source of truth for design-before-build (see the spec-driven-dev
contract). Governing decision records live under `docs/decisions/`.

## Ecology & world (the closed terrarium)
- **SPEC_TERRARIUM_LIVENESS.md** — feeding, foraging, maw combat, respawn, strata terrain (the base sim).
- **SPEC_BIOME.md** (BI1–BI7) — the closed biome & the panel (Phase 3): the sealed world and its glass.
- **SPEC_SEASONS_AND_STONE.md** — seasons, scarcity, farming, the oasis, ore, colony learning.
- **SPEC_WEATHER.md** (W1–W6) — desert weather: storm, hail, cold, flood.
- **SPEC_TIMBER_AND_FLAME.md** — timber, bone & flame: fortifications, organic weapons, decay, fire.
- **SPEC_HYDRO_HAND.md** (HH1–HH5) — the hand's water & seeds (Phase 2 / Hydro-Hand).
- **SPEC_ARENA.md** (AR1–AR7) — arena mode: the keeper's gifts, wrath, and neutrals.

## The keeper & the great other (god layer)
- **SPEC_KEEPER.md** (K1–K7) — the keeper: the hand that feeds, the gift ladder, the terminal.
- **SPEC_FACES.md** (F1–F5) — "look to your faces": carved sentiment glyphs / nature moods.
- **SPEC_AWARENESS.md** (AW1–AW6) — nature until the great other: keeper-directed feeling gates on `breached` (the `_escape` breakout).
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
- **SPEC_DYNASTIES.md** (D1–D12) — dynasties & the salience-scored chronicle; house names, epithets, saga.
- **SPEC_CANON_HOUSES.md** (CH1–CH4) — the canonical houses (Round B / Canon).

## Interface, tooling & harness
- **SPEC_DASHBOARD.md** (DB1–DB8) — the Keeper's Console (web dashboard / API).
- **SPEC_LIVE_VIEW.md** — the live terrarium viewer (`live_view.py`): render, HUD, EVENT_TINTS, manager screen.
- **SPEC_PLAY_KIT.md** (PK1–PK6) — a headless client to drive & test the terrarium.
- **SPEC_SANDBOX.md** (SB1–SB5) — the sandking sandbox (the escaped-maw play space beyond the glass).
