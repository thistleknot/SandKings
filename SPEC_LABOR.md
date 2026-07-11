# SPEC: Labor-Value & the Extractor's Surplus — LV1–LV7

Module **M1** of the inter-colony political-economy arc (governing scope record:
`docs/decisions/2026-07-09-intercolony-relations-spectrum.md`; this spec is the
no-dependency FOUNDATION — M2 `SPEC_SUBJUGATION` builds on it, M3 `SPEC_WAGES` /
M4 `SPEC_BARGAIN` are NOT specified here).

**One mechanic.** A unit produces value `V` at a deposit. `w ∈ [0,1]` is the
share of that value returned to the LABORER'S BIRTH colony; `(1−w)·V` is the
extractor's surplus. Birth allegiance (`SandKing.colony_id`) is fixed for life —
psionic conditioning is unoverwritable, so it NEVER changes. A NEW per-unit field
`laboring_for` (−1 = free) records the current extractor. Brute-force extraction
runs at `w = W_BRUTE = 0.0`.

This module lays the value-splitting spine and the shared helpers (composite
`power`, the `w` bargaining function) that M2–M4 reuse. It changes NO observable
behaviour on its own: every path is DEFAULT-NEUTRAL — with no thrall relationships
in play (`laboring_for < 0` everywhere, the born-free default), every credit site
behaves byte-for-byte as today.

All new state is getattr-guarded (old pickles lack it), pickled, and inheritance
follows the existing new-field convention (`stage`, `breached`);
`EnhancedSandKingsSimulation.step` stays inert.

> **TOP INVARIANT (default-neutral).** With `laboring_for < 0` on every unit — the
> only reachable state until M2 sets it — `_credit_labor` is a transparent
> pass-through: each of the four credit sites deposits exactly what it deposits
> today, the seeded RNG stream is untouched, and the full regression battery is
> byte-identical. This is LV7's FIRST acceptance clause.

---

## Data model (LV1)

**LV1 — The `laboring_for` field.** A new field on `SandKing` (the unit dataclass,
beside `colony_id` at `sandkings.py:723`):

```
laboring_for: int = -1   # colony_id of the current extractor; -1 = free (born free)
```

- `colony_id` (birth allegiance) is untouched — the psionic link is unoverwritable.
  `laboring_for` sits ORTHOGONAL to it: a unit's birth house never changes; only
  who currently extracts its production does.
- Every READ is getattr-guarded — `getattr(unit, 'laboring_for', -1)` — so units
  unpickled from pre-LV1 saves read as free. The dataclass default (`-1`) covers
  freshly constructed units; the getattr guard covers deserialized ones.
- Pickled automatically as a dataclass field. `brain_layer` / `SoldierLayer` carry
  NO loyalty field, so nothing there aliases or overrides this.
- **Respawn:** fresh units spawned into a respawned colony slot (`_respawn_colony`,
  `sandkings.py:4931`) are born FREE (`laboring_for = -1` by construction) — there
  is no colony-level inheritance of `laboring_for`, because it is a per-unit
  relationship to a possibly-dead extractor, not a heritable house trait. (The
  getattr-guard + dataclass default is the whole of LV1's respawn obligation;
  M2/SJ6 governs what happens to EXISTING thralls when a birth maw dies.)

Contract at the field:
- **Require** — callers treat `colony_id` as read-only birth allegiance.
- **Guarantee** — `laboring_for ∈ {-1} ∪ {valid colony_id}`; `-1` means free.
- **Maintain** — `colony_id` is never written by any M1/M2 path except SJ6's
  permanent conversion (which sets `colony_id := laboring_for` on birth-maw death).
- **Assert** — `getattr(unit, 'laboring_for', -1) == -1` for any unit whose
  extractor colony is dead or absent (enforced by `_credit_labor`, LV2).

## The single split fn (LV2)

**LV2 — `_credit_labor` fronts all four credit sites.** `V` (labor-value) is the
numeric amount a unit deposits at a production site. Today four sites credit it
directly to the acting unit's own colony. LV2 routes ALL of them through one
method on `TerrariumSimulation`:

```
def _credit_labor(self, unit: SandKing, colony: Colony, kind: str, amount) -> None:
    """Deposit `amount` of labor-value produced by `unit`, split between the
    extractor and the laborer's birth colony.

    kind ∈ {'ore:copper','ore:gold','salvage','food','crop','wood'} selects the
    sink. `colony` is the acting unit's own (birth) colony — under VIRTUAL labor
    delivery there is no unit migration, so the acting unit's colony_id equals its
    birth colony_id and equals `colony`.

    Preconditions (Require):
      - colony is unit's own colony (colony.colony_id == unit.colony_id).
      - amount >= 0; for discrete kinds (ore:*, salvage, wood) amount is an int
        item-count (always 1 at the live call sites); for continuous kinds
        (food, crop) amount is a float payout.
    Postconditions (Guarantee):
      - extractor_share + birth_share == amount  EXACTLY (mint-free, loss-free;
        birth_share is computed as amount - extractor_share, never rounded
        independently).
      - laboring_for < 0 (or a dead/absent extractor) => the ENTIRE amount lands
        in `colony` via kind's sink, byte-identical to the pre-LV2 code path
        (the default-neutral guarantee).
    Failure modes: none raised; a stale laboring_for pointing at a dead colony is
      self-healed to -1 and treated as free.
    """
```

Pseudocode:
```
ext_id = getattr(unit, 'laboring_for', -1)
extractor = self._colony_by_id(ext_id) if ext_id >= 0 else None     # :3681

# self-heal a dangling thrall pointer, then behave as free
if ext_id >= 0 and (extractor is None or not extractor.is_alive()):
    unit.laboring_for = -1
    ext_id = -1
    extractor = None

if ext_id < 0:
    # FREE PATH — byte-identical to today
    _deposit(colony, kind, amount)          # full amount to the birth colony
    return

# THRALL PATH — split by w (brute mode in M1/M2; M3 supplies a bargained w)
w = W_BRUTE                                 # 0.0 -> whole value to the extractor
extractor_share = _extract_share(kind, amount, w)   # (1-w)*amount, kind-aware
birth_share     = amount - extractor_share          # remainder: conserves exactly
_deposit(extractor, kind, extractor_share)
_deposit(colony,    kind, birth_share)
```

`_extract_share(kind, amount, w)` — the mint-free, exact-conserving split:
```
if kind in ('food', 'crop'):        # continuous: maw.eat float payout
    return (1.0 - w) * amount
else:                               # discrete item-count (ore:*, salvage, wood)
    return round((1.0 - w) * amount)   # extractor gets whole items; birth = remainder
# birth_share is always amount - extractor_share, so no mint and no loss for
# either kind. At w = W_BRUTE = 0: extractor_share == amount, birth_share == 0.
```

`_deposit(target, kind, amount)` — the ONLY place that knows each sink; it
reproduces exactly today's write for that kind:
```
kind == 'ore:copper' -> target.ore['copper'] = target.ore.get('copper',0) + int(amount)   # :3884
kind == 'ore:gold'   -> target.ore['gold']   = target.ore.get('gold',0)   + int(amount)   # :3884
kind == 'salvage'    -> target.salvage = getattr(target,'salvage',0) + int(amount)        # :3882
kind == 'food'       -> target.maw.eat(amount)                                             # :5083
kind == 'crop'       -> target.maw.eat(amount)                                             # :5118
kind == 'wood'       -> target.wood = getattr(target,'wood',0) + int(amount)              # :2000/:2013
# a zero amount is a no-op deposit (int(0) add / eat(0.0)); safe at w-boundaries.
```

**Call-site rewrites (the four hooks).** Each replaces its direct write with a
`_credit_labor` call; the free path makes each byte-identical to today.

1. **Ore / salvage** — `_haul_step`, `sandkings.py:3881–3884`:
```
if unit.carrying == 'salvage':
    self._credit_labor(unit, colony, 'salvage', 1)          # was colony.salvage += 1
else:
    self._credit_labor(unit, colony, 'ore:' + unit.carrying, 1)  # was colony.ore[..]+=1
```

2. **Foraged food** — harvest grab, `sandkings.py:5083`:
```
self._credit_labor(unit, colony, 'food', HARVEST_YIELD)     # was colony.maw.eat(HARVEST_YIELD)
```
(The corpse→bone and keeper-manna side effects at :5084–5096 stay put, unchanged.)

3. **Ripe-crop payout** — `sandkings.py:5117–5123`. GENERALIZE the existing ally
co-op split (`0.6`/`0.4`), do NOT duplicate it. The co-op axis (harvester vs
crop-owner) and the thrall axis (extractor vs birth) are ORTHOGONAL; route only the
harvester's OWN portion through `_credit_labor`, leave the owner's cut alone:
```
if foreign and d.ally(colony.colony_id, owner):
    self._credit_labor(unit, colony, 'crop', payout * 0.6)   # harvester's co-op share, thrall-redirectable
    owner_colony = self._colony_by_id(owner)
    if owner_colony is not None and owner_colony.is_alive():
        owner_colony.maw.eat(payout * 0.4)                   # owner's cut — UNCHANGED, not labor the harvester produced
else:
    self._credit_labor(unit, colony, 'crop', payout)
```
When `laboring_for < 0`, `_credit_labor(unit, colony, 'crop', x)` == `colony.maw.eat(x)`,
so both branches reproduce today's payout exactly. (Coupling resolution — see the
Ambiguities note.)

4. **Felled wood** — `_fell_tree`, `sandkings.py:2000` and `:2013`:
```
colony.wood = getattr(colony,'wood',0) + 1   ->   self._credit_labor(unit, colony, 'wood', 1)   # :2000
...  colony.wood += 1                          ->   self._credit_labor(unit, colony, 'wood', 1)   # :2013
```

Contract at `_credit_labor`:
- **Require** — `colony.colony_id == unit.colony_id`; `amount >= 0`; `kind` is one
  of the six sink tags.
- **Guarantee** — `extractor_share + birth_share == amount` exactly; free/dead-
  extractor path is byte-identical to the pre-LV2 write; no currency minted, no
  value lost.
- **Maintain** — no unit migration (virtual delivery); `colony_id` untouched.
- **Assert** — after a thrall deposit, both `extractor` and `colony` received a
  non-negative share summing to `amount`.

## The bargaining function (LV3)

**LV3 — `w_bargain`, a pure function of the negotiation state.** Defined now,
exercised by M3; in M1/M2 the brute path uses the `W_BRUTE` constant directly and
never calls this. Neutral defaults make it inert (nothing wired calls it):

```
def w_bargain(power_ratio: float = 1.0,
              desperation: float = 0.0,
              control: float = 0.0) -> float:
    """The share `w` returned to the laborer's birth colony under NEGOTIATED
    (non-brute) extraction. Pure; no side effects; deterministic.

    power_ratio = composite_power(birth_colony) / composite_power(extractor)
                  (> 1 => the laborer's house is the stronger, keeps more).
    desperation = extractor's need in [0,1] (higher => concedes a bigger w).
    control     = extractor's grip on a scarce factor in [0,1]
                  (higher => extracts more, smaller w).

    Returns w clamped to [0,1]. Neutral anchor: w_bargain() == W_FAIR (an even
    split) — balanced power, no desperation, no scarce-factor control. Sticky w
    with periodic renegotiation is M3's cadence; this fn only maps state -> w.
    """
    w = (W_FAIR
         + W_POWER_SENS      * (power_ratio - 1.0)
         + W_DESPERATION_SENS * desperation
         - W_CONTROL_SENS     * control)
    return max(0.0, min(1.0, w))
```

- **Require** — `power_ratio > 0`; `desperation, control ∈ [0,1]`.
- **Guarantee** — returns a value in `[0,1]`; `w_bargain() == W_FAIR`; monotone
  increasing in `power_ratio` and `desperation`, decreasing in `control`.
- **Maintain** — purity: same inputs → same output, no RNG, no state read.
- **Assert** — output clamped; never NaN (caller passes finite inputs).

## Composite power (LV4)

**LV4 — `composite_power`, the shared capability metric.** A pure module-level
function in `sandkings.py` (importable by tests without a sim instance). It is a
strict SUPERSET of the existing `politics.power` (`politics.py:179`) — same
military + wealth terms, PLUS currency, wood, and (scarce) technology, with the
keeper's FOREIGN gifts weighted highest:

```
def composite_power(colony) -> float:
    """Composite capability index: military + wealth + scarce technology.
    Pure read of colony fields; getattr-guarded for pre-feature pickles.
    Reused by M2 dominance (SJ2) and by w_bargain (LV3)."""
    ore   = getattr(colony, 'ore', {}) or {}
    techs = getattr(colony, 'techs', set()) or set()
    foreign = sum(1 for t in techs if t in TECH_FOREIGN)      # keeper gifts, scarce
    native  = len(techs) - foreign
    return (POWER_WEALTH_FOOD * colony.maw.food_stored
          + POWER_MILITARY_UNIT * len(colony.units)
          + POWER_MAW_HEALTH   * colony.maw.health
          + POWER_ORE_COPPER   * ore.get('copper', 0)
          + POWER_ORE_GOLD     * ore.get('gold', 0)
          + POWER_CURRENCY     * getattr(colony, 'currency', 0.0)
          + POWER_WOOD         * getattr(colony, 'wood', 0)
          + POWER_TECH_NATIVE  * native
          + POWER_TECH_FOREIGN * foreign)
```

`politics.power` stays as-is (P7 balance-of-power coalitions depend on its exact
value — changing it would NOT be default-neutral). `composite_power` is the NEW
metric for the labor/subjugation arc only.

- **Require** — `colony.maw` exists; `colony` may be missing any getattr-guarded field.
- **Guarantee** — a finite non-negative float; strictly greater than the
  military-only subtotal whenever the colony holds tech or wealth.
- **Maintain** — pure; no mutation of `colony`.
- **Assert** — a tech/wealth-rich colony outranks a bare-military colony of equal
  unit count (LV7).

## Surfacing (LV5)

**LV5 — expose the new state, change nothing else.** `build_state` gains a
per-unit `laboring_for` in whatever structure already surfaces units (or, if units
are not individually surfaced, a per-colony `thralls_out` / `thralls_in` count
derived by scanning `colony.units` and all colonies' units). The dashboard card /
live-view inspect panel MAY show "N thralls" but this is display-only. No control
flow keys off surfaced values. `composite_power(colony)` is available for a card
readout. Surfacing must not alter the RNG stream or any sim state.

## Persistence & regression guarantees (LV6)

**LV6 — pickle, inherit, regress clean.**
- `laboring_for` pickles as a dataclass field; unpickling a pre-LV1 unit yields no
  attribute, and every read uses `getattr(..., 'laboring_for', -1)` → free.
- Respawned colonies' fresh units are born free (LV1); no `laboring_for` inheritance.
- `EnhancedSandKingsSimulation.step` (the evolution wrapper) remains inert — it
  adds no thrall relationships, so it inherits the default-neutral guarantee.
- With no thralls set anywhere, a seeded run is byte-identical to a pre-LV1 run:
  same RNG draws (LV2 adds NO `random.*` calls on any path), same events, same
  telemetry.

## Constants (LV8 table)

| Constant | Value | Meaning |
|---|---|---|
| `W_BRUTE` | `0.0` | brute-mode share returned to the laborer's birth colony (a subsistence trickle is a one-line bump) |
| `W_FAIR` | `0.5` | neutral even-split anchor of `w_bargain` (balanced, non-desperate, no control) |
| `W_POWER_SENS` | `0.25` | `w_bargain` sensitivity to `(power_ratio − 1)` |
| `W_DESPERATION_SENS` | `0.25` | `w_bargain` sensitivity to extractor desperation |
| `W_CONTROL_SENS` | `0.25` | `w_bargain` sensitivity to extractor scarce-factor control |
| `POWER_WEALTH_FOOD` | `1.0` | `composite_power` weight on stored food (matches `politics.power`) |
| `POWER_MILITARY_UNIT` | `15.0` | weight per living unit (matches `politics.power`) |
| `POWER_MAW_HEALTH` | `0.2` | weight on maw health (matches `politics.power`) |
| `POWER_ORE_COPPER` | `25.0` | weight per copper ore (matches `politics.power`) |
| `POWER_ORE_GOLD` | `10.0` | weight per gold ore (matches `politics.power`) |
| `POWER_CURRENCY` | `1.0` | weight on grains held (new wealth term) |
| `POWER_WOOD` | `1.0` | weight per wood unit (new wealth term) |
| `POWER_TECH_NATIVE` | `8.0` | weight per known NATIVE tech (scarce capability) |
| `POWER_TECH_FOREIGN` | `30.0` | weight per known FOREIGN (keeper-gift) tech — scarcest, ranked highest |

## Acceptance (LV7)

`tests/test_labor.py`:

1. **DEFAULT-NEUTRAL (FIRST clause).** With `laboring_for = -1` on every unit
   (the born-free default), every one of the four credit sites deposits exactly as
   the pre-LV2 code did, the seeded RNG stream is byte-identical, and the full
   regression battery is green. Assert: a fixed-seed run through all four sites
   equals a pre-feature golden byte-for-byte (no extra `random.*` draws).
2. **Conservation, mint-free.** For a thrall deposit at arbitrary `w` on a
   continuous kind (`food`), `extractor_share + birth_share == amount` and
   `w·V + (1−w)·V == V` to float tolerance; no `currency` is minted and none lost.
   For discrete kinds, `extractor_share + birth_share == amount` exactly
   (remainder construction). At `w = W_BRUTE = 0`: extractor gets the whole
   value, birth gets zero.
3. **Composite power ranking.** `composite_power` ranks a tech-rich / wealth-rich
   colony ABOVE a bare-military colony of equal unit count; equals the
   `politics.power` subtotal plus the new currency/wood/tech terms; is finite and
   non-negative; leaves `colony` unmutated.
4. **`w_bargain` purity & shape.** `w_bargain() == W_FAIR`; output clamped to
   `[0,1]`; monotone up in `power_ratio` and `desperation`, down in `control`; no
   RNG consumed.
5. **Self-heal.** A unit whose `laboring_for` points at a dead/absent colony is
   reset to `-1` by `_credit_labor` and credited fully to its birth colony.
6. **Persistence.** Units pickle/unpickle with `laboring_for` intact; a pre-LV1
   pickle (no field) reads as free; respawned colonies' units are born free.
7. **Evolution inert.** `EnhancedSandKingsSimulation.step` produces no thralls and
   is byte-identical to a pre-LV1 run.

## Ambiguities resolved

- **Co-op split × thrall split coupling (crop site).** The existing `0.6/0.4`
  ally co-op split (harvester vs crop-owner) is a DIFFERENT axis from thrall
  extraction (extractor vs birth). Resolution: `_credit_labor` intercepts only the
  portion currently credited to the acting colony (the harvester's `0.6`, or the
  full payout when not an ally crop); the crop-owner's `0.4` is a separate payment
  and is untouched. This keeps the free path byte-identical and avoids double-
  charging a thrall who harvests an ally's field.
- **Discrete-good split.** Ore/wood/salvage are integer item-counts; a fractional
  `w` cannot store half an ore. Resolution: `extractor_share = round((1−w)·amount)`,
  `birth_share = amount − extractor_share` — mint-free and exact-conserving by
  remainder construction. Live M1/M2 calls only ever use `w = 0` (whole item to
  extractor) or the free path (whole item to birth); general-`w` fractional
  handling of physical goods is M3's concern and does not break this signature.
- **`power` naming.** The scope record's generic `power(colony)` maps to the new
  module-level `composite_power(colony)`; `politics.power` is left intact so P7
  coalition behaviour stays default-neutral.

## Events, Vocabulary & Surfacing

Standing contract for how this arc surfaces its own words, drama, and display.
M1 is the FOUNDATION substrate — it emits no events of its own (default-neutral),
but it owns the state the rest of the arc dramatises. What M1 contributes:

- **Events emitted:** NONE. M1 is pure accounting — no chronicle string, no
  salience, no tint. (Force emits capture/conversion drama in SPEC_SUBJUGATION;
  wages emit contract drama in SPEC_WAGES; the selector emits mode-shift drama in
  SPEC_BARGAIN.) M1 stays silent so the default battery is byte-identical.
- **Display fields it should surface (LV5, display-only):** per-unit
  `laboring_for`, and the derived per-colony `thralls_out` (own units with
  `laboring_for >= 0`) and `thralls_in` (units anywhere with `laboring_for ==
  this colony_id`); `composite_power(colony)` for a card readout. No control flow
  keys off any surfaced value.
- **Anchor it underpins:** `thrall` (SPEC_HIVE_MONITOR M15) reads exactly M1's
  `laboring_for` state — a colony's `thrall` anchor is active when it holds
  thralls (units with `laboring_for == its colony_id`) OR any of its own units is
  laboring (`laboring_for >= 0`). M1 emits no anchor of its own; it is the
  substrate the `thrall` word measures.
- **Lesson it contributes:** none directly. The wage form of this same
  labor-value split is what the codex `commerce` lesson (SPEC_CODEX CX7) teaches;
  M1 is the mechanism beneath it.

## Status / Reconciliation

- **Drafted 2026-07-10.** Spec-first: implementation pending.
- Foundation module (M1). No dependency on M2–M4. M2 `SPEC_SUBJUGATION` sets
  `laboring_for` (capture) and reuses `_credit_labor`, `composite_power`; M3
  `SPEC_WAGES` supplies a bargained `w` via `w_bargain`; M4 `SPEC_BARGAIN` drives
  the renegotiation cadence.
- Reuse, not reinvention: generalizes the crop `0.6/0.4` co-op split rather than
  duplicating it; `composite_power` extends `politics.power`'s shape; new state
  follows the `stage`/`breached` getattr-guarded, pickled, inherited convention.
- 2026-07-11 — Economy-arc alignment: added the "Events, Vocabulary & Surfacing"
  standing contract (M1 emits no events; surfaces `thralls_out`/`thralls_in` +
  `composite_power`; underpins the `thrall` anchor of SPEC_HIVE_MONITOR M15) and
  pinned the governing decision-record cross-reference to its full path.
