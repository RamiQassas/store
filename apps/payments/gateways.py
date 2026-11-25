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

        exact_amount = Decimal(str(order.total_amount)) if (order.total_amount and order.total_amount > Decimal("0.00")) else Decimal("0.00")
        if exact_amount <= Decimal("0.00"):
            for item in order.items.all():
                exact_amount += Decimal(str(item.unit_price)) * item.quantity
        if exact_amount <= Decimal("0.00"):
            exact_amount = Decimal("1.00")

        if syp_currency and float(getattr(syp_currency, "buy_rate", 1) or 1) > 1.0:
            syp_val = syp_currency.from_base(exact_amount, "deposit")
            charge_amount = int(round(float(syp_val)))
        else:
            charge_amount = int(round(float(exact_amount)))
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
                    is_active=True,
                )
                .exclude(api_key="")
                .exclude(api_secret="")
                .order_by("-updated_at")
                .first()
                or PaymentGatewayIntegration.all_objects.filter(
                    provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
                    is_active=True,
                )
                .order_by("-updated_at")
                .first()
            )

        if self.integration:
            return ShamCashClient.from_integration(self.integration)

        from django.conf import settings
        return ShamCashClient(
            agent_key=getattr(settings, "SHAM_CASH_AGENT_KEY", ""),
            secret_key=getattr(settings, "SHAM_CASH_SECRET_KEY", ""),
            base_url=getattr(settings, "SHAM_CASH_BASE_URL", None),
            mode=getattr(settings, "SHAM_CASH_MODE", "live"),
        )

    def check_health(self) -> Dict[str, Any]:
        """Test connectivity and encryption against ShamCash API."""
        client = self.get_client()
        if not client.agent_key or not client.raw_secret_key:
            return {"ok": False, "message": "معرف الوكيل (Agent Key) أو المفتاح السري (Secret Key) غير مهيأ."}
        try:
            # Probe getBillInfo with a non-existent test ID to verify JWE encryption & API handshake
            test_bill_no = f"PROBE-{int(time.time())}"
            try:
                client.get_bill_info(test_bill_no)
                return {
                    "ok": True,
                    "message": f"اتصال ناجح 100% ومصادقة سليمة مع خوادم شام كاش ({client.base_url}).",
                }
            except ShamCashError as e:
                # 1703 (Bill Not Found) means encryption, authentication, and routing succeeded!
                if e.error_code == 1703:
                    return {
                        "ok": True,
                        "message": f"تم التحقق بنجاح من صحة المفاتيح والتشفير والاتصال بخوادم شام كاش ({client.base_url})، والمصادقة سليمة 100%.",
                        "code": 1703,
                    }
                elif e.error_code == 504:
                    outbound_ip = ""
                    try:
                        import requests as _req
                        proxies = {"http": client.proxy_url, "https": client.proxy_url} if client.proxy_url else None
                        outbound_ip = _req.get("https://api4.ipify.org", proxies=proxies, timeout=4).text.strip()
                    except Exception:
                        pass
                    via_label = "عبر البروكسي المخصص" if client.proxy_url else "الاتصال المباشر للخادم"
                    ip_hint = (
                        f" (IP الصادر لـ {via_label}: {outbound_ip} — يرجى التأكد من أن هذا الـ IP سوري أو مضاف في القائمة البيضاء Whitelist لدى شام كاش)"
                        if outbound_ip
                        else ""
                    )
                    return {
                        "ok": False,
                        "message": f"انتهت مهلة الاتصال بخوادم شام كاش ({client.base_url}){ip_hint}.",
                        "code": 504,
                        "outbound_ip": outbound_ip,
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

        # Decouple internal UUID from billNo per Recommendation (Doc Section 10.1, Page 25):
        # Short alphanumeric reference with sequence suffix (e.g. DEP-CD3EA39D88-1-4821)
        short_dep = str(deposit.id).replace("-", "")[:10].upper()
        seq = ShamCashBillRecord.objects.filter(deposit=deposit).count() + 1
        bill_no = f"DEP-{short_dep}-{seq}-{int(time.time()) % 10000:04d}"

        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            callback_url = f"{site_url}{reverse('shamcash_callback')}"
            redirect_url = f"{site_url}{reverse('shamcash_redirect_bill', kwargs={'bill_no': bill_no})}"
        elif request:
            callback_url = request.build_absolute_uri(reverse("shamcash_callback"))
            redirect_url = request.build_absolute_uri(reverse("shamcash_redirect_bill", kwargs={"bill_no": bill_no}))
        else:
            callback_url = reverse("shamcash_callback")
            redirect_url = reverse("shamcash_redirect_bill", kwargs={"bill_no": bill_no})

        # Force HTTPS on callbackUrl and redirectUrl in live mode (Doc Section 6.1 & 9)
        if client.mode == "live":
            if callback_url.startswith("http://") and "localhost" not in callback_url and "127.0.0.1" not in callback_url:
                callback_url = "https://" + callback_url[len("http://"):]
            if redirect_url.startswith("http://") and "localhost" not in redirect_url and "127.0.0.1" not in redirect_url:
                redirect_url = "https://" + redirect_url[len("http://"):]

        # Dual currency: USD (1) or SYP (2)
        curr_code = deposit.currency.code if deposit.currency else "USD"
        if curr_code == "SYP":
            currency_id = ShamCashClient.CURRENCY_SYP
            bill_amount = Decimal(str(deposit.amount)).quantize(Decimal("0.01"))
        else:
            currency_id = ShamCashClient.CURRENCY_USD
            bill_amount = Decimal(str(deposit.amount)).quantize(Decimal("0.01"))

        notes = f"إيداع محفظة رقميات ({short_dep})"
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
            try:
                from django.utils.dateparse import parse_date
                raw_cd = res.get("createdDate")
                parsed_cd = parse_date(str(raw_cd)[:10]) if raw_cd else timezone.now().date()
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
                    created_date=parsed_cd,
                    expires_at=timezone.now() + timezone.timedelta(minutes=10),
                    raw_create_response=res,
                )
            except Exception as rec_err:
                import logging
                logging.getLogger(__name__).warning(f"ShamCashBillRecord deposit create warning: {rec_err}")

            return {
                "url": res.get("paymentUrl"),
                "paymentUrl": res.get("paymentUrl"),
                "payment_id": bill_no,
                "bill_no": bill_no,
                "billNo": bill_no,
                "provider": self.code,
                "status": "pending",
                "raw": res,
            }
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_payment(self, deposit, force: bool = False):
        """
        Verify deposit payment status.
        Per Official ShamCash Doc Section 10.3 (Page 26 - Avoid Polling):
        Relies on local DB (updated by Webhook) during the first 10 minutes,
        and invokes getBillInfo only once after >= 10 minutes (unless force=True).
        """
        from apps.payments.views_shamcash import reconcile_shamcash_deposit_if_overdue
        return reconcile_shamcash_deposit_if_overdue(deposit, force=force)

    def create_order_payment(self, order, request=None):
        """Create payment bill for direct order checkout."""
        from django.urls import reverse
        from django.conf import settings
        from django.utils import timezone
        from apps.common.models import Currency
        from apps.payments.models import ShamCashBillRecord
        client = self.get_client()

        # Decouple internal Order number from billNo per Recommendation (Doc Section 10.1, Page 25):
        # e.g. ORD-10025-1-4821
        clean_num = str(order.number).strip()
        if clean_num.upper().startswith("ORD-"):
            clean_num = clean_num[4:]
        elif clean_num.upper().startswith("ORD"):
            clean_num = clean_num[3:]
        clean_num = clean_num.strip("-") or str(order.id).replace("-", "")[:8].upper()
        seq = ShamCashBillRecord.objects.filter(order=order).count() + 1
        bill_no = f"ORD-{clean_num}-{seq}-{int(time.time()) % 10000:04d}"

        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        if site_url:
            callback_url = f"{site_url}{reverse('shamcash_callback')}"
            redirect_url = f"{site_url}{reverse('shamcash_redirect_bill', kwargs={'bill_no': bill_no})}"
        elif request:
            callback_url = request.build_absolute_uri(reverse("shamcash_callback"))
            redirect_url = request.build_absolute_uri(reverse("shamcash_redirect_bill", kwargs={"bill_no": bill_no}))
        else:
            callback_url = reverse("shamcash_callback")
            redirect_url = reverse("shamcash_redirect_bill", kwargs={"bill_no": bill_no})

        if client.mode == "live":
            if callback_url.startswith("http://") and "localhost" not in callback_url and "127.0.0.1" not in callback_url:
                callback_url = "https://" + callback_url[len("http://"):]
            if redirect_url.startswith("http://") and "localhost" not in redirect_url and "127.0.0.1" not in redirect_url:
                redirect_url = "https://" + redirect_url[len("http://"):]

        # Determine requested currency: USD (1) or SYP (2)
        meta = order.metadata if isinstance(order.metadata, dict) else {}
        req_curr = None
        if request:
            req_curr = request.POST.get("gateway_currency") or request.POST.get("currency")
        if not req_curr:
            req_curr = meta.get("gateway_currency") or meta.get("selected_currency")

        exact_amount = Decimal(str(order.total_amount)) if (order.total_amount and order.total_amount > Decimal("0.00")) else Decimal("0.00")
        if exact_amount <= Decimal("0.00"):
            for item in order.items.all():
                exact_amount += Decimal(str(item.unit_price)) * item.quantity
        if exact_amount <= Decimal("0.00"):
            exact_amount = Decimal("1.00")

        curr_places = meta.get("currency_places")
        if curr_places is not None:
            try:
                curr_places = int(curr_places)
            except (ValueError, TypeError):
                curr_places = None

        from decimal import ROUND_HALF_UP
        if req_curr and str(req_curr).upper() in ("SYP", "2"):
            # Syrian Pounds
            store = getattr(order, "store", None)
            syp_currency = None
            if store:
                syp_currency = Currency.all_objects.filter(store=store, code="SYP", is_active=True).first()
            if not syp_currency:
                syp_currency = Currency.all_objects.filter(code="SYP", is_active=True).first()

            syp_rate = Decimal(str(getattr(syp_currency, "buy_rate", 15000) or 15000))
            if syp_rate <= Decimal("1.0"):
                syp_rate = Decimal("15000")

            syp_val = syp_currency.from_base(exact_amount, "deposit") if syp_currency else (exact_amount * syp_rate)
            charge_amount = Decimal(str(round(syp_val))).quantize(Decimal("1"))
            currency_id = ShamCashClient.CURRENCY_SYP
            currency_code = "SYP"
        else:
            # USD default
            currency_id = ShamCashClient.CURRENCY_USD
            charge_amount = exact_amount.quantize(Decimal("0.01"))
            currency_code = "USD"
            syp_currency = Currency.all_objects.filter(code="SYP", is_active=True).first()
            syp_rate = Decimal(str(getattr(syp_currency, "buy_rate", 15000) or 15000))

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
            order.metadata["base_usd_amount"] = str(exact_amount)
            order.metadata["exchange_rate"] = str(syp_rate)
            order.metadata["payment_provider"] = self.code
            order.save(update_fields=["metadata"])

            # Create immutable bill record for compliance & 5-year retention
            try:
                from django.utils.dateparse import parse_date
                raw_cd = res.get("createdDate")
                parsed_cd = parse_date(str(raw_cd)[:10]) if raw_cd else timezone.now().date()
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
                    created_date=parsed_cd,
                    expires_at=timezone.now() + timezone.timedelta(minutes=10),
                    raw_create_response=res,
                )
            except Exception as rec_err:
                import logging
                logging.getLogger(__name__).warning(f"ShamCashBillRecord order create warning: {rec_err}")

            return {
                "url": res.get("paymentUrl"),
                "paymentUrl": res.get("paymentUrl"),
                "payment_id": bill_no,
                "bill_no": bill_no,
                "billNo": bill_no,
                "provider": self.code,
                "status": "pending",
                "raw": res,
            }
        except ShamCashError as err:
            raise PaymentGatewayError(str(err)) from err
        except Exception as err:
            raise PaymentGatewayError(f"تعذر إنشاء فاتورة الدفع عبر شام كاش: {err}") from err

    def verify_order_payment(self, order, force: bool = False):
        """
        Verify order payment status.
        Per Official ShamCash Doc Section 10.3 (Page 26 - Avoid Polling):
        Relies on local DB (updated by Webhook) during the first 10 minutes,
        and invokes getBillInfo only once after >= 10 minutes (unless force=True).
        """
        from apps.payments.views_shamcash import reconcile_shamcash_order_if_overdue
        return reconcile_shamcash_order_if_overdue(order, force=force)

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


class MTNPayGateway(BasePaymentGateway):
    """
    MTN Payment API (MTNPay / pos_web) Gateway implementation.
    Works identically to ShamCashGateway and PaymeraGateway for:
    - Instant Direct Product & Cart Checkouts
    - Instant Wallet Deposits
    - Status Verification (`pos_web/invoice/get`)
    - Full Order & Deposit Refunds (`pos_web/invoice/refund/initiate` + `confirm`)
    """
    code = "mtn_pay"

    def __init__(self, integration=None):
        self.integration = integration

    def get_terminal(self, store=None):
        from django.utils import timezone
        from apps.payments.models import MTNPayTerminalConfig, PaymentGatewayIntegration

        if not self.integration:
            self.integration = (
                PaymentGatewayIntegration.all_objects.filter(
                    provider=PaymentGatewayIntegration.Provider.MTN_PAY,
                    is_active=True,
                )
                .order_by("-id")
                .first()
            )

        import os
        target_tid = (
            (self.integration.terminal_id if self.integration and self.integration.terminal_id else "")
            or os.environ.get("MTN_PAY_TERMINAL_ID", "")
            or "9001000000064683"
        ).strip()
        target_base_url = (
            (self.integration.base_url if self.integration and self.integration.base_url else "")
            or "https://cash.mtnsyr.com:9000"
        ).strip()
        if target_base_url.rstrip("/") == "https://cash.mtnsyr.com":
            target_base_url = "https://cash.mtnsyr.com:9000"

        term = (
            MTNPayTerminalConfig.objects.filter(terminal_id=target_tid).first()
            or (MTNPayTerminalConfig.objects.filter(store=store).first() if store else None)
            or MTNPayTerminalConfig.objects.first()
        )
        default_settings = {
            "Currency": {"Code": "760", "Brief": "SYP", "Fractional": 100},
            "Limits": {"Minimum": 100, "Maximum": 5000000000000},
            "Allowed": {"Payment": True},
            "Description": {
                "Business": "E payment section",
                "Shop": "Raqmyat",
                "Address": "Damascus",
                "Phone": "963957222109",
                "UniquePayCode": f"MTN-{target_tid[-6:]}",
            },
        }
        if not term:
            term = MTNPayTerminalConfig.objects.create(
                store=store,
                terminal_id=target_tid,
                serial_number="RAQAMIYAT",
                base_url=target_base_url,
                language="en",
                is_activated=True,
                is_locked=False,
                activated_at=timezone.now(),
                terminal_settings=default_settings,
            )
        else:
            changed = False
            if term.terminal_id == "10000001" and target_tid and target_tid != "10000001":
                term.terminal_id = target_tid
                term.serial_number = f"SN-MTN-{target_tid[-6:]}"
                changed = True
            if not term.terminal_settings or not isinstance(term.terminal_settings, dict):
                term.terminal_settings = default_settings
                changed = True
            else:
                limits = term.terminal_settings.get("Limits")
                if not isinstance(limits, dict) or int(limits.get("Maximum", 0) or 0) < 5000000000000:
                    term.terminal_settings["Limits"] = {"Minimum": 100, "Maximum": 5000000000000}
                    changed = True
                allowed = term.terminal_settings.get("Allowed")
                if not isinstance(allowed, dict) or allowed.get("Payment") is not True:
                    term.terminal_settings["Allowed"] = {"Payment": True}
                    changed = True
            if not term.is_activated and not term.is_locked:
                term.is_activated = True
                term.activated_at = timezone.now()
                changed = True
            if changed:
                term.save()
        return term

    def get_client(self, store=None):
        from apps.payments.mtn_pay import MTNPaymentClient
        term = self.get_terminal(store=store)
        client = MTNPaymentClient(term)
        client.ensure_keypair()
        return client

    def create_payment(self, deposit, request=None):
        """Creates an MTNPay (Cash Mobile) invoice for a wallet deposit and returns the checkout redirect URL."""
        from django.urls import reverse
        from apps.common.models import Currency
        from apps.payments.mtn_pay import MTNPayError

        store = getattr(deposit, "store", None)
        client = self.get_client(store=store)

        currency_code = deposit.currency.code if deposit.currency else "USD"
        if currency_code == "SYP":
            syp_amount = Decimal(str(deposit.amount))
        else:
            syp_currency = (
                Currency.objects.filter(code="SYP", is_active=True).first()
                or Currency.all_objects.filter(code="SYP", is_active=True).first()
            )
            if syp_currency and hasattr(deposit.currency, "to_base"):
                usd_val = deposit.currency.to_base(deposit.amount, "deposit")
                syp_amount = syp_currency.from_base(usd_val, "deposit")
            else:
                syp_amount = Decimal(str(deposit.amount)) * Decimal("15000")

        clean_syp = max(1, int(round(float(syp_amount))))
        try:
            inv_record, raw_resp = client.create_invoice(
                major_amount=Decimal(str(clean_syp)),
                user=deposit.user,
                deposit=deposit,
                ttl=10,
            )
            checkout_url = reverse("mtn_invoice_checkout", args=[inv_record.invoice_number])
            deposit.gateway_payment_id = str(inv_record.invoice_number)
            if not isinstance(deposit.metadata, dict):
                deposit.metadata = {}
            deposit.metadata["mtn_invoice_number"] = inv_record.invoice_number
            deposit.metadata["mtn_url"] = checkout_url
            deposit.metadata["syp_amount"] = clean_syp
            deposit.metadata["payment_provider"] = self.code
            deposit.save(update_fields=["gateway_payment_id", "metadata"])
            return {
                "url": checkout_url,
                "paymentUrl": checkout_url,
                "payment_id": str(inv_record.invoice_number),
                "invoice_number": inv_record.invoice_number,
                "provider": self.code,
                "status": "pending",
                "raw": raw_resp,
            }
        except MTNPayError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_payment(self, deposit):
        from apps.payments.models import MTNPayInvoiceRecord
        from apps.payments.mtn_pay import MTNPayError

        inv_num = deposit.gateway_payment_id or (
            deposit.metadata.get("mtn_invoice_number") if isinstance(deposit.metadata, dict) else None
        )
        if not inv_num:
            rec = MTNPayInvoiceRecord.objects.filter(deposit=deposit).order_by("-created_at").first()
            if rec:
                inv_num = rec.invoice_number
        if not inv_num:
            raise PaymentGatewayError("لا يوجد رقم فاتورة MTNPay مسجل لهذا الإيداع.")

        client = self.get_client(store=getattr(deposit, "store", None))
        try:
            record, resp = client.get_invoice(int(inv_num))
            return {
                "status": "A" if (record and record.is_paid) else "P",
                "is_paid": bool(record and record.is_paid),
                "invoice": int(inv_num),
                "transaction": record.transaction_id if record else "",
                "raw": resp,
            }
        except MTNPayError as err:
            raise PaymentGatewayError(str(err)) from err

    def create_order_payment(self, order, request=None):
        """Creates an MTNPay invoice for a direct product or cart order."""
        from django.urls import reverse
        from apps.common.models import Currency
        from apps.payments.mtn_pay import MTNPayError

        store = getattr(order, "store", None)
        client = self.get_client(store=store)

        syp_currency = None
        if store:
            syp_currency = Currency.all_objects.filter(store=store, code="SYP", is_active=True).first()
        if not syp_currency:
            syp_currency = Currency.all_objects.filter(code="SYP", is_active=True).first()

        exact_amount = (
            Decimal(str(order.total_amount))
            if (order.total_amount and order.total_amount > Decimal("0.00"))
            else Decimal("0.00")
        )
        if exact_amount <= Decimal("0.00"):
            for item in order.items.all():
                exact_amount += Decimal(str(item.unit_price)) * item.quantity
        if exact_amount <= Decimal("0.00"):
            exact_amount = Decimal("1.00")

        syp_rate = Decimal(str(getattr(syp_currency, "buy_rate", 15000) or 15000))
        if syp_rate <= Decimal("1.0"):
            syp_rate = Decimal("15000")

        if syp_currency and float(getattr(syp_currency, "buy_rate", 1) or 1) > 1.0:
            syp_val = syp_currency.from_base(exact_amount, "deposit")
            charge_amount = max(1, int(round(float(syp_val))))
        else:
            charge_amount = max(1, int(round(float(exact_amount * syp_rate))))

        if charge_amount > 50000:
            raise PaymentGatewayError("الحد الأقصى للشراء عبر كاش موبايل هو 50,000 ليرة سورية.")

        try:
            inv_record, raw_resp = client.create_invoice(
                major_amount=Decimal(str(charge_amount)),
                user=order.customer,
                order=order,
                ttl=10,
            )
            checkout_url = reverse("mtn_invoice_checkout", args=[inv_record.invoice_number])
            if not isinstance(order.metadata, dict):
                order.metadata = {}
            order.metadata["gateway_payment_id"] = str(inv_record.invoice_number)
            order.metadata["mtn_invoice_number"] = inv_record.invoice_number
            order.metadata["mtn_url"] = checkout_url
            order.metadata["gateway_charge_amount"] = int(charge_amount)
            order.metadata["gateway_charge_currency"] = "SYP"
            order.metadata["base_usd_amount"] = str(exact_amount)
            order.metadata["exchange_rate"] = str(syp_rate)
            order.metadata["payment_provider"] = self.code
            order.save(update_fields=["metadata"])
            return {
                "url": checkout_url,
                "paymentUrl": checkout_url,
                "payment_id": str(inv_record.invoice_number),
                "invoice_number": inv_record.invoice_number,
                "provider": self.code,
                "status": "pending",
                "raw": raw_resp,
            }
        except MTNPayError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_order_payment(self, order):
        from apps.payments.models import MTNPayInvoiceRecord
        from apps.payments.mtn_pay import MTNPayError

        meta = order.metadata if isinstance(order.metadata, dict) else {}
        inv_num = meta.get("mtn_invoice_number") or meta.get("gateway_payment_id")
        if not inv_num:
            rec = MTNPayInvoiceRecord.objects.filter(order=order).order_by("-created_at").first()
            if rec:
                inv_num = rec.invoice_number
        if not inv_num:
            raise PaymentGatewayError("لا يوجد رقم فاتورة MTNPay مسجل لهذا الطلب.")

        client = self.get_client(store=getattr(order, "store", None))
        try:
            record, resp = client.get_invoice(int(inv_num))
            return {
                "status": "A" if (record and record.is_paid) else "P",
                "is_paid": bool(record and record.is_paid),
                "invoice": int(inv_num),
                "transaction": record.transaction_id if record else "",
                "raw": resp,
            }
        except MTNPayError as err:
            raise PaymentGatewayError(str(err)) from err

    def refund_order_payment(self, order, reason="", amount=None, actor=None):
        """Initiates and confirms a refund for an MTNPay order (`pos_web/invoice/refund/initiate` + `confirm`)."""
        from apps.payments.models import MTNPayInvoiceRecord
        from apps.payments.mtn_pay import MTNPayError

        meta = order.metadata if isinstance(order.metadata, dict) else {}
        inv_num = meta.get("mtn_invoice_number") or meta.get("gateway_payment_id")
        if not inv_num:
            rec = MTNPayInvoiceRecord.objects.filter(order=order).order_by("-created_at").first()
            if rec:
                inv_num = rec.invoice_number
        if not inv_num:
            raise PaymentGatewayError("لا يوجد رقم فاتورة MTNPay مسجل لهذا الطلب.")

        client = self.get_client(store=getattr(order, "store", None))
        try:
            refund_rec, _ = client.initiate_refund(int(inv_num))
            confirmed_rec, res = client.confirm_refund(int(inv_num), int(refund_rec.refund_invoice))
            order.metadata["mtn_refunded"] = True
            order.metadata["mtn_refund_invoice"] = confirmed_rec.refund_invoice
            order.metadata["mtn_refund_data"] = res
            order.save(update_fields=["metadata"])
            return res
        except MTNPayError as err:
            raise PaymentGatewayError(str(err)) from err


def gateway_for(provider_or_obj):
    if hasattr(provider_or_obj, "provider"):
        code = provider_or_obj.provider
        if code == "paymera":
            return PaymeraGateway(integration=provider_or_obj)
        if code == "sham_cash":
            return ShamCashGateway(integration=provider_or_obj)
        if code in ("mtn_pay", "mtn"):
            return MTNPayGateway(integration=provider_or_obj)
    elif hasattr(provider_or_obj, "gateway") and provider_or_obj.gateway:
        return gateway_for(provider_or_obj.gateway)
    elif hasattr(provider_or_obj, "provider_type"):
        code = provider_or_obj.provider_type
    else:
        code = str(provider_or_obj).strip().lower()

    if code in ("paymera", "direct_paymera"):
        return PaymeraGateway()
    if code in ("mtn_pay", "mtn", "direct_mtn_pay"):
        return MTNPayGateway()
    if code in ("sham_cash", "shamcash", "direct_sham_cash"):
        return ShamCashGateway()
    return ShamCashGateway()
