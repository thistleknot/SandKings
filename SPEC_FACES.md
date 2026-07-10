# SPEC: Look to Your Faces (Round A / Canon) — F1–F5

Canon (Martin, "Sandkings"): the colonies do not carve abstract symbols —
they carve the KEEPER'S FACE, and its expression is a serene, benevolent
likeness when the god is kind and twists into a malevolent caricature
("cruel idiot god", "satanic leer") when he is cruel. Wo's warning is the
whole story: **"Look to your faces, Simon Kress."** The keeper reads his
colonies' love or hatred in how they render him — and the souring is
GRADUAL, so it is an early warning of rebellion.

This round replaces the K4 abstract-symbol carvings with the canonical
face, driven by a slow-souring favor scalar.

## F1 — Face favor (the slow-souring scalar)
Each colony carries `face_favor` in [0,1] (default 0.5; getattr-guarded,
pickled). On each CARVE_INTERVAL tick it drifts:
- `keeper_attitude == 'reverent'` (or fed manna this window): += FACE_RECOVER
- `keeper_attitude == 'wrathful'`, drought active, OR starving
  (food < 2·BOOTSTRAP_FLOOR): -= FACE_SOUR
- otherwise: drift toward 0.5 by FACE_NEUTRAL_DRIFT.
Clamped [0,1]. Constants: FACE_SOUR 0.06, FACE_RECOVER 0.05,
FACE_NEUTRAL_DRIFT 0.02. Souring is faster than recovery — cruelty is
remembered, kindness re-earned.

## F2 — The face expression (what is carved)
The carved band tracks the GRADUAL favor scalar so the souring is VISIBLE
(devout → wary → hateful over time — the "look to your faces" warning);
wrath/drought only accelerate the decay of `keeper_sentiment`, they do not
slam the band:
- `'hateful'` if `keeper_sentiment` < 0.33 (the god soured);
- `'devout'` if `keeper_sentiment` > 0.66 (the god beloved);
- `'wary'` otherwise (impassive, watching).
CARVE_SYMBOLS becomes the face set: `serene ☺`, `plain ☻`, `wrath ☹`,
plus the pre-existing `machine ⌂` (the terminal's own glyph, K10 — the
machines write, not the face). The war/hunger/content symbol variants are
retired (the FACE now conveys the colony's stance toward the keeper; war
and hunger read from the mood line and thoughts as before).

## F3 — The warning event
The FIRST time a colony's carved face turns to `'wrath'` (a transition
from not-wrath to wrath), log "The carved face of House X twists into a
hateful mask" (salience 8) — and reset the flag if it recovers to serene,
so a repeated fall re-warns. This subsumes the old drought "carvings
twist into something hateful" line.

## F4 — Surfacing
- Render: carvings colour by face (live_view CARVE_COLORS): serene gold
  (255,235,140), plain pale grey (170,170,180), wrath red (230,70,60),
  machine blue (150,180,255). The glyph view already blits carvings; it
  now looks them up per-glyph.
- Look panel (R32): names the cell — "a carving of your face — serene" /
  "…— impassive" / "…— twisted with hate". Legend "-- carvings --" lists
  the three faces + machine with those meanings.
- Dashboard: House card gains `face` (serene/plain/wrath) so the keeper
  reads the terrarium's mood toward him at a glance.

## F5 — Acceptance
tests/test_faces.py: attitude/favor → expression mapping (wrath at low
favor or wrathful; serene only when reverent AND favor high; plain
between); face_favor sours monotonically under sustained drought and
recovers under manna, clamped [0,1], souring faster than recovery; the
carved glyph is one of the face set on the maw ring and purges when the
sand is disturbed; the first wrath transition fires the warning once;
state pickles; EnhancedSandKingsSimulation stays inert (no _keeper_tick).

## Status / Reconciliation
- Drafted + implemented 2026-07-09. The carving is SENTIMENT, not a literal
  face (per user: the sandkings have no image of the keeper) - a readable
  fact that sours GRADUALLY. Band tracks the favor scalar (devout>0.66 /
  wary / hateful<0.33); wrath/drought only accelerate the decay, so the
  souring is VISIBLE (soak: devout 0.84 -> wary 0.66 -> hateful 0.30). The
  warning fires once on the first turn to hateful and re-arms on recovery.
  Verified in-container: all 20 suites green incl. tests/test_faces.py (7).
  Also completed the Docker test-dep set (tqdm, matplotlib, httpx, pygame)
  so the FULL suite runs inside the image on the container's python.
