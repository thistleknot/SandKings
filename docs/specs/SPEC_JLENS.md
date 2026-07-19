# SPEC — The Colony J-lens: read (and steer) a colony's unspoken thoughts

Status: **IMPLEMENTED** (2026-07-18) — `MaskedMind.jlens/inject`, `TongueSystem.read_thoughts/inject_thought/
treachery`, wired in `_tongue_observe` (readout) + `_colony_encodings` (keeper injection) + `keeper_inject_thought`,
gated `JLENS_ENABLED` baseline-on, byte-identical off; battery 81/0; `tests/test_jlens.py` green; reads colonies'
unspoken thoughts live. No authored knobs (standouts = median+MAD-sigma; inject scales to the hidden's norm). Extends
SPEC_TONGUE. Inspired by Anthropic's global-workspace / Jacobian-lens work.

## Why

The keeper's opening question — "have they reached sentience? you should be able to observe logs." The Tongue already
gives colonies a learned vocabulary of thought; the J-lens reads it. The MaskedMind head is `Linear(hidden⊕ctx →
per-token logits)`, so the Jacobian of token t's logit w.r.t. the hidden is exactly `head.weight[t, :H]`. Projecting a
colony's brain ENCODING through `head.weight[:, :H]` (ctx=0) yields the tokens the colony is positioned to emit — its
J-space at that step, in its own evolved vocabulary. This is a legitimate *shallow* analog of the J-lens (read what it
might say), NOT a claim of a full global workspace — that structure would need the depth/scale NEAT+Breath are growing
toward; the J-lens is the instrument to WATCH for it.

## Decisions (resolved)

- **Read from the maw brain ENCODING** (`HiveMindBrain.forward` output, `H=encoding_dim=32`), already computed each
  neural step — the lens is a single extra `(vocab×H)·(H)` matvec, tight.
- **Jacobian = the head's hidden-half weight** (`head.weight[:, :H]`); no autograd needed (the head is linear in the
  hidden), so the lens is pure inference — zero RNG, zero evolution side-effects.
- **Injection** steers the hidden along a token's Jacobian direction before the colony acts (the god-hand at the level
  of thought). Keeper-triggered only (it changes dynamics), never automatic.
- **Awareness/treachery meter** = aggregate J-weight on the vocab's "dark" tokens (war/raid/betray/thrall…) — a
  readout of a colony privately leaning toward treachery before it acts.
- Gated `JLENS_ENABLED` baseline-on; off ⇒ no lens computed, byte-identical.

## Structural (additions to sim/tongue.py MaskedMind + TongueSystem)

Constant: JLENS_ENABLED — feature gate; off ⇒ no lens/thoughts computed (byte-identical).
(No authored top-k / strength knobs: read_thoughts surfaces the STATISTICAL standouts — weight above median +
robust MAD-sigma of the J-space, so a handful emerge naturally; inject scales to the hidden's OWN norm.)

class MaskedMind [entity] (existing): + two pure-inference readers over the existing `head`
    jlens(hidden) -> Tensor: per-vocab logit from the hidden ALONE (ctx=0) = head.weight[:, :H]·hidden + bias;
        the Jacobian read-out. Fails safe: returns zeros if hidden is degenerate. (Maintain: no Parameter/grad touched)
    inject(hidden, token_id, strength) -> Tensor: hidden nudged along head.weight[token_id, :H] (unit-normed) ·
        strength; raises that token's future logit. (Require: 0 <= token_id < vocab_size)

class TongueSystem [service] (existing): + the colony-facing lens
    read_thoughts(encoding, k) -> list[(str, float)]: the top-k J-space tokens (name, weight) for a colony's
        encoding; empty if the head is absent. Names via the vocab index.
    inject_thought(encoding, token: str, strength) -> encoding: steer an encoding toward a concept (keeper hand).
    treachery(encoding) -> float: summed J-space weight on the dark-token set in [0,1]; a betrayal-lean readout.

## Behavioral (wiring in sim/sandkings.py — the observe step)

Where JLENS_ENABLED and the colony has a neural brain, after the per-colony encoding is computed (the existing
`brain(states)` call), read the J-space and stash it on the colony for the log/console — a pure observation, no
dynamics change:

Loop over each living neural colony c each observe tick:
    enc ← c.genome.brain(...)                         # already computed for the sim
    When JLENS_ENABLED:
        c.thoughts ← tongue.read_thoughts(enc, JLENS_TOPK)   # [(token, weight), …]  (Maintain: no sim-state mutation
                                                             #   beyond the c.thoughts annotation)
    # story/chat surface: "[MIND] House N is thinking: war, hunger, betray"

Injection is a keeper command (mirrors keeper_command_war): `keeper_inject_thought(colony_id, token)` applies
`tongue.inject_thought` to the colony's next-step hidden.

## Acceptance

- Given JLENS_ENABLED False, When a neural colony steps, Then no `c.thoughts` is computed and the Tongue determinism
  suite stays byte-identical.
- Given a colony encoding, When read_thoughts runs, Then it returns JLENS_TOPK (name, weight) pairs ranked by the
  head's hidden-Jacobian, consuming no RNG and mutating no Parameter.
- Given inject(hidden, t, s>0), When the injected hidden is re-lensed, Then token t's J-space weight MUST rise
  (monotonic in s) — the steer works.
- Given a live soak with the gate on, When the story log is read, Then colonies' unspoken thoughts appear in their
  evolved vocabulary; the sim runs clean and remains checkpointable.

## Gating

`JLENS_ENABLED` module default False → `run_tests._GATE_NAMES`-style reset → entrypoint baseline-on. Off ⇒ zero lens
compute, byte-identical. The readout is side-effect-free (no RNG, no dynamics), so even on it cannot perturb evolution;
the gate bounds compute and keeps the battery provably clean.

## Provenance

Anthropic "A global workspace in language models" (J-lens / J-space, 2026); reuses SPEC_TONGUE's MaskedMind head.
Relates to [[tongue-arc-masked-mind]], [[neat-peft-adapter-direction]], [[multi-view-ensemble-learning]].
