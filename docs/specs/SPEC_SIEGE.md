# SPEC: Siege Engines (medieval siege train) — SE1…SE2

Governing intent (user, verbatim): "I still expect to see projectiles (such as catapults and ballistas).
Think siege towers. We need it all. I'm basically trying to rebuild medieval society with intelligent (neural)
insectoids." The catapult (lobbed area shot) already ships (SPEC_TECH TE11, EFFECTS_ENABLED). This spec adds the
rest of the siege train as VISIBLE, distinct engines.

Scope: two new siege engines a besieging house fields, each a GATED CAPABILITY of a house that already holds
the `catapult` (siege) tech — NOT new tech rows (adding a researchable tech would change tech-acquisition RNG
and break byte-identity; a gated behavior keyed on the existing tech does not). Baseline-ON, opt-out
`--no-siege`, in `_GATE_NAMES`, byte-identical off.

Cross-references (not duplicated):
- **SPEC_TECH TE11** — owns `_catapult_tick`, `CATAPULT_*`, the `catapult` tech, `diplomacy.war_target`. Both
  engines reuse the war-target delivery and require the `catapult` tech as the siege prerequisite.
- **SPEC_FAUNA_ECOLOGY FE4** — owns `sim.effects` / `_spawn_effect` / `_effects_tick`. SE1 extends it with a
  faster `'bolt'` projectile kind.

---

## SE1 — The ballista (a fast, direct, single-target bolt)

`_ballista_tick()` — gated `SIEGE_ENGINES_ENABLED`, cadence `BALLISTA_RELOAD` (faster than the catapult's 40).
A living house with the `catapult` tech and an in-range `war_target` looses a bolt:
- direct `BALLISTA_DAMAGE` to the target maw (high single-target; NO splash, NO fire — the anti-armor engine,
  contrast the catapult's area shot),
- a visible `_spawn_effect('bolt', maw, target)` — a `'bolt'` flies `BOLT_SPEED` cells/step (faster than a
  lobbed `'shot'`'s `SHOT_SPEED`) and bursts to a `'blast'` on arrival (reuses `_effects_tick`).
Deterministic (no RNG) → byte-identical off. `live_view` draws a bolt as a steel `»` in flight (pure read).

**Acceptance SE1.** A catapult-teched house at war with an in-range target: after `BALLISTA_RELOAD` steps the
target maw has taken `~BALLISTA_DAMAGE` and a `'bolt'` effect is in flight. Gate off → neither.

## SE2 — The siege tower (a mobile wall-breaker)

`sim.siege_towers` — a transient list of plain dicts `{owner, pos, target}` (checkpoint-safe), advanced by
`_siege_tower_tick` (gated `SIEGE_ENGINES_ENABLED`):
- **Deploy** (cadence `SIEGE_TOWER_DEPLOY`): a catapult-teched house with an in-range `war_target` and no live
  tower rolls one out from its maw toward the enemy maw.
- **Advance**: each tower steps `SIEGE_TOWER_SPEED` cells/step toward its target; on arrival (`_breach_palisade`)
  it smashes the enemy palisade ring (`WOOD_WALL`/`CASTLE` → `SAND`, clearing `_rot`) within `SIEGE_TOWER_BREACH`,
  opening the fortress — the answer to the palisade defense (SPEC_TECH T43) — then is spent.
A self-propelled engine crossing OPEN GROUND, distinct from the unit-carried battering ram (`ram_until`, which
smashes only walls a soldier is already adjacent to). Deterministic (no RNG) → byte-identical off.
`live_view` draws a tower as a big timber `⊓` in transit (pure read); legend gains a `siege` category.

**Acceptance SE2.** A catapult-teched house at war deploys a tower on the deploy cadence; the tower advances
each step; placed adjacent to an enemy `WOOD_WALL`, `_breach_palisade` turns it to `SAND`. Gate off → no tower.

## Constants (sandkings.py)

```
SIEGE_ENGINES_ENABLED = False  # gate (module default False -> byte-identical; entrypoint flips, --no-siege)
BALLISTA_RELOAD = 25           # steps between bolts (faster than the catapult's 40)
BALLISTA_DAMAGE = 20           # direct maw damage per bolt (high; no splash)
BALLISTA_RANGE  = 44           # flat trajectory reaches across the whole board
BOLT_SPEED      = 6            # a bolt flies faster than a lobbed shot (SHOT_SPEED = 3)
```

## Acceptance (tests/test_siege.py)

- Gate default OFF; gate-off full battery byte-identical.
- SE1: a war-ready catapult house looses a bolt (maw damage + visible 'bolt') on reload; the bolt flies faster
  than a shot and bursts on arrival.
