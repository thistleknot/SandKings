# SPEC: Wages — the Factor Market (Peace-tier Extraction) — WG1–WG12

Module **M3** of the inter-colony political-economy arc (governing scope record:
`docs/decisions/2026-07-09-intercolony-relations-spectrum.md`). Depends ONLY on
M1 `SPEC_LABOR` (`laboring_for`, `_credit_labor`, `_extract_share`, `_deposit`,
`composite_power`, `w_bargain`, `W_BRUTE`, `W_FAIR`) and is parallel-safe with M2
`SPEC_SUBJUGATION`. M4 `SPEC_BARGAIN` is NOT specified here.

**The mechanic.** M3 is the PEACE-tier, VOLUNTARY form of the same labor-value
extraction M2 does by force. Instead of capturing a unit, a colony *hires* another
colony's factors on a small pairwise **factor market**, priced in grains, settled
by grain transfer. Three factor classes trade by comparative advantage:

1. **LABOR CONTRACTS** — a labor-rich seller rents its units' output to a buyer
   (employer) at a bargained share. The buyer gets `(1−w)·V`, the laborer's BIRTH
   colony keeps `w·V`, delivered IN-KIND through M1 `_credit_labor` (interaction A).
   `w > 0` always (voluntary, never a thrall's `W_BRUTE=0`). NO enforcement, NO
   defiance. The buyer additionally pays a grain rent to the seller (F2).
2. **TECH LICENSES** — a buyer rents ACCESS to a keeper FOREIGN gift the seller
   HOLDS (`abacus`/`watch`/`calculator`/`pi`; a member of `TECH_FOREIGN` inside
   `seller.techs`). Access is non-rival, applied through a read-only **effective-gifts
   view**, expires with the contract, and **never mutates `seller.techs`** (decision
   coupling #5). The gift itself never transfers.
3. **RESOURCE SURPLUS** — a seller ships a food/ore/wood surplus to a buyer in
   deficit, paid in grains.

> **TOP INVARIANT (default-neutral) & FIRST ACCEPTANCE CLAUSE.** The whole module is
> gated behind `WAGE_ENABLED = False`. With it False: `_labor_market_tick`
> early-returns before ANY `random.*` call or state mutation; no contract is ever
> opened; no unit ever has `wage_ratio > 0` or a market-set `laboring_for`; the M1
> `_credit_labor` amendments read their getattr defaults (`wage_ratio → W_BRUTE`,
> `_license_yield_mult → 1.0`) and are **byte-identical** to the shipped code; and
> the full 37-suite Docker regression battery is unchanged. This is WGA-1.

All new state is getattr-guarded, pickled, and inherited per the `stage`/`breached`
convention; `EnhancedSandKingsSimulation.step` stays inert.

**Sizing decision — ONE file.** The decision record notes a WG-market / WG-settlement
seam. I keep M3 in a single file because the halves are NOT independently
implementable: settlement (WG8) cannot be built or tested without the market's
contract store (WG1), endowments (WG2), and pricing (WG3). Splitting would force the
settlement implementer to stub the entire market, defeating "independently
implementable." The internal sectioning below marks the seam (WG1–WG7 = market;
WG8–WG10 = settlement) for a future split if the file grows.

---

## Data model (WG1) — market

**WG1 — the contract store and the `wage_ratio` field.**

**WG1a — `SandKing.wage_ratio`.** A NEW getattr-guarded float on the unit dataclass
(`SandKing`, beside `laboring_for` at `sandkings.py:723`), pickled:

```
wage_ratio: float = 0.0   # laborer's BIRTH-colony output share under a live labor
                          # contract; 0.0 = none (== W_BRUTE, a forced thrall or free)
```

- Every READ is getattr-guarded: `getattr(unit, 'wage_ratio', W_BRUTE)`. A pre-M3
  pickle lacks the field → reads `W_BRUTE (0.0)` → indistinguishable from a forced
  thrall or a free unit, which is correct (only a live labor contract sets it > 0).
- **This is the discriminator for interaction B (WG11b):** `wage_ratio > 0` ⇔
  *contracted, voluntary* (skip subjugation); `wage_ratio ≤ 0` with `laboring_for ≥ 0`
  ⇔ *forced thrall* (M2 owns it).

**WG1b — the contract store.** A guarded per-sim list of plain dicts (no new pickled
class — dicts pickle cleanly and are rote to construct), via an accessor mirroring
`_house_grains` (`sandkings.py:2993`):

```
def _wage_contracts(self) -> list:
    if not hasattr(self, 'wage_contracts'):
        self.wage_contracts = []
    return self.wage_contracts
```

Each contract is a dict with EXACTLY these keys:

```
{
  'kind':        str,    # 'labor' | 'license' | 'goods'
  'buyer_id':    int,    # colony_id paying grains (employer / licensee / importer)
  'seller_id':   int,    # colony_id supplying the factor (laborers' birth / owner / exporter)
  'factor':      str,    # labor: unused (''); license: a TECH_FOREIGN name; goods: 'food'|'ore:copper'|'ore:gold'|'wood'
  'w':           float,  # labor only: seller's retained output share (else 0.0)
  'volume':      int,    # labor: contracted unit count; goods: units/interval; license: 1
  'fee':         float,  # grains transferred buyer->seller per settlement interval
  'escrow':      float,  # grains the buyer has prepaid and committed (>= 0 always)
  'unit_ids':    list,   # labor: ids of the seller units under contract (else [])
  'opened_step': int,
  'last_reneg':  int,    # step of last renegotiation
  'nonviable':   int,    # consecutive non-viable settlements (WG10 close counter)
  'suspended':   bool,   # True while the pair is at war (WG10 suspend)
  'alive':       bool,   # False once closed (dropped on the next tick sweep)
}
```

Contract at the store:
- **Require** — every dict carries all keys above; `buyer_id ≠ seller_id`;
  `escrow ≥ 0` always.
- **Guarantee** — at most one *labor* and one *license(per factor)* and one
  *goods(per factor)* contract per ordered `(buyer_id, seller_id)` pair
  (de-duplicated at OPEN, WG4).
- **Maintain** — a unit's `unit_ids` membership is consistent with its
  `laboring_for == buyer_id and wage_ratio == w` while the contract is live and not
  suspended.
- **Assert** — no live labor contract references a unit whose `laboring_for` points
  elsewhere (revert on mismatch, WG10).

## Endowments & complementarity (WG2) — market

**WG2 — factor endowments and the trade gate.** Pure reads; no mutation, no RNG.

```
def _factor_endowment(self, colony) -> dict:
    """Scarce-factor vector. Pure read; getattr-guarded."""
    free = sum(1 for u in colony.units if getattr(u, 'laboring_for', -1) < 0)
    ore  = getattr(colony, 'ore', {}) or {}
    techs = getattr(colony, 'techs', set()) or set()
    return {
        'labor': float(free),
        'food':  float(colony.maw.food_stored),
        'ore':   float(ore.get('copper', 0) + ore.get('gold', 0)),
        'wood':  float(getattr(colony, 'wood', 0)),
        'tech':  float(sum(1 for t in techs if t in TECH_FOREIGN)),
    }

def _complementarity(self, seller, buyer, factor_axis: str) -> float:
    """> 0 => seller SURPLUS, buyer DEFICIT in `factor_axis` (a trade opportunity)."""
    es = self._factor_endowment(seller)[factor_axis]
    eb = self._factor_endowment(buyer)[factor_axis]
    denom = es + eb
    return 0.0 if denom <= 0.0 else (es - eb) / denom

def _marginal_value(self, colony, factor_axis: str) -> float:
    """Grain value of ONE unit of `factor_axis` to `colony`: scarce => worth more."""
    endow = self._factor_endowment(colony)[factor_axis]
    return MV_BASE / (1.0 + endow)
```

- `factor_axis` for each kind: labor → `'labor'`; license → `'tech'`; goods → the
  goods' own axis (`'food'`, `'ore'`, `'wood'`).
- A pair may open a contract on an axis only when `_complementarity(seller, buyer,
  axis) >= COMPLEMENTARITY_THRESHOLD` (WG4). Because `_marginal_value` is
  monotone-decreasing in endowment, `mv_seller < mv_buyer` whenever complementarity
  is positive — this is what makes both sides gain from trade (WGA-2).

- **Require** — `colony.maw` exists; `factor_axis ∈ {'labor','food','ore','wood','tech'}`.
- **Guarantee** — finite non-negative floats; `_marginal_value` strictly decreasing
  in endowment; no mutation.
- **Assert** — `denom > 0` before dividing in `_complementarity`.

## Pricing (WG3) — market

**WG3 — the labor share `w` and the grain price/fee.** Reuses M1 `w_bargain` and
`composite_power`; deterministic, no RNG.

**WG3a — labor share `w` (seller's retained output).** `w_bargain`'s params map:
the *extractor* is the BUYER (employer), the *laborer's birth* is the SELLER.

```
def _labor_w(self, seller, buyer) -> float:
    pr = composite_power(seller) / max(EPS_POWER, composite_power(buyer))  # birth/extractor
    endow_b = self._factor_endowment(buyer)
    desperation = _clamp01(1.0 - endow_b['labor'] / DESPERATION_LABOR_REF)  # buyer's labor hunger
    control     = _clamp01(endow_b['tech']  / CONTROL_TECH_REF)             # buyer's scarce-factor grip
    w = w_bargain(pr, desperation, control)
    return max(W_CONTRACT_MIN, min(1.0 - W_CONTRACT_MIN, w))   # voluntary & thrall-distinct
```

Behavior this guarantees (all three are acceptance clauses):
- **Weaker/desperate seller gets a LOWER `w`.** A weaker seller → `pr < 1` →
  `w_bargain` returns less → seller keeps a smaller output share.
- **A foreign-gift holder extracts BETTER terms.** If the BUYER holds a gift, its
  `endow_b['tech'] > 0` → higher `control` → lower `w` (buyer keeps more), AND its
  `composite_power` is higher (`POWER_TECH_FOREIGN`) → lower `pr` → lower `w`. Both
  push the buyer's terms up versus an equal-military non-holder (WGA-4).
- `w` is clamped into `[W_CONTRACT_MIN, 1−W_CONTRACT_MIN]`, so a wage laborer ALWAYS
  has `wage_ratio > 0` (never mistaken for a `W_BRUTE=0` thrall — WG11b).

**WG3b — grain fee (buyer → seller per settlement interval).**

```
def _factor_price(self, seller, buyer, factor_axis: str) -> float:
    mv_s = self._marginal_value(seller, factor_axis)   # seller's reservation (low: abundant)
    mv_b = self._marginal_value(buyer,  factor_axis)   # buyer's willingness (high: scarce)
    pr = composite_power(seller) / max(EPS_POWER, composite_power(buyer))
    share = _clamp01(WAGE_POWER_SHARE_BASE + WAGE_POWER_SHARE_SENS * (pr - 1.0))
    return mv_s + share * (mv_b - mv_s)     # seller reservation .. buyer willingness
```

- The unit price sits strictly BETWEEN the two reservations whenever complementarity
  holds (`mv_s < price < mv_b`), so buyer surplus (`mv_b − price`) and seller surplus
  (`price − mv_s`) are BOTH positive → both strictly gain (WGA-2). `share` tilts the
  split toward the stronger party (higher `pr` → seller captures more).
- Per-kind `fee`:
  - **labor:** `fee = WAGE_GRAIN_RATE * price * volume` where `price =
    _factor_price(seller, buyer, 'labor')`, `volume = len(unit_ids)`. (The employer
    already receives `(1−w)·V` in-kind via `_credit_labor`; this grain rent is the
    F2 transfer that makes the seller strictly gain.)
  - **license:** `fee = LICENSE_FEE_BASE * _factor_price(seller, buyer, 'tech') /
    MV_BASE` (a base rent scaled by how scarce tech is to the buyer), `volume = 1`.
  - **goods:** `fee = _factor_price(seller, buyer, axis) * volume`, `volume =
    min(GOODS_VOLUME_CAP, floor(surplus_units))`.

- **Require** — complementarity already passed at OPEN; both colonies alive.
- **Guarantee** — `fee ≥ 0`; `mv_s ≤ price ≤ mv_b`; pure (no RNG, no mutation).
- **Assert** — `price >= mv_s` and `price <= mv_b`.

## Contract lifecycle — OPEN (WG4) — market

**WG4 — opening a contract.** In `_labor_market_tick` (WG11a), for each unordered
PEACE pair `(A, B)` (not at war with each other — see WG10 predicate) and each factor
axis, at most one new contract per tick:

```
for each candidate (seller, buyer, kind, factor_axis):
    if not WAGE_ENABLED: return                      # (never reached; tick already gated)
    if self._pair_at_war(seller, buyer): continue    # peace only
    if self._has_contract(buyer, seller, kind, factor):  continue   # de-dup (WG1 Guarantee)
    comp = self._complementarity(seller, buyer, factor_axis)
    if comp < COMPLEMENTARITY_THRESHOLD: continue    # no trade opportunity
    if kind == 'license' and factor not in {t for t in getattr(seller,'techs',set())
                                            if t in TECH_FOREIGN}: continue  # seller must HOLD it
    fee = <WG3b per-kind fee>
    if getattr(buyer, 'currency', 0.0) < fee: continue   # LIQUIDITY: cash-poor cannot hire (F2)
    # PREPAY escrow one interval up front (non-negativity, WG8)
    buyer.currency -= fee
    contract = { ...WG1b dict..., 'escrow': fee, 'fee': fee, 'w': w_or_0, 'suspended': False,
                 'alive': True, 'nonviable': 0, 'opened_step': self.step_count,
                 'last_reneg': self.step_count }
    if kind == 'labor':
        contract['w'] = self._labor_w(seller, buyer)
        contract['unit_ids'] = <pick up to LABOR_MAX_UNITS free seller units (WG5)>
        contract['volume']   = len(contract['unit_ids'])
        <WG5: bind those units: laboring_for=buyer_id, wage_ratio=w>
    self._wage_contracts().append(contract)
    self._log_event(f"House {seller} contracts {kind} to House {buyer}")
```

- Candidate ENUMERATION is deterministic (iterate `self.colonies` in order, axes in a
  fixed tuple); no RNG is consumed at OPEN. (If a later increment wants stochastic
  match selection it must draw ONLY after WG4's deterministic gates and only when
  `WAGE_ENABLED`, mirroring M2's RNG-ordering discipline.)
- **Require** — `WAGE_ENABLED` True; pair at peace; buyer solvent for one interval.
- **Guarantee** — opened contract has `escrow == fee` prepaid; buyer's `currency`
  never goes negative; labor units are bound per WG5.
- **Maintain** — grains conserved: `buyer.currency` decreased by exactly `fee`, held
  in `escrow` (no mint).
- **Assert** — `buyer.currency >= 0` after prepay; `contract['escrow'] == fee`.

## Labor contracts & the `_credit_labor` amendment (WG5) — market + M1 amendment

**WG5 — binding labor and redirecting output.** On OPEN of a `kind='labor'` contract,
select up to `LABOR_MAX_UNITS` FREE seller units and bind them:

```
def _bind_labor(self, contract, seller, buyer):
    picked = []
    for u in seller.units:
        if len(picked) >= LABOR_MAX_UNITS: break
        if getattr(u, 'laboring_for', -1) < 0:            # only free units
            u.laboring_for = buyer.colony_id              # virtual: NO migration (F3)
            u.wage_ratio   = contract['w']                # > 0 => voluntary (WG11b)
            picked.append(id(u) if not hasattr(u,'uid') else u.uid)
    return picked   # -> contract['unit_ids']
```

(Use whatever stable per-unit identity the codebase already has for `unit_ids`; if
none, store the unit objects directly in a parallel `contract['_units']` list —
Haiku: prefer an existing id field, else the object list. The identity is used only
to revert the SAME units on suspend/close, WG10.)

**WG5-M1 — the controlled M1 `_credit_labor` amendment (interaction A).** `_credit_labor`
(`sandkings.py:3907`) currently hardcodes the brute share and applies no productivity
multiplier. TWO getattr-guarded edits, BOTH default-neutral:

1. At the FIRST line of the method body (before the `ext_id`/self-heal block), scale
   the produced amount by the acting colony's licensed productivity:
```
   amount = amount * self._license_yield_mult(colony)   # WG6: 1.0 default => byte-identical
```
2. Replace the hardcoded thrall-path share at `sandkings.py:3948`:
```
   -   w = W_BRUTE
   +   w = getattr(unit, 'wage_ratio', W_BRUTE)          # A: wage laborer splits at its contract w
```

- Default-neutral proof: with `WAGE_ENABLED=False`, `_license_yield_mult` returns
  `1.0` (WG6) → `amount` unchanged; no unit has `wage_ratio` set → `getattr(...,
  W_BRUTE)` returns `0.0` → the thrall path is exactly today's `w = W_BRUTE`. Both
  edits are byte-identical at their getattr defaults. A forced M2 thrall (no
  `wage_ratio` set) keeps `w = 0.0`; a wage laborer (bound at WG5) splits at its
  `w > 0`, so the buyer/extractor gets `(1−w)·V` and the birth colony `w·V` — exactly
  interaction A, reusing M1's existing `_extract_share`/`_deposit` split unchanged.

Contract at the amended `_credit_labor`:
- **Require** — `colony.colony_id == unit.colony_id`; `amount ≥ 0`; `kind` is one of
  the six sink tags; `getattr(unit,'wage_ratio',W_BRUTE) ∈ [0,1]`.
- **Guarantee** — `extractor_share + birth_share == amount` EXACTLY (after the yield
  scale); at `wage_ratio=W_BRUTE` and `_license_yield_mult==1.0` the method is
  byte-identical to the pre-M3 code; grains are NEVER minted here (only goods sinks).
- **Maintain** — no unit migration (virtual); `colony_id` untouched;
  `_license_yield_mult` and the `wage_ratio` read consume no RNG.
- **Assert** — after a thrall/wage deposit, extractor and birth shares are
  non-negative and sum to the (possibly yield-scaled) `amount`.

## Tech licenses & the effective-gifts view (WG6) — market

**WG6 — non-rival access, never mutate the holding.** The foreign-gift holding is
`{t for t in colony.techs if t in TECH_FOREIGN}`; there is NO `colony_foreign` field.
A license grants the buyer the gift's productivity effect via a READ-ONLY view.

```
def _effective_foreign_techs(self, colony) -> set:
    """Own foreign gifts UNION gifts licensed-IN. Read-only; colony.techs untouched."""
    own = {t for t in getattr(colony, 'techs', set()) if t in TECH_FOREIGN}
    if not WAGE_ENABLED:
        return own                                   # default-neutral: no view expansion
    licensed = {c['factor'] for c in self._wage_contracts()
                if c['kind'] == 'license' and c['buyer_id'] == colony.colony_id
                and c['alive'] and not c['suspended']}
    return own | licensed

def _license_yield_mult(self, colony) -> float:
    """Productivity multiplier from LICENSED-IN foreign gifts only. 1.0 for owners
    and when disabled. Applied at the amended _credit_labor (WG5-M1)."""
    if not WAGE_ENABLED:
        return 1.0
    own = {t for t in getattr(colony, 'techs', set()) if t in TECH_FOREIGN}
    rented = self._effective_foreign_techs(colony) - own    # licensed-in only
    mult = 1.0
    for t in rented:
        mult *= LICENSE_TECH_MULT.get(t, 1.0)
    return mult
```

- **The owner is unaffected:** the owner's `rented` set is empty (it owns, not rents)
  → `_license_yield_mult(owner) == 1.0`; the owner's `machine_arc`, `controllers`, and
  forecast/prediction effects (which read `colony.techs`/`controllers` at
  `_predict_tool` `:3028`, `_score_forecasts` `:2999`) are untouched because
  `colony.techs` is NEVER written by M3 (coupling #5).
- **Expiry:** on suspend or close (WG10) the license leaves the effective view (its
  contract is `suspended`/`alive=False`) → `_license_yield_mult` drops back to `1.0`
  → the renter's boost vanishes with no residue. The renter's own `colony.techs`
  never changed, so nothing to unwind.
- **Discrete-good caveat:** the yield multiplier is observable on CONTINUOUS kinds
  (`food`,`crop`, via `maw.eat`); on DISCRETE kinds (`ore:*`,`salvage`,`wood`) M1's
  `_deposit` does `int(amount)`, so a `1.2×` on a single item rounds back to `1`.
  WGA-6 tests the license effect on `food` (continuous) to make it observable.

- **Require** — `colony` may lack `techs` (getattr-guarded).
- **Guarantee** — `colony.techs` is never mutated by either function; returns
  `own` / `1.0` exactly when `WAGE_ENABLED` is False; multiplier ≥ 1.0.
- **Maintain** — read-only view; keeper-ladder + augment/controller state intact.
- **Assert** — after any tick, `{t for t in colony.techs if t in TECH_FOREIGN}` for
  every colony equals its pre-tick own-set (holding immutable — WGA-6).

## Resource surplus (WG7) — market

**WG7 — goods shipments.** A `kind='goods'` contract moves `volume` units of `factor`
(`'food'|'ore:copper'|'ore:gold'|'wood'`) from seller to buyer each settlement
interval, paid by the grain fee (WG3b). Delivery reuses M1 `_deposit` in reverse (a
guarded debit on the seller, credit on the buyer), NOT a physical courier:

```
def _ship_goods(self, contract, seller, buyer):
    axis_kind = contract['factor']
    v = contract['volume']
    if not self._seller_has(seller, axis_kind, v):   # seller solvent in the good
        return False                                 # non-viable this interval (WG10)
    self._debit(seller, axis_kind, v)                # mirror of _deposit; never below 0
    self._deposit(buyer, axis_kind, v)               # reuse M1 _deposit (sandkings.py:3887)
    return True
```

`_debit(target, kind, amount)` is the exact inverse of M1 `_deposit`, guarded so no
sink goes negative (`ore[k] = max(0, ore[k]-n)`, `maw.food_stored = max(0.0,
food_stored - n)`, `wood = max(0, wood-n)`). Goods are POSITIVE-SUM across the pair
(each side values its traded good differently — WG2), grains ZERO-SUM (WG8).

- **Require** — seller holds ≥ `volume` of the good.
- **Guarantee** — buyer gains exactly what the seller loses (goods conserved); no
  sink negative.
- **Maintain** — grain settlement is separate (WG8); this moves only goods.
- **Assert** — post-ship, seller's sink ≥ 0.

## Settlement (WG8) — settlement seam

**WG8 — grain transfer, escrow/prepay, non-negativity (F2).** Every
`SETTLEMENT_INTERVAL` ticks, in `_labor_market_tick`, for each live non-suspended
contract:

```
def _settle(self, contract):
    buyer  = self._colony_by_id(contract['buyer_id'])
    seller = self._colony_by_id(contract['seller_id'])
    if buyer is None or seller is None or not buyer.is_alive() or not seller.is_alive():
        contract['alive'] = False; return          # dead party -> close (WG10)
    # 1. PAY OUT the escrow the buyer prepaid last interval (grains: transfer, no mint)
    pay = contract['escrow']
    contract['escrow'] = 0.0
    seller.currency = getattr(seller, 'currency', 0.0) + pay
    self._house_grains()[self._house_name(seller)] = \
        self._house_grains().get(self._house_name(seller), 0.0) + pay   # mirror CU1 ledger
    # 2. deliver this interval's goods (WG7) if a goods contract
    delivered = True
    if contract['kind'] == 'goods':
        delivered = self._ship_goods(contract, seller, buyer)
    # 3. PREPAY next interval (liquidity gate; non-negativity via refuse-if-poor)
    fee = contract['fee']
    if getattr(buyer, 'currency', 0.0) >= fee and delivered:
        buyer.currency -= fee
        contract['escrow'] = fee
        contract['nonviable'] = 0
    else:
        contract['nonviable'] = contract['nonviable'] + 1   # WG10 close counter
```

- **Grains are transferred, never minted:** the ONLY grain mint in the sim is
  `_score_forecasts` (`:2999`); WG8 moves existing grains buyer→seller and mirrors
  the per-house ledger (`_house_grains`, `:2993`) so surfacing stays consistent. Sum
  of `currency` across colonies + all `escrow` is invariant across a settlement
  (WGA-7).
- **Non-negativity:** a buyer pays ONLY from prepaid `escrow`, and prepays the NEXT
  interval only if solvent; `buyer.currency` never goes below 0. A cash-poor buyer
  simply accrues `nonviable` and is closed (WG10). This is the F2 liquidity
  constraint: a colony that cannot afford the factor cannot hold the contract.
- **Settlement medium justification (envoy vs direct):** M3 settles by DIRECT grain
  transfer, NOT the `_dispatch_gift`/`_deliver_gift` envoy courier (`:4316`/`:4359`).
  Rationale: grains (`currency`) are an ABSTRACT non-spatial ledger, not a physical
  carried good like the envoy's food/gold; routing them through a spatial courier
  adds RNG-touching pathing and a loss-in-transit surface that would threaten the
  byte-identical guarantee and complicate non-negativity. Direct transfer is the
  simpler mechanism that respects non-negativity. (Goods shipments, WG7, are likewise
  a direct debit/credit — the visible-fidelity courier is a PARKED follow-up, matching
  F3's parked physical migration.)

- **Require** — called at `step_count % SETTLEMENT_INTERVAL == 0`; contract live,
  not suspended.
- **Guarantee** — grains conserved (transfer, no mint); `buyer.currency ≥ 0`
  throughout; per-house ledger mirrored.
- **Maintain** — escrow invariant: paid-out escrow this interval was prepaid last
  interval; total grains + escrow conserved.
- **Assert** — `buyer.currency >= 0` and `contract['escrow'] >= 0` after `_settle`.

## Renegotiation (WG9) — settlement seam

**WG9 — sticky `w`/fee with periodic renegotiation (F1).** `w` and `fee` are STICKY:
recomputed ONLY every `RENEGOTIATE_INTERVAL` ticks (not every tick — avoids the
price-thrash coupling into `_resonance_tick`, coupling #6). At a renegotiation step,
for each live non-suspended contract:

```
if self.step_count - contract['last_reneg'] >= RENEGOTIATE_INTERVAL:
    seller = self._colony_by_id(contract['seller_id']); buyer = self._colony_by_id(contract['buyer_id'])
    contract['fee'] = <WG3b per-kind fee recomputed from current endowments/power>
    if contract['kind'] == 'labor':
        neww = self._labor_w(seller, buyer)
        contract['w'] = neww
        for u in <the contract's bound units>:       # re-stamp the live share
            if getattr(u, 'laboring_for', -1) == buyer.colony_id:
                u.wage_ratio = neww
    contract['last_reneg'] = self.step_count
```

- Renegotiation runs BEFORE settlement in the same tick (stage ordering, coupling #7:
  "w renegotiation before settlement").
- **Require** — contract live, not suspended.
- **Guarantee** — between renegotiations `w`/`fee` are unchanged (sticky); at a
  renegotiation they track current endowments/power via WG3.
- **Maintain** — bound units' `wage_ratio` equals the contract `w` after re-stamp.
- **Assert** — `contract['w'] > 0` for labor (still voluntary).

## Suspend on war / close on non-viability or death (WG10) — settlement seam

**WG10 — pause under war, free laborers, close when dead or unviable.**

```
def _pair_at_war(self, a, b) -> bool:
    d = self._diplomacy()
    return (d.war_target.get(a.colony_id) == b.colony_id
            or d.war_target.get(b.colony_id) == a.colony_id)

def _revert_labor(self, contract):
    """Free every bound laborer WITHOUT any subjugation/defiance ever applying."""
    for u in <the contract's bound units>:
        if getattr(u, 'laboring_for', -1) == contract['buyer_id']:
            u.laboring_for = -1        # back to free; production reverts via _credit_labor free path
            u.wage_ratio   = 0.0       # no residual share
    contract['unit_ids'] = []
```

Per tick, for each contract:
- **SUSPEND (war entry):** if `_pair_at_war(buyer, seller)` and not already suspended:
  set `contract['suspended'] = True`; `_revert_labor` (laborers go free, `wage_ratio→0`);
  the license leaves the effective view automatically (WG6 checks `not suspended`);
  refund remaining `escrow` to the buyer (`buyer.currency += escrow; escrow = 0.0`).
  The contract PAUSES (not closed) — it may RESUME when peace returns (re-bind labor,
  re-prepay) at the next OPEN sweep.
- **RESUME (peace returns):** a suspended contract whose pair is no longer at war and
  whose parties are alive is re-activated by the OPEN sweep (WG4) treating it as a
  fresh candidate if complementarity still holds; the stale suspended record is closed
  first (`alive=False`) to avoid duplicates.
- **CLOSE (dead party or persistent non-viability):** if either party is dead, OR
  `contract['nonviable'] >= NONVIABLE_LIMIT`: `_revert_labor`; refund `escrow` to the
  buyer if buyer alive; set `contract['alive'] = False`. A sweep drops `alive=False`
  records: `self.wage_contracts = [c for c in self._wage_contracts() if c['alive']]`.

**Critical (interaction B guarantee):** because a wage laborer is skipped by
`_subjugation_tick` (WG11b), it NEVER accrues `defiance` and is NEVER coerced. So war
suspension frees it cleanly with no M2 defiance ever having applied — the laborer just
reverts to free and its output returns to its birth colony via `_credit_labor`'s free
path (WGA-8).

- **Require** — called once per tick within `_labor_market_tick`.
- **Guarantee** — a suspended/closed labor contract leaves every bound unit free
  (`laboring_for=-1`, `wage_ratio=0`); escrow is refunded (grains conserved); no unit
  is left pointing at a stale buyer.
- **Maintain** — grains conserved across suspend/close (refund, not mint/burn).
- **Assert** — after WG10, no live+unsuspended contract references a dead colony; no
  freed unit has `wage_ratio > 0`.

## Tick placement & subjugation guard (WG11) — market + M2 amendment

**WG11a — `_labor_market_tick` placement.** Insert in `step()` as stage **5c**,
AFTER `_resolve_diplomacy()` (5b, `sandkings.py:1800`) and BEFORE `# 6. Combat
resolution` (`:1802`), so it reads THIS step's resolved war/truce state (`at_war` set
at `:1748`, diplomacy at `:1800`) before combat:

```
        # 5b. DIPLOMACY (SPEC_POLITICS)
        self._resolve_diplomacy()

        # 5c. WAGES (SPEC_WAGES): factor market — renegotiate, settle, open, suspend/close
        self._labor_market_tick()

        # 6. Combat resolution
        self._resolve_conflicts()
```

`_labor_market_tick` MUST early-out before any RNG/state when disabled:

```
def _labor_market_tick(self):
    if not WAGE_ENABLED:
        return                         # DEFAULT-NEUTRAL: no RNG, no state — byte-identical
    # order per coupling #7: renegotiate -> settle -> open -> suspend/close -> sweep
    if self.step_count % RENEGOTIATE_INTERVAL == 0:  self._wage_renegotiate()   # WG9
    if self.step_count % SETTLEMENT_INTERVAL == 0:   self._wage_settle_all()    # WG8
    self._wage_open_sweep()                                                     # WG4
    self._wage_suspend_close()                                                  # WG10
    self.wage_contracts = [c for c in self._wage_contracts() if c['alive']]     # sweep
```

Production (`_credit_labor` deposits in unit AI, `:2080/:4143/:5447/:5482`) runs in
the 5-loop BEFORE stage 5c, so a contract opened at 5c takes effect on the NEXT step's
production — consistent with sticky contracts.

**WG11b — the subjugation guard (interaction B, M2 `_subjugation_tick` amendment).**
M2's `_subjugation_tick` (`sandkings.py:4797`) gathers EVERY unit with
`laboring_for >= 0` (line 4808–4809) — which would WRONGLY sweep voluntary wage
laborers into defiance/coercion. Add ONE discriminator to the comprehension:

```
   thralls = [u for c in self.colonies for u in c.units
-             if getattr(u, 'laboring_for', -1) >= 0]
+             if getattr(u, 'laboring_for', -1) >= 0
+             and getattr(u, 'wage_ratio', W_BRUTE) <= 0.0]   # WG11b: skip VOLUNTARY wage labor
```

- **Discriminator = `wage_ratio > 0`.** Chosen over a separate `contracted` bool for
  DRY: `wage_ratio` is already load-bearing (interaction A / WG5-M1) and WG3a clamps a
  contracted `w ≥ W_CONTRACT_MIN > 0`, so `wage_ratio > 0` is an EXACT partition —
  forced M2 thralls always carry `W_BRUTE=0.0` (never set to a positive share), wage
  laborers always carry `w > 0`. (Rejected alternative: a `contracted` flag — an extra
  field with no added discriminating power.)
- **M2 unchanged when no contracts exist:** with `WAGE_ENABLED=False`, no unit ever
  has `wage_ratio > 0`, so `getattr(u,'wage_ratio',W_BRUTE) <= 0.0` is TRUE for every
  unit → the comprehension is byte-identical to M2's, and M2's own default-neutral
  gate (`CAPTURE_CHANCE=0`) still holds. The guard only ever EXCLUDES units M3 created.

- **Require** — the guard is applied only to the thrall-gather comprehension.
- **Guarantee** — voluntary wage laborers (`wage_ratio > 0`) are never processed by
  `_subjugation_tick` → never accrue defiance, never coerced; forced thralls
  (`wage_ratio == 0`, `laboring_for ≥ 0`) are processed exactly as M2 today.
- **Maintain** — M2 behavior byte-identical when no wage contracts exist.
- **Assert** — every unit `_subjugation_tick` touches has `getattr(u,'wage_ratio',
  W_BRUTE) <= 0.0`.

## Constants, runtime enablement & persistence (WG12)

**WG12 — constants.**

| Constant | Value | Meaning |
|---|---|---|
| `WAGE_ENABLED` | `False` | master gate; False ⇒ `_labor_market_tick` early-returns, no contracts, byte-identical battery |
| `RENEGOTIATE_INTERVAL` | `200` | ticks between sticky `w`/fee renegotiations (F1) |
| `SETTLEMENT_INTERVAL` | `50` | ticks between grain settlements + goods shipments |
| `COMPLEMENTARITY_THRESHOLD` | `0.30` | min `(surplus−deficit)/(sum)` on a factor axis to open a contract |
| `W_CONTRACT_MIN` | `0.05` | floor/ceiling clamp on a labor `w` (keeps it voluntary and `> 0`, thrall-distinct) |
| `LICENSE_FEE_BASE` | `2.0` | base grain rent per licensed foreign gift per settlement interval |
| `LICENSE_TECH_MULT` | `{'abacus':1.05,'watch':1.10,'calculator':1.20,'pi':1.40}` | per-gift labor-yield multiplier granted to the RENTER (via WG6) |
| `WAGE_GRAIN_RATE` | `0.5` | fraction of the marginal-value price paid as the labor grain rent |
| `WAGE_POWER_SHARE_BASE` | `0.5` | baseline split of trade surplus (even) |
| `WAGE_POWER_SHARE_SENS` | `0.25` | how much relative power tilts the surplus split |
| `MV_BASE` | `10.0` | marginal-value numerator (`MV = MV_BASE/(1+endowment)`) |
| `DESPERATION_LABOR_REF` | `8.0` | buyer free-unit count that saturates labor-desperation to 0 |
| `CONTROL_TECH_REF` | `2.0` | buyer foreign-gift count that saturates scarce-factor control to 1 |
| `LABOR_MAX_UNITS` | `4` | max seller units bound per labor contract |
| `GOODS_VOLUME_CAP` | `5` | max goods units shipped per settlement interval |
| `NONVIABLE_LIMIT` | `3` | consecutive non-viable settlements before a contract closes |
| `EPS_POWER` | `1e-9` | denominator guard for `composite_power` ratios |
| `WAGE_LIVE_ENABLED` | `False` | runtime-flag mirror (see WG12 runtime enablement) |

New pickled/getattr-guarded state: `SandKing.wage_ratio` (float, default `0.0`);
`TerrariumSimulation.wage_contracts` (list of dicts, default `[]` via `_wage_contracts`).
Helpers `_clamp01`, `_debit`, `_seller_has`, `_has_contract`, `_house_name` (existing)
are pure/guarded and consume no RNG.

**WG12 runtime enablement (interim, until M4 — mirrors M2 SJ9).** A `--wages`
launcher flag exercises the market before M4 without disturbing the default-neutral
gate: the module `WAGE_ENABLED` stays `False` (battery byte-identical); `--wages`
flips the LIVE module global `WAGE_ENABLED = True` for that run and sets
`sim.wage_enabled = True`. With the flag off, `WAGE_ENABLED` is `False` and every gate
is closed. (When M4 `SPEC_BARGAIN` lands it drives mode/enablement per pair and
supersedes the flag.)

**WG12 surfacing (display-only).** `build_state` MAY expose per-colony
`contracts_out`/`contracts_in` counts and `grains` (`currency`); no control flow keys
off surfaced values; surfacing consumes no RNG and mutates no sim state.

## Acceptance (WGA)

`tests/test_wages.py`:

1. **DEFAULT-NEUTRAL (FIRST clause).** With `WAGE_ENABLED = False`: a fixed-seed
   multi-step run is byte-identical to a pre-M3 golden — the RNG stream and the full
   37-suite regression battery match exactly. Assert specifically that
   `_labor_market_tick` consumes ZERO `random.*` draws and opens ZERO contracts, and
   that the amended `_credit_labor` is byte-identical: with no `wage_ratio` set,
   `getattr(unit,'wage_ratio',W_BRUTE)==0.0` and `_license_yield_mult(colony)==1.0`
   for every colony (patch `random.random` with a counting spy; assert count ==
   pre-M3 count).
2. **Labor contract redirects output; both strictly gain; grains transferred not
   minted.** With `WAGE_ENABLED=True`, a peace pair whose complementarity on `'labor'`
   ≥ threshold opens a labor contract at `w > 0`; the bound seller units get
   `laboring_for = buyer_id`, `wage_ratio = w`; a `_credit_labor('food', V)` deposit
   splits `(1−w)·V` to the buyer and `w·V` to the birth colony (conservation exact);
   after a settlement, `buyer.currency` fell and `seller.currency` rose by the SAME
   `fee` (Σ currency + Σ escrow invariant; `grains_minted` unchanged); and in
   scarcity-weighted value BOTH colonies are strictly better off (`price` strictly
   between `mv_seller` and `mv_buyer`).
3. **Weaker/desperate party gets a lower `w`.** Holding the buyer fixed, a seller with
   lower `composite_power` (fewer units/wealth) receives a strictly lower
   `_labor_w(seller, buyer)` than a stronger seller; a buyer with higher labor-deficit
   (lower free-unit count) yields a higher `w` to the seller.
4. **Gift-holder extracts better terms at equal military power.** Two buyers with
   EQUAL `POWER_MILITARY_UNIT` contribution (same unit count) but one HOLDING a
   `TECH_FOREIGN` gift: the gift-holder gets a strictly LOWER `w` (keeps more output)
   than the non-holder — via both higher `control` and higher `composite_power`.
5. **Comparative advantage.** A labor-rich / tech-poor colony (high `'labor'`
   endowment, zero foreign tech) SELLS a labor contract to and BUYS a tech license
   from a tech-rich / labor-poor colony — both directions open in the same peace pair
   under the complementarity gate.
6. **License multiplier applies to the renter, expires with the contract, owner &
   holding untouched.** Under a live license of `factor='calculator'`,
   `_license_yield_mult(renter) == LICENSE_TECH_MULT['calculator']` and a renter
   `food` deposit is scaled accordingly; the OWNER's `_license_yield_mult == 1.0` and
   its `_predict_tool`/forecast effects are unchanged; `{t for t in colony.techs if t
   in TECH_FOREIGN}` is IDENTICAL before and after (holding NEVER mutated); on close,
   `_license_yield_mult(renter)` returns to `1.0` with no residue.
7. **Grain non-negativity & conservation.** Across opens, settlements, suspends, and
   closes, `colony.currency >= 0` for every colony at every step; Σ(`currency`) +
   Σ(contract `escrow`) is invariant except for `_score_forecasts` mints; a buyer that
   cannot afford `fee` opens/renews NOTHING (liquidity constraint).
8. **War suspends contracts and frees laborers WITHOUT any M2 defiance.** When a peace
   pair with a live labor contract enters war (`_pair_at_war` True), the contract
   SUSPENDS, every bound laborer reverts to `laboring_for=-1`, `wage_ratio=0`, and
   escrow is refunded to the buyer; assert those laborers NEVER accrued `defiance`
   (they were skipped by `_subjugation_tick` throughout — WG11b) and were never
   coerced; production reverts to the birth colony via `_credit_labor`'s free path.
9. **M2 unchanged when no contracts exist.** With `WAGE_ENABLED=True` but no labor
   contracts (only M2 thralls at `CAPTURE_CHANCE=1.0`), `_subjugation_tick` processes
   thralls exactly as `tests/test_subjugation.py` expects — the `wage_ratio<=0` guard
   excludes nothing, because thralls carry `wage_ratio==0` (`W_BRUTE`).
10. **Persistence & inertness.** `wage_ratio` and `wage_contracts` pickle and
    getattr-guard (pre-M3 pickles read `0.0` / `[]`); `EnhancedSandKingsSimulation.step`
    opens no contracts and is byte-identical to a pre-M3 run.

## Ambiguities resolved

- **No `colony_foreign` field.** The decision record and task refer to `colony_foreign`;
  the actual per-colony foreign-gift holding is `{t for t in colony.techs if t in
  TECH_FOREIGN}` (`GIFT_LADDER`), and the gift's EFFECT flows through `colony.techs`,
  `colony.machine_arc`, and `colony.controllers`. "Never mutate `colony_foreign`" is
  realized as "never write `colony.techs`/`machine_arc`/`controllers`"; the license
  effect is delivered by the read-only `_effective_foreign_techs` view + a labor-yield
  multiplier (WG6), leaving the keeper-ladder/augment/controller subsystems intact.
- **Two instruments for a labor wage (in-kind split AND grain rent).** Interaction A
  requires the OUTPUT to split in-kind via `_credit_labor` (buyer gets `(1−w)V`,
  birth gets `wV`); F2 requires a grain TRANSFER. Both apply: the in-kind split is the
  employer's take; the grain rent (WG3b/WG8) is what makes the SELLER strictly gain
  and satisfies "grains transferred not minted." Both-sides-gain is proven with
  scarcity-weighted marginal values (WG2), since a pure shared linear metric under
  transfer is zero-sum — gains-from-trade require the differing per-colony valuations.
- **Settlement medium (direct transfer, not the envoy courier).** Grains are an
  abstract non-spatial ledger; routing them through the `_dispatch_gift` spatial
  courier would add RNG-touching pathing and a loss surface that threatens the
  byte-identical guarantee and complicates non-negativity. M3 uses direct
  `currency` transfer with prepaid escrow (WG8); goods use a direct debit/credit
  (WG7). The visible-fidelity courier is a PARKED follow-up (matches F3's parked
  physical migration).
- **Subjugation discriminator = `wage_ratio > 0`.** Chosen over a `contracted` flag
  for DRY (WG11b); WG3a's `w ≥ W_CONTRACT_MIN` clamp makes it an exact partition from
  `W_BRUTE=0` thralls.
- **Discrete-good yield rounding.** The license multiplier is observable only on
  continuous kinds (`food`/`crop`); discrete sinks (`ore:*`,`salvage`,`wood`) `int()`
  back to whole items. WGA-6 tests on `food`. A fractional-carry ledger for discrete
  goods is out of scope (matches M1's discrete-split note).

## WG13 — Liquidity floor (post-playtest reconciliation)

A 3000-step enabled playtest revealed the market never transacted: grains mint only
from forecast accuracy (`_score_forecasts`), and colonies forecast their own food
too poorly to earn any, so `currency` stayed 0 and the WG4 liquidity gate always
failed. WG13 adds a bootstrap floor: each `SETTLEMENT_INTERVAL`, inside
`_labor_market_tick` (so it is reached ONLY when `WAGE_ENABLED` — default-neutral
preserved), any living colony with `currency < ECON_GRAIN_FLOOR (60.0)` is topped up
to that floor. This seeds initial liquidity (and respawned colonies); trade then
recirculates grains by transfer, diverging balances by comparative advantage. NOTE:
this is a bootstrap, not a real grain economy — tying grain income to
production/population is a deferred CU-scope improvement (see docs/GOD_REVIEW_economy).

Two implementation bugs the same playtest surfaced were also fixed (code now matches
this spec's intent): (1) WG4/WG5 labor binding now happens ONLY after the liquidity
gate commits the contract (`_select_free_labor` selects without mutating;
`_bind_selected_labor` binds post-commit) — the prior code bound during fee
computation and leaked orphaned bound units on a liquidity skip. (2) WG9
`_wage_renegotiate` now routes a goods contract's factor through `_goods_axis`
(ore:* → 'ore') before `_factor_price`, matching WG4's mapping (it previously passed
the raw sink name and raised KeyError once goods contracts could open).

## Status / Reconciliation

- **Drafted 2026-07-10; implemented + playtest-hardened same day.** Kept as ONE file (the
  WG-market / WG-settlement seam is marked but the halves are not independently
  implementable — settlement needs the market's store/endowments/pricing).
- **Cross-module changes M1/M2 implementers must respect:**
  - **M1 `_credit_labor` amendment (WG5-M1, interaction A):** two getattr-guarded
    edits — a top-of-method `amount *= self._license_yield_mult(colony)` (WG6) and
    line `3948` `w = getattr(unit,'wage_ratio', W_BRUTE)`. Both byte-identical at their
    defaults (`1.0` / `W_BRUTE`); LV2 stays default-neutral (default `0.0` = today).
  - **M2 `_subjugation_tick` amendment (WG11b, interaction B):** one clause added to
    the thrall-gather at `4808–4809` — `and getattr(u,'wage_ratio',W_BRUTE) <= 0.0` —
    so voluntary wage laborers are never coerced. Inert when no contracts exist.
- Depends on M1 `SPEC_LABOR` (`laboring_for`, `_credit_labor`, `_extract_share`,
  `_deposit`, `composite_power`, `w_bargain`, `W_BRUTE`, `W_FAIR`). Parallel-safe with
  M2. Feeds M4 `SPEC_BARGAIN` (per-pair mode selection + enablement, superseding the
  `--wages` stub and choosing wage-vs-force by net extraction).
- Reuse, not reinvention: the labor split reuses M1 `_extract_share`/`_deposit`; the
  license effect rides a read-only view over `colony.techs` (never mutated); the tick
  slots into the existing numbered `step()` sequence at 5c; settlement reuses the
  `currency`/`_house_grains` ledger; the war predicate reads the existing
  `Diplomacy.war_target`.
