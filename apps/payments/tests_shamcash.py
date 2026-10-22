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
from apps.payments.models import DepositRequest, PaymentGatewayIntegration, PaymentMethod, ShamCashBillRecord
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


    @patch("requests.post")
    def test_refund_bill_spec(self, mock_post):
        """Test refundBill complies with Article 9 and Section 6.3."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": 2500,
            "succeeded": True,
            "data": {"tranId": 3919468},
            "message": "Success",
        }
        mock_post.return_value = mock_response

        client = ShamCashClient(
            agent_key="LELCNDrzTrEgXtv00OUdVeECa1CEZZiC",
            secret_key="1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg=",
            base_url="https://dev.shamlogix.tech/services",
            mode="sandbox",
        )
        res = client.refund_bill(
            bill_no="BN-123",
            amount=Decimal("10.50"),
            note="Customer requested a return",
            idempotency_key="9a3f8b7c-2e1d-4c5b-a6f7-e8d9c0b1a2f3",
        )
        self.assertEqual(res["tranId"], 3919468)

        # Check call arguments
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        body = call_kwargs["json"]
        self.assertEqual(body["agentKey"], "LELCNDrzTrEgXtv00OUdVeECa1CEZZiC")
        self.assertTrue(body["encData"])

        # Decrypt payload sent to ShamCash and verify keys
        decrypted = client.decrypt_payload(body["encData"])
        self.assertEqual(decrypted["billNo"], "BN-123")
        self.assertEqual(decrypted["amount"], 10.50)
        self.assertEqual(decrypted["note"], "Customer requested a return")
        self.assertEqual(decrypted["idempotencyKey"], "9a3f8b7c-2e1d-4c5b-a6f7-e8d9c0b1a2f3")
        self.assertNotIn("currencyId", decrypted)  # Implicit currency mapping!

    @patch("requests.post")
    def test_get_transactions_spec(self, mock_post):
        """Test getTransactions complies with Section 6.4 & 11 (limit and cursor)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": 2500,
            "succeeded": True,
            "data": {
                "hasMore": False,
                "lastReturnedTranId": 3919445,
                "list": [
                    {"billNo": "Test-123", "amount": 5000.0, "currencyId": 2, "tranId": 3827711, "tranTypeId": 1, "tranType": "payment"}
                ]
            },
            "message": "Success",
        }
        mock_post.return_value = mock_response

        client = ShamCashClient(
            agent_key="LELCNDrzTrEgXtv00OUdVeECa1CEZZiC",
            secret_key="1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg=",
            base_url="https://dev.shamlogix.tech/services",
            mode="sandbox",
        )
        res = client.get_transactions(from_date="2026-05-01", to_date="2026-06-01", after_tran_id=0, limit=500)
        self.assertFalse(res["hasMore"])
        self.assertEqual(res["lastReturnedTranId"], 3919445)
        self.assertEqual(len(res["list"]), 1)

        # Decrypt sent payload
        call_kwargs = mock_post.call_args[1]
        decrypted = client.decrypt_payload(call_kwargs["json"]["encData"])
        self.assertEqual(decrypted["afterTranId"], 0)
        self.assertEqual(decrypted["limit"], 500)
        self.assertNotIn("pageSize", decrypted)  # Must be 'limit', not 'pageSize'!

    @patch("requests.post")
    def test_create_bill_1704_graceful_handling(self, mock_post):
        """Test Section 10 Recommendation: 1704 (Bill No Already Exists) intercepted gracefully."""
        # First call returns 1704
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {"result": 1704, "message": "Bill No Already Exists", "data": None}

        # Second call to getBillInfo returns existing bill
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "result": 2500,
            "succeeded": True,
            "data": {
                "billNo": "BN-DUPLICATE",
                "paymentUrl": "https://shamcash.example/pay/existing",
                "statusId": 1,
            },
        }
        mock_post.side_effect = [resp1, resp2]

        client = ShamCashClient(
            agent_key="LELCNDrzTrEgXtv00OUdVeECa1CEZZiC",
            secret_key="1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg=",
            base_url="https://dev.shamlogix.tech/services",
            mode="sandbox",
        )
        res = client.create_bill(
            bill_no="BN-DUPLICATE",
            amount=Decimal("15.00"),
            currency_id=ShamCashClient.CURRENCY_USD,
            callback_url="https://example.com/callback",
            redirect_url="https://example.com/redirect",
        )
        self.assertEqual(res["billNo"], "BN-DUPLICATE")
        self.assertEqual(res["paymentUrl"], "https://shamcash.example/pay/existing")


class ShamCashAuditAndPortalTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_superuser(
            username="admin_test",
            email="admin_test@example.com",
            password="AdminPassword123!",
        )
        self.auditor = User.objects.create_user(
            username="shamcash_auditor_user",
            email="auditor_test@shamcash.sy",
            password="AuditorPass123!",
            role="shamcash_auditor",
        )
        self.regular_user = User.objects.create_user(
            username="regular_customer",
            email="customer_test@example.com",
            password="CustomerPass123!",
            role="customer",
        )
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

    def test_auditor_portal_access(self):
        from apps.payments.views_shamcash_admin import shamcash_auditor_portal_view

        # 1. Auditor can access
        req_auditor = self.factory.get(reverse("shamcash_auditor_portal"))
        req_auditor.user = self.auditor
        res_auditor = shamcash_auditor_portal_view(req_auditor)
        self.assertEqual(res_auditor.status_code, 200)

        # 2. Admin can access
        req_admin = self.factory.get(reverse("shamcash_auditor_portal"))
        req_admin.user = self.admin
        res_admin = shamcash_auditor_portal_view(req_admin)
        self.assertEqual(res_admin.status_code, 200)

        # 3. Regular customer is redirected
        req_customer = self.factory.get(reverse("shamcash_auditor_portal"))
        req_customer.user = self.regular_user
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req_customer, "session", {})
        setattr(req_customer, "_messages", FallbackStorage(req_customer))
        res_customer = shamcash_auditor_portal_view(req_customer)
        self.assertEqual(res_customer.status_code, 302)

    def test_5_year_log_retention(self):
        """Test API log is recorded in ShamCashApiLog."""
        from apps.payments.models import ShamCashApiLog

        client = ShamCashClient(
            agent_key="LELCNDrzTrEgXtv00OUdVeECa1CEZZiC",
            secret_key="1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg=",
            base_url="https://dev.shamlogix.tech/services",
            mode="sandbox",
        )

        with patch("requests.post") as mock_post:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "result": 2500,
                "data": {"statusId": 4, "tranId": 555666},
                "message": "Success",
            }
            mock_post.return_value = mock_res

            client.get_bill_info("LOG-TEST-001")

            log_entry = ShamCashApiLog.objects.filter(bill_no="LOG-TEST-001").first()
            self.assertIsNotNone(log_entry)
            self.assertEqual(log_entry.response_result_code, 2500)
            self.assertTrue(log_entry.is_success)

    def test_admin_dashboard_and_bills_views(self):
        from apps.payments.views_shamcash_admin import (
            shamcash_dashboard_view,
            shamcash_bills_list_view,
            shamcash_bill_detail_view,
            shamcash_compliance_dossier_view,
        )
        from apps.payments.models import ShamCashBillRecord

        bill = ShamCashBillRecord.objects.create(
            bill_no="BN-ADMIN-VIEW-TEST",
            bill_type="order",
            user=self.admin,
            amount=Decimal("100.00"),
            currency_id=1,
            currency_code="USD",
            status_id=4,
            status_name="paid",
            tran_id=12345678,
        )

        # Dashboard
        req_dash = self.factory.get(reverse("shamcash_dashboard"))
        req_dash.user = self.admin
        res_dash = shamcash_dashboard_view(req_dash)
        self.assertEqual(res_dash.status_code, 200)

        # Bills list
        req_list = self.factory.get(reverse("shamcash_bills"))
        req_list.user = self.admin
        res_list = shamcash_bills_list_view(req_list)
        self.assertEqual(res_list.status_code, 200)

        # Bill detail
        req_detail = self.factory.get(reverse("shamcash_bill_detail", kwargs={"bill_no": bill.bill_no}))
        req_detail.user = self.admin
        res_detail = shamcash_bill_detail_view(req_detail, bill_no=bill.bill_no)
        self.assertEqual(res_detail.status_code, 200)

        # Compliance dossier
        req_kyc = self.factory.get(reverse("shamcash_compliance_dossier"))
        req_kyc.user = self.admin
        res_kyc = shamcash_compliance_dossier_view(req_kyc)
        self.assertEqual(res_kyc.status_code, 200)

    def test_create_auditor_account_endpoint(self):
        from apps.payments.views_shamcash_admin import shamcash_create_auditor_view
        from django.contrib.messages.storage.fallback import FallbackStorage

        req = self.factory.post(
            reverse("shamcash_create_auditor"),
            data={"email": "new.auditor@shamcash.sy", "password": "NewSecretPass2026!"},
        )
        req.user = self.admin
        setattr(req, "session", {})
        setattr(req, "_messages", FallbackStorage(req))

        res = shamcash_create_auditor_view(req)
        self.assertEqual(res.status_code, 200)
        res_json = json.loads(res.content)
        self.assertTrue(res_json["ok"])

        # Verify user was created in DB
        created_user = User.objects.filter(email="new.auditor@shamcash.sy").first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.role, "shamcash_auditor")
        self.assertTrue(created_user.check_password("NewSecretPass2026!"))

    @patch("requests.post")
    def test_direct_order_creation_with_zero_wallet_balance(self, mock_post):
        """
        Verify direct purchase flow from ShamCash without requiring wallet deposit.
        Customer with 0.00 balance purchases directly, order is created in PENDING status,
        ShamCash bill is generated, and on webhook payment confirmation the order is fulfilled
        without touching user wallet.
        """
        from apps.orders.services import create_pending_gateway_order
        from apps.payments.gateways import ShamCashGateway
        from apps.wallets.services import get_or_create_wallet

        customer = self.regular_user
        wallet = get_or_create_wallet(customer)
        wallet.available_balance = Decimal("0.00")
        wallet.save(update_fields=["available_balance"])
        self.assertEqual(wallet.available_balance, Decimal("0.00"))

        # Setup product & variant
        category = Category.objects.create(name="Digital Products Direct")
        product = Product.objects.create(name="Sham Direct Gift Card", category=category, is_active=True)
        variant = ProductVariant.objects.create(
            product=product,
            name="25 USD Card",
            sku="SKU-SHAM-DIRECT-25",
            price=Decimal("25.00"),
            cost=Decimal("20.00"),
            delivery_type="keys",
            is_active=True,
        )
        ProductKey.objects.create(variant=variant, key_code="SHAM-DIRECT-CODE-12345", is_used=False)

        # Create pending gateway order (bypasses wallet deduction)
        order = create_pending_gateway_order(
            customer=customer,
            variant_id=variant.id,
            quantity=1,
            gateway_code="sham_cash",
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_balance, Decimal("0.00"))  # Wallet untouched!

        # Generate ShamCash Payment Bill
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": 2500,
            "message": "Bill created successfully",
            "data": {
                "billNo": f"ORD-{order.number}-TEST",
                "paymentUrl": "https://dev.shamlogix.tech/services/payment/ORD-TEST-123",
            },
        }
        mock_post.return_value = mock_response

        gw = ShamCashGateway(self.integration)
        gw_res = gw.create_order_payment(order)

        self.assertTrue(bool(gw_res.get("url")))
        self.assertIn("payment/ORD-TEST-123", gw_res["url"])

        # Check immutable bill record created
        bill_record = ShamCashBillRecord.objects.filter(order=order).first()
        self.assertIsNotNone(bill_record)
        self.assertEqual(bill_record.bill_type, ShamCashBillRecord.BillType.ORDER)
        self.assertEqual(bill_record.amount, Decimal("25.00"))
        self.assertEqual(bill_record.currency_id, ShamCashClient.CURRENCY_USD)

        # Simulate ShamCash Webhook (Customer pays bill via ShamCash)
        client_helper = ShamCashClient.from_integration(self.integration)
        payload = {
            "billNo": bill_record.bill_no,
            "tranId": 554433,
            "statusId": ShamCashClient.STATUS_PAID,
        }
        token = client_helper.encrypt_payload(payload)

        request = self.factory.post(
            reverse("shamcash_callback"),
            data=json.dumps({"encData": token}),
            content_type="application/json",
        )
        response = shamcash_callback_view(request)
        self.assertEqual(response.status_code, 200)

        # Verify order is fulfilled and customer wallet remains untouched
        order.refresh_from_db()
        self.assertIn(order.status, (Order.Status.PROCESSING, Order.Status.COMPLETED))
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_balance, Decimal("0.00"))  # Still 0.00!
