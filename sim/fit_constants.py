"""Fit Constants — a learned demonstrator for the four semi-permeable knobs.

Searches SUN_JITTER_SD, SUN_OSC_AMP, CAPTURE_TEMP, BARGAIN_TEMP against a
healthy-ecology objective (liveness, mode diversity, weather variance).
Reports fitted-vs-inert, does NOT edit sandkings.py.

FC1–FC12: full spec in SPEC_FIT_CONSTANTS.md.
"""

import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')  # headless BEFORE importing sandkings

import random
import math
import hashlib
import sqlite3

import numpy as np
import sandkings as sk

# --- Constants (FC2, FC3, FC11) ---

BOUNDS = {
    'SUN_JITTER_SD': (0.0, 3.0),   # daylight-hours noise SD
    'SUN_OSC_AMP':   (0.0, 6.0),   # daylight-hours swing amplitude
    'CAPTURE_TEMP':  (0.0, 0.4),   # metric power_ratio in [0,1] -> SMALL temp
    'BARGAIN_TEMP':  (0.0, 5.0),   # metric EV differences, larger scale
}

KNOB_ORDER = ('SUN_JITTER_SD', 'SUN_OSC_AMP', 'CAPTURE_TEMP', 'BARGAIN_TEMP')
BASELINE_VECTOR = (0.0, 0.0, 0.0, 0.0)

# Weights (must sum to 1.0)
W_LIVE = 1.0 / 3.0
W_DIV  = 1.0 / 3.0
W_VAR  = 1.0 / 3.0

# Reference variance for weather squashing
WEATHER_VAR_REF = 1.0

# Proposal RNG seed (SEPARATE from episode-seeding)
SEARCH_SEED = 12345

# Invocation defaults
N_ITERS = 8      # search proposals per run
N_SEEDS = 3      # distinct seeded episodes per candidate
STEPS   = 800    # sim steps per episode
SAMPLE  = 50     # telemetry sampling cadence
DB_PATH = 'fit_constants.db'

# The four feasible bargain modes
FEASIBLE_MODES = (
    sk.BARGAIN_MODE_NONE,
    sk.BARGAIN_MODE_WAGE,
    sk.BARGAIN_MODE_SUBJUGATE,
    sk.BARGAIN_MODE_ANNIHILATE
)

# Globals that must be saved/restored (FC7.4)
_GUARDED_GLOBALS = (
    'SUN_JITTER_SD', 'SUN_OSC_AMP', 'CAPTURE_TEMP', 'BARGAIN_TEMP',
    'BARGAIN_ENABLED', 'WAGE_ENABLED', 'CAPTURE_CHANCE'
)

# Module-level run counter (incremented only on checkpoint MISS)
_EPISODE_RUNS = 0


# --- Objective Functions (FC4.1–FC4.2) ---

def objective_components(alive_frac, mode_counts, sun_series):
    """Pure function: compute (liveness, diversity, variance) from telemetry.

    Args:
        alive_frac: fraction of colonies alive (already in [0,1])
        mode_counts: dict {mode_str: count}, counts >= 0
        sun_series: list of floats (sun_effective samples)

    Returns:
        (liveness, diversity, variance) each in [0,1]

    Guarantee (FC4.1):
        - liveness = alive_frac (pass-through)
        - diversity = normalized Shannon entropy over the 4 feasible modes
          - monoculture (all one mode) -> 0.0
          - uniform distribution -> 1.0
          - empty/zero total -> 0.0
        - variance = v / (v + WEATHER_VAR_REF) where v = np.var(sun_series)
          - constant series -> 0.0
          - empty series -> 0.0
    """
    liveness = float(alive_frac)

    # MODE_DIVERSITY: normalized Shannon entropy
    total = sum(mode_counts.values())
    if total <= 0:
        diversity = 0.0
    else:
        # H = -Σ (c/total) * ln(c/total) for c > 0
        h = 0.0
        for count in mode_counts.values():
            if count > 0:
                p = count / total
                h -= p * math.log(p)
        # Normalize by ln(4)
        diversity = h / math.log(4.0)

    # WEATHER_VARIANCE: population variance squashed to [0,1]
    if len(sun_series) < 2:
        variance = 0.0
    else:
        v = float(np.var(sun_series, ddof=0))  # population variance
        variance = v / (v + WEATHER_VAR_REF)

    return liveness, diversity, variance


def objective_scalar(liveness, diversity, variance):
    """Pure function: weighted sum of three components.

    Args:
        liveness, diversity, variance: each in [0,1]

    Returns:
        OBJECTIVE = W_LIVE*liveness + W_DIV*diversity + W_VAR*variance, in [0,1]
    """
    return W_LIVE * liveness + W_DIV * diversity + W_VAR * variance


# --- Episode Evaluation (FC4.3–FC4.5) ---

def run_episode(vector, seed, steps=None, sample=None):
    """Run ONE fresh seeded headless episode; return (alive_frac, mode_counts, sun_series).

    Args:
        vector: 4-tuple (SUN_JITTER_SD, SUN_OSC_AMP, CAPTURE_TEMP, BARGAIN_TEMP)
        seed: int, RNG seed
        steps: number of simulation steps (default STEPS=800)
        sample: sampling cadence (default SAMPLE=50)

    Returns:
        (alive_frac, mode_counts, sun_series) where:
        - alive_frac: fraction of alive colonies in [0,1]
        - mode_counts: dict {mode_str: count}
        - sun_series: list of sun_effective floats (sampled)

    Precondition:
        - vector ordered per KNOB_ORDER
        - caller restores globals afterward (FC7.4)

    Guarantee (FC4.3):
        - seeds module random and np.random
        - enables arc (BARGAIN_ENABLED, WAGE_ENABLED, CAPTURE_CHANCE > 0)
        - sets four knobs from vector
        - constructs sim at 80x48x16/4 colonies with bargain_enabled=True, keeper_auto=True
        - steps `steps` times, sampling every `sample` steps
        - deterministic given (vector, seed)
    """
    # Resolve budgets at CALL time (not def time) so a module-global override
    # (fit_constants.STEPS = ...) propagates through the whole eval/search chain
    # -- this is what lets the cheap FC tests run without threading steps through
    # every caller.
    if steps is None:
        steps = STEPS
    if sample is None:
        sample = SAMPLE
    # (1) SEED both module streams FIRST (playtest_economy.py pattern)
    random.seed(seed)
    np.random.seed(seed)

    # (2) SAVE the guarded globals so THIS episode self-restores them. run_episode
    # mutates sandkings module globals; EVERY entry point (direct test calls,
    # evaluate_candidate, run_search) must be leak-safe on its own rather than rely
    # on an outer fit() finally -- otherwise the last vector leaks into any later
    # code in the same process (e.g. sibling suites in the single-process battery).
    _saved = _save_globals(sk)
    try:
        # ENABLE the arc exactly like playtest_economy.py
        sk.BARGAIN_ENABLED = True
        sk.WAGE_ENABLED = True
        sk.CAPTURE_CHANCE = sk.BARGAIN_CAPTURE_CHANCE  # > 0 so CAPTURE_TEMP has effect (HS3)

        # (3) SET the four searched knobs from the candidate vector
        sk.SUN_JITTER_SD = float(vector[0])
        sk.SUN_OSC_AMP   = float(vector[1])
        sk.CAPTURE_TEMP  = float(vector[2])
        sk.BARGAIN_TEMP  = float(vector[3])

        # (4) CONSTRUCT the sim AFTER globals are set
        sim = sk.SandKingsSimulation(width=80, height=48, depth=16, num_colonies=4)
        sim.bargain_enabled = True
        sim.keeper_auto = True

        # (5) STEP, sampling telemetry every `sample` steps
        mode_counts = {m: 0 for m in FEASIBLE_MODES}
        sun_series = []
        for step in range(steps):
            sim.step()
            if step % sample == 0:
                for m in sim._bargain_modes().values():
                    mode_counts[m] = mode_counts.get(m, 0) + 1
                sun_series.append(float(getattr(sim, 'sun_effective', sk.SUN_HOURS_DEFAULT)))

        # (6) FINAL liveness
        total_colonies = len(sim.colonies)
        alive = len([c for c in sim.colonies if c.is_alive()])
        alive_frac = (alive / total_colonies) if total_colonies > 0 else 0.0

        return alive_frac, mode_counts, sun_series
    finally:
        # restore the guarded globals no matter what -- leak-safe per episode
        _restore_globals(sk, _saved)


def vector_hash(vector):
    """Stable hex digest of vector (checkpoint key helper).

    Args:
        vector: 4-tuple of floats

    Returns:
        hex string: hashlib.sha1 of '|'.join('%.6f' % x for x in vector)

    Guarantee (FC4.7):
        - pure, identical vectors -> identical hash
        - fixed precision (%.6f) to avoid float noise fragmenting cache
    """
    rounded = '|'.join('%.6f' % x for x in vector)
    return hashlib.sha1(rounded.encode()).hexdigest()


def _open_checkpoint(db_path):
    """Open sqlite checkpoint; CREATE TABLE IF NOT EXISTS.

    Args:
        db_path: path to fit_constants.db

    Returns:
        sqlite3.Connection

    Guarantee:
        - creates `episodes` and `incumbent` tables if not present (FC5 schema)
    """
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            param_hash TEXT NOT NULL,
            seed       INTEGER NOT NULL,
            liveness   REAL NOT NULL,
            diversity  REAL NOT NULL,
            variance   REAL NOT NULL,
            objective  REAL NOT NULL,
            PRIMARY KEY (param_hash, seed)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS incumbent (
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            sun_jitter_sd REAL NOT NULL,
            sun_osc_amp   REAL NOT NULL,
            capture_temp  REAL NOT NULL,
            bargain_temp  REAL NOT NULL,
            objective     REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def evaluate_episode(vector, seed, conn):
    """Checkpoint-guarded single-episode evaluation.

    Args:
        vector: 4-tuple
        seed: int
        conn: open sqlite connection

    Returns:
        (liveness, diversity, variance, objective)

    Guarantee (FC4.4, FC5):
        - on CACHE HIT: returns cached (l,d,v,o), does NOT call run_episode
        - on CACHE MISS: increments _EPISODE_RUNS, calls run_episode,
          computes components + scalar, INSERTs row, returns them
        - idempotent: re-evaluating same (vector, seed) reads cache on 2nd call (FC-5)
    """
    global _EPISODE_RUNS
    h = vector_hash(vector)
    row = conn.execute(
        "SELECT liveness, diversity, variance, objective FROM episodes "
        "WHERE param_hash=? AND seed=?", (h, seed)).fetchone()
    if row is not None:
        return (row[0], row[1], row[2], row[3])  # CACHE HIT

    # CACHE MISS
    _EPISODE_RUNS += 1
    alive_frac, mode_counts, sun_series = run_episode(vector, seed)
    l, d, v = objective_components(alive_frac, mode_counts, sun_series)
    obj = objective_scalar(l, d, v)
    conn.execute(
        "INSERT OR REPLACE INTO episodes "
        "(param_hash, seed, liveness, diversity, variance, objective) "
        "VALUES (?,?,?,?,?,?)", (h, seed, l, d, v, obj))
    conn.commit()
    return (l, d, v, obj)


def evaluate_candidate(vector, seeds, conn):
    """Average objective (and components) over N_SEEDS distinct seeded episodes.

    Args:
        vector: 4-tuple
        seeds: list of >= 1 ints
        conn: open sqlite connection

    Returns:
        (avg_objective, (avg_liveness, avg_diversity, avg_variance))

    Guarantee (FC4.5):
        - deterministic given (vector, seeds)
        - each component and objective averaged over seeds
    """
    n = len(seeds)
    acc_l = acc_d = acc_v = acc_o = 0.0
    for s in seeds:
        l, d, v, o = evaluate_episode(vector, s, conn)
        acc_l += l
        acc_d += d
        acc_v += v
        acc_o += o
    return (acc_o / n, (acc_l / n, acc_d / n, acc_v / n))


# --- Search & State Hygiene (FC7.3–FC7.4) ---

def _propose(proposer):
    """One random candidate uniformly within BOUNDS (private RNG instance).

    Args:
        proposer: random.Random(SEARCH_SEED) instance

    Returns:
        4-tuple candidate vector
    """
    return tuple(proposer.uniform(*BOUNDS[name]) for name in KNOB_ORDER)


def _save_globals(sk):
    """Save all 7 guarded globals from sandkings module.

    Returns:
        dict {name: value}
    """
    return {name: getattr(sk, name) for name in _GUARDED_GLOBALS}


def _restore_globals(sk, saved):
    """Restore all 7 guarded globals to sandkings module.

    Args:
        sk: sandkings module
        saved: dict {name: value} from _save_globals
    """
    for name, val in saved.items():
        setattr(sk, name, val)


def run_search(n_iters=N_ITERS, seeds=None, conn=None):
    """Keep-if-improved hill-climb from the inert baseline.

    Args:
        n_iters: number of proposals (default N_ITERS=8)
        seeds: list of seeds (default None -> list(range(N_SEEDS)))
        conn: open sqlite connection

    Returns:
        (incumbent_vector, incumbent_objective, incumbent_components, trajectory)

    Guarantee (FC4.6, FC-4):
        - incumbent starts at BASELINE_VECTOR
        - replaced ONLY on strictly-greater averaged objective
        - incumbent_objective >= baseline_objective (never regress)
        - trajectory: list of (incumbent_vector, inc_obj) per iteration
        - persists final incumbent to incumbent table

    Maintain (FC-1):
        - proposal RNG is a dedicated random.Random(SEARCH_SEED) instance
        - SEPARATE from module random that episodes reseed (determinism)
    """
    if seeds is None:
        seeds = list(range(N_SEEDS))

    # HS1: Proposal RNG is SEPARATE from module random
    proposer = random.Random(SEARCH_SEED)

    # Evaluate baseline
    incumbent = BASELINE_VECTOR
    inc_obj, inc_comps = evaluate_candidate(incumbent, seeds, conn)
    trajectory = [(incumbent, inc_obj)]

    # Hill-climb: keep if strictly improved
    for _ in range(n_iters):
        cand = _propose(proposer)
        cand_obj, cand_comps = evaluate_candidate(cand, seeds, conn)
        if cand_obj > inc_obj:  # STRICTLY greater -> keep (never regress)
            incumbent, inc_obj, inc_comps = cand, cand_obj, cand_comps
        trajectory.append((incumbent, inc_obj))

    # Persist final incumbent
    conn.execute(
        "INSERT OR REPLACE INTO incumbent "
        "(id, sun_jitter_sd, sun_osc_amp, capture_temp, bargain_temp, objective) "
        "VALUES (1,?,?,?,?,?)",
        (incumbent[0], incumbent[1], incumbent[2], incumbent[3], inc_obj))
    conn.commit()

    return incumbent, inc_obj, inc_comps, trajectory


def _report(base_obj, base_comps, incumbent, inc_obj, inc_comps):
    """Print table comparing inert baseline vs fitted incumbent.

    Args:
        base_obj: baseline objective
        base_comps: (base_l, base_d, base_v)
        incumbent: fitted vector
        inc_obj: fitted objective
        inc_comps: (inc_l, inc_d, inc_v)
    """
    base_l, base_d, base_v = base_comps
    inc_l, inc_d, inc_v = inc_comps

    print("==== fit_constants: learned vs inert (demonstrator; sandkings.py UNCHANGED) ====")
    print(f"                    OBJECTIVE   LIVENESS   MODE_DIV   WEATHER_VAR")
    print(f"  inert  (0,0,0,0)     {base_obj:.4f}      {base_l:.4f}       {base_d:.4f}        {base_v:.4f}")
    print(f"  fitted incumbent     {inc_obj:.4f}      {inc_l:.4f}       {inc_d:.4f}        {inc_v:.4f}")
    print(f"  fitted vector = "
          f"SUN_JITTER_SD={incumbent[0]:.4f}  "
          f"SUN_OSC_AMP={incumbent[1]:.4f}  "
          f"CAPTURE_TEMP={incumbent[2]:.4f}  "
          f"BARGAIN_TEMP={incumbent[3]:.4f}")
    print("  NOTE: this is a REPORT. Adopting these values into sandkings.py is a human decision.")
    print("================================================================================")


def fit(n_iters=N_ITERS, n_seeds=N_SEEDS, db_path=DB_PATH):
    """Top-level entry: save globals, run search, ALWAYS restore, report.

    Args:
        n_iters: number of proposals (default N_ITERS)
        n_seeds: distinct seeds per candidate (default N_SEEDS)
        db_path: sqlite checkpoint path (default DB_PATH)

    Returns:
        (incumbent, incumbent_objective, baseline_objective)

    Guarantee (FC-3):
        - on return OR exception, every _GUARDED_GLOBALS entry equals its pre-call value
        - the ONLY durable side effect is the sqlite checkpoint file
        - uses try/finally to ensure restoration even on exception
    """
    # HS2: Save globals BEFORE search, restore in finally
    saved = _save_globals(sk)
    conn = _open_checkpoint(db_path)
    try:
        # Evaluate baseline
        base_obj, base_comps = evaluate_candidate(BASELINE_VECTOR, list(range(n_seeds)), conn)

        # Run the search
        incumbent, inc_obj, inc_comps, trajectory = run_search(
            n_iters=n_iters, seeds=list(range(n_seeds)), conn=conn)

        # Report
        _report(base_obj, base_comps, incumbent, inc_obj, inc_comps)

        return incumbent, inc_obj, base_obj
    finally:
        # HS2: LOAD-BEARING restoration in finally
        _restore_globals(sk, saved)
        conn.close()


if __name__ == '__main__':
    fit()
