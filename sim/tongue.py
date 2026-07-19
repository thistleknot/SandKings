"""SPEC_TONGUE TG1 — the masked-prediction head ("the Tongue"), an ADDITIVE learned component.

A small self-supervised masked predictor that reads the frozen soldier GRU hidden (32-d) plus a multi-hot of the
colony's currently-active world-tokens with a random subset MASKED, and reconstructs the full active set — so
masking a token and recovering it from context+hidden is the training signal (perception as masked prediction). It
NEVER touches the Kanerva-SDM / GRUCell Parameters (SPEC_SENTIENCE design law: small inspectable learned components,
no architecture change to pickled nets). Per-token accuracy EMA is the raw comprehension signal; TG4 reads its
LEARNING PROGRESS (rate of change), not the raw value (noisy-TV correction).

TG1 is the reference slice: a single shared head over the anchor vocabulary, order-free bag of the current step's
tokens. The evolved `read_reach` gene (SPEC_TONGUE TG1) — the n-gram/Markov order over PRIOR steps — is carried on
the genome and threaded here as `reach`; the sequential-chain use of it is a later slice. TG2 replaces the learned
`emb` with a GloVe-seeded-then-learned shared space and swaps the softmax-ish head for embedding-regression + kNN
decode (Kumar & Tsvetkov 2019).

Gated: `TONGUE_ENABLED` default False ⇒ the sim never constructs a MaskedMind ⇒ battery byte-identical.
"""
from __future__ import annotations   # lazy annotations so forward refs (e.g. TongueSystem -> TokenSpace) resolve

from typing import Dict, List, Optional

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _HAVE_TORCH = True
except Exception:
    _HAVE_TORCH = False

TONGUE_ENABLED = False        # gate: default off (battery byte-identical); entrypoint flips baseline-on
TONGUE_LR = 0.01              # masked-head SGD step
TONGUE_MASK = 0.15            # fraction of active tokens masked per step (BERT-style)
TONGUE_HIDDEN = 32            # matches the soldier GRUCell hidden dim
TONGUE_ACC_DECAY = 0.99       # per-token accuracy EMA (mirrors ConceptProbe)
READ_REACH_DEFAULT = 3        # genome default n-gram/Markov order (evolved; NOT a fixed context length)
NEG_SAMPLING = False          # gate: off ⇒ the dense full-vocab BCE (byte-identical); entrypoint flips baseline-on.
#                               On ⇒ word2vec-NEG masked-prediction — loss over active + K sampled negatives only:
#                               better objective for a large sparse vocab AND O(active+K), not O(vocab). K reuses
#                               neural_hive.KANERVA_ACTIVE (not authored). This is what makes a big vocab CHEAP.


if _HAVE_TORCH:
    class MaskedMind(nn.Module):
        """SPEC_TONGUE TG1 masked-prediction head. Shared across colonies; per-token accuracy kept per instance.

        Require:  hidden is a length-`hidden_dim` float vector (the soldier GRU hidden); active_ids are token ids
                  in [0, vocab_size). Guarantee: `observe` runs exactly one gradient step on the masked-reconstruction
                  loss and returns the mean masked-token recovery accuracy this step (or None if <2 active tokens);
                  pure w.r.t. any external state (only its own Parameters + accuracy dict change). Maintain: never
                  references or mutates the SDM/GRU tensors.
        """

        def __init__(self, vocab_size: int, hidden_dim: int = TONGUE_HIDDEN):
            super().__init__()
            self.vocab_size = int(vocab_size)
            # TG2 / SPEC_ENSEMBLE_EMBED: when the learned ensemble mixture is on AND its frozen npz matches this
            # vocab/dim, the embedding table becomes a LEARNED mixture over 6 aligned member models (BERT, GloVe,
            # word2vec, Jina, Nomic, MiniLM); the mixture weights train on the masked-prediction loss. Off / npz
            # absent / shape-mismatch ⇒ the current random nn.Embedding (byte-identical). Built BEFORE the optimizer
            # so the mixture's params are trained; the frozen member buffer gets no gradient.
            self.emb = None
            try:
                import ensemble_embed as _ee
                if _ee.ENSEMBLE_EMBED_ENABLED:
                    b = _ee.load_ensemble()
                    if (b is not None and b.members.shape[2] == hidden_dim
                            and b.members.shape[1] <= self.vocab_size):
                        mem = b.members
                        if mem.shape[1] < self.vocab_size:       # SPEC_FOL_TONGUE: appended role tokens (⟨SUBJ⟩…)
                            import numpy as _np                   # get small random member rows (learnable, frozen-buffer)
                            pad = _np.random.RandomState(0).normal(
                                0, 0.1, (mem.shape[0], self.vocab_size - mem.shape[1], mem.shape[2])).astype(mem.dtype)
                            mem = _np.concatenate([mem, pad], axis=1)
                        self.emb = _ee.build_mixture(mem)
            except Exception:
                self.emb = None
            if self.emb is None:
                self.emb = nn.Embedding(self.vocab_size, hidden_dim)      # TG2 fallback: random table
            self.head = nn.Linear(hidden_dim * 2, self.vocab_size)        # (hidden ⊕ context mean) -> per-token logit
            self.opt = torch.optim.SGD(self.parameters(), lr=TONGUE_LR)
            self.acc: Dict[int, float] = {}                              # per-token recovery accuracy EMA

        def _feat(self, unmasked: List[int], hidden: "torch.Tensor") -> "torch.Tensor":
            if unmasked:
                ctx = self.emb(torch.tensor(unmasked, dtype=torch.long)).mean(0)
            else:
                ctx = torch.zeros(hidden.shape[-1])
            return torch.cat([hidden, ctx])

        def observe(self, hidden, active_ids: List[int], rng, reach: int = READ_REACH_DEFAULT) -> Optional[float]:
            active = sorted(set(int(i) for i in active_ids if 0 <= int(i) < self.vocab_size))
            if len(active) < 2:
                return None                                              # need one to mask and one for context
            masked = [i for i in active if rng.random() < TONGUE_MASK] or [active[rng.randrange(len(active))]]
            unmasked = [i for i in active if i not in masked]
            h = torch.as_tensor(hidden, dtype=torch.float32).reshape(-1)[:self.head.in_features // 2]
            if NEG_SAMPLING:
                return self._observe_neg(active, masked, self._feat(unmasked, h), rng)
            # dense path (NEG off) — EXACT current behavior, byte-identical
            target = torch.zeros(self.vocab_size)
            target[active] = 1.0                                         # reconstruct the FULL active set from context
            logits = self.head(self._feat(unmasked, h))
            loss = F.binary_cross_entropy_with_logits(logits, target)
            self.opt.zero_grad(); loss.backward(); self.opt.step()
            with torch.no_grad():
                p = torch.sigmoid(self.head(self._feat(unmasked, h)))
                return self._score_masked(masked, p, lambda i: i)

        def _score_masked(self, masked, p, index_of) -> float:
            """Fold each masked token's recovery (p > 0.5) into its accuracy EMA; return the mean this step. Shared by
            the dense and NEG paths — `index_of` maps a token id to its row in p (identity dense; position map NEG)."""
            hits = 0.0
            for i in masked:
                hit = 1.0 if float(p[index_of(i)]) > 0.5 else 0.0
                self.acc[i] = TONGUE_ACC_DECAY * self.acc.get(i, 0.5) + (1 - TONGUE_ACC_DECAY) * hit
                hits += hit
            return hits / len(masked)

        def _observe_neg(self, active, masked, feat, rng):
            """Lean-synergy masked-prediction: word2vec-NEG loss over the active positives + K sampled negatives
            (K = KANERVA_ACTIVE, reused). O(|active|+K), not O(vocab) — makes a large vocab CHEAP and a stronger
            objective than a dense sigmoid over hundreds of always-zero outputs. Accuracy is fused from the SAME
            (pre-step) subset logits — no second full forward."""
            import neural_hive
            k = int(getattr(neural_hive, 'KANERVA_ACTIVE', 16))
            na = len(active)
            # K negatives in ONE torch draw (collisions with active are tolerated — standard NEG, and cheap: no
            # Python rejection loop). subset = active (positives, lead) ++ negatives.
            sub = torch.cat([torch.tensor(active, dtype=torch.long),
                             torch.randint(self.vocab_size, (k,))])
            logits = feat @ self.head.weight[sub].t() + self.head.bias[sub]   # (na+K,) — only the needed outputs
            target = torch.zeros(na + k); target[:na] = 1.0                   # positives lead the subset
            loss = F.binary_cross_entropy_with_logits(logits, target)
            self.opt.zero_grad(); loss.backward(); self.opt.step()
            with torch.no_grad():
                p = torch.sigmoid(logits[:na].detach())                       # fused accuracy over the positives only
                apos = {t: j for j, t in enumerate(active)}                   # masked ⊆ active, which leads the subset
                return self._score_masked(masked, p, apos.__getitem__)

        def observe_triplet(self, hidden, slots, rng) -> Optional[float]:
            """SPEC_FOL_TONGUE: role-typed masked-SLOT training. `slots` = [(role_marker_id, filler_id), ...] for the
            RESOLVABLE slots of one triplet (>=2). Masks exactly ONE slot; the context is the OTHER fillers PLUS the
            masked slot's role marker (so subject-slot vs object-slot prediction are distinguishable with the same
            per-token-logit head — the whole 'no new architecture' trick). Recovers the masked filler via the SAME
            masked-prediction machinery (NEG or dense). Only called when FOL_TONGUE_ENABLED (gated) — never in the
            byte-identical battery, so its RNG/compute never touches the SPEC_TONGUE path.

            Require: filler/role ids in [0, vocab_size). Guarantee: one gradient step on the single-slot recovery
            loss; returns that slot's recovery ∈ {0,1} (or None if <2 resolvable slots). Maintain: frozen ensemble
            members stay frozen; `observe` unchanged."""
            slots = [(int(r), int(f)) for (r, f) in slots
                     if 0 <= int(f) < self.vocab_size and 0 <= int(r) < self.vocab_size]
            if len(slots) < 2:
                return None
            mi = rng.randrange(len(slots))
            role_id, target_id = slots[mi]
            context = [f for j, (_, f) in enumerate(slots) if j != mi] + [role_id]   # other fillers + masked ROLE
            active = sorted(set(context + [target_id]))
            masked = [target_id]
            unmasked = [i for i in active if i not in masked]
            h = torch.as_tensor(hidden, dtype=torch.float32).reshape(-1)[:self.head.in_features // 2]
            if NEG_SAMPLING:
                return self._observe_neg(active, masked, self._feat(unmasked, h), rng)
            target = torch.zeros(self.vocab_size)
            target[active] = 1.0
            logits = self.head(self._feat(unmasked, h))
            loss = F.binary_cross_entropy_with_logits(logits, target)
            self.opt.zero_grad(); loss.backward(); self.opt.step()
            with torch.no_grad():
                p = torch.sigmoid(self.head(self._feat(unmasked, h)))
                return self._score_masked(masked, p, lambda i: i)

        def recovery(self, hidden, active_ids: List[int], mask_ids: List[int]) -> float:
            """Deterministic read-out (no training): fraction of `mask_ids` recovered (p>0.5) given the rest as
            context. Used by tests + the comprehension meter."""
            active = sorted(set(int(i) for i in active_ids))
            masked = [int(i) for i in mask_ids]
            unmasked = [i for i in active if i not in masked]
            h = torch.as_tensor(hidden, dtype=torch.float32).reshape(-1)[:self.head.in_features // 2]
            with torch.no_grad():
                p = torch.sigmoid(self.head(self._feat(unmasked, h)))
            return sum(1.0 for i in masked if float(p[i]) > 0.5) / max(1, len(masked))

        def jlens(self, hidden) -> "torch.Tensor":
            """SPEC_JLENS: per-vocab logit the hidden ALONE is positioned to emit (context zeroed) — the Jacobian
            read-out over the head's hidden half (the head is linear in the hidden, so its weight IS the Jacobian).
            Pure inference: no autograd, no Parameter/RNG touched. Zeros if the hidden is degenerate."""
            H = self.head.in_features // 2
            with torch.no_grad():
                h = torch.as_tensor(hidden, dtype=torch.float32).reshape(-1)[:H]
                if h.numel() < H:
                    return torch.zeros(self.vocab_size)
                return self.head.weight[:, :H] @ h + self.head.bias

        def inject(self, hidden, token_id: int, strength=None) -> "torch.Tensor":
            """SPEC_JLENS: steer the hidden along token_id's Jacobian direction (head.weight[token_id, :H], unit-
            normed) so that token's future logit rises. Default strength is the hidden's OWN L2 norm — the push is
            scaled to the encoding it perturbs (identity-relative), not an authored magnitude. Returns a NEW tensor."""
            H = self.head.in_features // 2
            with torch.no_grad():
                h = torch.as_tensor(hidden, dtype=torch.float32).reshape(-1).clone()
                s = float(h[:H].norm()) if strength is None else float(strength)
                d = self.head.weight[int(token_id), :H]
                h[:H] = h[:H] + s * d / (d.norm() + 1e-8)
            return h


COMPREHENSION_EMA = 0.98      # TG4: level smoothing
LP_EMA = 0.9                  # TG4: learning-progress smoothing (rate of change)

# SPEC_JLENS — the colony J-lens (read/steer unspoken thoughts). JLENS_ENABLED lives in sandkings (the gate). No
# authored top-k / strength knobs: the readout surfaces the STATISTICAL standouts (median + robust MAD-sigma of the
# J-space, so a handful naturally) and injection scales to the hidden's OWN magnitude (identity-relative).
JLENS_DARK = frozenset({"war", "enemy", "betrayed", "siege", "jealousy", "death", "dread", "monster", "danger"})
#                              the treachery/aggression subset of the vocab (semantic, not a number); meter sums these

# SPEC_VOCAB_EXTEND — grow the REPRESENTED vocabulary (what the head/embeddings/J-lens cover) from the 42 anchors to
# their nearest-neighbor concept cloud in the GloVe geometry. Active/supervised tokens stay the anchors (ids 0..41).
VOCAB_EXTEND_ENABLED = False         # gate; entrypoint flips baseline-on. Off ⇒ the 42-anchor vocab (byte-identical).


def _neighbors_per_anchor() -> int:
    """Neighbors pulled per anchor — REUSED from the system's sparse-code width (neural_hive.KANERVA_ACTIVE, i.e.
    how many concepts co-activate), not an authored breadth knob. Falls back to sqrt(#protos) if torch is absent."""
    try:
        from neural_hive import KANERVA_ACTIVE
        return int(KANERVA_ACTIVE)
    except Exception:
        return 16


def extended_vocab(anchors, glove, m: int = None):
    """SPEC_VOCAB_EXTEND (pure): the anchors (ids preserved) followed by their deduped top-m GloVe cosine neighbors —
    a thematically coherent concept cloud grown along the universal geometry. m defaults to the sparse-code width
    (reused, not authored). Returns the anchors unchanged if glove is empty. Content words only (alpha, len>=3)."""
    if m is None:
        m = _neighbors_per_anchor()
    vocab = list(anchors)
    seen = set(anchors)
    if not glove:
        return vocab
    import numpy as np
    words = [w for w in glove.keys() if w.isalpha() and len(w) >= 3]
    W = np.stack([glove[w] for w in words]).astype(np.float32)
    W = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-8)
    for a in anchors:
        av = glove.get(a)
        if av is None:
            continue
        av = np.asarray(av, dtype=np.float32); av = av / (np.linalg.norm(av) + 1e-8)
        added = 0
        for j in np.argsort(-(W @ av)):
            w = words[int(j)]
            if w in seen:
                continue
            vocab.append(w); seen.add(w); added += 1
            if added >= m:
                break
    return vocab


class TongueSystem:
    """SPEC_TONGUE — the shared masked-mind + per-colony comprehension. One head (TG1), per-colony meters (TG4), the
    shared learned embedding (TG2), the chat log/volleys (TG6), and the vocabulary curriculum (TG9) hang here as the
    arc is built out. Owned by the sim, constructed only when TONGUE_ENABLED (so the battery never touches torch).

    The comprehension meter is LEARNING PROGRESS (the rate the masked-prediction accuracy is improving), not raw
    accuracy — the noisy-TV correction: a colony plateaued in a stochastic region reads 'done learning', not
    'confused'. `awake(colony)` = high level AND plateaued progress (it has modeled its world).
    """

    def __init__(self, vocab: Optional[List[str]] = None, chat_stem: Optional[str] = None):
        if vocab is None:
            from hive_mind_monitor import ANCHOR_SEEDS
            vocab = list(ANCHOR_SEEDS)
            # SPEC_VOCAB_EXTEND: grow the represented vocabulary to the anchors' concept cloud when on (anchors keep
            # ids 0..41 so game supervision is unchanged). Off / no GloVe ⇒ the 42 anchors (byte-identical).
            if VOCAB_EXTEND_ENABLED:
                try:
                    # PRE-DERIVED path: the ensemble npz already stores the extended token list (built offline). Use
                    # it — avoids re-running the ~40k-word GloVe neighbor search every startup (the ~5s lag). Only
                    # derive from GloVe if there is no matching npz.
                    import ensemble_embed as _ee
                    b = _ee.load_ensemble()
                    if b is not None and list(b.tokens[:len(vocab)]) == list(vocab):
                        vocab = list(b.tokens)
                    else:
                        from codex import _load_glove
                        vocab = extended_vocab(vocab, _load_glove())
                except Exception:
                    pass
        # SPEC_FOL_TONGUE: append the 3 role markers so masked-SLOT training can name WHICH slot is hidden, and load
        # the offline-decoded triplet store. On ⇒ vocab grows by 3 + facts load; off / no npz ⇒ vocab unchanged
        # (byte-identical bag-of-words Tongue).
        self._fol_store = None
        self._fol_roles = None
        try:
            import fol_tongue as _fol
            if _fol.FOL_TONGUE_ENABLED:
                store = _fol.load_store()
                if store is not None:
                    base = len(vocab)
                    vocab = list(vocab) + list(_fol.FOL_ROLE_TOKENS)
                    self._fol_store = store
                    self._fol_roles = tuple(range(base, base + len(_fol.FOL_ROLE_TOKENS)))  # SUBJ,PRED,OBJ ids
        except Exception:
            self._fol_store = None
        self.vocab = vocab
        self._id = {w: i for i, w in enumerate(vocab)}
        self.head = MaskedMind(len(vocab)) if _HAVE_TORCH else None
        self.level: Dict[int, float] = {}     # per-colony masked-prediction accuracy EMA
        self.progress: Dict[int, float] = {}  # per-colony LEARNING PROGRESS (the TG4 meter)
        self._prev: Dict[int, float] = {}
        # TG2/TG3/TG6/TG8: lazily built (GloVe load / torch heads are expensive; only when first needed)
        self.space: Optional[TokenSpace] = None
        self.reader = None
        self.vision = None
        self.chat = ChatLog(chat_stem)
        self.volley_stats: Dict[int, VolleyStats] = {}
        self._step = 0
        self._last_active: Dict[int, List[str]] = {}   # TG8: per-colony recent world-tokens (for the centroid)

    # ---- SPEC_JLENS: read (and steer) a colony's unspoken thoughts via the masked-mind head ----
    def _standouts(self, logits):
        """The STATISTICAL-standout J-space tokens (name, weight) — weight above median + robust MAD-sigma, ranked,
        so a handful emerge naturally (no authored top-k). One gather + one .tolist() (no per-element tensor→float)."""
        import torch
        med = logits.median()
        cut = med + 1.4826 * (logits - med).abs().median()          # robust standout cut, distribution-derived
        order = (logits > cut).nonzero(as_tuple=True)[0]
        order = order[torch.argsort(logits[order], descending=True)]
        return list(zip((self.vocab[i] for i in order.tolist()), logits[order].tolist()))

    def _dark_mass(self, logits) -> float:
        """Softmax J-space mass on the dark/treachery tokens, in [0,1] — the betrayal-lean readout."""
        import torch
        dark = [self._id[w] for w in JLENS_DARK if w in self._id]
        return float(torch.softmax(logits, dim=0)[dark].sum()) if dark else 0.0

    def read_thoughts(self, encoding, k=None):
        """The J-space tokens (name, weight) a colony is positioned to say but isn't — its unspoken thoughts. With no
        k, the statistical standouts (`_standouts`); else the top-k. Pure inference (no RNG, no state). [] if no head."""
        if self.head is None:
            return []
        import torch
        logits = self.head.jlens(encoding)
        if k is None:
            return self._standouts(logits)
        order = torch.topk(logits, min(int(k), len(self.vocab)))[1]
        return list(zip((self.vocab[i] for i in order.tolist()), logits[order].tolist()))

    def inject_thought(self, encoding, token: str, strength=None):
        """The god-hand at the level of mind: steer an encoding toward `token` so the colony leans that way. Strength
        defaults to the encoding's own magnitude (identity-relative). No-op if the head is absent or token OOV."""
        if self.head is None or token not in self._id:
            return encoding
        return self.head.inject(encoding, self._id[token], strength)

    def lens(self, encoding):
        """SPEC_JLENS: thoughts AND treachery from ONE jlens forward (the demand-driven readout). Pure inference."""
        if self.head is None:
            return [], 0.0
        logits = self.head.jlens(encoding)
        return self._standouts(logits), self._dark_mass(logits)

    def treachery(self, encoding) -> float:
        """A betrayal-lean readout in [0,1] — a colony privately leaning toward the dark tokens before it acts."""
        return self._dark_mass(self.head.jlens(encoding)) if self.head is not None else 0.0

    # ---- TG2/TG3: the shared space + reading the library ----
    def _space(self) -> TokenSpace:
        if self.space is None:
            self.space = TokenSpace(self.vocab)
            try:
                from codex import _load_glove
                g = _load_glove()
                if g:
                    self.space.seed_glove({w: list(g[w]) for w in self.vocab if w in g})
            except Exception:
                pass
        return self.space

    def read_text(self, words, rng) -> Optional[float]:
        """TG3/TG9: read one WikiText passage (masked LM). Introduces at most TONGUE_NEW_PER_READ NEW words per read
        ("a few masked words at a time"), GloVe-seeding each into the shared space; keeps the reader's learned
        weights across vocab growth (dim is fixed, only rows are appended). Reads each sequence CHUNK, then the whole
        passage (chunk-then-aggregate). The corpus-ordering by fewest-unlearned lives in `curriculum_order`."""
        if not _HAVE_TORCH:
            return None
        import numpy as np
        words = _words(words)
        sp = self._space()
        new = [w for w in dict.fromkeys(words) if w not in sp._id][:TONGUE_NEW_PER_READ]
        if new:
            glove = None
            try:
                from codex import _load_glove
                glove = _load_glove()
            except Exception:
                pass
            rows = []
            for w in new:
                sp._id[w] = len(sp.vocab); sp.vocab.append(w)
                v = (glove or {}).get(w)
                if v is not None and len(v) == sp.dim:              # GloVe-seed the new word (else small random)
                    a = np.asarray(v, dtype="float32"); a = a / (float(np.linalg.norm(a)) or 1.0)
                else:
                    a = np.random.RandomState(len(sp.vocab)).normal(0, 0.1, sp.dim).astype("float32")
                rows.append(a)
            sp.E = np.vstack([sp.E, np.stack(rows)])
        if self.reader is None:
            self.reader = TextReader(sp)
        acc = None
        for chunk in chunk_sequences(words):                       # TG9: individual sequences first ...
            r = self.reader.read(chunk, rng)
            if r is not None:
                acc = r
        whole = self.reader.read(words, rng)                       # ... then the aggregate
        return whole if whole is not None else acc

    def transmit(self, sim) -> None:
        """SPEC_COMPREHENSION_RL I2 (reduced, shared-head form): tribal knowledge spreads as UNDERSTANDING across
        non-hostile diplomatic edges — a wiser colony teaches a greener neighbour, raising its comprehension toward
        its own by a fraction of the gap. The teach rate REUSES the comprehension-EMA smoothing (1 - COMPREHENSION_EMA),
        no new constant. Enemies exchange NOTHING (broken comms across a war footing — politics.hostile). Non-critical
        (wrapped). Full concept-level triplet transmission (distinct per-colony ontologies via observe_triplet) needs
        PER-COLONY heads — a future increment (I3/I4 prerequisite); with one shared head this understanding-diffusion
        is the faithful reduced form of 'technology communicated as words'."""
        try:
            from politics import hostile
        except Exception:
            return
        colonies = list(getattr(sim, 'colonies', []))
        rate = 1.0 - COMPREHENSION_EMA          # reuse the level-smoothing constant as the teach rate (no new magic)
        gains: Dict[int, float] = {}
        for a in colonies:
            ka = self.level.get(a.colony_id, 0.0)
            for b in colonies:
                if a is b:
                    continue
                try:
                    if hostile(sim, a.colony_id, b.colony_id):
                        continue                # enemies have broken-down communications
                except Exception:
                    continue
                kb = self.level.get(b.colony_id, 0.0)
                if ka > kb:                     # the wiser teaches the greener; the gap shrinks by `rate`
                    gains[b.colony_id] = max(gains.get(b.colony_id, 0.0), rate * (ka - kb))
        for cid, g in gains.items():
            self.level[cid] = self.level.get(cid, 0.0) + g

    # ---- TG5: the keeper's war-command (compliance-gated) ----
    def command_war(self, comprehension: float, loyalty: float, alignment: float) -> bool:
        return obeys(comprehension, loyalty, alignment)

    # ---- TG6: strobed volleys ----
    def volley_tick(self, sim) -> None:
        """Called each step (gated). On a volley boundary, append a chat-log entry per breached colony with its
        decoded reply, comprehension, and the FRED-style trend stats."""
        self._step += 1
        import sandkings as _sk
        if self._step % getattr(_sk, 'TONGUE_VOLLEY', 200) != 0:
            return
        if getattr(_sk, 'COMPREHENSION_RL_ENABLED', False):
            self.transmit(sim)          # SPEC_COMPREHENSION_RL I2: spread understanding along non-hostile edges
        lo = self._step - getattr(_sk, 'TONGUE_VOLLEY', 200)
        frame_arr = frame_array(sim) if _HAVE_TORCH else None       # TG7 (shared across colonies this volley)
        frame_b64 = strobe_frame_b64(sim)
        for colony in getattr(sim, 'colonies', []):
            if not getattr(colony, 'breached', False):
                continue
            cid = colony.colony_id
            comp = self.comprehension(cid)
            vs = self.volley_stats.setdefault(cid, VolleyStats())
            stats = vs.push(comp)
            if frame_arr is not None:                               # TG8: align the vision encoder toward this
                self._align_vision(cid, frame_arr)                  #      colony's world-token centroid
            reply = ""
            try:
                from hive_mind_monitor import compose_utterance
                if colony.units:
                    reply = compose_utterance(colony.units[0], colony, sim)
            except Exception:
                pass
            self.chat.append({
                "step_range": f"{lo}-{self._step}", "house": getattr(colony, 'house', str(cid)),
                "colony": cid, "comprehension": round(comp, 3),
                "learning_progress": round(self.learning_progress(cid), 4),
                "reply": reply, "keeper_said": "", "stats": stats, "frame_png_b64": frame_b64,
            })

    # ---- TG8: vision (CNN into the shared space) + self-recognition ----
    def _centroid(self, colony_id: int):
        """The colony's world-token centroid in the shared space (mean of its recent active tokens' vectors)."""
        import numpy as np
        words = self._last_active.get(colony_id) or []
        sp = self._space()
        vecs = [sp.E[sp._id[w]] for w in words if w in sp._id]
        if not vecs:
            return np.zeros(sp.dim, dtype="float32")
        return np.mean(vecs, axis=0).astype("float32")

    def _align_vision(self, colony_id: int, frame_arr) -> None:
        if not _HAVE_TORCH:
            return
        try:
            if self.vision is None:
                self.vision = VisionEncoder(self._space().dim)
            self.vision.align(frame_arr, self._centroid(colony_id))
        except Exception:
            pass

    def recognize_map(self, sim, colony_id: int) -> float:
        """TG8 self-recognition: how strongly does the colony recognize a rendered map of its world? cosine of the
        image embedding to its world-token centroid, in [-1,1]. The measurable 'it saw a picture of its cage.'"""
        if not _HAVE_TORCH or self.vision is None:
            return 0.0
        try:
            return self.vision.recognizes(frame_array(sim), self._centroid(colony_id))
        except Exception:
            return 0.0

    def ids(self, words) -> List[int]:
        return [self._id[w] for w in words if w in self._id]

    def observe(self, colony_id: int, hidden, active_words, reach: int = READ_REACH_DEFAULT) -> Optional[float]:
        """One masked step for a colony: mask+predict its active world-tokens, update the comprehension meters.
        Returns this step's recovery accuracy (or None). Gate/torch checked by the caller."""
        if self.head is None:
            return None
        import random as _r
        self._last_active[colony_id] = list(active_words)          # TG8: remember for the recognition centroid
        acc = self.head.observe(hidden, self.ids(active_words), _r.Random(), reach=reach)
        if acc is None:
            return None
        lvl = COMPREHENSION_EMA * self.level.get(colony_id, acc) + (1 - COMPREHENSION_EMA) * acc
        delta = lvl - self.level.get(colony_id, lvl)                  # change in level = raw learning progress
        self.level[colony_id] = lvl
        self.progress[colony_id] = LP_EMA * self.progress.get(colony_id, 0.0) + (1 - LP_EMA) * delta
        if self._fol_store is not None:                              # SPEC_FOL_TONGUE: also ground THIS encoding
            self._train_fol(hidden, _r.Random())                     #   against decoded relational facts (gated)
        return acc

    def _train_fol(self, hidden, rng) -> None:
        """SPEC_FOL_TONGUE: train the colony's encoding on a small sample of decoded corpus triplets (the 'library of
        facts'), masking one role slot per triplet. K = TONGUE_NEW_PER_READ (reused — 'a few at a time'). Only reached
        when FOL_TONGUE_ENABLED loaded a store; gate off ⇒ never called (byte-identical)."""
        store, roles = self._fol_store, self._fol_roles
        n = len(store.rows)
        if n == 0 or self.head is None:
            return
        for _ in range(min(TONGUE_NEW_PER_READ, n)):
            r = store.rows[rng.randrange(n)]
            slots = [(roles[k], int(r[k])) for k in range(3) if int(r[k]) >= 0]   # SUBJ/PRED/OBJ, skip -1
            if len(slots) >= 2:
                self.head.observe_triplet(hidden, slots, rng)

    def fol_utterance(self, colony_id: int, hidden) -> str:
        """SPEC_FOL_TONGUE: the colony's FOL-shaped reply — the decoded fact its mind is most positioned to 'say'
        right now. Scores stored triplets by the J-lens activation of their predicate slot (the head's Jacobian on
        the hidden), renders the top one as `predicate(subject, object) [observed|inferred]`. '' if unavailable."""
        import fol_tongue as _fol
        store = self._fol_store
        if store is None or self.head is None or len(store.rows) == 0:
            return ""
        try:
            logits = self.head.jlens(hidden)                          # per-vocab pull the encoding exerts
            preds = store.rows[:, 1]
            pidx = torch.as_tensor(preds, dtype=torch.long)
            best = int(preds[int(logits[pidx].argmax())]) if len(preds) else -1
            cand = [i for i in range(len(store.rows)) if int(store.rows[i, 1]) == best] or [0]
            i = cand[0]
            return _fol.format_triplet(self.vocab, store.rows[i], float(store.conf[i]))
        except Exception:
            return ""

    def comprehension(self, colony_id: int) -> float:
        """The comprehension LEVEL (masked-prediction accuracy EMA) in [0,1]."""
        return float(self.level.get(colony_id, 0.0))

    def learning_progress(self, colony_id: int) -> float:
        """The TG4 meter: rate the colony's world-model is still improving (reducible uncertainty)."""
        return float(self.progress.get(colony_id, 0.0))

    def awake(self, colony_id: int, level_min: float = 0.8, plateau: float = 0.002) -> bool:
        """TG4 awakening signal: has modeled its world — high comprehension AND learning has plateaued (it has
        squeezed out the reducible uncertainty), not merely stuck at high error in a noisy region."""
        return self.comprehension(colony_id) >= level_min and abs(self.learning_progress(colony_id)) < plateau


# ---------------------------------------------------------------------------------------------------------------
# TG2 — the GloVe-seeded, LEARNED shared token space (corpus correction: seed, don't freeze). Used for kNN decode
# (Kumar & Tsvetkov 2019) and as the bridge world-tokens ↔ text-tokens ↔ image (TG3/TG8).
# ---------------------------------------------------------------------------------------------------------------
import math

GLOVE_DIM = 50


class TokenSpace:
    """A shared embedding over the vocabulary, GloVe-seeded then learned. Pure numpy so it loads/tests without torch;
    the learned drift is applied by whatever head owns it. `nearest` is the kNN decode."""

    def __init__(self, vocab: List[str], dim: int = GLOVE_DIM):
        import numpy as np
        self.vocab = list(vocab)
        self._id = {w: i for i, w in enumerate(self.vocab)}
        self.dim = dim
        rng = np.random.RandomState(0)
        self.E = rng.normal(0, 0.1, (len(self.vocab), dim)).astype("float32")   # random init; seed_glove overwrites

    def seed_glove(self, glove: Dict[str, "list"]) -> int:
        """Overwrite rows for in-GloVe vocab words with their (L2-normalized) GloVe vectors. Returns #seeded.
        (TG2 corpus correction: this is a SEED — the owning head is free to keep learning E.)"""
        import numpy as np
        n = 0
        for w, i in self._id.items():
            v = glove.get(w)
            if v is not None and len(v) == self.dim:
                a = np.asarray(v, dtype="float32")
                nrm = float(np.linalg.norm(a)) or 1.0
                self.E[i] = a / nrm
                n += 1
        return n

    def vec(self, word: str):
        i = self._id.get(word)
        return None if i is None else self.E[i]

    def nearest(self, vec, k: int = 1):
        """kNN decode: the k nearest vocab words to `vec` by cosine (the continuous-output decode step)."""
        import numpy as np
        a = np.asarray(vec, dtype="float32")
        na = float(np.linalg.norm(a)) or 1.0
        sims = (self.E @ a) / (np.linalg.norm(self.E, axis=1) * na + 1e-9)
        order = np.argsort(-sims)[:k]
        return [self.vocab[i] for i in order]


# ---------------------------------------------------------------------------------------------------------------
# TG5 — the compliance gate: obey = comprehension × loyalty × alignment. A command is never guaranteed.
# ---------------------------------------------------------------------------------------------------------------

TONGUE_OBEY_MIN = 0.25        # obey iff comprehension×loyalty×alignment exceeds this


def compliance(comprehension: float, loyalty: float, alignment: float) -> float:
    """SPEC_TONGUE TG5: the probability-like compliance score. A breached, resentful (low-loyalty) or
    self-endangering (low-alignment) house scores low even if it understands you perfectly."""
    return max(0.0, float(comprehension)) * max(0.0, float(loyalty)) * max(0.0, float(alignment))


def obeys(comprehension: float, loyalty: float, alignment: float, threshold: float = TONGUE_OBEY_MIN) -> bool:
    return compliance(comprehension, loyalty, alignment) >= threshold


# ---------------------------------------------------------------------------------------------------------------
# TG6 — strobed volleys + FRED-style stats (Tukey quantile MAs, mean/sdev, MACD directional change).
# ---------------------------------------------------------------------------------------------------------------


class VolleyStats:
    """SPEC_TONGUE TG6: over a rolling window of per-volley scalars, report the Tukey quantile moving averages
    (median + quartile band), mean, sdev, and a MACD-style directional-change signal (fast vs slow median cross)."""

    def __init__(self, window: int = 12, fast: int = 3, slow: int = 9):
        from collections import deque
        self.window, self.fast, self.slow = window, fast, slow
        self.series = deque(maxlen=max(window, slow))
        self._last_dir = 0

    def push(self, value: float) -> Dict:
        import numpy as np
        self.series.append(float(value))
        arr = np.asarray(self.series, dtype="float64")
        w = arr[-self.window:]
        q = np.quantile(w, [0.0, 0.25, 0.5, 0.75, 1.0]).tolist()   # Tukey five-number summary
        fast_med = float(np.median(arr[-self.fast:]))
        slow_med = float(np.median(arr[-self.slow:]))
        diff = fast_med - slow_med
        direction = 1 if diff > 1e-9 else (-1 if diff < -1e-9 else 0)   # expansion / contraction / plateau
        crossed = direction != 0 and direction != self._last_dir and self._last_dir != 0
        if direction != 0:
            self._last_dir = direction
        return {
            "quantiles": {"min": q[0], "q1": q[1], "median": q[2], "q3": q[3], "max": q[4]},
            "mean": float(w.mean()), "sdev": float(w.std()),
            "fast_median": fast_med, "slow_median": slow_med,
            "direction": ("expansion" if direction > 0 else "contraction" if direction < 0 else "plateau"),
            "crossed": bool(crossed),
        }


class ChatLog:
    """SPEC_TONGUE TG6: append per-volley keeper⇄colony exchanges to <run>.chat.md + a .jsonl sibling (gitignored
    runtime output). One volley = one strobe frame of the relationship."""

    def __init__(self, path_stem: Optional[str] = None):
        self.path_stem = path_stem
        self.entries: List[Dict] = []

    def append(self, entry: Dict) -> None:
        import json
        self.entries.append(entry)
        if not self.path_stem:
            return
        try:
            with open(self.path_stem + ".jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            with open(self.path_stem + ".chat.md", "a", encoding="utf-8") as f:
                house = entry.get("house", "?")
                said = entry.get("keeper_said", "")
                rep = entry.get("reply", "")
                d = entry.get("stats", {}).get("direction", "")
                f.write(f"- **{house}** (step {entry.get('step_range','')}, trust {d}) — "
                        f"keeper: `{said}` · house: \"{rep}\"\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------------------------------------------
# TG9 — the vocabulary curriculum: expand where LEARNING PROGRESS is highest (not least-residual, not max-error).
# ---------------------------------------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------------------------------------
# TG7 — the strobe frame: a small PIL snapshot with the SUBSURFACE revealed (translucent rock + tunnel highlight),
# entities in house colors. PIL-based (portable; no pygame) so it runs headless and in the container alike.
# ---------------------------------------------------------------------------------------------------------------

_FRAME_PAL = {
    1: (194, 178, 128), 2: (95, 95, 105), 3: (170, 195, 205), 4: (90, 200, 90), 5: (150, 90, 90),
    6: (90, 80, 70), 7: (120, 90, 60), 8: (80, 160, 70), 9: (200, 190, 70), 14: (110, 80, 50),
    15: (140, 100, 60), 17: (150, 150, 160), 18: (60, 110, 200), 21: (170, 140, 90),
}   # voxel value -> color (AIR=0 handled separately); see VoxelType


def frame_array(sim):
    """(H, W, 3) uint8 top-down snapshot with subsurface reveal: topmost non-air voxel colored; a column with an
    AIR pocket UNDER the surface (a tunnel) is lightened so the burrows read through the 'translucent rock';
    units/maws overdrawn in house colors."""
    import numpy as np
    vox = sim.world.voxels
    w, h, d = vox.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        col = vox[x]
        for y in range(h):
            cz = col[y]
            top = None
            for z in range(d - 1, -1, -1):
                if cz[z] != 0:
                    top = int(cz[z]); ts = z; break
            if top is None:
                img[y, x] = (12, 12, 16); continue
            base = _FRAME_PAL.get(top, (60, 60, 66))
            if any(cz[z] == 0 for z in range(0, ts)):        # AIR below the surface = a tunnel -> translucent reveal
                base = tuple(min(255, c + 40) for c in base)
            img[y, x] = base
    for colony in getattr(sim, 'colonies', []):
        color = tuple(int(c) for c in getattr(colony, 'color', (255, 255, 255)))[:3]
        for u in getattr(colony, 'units', []):
            ux, uy = u.position[0], u.position[1]
            if 0 <= uy < h and 0 <= ux < w:
                img[uy, ux] = color
        if getattr(colony, 'is_alive', lambda: False)() and getattr(colony, 'maw', None):
            mx, my = colony.maw.position[0], colony.maw.position[1]
            if 0 <= my < h and 0 <= mx < w:
                img[my, mx] = (255, 255, 0)
    return img


def strobe_frame_b64(sim, scale: int = 4) -> Optional[str]:
    """The TG7 frame as a base64 PNG for the volley JSONL. None on any failure (non-critical)."""
    try:
        import base64
        import io
        from PIL import Image
        arr = frame_array(sim)
        im = Image.fromarray(arr, "RGB").resize((arr.shape[1] * scale, arr.shape[0] * scale), Image.NEAREST)
        buf = io.BytesIO(); im.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def next_to_learn(progress: Dict[str, float]) -> Optional[str]:
    """SPEC_TONGUE TG9: the token to read into next = the one with maximal LEARNING PROGRESS (rate of error
    reduction). NOT least-residual (self-paced — traps on mastered) and NOT max-error (uncertainty — noisy-TV trap).
    Returns None if nothing is still improving."""
    live = {w: lp for w, lp in progress.items() if lp > 1e-6}
    if not live:
        return None
    return max(live.items(), key=lambda kv: kv[1])[0]


TONGUE_NEW_PER_READ = 3       # TG9: introduce at most this many NEW words per read — "a few masked words at a time"


def _words(text) -> List[str]:
    """Lowercased word tokens (letters only) from a string or an already-split list."""
    import re
    if isinstance(text, str):
        return re.findall(r"[a-z]+", text.lower())
    return [str(w).lower() for w in text]


def curriculum_order(texts: List, known_words) -> List:
    """SPEC_TONGUE TG9 — comprehensible input (Krashen i+1): read the texts with the FEWEST unlearned words first. A
    mostly-known text lets the reader infer its few new words from context; a text full of unknowns is unlearnable
    (nothing to anchor them to). This is the cheap, correct difficulty signal for READING (distinct from the
    learning-progress token curriculum). Stable sort keeps ties in input order."""
    known = set(known_words)
    return sorted(texts, key=lambda t: sum(1 for w in set(_words(t)) if w not in known))


def chunk_sequences(words: List[str], size: int = 12) -> List[List[str]]:
    """TG9: split a passage into individual sequences (chunks) — read each on its own, then the aggregate."""
    return [words[i:i + size] for i in range(0, len(words), size)] or [words]


if _HAVE_TORCH:
    class TextReader(nn.Module):
        """SPEC_TONGUE TG3 — masked LANGUAGE modeling over WikiText via the shared TokenSpace. Predict a masked
        word's EMBEDDING from its context (Kumar & Tsvetkov 2019 continuous-output / cosine regression) and
        kNN-decode. Because it reads and writes the SAME space as the world-tokens (TG2), world-grounding transfers
        to reading (GVF / auxiliary-task shared bottleneck)."""

        def __init__(self, space: TokenSpace):
            super().__init__()
            self.space = space
            self.W = nn.Linear(space.dim, space.dim)
            self.opt = torch.optim.SGD(self.parameters(), lr=0.05)
            self.acc = 0.5

        def _predict(self, ctx_ids):
            ctx = torch.tensor(self.space.E[ctx_ids], dtype=torch.float32).mean(0)
            return self.W(ctx)

        def read(self, words, rng) -> Optional[float]:
            ids = [self.space._id[w] for w in words if w in self.space._id]
            if len(ids) < 2:
                return None
            pos = rng.randrange(len(ids))
            masked_id = ids[pos]
            ctx_ids = [i for j, i in enumerate(ids) if j != pos] or [ids[(pos + 1) % len(ids)]]
            pred = self._predict(ctx_ids)
            target = torch.tensor(self.space.E[masked_id], dtype=torch.float32)
            loss = 1.0 - F.cosine_similarity(pred, target, dim=0)
            self.opt.zero_grad(); loss.backward(); self.opt.step()
            with torch.no_grad():
                nn_word = self.space.nearest(self._predict(ctx_ids).numpy())[0]
            hit = 1.0 if self.space._id.get(nn_word) == masked_id else 0.0
            self.acc = 0.99 * self.acc + 0.01 * hit
            return hit

    class VisionEncoder(nn.Module):
        """SPEC_TONGUE TG8 — a small CNN mapping a rendered frame (3,H,W) into the shared TokenSpace. Aligned so a
        frame of a colony's OWN world embeds near that colony's world-token centroid — self-recognition: cosine of
        the image embedding to the live world-token vector is the measurable "it saw a picture of its cage."
        Trained on the game's OWN renders (WikiText has no images)."""

        def __init__(self, dim: int = GLOVE_DIM):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv2d(3, 8, 3, 2, 1), nn.ReLU(),
                nn.Conv2d(8, 16, 3, 2, 1), nn.ReLU(),
                nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(16, dim))
            self.opt = torch.optim.SGD(self.parameters(), lr=0.02)

        def encode(self, img):
            x = torch.as_tensor(img, dtype=torch.float32)
            if x.dim() == 3 and x.shape[-1] == 3:
                x = x.permute(2, 0, 1)                     # HWC -> CHW
            return self.net(x.unsqueeze(0)).squeeze(0)

        def align(self, img, target_vec) -> float:
            """One step aligning the image embedding toward a target (the colony's world-token centroid)."""
            t = torch.as_tensor(target_vec, dtype=torch.float32)
            e = self.encode(img)
            loss = 1.0 - F.cosine_similarity(e, t, dim=0)
            self.opt.zero_grad(); loss.backward(); self.opt.step()
            return float(loss.detach())

        def recognizes(self, img, target_vec) -> float:
            """Self-recognition score: cosine(image embedding, target world-token vector) in [-1,1]."""
            with torch.no_grad():
                e = self.encode(img)
                t = torch.as_tensor(target_vec, dtype=torch.float32)
                return float(F.cosine_similarity(e, t, dim=0))
