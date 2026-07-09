"""Build thought_vocabulary.json: embedding-derived word clusters per anchor.

Build-time tool (SPEC_HIVE_MONITOR.md M9) — run manually, once:
    python thought_vocabulary.py

Downloads GloVe wiki-gigaword-50 (~66MB, cached beside this file), takes
the first 10,000 frequency-ordered entries as the vocabulary, and for each
anchor seed word selects up to 5 nearest in-vocabulary neighbors by cosine
similarity (>= 0.5), each candidate assigned only to its closest anchor.
Clusters are written mild -> seed (ascending similarity, seed last) so the
runtime can scale word choice with decoded probability.

Preconditions: numpy; network for the first run (falls back to the
embedded curated table without it, and says so). Failure modes: a partial
download is discarded; unknown seed words raise.
"""

import gzip
import json
import os
import sys
import urllib.request

import numpy as np

GLOVE_URL = ("https://github.com/piskvorky/gensim-data/releases/download/"
             "glove-wiki-gigaword-50/glove-wiki-gigaword-50.gz")
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "glove-wiki-gigaword-50.gz")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "thought_vocabulary.json")
VOCAB_SIZE = 10_000   # "top 10k words": GloVe entries are frequency-ordered
NEIGHBORS_PER_ANCHOR = 5
MIN_SIMILARITY = 0.5

# The 20 anchor seed words (SPEC M1). Order matters only for display.
ANCHOR_SEEDS = [
    "food", "hunger", "war", "defense", "underground", "danger", "flee",
    "hunt", "wounded", "home", "feast", "buried", "crowd", "alone", "rich",
    "storm", "death", "enemy", "victory", "siege", "jealousy", "love",
    "clueless",
]

# Manual pruning: embedding neighbors that read wrong for the game
# (reviewed against the actual top-10k build; SPEC M9 blocklist).
BLOCKLIST = {
    "food": {"coffee", "products", "supplies", "items", "goods", "supply",
             "medicines"},
    "hunger": {"aids", "prolonged", "violence"},   # disease name, filler
    "war": {"iraq", "wars", "invasion"},
    "defense": {"administration", "intelligence", "defence"},
    "underground": {"site", "sites", "connected", "tunnels", "tracks",
                    "operated"},
    "danger": {"consequences", "cause"},
    "flee": {"thousands", "forcing"},
    "wounded": {"civilians", "policemen"},
    "home": {"house", "homes", "back", "came", "where", "went", "leaving"},
    "death": {"deaths", "brought", "father"},
    "storm": {"storms"},
    "enemy": {"enemies", "terrorists"},
    "victory": {"victories", "defeat", "clinched"},  # 'defeat' is the opposite
    "feast": {"feasts", "easter"},
    "crowd": {"crowds", "watched", "greeted"},
    "alone": {"still", "than", "now", "just", "actually"},
    "rich": {"particularly", "especially"},
    "jealousy": {"guilt", "emotions", "feelings"},
    "love": {"me", "loves", "my"},
}
# Words too generic/odd to ever use, regardless of anchor
GLOBAL_BLOCK = {"the", "of", "and", "a", "to", "in", "is", "it", "he",
                "she", "mr", "mrs", "said", "says", "also", "u.s.", "un"}

# Anchors whose embedding neighborhoods are function-word swamps: the
# blocklist just backfills more junk, so these use curated clusters
# (still mild -> seed). SPEC M9 manual-pruning mechanism.
CURATED_OVERRIDE = {
    "home": ["nest", "hearth", "haven", "home"],
    "alone": ["lost", "isolated", "lonely", "alone"],
    "defense": ["guard", "protect", "shield", "defense"],
}

# Curated fallback (used only if the download fails; SPEC M9)
FALLBACK = {
    "food": ["meal", "eat", "hungry", "gather", "food"],
    "hunger": ["appetite", "starving", "famine", "hunger"],
    "war": ["conflict", "battle", "fight", "war"],
    "defense": ["guard", "protect", "shield", "defense"],
    "underground": ["below", "tunnel", "deep", "underground"],
    "danger": ["threat", "risk", "peril", "danger"],
    "flee": ["retreat", "escape", "run", "flee"],
    "hunt": ["chase", "stalk", "prey", "hunt"],
    "wounded": ["hurt", "bleeding", "pain", "wounded"],
    "home": ["nest", "hearth", "haven", "home"],
    "feast": ["carrion", "bounty", "banquet", "feast"],
    "buried": ["entombed", "covered", "sunken", "buried"],
    "crowd": ["swarm", "throng", "mass", "crowd"],
    "alone": ["lost", "isolated", "lonely", "alone"],
    "rich": ["wealthy", "abundant", "prosperous", "rich"],
    "storm": ["wind", "tempest", "gale", "storm"],
    "death": ["doom", "dying", "grave", "death"],
    "enemy": ["foe", "rival", "hostile", "enemy"],
    "victory": ["triumph", "win", "glory", "victory"],
    "siege": ["assault", "blockade", "onslaught", "siege"],
    "jealousy": ["envy", "resentment", "covet", "jealousy"],
    "love": ["care", "devotion", "tenderness", "love"],
    "clueless": ["oblivious", "unaware", "naive", "clueless"],
}


def download_vectors() -> str:
    """Fetch (or reuse) the GloVe archive; returns the local path."""
    if os.path.exists(CACHE_PATH):
        print(f"[cache] using {CACHE_PATH}")
        return CACHE_PATH
    print(f"[download] {GLOVE_URL} (~66MB, one time)...")
    tmp = CACHE_PATH + ".part"
    urllib.request.urlretrieve(GLOVE_URL, tmp)
    os.replace(tmp, CACHE_PATH)
    print(f"[download] saved to {CACHE_PATH}")
    return CACHE_PATH


def load_top_vocab(path: str, size: int = VOCAB_SIZE):
    """First `size` frequency-ordered entries, plus vectors for any anchor
    seeds that live deeper in the vocabulary (neighbor CANDIDATES must be
    top-`size`; seeds themselves may be rarer words like 'feast')."""
    words, vectors = [], []
    seed_vecs = {}
    pending_seeds = set(ANCHOR_SEEDS)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip().split(" ")
            if len(parts) < 10:
                continue
            word = parts[0]
            if len(words) < size:
                words.append(word)
                vectors.append(np.asarray(parts[1:], dtype=np.float32))
            if word in pending_seeds:
                seed_vecs[word] = np.asarray(parts[1:], dtype=np.float32)
                pending_seeds.discard(word)
            if len(words) >= size and not pending_seeds:
                break
    if pending_seeds:
        raise KeyError(f"anchor seeds missing from the model: {sorted(pending_seeds)}")
    matrix = np.vstack(vectors)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    seeds = np.vstack([seed_vecs[s] for s in ANCHOR_SEEDS])
    seeds /= np.linalg.norm(seeds, axis=1, keepdims=True) + 1e-9
    return words, matrix, seeds


def build_clusters(words, matrix, seed_vecs):
    """M9: exclusive nearest-neighbor clusters per anchor, mild -> seed."""
    sims = matrix @ seed_vecs.T                                  # (V, 20)

    # each candidate word belongs only to its closest anchor
    owner = np.argmax(sims, axis=1)
    clusters = {}
    for a, seed in enumerate(ANCHOR_SEEDS):
        if seed in CURATED_OVERRIDE:
            clusters[seed] = list(CURATED_OVERRIDE[seed])
            continue
        blocked = BLOCKLIST.get(seed, set()) | GLOBAL_BLOCK | set(ANCHOR_SEEDS)
        candidates = [
            (float(sims[i, a]), words[i]) for i in range(len(words))
            if owner[i] == a and words[i] != seed
            and words[i] not in blocked and words[i].isalpha()
            and sims[i, a] >= MIN_SIMILARITY
        ]
        candidates.sort(reverse=True)
        picked = [w for _, w in candidates[:NEIGHBORS_PER_ANCHOR]]
        picked.reverse()                       # mild (weakest) first ...
        clusters[seed] = picked + [seed]       # ... seed word last (strongest)
    return clusters


def main() -> None:
    try:
        path = download_vectors()
        words, matrix, seed_vecs = load_top_vocab(path)
        clusters = build_clusters(words, matrix, seed_vecs)
        source = f"glove-wiki-gigaword-50 top {VOCAB_SIZE}"
    except Exception as error:  # network/parse failure: curated fallback
        print(f"[fallback] embedding build failed ({error}); "
              "writing curated table instead")
        clusters, source = dict(FALLBACK), "curated fallback"

    payload = {"source": source, "clusters": clusters}
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print(f"[ok] wrote {OUT_PATH} ({source})")
    for anchor, cluster in clusters.items():
        print(f"  {anchor:>12}: {' '.join(cluster)}")


if __name__ == "__main__":
    main()
