import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.payments.models import (
    MTNPayApiLog,
    MTNPayInvoiceRecord,
    MTNPayRefundRecord,
    MTNPayTerminalConfig,
)
from apps.payments.mtn_pay import (
    MTN_ERROR_CATALOG,
    MTNCryptoEngine,
    MTNPayError,
    MTNPaymentClient,
)


class MTNPayIntegrationTests(TestCase):
    def setUp(self):
        self.priv_pem, self.pub_b64 = MTNCryptoEngine.generate_rsa1024_keypair()
        self.server_priv_pem, self.server_pub_b64 = MTNCryptoEngine.generate_rsa1024_keypair()

        self.terminal = MTNPayTerminalConfig.objects.create(
            terminal_id="99887766",
            serial_number="SN-TEST-1024",
            language="en",
            public_key_b64=self.pub_b64,
            server_public_key_b64=self.server_pub_b64,
            is_activated=True,
            terminal_settings={
                "Currency": {"Code": "760", "Brief": "SYP", "Fractional": 100},
                "Limits": {"Minimum": 10000, "Maximum": 50000000},
                "Allowed": {"Payment": True},
                "Description": {
                    "Business": "Raqamiyat Digital LLC",
                    "Shop": "Main Flagship Store",
                    "Address": "Damascus, Syria",
                    "Phone": "+963947991951",
                    "UniquePayCode": "RQ-POS-9988",
                },
            },
        )
        MTNCryptoEngine.save_private_key_securely(self.terminal.terminal_id, self.priv_pem)

    def _make_signed_server_response(self, payload: dict, status_code: int = 200):
        resp_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sig = MTNCryptoEngine.sign_payload(resp_bytes, self.server_priv_pem)
        return status_code, {"X-Signature": sig, "Content-Type": "application/json; charset=utf-8"}, resp_bytes

    # ── 1. Cryptographic & X-Signature Verification ──────────────────────────
    def test_rsa1024_sha256_signature_and_verification(self):
        sample_body = b'{"Amount":250000,"Invoice":170000001}'
        sig_b64 = MTNCryptoEngine.sign_payload(sample_body, self.priv_pem)
        self.assertTrue(MTNCryptoEngine.verify_signature(sample_body, sig_b64, self.pub_b64))
        self.assertFalse(MTNCryptoEngine.verify_signature(b'{"Amount":999999}', sig_b64, self.pub_b64))

    # ── 2. POS Activation, 3-Attempt Protection & Financial Units/Limits ─────
    def test_pos_activation_and_financial_constraints(self):
        unactivated = MTNPayTerminalConfig.objects.create(
            terminal_id="11223344",
            serial_number="SN-ACT-01",
            public_key_b64=self.pub_b64,
            server_public_key_b64=self.server_pub_b64,
            is_activated=False,
        )
        MTNCryptoEngine.save_private_key_securely(unactivated.terminal_id, self.priv_pem)

        # Simulate 3 failed activation attempts (300) -> locks terminal (304)
        def fail_transport(req_name, headers, body_bytes):
            self.assertEqual(req_name, "pos_web/pos/activate")
            self.assertEqual(headers["Subject"], "11223344")
            self.assertTrue(MTNCryptoEngine.verify_signature(body_bytes, headers["X-Signature"], self.pub_b64))
            return self._make_signed_server_response({"Errno": 300, "CountAbuse": unactivated.activation_attempts + 1}, 400)

        client_fail = MTNPaymentClient(unactivated, private_key_pem=self.priv_pem, transport=fail_transport)
        for _ in range(3):
            with self.assertRaises(MTNPayError) as ctx:
                client_fail.activate_pos(secret_code="12345678", serial_number="SN-ACT-01")
            self.assertEqual(ctx.exception.errno, 300)

        unactivated.refresh_from_db()
        self.assertTrue(unactivated.is_locked)
        with self.assertRaises(MTNPayError) as lock_ctx:
            client_fail.activate_pos(secret_code="12345678", serial_number="SN-ACT-01")
        self.assertEqual(lock_ctx.exception.errno, 304)

        # Unlock and succeed activation
        unactivated.is_locked = False
        unactivated.activation_attempts = 0
        unactivated.count_abuse = 0
        unactivated.save()

        settings_payload = {
            "Errno": 0,
            "Settings": {
                "Currency": {"Code": "760", "Brief": "SYP", "Fractional": 100},
                "Limits": {"Minimum": 50000, "Maximum": 10000000},
                "Allowed": {"Payment": True},
                "Description": {
                    "Business": "Raqamiyat",
                    "Shop": "Branch 1",
                    "Address": "Syria",
                    "Phone": "0947991951",
                    "UniquePayCode": "UPC-777",
                },
            },
        }
        client_ok = MTNPaymentClient(
            unactivated,
            private_key_pem=self.priv_pem,
            transport=lambda r, h, b: self._make_signed_server_response(settings_payload),
        )
        client_ok.activate_pos(secret_code="87654321", serial_number="SN-ACT-01")
        unactivated.refresh_from_db()
        self.assertTrue(unactivated.is_activated)
        self.assertEqual(client_ok.to_minor_units(Decimal("1500.00")), 150000)

        # Below Minimum (500 SYP -> 50000 minor; test 200 SYP -> 20000 minor)
        with self.assertRaises(MTNPayError):
            client_ok.validate_amount_and_permissions(20000)
        # Above Maximum
        with self.assertRaises(MTNPayError):
            client_ok.validate_amount_and_permissions(99000000)

        # Allowed.Payment == False -> 405
        unactivated.terminal_settings["Allowed"]["Payment"] = False
        with self.assertRaises(MTNPayError) as perm_ctx:
            client_ok.validate_amount_and_permissions(100000)
        self.assertEqual(perm_ctx.exception.errno, 405)

    # ── 3. Full Phone Payment Flow (Create -> Initiate -> Confirm) ───────────
    def test_full_phone_payment_lifecycle(self):
        def router(req_name, headers, body_bytes):
            self.assertTrue(MTNCryptoEngine.verify_signature(body_bytes, headers["X-Signature"], self.pub_b64))
            data = json.loads(body_bytes.decode("utf-8"))
            if req_name == "pos_web/invoice/create":
                self.assertEqual(data["Amount"], 250000)  # 2500 SYP * 100
                return self._make_signed_server_response({
                    "Errno": 0,
                    "Receipt": {
                        "Invoice": data["Invoice"],
                        "Amount": data["Amount"],
                        "QR": "MTNQR://99887766/1",
                        "Status": 1,
                        "Transaction": "TX-INIT-100",
                        "Commission": 500,
                        "Tax": 50,
                        "Created": "2026-11-18T12:00:00",
                        "Expired": "2026-11-18T12:15:00",
                        "Processed": "",
                    },
                })
            if req_name == "pos_web/payment_phone/initiate":
                self.assertTrue(data["Guid"])
                self.assertEqual(data["Phone"], "963947991951")
                return self._make_signed_server_response({
                    "Errno": 0,
                    "OperationNumber": 55443322,
                    "PaySystem": "MTNPay",
                })
            if req_name == "pos_web/payment_phone/confirm":
                self.assertEqual(data["OperationNumber"], 55443322)
                self.assertEqual(data["Code"], "991122")
                return self._make_signed_server_response({
                    "Errno": 0,
                    "Status": 9,
                    "Transaction": "TX-CONFIRMED-999",
                    "Abuse": 2,
                })
            raise AssertionError(f"Unexpected endpoint: {req_name}")

        client = MTNPaymentClient(self.terminal, private_key_pem=self.priv_pem, transport=router)
        inv_rec, _ = client.create_invoice(major_amount=Decimal("2500.00"), invoice_number=2026111801)
        self.assertEqual(inv_rec.amount_minor, 250000)
        self.assertEqual(inv_rec.status_code, 1)

        client.initiate_phone_payment(invoice_number=2026111801, customer_phone="+963 947 991 951")
        inv_rec.refresh_from_db()
        self.assertEqual(inv_rec.operation_number, "55443322")
        self.assertEqual(inv_rec.pay_system, "MTNPay")
        self.assertEqual(inv_rec.status_code, 5)

        paid_rec, _ = client.confirm_phone_payment(invoice_number=2026111801, sms_code="991122")
        self.assertTrue(paid_rec.is_paid)
        self.assertEqual(paid_rec.status_code, 9)
        self.assertEqual(paid_rec.transaction_id, "TX-CONFIRMED-999")
        self.assertEqual(paid_rec.abuse_remaining, 2)

    # ── 4. Full Refund Flow + Same-Day Commission/TaxSender Rule ─────────────
    def test_refund_initiate_confirm_cancel_and_same_day_rule(self):
        inv = MTNPayInvoiceRecord.objects.create(
            terminal=self.terminal,
            invoice_number=3030301,
            amount_major=Decimal("1000.00"),
            amount_minor=100000,
            currency_code="SYP",
            status_code=9,
            transaction_id="TX-3030301",
            processed_remote="2026-11-10T10:00:00",  # Different day from refund!
        )

        def refund_router(req_name, headers, body_bytes):
            data = json.loads(body_bytes.decode("utf-8"))
            if req_name == "pos_web/invoice/refund/initiate":
                return self._make_signed_server_response({
                    "Errno": 0,
                    "BaseInvoice": data["Invoice"],
                    "RefundInvoice": 9090901,
                    "RefundInvoiceDate": "2026-11-18T15:00:00",
                    "RefundAmount": 100000,
                    "Amount": 100000,
                    "Commission": 250,
                    "TaxSender": 25,
                    "Parameters": [{"key": "reason", "val": "customer_request"}],
                })
            if req_name == "pos_web/invoice/refund/confirm":
                self.assertEqual(data["BaseInvoice"], 3030301)
                self.assertEqual(data["RefundInvoice"], 9090901)
                return self._make_signed_server_response({
                    "Errno": 0,
                    "RefundInvoice": 9090901,
                    "Amount": 100000,
                })
            if req_name == "pos_web/invoice/refund/cancel":
                self.assertEqual(data["InvoiceCancelID"], 9090901)
                return self._make_signed_server_response({"Errno": 0})
            raise AssertionError(f"Unexpected endpoint: {req_name}")

        client = MTNPaymentClient(self.terminal, private_key_pem=self.priv_pem, transport=refund_router)
        ref_rec, _ = client.initiate_refund(3030301)
        # Because refund date (2026-11-18) != payment date (2026-11-10), Commission & TaxSender MUST be 0
        self.assertFalse(ref_rec.is_same_day)
        self.assertEqual(ref_rec.commission_minor, 0)
        self.assertEqual(ref_rec.tax_sender_minor, 0)

        confirmed_rec, _ = client.confirm_refund(3030301, 9090901)
        self.assertEqual(confirmed_rec.status, MTNPayRefundRecord.RefundStatus.CONFIRMED)
        inv.refresh_from_db()
        self.assertTrue(inv.is_refunded)

        cancelled_rec, _ = client.cancel_refund(9090901)
        self.assertEqual(cancelled_rec.status, MTNPayRefundRecord.RefundStatus.CANCELLED)

    # ── 5. Timeout (408) Auto-Retry & Disconnect Recovery via invoice/get ────
    def test_timeout_408_retry_and_disconnect_recovery_via_invoice_get(self):
        inv = MTNPayInvoiceRecord.objects.create(
            terminal=self.terminal,
            invoice_number=4040401,
            amount_major=Decimal("500.00"),
            amount_minor=50000,
            currency_code="SYP",
            status_code=5,
            customer_phone="963947991951",
            guid="guid-test-408",
            operation_number="777111",
        )
        calls = []

        def flaky_transport(req_name, headers, body_bytes):
            calls.append((req_name, body_bytes))
            if req_name == "pos_web/payment_phone/confirm":
                # Always timeout on confirm so client falls back to pos_web/invoice/get
                raise TimeoutError("Simulated network drop during payment confirmation")
            if req_name == "pos_web/invoice/get":
                return self._make_signed_server_response({
                    "Errno": 0,
                    "Receipt": {
                        "Invoice": 4040401,
                        "Status": 9,
                        "Transaction": "TX-RECOVERED-408",
                        "Processed": "2026-11-18T16:00:00",
                    },
                })
            raise AssertionError(req_name)

        client = MTNPaymentClient(
            self.terminal,
            private_key_pem=self.priv_pem,
            transport=flaky_transport,
            max_timeout_retries=1,
        )
        recovered_inv, _ = client.confirm_phone_payment(4040401, sms_code="112233")
        self.assertTrue(recovered_inv.is_paid)
        self.assertEqual(recovered_inv.transaction_id, "TX-RECOVERED-408")
        # Confirm was tried twice (initial + 1 retry with identical body) then recovered via invoice/get
        self.assertEqual(calls[0][0], "pos_web/payment_phone/confirm")
        self.assertEqual(calls[1][0], "pos_web/payment_phone/confirm")
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertEqual(calls[2][0], "pos_web/invoice/get")

    # ── 6. Mandatory Error Table & Private Key Non-Leakage Audit ─────────────
    def test_mandatory_error_codes_and_no_secret_leakage(self):
        required_codes = [
            400, 401, 403, 302, 500,
            405, 408,
            300, 301, 303, 304,
            404, 409, 603, 609,
            660, 661, 662,
            613, 40401, 40025, 40026, 40301,
        ]
        for code in required_codes:
            self.assertIn(code, MTN_ERROR_CATALOG)
            err = MTNPayError.from_errno(code)
            self.assertEqual(err.errno, code)
            self.assertTrue(len(str(err)) > 5)

        User = get_user_model()
        admin = User.objects.create_superuser(
            email="mtn_admin@example.com",
            username="mtn_admin",
            password="StrongPassword123!",
        )
        inv = MTNPayInvoiceRecord.objects.create(
            terminal=self.terminal,
            invoice_number=5050501,
            amount_major=Decimal("1200.00"),
            amount_minor=120000,
            currency_code="SYP",
            status_code=1,
        )
        c = Client(HTTP_HOST="raqamiyatapp.com")
        c.force_login(admin)

        r_admin = c.get("/control/mtn-pay/", secure=True)
        self.assertEqual(r_admin.status_code, 200)
        html_admin = r_admin.content.decode("utf-8")
        self.assertNotIn("BEGIN PRIVATE KEY", html_admin)
        self.assertNotIn(self.priv_pem[:30], html_admin)

        r_checkout = c.get(f"/payments/mtn/{inv.invoice_number}/", secure=True)
        self.assertEqual(r_checkout.status_code, 200)
        html_checkout = r_checkout.content.decode("utf-8")
        self.assertNotIn("BEGIN PRIVATE KEY", html_checkout)
        self.assertIn("RQ-POS-9988", html_checkout)

    # ── 7. Unified Gateway Adapter (MTNPayGateway) & API Gateways Admin ──────
    def test_mtn_pay_gateway_adapter_and_unified_api_list(self):
        from apps.common.models import Currency
        from apps.payments.gateways import MTNPayGateway, gateway_for
        from apps.payments.models import DepositRequest, PaymentGatewayIntegration

        usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "buy_rate": Decimal("1.0"), "sell_rate": Decimal("1.0"), "is_default": True, "is_active": True},
        )
        syp, _ = Currency.objects.get_or_create(
            code="SYP",
            defaults={"name": "Syrian Pound", "symbol": "ل.س", "buy_rate": Decimal("15000.0"), "sell_rate": Decimal("15000.0"), "is_active": True},
        )

        gw_obj = PaymentGatewayIntegration.objects.filter(provider="mtn_pay").first()
        if not gw_obj:
            gw_obj = PaymentGatewayIntegration.objects.create(
                name="إم تي إن كاش (MTNPay)",
                provider="mtn_pay",
                mode="sandbox",
                terminal_id=self.terminal.terminal_id,
                base_url="https://cash.mtnsyr.com",
                is_active=True,
                can_deposit=True,
            )
        pm = gw_obj.sync_payment_method()
        self.assertIsNotNone(pm)
        self.assertEqual(gw_obj.logo_url, "/static/site/img/brands/mtn.svg")

        gw = gateway_for("mtn_pay")
        self.assertIsInstance(gw, MTNPayGateway)

        # Inject deterministic in-memory signed transport so unit test never calls live internet
        def mock_gw_transport(req_name, headers, body_bytes):
            data = json.loads(body_bytes.decode("utf-8"))
            if req_name == "pos_web/invoice/create":
                return self._make_signed_server_response({
                    "Errno": 0,
                    "Receipt": {
                        "Invoice": data["Invoice"],
                        "Amount": data["Amount"],
                        "QR": f"MTNPAY://{data['Invoice']}",
                        "Status": 1,
                        "Transaction": f"TX-{data['Invoice']}",
                    },
                })
            if req_name == "pos_web/payment_phone/initiate":
                return self._make_signed_server_response({
                    "Errno": 0,
                    "OperationNumber": 778899,
                    "PaySystem": "MTNPay",
                })
            if req_name == "pos_web/payment_phone/confirm":
                return self._make_signed_server_response({
                    "Errno": 0,
                    "Status": 9,
                    "Transaction": f"TX-PAID-{data['Invoice']}",
                    "Abuse": 3,
                })
            return self._make_signed_server_response({"Errno": 0})

        orig_get_client = gw.get_client
        def patched_get_client(store=None):
            c = MTNPaymentClient(self.terminal, private_key_pem=self.priv_pem, transport=mock_gw_transport)
            return c
        gw.get_client = patched_get_client

        User = get_user_model()
        customer = User.objects.create_user(
            email="mtn_cust@example.com",
            username="mtn_cust",
            password="StrongPassword123!",
        )
        dep = DepositRequest.objects.create(
            user=customer,
            payment_method=pm,
            currency=usd,
            amount=Decimal("2.00"),
            final_amount=Decimal("2.00"),
        )
        res = gw.create_payment(dep)
        self.assertIn("/payments/mtn/", res["url"])
        self.assertTrue(res["payment_id"])

        # Complete phone payment and verify wallet is credited automatically
        inv_num = int(res["payment_id"])
        client = gw.get_client()
        client.initiate_phone_payment(invoice_number=inv_num, customer_phone="963947991951")
        paid_rec, _ = client.confirm_phone_payment(invoice_number=inv_num, sms_code="123456")
        self.assertTrue(paid_rec.is_paid)
        dep.refresh_from_db()
        self.assertEqual(dep.status, DepositRequest.Status.COMPLETED)
