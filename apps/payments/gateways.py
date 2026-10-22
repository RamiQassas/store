"""
Payment Gateway Abstract and Concrete Implementations
Supports Paymera eGate and ShamCash E-Payment
"""

from decimal import Decimal
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from apps.payments.paymera import PaymeraClient, PaymeraError
from apps.payments.shamcash import ShamCashClient, ShamCashError

logger = logging.getLogger(__name__)


class PaymentGatewayError(Exception):
    pass


class BasePaymentGateway:
    code = "base"

    def create_payment(self, deposit, request=None):
        raise NotImplementedError

    def verify_payment(self, deposit):
        raise NotImplementedError

    def create_order_payment(self, order, request=None):
        raise NotImplementedError

    def verify_order_payment(self, order):
        raise NotImplementedError


class PaymeraGateway(BasePaymentGateway):
    code = "paymera"

    def __init__(self, integration=None):
        self.integration = integration

    def get_client(self) -> PaymeraClient:
        has_creds = (
            self.integration
            and getattr(self.integration, "api_key", None)
            and getattr(self.integration, "terminal_id", None)
        )
        if not has_creds:
            from apps.payments.models import PaymentGatewayIntegration
            self.integration = (
                PaymentGatewayIntegration.all_objects.filter(
                    provider=PaymentGatewayIntegration.Provider.PAYMERA,
                    is_active=True
                )
                .exclude(terminal_id="")
                .exclude(api_key="")
                .first()
            )

        if self.integration:
            return PaymeraClient.from_integration(self.integration)

        from django.conf import settings
        return PaymeraClient(
            api_key=getattr(settings, "PAYMERA_API_KEY", ""),
            terminal_id=getattr(settings, "PAYMERA_TERMINAL_ID", ""),
            base_url=getattr(settings, "PAYMERA_BASE_URL", "https://egate-t.paymera.cc"),
            mode=getattr(settings, "PAYMERA_MODE", "sandbox"),
        )

    def create_payment(self, deposit, request=None):
        from django.urls import reverse
        client = self.get_client()

        # Determine callback & trigger URLs
        if request:
            callback_base = request.build_absolute_uri(reverse("paymera_callback"))
            trigger_base = request.build_absolute_uri(reverse("paymera_trigger"))
        else:
            callback_base = reverse("paymera_callback")
            trigger_base = reverse("paymera_trigger")

        callback_url = f"{callback_base}?deposit_id={deposit.id}"
        trigger_url = f"{trigger_base}?deposit_id={deposit.id}"

        # Paymera operations are strictly in Syrian Liras (SYP)
        currency_code = deposit.currency.code if deposit.currency else "USD"
        if currency_code == "SYP":
            syp_amount = deposit.amount
        else:
            from apps.common.models import Currency
            syp_currency = Currency.objects.filter(code="SYP", is_active=True).first() or Currency.all_objects.filter(code="SYP", is_active=True).first()
            if syp_currency and hasattr(deposit.currency, "to_base"):
                usd_val = deposit.currency.to_base(deposit.amount, "deposit")
                syp_amount = syp_currency.from_base(usd_val, "deposit")
            else:
                syp_amount = deposit.amount

        clean_syp = int(round(float(syp_amount)))
        if clean_syp <= 0:
            clean_syp = 1

        notes = f"Deposit {deposit.id} for user {deposit.user.email}"
        try:
            res = client.create_payment(
                amount=clean_syp,
                callback_url=callback_url,
                trigger_url=trigger_url,
                notes=notes,
                lang="ar",
            )
            deposit.gateway_payment_id = res["payment_id"]
            if not isinstance(deposit.metadata, dict):
                deposit.metadata = {}
            deposit.metadata["paymera_url"] = res["url"]
            deposit.metadata["paymera_payment_id"] = res["payment_id"]
            deposit.metadata["syp_amount"] = clean_syp
            deposit.save(update_fields=["gateway_payment_id", "metadata"])
            return res
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_payment(self, deposit):
        payment_id = deposit.gateway_payment_id or (
            deposit.metadata.get("paymera_payment_id") if isinstance(deposit.metadata, dict) else None
        )
        if not payment_id:
            raise PaymentGatewayError("لا يوجد معرف دفعة بيميرا مسجل.")

        client = self.get_client()
        try:
            return client.get_payment_status(payment_id)
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err

    def create_order_payment(self, order, request=None):
        from django.urls import reverse
        from apps.common.models import Currency
        client = self.get_client()

        from django.conf import settings

        if request:
            callback_base = request.build_absolute_uri(reverse("paymera_callback"))
        else:
            callback_base = reverse("paymera_callback")

        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            trigger_base = f"{site_url}{reverse('paymera_trigger')}"
        elif request:
            trigger_base = request.build_absolute_uri(reverse("paymera_trigger"))
        else:
            trigger_base = reverse("paymera_trigger")

        callback_url = f"{callback_base}?order_id={order.id}"
        trigger_url = f"{trigger_base}?order_id={order.id}"

        store = getattr(order, "store", None)
        syp_currency = None
        if store:
            syp_currency = Currency.all_objects.filter(store=store, code="SYP", is_active=True).first()
        if not syp_currency:
            syp_currency = Currency.all_objects.filter(code="SYP", is_active=True).first()

        exact_usd = Decimal("0.00")
        for item in order.items.all():
            exact_usd += Decimal(str(item.unit_price)) * item.quantity
        if exact_usd <= 0:
            exact_usd = order.total_amount

        if syp_currency:
            syp_val = syp_currency.from_base(exact_usd, "deposit")
            charge_amount = int(round(float(syp_val)))
        else:
            charge_amount = int(round(float(exact_usd)))
        if charge_amount <= 0:
            charge_amount = 1

        notes = f"Order {order.number} for {order.customer.email}"
        try:
            res = client.create_payment(
                amount=charge_amount,
                callback_url=callback_url,
                trigger_url=trigger_url,
                notes=notes,
                lang="ar",
            )
            if not isinstance(order.metadata, dict):
                order.metadata = {}
            order.metadata["gateway_payment_id"] = res["payment_id"]
            order.metadata["paymera_url"] = res["url"]
            order.metadata["gateway_charge_amount"] = int(charge_amount)
            order.metadata["gateway_charge_currency"] = "SYP"
            order.metadata["payment_provider"] = self.code
            order.save(update_fields=["metadata"])
            return res
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_order_payment(self, order):
        payment_id = (
            order.metadata.get("gateway_payment_id")
            if isinstance(order.metadata, dict)
            else None
        )
        if not payment_id:
            raise PaymentGatewayError("لا يوجد معرف دفعة مسجل للطلب.")

        client = self.get_client()
        try:
            return client.get_payment_status(payment_id)
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err


class ShamCashGateway(BasePaymentGateway):
    """
    ShamCash E-Payment Gateway implementation.
    Complies strictly with ShamCash Integration Guide v1.0.0 and Terms & Conditions.
    Supports:
    - Wallet Deposits in USD (currencyId=1) and SYP (currencyId=2) with 0% extra surcharge.
    - Direct Product Checkouts in USD (currencyId=1) and SYP (currencyId=2).
    - Direct JWE AES-256-GCM encryption with mandatory replay protection (iat/exp).
    - Immutable ShamCashBillRecord and ShamCashRefundRecord ledger.
    - Full & Partial Refunds with idempotencyKey enforcement (10 to 100 chars).
    - Real-time fallback status inquiry and active health check.
    """
    code = "sham_cash"

    def __init__(self, integration=None):
        self.integration = integration

    def get_client(self) -> ShamCashClient:
        has_creds = (
            self.integration
            and getattr(self.integration, "api_key", None)
            and getattr(self.integration, "api_secret", None)
        )
        if not has_creds:
            from apps.payments.models import PaymentGatewayIntegration
            self.integration = (
                PaymentGatewayIntegration.all_objects.filter(
                    provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
                    is_active=True
                )
                .exclude(api_key="")
                .exclude(api_secret="")
                .first()
            )

        if self.integration:
            return ShamCashClient.from_integration(self.integration)

        from django.conf import settings
        return ShamCashClient(
            agent_key=getattr(settings, "SHAM_CASH_AGENT_KEY", ""),
            secret_key=getattr(settings, "SHAM_CASH_SECRET_KEY", ""),
            base_url=getattr(settings, "SHAM_CASH_BASE_URL", None),
            mode=getattr(settings, "SHAM_CASH_MODE", "sandbox"),
        )

    def check_health(self) -> Dict[str, Any]:
        """Test connectivity and encryption against ShamCash API."""
        client = self.get_client()
        if not client.agent_key or not client.raw_secret_key:
            return {"ok": False, "message": "Agent Key أو Secret Key غير مهيأ."}
        try:
            # Probe getBillInfo with a non-existent test ID to verify JWE encryption & API handshake
            test_bill_no = f"PROBE-{int(time.time())}"
            try:
                client.get_bill_info(test_bill_no)
                return {"ok": True, "message": "اتصال ناجح 100% ومصادقة سليمة مع خوادم شام كاش."}
            except ShamCashError as e:
                # 1703 (Bill Not Found) means encryption, authentication, and routing succeeded!
                if e.error_code == 1703:
                    return {
                        "ok": True,
                        "message": "تم التحقق بنجاح من صحة المفاتيح والتشفير والاتصال بخوادم شام كاش، والمصادقة سليمة 100%.",
                        "code": 1703,
                    }
                elif e.error_code in (1701, 1702, 1705, 1706):
                    return {
                        "ok": False,
                        "message": f"فشل التحقق من بيانات الاعتماد: {e}",
                        "code": e.error_code,
                    }
                return {
                    "ok": False,
                    "message": f"استجابة من شام كاش: {e}",
                    "code": e.error_code,
                }
        except Exception as exc:
            return {"ok": False, "message": f"خطأ اتصال بالشبكة: {exc}"}

    def create_payment(self, deposit, request=None):
        """Create payment bill for wallet deposit."""
        from django.urls import reverse
        from django.conf import settings
        from django.utils import timezone
        from apps.payments.models import ShamCashBillRecord
        client = self.get_client()

        # Decouple internal ID from billNo per Recommendation (Doc Section 10)
        bill_no = f"DEP-{deposit.id}-{int(time.time())}"

        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            callback_base = f"{site_url}{reverse('shamcash_callback')}"
            redirect_base = f"{site_url}{reverse('shamcash_redirect')}"
        elif request:
            callback_base = request.build_absolute_uri(reverse("shamcash_callback"))
            redirect_base = request.build_absolute_uri(reverse("shamcash_redirect"))
        else:
            callback_base = reverse("shamcash_callback")
            redirect_base = reverse("shamcash_redirect")

        callback_url = f"{callback_base}?type=deposit&id={deposit.id}&bill_no={bill_no}"
        redirect_url = f"{redirect_base}?type=deposit&id={deposit.id}&bill_no={bill_no}"

        # Dual currency: USD (1) or SYP (2)
        curr_code = deposit.currency.code if deposit.currency else "USD"
        if curr_code == "SYP":
            currency_id = ShamCashClient.CURRENCY_SYP
            bill_amount = Decimal(str(deposit.amount)).quantize(Decimal("0.01"))
        else:
            currency_id = ShamCashClient.CURRENCY_USD
            bill_amount = Decimal(str(deposit.amount)).quantize(Decimal("0.01"))

        notes = f"إيداع محفظة رقم {deposit.id} للمستخدم {deposit.user.email}"
        try:
            res = client.create_bill(
                bill_no=bill_no,
                amount=bill_amount,
                currency_id=currency_id,
                callback_url=callback_url,
                redirect_url=redirect_url,
                note=notes,
            )
            deposit.gateway_payment_id = bill_no
            if not isinstance(deposit.metadata, dict):
                deposit.metadata = {}
            deposit.metadata["shamcash_bill_no"] = bill_no
            deposit.metadata["shamcash_url"] = res.get("paymentUrl")
            deposit.metadata["shamcash_currency_id"] = currency_id
            deposit.metadata["shamcash_charge_amount"] = str(bill_amount)
            deposit.metadata["shamcash_created_date"] = res.get("createdDate")
            deposit.metadata["payment_provider"] = self.code
            deposit.save(update_fields=["gateway_payment_id", "metadata"])

            # Create immutable bill record for compliance & 5-year retention
            created_date = None
            created_time = None
            if res.get("createdDate"):
                try:
                    created_date = res.get("createdDate")
                except Exception:
                    pass

            ShamCashBillRecord.objects.create(
                bill_no=bill_no,
                bill_type=ShamCashBillRecord.BillType.DEPOSIT,
                user=deposit.user,
                deposit=deposit,
                amount=bill_amount,
                currency_id=currency_id,
                currency_code=curr_code,
                status_id=ShamCashClient.STATUS_PENDING,
                status_name=ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PENDING],
                payment_url=res.get("paymentUrl") or "",
                callback_url=callback_url,
                redirect_url=redirect_url,
                note=notes,
                created_date=created_date,
                expires_at=timezone.now() + timezone.timedelta(minutes=10),
                raw_create_response=res,
            )

            return {
                "url": res.get("paymentUrl"),
                "payment_id": bill_no,
                "bill_no": bill_no,
                "provider": self.code,
                "status": "pending",
                "raw": res,
            }
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_payment(self, deposit):
        bill_no = (
            deposit.gateway_payment_id
            or (deposit.metadata.get("shamcash_bill_no") if isinstance(deposit.metadata, dict) else None)
        )
        if not bill_no:
            raise PaymentGatewayError("لا يوجد رقم فاتورة شام كاش مسجل لهذا الإيداع.")

        client = self.get_client()
        try:
            return client.get_bill_info(bill_no)
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def create_order_payment(self, order, request=None):
        """Create payment bill for direct order checkout."""
        from django.urls import reverse
        from django.conf import settings
        from django.utils import timezone
        from apps.common.models import Currency
        from apps.payments.models import ShamCashBillRecord
        client = self.get_client()

        # Decouple internal ID from billNo per Recommendation (Doc Section 10)
        bill_no = f"ORD-{order.number}-{int(time.time())}"

        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            callback_base = f"{site_url}{reverse('shamcash_callback')}"
            redirect_base = f"{site_url}{reverse('shamcash_redirect')}"
        elif request:
            callback_base = request.build_absolute_uri(reverse("shamcash_callback"))
            redirect_base = request.build_absolute_uri(reverse("shamcash_redirect"))
        else:
            callback_base = reverse("shamcash_callback")
            redirect_base = reverse("shamcash_redirect")

        callback_url = f"{callback_base}?type=order&id={order.id}&bill_no={bill_no}"
        redirect_url = f"{redirect_base}?type=order&id={order.id}&bill_no={bill_no}"

        # Determine requested currency: USD (1) or SYP (2)
        meta = order.metadata if isinstance(order.metadata, dict) else {}
        req_curr = None
        if request:
            req_curr = request.POST.get("gateway_currency") or request.POST.get("currency")
        if not req_curr:
            req_curr = meta.get("gateway_currency") or meta.get("selected_currency")

        exact_usd = Decimal("0.00")
        for item in order.items.all():
            exact_usd += Decimal(str(item.unit_price)) * item.quantity
        if exact_usd <= 0:
            exact_usd = Decimal(str(order.total_amount))

        if req_curr and str(req_curr).upper() in ("SYP", "2"):
            # Syrian Pounds
            store = getattr(order, "store", None)
            syp_currency = None
            if store:
                syp_currency = Currency.all_objects.filter(store=store, code="SYP", is_active=True).first()
            if not syp_currency:
                syp_currency = Currency.all_objects.filter(code="SYP", is_active=True).first()

            if syp_currency:
                syp_val = syp_currency.from_base(exact_usd, "deposit")
                charge_amount = Decimal(str(syp_val)).quantize(Decimal("0.01"))
            else:
                charge_amount = exact_usd.quantize(Decimal("0.01"))

            currency_id = ShamCashClient.CURRENCY_SYP
            currency_code = "SYP"
        else:
            # USD default
            currency_id = ShamCashClient.CURRENCY_USD
            charge_amount = exact_usd.quantize(Decimal("0.01"))
            currency_code = "USD"

        notes = f"سداد طلب رقم {order.number} للعميل {order.customer.email}"
        try:
            res = client.create_bill(
                bill_no=bill_no,
                amount=charge_amount,
                currency_id=currency_id,
                callback_url=callback_url,
                redirect_url=redirect_url,
                note=notes,
            )
            if not isinstance(order.metadata, dict):
                order.metadata = {}
            order.metadata["gateway_payment_id"] = bill_no
            order.metadata["shamcash_bill_no"] = bill_no
            order.metadata["shamcash_url"] = res.get("paymentUrl")
            order.metadata["gateway_charge_amount"] = str(charge_amount)
            order.metadata["gateway_charge_currency"] = currency_code
            order.metadata["payment_provider"] = self.code
            order.save(update_fields=["metadata"])

            # Create immutable bill record for compliance & 5-year retention
            ShamCashBillRecord.objects.create(
                bill_no=bill_no,
                bill_type=ShamCashBillRecord.BillType.ORDER,
                user=order.customer,
                order=order,
                amount=charge_amount,
                currency_id=currency_id,
                currency_code=currency_code,
                status_id=ShamCashClient.STATUS_PENDING,
                status_name=ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PENDING],
                payment_url=res.get("paymentUrl") or "",
                callback_url=callback_url,
                redirect_url=redirect_url,
                note=notes,
                created_date=res.get("createdDate"),
                expires_at=timezone.now() + timezone.timedelta(minutes=10),
                raw_create_response=res,
            )

            return {
                "url": res.get("paymentUrl"),
                "payment_id": bill_no,
                "bill_no": bill_no,
                "provider": self.code,
                "status": "pending",
                "raw": res,
            }
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_order_payment(self, order):
        bill_no = (
            order.metadata.get("shamcash_bill_no")
            or order.metadata.get("gateway_payment_id")
            if isinstance(order.metadata, dict)
            else None
        )
        if not bill_no:
            raise PaymentGatewayError("لا يوجد رقم فاتورة شام كاش مسجل لهذا الطلب.")

        client = self.get_client()
        try:
            return client.get_bill_info(bill_no)
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def refund_order_payment(self, order, reason="", amount=None, actor=None):
        """
        Refund a direct order paid via ShamCash.
        Enforces Article 9 (Refund Rules) and Article 14 (Dispute & Refund Logging).
        """
        import uuid
        from apps.payments.models import ShamCashBillRecord, ShamCashRefundRecord
        meta = order.metadata if isinstance(order.metadata, dict) else {}
        bill_no = meta.get("shamcash_bill_no") or meta.get("gateway_payment_id")
        if not bill_no:
            raise PaymentGatewayError("لا يمكن استرداد طلب بدون رقم فاتورة شام كاش.")

        if amount:
            refund_amt = Decimal(str(amount)).quantize(Decimal("0.01"))
        else:
            refund_amt = Decimal(str(meta.get("gateway_charge_amount") or order.total_amount)).quantize(Decimal("0.01"))

        client = self.get_client()
        idempotency_key = f"REF-ORD-{order.id}-{uuid.uuid4().hex[:12]}"
        note = reason or f"استرداد قيمة الطلب {order.number}"

        try:
            res = client.refund_bill(
                bill_no=bill_no,
                amount=refund_amt,
                note=note,
                idempotency_key=idempotency_key,
            )
            tran_id = res.get("tranId")

            bill_record = ShamCashBillRecord.objects.filter(bill_no=bill_no).first()
            if bill_record:
                bill_record.total_refunded_amount += refund_amt
                if bill_record.total_refunded_amount >= bill_record.amount:
                    bill_record.status_id = ShamCashClient.STATUS_REFUNDED
                    bill_record.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_REFUNDED]
                else:
                    bill_record.status_id = ShamCashClient.STATUS_PARTLY_REFUNDED
                    bill_record.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PARTLY_REFUNDED]
                bill_record.save(update_fields=["total_refunded_amount", "status_id", "status_name", "updated_at"])

                ShamCashRefundRecord.objects.create(
                    bill=bill_record,
                    bill_no=bill_no,
                    amount=refund_amt,
                    idempotency_key=idempotency_key,
                    tran_id=tran_id,
                    note=note,
                    status="success",
                    created_by=actor,
                    raw_response=res,
                )

            order.metadata["shamcash_refunded"] = True
            order.metadata["shamcash_refund_data"] = res
            order.save(update_fields=["metadata"])
            return res
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def refund_deposit_payment(self, deposit, reason="", amount=None, actor=None):
        """Refund a wallet deposit executed via ShamCash."""
        import uuid
        from apps.payments.models import ShamCashBillRecord, ShamCashRefundRecord
        bill_no = deposit.gateway_payment_id or (deposit.metadata.get("shamcash_bill_no") if isinstance(deposit.metadata, dict) else None)
        if not bill_no:
            raise PaymentGatewayError("لا يمكن استرداد إيداع بدون رقم فاتورة شام كاش.")

        if amount:
            refund_amt = Decimal(str(amount)).quantize(Decimal("0.01"))
        else:
            refund_amt = Decimal(str(deposit.amount)).quantize(Decimal("0.01"))

        client = self.get_client()
        idempotency_key = f"REF-DEP-{deposit.id}-{uuid.uuid4().hex[:12]}"
        note = reason or f"استرداد قيمة الإيداع {deposit.id}"

        try:
            res = client.refund_bill(
                bill_no=bill_no,
                amount=refund_amt,
                note=note,
                idempotency_key=idempotency_key,
            )
            tran_id = res.get("tranId")

            bill_record = ShamCashBillRecord.objects.filter(bill_no=bill_no).first()
            if bill_record:
                bill_record.total_refunded_amount += refund_amt
                if bill_record.total_refunded_amount >= bill_record.amount:
                    bill_record.status_id = ShamCashClient.STATUS_REFUNDED
                    bill_record.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_REFUNDED]
                else:
                    bill_record.status_id = ShamCashClient.STATUS_PARTLY_REFUNDED
                    bill_record.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PARTLY_REFUNDED]
                bill_record.save(update_fields=["total_refunded_amount", "status_id", "status_name", "updated_at"])

                ShamCashRefundRecord.objects.create(
                    bill=bill_record,
                    bill_no=bill_no,
                    amount=refund_amt,
                    idempotency_key=idempotency_key,
                    tran_id=tran_id,
                    note=note,
                    status="success",
                    created_by=actor,
                    raw_response=res,
                )
            return res
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err


def gateway_for(provider_or_obj):
    if hasattr(provider_or_obj, "provider"):
        code = provider_or_obj.provider
        if code == "paymera":
            return PaymeraGateway(integration=provider_or_obj)
        if code == "sham_cash":
            return ShamCashGateway(integration=provider_or_obj)
    elif hasattr(provider_or_obj, "gateway") and provider_or_obj.gateway:
        return gateway_for(provider_or_obj.gateway)
    elif hasattr(provider_or_obj, "provider_type"):
        code = provider_or_obj.provider_type
    else:
        code = str(provider_or_obj)

    if code == "paymera":
        return PaymeraGateway()
    if code == "sham_cash":
        return ShamCashGateway()
    return ShamCashGateway()
