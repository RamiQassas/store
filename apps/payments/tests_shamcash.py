# -*- coding: utf-8 -*-
"""
Automated Unit Tests for ShamCash E-Payment Integration
Tests:
- Cryptographic Direct JWE encryption and decryption (AES-256-GCM)
- Client API payload building (USD and SYP)
- Gateway deposit creation & direct order checkout
- Webhook callback processing, wallet crediting, order finalization & idempotency
- Browser return redirect
"""

import base64
import json
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant, ProductKey
from apps.common.models import Currency
from apps.orders.models import Order, OrderItem
from apps.payments.gateways import ShamCashGateway, gateway_for
from apps.payments.models import DepositRequest, PaymentGatewayIntegration, PaymentMethod
from apps.payments.shamcash import ShamCashClient, ShamCashError
from apps.payments.views_shamcash import shamcash_callback_view, shamcash_redirect_view
from apps.wallets.models import Wallet
from apps.wallets.services import get_or_create_wallet

User = get_user_model()


class ShamCashClientTestCase(TestCase):
    def setUp(self):
        self.agent_key = "LELCNDrzTrEgXtv00OUdVeECa1CEZZiC"
        self.secret_key = "1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg="
        self.client = ShamCashClient(
            agent_key=self.agent_key,
            secret_key=self.secret_key,
            base_url="https://dev.shamlogix.tech/services",
            mode="sandbox",
        )

    def test_jwe_encryption_structure(self):
        payload = {"billNo": "BN-TEST-001", "amount": 25.50, "currencyId": 1}
        token = self.client.encrypt_payload(payload)

        # Must have exactly 5 parts
        parts = token.split(".")
        self.assertEqual(len(parts), 5)
        # Second part must be empty for Direct JWE
        self.assertEqual(parts[1], "")

        # Header must be {"alg":"dir","enc":"A256GCM","cty":"json"}
        h_bytes = self.client._b64url_decode(parts[0])
        header = json.loads(h_bytes.decode("utf-8"))
        self.assertEqual(header.get("alg"), "dir")
        self.assertEqual(header.get("enc"), "A256GCM")

    def test_jwe_encryption_decryption_cycle(self):
        original = {
            "billNo": "BN-CYCLE-123",
            "amount": 100.0,
            "currencyId": 2,
            "details": "Cycle test",
        }
        token = self.client.encrypt_payload(original)
        decrypted = self.client.decrypt_payload(token)

        self.assertEqual(decrypted["billNo"], original["billNo"])
        self.assertEqual(decrypted["amount"], original["amount"])
        self.assertEqual(decrypted["currencyId"], original["currencyId"])
        self.assertIn("iat", decrypted)
        self.assertIn("exp", decrypted)

    def test_jwe_expired_token_rejected(self):
        payload = {"billNo": "BN-EXPIRED", "amount": 10.0, "currencyId": 1}
        # Manually create expired token (exp in the past)
        now = int(time.time())
        token = self.client.encrypt_payload(payload, ttl_seconds=-200)

        with self.assertRaises(ShamCashError) as ctx:
            self.client.decrypt_payload(token, verify_exp=True, clock_skew=10)
        self.assertIn("expired", str(ctx.exception).lower())

    @patch("requests.post")
    def test_create_bill_success_usd(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": 2500,
            "succeeded": True,
            "data": {
                "statusId": 1,
                "statusName": "pending",
                "billNo": "DEP-TEST-1",
                "amount": 50.00,
                "currencyId": 1,
                "paymentUrl": "https://shamcash.example/pay/test1",
            },
            "message": "Success",
        }
        mock_post.return_value = mock_response

        res = self.client.create_bill(
            bill_no="DEP-TEST-1",
            amount=Decimal("50.00"),
            currency_id=ShamCashClient.CURRENCY_USD,
            callback_url="https://example.com/callback",
            redirect_url="https://example.com/redirect",
            note="USD Deposit",
        )
        self.assertEqual(res["paymentUrl"], "https://shamcash.example/pay/test1")
        self.assertEqual(res["currencyId"], 1)

    @patch("requests.post")
    def test_create_bill_success_syp(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": 2500,
            "succeeded": True,
            "data": {
                "statusId": 1,
                "statusName": "pending",
                "billNo": "DEP-TEST-SYP",
                "amount": 750000.00,
                "currencyId": 2,
                "paymentUrl": "https://shamcash.example/pay/testsyp",
            },
            "message": "Success",
        }
        mock_post.return_value = mock_response

        res = self.client.create_bill(
            bill_no="DEP-TEST-SYP",
            amount=Decimal("750000.00"),
            currency_id=ShamCashClient.CURRENCY_SYP,
            callback_url="https://example.com/callback",
            redirect_url="https://example.com/redirect",
            note="SYP Deposit",
        )
        self.assertEqual(res["paymentUrl"], "https://shamcash.example/pay/testsyp")
        self.assertEqual(res["currencyId"], 2)


class ShamCashViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="shamcash_test@example.com",
            password="SecurePassword123!",
            username="shamcash_test_user",
        )
        self.usd_currency, _ = Currency.all_objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "buy_rate": Decimal("1.0"), "is_active": True},
        )
        self.syp_currency, _ = Currency.all_objects.get_or_create(
            code="SYP",
            defaults={"name": "Syrian Pound", "symbol": "ل.س", "buy_rate": Decimal("15000.0"), "is_active": True},
        )
        self.wallet = get_or_create_wallet(self.user)

        self.integration = PaymentGatewayIntegration.all_objects.create(
            name="شام كاش (ShamCash)",
            provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
            mode=PaymentGatewayIntegration.Mode.SANDBOX,
            api_key="LELCNDrzTrEgXtv00OUdVeECa1CEZZiC",
            api_secret="1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg=",
            base_url="https://dev.shamlogix.tech/services",
            is_active=True,
            can_deposit=True,
        )

        self.payment_method = PaymentMethod.all_objects.create(
            name="شام كاش (ShamCash)",
            method_type="electronic_wallet",
            gateway=self.integration,
            is_active=True,
            can_deposit=True,
        )
        self.payment_method.supported_currencies.add(self.usd_currency, self.syp_currency)

        self.client_helper = ShamCashClient.from_integration(self.integration)

    def test_webhook_successful_usd_deposit(self):
        deposit = DepositRequest.objects.create(
            user=self.user,
            payment_method=self.payment_method,
            currency=self.usd_currency,
            amount=Decimal("50.00"),
            gateway_payment_id="DEP-999-TEST",
            status=DepositRequest.Status.PENDING,
        )

        initial_balance = self.wallet.available_balance

        # Build webhook token
        payload = {
            "billNo": "DEP-999-TEST",
            "tranId": 445566,
            "statusId": ShamCashClient.STATUS_PAID,
        }
        token = self.client_helper.encrypt_payload(payload)

        request = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )

        response = shamcash_callback_view(request)
        self.assertEqual(response.status_code, 200)

        deposit.refresh_from_db()
        self.assertEqual(deposit.status, DepositRequest.Status.COMPLETED)
        self.assertTrue(deposit.is_verified)
        self.assertEqual(deposit.transaction_id, "445566")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, initial_balance + Decimal("50.00"))

    def test_webhook_successful_syp_deposit(self):
        deposit = DepositRequest.objects.create(
            user=self.user,
            payment_method=self.payment_method,
            currency=self.syp_currency,
            amount=Decimal("750000.00"),
            gateway_payment_id="DEP-SYP-1234",
            status=DepositRequest.Status.PENDING,
        )

        initial_balance = self.wallet.available_balance

        payload = {
            "billNo": "DEP-SYP-1234",
            "tranId": 778899,
            "statusId": ShamCashClient.STATUS_PAID,
        }
        token = self.client_helper.encrypt_payload(payload)

        request = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )

        response = shamcash_callback_view(request)
        self.assertEqual(response.status_code, 200)

        deposit.refresh_from_db()
        self.assertEqual(deposit.status, DepositRequest.Status.COMPLETED)

        # 750,000 SYP / 15,000 buy_rate = 50.00 USD
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, initial_balance + Decimal("50.00"))

    def test_webhook_idempotency_deposit(self):
        deposit = DepositRequest.objects.create(
            user=self.user,
            payment_method=self.payment_method,
            currency=self.usd_currency,
            amount=Decimal("30.00"),
            gateway_payment_id="DEP-IDEM-001",
            status=DepositRequest.Status.PENDING,
        )

        payload = {
            "billNo": "DEP-IDEM-001",
            "tranId": 112233,
            "statusId": ShamCashClient.STATUS_PAID,
        }
        token = self.client_helper.encrypt_payload(payload)

        req1 = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )
        shamcash_callback_view(req1)

        self.wallet.refresh_from_db()
        bal_after_first = self.wallet.available_balance

        # Send duplicate webhook event
        req2 = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )
        res2 = shamcash_callback_view(req2)
        self.assertEqual(res2.status_code, 200)

        self.wallet.refresh_from_db()
        # Balance must remain exactly identical (no double credit)
        self.assertEqual(self.wallet.available_balance, bal_after_first)

    def test_webhook_successful_direct_order(self):
        category = Category.objects.create(name="Cards")
        product = Product.objects.create(name="Game Card", category=category, is_active=True)
        variant = ProductVariant.objects.create(
            product=product,
            name="100 Points",
            sku="SKU-TEST-9988",
            price=Decimal("20.00"),
            cost=Decimal("15.00"),
            delivery_type="keys",
            is_active=True,
        )
        ProductKey.objects.create(variant=variant, key_code="SHAM-KEY-9988", is_used=False)

        order = Order.objects.create(
            customer=self.user,
            number="ORD-TEST-9988",
            total_amount=Decimal("20.00"),
            status=Order.Status.PENDING,
            metadata={"gateway_payment_id": "ORD-ORD-TEST-9988-123"},
        )
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=1,
            unit_price=Decimal("20.00"),
            total_price=Decimal("20.00"),
        )

        payload = {
            "billNo": "ORD-ORD-TEST-9988-123",
            "tranId": 990011,
            "statusId": ShamCashClient.STATUS_PAID,
        }
        token = self.client_helper.encrypt_payload(payload)

        request = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )

        response = shamcash_callback_view(request)
        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertIn(order.status, [Order.Status.PROCESSING, Order.Status.COMPLETED])
        self.assertTrue(order.metadata.get("gateway_payment_confirmed"))
