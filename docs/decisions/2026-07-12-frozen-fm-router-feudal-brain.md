# Decision: Frozen foundation-model router — a feudal maw/spawn brain

Date: 2026-07-12. Status: architecture accepted (this design dialogue); scope
**undetermined** → next step is a scope decomposition (Fable), then per-module
specs (Opus), then phased impl. No code yet. Identity-at-neutral / default-off
gating per house rules once implementation begins.

## Problem / vision

Stop **evolving intelligence from scratch**. A random-init maw brain climbing to
competence by neuroevolution is slow, unstable, and re-derives inductive priors
the ML field already ships for free. The sand kings are meant to *start*
intelligent and only learn the small **delta** — from a competent baseline to the
"aha moment" that unlocks the breakout. That delta is narrow, so the *learnable*
net can be tiny if we **borrow a frozen, pretrained universal function
approximator** and only train the orchestration on top.

This also realizes the founding compute split verbatim: **the maw bears ~85% of
the cost, the spawn the trailing ~15%** — see [[semipermeable-params-direction]]
and the 85/15 note. The expensive frozen substrate lives in the queen, amortized
**once per colony per batch cycle** (NOT per step); per-step cost is only the spawn's
cheap conditioned mini-nets + compiled rules.

## Architectural decision — FEUDAL 3-TIER: queen routes frozen FM functions; managers mediate; spawn execute

A feudal hierarchical-RL structure (FeUdal Networks; options/skill-orchestration
family): **three tiers, disjoint jobs, two clocks.**

- **Queen (maw) = the mind — the ONLY RL-trained component, batch clock.** An **agentic
  tool-calling agent** (ReAct-style): it holds a **human-readable dialogue** with its
  manager-adviser and, when ready, **orders the frozen TabFM "master tools"** (agentic
  ordering of calls) and/or commits an **ad-mixture of options** — or **continues the
  conversation** to gather more (much like Claude Code's back-and-forth before a tool
  call). Tool responses feed an **RL loop internal to the maw**. **Substrate: compact RL
  policy** (resolved → B) — a small RL net, no LLM; obs = the manager's parsed schema +
  latent, action = mixture-over-menu | continue-query.
- **Manager (officer) = adviser — NON-RL, batch clock.** Frozen **Qwen + few-shot**, with
  **temp 0 + constrained/grammar decoding** so it emits a *stable schema* the maw can parse
  and choose from (the format-stability concern → solved by few-shot + JSON/grammar
  decoding, not free text). Transcribes fauna tags → feedback, synthesizes the option
  menu/advice, and issues the maw's committed instruction downward as **pheromone
  packets**. **No learning.** New role — no current code analog.
- **Spawn (worker) = existing `SoldierLayer` mini-nets — step clock.** Per step: run a
  **compiled rule set** (from the queen's DSL) + a **bounded RL residual** conditioned on
  the fixed beacon + local obs → action; deposit cheap thought-tags on pheromones. The
  ~15%. **No FM, no LLM on the per-step path.**

### How a directive becomes behavior — parameterized skills + residual RL

The maw does not micro-control spawn. It **sets each spawn's constants** — food
ration, labor-role weights, responsibility assignment (a Dwarf-Fortress **labor
optimizer**). Those constants ARE the directive / "TextGrad formula," and they
parameterize a **deterministic base response** the spawn runs by default
(parameterized skills: the manager sets the worker's params θ — Learning
Parameterized Skills, arXiv 1206.6398). On top of the base, the spawn's small local
net adds a **bounded RL residual** — the *play*: `a_total = a_directive(s) +
a_residual(s; θ)`, residual clipped to ~10–20% of action range (Residual Policy
Learning, arXiv 1812.03201). The clip *is* the play: it keeps the spawn on-directive
while letting it react to its immediate environment — the "alive" feeling.

The maw's constants are **held fixed within a batch cycle** ("constants between
batch cycles"), so the residual RL trains against a **stationary directive** — clean
credit assignment, and residual RL's headline win: convergence in 10^4–10^5 steps vs
10^6–10^7 for full RL on the same tasks. That is how RL is *reserved for where it
matters* — a cheap bounded residual per spawn, never a full policy per spawn.

### Chained message passing (the note + the bus)

Mental model: the maw **writes a note** — a low-bandwidth message of a few constants
+ conditional "if-X-in-your-environment-do-Y" response rules — that is **dispersed
down the hierarchy** to the team. Spawn consume only `note + local environment`,
never the maw's reasoning; that bandwidth cap is what makes the chain cheap and
arbitrarily deep. This is hierarchical goal-propagation, and it rhymes with the
GraphPFN in the zoo (attention-based graph message passing).

The **dispersal medium is the existing pheromone/psionic network** — the maw injects
the note, the network fans it out, each spawn reads the local message. Open structural
fork ("maw writes a note for its *manager* to disperse"):
- **2-tier:** the pheromone bus *is* the "manager" (a medium, not an agent). Simplest.
- **3-tier (officer caste):** maw → a **manager/officer spawn** that aggregates its
  squad's local state upward and relays a squad-local note downward → workers.
  Multi-level feudal; bounds the maw's fan-out; pure Dwarf-Fortress manager-noble.
Decide before speccing the message schema — it sets the hierarchy depth.
**Resolved → 3-tier, bidirectional** (see "Queen mind + reduced minds" below).

### Psionic dispersal — distance-temperature, EMA, frozen rollout

The **batch-cycle update IS the psionic broadcast**: the psionic/pheromone network is
the *batch-clock* bus (carries the revised note on dispersal, not per-step chatter).

- **Distance → temperature → perturbation.** The same note is decoded *hotter* the
  farther a spawn sits from the source — grounded in the existing pheromone
  concentration decay (distance ↑ → SNR ↓ → more interpolation/sampling → higher
  effective temperature). Emergent payoff: **exploration–exploitation zoning** — core
  spawn exploit the directive faithfully (low temp), frontier spawn improvise (high
  temp). Spatially-structured parameter-space noise (cf. Plappert et al. 2017).
- **EMA rolling update.** `constants ← (1−α)·constants + α·(received note)` — Polyak /
  target-smoothing: self-correcting, anti-thrash; the within-batch deterministic policy
  drifts slowly rather than snapping.
- **Cost thesis (crystallized).** Policy **weights are frozen for the whole batch
  rollout** — no learning, no sampling, parallel, cheap. Learning + constant
  perturbation + EMA happen only at the boundary.

**Load-bearing clarification:** "deterministic between batches" = frozen policy
*weights*, NOT frozen *behavior*. The spawn still reads live observations and reacts
every step via the bounded residual — that closed-loop reaction is the mandated
"alive" RL and **cannot** be replaced by the open-loop distance-temp perturbation
(diversity ≠ responsiveness). Within-batch = frozen weights + reactive residual;
boundary = revise constants, EMA-disperse with distance-temperature, RL-update the
residual. The temperature gradient rides whichever hierarchy the tier fork picks
(distance-from-maw in 2-tier, distance-from-officer in 3-tier).

### Cadence, contact, global awareness, indexed dispatch

- **Cadence:** the batch cycle rides the existing `POP_TICK_INTERVAL = 50`
  (`sandkings.py:86`) — the strategy clock, distinct from `BIOME_TICK`=20 / `TECH_TICK`.
  No rogue clock. **Stagger the phase per colony** (`(step + colony_id·k) % 50`) so the
  heavy maw passes don't all fire on one boundary (compute-spike avoidance).
- **Contact → temperature 0 → crystal-clear orders.** The clean limit of the distance
  gradient (`temp(0)=0`): a spawn in direct contact with the maw receives the directive
  with zero perturbation. Biologically grounded (eusocial contact communication —
  trophallaxis / antennation). Emergent: units pilgrimage back to the maw to resync
  hazy frontier orders.
- **Global awareness in the note = CTDE** (centralized training / decentralized
  execution). The maw holds the global view; the note injects *just enough* privileged
  global context into otherwise-local spawn. This is the manager's reason to exist.
- **Indexed single-pass dispatch (batching primitive).** Batched inference with
  scatter/gather — stack rows into one tensor → one forward → scatter outputs by
  `id(unit)` (the existing `_colony_encodings`, re-roled). Applies to (a) the **spawn
  shared-weight local nets per step** (cheap; enabled by the state-not-weights rule) and
  (b) any **colony-level** TabFM call at the batch boundary (homogeneous askers batch →
  O(#functions), not O(#spawn)). The queen's default is **one colony-level problem per
  function per batch**, NOT per-spawn rows; per-spawn rows are the O(#spawn) fine-grained
  knob.

### Queen mind + reduced minds — CTDE, bidirectional 3-tier

**Not a hive mind.** One **queen mind** (maw, large centralized reasoner) + N
**reduced minds** (spawn, small individual policies). This is **CTDE** (centralized
training / decentralized execution) with *individual* policies: each spawn is
**conditioned on** the beacon, not commanded by it. The beacon is an input feature to
the spawn's local net, interpreted against its own obs + private memory +
RL-from-experience → distinct behavior. **Spawn have read-only access to the maw**
(CTDE's contract: execution reads the centralized signal, never writes it). The
"distinction / self-awareness" is real: private state + conditioning on a shared
signal. (The batched single-pass dispatch is a *compute convenience* that also carries
the in-world **beacon** broadcast — two things riding one mechanism; don't conflate.)

**Resolves the tier fork → 3-tier, bidirectional.** The **manager mediates**: beacon
down, aggregated squad reports up. The upward path is **not optional** — the maw's
"one big problem" needs an input, and that input is the managers' compressed squad
summary (CTDE's centralized reasoner needs the joint observation). Loop:
`managers aggregate up → maw poses one big problem on the aggregate → TabFM →
beacon (its raw output) down → managers relay (distance-temp) → spawn interpret`.
Two channels: **read** = beacon (spawn ← maw); **write** = reports (spawn → manager →
maw). Never spawn → maw directly.

**Payload = TabFM's raw output** (one inference/cycle; the output vector is a
conditioning feature in each spawn's net). "One big problem" vs "distinct spawn" is
reconciled by scope: the TabFM call is **colony-level** (→ colony strategy constants);
**per-spawn variety comes from the local nets + private state + distance-temp**, not
per-spawn TabFM calls. (Per-spawn rows are a knob at O(#spawn) cost.)

**Engineering rule — distinction lives in private *state*, not private *weights*.**
Per-spawn weight matrices cannot be batched (→ O(N) forwards, killing the indexed
single-pass). Spawn share one small-net architecture + weights, individuated by their
**private stochastic latent** (the trainable latent) + local obs + perturbed beacon →
keeps the single batched pass AND gives each spawn a distinct inner life. Weight-level
individuality comes slowly from evolution/lineage; runtime rollout stays
shared-weights + private-state.

### Upward feedback — stigmergy (lateral) + contact-gated manager log (to queen)

**Spawn have NO psionic uplink — the queen channel is receive-only.** (Corrects the
earlier "mean-field aggregation" framing.) Spawn-originated information travels two
non-psionic ways:

1. **Stigmergy (lateral; never reaches the queen).** Decaying, typed ± pheromone trails
   (`food`/`threat`/`hot`, positive and negative) laid along traversed paths so the
   trail radiates a followable gradient back to its source ("glowing fauna from one
   energy source") — a decentralized, decaying **spatial value function** others
   hill-climb (Grassé stigmergy; Ant Colony Optimization; eligibility-trace-like backward
   credit along the path). **Already in code:** `PheromoneLayer` (per-colony/type
   `deposit`, `decay`=0.95, `gradient_direction`). Refinements only: confirm typed ±
   valence + lay trails along the return path.
2. **Contact-gated manager log (the only route to the queen).** A spawn's "thought"
   reaches the queen ONLY by **physically contacting a manager**, who logs it (symbolic:
   typed/valenced/located) and relays the log at the batch boundary. The manager pools
   its **contacted subset** with order-stats — **mean** (load→reallocation), **max/any**
   (extremes→threat), **variance** (disagreement) — but over who it *touched*, not the
   whole colony.

**Consequence (honest): the queen's centralized view is a contact-SAMPLED partial
observation**, biased to manager coverage; frontier units are "dark." Breaks naive
CTDE-full-obs → **communication-constrained CTDE**. It is a *feature*: **stigmergy is
the coverage for what the queen can't see** — pheromones self-organize local/frontier
behavior in real time (queen out of the loop), the queen does global strategy on the
sampled log, the RL residual handles local reaction; the three layers cover each other.
The manager is a **mobile collector** whose circulation sets the queen's awareness
(emergent lever + natural bandwidth bound).

**Two abstraction levels:** pheromone = subsymbolic scalar field (spawn-local, fast,
queen-blind); thought-log = symbolic (contact-gated, feeds the 50-step batch). **DF
thoughts** ride the symbolic log: each spawn's private latent carries valence dims
(mood/stress/threat-salience) that become logged thoughts on contact.

**TextGrad on both sides:** beacon-down = forward pass; thought-log-up = backward
critique → TextGrad revises the directive (needs the log structured — the DSL — so
"warriors report heavy losses NE" becomes a gradient: reduce aggression NE). The
pheromone loop is *separate* — pure stigmergic self-organization, no TextGrad.

### Grounded directives (phase-2) — language maw + entity blackboard

Directives like *"attack the rabbit that appeared from the upper-left quadrant 10 steps
ago"* exceed a numeric constant-vector and tip the maw fork → **language maw**: TextGrad
frames the optimization as a prompt; Qwen-0.8B composes the grounded directive. Costs,
both bounded: (1) the LLM runs **maw-only, batch-clock-only** (once per colony per
`POP_TICK_INTERVAL`; spawn never run it — 85/15 intact); (2) needs an
**entity/spatiotemporal blackboard** (seen entities with position + timestamp) for the
directive to *refer* to and the spawn to *resolve*. Buildable but a distinct capability
layer — **phase-2** on top of the numeric core; the rabbit case is the use-case that
justifies paying for the language maw.

### Division of labor — TabFM engine vs Qwen interpreter; the directive DSL

**Economy is not TabFM-vs-Qwen — it is keeping *both* off the per-step spawn path.**
Rule that sets the whole budget: **no foundation-model forward per spawn per step.**
TabFM and Qwen both live at the maw's **batch clock**; the spawn run a compiled cheap
policy.

- **TabFM = the function/engine.** At the batch boundary it emits a **compiled rule
  set** (a decision-list — literally if/else, which is what a tree/FM is under the
  hood). The spawn **execute that rule set deterministically each step** (+ RL
  residual). TabFM *produces* rules once/cycle (cheap); spawn *run* them per step
  (free). Un-economical trap: TabFM live per spawn per step — never on the hot path.
- **Qwen/TextGrad = the interpreter.** Verbalizes the logic for the player and
  (phase-2) composes grounded directives. Not a substitute for TabFM — a different
  axis (*what to do* vs *how to say it*).

**The directive DSL (clean pseudocode) is the single artifact — one thing, three
consumers:** a **compiler** → spawn deterministic rules (execution); **Qwen** →
player-facing thoughts (`aggression:70% warriors, alert, patrol NE` → *"the warriors
grow restless and turn northeast"*) (observability); **TextGrad** → optimizes it as
text/pseudocode (outer loop). "Qwen struggles unless clean pseudocode" is *why the DSL
must exist* — it is simultaneously the clean pseudocode Qwen needs and what compiles to
deterministic if/else.

**Language layer is lazy/on-demand:** verbalize only on player inspection or significant
events (DF announcements), not every colony every cycle. TabFM always-on (batch clock);
Qwen on-demand. Economy preserved by keeping both off the per-step path and gating the
language layer on demand.

### Where the language faculty lives — manager tier; thought-tags; gather-then-interpret

Cost placement (cheapest coherent): **the language / TextGrad faculty lives at the
MANAGER tier — not per-spawn, not necessarily the queen.**

- **Spawn never run an LLM.** They run their **local RL net** (reactive residual) and
  deposit cheap **thought-tags** onto pheromones — a small typed/valenced/located marker
  co-located with the scalar field (`{type:threat, dir:NE, valence:−, t}`), not an
  LLM-generated sentence. **Semantic stigmergy:** the tag is the payload on the
  pheromone. O(1) per deposit.
- **Manager gathers-then-interprets ONCE.** After a handful of tags are gathered (from
  contacted spawn / encountered trails), the manager runs a **single**
  interpretation/translation pass (Qwen/TextGrad) over the batch → one representation it
  reads and logs to the queen. Expensive step is O(gathers), not O(spawn) — map (cheap
  tag deposit) / reduce (one manager interpretation).
- **Queen stays numeric.** With the manager as the translation membrane, the queen runs
  **TabFM (numeric)** on the manager-supplied representations; the **manager** is the
  bilingual tier — up: tags → representation for the queen; down: the queen's numeric
  directive → verbalized player-facing thoughts + spawn tags. Resolves the
  numeric-vs-language maw fork *better than a language maw*: language benefits without a
  language queen, concentrated at one tier, once per gather.

**Closes the psionic-uplink concern:** there is NO spawn→queen telepathy. The entire
uplink is physical/stigmergic — tags on decaying pheromones + manager contact + one
manager interpretation → log → queen. The batched psionic broadcast is **down-only** (a
compute convenience for the beacon); nothing psionic travels up.

### The maw's agentic decision loop — dialogue → order frozen tools → internal RL

**Only the maw is RL-trained.** It is an **agentic tool-calling agent** (ReAct-style); the
manager is a **non-RL, few-shot-prompted** adviser. Loop per batch cycle:

1. **Spawn** leave thought-tags on pheromones (step clock, cheap).
2. **Manager (adviser, non-RL):** frozen Qwen + few-shot, **temp 0 + constrained decoding**
   → deterministically transcribes tags → fauna feedback, and emits a **stable-schema**
   option menu + advisory the maw can parse.
3. **Maw (RL agent):** holds a **human-readable dialogue** with the manager; when ready,
   emits an **agentic ordering of frozen TabFM "master-tool" calls** and/or an **ad-mixture
   of options**, or **continues the conversation** for more (like Claude Code's check-ins
   before calling tools). Frozen tool responses feed an **RL loop internal to the maw**
   (reward = downstream survival/dominance).
4. **Manager issues** the committed instruction **as pheromone packets** to its squad.
   Down-channel: queen →(psionic)→ managers →(pheromone packets)→ spawn.

**TabFM = the frozen "master tools"** the maw orders (not a menu-scorer). **The learnable
surface is exactly one thing: the maw's tool-calling policy.** Everything else — TabFM, the
manager's Qwen, the spawn substrate — is frozen or prompted. **Compute:** "85%" = the top
cognitive apparatus (queen + managers, batch clock); "15%" = the spawn field (step clock).

**RESOLVED → B (compact RL policy).** The maw is a **small RL net, no LLM.** *Observation*
= the manager's **parsed grammar-schema advisory** + colony aggregate + its own latent;
*action* = a **mixture over the option menu** (ad-mixture of ordered tool-calls) **or
continue-with-structured-query**. Consequences:
- **Qwen runs only at the manager**; no LLM on the maw or spawn.
- **QLoRA drops out** — no LLM adapter to train. Of the four TRIZ tools, **TabFM + Qwen +
  TextGrad are used; QLoRA is not** (it was the price of Option A).
- The maw↔manager "dialogue" is **structured turns**; the human-readable text is the
  manager's Qwen **rendering choices for the player**, not free-form maw language.
- The router-reward / credit-assignment hard part now lives on a **tiny action space** —
  far more tractable than a full tool-use LLM (downgrades open-risk #1).

### Pheromones as a mycorrhizal memory network — proto-thoughts, class-sentiment, regional consensus

The pheromone field is an **above-surface network** analogous to the mycorrhizal
"wood-wide-web" (real biology: trees relay stress/defense signals through fungal networks —
Simard et al.). It is not just gradients — it is the colony's **distributed, spatial,
decaying memory + comms substrate**, carrying:
- **Proto-thoughts** attached to trails, generated from **nearby conditions felt** (cheap,
  spawn-deposited).
- **Idea-classes with ± sentiment** — each class (a place, a prey, a hazard) accumulates
  running positive/negative valence as spawn deposit experiences → a spatial, class-indexed
  affect map.
- **Logged consensus memories** written back by the batch-cycle poll (below).

**Regional consensus poll (batch cycle; LLM budget bounded to regions × batch):** partition
the map into regions (start coarse — quadrants); per region, aggregate the mass of spawn
proto-thoughts + class-sentiments into a **preloaded prompt** (nearby conditions + a stat
block); **one temp-0 Qwen call per region** responds *as the regional consensus*; the result
is written **straight back to the pheromone field as a logged "memory."** LLM used
*intelligently* — per region per batch, never per spawn per step. **Executor = the manager**
(Qwen stays manager-side); spawn contribute cheap proto-thoughts and *benefit* from the
consensus without each running an LLM.

**Two design notes:** (1) **region granularity × colonies = the LLM budget** — keep it coarse
unless a region needs resolution; (2) **logged memories decay slower than raw trails** — two
rates (fast trails for real-time coordination, slow memories so the field persists as
memory).

**Bonus:** this memory field is a cheap version of the phase-2 **entity/spatiotemporal
blackboard** — grounded references ("a threat at upper-left, recent") resolve against the
logged spatial memories, bringing the grounded-directive vision closer with no separate
subsystem. Feeds up: regional consensus memories → the manager's advisory schema → the maw.

### Design intent — lossy by design ("the letters never sent")

Flavor that is also a spec constraint. The pheromone comms are **trench-warfare
phonelines** (laid terrain, degrading with distance, cuttable), and most spawn
proto-thoughts are **battlefield love letters never sent** — they decay before a manager
collects them, or fall in an unpolled region. **The loss is a FEATURE, not a bug:** it is
the pathos and the emergent realism — a non-omniscient queen ruling on a sampled fraction of
what the colony felt. **Do NOT "fix" the contact-sampled partial observation into a complete
uplink** — that erases what makes it feel alive. Optional observability payoff: surface the
*lost* memories to the **player** (the decayed thoughts that never reached command) — the
metaphor made playable.

### Refinement: Qwen as AutoML-config tool; TextGrad as a second (coupled) RL

Sharpens the maw's tool-call and re-shuffles where language/learning sit:
- **Qwen as an AutoML-config tool the maw calls.** Given the state's `pandas.columns`, Qwen
  selects **which columns are X (features), which is y (target), which backend/algorithm, and
  what objective** (classification vs regression). The maw's tool-call is thus a **concrete
  feature/task spec**, not a raw vector; TabFM runs that spec on the actual data → an interpreted
  answer. Consistent with "maw = compact RL, no LLM": Qwen is a *tool the maw invokes*, not its
  controller. Maps onto the build: "objective" = task type (TabPFN ships Classifier + Regressor),
  "algorithm" = the `FM_BACKENDS` choice.
- **TextGrad lives at the MANAGER as a shared-trunk, two-head refiner** (SETTLED). Trunk reads
  `{maw communication + fauna}`; **Head-U** emits the reply up to the maw, **Head-D** emits the
  directive down to the spawn — one forward → rationale + both recipient messages ("what I'll say
  and why, then the pieces"). **Alternating-frozen heads** (actor-critic intuition as a stability
  rule): freeze one head while the other responds/updates, so the two directions couple through the
  shared trunk but **structurally cannot oscillate** (enforces disjoint-variables by construction).
  This **revises "manager is non-RL"** — the manager gains this one two-head refiner; the maw stays
  the pure decision-RL.
- **Spawn adaptive upward voice** — extend the spawn local RL with a small **signaling head** so
  *what they deposit* varies with env (fills the "no connective response to the manager" gap);
  still inside the ~15%.

**Build discipline (learner count):**
three small learners total — maw *decision* RL, manager *two-head TextGrad* RL, spawn *signaling* RL
— which walk back the "one learnable surface" simplification. Build discipline: **ship the maw
decision-RL alone first (Phases 0–2)**; the manager two-head refiner and the spawn signaling head are
**gated later phases**, added once the maw loop is stable, so we never stabilize coupled learners at
once.

### The frozen function library (PFN zoo, per modality)

Each sub-problem of a "systems" decision maps to a frozen prior-data-fitted network
— a universal in-context approximator that needs **no task-specific training**:

| sub-problem | frozen function |
|---|---|
| tabular supervised/unsupervised (threat, forage yield) | TabPFN / TabPFN-v2 |
| graph (terrain, pathing, kinship) | GraphPFN (arXiv 2509.21489) |
| time-series (population/resource trend) | TS-PFN |
| causal (intervention/what-if) | CausalFM / Do-PFN (arXiv 2506.10914) |

The router does not force any single model to chain (PFNs are single-shot, not
CoT). **The chain lives in the router** — it composes atomic frozen inferences into
a system-level decision. This is the resolution of the CoT objection.

### Trainable stochastic latent (the "extra memory / decision space")

"Give a ReAct agent trainable latent space." The repo already has the primitive:
the earned **KV-cache augment** (`neural_hive.py:302`, `cache_len` /
`memory_augment`, `AUG_CACHE_STEP=8`, AUG1–AUG3). Today it is a *fixed* summary of
cached past states. The delta: make it a **learned** summary — inner loop writes
it, outer batch consolidates it. **Constraint:** it must be **stochastic**, not a
deterministic hidden state — group-relative RL (GRPO) is known to fail on
deterministic latent recurrence (Coconut / continuous-thought line, arXiv
2512.11816); the working fix is injected stochasticity (variational dropout / mask
replay, arXiv 2606.10184). So: stochastic latent goal, feudal-style.

## Two-timescale optimization (inner RL / outer consolidation)

- **Inner — every step:** the **spawn** act online — compiled rules + bounded RL residual
  conditioned on the fixed beacon + local obs (reward = survival/dominance, embodied,
  sparse). The queen's router does NOT run per step.
- **Outer — every batch cycle:** re-run a DSPy/TextGrad-shaped **offline** pass over
  that batch's accumulated `(state → route → outcome)` traces to rewrite the
  **programmatic rules** — default constants, routing priors, live-function set,
  latent consolidation. This is the existing generation/consolidation cadence
  applied to the router (same "frequent updates + periodic consolidation" split the
  memory architecture already uses); DSPy's compile step is the **warm start** for
  the constants, RL routes online thereafter.

**Stability rule (load-bearing):** inner and outer must touch **disjoint
variables** — outer owns structure/defaults/curriculum/available-functions; inner
owns the routing policy + soft constants online. Same objective on shared params =
two-optimizer oscillation. (This is exactly why DSPy's compile-time structure and
the LM's run-time execution do not fight.)

## Why frozen PFN and not a QLoRA'd LLM

- **No representation mismatch.** A PFN's native input *is* a tabular feature/CSV
  row — the sand-king state (`encode_soldier_state`, ~40 dims) drops in directly. An
  LLM needs a learned projection from 40-dim state into token/embedding space.
- **No "what tasks?" problem.** PFNs are in-context; you feed the colony's *own*
  experience rows at inference — nothing to pre-train on. The task-definition
  friction the user flagged dissolves under PFN and persists under an LLM.
- **Much smaller trainable footprint.** Because it is *layered* (frozen substrate +
  thin router + spawn mini-nets), the learnable parameter count is tiny vs adapting
  a billion-param LLM even with QLoRA/QA-LoRA. Frozen substrate → no backprop
  through the big part; only the router + latent + spawn nets update.
- **GGUF is not a path for PFN.** GGUF/llama.cpp targets LLM tensor layouts +
  tokenizers; a row/column-attention PFN with no tokenizer does not convert.
  (QA-LoRA — quantization-aware LoRA, arXiv 2309.14717 — is real but an LLM
  technique, orthogonal to the base choice.)

## Grounding (empirical)

- Frozen TabFM as an RL value/Q approximator, pure in-context, no gradients:
  "Gradient-Free Deep RL with TabPFN" (arXiv 2509.11259). Caveat: demonstrated only
  on low-dim classic control; latency quadratic in context; discrete actions.
- Frozen-FM-features + swap-only-the-head protocol (arXiv 2606.02106).
- Feudal / options / manager-over-frozen-skills HRL; hierarchical credit assignment.
- Latent reasoning + the deterministic-recurrence RL failure (arXiv 2512.11816,
  2606.10184).
- LoRA/QLoRA/QA-LoRA as the adapter precedent (arXiv 2309.14717).

## Maps onto existing code (a re-role, not new machinery)

- `HiveMindBrain` → maw/Manager: the frozen-PFN router + latent (batched once/colony
  via `_colony_encodings`, already added).
- `SoldierLayer` → spawn/Worker: conditioned mini-net + compiled rules + tag deposit.
- **Manager/officer tier → NEW** (no current analog; a genuine addition, not a re-role):
  the bilingual mediator between queen (numeric) and spawn (stigmergic); hosts the
  language faculty + the contact-gated thought-log.
- `memory_augment` / `cache_len` → the trainable stochastic latent.
- Neuroevolution cadence → the outer consolidation loop.
- Soft constants → [[semipermeable-params-direction]] (jitter/soft_gate,
  identity-at-neutral).

## Open risks / undetermined scope (why this goes to Fable next)

1. **Router reward + credit assignment across composed calls — THE hard part.** The
   PFN zoo is frozen/borrowed/easy; all risk concentrates here. Sparse embodied
   reward over a multi-call chain.
2. **Latent must be stochastic** to be RL-trainable (above).
3. **TabPFN-v2 embedding-extraction API** for the permeable-head path — needs a
   spike before speccing; may constrain to the pure-in-context or context+head
   compose.
4. **Per-colony latency budget** of the PFN zoo on GPU (quadratic-in-context); must
   stay within the per-step frame at colony scale.
5. **Two-optimizer separation-of-variables** discipline must be enforced by design,
   not convention.
6. **Identity-at-neutral / default-off gate** so the battery stays byte-identical
   until the subsystem is enabled (house rule; cf. the hydro/dynamic gates).

## Status & routing

Architecture accepted here. Scope is undetermined (a PFN-zoo integration + an RL
router + a trainable latent + a two-timescale loop across `neural_hive.py`,
`neuroevolution.py`, `sandkings.py`, `tech.py`) → **Fable** decomposes scope →
**Opus** writes per-module specs (incl. the identity-at-neutral gate) → **Haiku**
implements → **Sonnet** verifies. A dependency-0 spike (does TabPFN-v2 expose
per-step embeddings within the per-colony latency budget?) gates the head-vs-
context decision and should run first.
