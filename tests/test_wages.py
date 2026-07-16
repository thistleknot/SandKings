"""Acceptance tests for SPEC_WAGES.md (WG1-WG12) - the wage market.

Labor contracts, tech licenses, and goods trade at negotiated prices. The spec
gates all features behind WAGE_ENABLED; with it False, the module is
byte-identical to pre-M3 code (WGA-1). With it True, enables labor redistribution
(WGA-2–WGA-4), comparative advantage (WGA-5), license effects (WGA-6),
grain non-negativity (WGA-7), war suspension without defiance (WGA-8),
M2 inertness (WGA-9), and pickling/getattr-guarding (WGA-10).
"""

import os
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))

import numpy as np

from sandkings import (
    WAGE_ENABLED, RENEGOTIATE_INTERVAL, SETTLEMENT_INTERVAL,
    COMPLEMENTARITY_THRESHOLD, W_CONTRACT_MIN, LICENSE_FEE_BASE,
    LICENSE_TECH_MULT, WAGE_GRAIN_RATE, WAGE_POWER_SHARE_BASE,
    WAGE_POWER_SHARE_SENS, MV_BASE, DESPERATION_LABOR_REF, CONTROL_TECH_REF,
    LABOR_MAX_UNITS, GOODS_VOLUME_CAP, NONVIABLE_LIMIT, EPS_POWER,
    W_BRUTE, W_FAIR, TECH_FOREIGN, GIFT_LADDER,
    SandKing, SandKingsSimulation, UnitType, Colony
)


def make_sim(seed: int = 5) -> SandKingsSimulation:
    """Create a reproducible simulation with 3 colonies. Matches test_tech.py pattern."""
    random.seed(seed)
    np.random.seed(seed)
    sim = SandKingsSimulation(width=48, height=36, depth=12, num_colonies=3)
    sim.keeper_auto = False
    return sim


class TestWagesDefaultNeutral(unittest.TestCase):
    """WGA-1: DEFAULT-NEUTRAL. With WAGE_ENABLED=False, module is byte-identical to pre-M3."""

    def test_wage_enabled_defaults_false(self):
        """WAGE_ENABLED module constant defaults to False."""
        assert WAGE_ENABLED is False, "WAGE_ENABLED should default to False"

    def test_labor_market_tick_early_returns_when_disabled(self):
        """_labor_market_tick() early-returns before any RNG/state when WAGE_ENABLED=False."""
        sim = make_sim()
        initial_contracts = len(sim._wage_contracts())
        random_call_count = 0

        with patch('random.random', side_effect=lambda: (random_call_count := random_call_count + 1, 0.5)[1]):
            sim._labor_market_tick()

        assert len(sim._wage_contracts()) == initial_contracts, "No contracts should open with WAGE_ENABLED=False"
        assert random_call_count == 0, "_labor_market_tick should consume zero random() calls when disabled"

    def test_credit_labor_bytewise_identical_with_defaults(self):
        """_credit_labor with default wage_ratio (0.0) and license_yield_mult (1.0) is byte-identical."""
        sim = make_sim()
        colony = sim.colonies[0]
        colony.units.clear()
        mx, my, mz = colony.maw.position
        unit = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
        unit.laboring_for = -1  # free
        assert getattr(unit, 'wage_ratio', W_BRUTE) == 0.0
        assert sim._license_yield_mult(colony) == 1.0

        colony.units.append(unit)
        initial_food = colony.maw.food_stored
        amount = 10.0

        sim._credit_labor(unit, colony, 'food', amount)

        # With wage_ratio=0 and mult=1.0, should deposit entire amount to colony
        expected_food = initial_food + amount
        assert colony.maw.food_stored == expected_food, f"Expected {expected_food}, got {colony.maw.food_stored}"

    def test_subjugation_tick_unchanged_when_no_wage_contracts(self):
        """_subjugation_tick processes thralls exactly as before when no wage contracts exist."""
        # Create a fresh sim with a thrall (laboring_for >= 0, wage_ratio == 0)
        sim = make_sim()
        colony = sim.colonies[0]
        captor = sim.colonies[1]
        colony.units.clear()
        captor.units.clear()

        mx, my, mz = colony.maw.position
        unit = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
        unit.laboring_for = captor.colony_id  # thrall
        unit.defiance = 0.0
        assert getattr(unit, 'wage_ratio', W_BRUTE) == 0.0

        colony.units.append(unit)
        captor.maw.position = (mx + 10, my + 10, mz)  # far away, unguarded

        initial_defiance = unit.defiance
        sim._subjugation_tick()

        # Thrall with wage_ratio=0 should be processed; defiance should rise when unguarded
        assert unit.defiance > initial_defiance, "Thrall defiance should rise when unguarded"


class TestWagesLaborContractRedirection(unittest.TestCase):
    """WGA-2: Labor contracts redirect output; both strictly gain."""

    def test_labor_contract_opens_on_complementarity(self):
        """Labor contract opens when seller has surplus labor and buyer has deficit."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            seller = sim.colonies[0]
            buyer = sim.colonies[1]

            # Set endowments: seller labor-rich, buyer labor-poor
            seller.units.clear()
            buyer.units.clear()
            # Add 5 free units to seller
            mx, my, mz = seller.maw.position
            for i in range(5):
                u = SandKing(seller.colony_id, (mx + i, my, mz), UnitType.WORKER)
                seller.units.append(u)
            # Add 0 free units to buyer (labor-poor)
            # Set buyer to have currency for one settlement
            buyer.currency = 100.0
            seller.currency = 0.0
            buyer.maw.food_stored = 2.0  # some food, not much
            seller.maw.food_stored = 20.0  # plenty of food

            # Open a contract
            initial_contracts = len(sim._wage_contracts())
            sim._wage_open_sweep()

            # Check that a labor contract was opened
            assert len(sim._wage_contracts()) > initial_contracts, "No labor contract opened"
            labor_contracts = [c for c in sim._wage_contracts() if c['kind'] == 'labor']
            assert len(labor_contracts) > 0, "Expected a labor contract"
            assert labor_contracts[0]['seller_id'] == seller.colony_id
            assert labor_contracts[0]['buyer_id'] == buyer.colony_id
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled

    def test_output_split_in_kind(self):
        """Labor output splits in-kind: buyer gets (1-w)*V, birth gets w*V."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            colony = sim.colonies[0]
            buyer = sim.colonies[1]
            colony.units.clear()

            mx, my, mz = colony.maw.position
            unit = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
            unit.laboring_for = buyer.colony_id
            unit.wage_ratio = 0.3  # seller keeps 30%
            colony.units.append(unit)

            colony.maw.food_stored = 100.0
            buyer.maw.food_stored = 50.0

            amount = 20.0  # 20 food produced
            # With w=0.3: birth should get 20*0.3=6, buyer should get 20*0.7=14
            initial_colony_food = colony.maw.food_stored
            initial_buyer_food = buyer.maw.food_stored

            sim._credit_labor(unit, colony, 'food', amount)

            # Check conservation
            total_produced = (colony.maw.food_stored - initial_colony_food) + (buyer.maw.food_stored - initial_buyer_food)
            assert abs(total_produced - amount) < 0.01, f"Expected conservation, got {total_produced} vs {amount}"

            # Check split
            colony_share = colony.maw.food_stored - initial_colony_food
            buyer_share = buyer.maw.food_stored - initial_buyer_food
            assert abs(colony_share - amount * 0.3) < 0.01
            assert abs(buyer_share - amount * 0.7) < 0.01
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled

    def test_grain_transfer_on_settlement(self):
        """On settlement, grains transfer buyer->seller; Σ(currency)+Σ(escrow) conserved."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            seller = sim.colonies[0]
            buyer = sim.colonies[1]

            seller.currency = 10.0
            buyer.currency = 100.0

            contract = {
                'kind': 'labor',
                'buyer_id': buyer.colony_id,
                'seller_id': seller.colony_id,
                'factor': 'labor',
                'w': 0.3,
                'volume': 2,
                'fee': 20.0,
                'escrow': 20.0,
                'unit_ids': [],
                'opened_step': 0,
                'last_reneg': 0,
                'nonviable': 0,
                'suspended': False,
                'alive': True,
            }

            initial_sum = seller.currency + buyer.currency + contract['escrow']
            sim._settle(contract)

            # After settle: old escrow paid out (-> seller), then re-prepaid by solvent buyer (-> new escrow)
            # With buyer.currency=100 >= fee=20, buyer re-prepays next interval
            assert contract['escrow'] == 20.0, f"Expected re-prepay of 20.0, got {contract['escrow']}"
            # Sum conserved (initial 130 = seller 10 + buyer 100 + escrow 20)
            # After: seller 30, buyer 80, escrow 20 = 130
            final_sum = seller.currency + buyer.currency + contract.get('escrow', 0)
            assert abs(final_sum - initial_sum) < 0.01, f"Grains not conserved: {initial_sum} -> {final_sum}"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesWeakerPartyLowerW(unittest.TestCase):
    """WGA-3: Weaker/desperate seller gets lower w."""

    def test_weaker_seller_lower_w(self):
        """A seller with lower composite_power receives lower w from the same buyer."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            weak_seller = sim.colonies[0]
            strong_seller = sim.colonies[1]
            buyer = sim.colonies[2]

            weak_seller.units.clear()
            strong_seller.units.clear()
            buyer.units.clear()

            # Make strong_seller stronger
            mx, my, mz = strong_seller.maw.position
            for i in range(10):
                u = SandKing(strong_seller.colony_id, (mx + i % 3, my + i // 3, mz), UnitType.SOLDIER)
                strong_seller.units.append(u)
            strong_seller.currency = 100.0
            strong_seller.ore = {'copper': 10, 'gold': 5}

            # weak_seller has few units
            mx, my, mz = weak_seller.maw.position
            u = SandKing(weak_seller.colony_id, (mx + 1, my, mz), UnitType.WORKER)
            weak_seller.units.append(u)
            weak_seller.currency = 0.0
            weak_seller.ore = {}

            buyer.units.clear()
            buyer.currency = 100.0

            w_weak = sim._labor_w(weak_seller, buyer)
            w_strong = sim._labor_w(strong_seller, buyer)

            # Weaker seller should get lower w (keeps less)
            assert w_weak < w_strong, f"Weak seller should have lower w: {w_weak} >= {w_strong}"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesGiftHolderTerms(unittest.TestCase):
    """WGA-4: Gift-holder extracts better terms (lower w) at equal military power."""

    def test_gift_holder_lower_w(self):
        """A buyer holding a TECH_FOREIGN gift gets lower w (keeps more) than non-holder."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            seller = sim.colonies[0]
            buyer_with_gift = sim.colonies[1]
            buyer_without_gift = sim.colonies[2]

            seller.units.clear()
            buyer_with_gift.units.clear()
            buyer_without_gift.units.clear()

            # Give both buyers same unit count (equal military power)
            mx, my, mz = buyer_with_gift.maw.position
            for i in range(5):
                u = SandKing(buyer_with_gift.colony_id, (mx + i, my, mz), UnitType.SOLDIER)
                buyer_with_gift.units.append(u)

            mx, my, mz = buyer_without_gift.maw.position
            for i in range(5):
                u = SandKing(buyer_without_gift.colony_id, (mx + i, my, mz), UnitType.SOLDIER)
                buyer_without_gift.units.append(u)

            # Give buyer_with_gift a foreign tech
            buyer_with_gift.techs = {'abacus'}
            buyer_without_gift.techs = set()

            seller.units.clear()
            mx, my, mz = seller.maw.position
            for i in range(10):
                u = SandKing(seller.colony_id, (mx + i % 3, my + i // 3, mz), UnitType.WORKER)
                seller.units.append(u)

            w_without_gift = sim._labor_w(seller, buyer_without_gift)
            w_with_gift = sim._labor_w(seller, buyer_with_gift)

            # Buyer with gift should get lower w (keeps more)
            assert w_with_gift < w_without_gift, f"Gift holder should have lower w: {w_with_gift} >= {w_without_gift}"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesComparativeAdvantage(unittest.TestCase):
    """WGA-5: Comparative advantage - labor-rich sells labor, tech-poor buys tech."""

    def test_comparative_advantage_both_directions(self):
        """In a peace pair, labor-rich sells labor AND tech-poor buys tech simultaneously."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            labor_rich = sim.colonies[0]
            tech_rich = sim.colonies[1]

            labor_rich.units.clear()
            tech_rich.units.clear()

            # labor_rich: many workers, no foreign tech
            mx, my, mz = labor_rich.maw.position
            for i in range(8):
                u = SandKing(labor_rich.colony_id, (mx + i % 3, my + i // 3, mz), UnitType.WORKER)
                labor_rich.units.append(u)
            labor_rich.techs = set()
            labor_rich.currency = 100.0

            # tech_rich: few workers, has foreign tech
            mx, my, mz = tech_rich.maw.position
            u = SandKing(tech_rich.colony_id, (mx + 1, my, mz), UnitType.WORKER)
            tech_rich.units.append(u)
            tech_rich.techs = {'abacus', 'watch'}
            tech_rich.currency = 100.0

            initial_contracts = len(sim._wage_contracts())
            sim._wage_open_sweep()

            # Should open both a labor contract (labor_rich sells) and a license (tech_rich rents)
            new_contracts = [c for c in sim._wage_contracts() if sim._wage_contracts().index(c) >= initial_contracts]
            labor_contracts = [c for c in new_contracts if c['kind'] == 'labor']
            license_contracts = [c for c in new_contracts if c['kind'] == 'license']

            assert len(labor_contracts) > 0, "Should open a labor contract"
            assert len(license_contracts) > 0, "Should open a license contract"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesLicenseYield(unittest.TestCase):
    """WGA-6: License multiplier applies to renter, expires with contract, owner untouched."""

    def test_license_yield_mult_renter_vs_owner(self):
        """Renter under license gets yield boost; owner doesn't."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            owner = sim.colonies[0]
            renter = sim.colonies[1]

            owner.techs = {'abacus'}
            renter.techs = set()

            # Create a license contract
            contract = {
                'kind': 'license',
                'buyer_id': renter.colony_id,
                'seller_id': owner.colony_id,
                'factor': 'abacus',
                'w': 0.0,
                'volume': 1,
                'fee': 2.0,
                'escrow': 2.0,
                'unit_ids': [],
                'opened_step': 0,
                'last_reneg': 0,
                'nonviable': 0,
                'suspended': False,
                'alive': True,
            }
            sim.wage_contracts = [contract]

            # Renter's yield should be boosted
            renter_mult = sim._license_yield_mult(renter)
            assert renter_mult == LICENSE_TECH_MULT['abacus'], f"Renter mult should be {LICENSE_TECH_MULT['abacus']}, got {renter_mult}"

            # Owner's yield should be 1.0 (unaffected)
            owner_mult = sim._license_yield_mult(owner)
            assert owner_mult == 1.0, f"Owner mult should be 1.0, got {owner_mult}"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled

    def test_license_expires_on_close(self):
        """When a license contract is closed, renter's yield multiplier reverts to 1.0."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            owner = sim.colonies[0]
            renter = sim.colonies[1]

            owner.techs = {'calculator'}
            renter.techs = set()

            contract = {
                'kind': 'license',
                'buyer_id': renter.colony_id,
                'seller_id': owner.colony_id,
                'factor': 'calculator',
                'w': 0.0,
                'volume': 1,
                'fee': 2.0,
                'escrow': 2.0,
                'unit_ids': [],
                'opened_step': 0,
                'last_reneg': 0,
                'nonviable': 0,
                'suspended': False,
                'alive': True,
            }
            sim.wage_contracts = [contract]

            # Renter has boost
            assert sim._license_yield_mult(renter) == LICENSE_TECH_MULT['calculator']

            # Close the contract
            contract['alive'] = False

            # Renter's boost is gone
            assert sim._license_yield_mult(renter) == 1.0
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesNonNegativity(unittest.TestCase):
    """WGA-7: Grain non-negativity & conservation."""

    def test_buyer_currency_never_negative(self):
        """Across all contract operations, buyer.currency stays >= 0."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            buyer = sim.colonies[0]
            seller = sim.colonies[1]

            buyer.currency = 10.0  # limited funds
            seller.currency = 0.0

            # Try to open contracts that require high fees
            seller.units.clear()
            buyer.units.clear()
            mx, my, mz = seller.maw.position
            for i in range(10):
                u = SandKing(seller.colony_id, (mx + i % 3, my + i // 3, mz), UnitType.WORKER)
                seller.units.append(u)

            initial_buyer_currency = buyer.currency
            sim._wage_open_sweep()

            # After open sweep, buyer should still have >= 0 currency
            assert buyer.currency >= 0, f"Buyer currency went negative: {buyer.currency}"
            # And it should be <= initial (prepaid)
            assert buyer.currency <= initial_buyer_currency
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled

    def test_grains_conserved_across_settlement(self):
        """Σ(currency) + Σ(escrow) is invariant across settlement (except _score_forecasts mints)."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            buyer = sim.colonies[0]
            seller = sim.colonies[1]

            buyer.currency = 100.0
            seller.currency = 50.0

            contract = {
                'kind': 'labor',
                'buyer_id': buyer.colony_id,
                'seller_id': seller.colony_id,
                'factor': 'labor',
                'w': 0.3,
                'volume': 2,
                'fee': 20.0,
                'escrow': 20.0,
                'unit_ids': [],
                'opened_step': 0,
                'last_reneg': 0,
                'nonviable': 0,
                'suspended': False,
                'alive': True,
            }

            initial_total = buyer.currency + seller.currency + contract['escrow']
            sim._settle(contract)
            final_total = buyer.currency + seller.currency + contract['escrow']

            assert abs(final_total - initial_total) < 0.01, f"Grains not conserved: {initial_total} -> {final_total}"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWarsWarSuspension(unittest.TestCase):
    """WGA-8: War suspends contracts and frees laborers WITHOUT M2 defiance."""

    def test_war_entry_suspends_contract(self):
        """When a peace pair enters war, labor contracts suspend."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            buyer = sim.colonies[0]
            seller = sim.colonies[1]

            seller.units.clear()
            buyer.units.clear()

            # Create a labor contract
            mx, my, mz = seller.maw.position
            unit = SandKing(seller.colony_id, (mx + 1, my, mz), UnitType.WORKER)
            unit.laboring_for = buyer.colony_id
            unit.wage_ratio = 0.3
            seller.units.append(unit)

            contract = {
                'kind': 'labor',
                'buyer_id': buyer.colony_id,
                'seller_id': seller.colony_id,
                'factor': 'labor',
                'w': 0.3,
                'volume': 1,
                'fee': 5.0,
                'escrow': 5.0,
                'unit_ids': [unit.unit_id],
                'opened_step': 0,
                'last_reneg': 0,
                'nonviable': 0,
                'suspended': False,
                'alive': True,
            }
            sim.wage_contracts = [contract]

            # Enter war
            d = sim._diplomacy()
            d.war_target[buyer.colony_id] = seller.colony_id

            # Suspend/close contracts
            sim._wage_suspend_close()

            assert contract['suspended'] is True, "Contract should be suspended"
            assert unit.laboring_for == -1, "Unit should be freed"
            assert unit.wage_ratio == 0.0, "Unit wage_ratio should reset"
            assert contract['escrow'] == 0.0, "Escrow should be refunded"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesM2Unchanged(unittest.TestCase):
    """WGA-9: M2 unchanged when no wage contracts exist."""

    def test_m2_byte_identical_with_only_thralls(self):
        """With WAGE_ENABLED=True but no wage contracts, M2 thralls processed exactly as before."""
        sandkings_module = sys.modules['sandkings']
        original_wage_enabled = sandkings_module.WAGE_ENABLED
        try:
            sandkings_module.WAGE_ENABLED = True

            sim = make_sim()
            colony = sim.colonies[0]
            captor = sim.colonies[1]

            colony.units.clear()
            captor.units.clear()

            # Create a thrall (laboring_for >= 0, wage_ratio == 0)
            mx, my, mz = colony.maw.position
            unit = SandKing(colony.colony_id, (mx + 1, my, mz), UnitType.WORKER)
            unit.laboring_for = captor.colony_id
            unit.defiance = 0.0
            assert getattr(unit, 'wage_ratio', W_BRUTE) == 0.0
            colony.units.append(unit)

            # No wage contracts
            assert len(sim._wage_contracts()) == 0

            captor.maw.position = (mx + 10, my + 10, mz)  # far away

            initial_defiance = unit.defiance
            sim._subjugation_tick()

            # Thrall should be processed (defiance rises when unguarded)
            assert unit.defiance > initial_defiance, "Thrall defiance should rise when unguarded"
        finally:
            sandkings_module.WAGE_ENABLED = original_wage_enabled


class TestWagesPersistence(unittest.TestCase):
    """WGA-10: Persistence & inertness - wage_ratio pickles, EnhancedSim unchanged."""

    def test_wage_ratio_pickles(self):
        """wage_ratio field pickles and unpickles correctly."""
        import pickle

        unit = SandKing(0, (1, 1, 1), UnitType.WORKER)
        unit.wage_ratio = 0.25

        pickled = pickle.dumps(unit)
        unpickled = pickle.loads(pickled)

        assert unpickled.wage_ratio == 0.25, "wage_ratio should pickle"

    def test_wage_contracts_lazy_accessor(self):
        """_wage_contracts() lazy accessor works like _house_grains()."""
        sim = make_sim()
        assert not hasattr(sim, 'wage_contracts') or sim.wage_contracts == []
        contracts = sim._wage_contracts()
        assert isinstance(contracts, list)

        # Modify via accessor
        contracts.append({'test': True})
        assert len(sim._wage_contracts()) == 1


if __name__ == '__main__':
    unittest.main()
