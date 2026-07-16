"""Telemetry & the regression tool (SPEC_TOOLS.md).

Environment stats made freely available (the Dwarf-Therapist analogue),
plus a PRE-WRAPPED regression call the awakened invoke to predict their
fortunes. Safe: fixed analysis functions, never evaluated text; no
network, no eval/exec. Preconditions: numpy; sklearn optional (numpy
polyfit fallback). A TabPFM regressor can drop into REGRESSION_BACKENDS
without touching callers.
"""

from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

import numpy as np

TELEMETRY_INTERVAL = 50     # steps between telemetry samples (TL1)
TELEMETRY_HISTORY = 64      # rows kept per colony (bounded ring)
TOOL_NUDGE = 0.03           # disposition nudge from a prediction (TL3)


def _new_ring() -> deque:
    """Module-level factory so the defaultdict pickles (no lambda)."""
    return deque(maxlen=TELEMETRY_HISTORY)


class Telemetry:
    """A bounded per-colony ring of environment stats (TL1). Pickles
    cheaply (small deques of plain floats)."""

    def __init__(self):
        self.rows: Dict[int, deque] = defaultdict(_new_ring)

    def record(self, sim) -> None:
        season = sim.season_index()
        holder = (sim.oasis_holder()
                  if callable(getattr(sim, 'oasis_holder', None)) else None)
        for colony in sim.colonies:
            if not colony.is_alive():
                continue
            att = (sim.keeper_attitude(colony)
                   if hasattr(sim, 'keeper_attitude') else 'none')
            self.rows[colony.colony_id].append({
                "step": int(sim.step_count),
                "food": round(float(colony.maw.food_stored), 1),
                "pop": int(len(colony.units)),
                "maw_hp": round(float(colony.maw.health), 1),
                "at_war": bool(getattr(colony, 'at_war', False)),
                "season": int(season),
                "oasis": colony.colony_id == holder,
                "attitude": att,
            })

    def history(self, colony_id: int) -> List[dict]:
        return list(self.rows.get(colony_id, ()))


def _fit_sklearn(steps: np.ndarray, food: np.ndarray) -> Tuple[float, float]:
    from sklearn.linear_model import LinearRegression
    model = LinearRegression().fit(steps.reshape(-1, 1), food)
    return float(model.coef_[0]), float(model.intercept_)


def _fit_numpy(steps: np.ndarray, food: np.ndarray) -> Tuple[float, float]:
    slope, intercept = np.polyfit(steps, food, 1)
    return float(slope), float(intercept)


# ordered: the first importable backend wins. A TabPFM regressor slots
# in here (same (steps, food) -> (slope, intercept) contract).
REGRESSION_BACKENDS = (("sklearn", _fit_sklearn), ("numpy", _fit_numpy))


def _fit(steps: np.ndarray, food: np.ndarray) -> Tuple[float, float, str]:
    for name, fn in REGRESSION_BACKENDS:
        try:
            slope, intercept = fn(steps, food)
            return slope, intercept, name
        except Exception:
            continue
    return 0.0, float(food[-1]) if len(food) else 0.0, "none"


def predict_food(rows: List[dict],
                 horizon: int = TELEMETRY_INTERVAL) -> Optional[Tuple[float, float]]:
    """TL2: fit food vs step over recent rows, extrapolate one horizon
    ahead. Returns (predicted_next, slope), or None with < 3 rows."""
    if len(rows) < 3:
        return None
    steps = np.array([r["step"] for r in rows], dtype=np.float64)
    food = np.array([r["food"] for r in rows], dtype=np.float64)
    slope, intercept, _backend = _fit(steps, food)
    predicted = slope * (steps[-1] + horizon) + intercept
    return float(predicted), float(slope)
