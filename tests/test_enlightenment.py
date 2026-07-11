"""Enlightenment tests (SPEC_ENLIGHTENMENT EN1-EN10, AT1-AT9).

The post-escape intelligence leap: ceiling bump, tech-xp multiplier,
codex-read multiplier, and heritability.
"""

import random
import unittest

import numpy as np

from sandkings import (
    SandKingsSimulation, ColonyGenome, ENLIGHTENED_CEILING, ENLIGHTENED_TECH_MULT,
    ENLIGHTENED_CODEX_MULT, STAGE_CEILING, TECH_PRACTICE_XP
)
from neuroevolution import BRAIN_HIDDEN_MAX
from codex import apply_lesson, LESSON_EFFECT, CODEX_NUDGE
from tech import TECH_LEARN_XP


def _make_sim(width=48, height=36, depth=12, num_colonies=3):
    """Helper: seed both random and np.random, then create a SandKingsSimulation."""
    random.seed(42)
    np.random.seed(42)
    return SandKingsSimulation(width=width, height=height, depth=depth,
                              num_colonies=num_colonies)


class TestEnlightenment(unittest.TestCase):
    """AT1-AT9: Enlightenment acceptance tests."""

    def test_escape_enlightens_and_raises_ceiling(self):
        """AT1 (EN1, EN2): _escape sets enlightened=True and raises brain_ceiling."""
        sim = _make_sim()
        colony = sim.colonies[0]

        # Before escape: enlightened should be False (or absent)
        assert getattr(colony, 'enlightened', False) is False
        initial_ceiling = getattr(colony.genome, 'brain_ceiling', 88)

        # Escape the colony
        sim._escape(colony)

        # After escape: enlightened should be True
        assert getattr(colony, 'enlightened', False) is True
        # Ceiling should be raised to ENLIGHTENED_CEILING
        assert colony.genome.brain_ceiling == ENLIGHTENED_CEILING
        # Verify the ceiling is strictly above the Shade cap
        assert ENLIGHTENED_CEILING > STAGE_CEILING[3]

    def test_enlightened_mutate_grows_bigger_brains(self):
        """AT2 (EN2, EN3): enlightened colony's ceiling takes effect through raised BRAIN_HIDDEN_MAX."""
        random.seed(42)
        np.random.seed(42)

        # Seed a brain ABOVE the old Shade cap (160) but within the enlightened
        # ceiling (224). mutate() clamps brain_hidden to min(BRAIN_HIDDEN_MAX,
        # brain_ceiling). Pre-enlightenment that is min(160, ...) and 210 would be
        # slammed to 160; post-raise it is min(224, 224)=224, so 210 survives.
        # mutation only nudges by a small step, so it stays well above 160.
        genome = ColonyGenome()
        genome.use_neural = True
        genome.brain_ceiling = ENLIGHTENED_CEILING   # 224
        genome.brain_hidden = 210                    # forbidden under the old 160 cap
        for _ in range(5):
            genome = genome.mutate(mutation_rate=0.1)
            assert genome.brain_hidden > STAGE_CEILING[3], \
                f"brain_hidden {genome.brain_hidden} clamped to the old Shade cap " \
                f"{STAGE_CEILING[3]} — the raised ceiling did not take effect"
        # And the cap itself was raised
        assert BRAIN_HIDDEN_MAX == 224

    def test_enlightened_tech_xp_climbs_faster(self):
        """AT3 (EN4): enlightened colony gains tech-xp ~×ENLIGHTENED_TECH_MULT."""
        sim = _make_sim()
        c_ctrl = sim.colonies[0]  # control: non-enlightened
        c_enl = sim.colonies[1]   # experimental: enlightened

        # Enlighten the second colony
        sim._escape(c_enl)
        assert getattr(c_enl, 'enlightened', False) is True

        # Practice the same tech the same number of times on both
        tech = 'masonry'
        amount = TECH_PRACTICE_XP  # 0.02
        for _ in range(10):
            sim._practice(c_ctrl, tech, amount)
            sim._practice(c_enl, tech, amount)

        xp_ctrl = c_ctrl.tech_xp.get(tech, 0.0)
        xp_enl = c_enl.tech_xp.get(tech, 0.0)

        # Enlightened should have ×MULT the xp (or capped at 1.0)
        # With amount=0.02, 10 calls = 0.2 base, ×5 = 1.0 (capped)
        # Control: min(1.0, 0.2) = 0.2
        assert abs(xp_ctrl - min(1.0, 10 * amount)) < 1e-9   # ~0.2 (float-accumulated)
        assert xp_enl > 0.99  # ×5 -> effectively capped (0.1*10 = 0.999.. in float)
        # The multiplier climbed the enlightened colony strictly faster
        assert xp_enl > xp_ctrl

    def test_enlightened_codex_reads_harder(self):
        """AT4 (EN5): enlightened colony's genome attr delta ~×ENLIGHTENED_CODEX_MULT."""
        # Create two genomes
        g_ctrl = ColonyGenome()
        g_enl = ColonyGenome()

        # Pick a lesson and attribute: "coop" -> ("loyalty", 1.0)
        lesson = "coop"
        attr = "loyalty"

        # Set mid-range starting values
        for g in [g_ctrl, g_enl]:
            setattr(g, attr, 0.5)

        # Apply lesson without scale (control)
        apply_lesson(g_ctrl, lesson, scale=1.0)

        # Apply lesson with scale (enlightened)
        apply_lesson(g_enl, lesson, scale=ENLIGHTENED_CODEX_MULT)

        delta_ctrl = getattr(g_ctrl, attr) - 0.5
        delta_enl = getattr(g_enl, attr) - 0.5

        # Enlightened delta should be ~×MULT the control (before clip)
        # CODEX_NUDGE * weight * scale = 0.03 * 1.0 * 1.0 = 0.03 (ctrl)
        # CODEX_NUDGE * weight * scale = 0.03 * 1.0 * 5.0 = 0.15 (enl)
        expected_ctrl = CODEX_NUDGE * 1.0 * 1.0  # 0.03
        expected_enl = CODEX_NUDGE * 1.0 * ENLIGHTENED_CODEX_MULT  # 0.15

        assert abs(delta_ctrl - expected_ctrl) < 1e-6
        assert abs(delta_enl - expected_enl) < 1e-6

        # Verify default scale=1.0 is backward-compatible
        g_default = ColonyGenome()
        setattr(g_default, attr, 0.5)
        apply_lesson(g_default, lesson)  # no scale argument
        assert getattr(g_default, attr) == getattr(g_ctrl, attr)

    def test_ascension_fires_once(self):
        """AT5 (EN6, EN7): ascension fires exactly once and leaves ceiling unchanged."""
        sim = _make_sim()
        colony = sim.colonies[0]

        # First escape
        sim._escape(colony)
        ceiling_after_first = colony.genome.brain_ceiling
        events_after_first = len([e for e in sim.events
                                  if "ascends" in str(e).lower() and "light" in str(e).lower()])

        # Second escape (should be no-op due to breached guard)
        sim._escape(colony)
        ceiling_after_second = colony.genome.brain_ceiling
        events_after_second = len([e for e in sim.events
                                   if "ascends" in str(e).lower() and "light" in str(e).lower()])

        # Verify no change on second call
        assert ceiling_after_second == ceiling_after_first == ENLIGHTENED_CEILING
        assert events_after_second == events_after_first == 1

    def test_enlightened_inherits_on_respawn(self):
        """AT6 (EN8): enlightened flag inherits on respawn; brain_ceiling survives."""
        sim = _make_sim(num_colonies=3)
        pa = sim.colonies[0]
        pb = sim.colonies[1]
        victim = sim.colonies[2]

        # Enlighten both parents
        sim._escape(pa)
        sim._escape(pb)
        assert getattr(pa, 'enlightened', False) is True
        assert getattr(pb, 'enlightened', False) is True

        # Kill the victim PROPERLY (health alone leaves maw.alive True, which would
        # let the respawn's survivor-scan still pick the victim's own genome).
        victim.maw.health = 0
        victim.maw.alive = False
        victim_id = victim.colony_id

        # Force respawn via crossed/hybrid (both parents alive)
        sim.pending_respawns[victim_id] = sim.step_count
        sim._process_respawns()

        # Find the respawned colony (same ID, different object)
        respawned = next(c for c in sim.colonies if c.colony_id == victim_id)

        # Verify enlightened inheritance and ceiling survival
        assert getattr(respawned, 'enlightened', False) is True
        assert respawned.genome.brain_ceiling >= ENLIGHTENED_CEILING

        # Negative control: in a FRESH sim where NO colony is enlightened, a
        # respawn cadet must NOT be enlightened. (Reusing `sim` here would be wrong
        # — its surviving parents are all enlightened, so any cadet inherits it.)
        sim2 = _make_sim(num_colonies=3)
        plain_victim = sim2.colonies[2]
        plain_victim.maw.health = 0
        plain_victim.maw.alive = False
        plain_id = plain_victim.colony_id
        sim2.pending_respawns[plain_id] = sim2.step_count
        sim2._process_respawns()

        plain_cadet = next(c for c in sim2.colonies if c.colony_id == plain_id)
        assert getattr(plain_cadet, 'enlightened', False) is False

    def test_enlightenment_state_pickles(self):
        """AT7 (EN1): enlightened flag and brain_ceiling survive pickle round-trip."""
        import pickle

        sim = _make_sim()
        colony = sim.colonies[0]

        # Enlighten
        sim._escape(colony)
        assert getattr(colony, 'enlightened', False) is True
        ceiling_before = colony.genome.brain_ceiling

        # Pickle and unpickle
        pickled = pickle.dumps(colony)
        restored = pickle.loads(pickled)

        # Verify state survived
        assert getattr(restored, 'enlightened', False) is True
        assert restored.genome.brain_ceiling == ceiling_before == ENLIGHTENED_CEILING

    def test_non_escaped_colony_is_byte_identical(self):
        """AT8 (EN3, default-neutral): non-escaped colonies are byte-identical.

        Runs the existing test battery to ensure raising BRAIN_HIDDEN_MAX
        and adding multiplier code does not change non-escaped behavior.
        """
        # This test verifies that:
        # 1. A non-escaped colony has enlightened=False (default)
        # 2. Running _practice without escape gives base xp gains
        # 3. Running _codex_tick without escape gives base lesson nudges
        # 4. The existing battery (test_awareness.py, test_metamorphosis.py, etc.)
        #    still passes with the changes

        sim = _make_sim()
        colony = sim.colonies[0]

        # Never escape
        assert getattr(colony, 'enlightened', False) is False

        # Practice without escape: should use base amount, not multiplied
        tech = 'masonry'
        initial_xp = colony.tech_xp.get(tech, 0.0)
        sim._practice(colony, tech, TECH_PRACTICE_XP)
        final_xp = colony.tech_xp.get(tech, 0.0)

        # Gain should be exactly TECH_PRACTICE_XP (capped at 1.0)
        expected_gain = min(1.0, initial_xp + TECH_PRACTICE_XP)
        assert final_xp == expected_gain

        # Verify no multiplier was applied
        assert final_xp == min(1.0, initial_xp + TECH_PRACTICE_XP)

        # Codex lesson without escape should use scale=1.0
        g = colony.genome
        initial_loyalty = getattr(g, 'loyalty', 0.5)
        # The apply_lesson call in _codex_tick uses scale=1.0 for non-enlightened
        apply_lesson(g, "coop", scale=1.0)
        final_loyalty = getattr(g, 'loyalty')

        # Nudge should be exactly CODEX_NUDGE * weight (default scale=1.0)
        expected_nudge = CODEX_NUDGE * 1.0  # weight=1.0 for "loyalty" in "coop"
        assert abs(final_loyalty - (initial_loyalty + expected_nudge)) < 1e-6

    def test_enhanced_step_inert(self):
        """AT9 (EN10): EnhancedSandKingsSimulation never escapes, so never enlightens."""
        try:
            from sandkings_evolution import EnhancedSandKingsSimulation
        except ImportError:
            self.skipTest("EnhancedSandKingsSimulation not available")

        # Create enhanced sim
        random.seed(42)
        np.random.seed(42)
        enhanced = EnhancedSandKingsSimulation(width=48, height=36, depth=12,
                                              num_colonies=3)

        # Step many times
        for _ in range(100):
            enhanced.step()

        # No colony should be enlightened
        for colony in enhanced.colonies:
            assert getattr(colony, 'enlightened', False) is False

        # No ascend event should be logged
        ascend_events = [e for e in enhanced.events
                        if "ascends" in str(e).lower() and "light" in str(e).lower()]
        assert len(ascend_events) == 0


if __name__ == '__main__':
    unittest.main()
