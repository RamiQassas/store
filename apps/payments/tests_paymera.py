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
