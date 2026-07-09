# Spec: The Political World (trust, gifts, truces, coalitions, betrayal)

Layer: **Requirements** + **Behavioral** blocks (diplomacy phase, betrayal
cascade). Governs: `politics.py`, the diplomacy phase of `step()`, combat
gating, the war-footing redesign (amends T10), envoys, coalition logic,
respawn reputation, anchors M11, viewer surface R25–R27. IDs **P1–P15**.
Status: draft → implement → reconcile (log at bottom).

Theory → mechanism (binding intent): Axelrod iterated cooperation (trust
built slowly by honored commitments, destroyed fast, decays toward
forgiveness); Nowak/Sigmund indirect reciprocity (betrayal costs standing
with everyone); Waltz structural realism (coalitions balance against
capability, not intent; victors quarrel); Ostrom common-pool cultivation
(principles 1/2/4/5 map; 3/7/8 explicitly out of scope).

## 1. Implementation Requirements (constants, all in politics.py)

- `TRUST_DECAY = 0.999`/step (half-life ≈ 693 ≈ 1.7 seasons).
- Thresholds: `ALLY_TRUST = 40`, `ALLY_EXIT = 25` (latched, mutual),
  `FRIENDLY = 15`, `HOSTILE = -25`, `NEMESIS = -60`.
- Deltas: unit kill −4; maw damage −0.08/HP and −10 first-blood; crop
  raid −6/voxel; gift +12 (food) / +18 (gold) × `0.5^k` diminishing in
  `GIFT_WINDOW = 500`; truce honored +0.02/step; joint war +0.05/step;
  coalition drift +0.08/step capped at +60; betrayal −60 victim, −20
  every observer. Clamp [−100, 100] on every write.
- `TRUCE_DURATION = 400` (= one season); `GRUDGE_LOCK = 600`;
  `BETRAYAL_COOLDOWN = 800`; rejected-proposal cooldown 100.
- `GIFT_SIZE_FOOD = min(60, 0.25·stores)` floor 20; `GIFT_SIZE_GOLD = 5`;
  `GIFT_COOLDOWN = 150` per (giver, recipient).
- `DIPLOMACY_INTERVAL = 25` (policy cascade cadence; the colony learner
  already ticks at 25 — one cadence).
- Power: `power(c) = food + 15·pop + 0.2·mawHP + 25·copper + 10·gold`;
  hegemon enter `share > 1.6/n`, exit `< 1.3/n` (n = living colonies).
- `COOP_YIELD_BONUS = 0.25`; co-op harvest split 60% harvester / 40%
  owner; tend adds +1 crop progress per allied visit-step.
- `ColonyGenome.loyalty` init `uniform(0.2, 0.9)`, EVOLVABLE (MUST be in
  `mutate()`'s attr list).
- All diplomacy state pickles with the sim; lazy `sim._diplomacy()`
  accessor (checkpoint-compat convention). `hostile()` defaults to
  all-hostile when the sim lacks diplomacy (evolution-sim guard).

## 2. Functional Requirements

- **P1 (relation state)** `politics.py` holds `Relation` (directional:
  trust, gift timestamps/window count, last_betrayed_by, last_hostility)
  per ordered pair and a `Diplomacy` container (relations, symmetric
  `truce_until` by frozenset, per-colony `war_target`, hegemon id,
  betrayal timestamps). Update events per the §1 delta table, applied at
  the hooks where those outcomes already occur (kill logging, siege
  damage, raze, envoy arrival, per-step truce/joint-war/coalition ticks).
- **P2 (decay)** Every step trust decays ×TRUST_DECAY toward 0. `ally(a,b)`
  is a latched predicate: sets when BOTH directions ≥ ALLY_TRUST, clears
  when either < ALLY_EXIT.
- **P3 (gifts)** A gift is a physical ENVOY: the sender's worker nearest
  its maw is tasked; the amount is escrowed (debited at dispatch); the
  envoy paths to the recipient maw (`_step_toward`); at Chebyshev ≤ 2 the
  recipient gains the amount and trust rises (recipient→sender). Envoys
  never initiate combat; the RECIPIENT's units skip envoys addressed to
  them; third parties may kill them (gift lost, event). If war intervenes
  in transit the gift is refused (−25 sender→recipient, event). Events:
  dispatch `Colony {a} sends tribute to Colony {b}`; arrival `Colony {b}
  accepts Colony {a}'s tribute`; death `Colony {a}'s envoy perishes!`;
  refusal `Colony {b} spurns Colony {a}'s envoy!`.
- **P4 (truces)** Symmetric, expiring pacts. Proposal via the P11 cascade;
  acceptance same tick by the counterpart's rules: auto-accept when its
  food < 2·BOOTSTRAP_FLOOR (exhaustion peace); accept when trust >
  NEMESIS unless (aggression > 0.8 and its power > 1.5× proposer's);
  refuse under GRUDGE_LOCK; rejected proposals wait 100 steps. At expiry:
  silent renewal when both sides still accept and neither trust < 0, else
  `The truce between Colony {a} and Colony {b} lapses`. Signing event:
  `Colony {a} and Colony {b} strike a truce` + both decision logs with
  moods. A truce is inviolable except via P6.
- **P5 (war target; amends T10)** `colony.at_war` derives from
  `war_target is not None`; the hoard trigger and hysteresis are
  unchanged, but entering war selects ONE target:
  coalition override → the hegemon; else argmax over living, non-truced,
  non-coalition-partner rivals of `0.45·hatred + 0.35·wealth −
  0.20·strength` (each normalized over eligibles). No eligible target →
  restless peace (log once `Colony {a} seethes, but has no enemy`).
  Target is sticky until it dies or a truce is signed with it. Event:
  `Colony {a} declares war on Colony {b}!` (replaces the T10 text; the
  "war" tint substring still matches). Cross-map sieges (T10) apply ONLY
  to the target (and the hegemon under coalition).
  *D1/D3 amendment (SPEC_DYNASTIES): same-house kin are excluded from
  eligibility, and an outstanding house grudge adds +0.3 to the target
  score (the blood feud directs the spear across generations; a
  throttled "blood feud flares" event fires on selection).*
- **P6 (betrayal)** The only attack path under a truce. Gates (all):
  active truce; aggression > 0.75 and loyalty < 0.35; jealousy (target
  food > 2× mine — the EXISTING anchor predicate); my power > 1.5×
  target's; my food > WAR_CHEST; ≥ BETRAYAL_COOLDOWN since my last
  betrayal. Execution (atomic, once): drop the truce; −60 victim→me,
  −20 every third colony→me; set victim's GRUDGE_LOCK; `war_target = victim`;
  event `Colony {a} betrays Colony {b}!`; decision log with colony mood
  (which will, by construction, tend to contain jealousy/rich — assert in
  the test).
- **P7 (hegemon)** Power share per §1; hegemon enter/exit with hysteresis;
  entry event `A coalition rises against Colony {h}!`, exit `The
  coalition against Colony {h} dissolves`.
- **P8 (coalitions)** While a hegemon exists: non-hegemon pairwise drift
  (+0.08/step, cap +60); coalition members entering war target the
  hegemon and mobilize at WAR_CHEST·0.5; co-belligerents (both targeting
  the hegemon) are non-hostile to each other. When the hegemon's maw
  falls: the T5 corpse feast is the spoils (emergent scramble) and every
  ex-member's trust toward the NEW strongest ex-member drops −10
  (victors' quarrel).
- **P9 (combat gating)** One pure `hostile(sim, a, b)`: False for self,
  active truce, latched allies, or co-belligerents; True otherwise —
  and True universally when the sim has no diplomacy (evolution sims).
  *D1 amendment (SPEC_DYNASTIES): same-house colonies are kin —
  hostile() returns False for them before any trust logic.*
  Gated sites (ALL SEVEN): `_resolve_conflicts` pair loop;
  `_apply_maw_siege_damage`; soldier rule-based enemy/maw scans; scout
  alarm (T11); maw-migration threat scan (T15); monitor `build_context`
  rival scans (`enemy_dist`/`enemy_maw_cheb`/danger/hunt filtered;
  `jealousy`'s richest-rival read stays UNFILTERED — envying allies
  feeds betrayal); neural `enemy_positions`.
- **P10 (cooperative cultivation)** Safe passage follows from P9. TEND:
  an allied worker adjacent to an ally's CROP adds +1 progress once per
  visit-step (a new low-priority worker branch below farming); a crop
  tended by ≥ 2 colonies in its life yields ×(1+COOP_YIELD_BONUS), split
  60/40 harvester/owner. Truced (non-allied) colonies' crops are NOT
  valid forage targets — raid-under-truce happens only via P6.
- **P11 (policy cascade)** Every DIPLOMACY_INTERVAL steps, colonies in
  randomized order run first-match: BETRAY (P6 gates) → APPEASE (an
  aggressor targets me with power > 1.4× mine and my share < 0.8/n →
  gift + propose truce) → RECIPROCATE (unanswered gift < 300 steps old
  and food > WAR_CHEST/2 → half-size gift back) → INVEST (hegemon exists,
  not me → gift my highest-trust non-hegemon) → SUE-FOR-PEACE (mutual
  non-hostility, both food < WAR_CHEST, no truce/grudge/recent rejection
  → propose truce). Every act logs a decision with the colony mood.
- **P12 (respawn reputation — asymmetric shadow)** On respawn: successor's
  outbound trust = 0 (new polity, fresh mind per M6); inbound (others →
  successor) = `clamp(0.25 · old, −15, +15)` (folk memory of the banner);
  truces, war targets, and grudges involving the slot are cleared at the
  T5 death cascade.
  *D3 note (SPEC_DYNASTIES): house-level grudges (`sim.house_grudges`,
  keyed by house names) never decay and survive respawn; the 0.25x
  trust shadow above is unchanged.*
- **P13 (surfacing)** Event catalog per the texts above + crop raid
  `Colony {a} raids Colony {b}'s fields!`. EVENT_TINTS: "betrays" pink-red,
  "truce" green, "tribute"/"envoy" gold, "coalition" blue, "raids"
  orange, "seethes" grey. HUD: war tag gains its target `[WAR→2]`; per-
  colony ` T:1,3 A:2` treaty/ally markers. Manager: RELATIONS block
  (per rival: →out ←in trust, standing, truce countdown / war marker).
  Glyphs: envoy worker letter rendered in gold; allied territory tint
  blends 25% toward the ally's color; units standing in allied/truced
  foreign territory get a white border (safe passage).
- **P14 (anchors, M11)** ally (any latched ally or active truce),
  betrayed (my colony betrayed within 300 steps), gratitude (gift
  received within 300 steps), dread (a hegemon exists and it is not us).
  Colony-level context bools from `sim._diplomacy()`; probes setdefault;
  vocabulary rebuild (31 seeds at this round; 35 as of M13).
- **P15 (compatibility)** Old checkpoints: `_diplomacy()` lazy-creates
  neutral state; `war_target`/`at_war` read via guards in view code.
  Evolution sims: no diplomacy phase (fitness stays pure combat);
  `hostile()` defaults all-hostile there. GPU sim: classes only.

## 3. Behavioral Spec — diplomacy phase (step 5b, before combat)

```
Every step: decay all trust; tick truce-honored/joint-war/coalition drift;
            evaluate hegemon enter/exit (events on transition);
            move envoys one step (deliver / die / refuse per P3)
Every DIPLOMACY_INTERVAL steps: run the P11 cascade per living colony in
            randomized order (first matching rule acts)
Truce expiry check per step: renew silently or lapse with event
```

## 4. Behavioral Spec — betrayal cascade

```
When the P11 cascade selects BETRAY(me, T):
    delete truce {me,T}; trust[T→me] −60; ∀ other living c: trust[c→me] −20
    relations[T→me].last_betrayed_by ← step   (GRUDGE_LOCK starts)
    war_target[me] ← T; my last-betrayal step ← step
    log event + decision (mood = colony_thought at this instant)
Invariant: fires at most once per BETRAYAL_COOLDOWN per colony
```

## 5. Acceptance (Given/When/Then, mapped to tests/test_politics.py)

- (P1/P2) deltas apply and clamp; decay ×0.999 both signs.
- (P4) adjacent enemy soldiers + a maw-adjacent attacker under truce deal
  zero damage; honored ticks accrue; expiry lapses or renews per rules.
- (P3) dispatch escrows, arrival credits + trust; second gift in window
  yields half; third inside cooldown blocked; recipient units skip the
  envoy; mid-transit war → refusal event.
- (P5) rigged trust/power picks the rich-hated-weak target; declaration
  event exact; restless peace logs once.
- (P6) rigged hawk+jealousy+truce fires exactly one betrayal with
  −60/−20, grudge refusal, and a mood containing "jealousy".
- (P7/P8) a 3× power colony triggers the coalition (event once), drift
  raises non-hegemon trust, co-belligerent soldiers don't fight, hegemon
  fall → dissolution + victors' quarrel −10.
- (P10) allied tend adds progress; co-op harvest splits 60/40 with +25%;
  truced crops not foraged.
- (P12) predecessor at −80 → successor inbound within ±15, outbound 0,
  truces/grudges cleared.
- (P14) anchor predicates from rigged relation state.
- (P13) manager RELATIONS block + HUD `[WAR→n]` render from pure builders.
- (P15) politics pickles round-trip; a pre-politics checkpoint resumes;
  Enhanced sim runs 200 steps with no diplomacy state.
- Soak (5000 steps, all systems): ≥1 truce; ≥1 betrayal OR coalition; no
  hostile-event gap > 1500 steps; every slot alive-or-pending; throughput
  within 10% of baseline.

## 6. Reconciliation Log

- 2026-07-08 — Implemented P1–P15 with deviations, intent-preserving:
  - P5 refined during testing: the soldier maw scan now picks the nearest
    ENGAGEABLE maw (local range OR the war target) — the first cut picked
    the globally nearest and stalled cross-map raids whose target wasn't
    closest.
  - P13 safe-passage border in BLOCKS mode deferred (glyph mode carries
    the envoy gold letter and allied HUD marks; border noted for a polish
    pass). Allied-territory tint blend deferred with it — the RELATIONS
    block and `T:`/`A:` HUD marks carry the information.
  - P10 tend requires the crop to be in the growth registry (ripe crops
    aren't tendable — nothing left to accelerate).
  - Trust deltas for unit kills/sieges/razes are applied inline at the
    existing outcome hooks; raze additionally requires hostility (truced
    fields can only fall via betrayal, closing a gate the spec implied).
  - Verified: 16 politics tests + all five prior suites green; 5000-step
    soak per §5 criteria.
