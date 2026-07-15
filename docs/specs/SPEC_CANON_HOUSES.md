# SPEC: The Canonical Houses (Round B / Canon) — CH1–CH4

Canon: the novella's terrarium holds four color-houses with distinct
temperaments — the White (Kress's favorites: most powerful, grandest
castle), the Red (the most creative), the Black (whose carved face
struck Kress as "wise and benevolent"), and the Orange (last and least,
the perpetual underdog with the shabby castle). A `--canon` start seats
these four as the founding houses so the drama has the story's actors.

## CH1 — The flag
`SandKingsSimulation(canon=False)` kwarg; `--canon` CLI flag (sandkings
main + dashboard). When set, `num_colonies` is forced to 4 (the four
colors) and `_spawn_colonies` applies the canonical presets AFTER its
normal random spawn (so positions, oasis luck, and the machinery are
unchanged — only names + dispositions + starting stock are overridden).
`sim.canon` is stored (pickled, getattr-guarded).

## CH2 — The houses (colony_id ↔ Colony.COLORS order)
Colony colors are already [Red, White, Black, Orange]. Canon presets, by
id:
- 0 RED "Crimson", epithet "the Creative": plasticity 0.85, fertility
  0.80 (adapts and breeds inventively).
- 1 WHITE "Pale", epithet "the Favored": aggression 0.85, expansion 0.80;
  starts richest — maw food ×1.6 and two extra workers (Kress's
  favorites, the grandest castle).
- 2 BLACK "Sable", epithet "the Wise": patience 0.90, loyalty 0.90
  (the wise, benevolent face — long-term, faithful).
- 3 ORANGE "Amber", epithet "the Underdog": all dispositions modest;
  starts poorest — maw food ×0.6 (last and least).
House names are fixed strings (not random); the epithets are preset in
`house_epithets` so they show immediately (Dynasties D2 will still
re-judge them at death). Presets are the START — mutation, respawn
crossover, and evolution proceed normally (the underdog CAN rise).

## CH3 — Surfacing
No new glyphs. The houses simply appear named in the HUD/roster, saga,
dashboard, and manager with their canonical names + epithets from step
0. A canon start logs "The four houses wake: Crimson, Pale, Sable, and
Amber" (salience 6).

## CH4 — Acceptance
tests/test_canon.py: a canon sim has exactly 4 colonies with the fixed
house names and preset epithets; the dispositions match the table
(white most aggressive, black most patient, red most plastic, orange
weakest); white starts richest and orange poorest; a non-canon sim is
unchanged (random houses); presets still mutate (genome.mutate moves
them) and a canon colony still respawns; state pickles; evolution sim
unaffected (it does not read canon).

## Status / Reconciliation
- Drafted + implemented 2026-07-09. `_apply_canon` neutralizes each canon
  genome to a 0.5 baseline before applying the house's signature traits,
  so the table holds deterministically (white most aggressive, black most
  patient, red most plastic, amber weakest). White starts richest (×1.6
  food + 2 workers), amber poorest (×0.6). Verified in-container: 21/21
  suites green incl. tests/test_canon.py (6). `--canon` on both CLIs.
