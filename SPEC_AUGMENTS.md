# SPEC: Augments (Round 14) — AUG1–AUG5

User intent: "allow the maw to understand how to bio-mechanically alter
themselves, maybe for longevity... if they can master a raspberry pi they
can design neuron chips to augment themselves... akin to a KV cache...
they have to learn to 'upgrade' themselves with technology as a memory
extension. I don't want them to figure out engineering - just common
pieces of technology pre-wrapped for them... a simple call made known."

Design: an awakened colony EARNS a memory augment - the KV-cache
analogue - by invoking a PRE-WRAPPED terminal call. No engineering: the
capability is a single opcode already in their reach; using it widens
their soldiers' effective memory. It is learned (invoked), never
auto-granted at the breach.

## AUG1 — The KV cache (SoldierLayer memory bank)
`SoldierLayer` gains `cache_len` (default 0 = off) and a `mem_bank`
ring of its recent GRU hidden states. When `cache_len > 0`, forward
blends the mean of the bank into the state feeding the action head:
`effective = h + AUG_BLEND * mean(bank)` - literally caching past
states (keys/values) to extend temporal context, like a transformer's
KV cache generalized to the unit's recurrent memory. The RAW hidden
(read by the concept probes, N-spec) is unchanged, so decoded thoughts
keep their meaning; only behavior gains longer memory. Default 0 means
existing brains are byte-for-byte unchanged.

## AUG2 — Earning it (the pre-wrapped call)
A colony carries `memory_augment` (0..AUG_MAX 4). Terminal command
value 3 (K10 shell, pi-only) INSTALLS/UPGRADES the augment: +1 level,
each level adds AUG_CACHE_STEP (8) to the soldiers' cache_len. First
install: "House X augments its mind with cached memory" (salience 8).
The keeper may also bestow it as a gift ('neuron_chip', K9 ladder
extension) - a gift from the gods. Either way it is a wrapped call, not
engineering.

## AUG3 — Application
Each neural soldier's `brain_layer.cache_len` is synced to its colony's
`memory_augment * AUG_CACHE_STEP` on its AI tick (idempotent; covers
every spawn/mate path without touching them). Cadet branches inherit
the augment level (the upgrade persists in the bloodline, like the
breach). Longevity flavor: augmented colonies read the codex and fight
with steadier memory; the augment is a lasting advantage under
selection.

## AUG4 — Surfacing
The inspect panel (R33) and dashboard House card show an augment badge
("mem+N") for augmented colonies. EVENT_TINTS: "augments its mind"
breach-blue. SALIENCE: the augment install is 8 (a self-modification is
history).

## AUG5 — Acceptance
tests/test_augments.py: an augmented SoldierLayer fills its bank and
its action output reflects blended context while the raw hidden (probe
input) is unchanged; cache_len 0 is byte-identical to today; the
terminal grants the augment only to pi readers, bounded at AUG_MAX,
fires once; the augment level rides the cadet bloodline; everything
pickles; evolution sim inert. Skips cleanly without torch.

## Status / Reconciliation
- Drafted + implemented 2026-07-09 (same session). Verified: cache_len 0
  is byte-identical to the pre-augment layer; an augmented layer fills
  its bank and blends context into the ACTION output while the raw
  probe-read hidden is unchanged; the terminal grants the augment only
  to pi readers and caps at AUG_MAX; the level rides the cadet
  bloodline; the augmented layer pickles; evolution sim inert. 16/16
  suites green incl. tests/test_augments.py (6). Note: the keeper
  'neuron_chip' gift path (AUG2) is specced but deferred; the terminal
  self-install is the shipped route.
