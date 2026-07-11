# God Review — The Inter-Colony Political Economy (M1–M4)

Date: 2026-07-10. Reviewer: the orchestrator, from the god's-eye seat.
Method: spec audit + code read + an instrumented 3000-step playtest with the
economy enabled (`playtest_economy.py`), before and after fixes.

## Verdict

The arc is architecturally sound and, after three playtest-surfaced fixes, produces
a **living** economy: in peace colonies trade by comparative advantage and grains
accumulate unevenly (winners and losers emerge); under grudge the same pair tips to
force. Default-neutral discipline is airtight — with the gates off, all 39 test
suites are byte-identical, so nothing here touches a normal (non-`--bargain`) game.

The headline design goal HOLDS: **wages win over force from the cost constants
alone** — `(1−W_FAIR)·WAGE_RELIABILITY (0.5) > (1−W_BRUTE)·BRUTE_RELIABILITY (0.45)`
plus positive brute costs — not from any "prefer wages" branch. The playtest
confirms it empirically: wage is the dominant mode in low-grudge conditions.

## What the playtest proved works

- **Mode selection is genuinely emergent.** Early ticks are wage-dominant; as
  grudges build (blood feuds + soured trust) pairs tip to annihilate; subjugate
  appears in the narrow force-optimal band.
- **The factor market transacts.** Labor and goods contracts open, settle in
  grains, renegotiate on cadence, and suspend on war — continuously across 3000
  steps.
- **Grains are a real, scarce medium.** Starting from a liquidity floor (~60),
  trade redistributed them to `[118, 152, 59]` by step 3000 — a rich trading house
  and a deficit house at the floor. Money as the scoreboard of comparative
  advantage.
- **Liveness is preserved.** The terrarium stays alive (3–4 colonies) with the
  economy running; it does not death-spiral the tank.

## What was BROKEN (found only by playtesting — unit tests passed throughout)

These are the reason a playtest was mandatory: every one of these passed the
39-suite battery, because the battery tests the *gated-off* default-neutral path
and the mechanics in isolation, not the *enabled* economy under load.

1. **Bug A — labor-binding leak (FIXED).** `_wage_open_sweep` bound seller units
   (set `laboring_for`/`wage_ratio`) *while computing the fee*, before the
   liquidity gate. A failed-liquidity `continue` then skipped contract creation but
   left the units bound — orphaned forever. They accumulated (120 units), starving
   the free-labor pool, which collapsed `E_wage`, which drove every pair to `NONE`.
   The economy froze by ~step 1500. Fix: split selection (pure, `_select_free_labor`)
   from binding (`_bind_selected_labor`), and bind only AFTER the contract commits —
   the order the spec's WG4 actually intended.

2. **Balance B — grain drought (FIXED).** Grains mint only from forecast accuracy
   (`_score_forecasts`), and colonies predict their own food far too poorly to earn
   any — so `currency` stayed 0.0 for every colony, the liquidity gate always failed,
   and **zero contracts ever transacted**. The wage economy assumed a money supply
   that the CU currency never actually produces. Fix: `WG13` liquidity floor —
   each settlement interval, top a broke living colony up to `ECON_GRAIN_FLOOR (60)`,
   gated inside `_labor_market_tick` (so default-neutral is untouched). This bootstraps
   and recirculates money; trade then diverges balances naturally.

3. **Bug C — goods-renegotiation crash (FIXED).** Latent twin of an earlier bug:
   `_wage_renegotiate` passed a goods sink name (`'ore:copper'`) straight to
   `_factor_price`→`_marginal_value`, which keys endowments on `'ore'` → `KeyError`.
   It only surfaced once Fix B let goods contracts open and reach a renegotiation
   interval. Fix: route through `_goods_axis` (as `_wage_open_sweep` already did).

## What remains UNDER-TUNED (recommendations, not bugs)

1. **Subjugation almost never fires under the full bargain (`--bargain`).** Across
   3000 steps, `forced_thralls` stayed 0. This is *partly by design* — wages are
   preferred, so brute capture is meant to be rare — but literally zero is too rare
   for a headline feature ("subjugation of spawn between maws"). Root cause:
   SUBJUGATE mode is *advisory* — it sets the capture stance but does NOT drive war
   entry (only WAGE suppresses war). So capture needs an independent WAR_CHEST war +
   melee + local dominance to coincide with a SUBJUGATE-mode pair. To SEE slavery
   today, run `--subjugation` (M2 standalone), which broadly enables capture for any
   at-war colony (the earlier smoke test produced thralls that way).
   **Recommended follow-up:** have SUBJUGATE mode nudge war-entry propensity (lower
   the WAR_CHEST threshold for a SUBJUGATE-selected target), or relax the capture
   local-dominance test, so the mode actually leads to captures. Deferred here
   because it changes war-entry behavior and deserves a design decision.

2. **Tech-licensing — CONFIRMED working when a gift-holder exists.** A targeted
   playtest (`playtest_license.py`) seeded colony 0 with the `calculator` and let the
   economy run: all three rivals opened LICENSE contracts renting the calculator from
   colony 0 (`(0->1), (0->2), (0->3)`), paying a recurring grain fee, and the gift
   NEVER transferred (non-rival access via the effective-gifts view). The monopolist
   ended at **761 grains vs renters at 50–102** — the scarce keeper-gift cashed out as
   monopoly rents. This is the user's "weak civ rents the calculator" scenario,
   emergent and exactly on-design. The reason it did not appear in the general
   playtest is simply that colonies rarely acquire a foreign gift in a headless run
   (gifts come from the keeper ladder + breaching). No fix needed; the path is live —
   it just needs a gift in the tank.

3. **Grain scarcity is currently faked by the floor.** The honest fix is to make the
   CU currency actually fund an economy — tie grain income to production/population
   (a tax base) rather than to a forecast game colonies can't win. The floor is a
   sound bootstrap; a real grain economy is a larger CU-scope change.

4. **Cosmetic: "House X contracts goods to House X".** After a colony falls and a new
   one takes its slot, two live colonies can share a dynasty *name*, so the trade log
   reads as a house trading with itself. The contract is between two distinct
   colony_ids; only the surfaced name collides. Harmless; note for a future
   house-naming/deduplication pass.

5. **Flagged forks from SPEC_BARGAIN remain open by choice:** `_betray` war entry is
   not gated by the bargain; the pre-suppression feud-flare log may fire on a pair
   whose war M4 then suppresses. Both display-only / out of the economic-war scope.

## Bottom line

The economy went from "default-neutral-correct but dead in play" to a functioning,
legible political economy in three surgical fixes, all gated and battery-green. The
peace tier (wages/trade) is the star and behaves as designed. The war tier
(subjugation) works mechanically (M2 standalone) but is squeezed out under the full
bargain — the one thing a future pass should tune so the whip is visible alongside
the wage.
