# SPEC — Fauna Ecology: a world alive (visible pond life + predatory shoals)

Status: IN PROGRESS (A World Alive arc). Rendering pieces are pure-renderer (no gate); sim-side pieces are
baseline-ON, byte-identical off. The umbrella for the ecology that makes the terrarium feel alive — visible
fish/boats, new fauna species, and shoals that grow into a threat — ahead of the domestication arc
(SPEC_DOMESTICATION, later).

## FE1 — World Alive rendering (pure renderer, `live_view.py`, no sim state)

Drawn as new passes in the TOPDOWN/SLICE draw stack; read sim scalars/flags, mutate nothing, use no shared RNG
(so they cannot shift the byte-identical battery).
- **Fish (the shoal):** scatter `FISH_GLYPHS` over the oasis disc (`OASIS_RADIUS` circle at map center) ∪ real
  `WATER` voxels at the z-slice, count `∝ guppy_pop` (≤ `FISH_MAX`), glyph-cycled and wall-clock-phased so the
  shoal shimmers/darts. Deterministic (hash + `pygame.time.get_ticks()`), never the global RNG.
- **Boats:** a `unit.rafted` unit (flag already set by the sim's raft/flood code) draws a timber `BOAT_GLYPH`
  hull with the spawn glyph riding visibly on top (previously the unit was hidden behind a water glyph).
- **Fauna glyphs:** every `FAUNA` species now has a `BEAST_GLYPHS` entry (cricket/ant/fly/small_spider/mouse/
  cat/beetle/guppy previously fell through to `"?"`). `cat` and `guppy` join `BEAST_PREDATORS` (red = threat).
- Legend (`L`) documents fish + rafts; the new beasts auto-enumerate.
- **Purity contract:** a render pass MUST NOT mutate the sim (`tests/test_live_view.py::test_world_alive_render_is_pure`
  asserts `guppy_pop`/`step_count` unchanged by a `_render_body` call).

## FE2 — New fauna species (`FAUNA`, sandkings.py)

- **beetle** `(0.0, 40, 4, (1,2), 0, 4)` — a sturdy harmless burrower; keeper-introducible (`KEEPER_NEUTRAL` →
  `KEEPER_FAUNA` → `keeper_release`, the web release UI, its glyph `⊙`). A good future livestock / tame candidate.
- **guppy** `(0.0, 30, 8, (1,3), 5, 3)` — a predatory big guppy (see FE3); weight 0 (never a random incursion),
  surfaced only by the predatory shoal, glyph `»`, a predator.
- Both are weight-0 additions: `random.choices` selection over `FAUNA` weights is unchanged for a given draw, so
  the battery stays byte-identical (the existing cricket/ant/… are weight-0 the same way).

## FE3 — Guppies grow into predators (`GUPPY_PREDATOR_ENABLED`, gated, `_guppy_predation`)

Baseline-ON, opt-out `--no-guppy-predator`, in `_GATE_NAMES`. Called from `_guppy_tick` only when
`GUPPIES_ENABLED` **and** `GUPPY_PREDATOR_ENABLED` **and** `guppy_pop > GUPPY_PREDATOR_FRAC · GUPPY_CAP`
(double-gated → the battery never reaches it → byte-identical off).
- **Predation:** an overgrown shoal snaps at exposed spawn near the oasis. Each unit within `OASIS_RADIUS+1` of
  the pond center and `_exposed` is bitten with `p = min(GUPPY_BITE_MAX, GUPPY_BITE_K · over)` (where
  `over` = how far past threshold the shoal is), dealing `GUPPY_BITE_DAMAGE` (resilience-reduced); a kill drops a
  `CORPSE` and a "the shoal drags a sand king down" event.
- **Visible threat:** a few big guppies surface as huntable predator `Beast('guppy', …)` over the oasis
  (capped at 4, chance `GUPPY_SURFACE_P`) — a bounty for the brave.
- Constants (sandkings.py, provisional): `GUPPY_PREDATOR_FRAC=0.7`, `GUPPY_BITE_MAX=0.15`, `GUPPY_BITE_K=0.35`,
  `GUPPY_BITE_DAMAGE=6`, `GUPPY_SURFACE_P=0.2`.

## Acceptance (`tests/test_fauna_ecology.py`, `tests/test_live_view.py`)

- Gate default off; guppy/beetle are weight-0 species in `FAUNA`.
- An overgrown shoal (`guppy_pop = GUPPY_CAP`) bites an exposed unit at the oasis (damage applied) and surfaces
  predator guppy Beasts.
- Gate off: a maxed shoal never predates (the tick is byte-identical) — full battery byte-identical with the
  gate off.
- The World Alive render passes draw without crashing and mutate nothing (purity).
