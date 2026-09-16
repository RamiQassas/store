# -*- coding: utf-8 -*-
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from apps.common.models import Currency
from apps.payments.models import DepositRequest, PaymentGatewayIntegration, PaymentMethod
from apps.payments.paymera import PaymeraClient, PaymeraError
from apps.payments.views_paymera import paymera_callback_view, paymera_trigger_view
from apps.wallets.services import get_or_create_wallet

User = get_user_model()


class PaymeraClientTestCase(TestCase):
    def setUp(self):
        self.client = PaymeraClient(
            api_key="test_api_key_123",
            terminal_id="99990001",
            base_url="https://egate-t.paymera.cc",
            mode="sandbox"
        )

    def test_basic_auth_header(self):
        headers = self.client._get_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(headers["Content-Type"], "application/json")

    @patch("requests.post")
    def test_create_payment_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ErrorMessage": "Success",
            "ErrorCode": 0,
            "Data": {
                "url": "http://egate-t.paymera.cc/start/test-uuid-1234/ar",
                "paymentId": "test-uuid-1234"
            }
        }
        mock_post.return_value = mock_response

        res = self.client.create_payment(
            amount=1860000,
            callback_url="https://example.com/callback/",
            trigger_url="https://example.com/trigger/",
            lang="ar",
            notes="Test Note"
        )

        self.assertEqual(res["payment_id"], "test-uuid-1234")
        self.assertEqual(res["url"], "http://egate-t.paymera.cc/start/test-uuid-1234/ar")

        called_payload = mock_post.call_args[1]["json"]
        self.assertEqual(called_payload["amount"], 1860000)
        self.assertEqual(called_payload["terminalId"], "99990001")
        self.assertEqual(called_payload["lang"], "ar")

    @patch("requests.post")
    def test_create_payment_api_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ErrorMessage": "Invalid terminal",
            "ErrorCode": 100,
        }
        mock_post.return_value = mock_response

        with self.assertRaises(PaymeraError) as ctx:
            self.client.create_payment(
                amount=50000,
                callback_url="https://example.com/callback/",
                trigger_url="https://example.com/trigger/"
            )
        self.assertEqual(ctx.exception.error_code, 100)

    @patch("requests.get")
    def test_get_payment_status(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ErrorMessage": "Success",
            "ErrorCode": 0,
            "Data": {
                "status": "A",
                "creationTimestamp": "2026-09-09 12:00:00",
                "rrn": "000009876543",
                "amount": 1860000,
                "terminalId": "99990001",
                "notes": "Test"
            }
        }
        mock_get.return_value = mock_response

        status_data = self.client.get_payment_status("test-uuid-1234")
        self.assertEqual(status_data["status"], "A")
        self.assertEqual(status_data["rrn"], "000009876543")


class PaymeraViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="paymera_tester",
            email="tester@example.com",
            password="Password123!"
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="SYP",
            defaults={"name": "Syrian Pound", "symbol": "LS", "buy_rate": Decimal("1.0"), "sell_rate": Decimal("1.0"), "is_active": True}
        )
        self.wallet = get_or_create_wallet(self.user)
        self.wallet.currency = self.currency
        self.wallet.available_balance = Decimal("0.00")
        self.wallet.save()

        self.integration = PaymentGatewayIntegration.objects.create(
            name="Paymera Test",
            provider=PaymentGatewayIntegration.Provider.PAYMERA,
            mode=PaymentGatewayIntegration.Mode.SANDBOX,
            terminal_id="99990001",
            api_key="key_abc123",
            base_url="https://egate-t.paymera.cc",
            is_active=True,
            can_deposit=True
        )

        self.method = PaymentMethod.objects.create(
            name="بطاقة مصرفية عبر بيميرا",
            method_type="بوابة دفع إلكترونية",
            gateway=self.integration,
            is_active=True,
            can_deposit=True
        )
        self.method.supported_currencies.add(self.currency)

        self.deposit = DepositRequest.objects.create(
            user=self.user,
            payment_method=self.method,
            currency=self.currency,
            amount=Decimal("150000"),
            wallet_amount=Decimal("150000"),
            final_amount=Decimal("150000"),
            status=DepositRequest.Status.PENDING,
            gateway_payment_id="pay_uuid_test"
        )

    @patch("apps.payments.views_paymera.notify_user")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_trigger_accepted(self, mock_status, mock_notify):
        mock_status.return_value = {
            "status": "A",
            "rrn": "RRN-998877",
            "amount": 150000,
            "raw": {"ErrorCode": 0}
        }

        request = self.factory.get(f"/payments/paymera/trigger/?deposit_id={self.deposit.id}")
        response = paymera_trigger_view(request)

        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.content)
        self.assertEqual(res_data["status"], "ok")

        # Verify DB state
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.status, DepositRequest.Status.COMPLETED)
        self.assertEqual(self.deposit.transaction_id, "RRN-998877")

        # Verify wallet credited
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("150000"))

        # Verify idempotency (calling again does not double-credit)
        response2 = paymera_trigger_view(request)
        self.assertEqual(response2.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("150000"))

    @patch("apps.payments.views_paymera.notify_user")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_trigger_failed(self, mock_status, mock_notify):
        mock_status.return_value = {
            "status": "F",
            "rrn": None,
            "amount": 150000,
            "raw": {"ErrorCode": 0}
        }

        request = self.factory.get(f"/payments/paymera/trigger/?deposit_id={self.deposit.id}")
        response = paymera_trigger_view(request)

        self.assertEqual(response.status_code, 200)
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.status, DepositRequest.Status.REJECTED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("0.00"))

    @patch("apps.notifications.services.notify_staff")
    @patch("apps.notifications.services.notify_user")
    @patch("apps.payments.views_paymera.finalize_paid_gateway_order")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_direct_order_trigger_accepted(self, mock_status, mock_finalize, mock_notify_user, mock_notify_staff):
        from apps.catalog.models import Category, Product, ProductVariant, ProductKey
        from apps.orders.models import Order, Invoice
        from apps.orders.services import create_pending_gateway_order, finalize_paid_gateway_order
        from apps.payments.gateways import gateway_for

        cat = Category.objects.create(name="Gaming Cards")
        prod = Product.objects.create(category=cat, name="PUBG UC", is_active=True)
        var = ProductVariant.objects.create(
            product=prod,
            name="60 UC",
            sku="UC-60",
            price=Decimal("1.00"),
            cost=Decimal("0.80"),
            delivery_type="keys",
            is_active=True,
            metadata={"qty_type": "fixed", "qty_min": 1, "qty_max": 1}
        )
        ProductKey.objects.create(variant=var, key_code="PUBG-KEY-123", is_used=False)

        # 1. Create Pending Order
        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            gateway_code="paymera",
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.metadata.get("payment_gateway"), "paymera")

        # 2. Mock create payment
        gw = gateway_for("paymera")
        with patch.object(PaymeraClient, "create_payment", return_value={"payment_id": "ord-pay-99", "url": "https://egate.paymera.cc/start/99"}):
            res = gw.create_order_payment(order)
            self.assertEqual(res["payment_id"], "ord-pay-99")
            order.refresh_from_db()
            self.assertEqual(order.metadata["gateway_payment_id"], "ord-pay-99")

        # 3. Trigger view
        mock_status.return_value = {
            "status": "A",
            "rrn": "RRN-ORDER-5544",
            "amount": 15000,
            "raw": {"ErrorCode": 0}
        }
        # Let mock_finalize call the real finalize_paid_gateway_order
        mock_finalize.side_effect = finalize_paid_gateway_order

        request = self.factory.get(f"/payments/paymera/trigger/?order_id={order.id}")
        response = paymera_trigger_view(request)
        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIn("keys", order.fulfillment_data)
        self.assertEqual(order.fulfillment_data["keys"], ["PUBG-KEY-123"])
        self.assertTrue(Invoice.objects.filter(order=order).exists())

    @patch("apps.notifications.services.notify_staff")
    @patch("apps.notifications.services.notify_user")
    @patch("services.provider.manager.ProviderManager.place_order")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_api_product_trigger_accepted(self, mock_status, mock_place_order, mock_notify_user, mock_notify_staff):
        from apps.catalog.models import Category, Product, ProductVariant
        from apps.orders.models import Order
        from apps.orders.services import create_pending_gateway_order, finalize_paid_gateway_order
        from apps.providers.models import ProviderProfile, ProviderProduct

        profile = ProviderProfile.objects.create(
            provider_name="Alkasr",
            base_url="https://api.alkasr-vip.com/client/api",
            api_token="test-token",
            is_active=True
        )
        prov_prod = ProviderProduct.objects.create(
            profile=profile,
            remote_id="998877",
            name="PUBG 60 UC API",
            cost_price=Decimal("0.85"),
            product_type="package",
            is_active=True
        )

        cat = Category.objects.create(name="Topup Games")
        prod = Product.objects.create(category=cat, name="PUBG Direct", is_active=True, is_api_product=True, api_provider="alkasr")
        var = ProductVariant.objects.create(
            product=prod,
            name="60 UC",
            sku="UC-API-60",
            price=Decimal("1.10"),
            cost=Decimal("0.85"),
            is_active=True,
            api_product_id="998877",
            metadata={"qty_type": "fixed", "qty_min": 1, "qty_max": 1}
        )

        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            gateway_code="paymera",
            metadata={"player_id": "5123456789"}
        )
        order.metadata["gateway_payment_id"] = "ord-api-pay-99"
        order.save(update_fields=["metadata"])
        self.assertEqual(order.status, Order.Status.PENDING)

        mock_status.return_value = {
            "status": "A",
            "rrn": "RRN-API-7788",
            "amount": 16000,
            "raw": {"ErrorCode": 0}
        }
        mock_place_order.return_value = {
            "status": "accept",
            "remote_order_id": "ALKASR-ORD-4455",
            "raw_response": {"order_id": "ALKASR-ORD-4455", "msg": "عملية التحويل تمت بنجاح"}
        }

        request = self.factory.get(f"/payments/paymera/trigger/?order_id={order.id}")
        response = paymera_trigger_view(request)
        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.api_order_id, "ALKASR-ORD-4455")
        mock_place_order.assert_called_once()
        formatted = order.formatted_metadata()
        self.assertTrue(any(item["label"] == "player_id" and item["value"] == "5123456789" for item in formatted))
        self.assertFalse(any(item["label"] in ("payment_gateway", "gateway_payment_id") for item in formatted))

    @patch("apps.notifications.services.notify_staff")
    @patch("apps.notifications.services.notify_user")
    @patch("services.provider.manager.ProviderManager.place_order")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_substore_api_order_fulfillment(self, mock_status, mock_place_order, mock_notify_user, mock_notify_staff):
        from apps.catalog.models import Category, Product, ProductVariant
        from apps.orders.models import Order
        from apps.orders.services import create_pending_gateway_order
        from apps.providers.models import ProviderProfile, ProviderProduct, ProviderMapping
        from apps.stores.models import Store, SubscriptionPlan
        from apps.common.tenant_utils import set_current_store

        # 1. Setup Store
        plan = SubscriptionPlan.objects.create(name="Pro Plan", price_monthly=Decimal("20.00"))
        store = Store.objects.create(
            owner=self.user,
            name="Gamer Shop",
            subdomain="gamershop",
            subscription_plan=plan,
            is_active=True
        )

        # 2. Setup Global Provider
        profile = ProviderProfile.objects.create(
            provider_name="Alkasr",
            base_url="https://api.alkasr-vip.com/client/api",
            api_token="token-substore-test",
            is_active=True
        )
        prov_prod = ProviderProduct.objects.create(
            profile=profile,
            remote_id="888111",
            name="FreeFire 100 Diamonds",
            cost_price=Decimal("0.90"),
            product_type="package",
            is_active=True
        )

        # 3. Setup Sub-store product & variant (mapped to provider)
        cat = Category.objects.create(name="FreeFire", store=store)
        prod = Product.objects.create(category=cat, store=store, name="FF Diamonds", is_active=True)
        var = ProductVariant.objects.create(
            product=prod,
            name="100 Diamonds",
            sku="PRV-888111",
            price=Decimal("1.25"),
            cost=Decimal("0.90"),
            is_active=True,
            metadata={"qty_type": "fixed", "qty_min": 1, "qty_max": 1, "remote_id": "888111"}
        )
        ProviderMapping.objects.create(local_variant=var, provider_product=prov_prod)

        # 4. Create pending order on sub-store
        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            fulfillment_data={"player_id": "999888777"},
            gateway_code="paymera",
            metadata={"player_id": "999888777"}
        )
        order.metadata["gateway_payment_id"] = "substore-pay-123"
        order.save(update_fields=["metadata"])
        self.assertEqual(order.store, store)
        self.assertEqual(order.status, Order.Status.PENDING)

        # 5. Simulate Paymera Webhook arriving at sub-store context
        mock_status.return_value = {
            "status": "A",
            "rrn": "RRN-SUBSTORE-999",
            "amount": 18000,
            "raw": {"ErrorCode": 0}
        }
        mock_place_order.return_value = {
            "status": "accept",
            "remote_order_id": "ALKASR-SUB-1010",
            "raw_response": {"order_id": "ALKASR-SUB-1010"}
        }

        # Set tenant in thread-local storage as TenantMiddleware would
        set_current_store(store)
        try:
            request = self.factory.get(f"/payments/paymera/trigger/?order_id={order.id}")
            request.store = store
            response = paymera_trigger_view(request)
            self.assertEqual(response.status_code, 200)

            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.COMPLETED)
            self.assertEqual(order.api_order_id, "ALKASR-SUB-1010")
            mock_place_order.assert_called_once()
        finally:
            set_current_store(None)

    @patch("apps.payments.views_paymera.finalize_paid_gateway_order")
    def test_paymera_callback_url_cancelled_marks_order_cancelled(self, mock_finalize):
        """Test that user clicking cancel or returning with status=cancel immediately cancels the order."""
        from apps.catalog.models import Category, Product, ProductVariant
        from apps.orders.models import Order
        from apps.orders.services import create_pending_gateway_order
        from django.contrib.messages.storage.cookie import CookieStorage

        cat = Category.objects.create(name="Cards")
        prod = Product.objects.create(category=cat, name="Gift Card", is_active=True)
        var = ProductVariant.objects.create(
            product=prod, name="10 USD", sku="GC-10", price=Decimal("10.00"), cost=Decimal("8.00"), is_active=True
        )
        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            gateway_code="paymera",
        )
        order.metadata["gateway_payment_id"] = "pay-canc-1"
        order.save(update_fields=["metadata"])

        request = self.factory.get(f"/payments/paymera/callback/?order_id={order.id}&status=cancel")
        request.user = self.user
        setattr(request, "_messages", CookieStorage(request))
        response = paymera_callback_view(request)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        mock_finalize.assert_not_called()

    @patch("apps.payments.views_paymera.finalize_paid_gateway_order")
    @patch.object(PaymeraClient, "get_payment_status")
    def test_paymera_callback_api_cancelled_marks_order_cancelled(self, mock_status, mock_finalize):
        """Test that Paymera API returning status='C' immediately cancels the order."""
        from apps.catalog.models import Category, Product, ProductVariant
        from apps.orders.models import Order
        from apps.orders.services import create_pending_gateway_order
        from django.contrib.messages.storage.cookie import CookieStorage

        cat = Category.objects.create(name="Cards2")
        prod = Product.objects.create(category=cat, name="Gift Card 2", is_active=True)
        var = ProductVariant.objects.create(
            product=prod, name="20 USD", sku="GC-20", price=Decimal("20.00"), cost=Decimal("18.00"), is_active=True
        )
        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            gateway_code="paymera",
        )
        order.metadata["gateway_payment_id"] = "pay-canc-2"
        order.save(update_fields=["metadata"])

        mock_status.return_value = {
            "status": "C",
            "amount": 20000,
            "raw": {"ErrorCode": 0}
        }

        request = self.factory.get(f"/payments/paymera/callback/?order_id={order.id}")
        request.user = self.user
        setattr(request, "_messages", CookieStorage(request))
        response = paymera_callback_view(request)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        mock_finalize.assert_not_called()

    def test_finalize_paid_gateway_order_rejects_non_accepted_status(self):
        """Test defensive security: finalize_paid_gateway_order refuses to fulfill if status is not 'A'."""
        from apps.catalog.models import Category, Product, ProductVariant, ProductKey
        from apps.orders.models import Order
        from apps.orders.services import create_pending_gateway_order, finalize_paid_gateway_order

        cat = Category.objects.create(name="Security Cat")
        prod = Product.objects.create(category=cat, name="Security Product", is_active=True)
        var = ProductVariant.objects.create(
            product=prod, name="Security Var", sku="SEC-1", price=Decimal("5.00"), cost=Decimal("4.00"), delivery_type="keys", is_active=True
        )
        ProductKey.objects.create(variant=var, key_code="SHOULD-NOT-BE-DELIVERED", is_used=False)

        order = create_pending_gateway_order(
            customer=self.user,
            variant_id=var.id,
            quantity=1,
            gateway_code="paymera",
        )

        # Calling finalize with None or non-A status
        res1 = finalize_paid_gateway_order(order, None)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertNotIn("keys", order.fulfillment_data or {})

        res2 = finalize_paid_gateway_order(order, {"status": "C"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertNotIn("keys", order.fulfillment_data or {})



