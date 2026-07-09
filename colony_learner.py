"""Colony posture learner: tabular TD(0) over a coarse economic state.

Governed by SPEC_SEASONS_AND_STONE.md T26. The learner BIASES the rule
baseline (gates, mixes, guard behavior) and never overrides it — the
chess-findings recipe: the heuristic carries early play, learning refines.
gamma is the colony's evolvable `genome.patience`: the discount factor IS
the long-term-vs-short-term temperament.

Preconditions: numpy only; pickles with the sim. Failure modes: unknown
states start at zero Q (optimistic-neutral); epsilon never falls below
EPSILON_FLOOR so exploration never dies.
"""

import random
from typing import Dict, Optional, Tuple

import numpy as np

LEARN_INTERVAL = 25    # steps between posture decisions / TD updates
LEARN_RATE = 0.2
EPSILON_START = 0.8    # mostly-follow-baseline early (anneal in)
EPSILON_FLOOR = 0.4
EPSILON_DECAY = 0.999  # per decision
POSTURES = ("FORAGE", "FARM", "RAID", "FORTIFY")
POP_WEIGHT = 15.0      # reward values a unit like the power index does


def observe_state(sim, colony) -> Tuple[int, int, int, bool, bool]:
    """Coarse state: (season, food-band, threat-band, farms>0, oasis-held)."""
    food = colony.maw.food_stored
    if food < 30:
        food_band = 0
    elif food < 200:
        food_band = 1
    elif food < 400:
        food_band = 2
    else:
        food_band = 3

    threat = 0
    mx, my, mz = colony.maw.position
    for other in sim.colonies:
        if other.colony_id == colony.colony_id:
            continue
        for enemy in other.units:
            d = (abs(enemy.position[0] - mx) + abs(enemy.position[1] - my)
                 + abs(enemy.position[2] - mz))
            if d <= 2:
                threat = 2
                break
            if d <= 15:
                threat = max(threat, 1)
        if threat == 2:
            break

    farms = sim._farm_plot_count(colony) > 0
    oasis = sim.oasis_holder() == colony.colony_id
    return (sim.season_index(), food_band, threat, farms, oasis)


class ColonyLearner:
    """One colony's Q-table, epsilon, and pending TD transition."""

    def __init__(self):
        self.q: Dict[Tuple, np.ndarray] = {}
        self.epsilon = EPSILON_START
        self.posture = "FORAGE"
        self.decisions = 0
        self._last_state: Optional[Tuple] = None
        self._last_action = 0
        self._last_value = 0.0

    def _qrow(self, state: Tuple) -> np.ndarray:
        if state not in self.q:
            self.q[state] = np.zeros(len(POSTURES))
        return self.q[state]

    def decide(self, sim, colony, gamma: float) -> str:
        """TD(0) update on the last transition, then epsilon-greedy pick."""
        state = observe_state(sim, colony)
        value = colony.maw.food_stored + POP_WEIGHT * len(colony.units)

        if self._last_state is not None:
            reward = (value - self._last_value) / LEARN_INTERVAL
            row = self._qrow(self._last_state)
            target = reward + gamma * float(self._qrow(state).max())
            row[self._last_action] += LEARN_RATE * (target - row[self._last_action])

        if random.random() < self.epsilon:
            action = random.randrange(len(POSTURES))
        else:
            action = int(np.argmax(self._qrow(state)))
        self.epsilon = max(EPSILON_FLOOR, self.epsilon * EPSILON_DECAY)

        self._last_state = state
        self._last_action = action
        self._last_value = value
        self.decisions += 1
        self.posture = POSTURES[action]
        return self.posture

    def best_posture(self, state: Tuple) -> str:
        """The learned greedy choice for a state ('?' before any data)."""
        if state not in self.q or not self.q[state].any():
            return "?"
        return POSTURES[int(np.argmax(self.q[state]))]
