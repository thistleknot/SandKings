# SPEC: The Bargain — Mode Selection by Net Extraction — BG1–BG12

Module **M4** of the inter-colony political-economy arc (governing scope record:
`docs/decisions/2026-07-09-intercolony-relations-spectrum.md`, entry BG1–BG6).
Depends on **all three** lower modules: M1 `SPEC_LABOR` (`composite_power`,
`w_bargain`, `W_BRUTE`, `W_FAIR`), M2 `SPEC_SUBJUGATION` (`_subjugate_stance`,
`_try_capture`, `CAPTURE_CHANCE`, `subjugation_stance`), and M3 `SPEC_WAGES`
(`_wage_open_sweep`, `_labor_w`, `_factor_endowment`, `_factor_price`,
`_pair_at_war`, `_clamp01`, `WAGE_ENABLED`). **Terminal module — it closes the
arc.** It supersedes the SJ9 `--subjugation` war-driven stance and the WG12
`--wages` always-on market with a single per-pair mode decision.

**The mechanic.** For each unordered colony pair, M4 chooses one **enforcement
mode** — how (or whether) the stronger colony extracts the weaker's labor-value —
and drives the lower modules to realise it. It is ONE continuous decision over the
SAME labor-value split `w` that M1/M2/M3 already implement, not three disjoint
branches:

- **ANNIHILATE** — war, value destroyed (today's default war/combat behaviour).
- **SUBJUGATE** — war, brute capture at `w = W_BRUTE = 0` (M2 drives the capture).
- **WAGE / TRADE** — peace, `w > 0` (M3 opens contracts; hire labor / license
  tech / trade goods).

**The core principle (must be EMERGENT, not hard-coded).** A rational maw prefers
the mode with the highest NET extraction. M4 computes and compares three
expected-values per pair — `E_wage`, `E_brute`, `E_destroy` — and picks the max.
Wages WIN when both wage and brute are feasible **because force leaks and wages
scale**: the extractor keeps only `(1−w)` of each unit's value under wages but
keeps it RELIABLY, at zero enforcement cost, in peacetime; under brute it keeps
the whole value but only the fraction that survives defiance, and pays
enforcement plus war attrition. That efficiency gap lives in the **cost
constants** (BG8), not in an `if prefer_wages` branch. Grudge (`house_grudges` +
negative diplomatic trust) narrows the bargaining range toward force/annihilation
by collapsing `E_wage` and inflating `E_destroy`.

> **TOP INVARIANT (default-neutral) & FIRST ACCEPTANCE CLAUSE.** The entire module
> is gated behind `BARGAIN_ENABLED = False`. With it False: `_bargain_tick`
> early-returns before touching `self._bargain_modes`, any RNG, or any colony/unit
> state; it sets NO `subjugation_stance`, opens NO contract, and does NOT alter war
> entry — the existing WAR_CHEST/grudge path at `sandkings.py:1746–1778` runs
> byte-for-byte as today because the war-entry edit (BG6) short-circuits on
> `BARGAIN_ENABLED`. M2 stays at its own gate (`CAPTURE_CHANCE = 0.0`) and M3 at
> its own (`WAGE_ENABLED = False`). The full regression battery (38 suites once
> `tests/test_bargain.py` lands) is byte-identical, verified with an RNG counting
> spy AND a war-entry-sequence golden. This is BGA-1.

All new state is getattr-guarded, pickled/regenerated per the `stage`/`breached`
convention; `EnhancedSandKingsSimulation.step` (`sandkings_evolution.py:281`) stays
inert. M4 adds **no new pickled unit field** — it reuses M1/M2/M3 state.

> Naming note: the running simulation class is `SandKingsSimulation`
> (`sandkings.py:1373`, `step()` at `:1524`); the arc specs refer to it as
> `TerrariumSimulation`. All method anchors below are on that class unless a
> `politics.py` / `sandkings_evolution.py` path is given.

---

## Per-pair mode state (BG1)

**BG1 — the mode enum, the per-step mode map, and its accessor.** M4's authoritative
output is a transient per-step map from an unordered colony pair to its selected
mode. It is REBUILT every `_bargain_tick` (colonies grow, die, and shift power each
step) and read by three consumers: the war-entry gate (BG6), the subjugation-stance
gate (BG5a), and the wage open-sweep gate (BG5b).

```
# module-level mode tags (string constants; pickle-trivial, log-readable)
BARGAIN_MODE_NONE       = 'none'         # no arrangement worth making (peace, no contract)
BARGAIN_MODE_WAGE       = 'wage'         # peace: M3 opens contracts for this pair
BARGAIN_MODE_SUBJUGATE  = 'subjugate'    # war: M2 captures for this pair
BARGAIN_MODE_ANNIHILATE = 'annihilate'   # war: normal combat, value destroyed
```

```
def _bargain_modes(self) -> dict:
    """Per-step map {frozenset({a_id, b_id}): mode_str}. Transient: rebuilt each
    _bargain_tick; getattr-guarded so a resumed/inert sim reads an empty map."""
    if not hasattr(self, 'bargain_modes'):
        self.bargain_modes = {}
    return self.bargain_modes

def _bargain_mode(self, a: Colony, b: Colony) -> str:
    """Mode selected for the unordered pair (a, b) THIS step; NONE if unset."""
    return self._bargain_modes().get(frozenset((a.colony_id, b.colony_id)),
                                     BARGAIN_MODE_NONE)

def _bargain_mode_ids(self, a_id: int, b_id: int) -> str:
    """Mode by colony_id (used by the war-entry gate, which has ids not colonies)."""
    return self._bargain_modes().get(frozenset((a_id, b_id)), BARGAIN_MODE_NONE)
```

Contract at the mode map:
- **Require** — keys are `frozenset` of two DISTINCT living colony_ids.
- **Guarantee** — every value is one of the four `BARGAIN_MODE_*` tags; an absent
  pair reads `BARGAIN_MODE_NONE`.
- **Maintain** — the map is rebuilt from scratch each `_bargain_tick`; stale pairs
  (a dead colony) do not persist because the tick only writes living pairs.
- **Assert** — after `_bargain_tick`, `set(self._bargain_modes())` contains only
  frozensets whose members are both currently-living colony_ids.

## The expected-value model (BG2)

**BG2 — `E_wage`, `E_brute`, `E_destroy`.** All three are pure, deterministic reads
(NO RNG). They estimate net extractable value over a fixed planning horizon
`BARGAIN_V_EST` (estimated labor-value per unit per horizon). The three helpers
reuse M1 `composite_power` and M3 `_factor_endowment` / `_labor_w` so the pricing
is consistent with what the lower modules will actually deliver.

**BG2a — `E_wage` (peaceful, reliable, scalable, zero enforcement).**
```
def _bargain_ev_wage(self, extractor: Colony, birth: Colony) -> float:
    """Net value `extractor` can pull from `birth`'s labor via M3 wage contracts.
    Reliable (no defiance leak), scalable (all free units), no enforcement cost,
    no war loss. Pure; no RNG."""
    n_labor = self._factor_endowment(birth)['labor']        # free hireable units (M3, :~)
    w       = self._labor_w(birth, extractor)               # M3 price: seller=birth, buyer=extractor
    trust_f = self._bargain_trust_factor(extractor, birth)  # grudge collapses willingness (BG3)
    return (BARGAIN_WAGE_RELIABILITY
            * n_labor * (1.0 - w) * BARGAIN_V_EST
            * trust_f)
```

**BG2b — `E_brute` (war-only, leaky, costly, attritional).**
```
def _bargain_ev_brute(self, captor: Colony, victim: Colony) -> float:
    """Net value via M2 forced capture. Whole value per thrall (w = W_BRUTE = 0),
    but only BARGAIN_BRUTE_RELIABILITY survives defiance; minus per-thrall
    enforcement; minus war attrition (0 if already at war — sunk). Pure; no RNG."""
    dom = composite_power(captor) / max(EPS_POWER, composite_power(victim))
    if dom < BARGAIN_DOMINANCE_MIN:
        return 0.0                                          # cannot capture -> infeasible
    n_cap  = self._bargain_capturable(captor, victim)       # dominance-bounded (BG2d)
    gross  = n_cap * BARGAIN_V_EST * (1.0 - W_BRUTE)        # W_BRUTE = 0 -> whole value
    leaked = gross * BARGAIN_BRUTE_RELIABILITY              # < 1: defiance/refusal/break-free
    enforce  = BARGAIN_ENFORCE_COST * n_cap
    war_loss = 0.0 if self._pair_at_war(captor, victim) else BARGAIN_WAR_LOSS
    return leaked - enforce - war_loss
```

**BG2c — `E_destroy` (annihilation: no extraction, remove the rival's power).**
```
def _bargain_ev_destroy(self, aggressor: Colony, rival: Colony) -> float:
    """Value of simply destroying `rival`'s power, scaled by grudge/threat.
    Pure; no RNG."""
    grudge   = self._bargain_grudge(aggressor, rival)       # 0..1 (BG3)
    war_loss = 0.0 if self._pair_at_war(aggressor, rival) else BARGAIN_WAR_LOSS
    return BARGAIN_DESTROY_WEIGHT * composite_power(rival) * grudge - war_loss
```

**BG2d — `_bargain_capturable` (dominance-bounded capture pool).**
```
def _bargain_capturable(self, captor: Colony, victim: Colony) -> float:
    """Free victim units the captor could realistically take, rising with
    dominance. Same pool E_wage would hire, so the comparison is apples-to-apples."""
    n_free = sum(1 for u in victim.units if getattr(u, 'laboring_for', -1) < 0)
    dom    = composite_power(captor) / max(EPS_POWER, composite_power(victim))
    return n_free * _clamp01((dom - 1.0) / BARGAIN_DOMINANCE_SCALE)
```

- **Require** — both colonies alive; `_factor_endowment` / `composite_power` /
  `_labor_w` / `_pair_at_war` are the M1/M3 helpers (verified present at
  `sandkings.py` — `_factor_endowment`, `_labor_w`, `_pair_at_war:3225`;
  `composite_power` module-level).
- **Guarantee** — all four return finite floats; consume ZERO RNG; mutate nothing.
  `E_brute` returns `0.0` below dominance (infeasible), matching M2's requirement
  that capture needs local dominance.
- **Maintain** — the SAME `BARGAIN_V_EST` horizon and the SAME free-unit pool feed
  wage and brute, so the mode choice is a genuine like-for-like net comparison.
- **Assert** — `E_wage >= 0`; `E_brute` finite; `E_destroy` finite.

## Grudge & trust — narrowing the bargaining range (BG3)

**BG3 — grudge collapses `E_wage`, inflates `E_destroy`.** Grudge fuses two verified
signals: the house-keyed blood-feud presence (`_house_grudges()`, `sandkings.py:1891`,
a `{(victim_house, traitor_house): step}` map) and continuous negative diplomatic
trust (`self._diplomacy().trust(a_id, b_id)`, `politics.py:84`; negative = hatred).

```
def _bargain_grudge(self, a: Colony, b: Colony) -> float:
    """0..1 grudge/threat between the two houses. Pure; no RNG."""
    d  = self._diplomacy()
    ha = self._house_name(a); hb = self._house_name(b)
    grudges = self._house_grudges()
    feud   = 1.0 if ((ha, hb) in grudges or (hb, ha) in grudges) else 0.0
    hatred = max(0.0, -d.trust(a.colony_id, b.colony_id)) / BARGAIN_TRUST_REF
    return _clamp01(BARGAIN_GRUDGE_FEUD_W * feud + BARGAIN_GRUDGE_TRUST_W * hatred)

def _bargain_trust_factor(self, a: Colony, b: Colony) -> float:
    """Willingness to hold a VOLUNTARY wage relation: 1.0 with no grudge, ->0 as
    grudge rises. Pure; no RNG."""
    return _clamp01(1.0 - BARGAIN_GRUDGE_SENS * self._bargain_grudge(a, b))
```

- **The monotone chain (BGA-2).** As grudge rises: `_bargain_trust_factor` falls →
  `E_wage` falls; `_bargain_grudge` rises → `E_destroy` rises; `E_brute` is
  grudge-independent. So the selected mode moves monotonically
  **WAGE → SUBJUGATE → ANNIHILATE** as grudge climbs, holding power/endowment fixed.
  This is the decision-record's "grudge narrows the bargaining range toward
  force/annihilation," realised through the constants.
- **Require** — `a`, `b` living; `BARGAIN_TRUST_REF > 0`.
- **Guarantee** — `_bargain_grudge ∈ [0,1]`, `_bargain_trust_factor ∈ [0,1]`;
  both pure, no RNG, no mutation.
- **Assert** — outputs clamped to `[0,1]`.

## Mode selection — the argmax (BG4)

**BG4 — `_bargain_pair_mode`, the emergent choice.** The stronger colony (by
`composite_power`) is the extractor/aggressor; M4 compares the three EVs for the
"strong extracts weak" direction and picks the max. Wages win ties (deterministic
tie-break); the SUBSTANTIVE win is from the constants (BG8), not the tie-break.

```
def _bargain_pair_mode(self, a: Colony, b: Colony) -> str:
    """Choose the enforcement mode for the unordered pair (a, b). Pure; no RNG."""
    if composite_power(a) >= composite_power(b):
        strong, weak = a, b
    else:
        strong, weak = b, a
    e_wage    = self._bargain_ev_wage(strong, weak)
    e_brute   = self._bargain_ev_brute(strong, weak)
    e_destroy = self._bargain_ev_destroy(strong, weak)
    best = max(e_wage, e_brute, e_destroy)
    if best <= 0.0:
        return BARGAIN_MODE_NONE                     # nothing worth doing -> plain peace
    if e_wage >= e_brute and e_wage >= e_destroy:
        return BARGAIN_MODE_WAGE
    if e_brute >= e_destroy:
        return BARGAIN_MODE_SUBJUGATE
    return BARGAIN_MODE_ANNIHILATE
```

**The emergent inequality that makes WAGES WIN (BGA-4, headline).** In a
both-feasible symmetric scenario (dominance just past `BARGAIN_DOMINANCE_MIN`, no
grudge → `trust_f = 1`), balanced power gives `w = W_FAIR = 0.5`, so the extractor's
reliable wage take per unit is `(1 − W_FAIR) × BARGAIN_WAGE_RELIABILITY = 0.5`
whereas its brute take per unit is `(1 − W_BRUTE) × BARGAIN_BRUTE_RELIABILITY =
0.45`, BEFORE brute also pays `BARGAIN_ENFORCE_COST` and (at peace)
`BARGAIN_WAR_LOSS`. Because `0.5 > 0.45` and the brute costs are strictly positive,
`E_wage > E_brute` **from the constants alone** — no branch says "prefer wages."
The acceptance test constructs exactly this scenario and asserts
`_bargain_pair_mode == BARGAIN_MODE_WAGE`. Tuning the two reliabilities so that
`(1 − W_FAIR)·BARGAIN_WAGE_RELIABILITY > (1 − W_BRUTE)·BARGAIN_BRUTE_RELIABILITY`
is the load-bearing constant relationship; keep it invariant under any retune.

- **Require** — `a`, `b` living and distinct.
- **Guarantee** — returns one `BARGAIN_MODE_*` tag; deterministic; no RNG.
- **Assert** — the returned tag is in the four-value enum.

## The driver — how M4 turns on the arc and steers M2/M3 (BG5)

**BG5 — one switch, three consumers.** When BARGAIN is enabled, `_bargain_tick`
(BG7) makes M4 the DRIVER of the lower modules. So the operator enables ONE thing,
M4 flips the two dependency gates globally and then steers per pair:

- **Global gates (enable once).** The `--bargain` launcher (BG9) sets
  `BARGAIN_ENABLED = True`, `WAGE_ENABLED = True`, and
  `CAPTURE_CHANCE = BARGAIN_CAPTURE_CHANCE` (> 0), plus `sim.bargain_enabled = True`.
  This opens M2's capture RNG gate and M3's market gate; per-pair selection below
  decides which pairs actually use them. (Default battery: all three stay at their
  shipped defaults — see BG1 top invariant.)
- **Per-pair steering** is realised through the mode map (BG1) plus ONE added branch
  in each lower module's existing read-point. M2 and M3 are otherwise UNCHANGED.

**BG5a — the M2 `_subjugate_stance` amendment (one added branch).** M2's
`_subjugate_stance` (`sandkings.py:4177`) is the exact gate `_try_capture` (:4231)
consults before the capture RNG. Add a leading BARGAIN branch so capture happens
ONLY for pairs M4 selected SUBJUGATE — preserving per-pair precision (a colony may
be SUBJUGATE toward one rival and WAGE toward another):

```
   def _subjugate_stance(self, captor_colony, victim_colony) -> bool:
+      if getattr(self, 'bargain_enabled', False):
+          return self._bargain_mode(captor_colony, victim_colony) == BARGAIN_MODE_SUBJUGATE
       if getattr(captor_colony, 'subjugation_stance', False):
           return True
       return bool(getattr(self, 'subjugation_enabled', False)
                   and getattr(captor_colony, 'at_war', False))
```

- Byte-identical when disabled: `getattr(self, 'bargain_enabled', False)` is False in
  every non-`--bargain` run (and in the default battery), so the existing two
  branches run exactly as M2 shipped.
- Chosen OVER writing a colony-wide `subjugation_stance = True` (which the scope
  record floated): a per-colony flag would let a captor enslave ANY at-war victim,
  not just its SUBJUGATE-pair, breaking per-pair precision. The mode-map read is the
  minimal edit that keeps M4's pairwise decision intact. (See Ambiguities, fork #2.)

**BG5b — the M3 `_wage_open_sweep` amendment (one added guard).** M3's
`_wage_open_sweep` (`sandkings.py:3274`) currently opens contracts for EVERY peace
pair when `WAGE_ENABLED`. Add ONE guard, right after its existing `_pair_at_war`
skip (:3283), so under BARGAIN only WAGE-selected pairs open:

```
                   if self._pair_at_war(seller_cand, buyer_cand):
                       continue    # peace only
+                  if (getattr(self, 'bargain_enabled', False)
+                          and self._bargain_mode(seller_cand, buyer_cand) != BARGAIN_MODE_WAGE):
+                      continue    # M4 routes only WAGE pairs into the market
```

- Byte-identical when disabled: `bargain_enabled` False → the guard is never taken →
  M3 behaves exactly as WG4 (and the `--wages`-only path is unchanged).
- Note this guard does NOT touch the suspend/close/settle logic — an existing
  contract on a pair M4 flips to SUBJUGATE/ANNIHILATE is closed by M3's own
  `_wage_suspend_close` (`:3243`) via `_pair_at_war` once war is entered (BG6 lets
  the war actually start for force pairs).

Contract at the driver amendments:
- **Require** — both branches are reached only when `self.bargain_enabled` is True.
- **Guarantee** — with `bargain_enabled` False, both amendments are inert and M2/M3
  are byte-identical; with it True, capture fires only on SUBJUGATE pairs and
  contracts open only on WAGE pairs.
- **Maintain** — no other M2/M3 line changes; `subjugation_stance` per-colony flag
  and the `--subjugation`/`--wages` stand-ins remain for standalone use.
- **Assert** — no pair is simultaneously SUBJUGATE for capture AND WAGE for the
  open-sweep (the mode map holds one tag per pair).

## Rewiring war entry — the ONE behaviour-changing edit (BG6)

**BG6 — gate the WAR_CHEST war declaration.** The real war-entry hook is the WAR
FOOTING block inside `step()`'s stage-5 per-colony loop, `sandkings.py:1746–1778`;
the declaration is `d.war_target[cid] = target` at **`:1759`**, taken when
`colony.maw.food_stored > enter_at` and `_select_war_target` (`:4645`) returns a
target. M4 suppresses that declaration when the bargain prefers a wage relation to
the chosen target. Edit the block at `:1756–1762`:

```
           if current_target is None:
               if colony.maw.food_stored > enter_at:
                   target = self._select_war_target(colony)
+                  if (BARGAIN_ENABLED and target is not None
+                          and self._bargain_mode_ids(cid, target) == BARGAIN_MODE_WAGE):
+                      target = None    # bargain: a wage relation nets more than war
                   d.war_target[cid] = target
                   if target is not None:
                       self._log_event(f"Colony {cid} declares war"
                                       f" on Colony {target}!")
                       ...
```

- **This is the only edit in the whole arc that changes existing control flow, and
  it is gated behind the module global `BARGAIN_ENABLED`.** With
  `BARGAIN_ENABLED = False` the new `if` short-circuits on its first operand, `target`
  is untouched, and `d.war_target[cid] = target` plus the declare-war log fire
  exactly as today → war entry is byte-for-byte identical (BGA-1 verifies with a
  war-target/declares-war golden). SUBJUGATE and ANNIHILATE targets are NOT
  suppressed — those modes WANT war, so M4 lets the existing path enter it (the
  pair then goes to combat, and for SUBJUGATE, `_subjugate_stance` (BG5a) turns
  capture on for that pair).
- **The `_betray` path (`sandkings.py:4772`) is deliberately NOT gated.** P6
  betrayal is an explicit treachery declaration, not the WAR_CHEST/grudge economic
  war entry M4 arbitrates; folding it in would broaden scope beyond the "hoard-driven
  war vs. wage" decision. (See Ambiguities, fork #1 — flagged for reviewer.)
- **Known enabled-path wrinkle:** `_select_war_target` is still CALLED before the
  suppression check, so its cosmetic feud-flare log (`:4682`) and `self._feud_logged`
  update may fire even on a suppressed (WAGE) pair. This is display-only and occurs
  ONLY on the enabled path; it does not touch war_target, RNG, or the default
  battery. (Ambiguities, fork #3.)

Contract at the war-entry edit:
- **Require** — the added `if` sits between `_select_war_target` and the
  `d.war_target[cid] = target` assignment; its first operand is the module global
  `BARGAIN_ENABLED`.
- **Guarantee** — with `BARGAIN_ENABLED` False, `target` and the assignment are
  unchanged (byte-identical war entry); with it True, a WAGE-mode target is
  suppressed to `None` (colony stands down this step) while SUBJUGATE/ANNIHILATE
  targets proceed to war.
- **Maintain** — no RNG added on any path; `_select_war_target`'s own behaviour is
  unchanged; the stand-down branch (`:1771–1778`) is untouched.
- **Assert** — after the block, `d.war_target[cid]` is either `None` or a living
  colony_id; when `BARGAIN_ENABLED` False, it equals the pre-M4 value.

## Tick placement & ordering (BG7)

**BG7 — `_bargain_tick` runs BEFORE the stage-5 loop.** Because the war-entry hook
(BG6) is inside stage 5 (`:1756`), M4's per-pair modes MUST be computed before that
loop begins — earlier than diplomacy (5b, `:1830`), wages (5c, `:1833`), and combat
(6, `:1836`). Insert a new stage **4b** in `step()` immediately before
`# 5. Food consumption and starvation` (`sandkings.py:1642`):

```
        # 3i. PALISADE ROT ...
            ...
+       # 4b. THE BARGAIN (SPEC_BARGAIN): choose per-pair enforcement mode from
+       #     net extraction BEFORE war entry / wages / capture read it
+       self._bargain_tick()

        # 5. Food consumption and starvation (DARWINIAN PRESSURE)
        for colony in self.colonies:
            ...
```

```
def _bargain_tick(self):
    """Rebuild the per-pair mode map from net-extraction EVs, then let the existing
    hooks read it (war entry BG6 in stage 5; wage open-sweep BG5b at 5c; capture
    BG5a at stage 6). Consumes NO RNG. DEFAULT-NEUTRAL when disabled."""
    if not BARGAIN_ENABLED:
        return                                    # early-out: no map, no state, no RNG
    modes = {}
    living = [c for c in self.colonies if c.is_alive()]
    for i, a in enumerate(living):
        for b in living[i + 1:]:
            modes[frozenset((a.colony_id, b.colony_id))] = self._bargain_pair_mode(a, b)
    self.bargain_modes = modes                    # replaces last step's map wholesale
```

- **Ordering rationale (satisfies decision-record coupling #7, "M4 stance before
  war entry"):** stage 4b writes the modes; stage 5 reads them at war entry (BG6);
  stage 5c reads them at the wage open-sweep (BG5b); stage 6 reads them at capture
  (BG5a). Every consumer sees the SAME map, computed from this step's power /
  endowment / grudge and last step's resolved war state (`war_target`, set at 5b
  last tick) — the standard one-step diplomacy latency already present in the sim.
- **Require** — called once per `step()`, before the stage-5 loop.
- **Guarantee** — no RNG, no colony/unit mutation; on the disabled path it does not
  even allocate the map (the getattr accessor yields empty).
- **Maintain** — the map is fully rebuilt each tick; it never carries a dead pair.
- **Assert** — after a call, every key is a two-living-colony frozenset (BG1).

## Constants (BG8)

| Constant | Value | Meaning |
|---|---|---|
| `BARGAIN_ENABLED` | `False` | master gate; False ⇒ `_bargain_tick` early-returns, no war-entry change, byte-identical battery |
| `BARGAIN_CAPTURE_CHANCE` | `0.4` | live `CAPTURE_CHANCE` the `--bargain` switch sets (mirrors `SUBJUGATION_LIVE_CHANCE`) so SUBJUGATE pairs can capture |
| `BARGAIN_V_EST` | `10.0` | estimated labor-value per free unit per planning horizon (common scale for all three EVs) |
| `BARGAIN_WAGE_RELIABILITY` | `1.0` | fraction of wage output realised (no defiance leak; peacetime) |
| `BARGAIN_BRUTE_RELIABILITY` | `0.45` | fraction of captured output realised after defiance/refusal/break-free leak — **must stay `< (1 − W_FAIR)` so wages win when both feasible (BGA-4)** |
| `BARGAIN_ENFORCE_COST` | `2.0` | value spent guarding each thrall per horizon (brute only) |
| `BARGAIN_WAR_LOSS` | `30.0` | expected attrition to ENTER/prosecute a war from peace; `0` once already at war (sunk) |
| `BARGAIN_DESTROY_WEIGHT` | `0.15` | fraction of the rival's `composite_power` valued by annihilating it |
| `BARGAIN_DOMINANCE_MIN` | `1.1` | min `composite_power` ratio for brute capture to be feasible (`E_brute = 0` below) |
| `BARGAIN_DOMINANCE_SCALE` | `1.0` | how fast the capturable pool grows with dominance past 1.0 |
| `BARGAIN_TRUST_REF` | `100.0` | negative-trust magnitude that saturates hatred to 1.0 (matches `_select_war_target`'s `/100.0`) |
| `BARGAIN_GRUDGE_FEUD_W` | `0.6` | weight of a blood-feud presence in the grudge score |
| `BARGAIN_GRUDGE_TRUST_W` | `0.6` | weight of negative diplomatic trust in the grudge score |
| `BARGAIN_GRUDGE_SENS` | `1.2` | how hard grudge collapses the wage trust-factor (`trust_f = 1 − sens·grudge`) |

New getattr-guarded sim state: `sim.bargain_enabled` (bool, default False, read by
the BG5 amendments); `sim.bargain_modes` (dict, transient, rebuilt each tick via
`_bargain_modes()`). **No new pickled unit field.** Constants live beside the M2/M3
block (`sandkings.py:295–320`). The load-bearing tuning invariant:
`(1 − W_FAIR)·BARGAIN_WAGE_RELIABILITY > (1 − W_BRUTE)·BARGAIN_BRUTE_RELIABILITY`
(here `0.5 > 0.45`) — any retune MUST preserve it or BGA-4 breaks.

## Runtime enablement (BG9 — the `--bargain` switch, supersedes SJ9 / --wages)

**BG9 — one flag turns on the whole arc.** Mirroring SJ9 (`--subjugation`,
`sandkings.py:6459/6495`) and WG12 (`--wages`, `:6462/6504`), add a `--bargain`
launcher flag. It is the TERMINAL switch: it turns on capture, wages, AND per-pair
selection together, so the operator enables one thing rather than three.

Argparse (beside the `--wages` definition, `:6462`):
```
   parser.add_argument('--bargain', action='store_true',
                       help='Enable the full inter-colony bargain: each pair '
                            'chooses annihilate / subjugate / wage by net '
                            'extraction, driving capture and the wage market '
                            '(SPEC_BARGAIN; supersedes --subjugation and --wages)')
```

Launcher block (after the `--wages` block, `:6504–6508`):
```
   if getattr(args, 'bargain', False):
       globals()['BARGAIN_ENABLED'] = True
       globals()['WAGE_ENABLED']    = True
       globals()['CAPTURE_CHANCE']  = BARGAIN_CAPTURE_CHANCE
       sim.bargain_enabled = True
       print("[CHAIN] BARGAIN ENABLED - each colony pair chooses annihilate/"
             "subjugate/wage by net extraction; wages win when force merely leaks "
             "(SPEC_BARGAIN)")
```

- With the flag OFF: `BARGAIN_ENABLED` stays `False`, `sim.bargain_enabled` is
  absent (getattr → False), `WAGE_ENABLED` stays `False`, `CAPTURE_CHANCE` stays
  `0.0`. Every gate closed; battery byte-identical.
- `--bargain` makes `--subjugation` and `--wages` redundant: it drives their gates
  itself and routes per pair. If a run passes `--bargain` alongside either, the
  bargain branches (BG5a/BG5b) take precedence because they are checked FIRST /
  gated on `bargain_enabled`.

## Persistence & inertness (BG10)

**BG10 — pickle-safe, regenerated, evolution-inert.**
- `sim.bargain_enabled` getattr-guards to False on pre-M4 pickles; it is a per-run
  launcher flag, not durable behaviour, so a resumed sim without `--bargain` is
  inert.
- `sim.bargain_modes` is TRANSIENT — rebuilt every `_bargain_tick`. It may pickle as
  an ordinary dict, but correctness never depends on the restored value: the first
  tick after resume overwrites it. A pre-M4 pickle lacking it reads empty via
  `_bargain_modes()`.
- No new pickled unit field (M4 reuses `laboring_for`/`wage_ratio`/`defiance` from
  M1/M2/M3); nothing new to inherit on respawn.
- `EnhancedSandKingsSimulation.step` (`sandkings_evolution.py:281`) adds no bargain
  state and never sets `BARGAIN_ENABLED`, so it inherits the default-neutral
  guarantee and is byte-identical to a pre-M4 run.

## Acceptance (BGA)

`tests/test_bargain.py`. Clause **BGA-1 is FIRST and gating.**

1. **DEFAULT-NEUTRAL (FIRST clause).** With `BARGAIN_ENABLED = False`: a fixed-seed
   multi-step run is byte-identical to a pre-M4 golden.
   - Patch `random.random` (and `random.sample`/`random.choice`) with a counting
     spy across the run; assert the draw count equals the pre-M4 count — i.e.
     `_bargain_tick` consumes ZERO RNG and its early-return path allocates no map.
   - Assert the **war-entry sequence is byte-identical**: capture the per-step
     `d.war_target` map and every "declares war" event; they must match the pre-M4
     golden exactly (the BG6 edit short-circuits on `BARGAIN_ENABLED`).
   - Assert M2 (`CAPTURE_CHANCE = 0`) and M3 (`WAGE_ENABLED = False`) stay inert.
2. **Stance monotone in grudge (BG3).** Fix two colonies' power and complementary
   labor endowment; sweep grudge from 0 → high (via `house_grudges` and/or negative
   trust). Assert `_bargain_pair_mode` moves monotonically
   `WAGE → SUBJUGATE → ANNIHILATE` and never regresses as grudge rises.
3. **WAGES WIN when both feasible — the efficiency-gap emergence (BG4, HEADLINE).**
   Construct a pair where BOTH wage and brute are feasible: dominance just past
   `BARGAIN_DOMINANCE_MIN`, no grudge (`trust_f = 1`), balanced power so
   `_labor_w ≈ W_FAIR`, several free units in the weaker colony. Assert
   `_bargain_pair_mode == BARGAIN_MODE_WAGE` AND that it is chosen purely from the EV
   comparison (`E_wage > E_brute`), driven by
   `(1 − W_FAIR)·BARGAIN_WAGE_RELIABILITY > (1 − W_BRUTE)·BARGAIN_BRUTE_RELIABILITY`
   plus the positive brute costs — NOT by any preference branch. Then step the sim
   with `--bargain`-equivalent globals and assert the pair does NOT enter war (BG6
   suppresses the declaration) and DOES open at least one M3 labor contract.
4. **Force chosen only under war economics (BG2b).** Show SUBJUGATE is selected only
   when brute nets most: either the pair is ALREADY at war (`BARGAIN_WAR_LOSS` sunk →
   0) or dominance is high enough that `_bargain_capturable` and thus `E_brute`
   exceeds a grudge-suppressed `E_wage`, while `E_destroy` stays below `E_brute`
   (moderate grudge). Assert that at peace with low dominance, SUBJUGATE is NOT
   chosen (its `E_brute` is dragged negative by `BARGAIN_WAR_LOSS`).
5. **Annihilate only outside the bargaining range (BG2c/BG3).** With grudge high
   enough that `trust_f → 0` (`E_wage → 0`) AND the rival powerful enough that
   `E_destroy > E_brute`, assert `_bargain_pair_mode == BARGAIN_MODE_ANNIHILATE`,
   the pair is allowed to enter war (BG6 does not suppress), and NO capture stance /
   NO wage contract is set for it.
6. **Driver plumbing — one switch, per-pair routing (BG5).** With `bargain_enabled`
   True: for a SUBJUGATE pair, `_subjugate_stance(captor, victim)` returns True and a
   broken victim unit is captured (M2 path) while the SAME captor toward a WAGE
   rival does NOT capture; for a WAGE pair, `_wage_open_sweep` opens a contract while
   a SUBJUGATE/ANNIHILATE pair opens none. Assert per-pair precision: a colony
   SUBJUGATE toward X and WAGE toward Y captures only from X and contracts only
   with Y.
7. **War-entry byte-identical when disabled (BG6).** Dedicated golden on the WAR
   FOOTING block: with `BARGAIN_ENABLED = False`, the `_select_war_target` →
   `d.war_target[cid] = target` → declare-war-log path is unchanged across a seeded
   run (subsumed by BGA-1 but asserted directly on the block for regression
   pinpointing).
8. **`BARGAIN_ENABLED = False` ⇒ battery byte-identical.** The full 38-suite Docker
   battery is green with the module at its shipped default; explicitly re-run the
   M1/M2/M3 suites (`test_labor.py`, `test_subjugation.py`, `test_wages.py`)
   unchanged.
9. **Persistence / inertness (BG10).** `sim.bargain_enabled` getattr-guards to False
   on a pre-M4 pickle; `sim.bargain_modes` is rebuilt on the first post-resume tick;
   `EnhancedSandKingsSimulation.step` sets no bargain state and is byte-identical to
   a pre-M4 run.

## Ambiguities resolved (and forks flagged for the reviewer)

- **Fork #1 — betrayal war entry (`_betray`, `:4772`) is NOT gated by M4.**
  Resolved: M4 arbitrates only the WAR_CHEST/grudge ECONOMIC war entry (`:1759`);
  P6 betrayal is an explicit treachery mechanic outside the wage-vs-force economic
  decision. A reviewer who wants betrayal to also respect a WAGE-mode preference
  should say so — it is a one-line analogous gate at `:4772`, deferred here to keep
  the behaviour-changing surface to exactly one edit. **Flagged.**
- **Fork #2 — per-pair mode map vs. colony-wide `subjugation_stance`.** The scope
  record floated "M4 sets `subjugation_stance` True." Resolved AGAINST that:
  `subjugation_stance` is per-colony and would let a captor enslave any at-war
  victim, violating M4's pairwise decision. M4 instead drives capture through a
  per-pair mode read added to `_subjugate_stance` (BG5a). Minimal (one branch) and
  precise. **Flagged** as a deviation from the record's suggested mechanism.
- **Fork #3 — cosmetic feud log on a suppressed WAGE pair.** `_select_war_target`
  runs before BG6's suppression, so its feud-flare log may fire on a pair whose war
  M4 then suppresses. Enabled-path, display-only, no state/RNG impact. Left as-is;
  **flagged** for awareness.
- **Grudge signal fusion.** `house_grudges` is a house-keyed PRESENCE map (no
  magnitude); diplomatic `trust` is the continuous signal. Resolved: fuse both —
  feud presence (binary, weighted `BARGAIN_GRUDGE_FEUD_W`) plus normalised negative
  trust (weighted `BARGAIN_GRUDGE_TRUST_W`) — so grudge has both a discrete
  blood-feud component and a continuous hostility component, and BGA-2's monotone
  sweep can be driven by either.
- **Mode direction (who extracts whom).** Resolved: the stronger colony by
  `composite_power` is the extractor/aggressor; M4 evaluates the "strong extracts
  weak" direction only (pairwise, single mode per pair), matching the record's
  "pairwise only" scope and avoiding a two-direction tie problem.
- **EV constants are illustrative but the inequality is load-bearing.** The exact
  values (`BARGAIN_V_EST`, costs, weights) are tunable; the acceptance tests
  construct scenarios to each regime. The ONE relationship that must hold under any
  retune is `(1 − W_FAIR)·BARGAIN_WAGE_RELIABILITY > (1 − W_BRUTE)·BARGAIN_BRUTE_RELIABILITY`
  (BGA-4) — this is the emergent "wages beat force because force leaks" mechanism.

## Status / Reconciliation

- **Drafted 2026-07-10.** Spec-first: implementation pending. Terminal module (M4)
  of the inter-colony arc; depends on M1 `SPEC_LABOR`, M2 `SPEC_SUBJUGATION`,
  M3 `SPEC_WAGES` (all implemented). **Closes the arc.**
- **Supersedes** the SJ9 `--subjugation` war-driven stance and the WG12 `--wages`
  always-on market: with `--bargain`, M4 drives `subjugation_stance` (via the
  per-pair mode read in `_subjugate_stance`, BG5a) and the wage open-sweep (BG5b)
  per pair by net-extraction EV, rather than "war ⇒ enslave" / "peace ⇒ always
  trade." The `--subjugation` and `--wages` flags remain for standalone module
  exercise.
- **Cross-module edits the implementer must make (all minimal, all gated on
  `sim.bargain_enabled` / `BARGAIN_ENABLED`):**
  - M2 `_subjugate_stance` (`:4177`): one added leading branch (BG5a).
  - M3 `_wage_open_sweep` (`:3274`, after the `_pair_at_war` skip at `:3283`): one
    added guard (BG5b).
  - `step()` WAR FOOTING block (`:1756–1762`): the one behaviour-changing war-entry
    gate (BG6).
  - `step()` stage 4b (before `:1642`): the `_bargain_tick` call (BG7).
  - Launcher (`:6462` argparse, after `:6508`): the `--bargain` flag + block (BG9).
- **Reuse, not reinvention:** the EV model reuses M1 `composite_power`/`W_FAIR`/
  `W_BRUTE`, M3 `_factor_endowment`/`_labor_w`/`_pair_at_war`/`_clamp01`, and the
  existing `_house_grudges`/`Diplomacy.trust` signals; the driver rides M2/M3's
  existing read-points with one branch each; the tick slots into the numbered
  `step()` sequence as stage 4b; the flag mirrors SJ9/WG12.
