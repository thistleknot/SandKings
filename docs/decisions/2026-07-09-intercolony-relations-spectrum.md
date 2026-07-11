# Decision: Inter-Colony Labor Extraction — Unified Wage/Force Model

Date: 2026-07-09 (persisted 2026-07-10)
Author: opus_architect (Fable 5) — undetermined-scope decomposition
Status: ACCEPTED — all forks F1–F6 resolved (see below); M1/M2 specs authored, M3/M4 pending
Supersedes: an earlier draft that decomposed annihilation / subjugation /
mercantile-peace as three parallel mechanics. Per user reframe they are ONE
mechanic — extracting another colony's labor-value — at rising abstraction.
Subjugation persists at the mercantile tier as the wage relation.

> Provenance note: Fable returned this record in-agent but never persisted it;
> it was written to disk on 2026-07-10 from the agent's returned content after
> opus_coder flagged the missing file. Faithful to the returned text.

## The Unified Model (the load-bearing abstraction)

- Every unit produces labor value **V** per deposit event (the food/ore/wood
  it credits — the four hooks below).
- **wage_ratio w in [0,1]** = share of V returned to the laborer's BIRTH
  colony; **(1−w)·V** = surplus the extractor keeps. w is the exchange rate;
  the surplus flowing as grains is "power liquidated through a common currency."
- **BRUTE mode** (war only): w ~ 0, enforced by force. Psionic birth-tie
  (`colony_id`) intact => coercion, not conversion => leaky and expensive
  (guards, defiance, break-free, war cost). Annihilation is the w-undefined
  limit: value destroyed, not extracted.
- **WAGE mode** (peace only): w > 0 set by bargaining = f(relative power,
  labor scarcity/desperation, control of scarce factors). Voluntary, stable,
  zero enforcement cost. Subjugation "at a higher level."
- **Comparative advantage** (Ricardo / factor endowments): each colony trades
  its abundant factor — labor, monopolized tech access, or resource surplus —
  for its scarce one. User's example: a weak civ trades tree-cutting labor to
  the advanced civ that controls the keeper's `calculator`. Bargaining power =
  control of scarce factors; a colony with only labor accepts a bad w because
  it has nothing scarce to bargain with.
- **Ranking pressure**: net extraction via wages is typically HIGHER than via
  force despite the smaller per-unit take, because wage labor is reliable,
  scalable, and peacetime. That efficiency gap is the decision logic that makes
  rational maws climb whip -> wage. Annihilation only when no extraction is
  feasible.
- **Genre lodestar**: the mercantile layer should read like a Capsim-Capstone
  geopolitical business sim — colonies as one-city firm-nations competing on
  price, tech, capacity, and labor terms. Dovetails the existing
  one-city-civilization lens in INSPIRATIONS.md. (Docs follow-up, outside this
  decomposition: add a "geopolitical business sim / comparative-advantage
  market" entry to INSPIRATIONS.md.)

## Substrate Map (ground hooks — active sim class TerrariumSimulation, step() at sandkings.py:1417)

| Hook | Location | Role |
|---|---|---|
| Allegiance | `SandKing.colony_id` ~:723; `brain_layer`/`SoldierLayer` has NO loyalty field | `laboring_for` sits BESIDE `colony_id`; psionic conditioning untouched |
| Combat | `_resolve_conflicts` :5444–5560; targeting = adjacency r1 + `hostile()` (not raw colony_id); lethal branches queue `units_to_remove` :5487–5490, :5507–5510; removal :5544–5560 | capture-not-kill hooks at the two lethal branches; `hostile()` must learn thrall status |
| Labor credit (V) | ore `colony.ore[kind]+=1` `_haul_step` :3884 (salvage :3882); food `colony.maw.eat(HARVEST_YIELD)` :5083; ripe-crop `maw.eat` :5118 (already an ally 0.6/0.4 split — precedent); wood `colony.wood+=1` `_fell_tree` :2000/:2013 | the four redirect points an extractor hijacks |
| Grains | `_score_forecasts` :2919–2945 credits `colony.currency` + `house_grains`; `Colony.currency` init ~:875; forecast accuracy is the ONLY mint today | wages are a NEW grain flow (fork F2 = transfer existing grains) |
| Envoys/tribute | `SandKing.gift_amount/gift_kind/gift_to`; existing tribute/gift dispatch path | generalize to recurring settlement shipments (M3) |
| Keeper foreign gifts | `GIFT_LADDER` (abacus/watch/calculator/pi), `TECH_FOREIGN`; held in `colony_foreign`, keeper-granted; effect multipliers | the MONOPOLY factor: scarce, non-reproducible, keeper-only — licensable via an "effective gifts" VIEW (M3) |
| True conversion | `_check_maw_deaths` :4858–4921 (called :1731) destroys all units (`colony.units.clear()` :4863–4865), spills ore, resets ownership -> −1 :4892; only `_plunder_techs` :2667–2689 transfers anything | maw death severs the psionic tie — the ONLY true-conversion path; thralls convert here, BEFORE the clear/wipe |
| Tick insertion | `_subjugation_tick` after `_resolve_conflicts` (:1725), before `_check_maw_deaths` (:1731); 5a-xxx / 6 / 7 label convention | capture inside `_resolve_conflicts`; settlement rides its own tick |
| War/relations | `at_war` per pair, WAR_CHEST, `house_grudges`, `_resonance_tick` | mode selection (M4) rewires war entry; grudge narrows the bargaining range |

## Module Decomposition (one shared substrate, two modes, one selector)

All modules DEFAULT-NEUTRAL: inert at shipped defaults so the 35-suite Docker
battery stays green.

### M1 — SPEC_LABOR.md (LV1–LV7): labor-value + wage-split substrate
Shared accounting every other module consumes — no behavior change. `V` at the
four credit hooks; `SandKing.laboring_for: int = −1` beside `colony_id`; a single
split function `_credit_labor` fronting all four hooks (generalizes the ripe-crop
0.6/0.4 ally split); the pure `w` bargaining function (scarce-factor control
includes foreign-gift holdings + military power); composite `power(colony)`.
Default-neutral: `laboring_for=−1` => today's credit exactly. Tests:
`tests/test_labor.py`. Depends: nothing. Blocks: M2, M3, M4.

### M2 — SPEC_SUBJUGATION.md (SJ1–SJ8): BRUTE mode — force, war only
Capture-not-kill at the lethal branches (RNG-guarded on `CAPTURE_CHANCE<=0`);
`laboring_for=captor` at w=W_BRUTE; `colony_id` NEVER rewritten. Defiance meter
(rises unguarded, accelerated near birth maw); threat-of-harm coercion;
break-free + flee home. `hostile()` extended for thralls. True conversion in
`_check_maw_deaths` BEFORE :4863/:4892. Gate `CAPTURE_CHANCE=0.0`. Tick
`_subjugation_tick`. Tests: `tests/test_subjugation.py`. Depends: M1. Blocks: M4.

### M3 — SPEC_WAGES.md (WG1–WG9): WAGE mode — factor market, peace only
Same split, voluntarily, over a small FACTOR MARKET traded by comparative
advantage: (1) LABOR CONTRACTS (rent unit output over the same hooks, w>0, no
enforcement); (2) TECH LICENSES (rent ACCESS to a held keeper foreign gift via an
"effective gifts" VIEW — never mutate `colony_foreign`); (3) RESOURCE SURPLUS.
Priced in grains by scarcity × relative power. Settlement via generalized envoy
dispatch; grains non-negativity respected (escrow/prepay). Gate
`WAGE_ENABLED=False`. Tests: `tests/test_wages.py`. Depends: M1. Blocks: M4.
Parallel-safe with M2. Sizing note: split at WG-market / WG-settlement if it
exceeds one rote-implementable spec.

### M4 — SPEC_BARGAIN.md (BG1–BG6): mode selection — the ranking pressure
Per-pair, choose ENFORCEMENT MODE and set w from net-extraction comparison
(E_wage vs E_brute vs destruction value). Wages-win-when-feasible must be
EMERGENT from cost constants (acceptance test enforces it). Grudge narrows the
bargaining range. Rewires war entry; the only module that alters existing
behavior. Master gate `BARGAIN_ENABLED=False`. Tests: `tests/test_bargain.py`.
Depends: M1, M2, M3. Terminal.

## Build Order
M1 -> (M2 || M3) -> M4. M1 first (it IS the model). M2/M3 are the two enforcement
modes over disjoint hook sets (combat vs diplomacy/envoys) — parallel-safe. M4
last (only module that alters war-entry/kill behavior; needs both modes priced).

## New vs Generalization
- Generalized: ripe-crop 0.6/0.4 split -> the wage split; gift/tribute envoy ->
  settlement shipments; foreign-gift effect application -> licensed "effective
  gifts" view; war-entry rule -> M4 outside-option; `_plunder_techs` kept as-is
  as annihilation-tier spoils.
- New: V accounting; `laboring_for` dual allegiance; defiance/threat coercion;
  maw-death conversion; w bargaining fn; factor-endowment vectors +
  comparative-advantage trade selection; tech-license contracts; labor->grains
  flow; mode-selection state machine.

## Risky Couplings / Ordering
1. Conversion must run in `_check_maw_deaths` BEFORE `colony.units.clear()`
   (:4863) and the ownership reset (:4892).
2. Capture bypasses the removal path (:5544–5560) — verify nothing downstream
   (ecology/corpse, telemetry) assumes every lethal branch removes a unit; test
   under nonzero CAPTURE_CHANCE.
3. `hostile()` extension touches ALL combat targeting — keep a pure predicate
   change with its own battery check.
4. Grain non-negativity vs settlement — escrow/prepay in M3.
5. Licensed foreign-gift effects must apply through an "effective gifts" VIEW,
   never by mutating `colony_foreign` (else keeper-ladder + augment state
   corrupts on expiry).
6. If wage relations decay grudge (F6), that feeds `_resonance_tick`/war-exit —
   oscillation risk; needs hysteresis (adopted).
7. Stage ordering: M4 stance before war entry; defiance/defection before that
   tick's labor credit; w renegotiation before settlement.

## Design Forks — RESOLVED
- **F1 bargaining form/cadence of w** — STICKY w with periodic renegotiation
  (avoids price-thrash coupling into resonance).
- **F2 settlement medium / monetary base** — wages TRANSFER existing grains (no
  mint). CU stays forecast-minted only; grains become a liquidity constraint on
  hiring. Zero-sum money, positive-sum goods.
- **F3 physical vs virtual wage labor** — VIRTUAL first pass (production-share
  redirect / terms-of-trade; no unit migration). Physical labor-migration PARKED
  as a visible-fidelity follow-up.
- **F4 non-thrall survivors of a dead maw** — die as today (:4863); only
  pre-existing thralls convert.
- **F5 W_BRUTE** — 0.0 (pure whip; named constant, one-line change to a trickle).
- **F6 peace dividend** — YES, wage relations decay grudge, WITH hysteresis
  (damped so colonies don't oscillate war<->trade<->war).

## Parked (out of scope this pass)
- Licensing ordinary (non-foreign) tech tiers — truce barter/TE12 diffuses those.
- Transfer/sale of foreign-gift OWNERSHIP — access rental only.
- Multilateral markets / >2-colony price discovery — pairwise only.
- Thrall reproduction / allegiance of births under subjugation.
- Human-player participation via Dialogue/Grains.
- Physical labor migration (F3) — visible-fidelity follow-up.
- INSPIRATIONS.md "geopolitical business sim" entry — docs follow-up.

## Handoff
opus_coder writes four rendered specs in build order (M1 SPEC_LABOR; M2
SPEC_SUBJUGATION || M3 SPEC_WAGES; M4 SPEC_BARGAIN), each with pseudocode,
constants, one test file. M1/M2 authored 2026-07-10.
