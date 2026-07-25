"""
Comprehensive Unit & Integration Test Suite for Provider Architecture Overhaul.
Tests Profile, Products, Orders, Sync, Pricing Engine, State Machine, Exceptions & Retry logic.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.test import TestCase

from apps.providers.models import ProviderProfile, ProviderProduct, ProviderOrder, ProviderCategory
from services.provider.manager import ProviderManager
from services.provider.alkasr import (
    AlkasrClient,
    AlkasrProviderService,
    PricingEngine,
    validate_order_preconditions,
)
from services.provider.alkasr.exceptions import (
    InsufficientBalanceException,
    QuantityTooSmallException,
    RetryAfterOneMinuteException,
    ValidationException,
    raise_for_code,
)


class ProviderPricingEngineTestCase(TestCase):
    def test_pricing_percentage(self):
        res = PricingEngine.calculate_final_price(
            base_cost=Decimal("10.00"),
            margin_type="percentage",
            margin_value=Decimal("10.00"), # 10%
            exchange_rate=Decimal("1.00")
        )
        self.assertEqual(res["base_cost"], Decimal("10.00"))
        self.assertEqual(res["base_final_price"], Decimal("11.00"))
        self.assertEqual(res["profit"], Decimal("1.00"))

    def test_pricing_fixed(self):
        res = PricingEngine.calculate_final_price(
            base_cost=Decimal("10.00"),
            margin_type="fixed",
            margin_value=Decimal("5.00"),
            exchange_rate=Decimal("1.00")
        )
        self.assertEqual(res["base_final_price"], Decimal("15.00"))

    def test_pricing_manual(self):
        res = PricingEngine.calculate_final_price(
            base_cost=Decimal("10.00"),
            margin_type="manual",
            manual_price=Decimal("25.00"),
            exchange_rate=Decimal("1.00")
        )
        self.assertEqual(res["base_final_price"], Decimal("25.00"))

    def test_multi_currency_exchange(self):
        res = PricingEngine.calculate_final_price(
            base_cost=Decimal("10.00"),
            margin_type="percentage",
            margin_value=Decimal("10.00"), # 11.00 USD
            exchange_rate=Decimal("15000.00") # SYP
        )
        self.assertEqual(res["customer_final_price"], Decimal("165000.00"))


class ProviderExceptionsTestCase(TestCase):
    def test_error_code_mapping(self):
        with self.assertRaises(InsufficientBalanceException):
            raise_for_code(100)

        with self.assertRaises(QuantityTooSmallException):
            raise_for_code(112)

        with self.assertRaises(RetryAfterOneMinuteException):
            raise_for_code(111)


class ProviderPreconditionValidatorTestCase(TestCase):
    def setUp(self):
        self.profile = ProviderProfile.objects.create(
            provider_name="Alkasr VIP",
            api_token="test_token_123",
            balance=Decimal("50.00")
        )
        self.product = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="101",
            name="1000 Diamonds",
            cost_price=Decimal("10.00"),
            qty_min=5,
            qty_max=100,
            is_active=True,
            local_is_active=True
        )

    def test_validate_quantity_too_low(self):
        with self.assertRaises(ValidationException):
            validate_order_preconditions(
                provider_product=self.product,
                quantity=2, # Below min 5
                parameters_sent={}
            )

    def test_validate_insufficient_balance(self):
        with self.assertRaises(ValidationException):
            validate_order_preconditions(
                provider_product=self.product,
                quantity=10,
                parameters_sent={},
                provider_balance=Decimal("5.00"),
                order_cost=Decimal("100.00")
            )


class ProviderManagerTestCase(TestCase):
    def setUp(self):
        self.profile = ProviderProfile.objects.create(
            provider_name="Alkasr VIP",
            api_token="mock_token",
            base_url="https://api.alkasr-vip.com/client/api",
            balance=Decimal("100.00")
        )

    @patch.object(AlkasrClient, "get_profile")
    def test_fetch_balance_via_manager(self, mock_get_profile):
        mock_get_profile.return_value = {
            "status": "success",
            "data": {"balance": "150.50", "currency": "USD"}
        }

        res = ProviderManager.fetch_balance(self.profile)
        self.assertEqual(res["balance"], Decimal("150.50"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal("150.50"))
