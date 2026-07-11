# SPEC: Nature until the Great Other (Phase 1 / Awareness) — AW1–AW6

The sandkings have never seen the keeper. Before they break out of the glass
they should feel only NATURE — "opinions about unexplained forces" — never
worship or hatred of a *being*. Love and hatred of the "great other" switch on
ONLY at the breakout (the 13th-Floor revelation), and how they were treated as
nature seeds their opening stance toward the god they now know exists.

This re-gates the keeper-directed emotional layer (worship, keeper_sentiment,
the carved "faces", the wrathful attitude) on `breached`. The psionic turning
(PS1/PS4) already gates on stage ≥ 2/3, so it is unchanged.

> Cross-ref (inbound): the ONE true breakout `_escape` (the AW4 revelation choke
> point, terminal mastery) now ALSO triggers the ENLIGHTENMENT ascension — a
> bounded intelligence leap (raised brain ceiling, faster native-tech + codex
> climb) appended after `_reveal`. The revelation and the ascension fire from the
> SAME `_escape` breakout; the ascend string is DISTINCT from the "beyond the
> glass" revelation line so revelation counts are unaffected. See
> `SPEC_ENLIGHTENMENT.md` (EN2/EN7).

## AW1 — Awareness = breached (the true breakout ONLY)
A colony is AWARE of the keeper iff `getattr(colony, 'breached', False)`. All
keeper-DIRECTED feeling requires awareness. `breached` is set by the ONE true
breakout — `_escape`, reached only by terminal mastery (K10, the raspberry-pi
terminal past the glass into the sandbox). The metamorphosis MOLT (growing into
the new breed, `_set_stage`) is PHYSICAL and grants NO awareness — a stage-2/3
body can still feel only nature until it escapes. Psionic projection/turning
(PS1/PS4) is likewise gated on `breached`, not stage.

## AW2 — Pre-breach: the mood of unexplained forces
`_nature_mood(colony) -> 'bounty' | 'lean' | 'dread'` from conditions only:
- **dread** — drought, starvation (`food < 2·BOOTSTRAP_FLOOR`), or any active
  harsh weather (cold/frost, arena heat/cold, flood, hail, sandstorm);
- **bounty** — recently fed (`keeper_attitude == 'reverent'`) or a full hoard;
- **lean** — otherwise.
Pre-breach carvings write `NATURE_SYMBOLS[mood]` (☀ bounty / ☁ lean / ☈ dread) —
the forces they feel, not a keeper's face. `keeper_sentiment` is FROZEN
(neutral 0.5) pre-breach — `_update_sentiment` is not called for un-breached
colonies.

## AW3 — Post-breach: the great other
Once breached, a colony runs the existing keeper layer unchanged:
`_update_sentiment` drifts `keeper_sentiment` (F1/F2), the carving writes the
`CARVE_SYMBOLS` face band (devout ♥ / wary ◦ / hateful ☠), the "hateful mask"
warning (F3) fires, and eating keeper manna sets `worshipped = True` ("begins to
worship the hand that feeds"). `keeper_attitude`'s `wrathful` (drought +
worshipped) is therefore reachable only post-breach. `worshipped` is set ONLY
when breached (the pre-breach manna eat still sets `keeper_fed_step` — fortune —
but never `worshipped`).

## AW4 — The revelation (the 13th Floor)
`_reveal(colony)` fires once, from `_escape` — the single choke point where
`breached` goes False→True (terminal mastery only; the molt does not lead
here). `_escape` sets `breached=True`, gives the new-breed body if unmolted,
then `_reveal`s. It:
- sets a getattr-guarded `revelation = True` (fires once);
- SEEDS `keeper_sentiment` from `_nature_mood` at that instant —
  bounty→0.7 (wakes grateful), lean→0.5, dread→0.3 (wakes resentful);
- logs "House X glimpses the world beyond the glass — and knows the hand that
  fed and starved it".
Cadet branches born already breached (respawn inheritance) inherit
`keeper_sentiment` and are marked `revelation = True` (born knowing — no second
revelation event). (After `_reveal`, the same `_escape` appends the
ENLIGHTENMENT ascension burst — a purely-additive leap that leaves every AW4
field above untouched; see `SPEC_ENLIGHTENMENT.md` EN2/EN6/EN7.)

## AW5 — The gift ladder gates on flourishing, not worship
The tech-gift ladder (K9) no longer requires `worshipped` (now post-breach
only). It gates on a pre-breach FLOURISHING state — `keeper_attitude_any(
'reverent')` (a recently-fed, thriving colony draws the operator's hand) — so
the ladder→pi→terminal→breach path still works without pre-breach worship. This
resolves the worship↔breach circularity.

## AW6 — Acceptance (tests/test_awareness.py)
- Pre-breach: eating keeper manna sets `keeper_fed_step` but NOT `worshipped`;
  the carving is a NATURE glyph (not a face); `keeper_sentiment` does not move
  across `_keeper_tick`.
- The gift ladder fires for a flourishing UN-breached colony.
- At breach: `_reveal` fires exactly once; `keeper_sentiment` is seeded by the
  prior treatment (well-fed → high, starved/droughted → low); a second stage
  promotion does not re-reveal.
- Post-breach: the face carving + sentiment drift + the "hateful mask" warning
  work as before.
- Cadet born breached inherits sentiment and does not emit a revelation event.
- State pickles; `EnhancedSandKingsSimulation.step` stays inert.
- Reconciliation: `SPEC_FACES.md` F1 (breach gate + pre-breach nature mood) and
  `SPEC_KEEPER.md` K3 (worship is post-breach; the revelation) updated.

## Status / Reconciliation
- Drafted 2026-07-10; implemented the same session (Phase 1 of the closed-biome
  arc).
- 2026-07-11 — Economy-arc alignment: added the inbound cross-ref noting the
  `_escape` breakout now also triggers the enlightenment ascension (SPEC_ENLIGHTENMENT
  EN2/EN7), appended after `_reveal` with a distinct string so revelation counts
  are unaffected. No AW mechanic change.
