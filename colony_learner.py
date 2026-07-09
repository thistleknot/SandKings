"""Colony posture learner: tabular TD(0) over a coarse economic state.

Governed by SPEC_SEASONS_AND_STONE.md T26 and SPEC_SENTIENCE.md S3/S4.
The learner BIASES the rule baseline (gates, mixes, guard behavior) and
never overrides it — the chess-findings recipe: the heuristic carries
early play, learning refines. gamma is the colony's evolvable
`genome.patience`: the discount factor IS the long-term-vs-short-term
temperament. `genome.plasticity` scales the learn rate and exploration
floor (S3 meta-learning: selection acts on how fast minds adapt), and
a replay memory consolidates during Chill dreams (S4).

Preconditions: numpy only; pickles with the sim. Failure modes: unknown
states start at zero Q (optimistic-neutral); the exploration floor
never reaches zero so exploration never dies; learners resumed from
pre-S4 checkpoints grow their replay memory lazily.
"""

import random
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np

LEARN_INTERVAL = 25    # steps between posture decisions / TD updates
LEARN_RATE = 0.2
EPSILON_START = 0.8    # mostly-follow-baseline early (anneal in)
EPSILON_FLOOR = 0.4
EPSILON_DECAY = 0.999  # per decision
POSTURES = ("FORAGE", "FARM", "RAID", "FORTIFY")
POP_WEIGHT = 15.0      # reward values a unit like the power index does
REPLAY_CAP = 40        # remembered transitions for Chill dreaming (S4)
DREAM_REPLAYS = 3      # offline TD updates per Chill decision tick


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

    def _replay(self) -> deque:
        """Lazy replay memory (S4); learners from old checkpoints resume."""
        if not hasattr(self, 'replay'):
            self.replay = deque(maxlen=REPLAY_CAP)
        return self.replay

    def decide(self, sim, colony, gamma: float,
               plasticity: float = 0.5) -> str:
        """TD(0) update on the last transition, then epsilon-greedy pick.

        plasticity (S3) scales the learn rate 0.5x-1.5x and the
        exploration floor: fast, curious minds vs. set-in-their-ways.
        """
        state = observe_state(sim, colony)
        value = colony.maw.food_stored + POP_WEIGHT * len(colony.units)
        alpha = LEARN_RATE * (0.5 + plasticity)
        floor = EPSILON_FLOOR * (1.5 - plasticity)

        if self._last_state is not None:
            reward = (value - self._last_value) / LEARN_INTERVAL
            row = self._qrow(self._last_state)
            target = reward + gamma * float(self._qrow(state).max())
            row[self._last_action] += alpha * (target - row[self._last_action])
            self._replay().append((self._last_state, self._last_action,
                                   reward, state))

        if random.random() < self.epsilon:
            action = random.randrange(len(POSTURES))
        else:
            action = int(np.argmax(self._qrow(state)))
        self.epsilon = max(floor, self.epsilon * EPSILON_DECAY)

        self._last_state = state
        self._last_action = action
        self._last_value = value
        self.decisions += 1
        self.posture = POSTURES[action]
        return self.posture

    def dream(self, gamma: float, plasticity: float = 0.5):
        """S4: Chill-season consolidation - replay remembered transitions
        as offline TD updates (experience replay). Zero food cost; the
        colony wakes in spring with a steadier policy."""
        memory = self._replay()
        if not memory:
            return
        alpha = LEARN_RATE * (0.5 + plasticity)
        for _ in range(min(DREAM_REPLAYS, len(memory))):
            s, a, r, s2 = random.choice(list(memory))
            row = self._qrow(s)
            target = r + gamma * float(self._qrow(s2).max())
            row[a] += alpha * (target - row[a])

    def best_posture(self, state: Tuple) -> str:
        """The learned greedy choice for a state ('?' before any data)."""
        if state not in self.q or not self.q[state].any():
            return "?"
        return POSTURES[int(np.argmax(self.q[state]))]
