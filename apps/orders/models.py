import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.catalog.models import ProductVariant
from apps.common.models import TimeStampedModel
from apps.common.tenant_utils import TenantManager


class Coupon(TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "نسبة مئوية (%)"
        FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت (USD)"

    code = models.CharField(max_length=40, verbose_name="الكود")
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.PERCENTAGE, verbose_name="نوع الخصم")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة الخصم (%)")
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة الخصم (USD)")
    max_uses = models.PositiveIntegerField(default=0, verbose_name="أقصى عدد استخدام لجميع المستخدمين (0 = غير محدود)")
    max_uses_per_user = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد استخدام لكل مستخدم")
    used_count = models.PositiveIntegerField(default=0, verbose_name="إجمالي عدد المرات التي تم استخدامه")
    min_order_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الحد الأدنى للطلب (USD)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coupons",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    is_verified_only = models.BooleanField(default=True, verbose_name="للحسابات الموثقة فقط")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    valid_for_users_before = models.DateTimeField(null=True, blank=True, verbose_name="صالح للحسابات المسجلة قبل تاريخ")
    valid_for_users_after = models.DateTimeField(null=True, blank=True, verbose_name="صالح للحسابات المسجلة بعد تاريخ")
    
    limit_to_products = models.ManyToManyField("catalog.Product", blank=True, verbose_name="محدد لمنتجات معينة")
    apply_to_all_products = models.BooleanField(default=True, verbose_name="يعمل على جميع المنتجات")
    
    # New Restrictions
    limit_to_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, verbose_name="محدد لعملاء معينين")
    limit_to_tiers = models.JSONField(default=list, blank=True, verbose_name="محدد لفئات معينة (Tiers)")
    limit_to_area = models.CharField(max_length=255, blank=True, verbose_name="محدد لمنطقة معينة (كلمة دلالية)")
    
    class AreaType(models.TextChoices):
        RESIDENCE = "residence", "مكان الإقامة الحالي"
        BIRTH = "birth", "مكان الولادة"
        BOTH = "both", "كلاهما"
        
    allow_area_type = models.CharField(max_length=20, choices=AreaType.choices, default=AreaType.RESIDENCE, verbose_name="نوع المطابقة الجغرافية")
    limit_to_place_of_birth = models.CharField(max_length=255, blank=True, verbose_name="محدد لمحل الولادة (كلمة دلالية)")

    # New Logic (Task 3)
    class MatchMode(models.TextChoices):
        ALL = "all", "يجب تحقق جميع الشروط (AND)"
        ANY = "any", "يكفي تحقق أي شرط واحد (OR)"
        
    match_mode = models.CharField(max_length=10, choices=MatchMode.choices, default=MatchMode.ALL, verbose_name="طريقة المطابقة")

    # IP-based Geographic matching (Task 2)
    limit_to_ip_countries = models.JSONField(default=list, blank=True, verbose_name="محدد لدول معينة (IP-based)")
    limit_to_ip_cities = models.JSONField(default=list, blank=True, verbose_name="محدد لمدن/مناطق معينة (IP-based)")

    class Meta:
        verbose_name = "كوبون"
        verbose_name_plural = "الكوبونات"
        unique_together = ("store", "code")

    def __str__(self):
        return self.code


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد المعالجة"
        SHIPPED = "shipped", "قيد الشحن"
        DELIVERED = "delivered", "مسلّم"
        RETURNED = "returned", "مرتجع"
        COMPLETED = "completed", "مكتمل"
        REFUNDED = "refunded", "مسترد"
        CANCELLED = "cancelled", "ملغى"
        DISPUTED = "disputed", "متنازع عليه"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT, verbose_name="العميل")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    number = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="رقم الطلب")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING, verbose_name="الحالة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المبلغ")
    original_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="المبلغ الأصلي قبل التعديل")
    price_adjustment_reason = models.TextField(blank=True, verbose_name="سبب تعديل السعر")
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="الكوبون")
    fulfillment_data = models.JSONField(default=dict, blank=True, verbose_name="بيانات التنفيذ")
    admin_note = models.TextField(blank=True, verbose_name="ملاحظات المدير")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    is_delivery_read = models.BooleanField(default=False, verbose_name="تمت رؤية المنتج الرقمي")
    api_order_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم الطلب في Alkasr")
    api_order_uuid = models.UUIDField(blank=True, null=True, verbose_name="UUID الطلب في Alkasr")

    # Shipping information for physical products
    shipping_name = models.CharField(max_length=150, blank=True, verbose_name="اسم المستلم")
    shipping_phone = models.CharField(max_length=32, blank=True, verbose_name="رقم هاتف الشحن")
    shipping_address = models.TextField(blank=True, verbose_name="عنوان الشحن")
    shipping_carrier = models.CharField(max_length=100, blank=True, verbose_name="شركة الشحن")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="رقم التتبع")

    @property
    def total_price(self):
        return self.total_amount

    @property
    def subtotal(self):
        return self.original_total or self.total_amount

    @property
    def has_physical_products(self):
        return self.items.filter(variant__product__product_type="physical").exists()

    @property
    def is_app_order(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        if meta.get("client_platform") == "app":
            return True
        ua = meta.get("user_agent", "")
        if "RaqamiyatAndroid" in ua:
            return True
        if self.customer and getattr(self.customer, "is_mobile_app", False):
            return True
        return False

    @property
    def is_paid(self):
        if self.status in [
            self.Status.PROCESSING,
            self.Status.SHIPPED,
            self.Status.DELIVERED,
            self.Status.COMPLETED,
            self.Status.REFUNDED,
        ]:
            return True
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        if meta.get('is_paid') or meta.get('gateway_payment_confirmed') or meta.get('gateway_payment_id'):
            return True
        if meta.get('shamcash_bill_no') and (meta.get('shamcash_refunded') or meta.get('is_paid') or meta.get('status') == 'paid'):
            return True
        return False

    @property
    def platform_badge(self):
        if self.is_app_order:
            return {"type": "app", "label": "تطبيق رقميات", "icon": "fa-mobile-screen-button"}
        return {"type": "browser", "label": "متصفح ويب", "icon": "fa-globe"}

    class Meta:
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_status = Order.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            except Exception:
                pass

        if not self.number:
            self.number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

        if self.status == Order.Status.COMPLETED and old_status != Order.Status.COMPLETED:
            self.generate_recharge_cards()

    def generate_recharge_cards(self):
        from apps.wallets.models import RechargeCard
        from apps.common.models import Currency
        import secrets

        generated_codes = []
        for item in self.items.all():
            variant = item.variant
            if getattr(variant, "is_recharge_card", False):
                for _ in range(item.quantity):
                    code = f"RC-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
                    amount = variant.recharge_amount
                    if amount <= 0:
                        amount = variant.price
                    currency = variant.recharge_currency
                    if not currency:
                        currency = Currency.objects.filter(code="USD").first() or Currency.objects.filter(is_default=True).first()

                    RechargeCard.objects.create(
                        code=code,
                        amount=amount,
                        currency=currency,
                        order=self,
                        status=RechargeCard.Status.ACTIVE,
                        store=self.store
                    )
                    generated_codes.append(code)

        if generated_codes:
            ff_data = dict(self.fulfillment_data or {})
            existing_codes = ff_data.get("أكواد الشحن", "")
            all_codes = [c.strip() for c in existing_codes.split("|") if c.strip()] if existing_codes else []
            all_codes.extend(generated_codes)
            ff_data["أكواد الشحن"] = " | ".join(all_codes)
            Order.objects.filter(pk=self.pk).update(fulfillment_data=ff_data)

    def formatted_metadata(self):
        """Returns a list of dicts with 'label' and 'value' for customer input metadata only."""
        if not self.metadata or not isinstance(self.metadata, dict):
            return []
            
        results = []
        try:
            first_item = self.items.first()
        except Exception:
            first_item = None
        schema = {}
        if first_item and getattr(first_item, "variant", None) and getattr(first_item.variant, "product", None):
            schema = first_item.variant.product.form_schema
            
        fields = schema.get("fields", []) if isinstance(schema, dict) else []
        
        # Create a mapping of field key to human label
        label_map = {}
        for f in fields:
            if isinstance(f, dict):
                lbl = f.get("label", "")
                fid = f.get("name") or f.get("id") or f.get("key") or lbl
                if fid:
                    label_map[str(fid).strip()] = str(lbl).strip() if lbl else str(fid).strip()
        
        # If the product defines explicit form schema fields, strictly return ONLY those fields!
        if label_map:
            for key, lbl in label_map.items():
                if key in self.metadata and self.metadata[key] not in (None, "") and not isinstance(self.metadata[key], (dict, list)):
                    results.append({"label": lbl, "value": self.metadata[key]})
            if results:
                return results

        # Fallback if no schema is defined:
        # Strictly exclude all technical/internal/gateway/refund/calculation keys:
        SYSTEM_KEY_PREFIXES = (
            "api", "paymera", "shamcash", "gateway", "payment", "refund", "alkasr",
            "tafa3ol", "checkout", "stripe", "direct_", "is_", "has_", "csrf", "session",
            "cookie", "cart", "external", "raw_", "ff_", "provider", "order_", "exchange",
            "base_", "currency_", "selected_", "displayed_"
        )
        EXCLUDED_KEYS = {
            "api_provider", "api_status", "api_last_response", "api_refunded",
            "response", "api_response", "api_error", "alkasr", "provider",
            "provider_order_id", "api_order_id", "api_order_uuid", "provider_id",
            "raw_response", "external_id", "external_order_id", "api",
            "payment_gateway", "payment_provider", "gateway_payment_id", "is_direct_gateway_purchase",
            "direct_gateway_purchase", "gateway_order", "direct_gateway", "checkout_session_id",
            "stripe_session_id", "transaction_id", "payment_id", "payment_reference",
            "payment_method", "client_secret", "payment_status", "order_channel",
            "paymera_url", "paymera_payment_id", "syp_amount", "paymera",
            "gateway_charge_amount", "gateway_charge_currency", "tafa3ol",
            "notes", "admin_notes", "price_adjustment_reason", "is_paid",
            "exchange_rate", "base_usd_amount", "currency_places", "selected_currency",
            "displayed_unit_price", "shamcash_url", "shamcash_bill_no", "shamcash_refunded",
            "shamcash_refund_actor", "shamcash_refund_reason", "shamcash_refund_tran_id",
            "shamcash_refund_timestamp", "refund_reason", "refund_status", "refund_requested",
            "refund_approved_at", "refund_approved_by", "refund_requested_at",
            "refund_rejection_reason", "gateway_currency", "bill_no", "tran_id",
            "gateway_payment_confirmed", "paymera_otp", "actor", "timestamp"
        }
        COMMON_LABELS = {
            "player_id": "آيدي اللاعب",
            "playerid": "آيدي اللاعب",
            "player_name": "اسم اللاعب",
            "account_id": "معرف الحساب",
            "user_id": "معرف المستخدم",
            "server": "السيرفر",
            "server_id": "معرف السيرفر",
            "zone": "المنطقة / الزون",
            "zone_id": "معرف المنطقة (Zone ID)",
            "character_name": "اسم الشخصية",
            "username": "اسم المستخدم",
            "whatsapp": "رقم الواتساب",
            "phone": "رقم الهاتف",
            "email": "البريد الإلكتروني",
            "link": "الرابط",
            "url": "الرابط",
            "profile_url": "رابط الحساب",
            "national_id": "الرقم الوطني",
        }

        for key, val in self.metadata.items():
            if val is None or val == "" or isinstance(val, (dict, list)):
                continue
            k_str = str(key).strip()
            k_lower = k_str.lower()
            if (
                k_lower in EXCLUDED_KEYS
                or any(k_lower.startswith(p) for p in SYSTEM_KEY_PREFIXES)
                or (any(k_lower.endswith(s) for s in ("_id", "_key", "_token", "_url", "_secret", "_status", "_at", "_by", "_code", "_rate", "_actor", "_reason", "_timestamp"))
                    and k_lower not in ("player_id", "server_id", "zone_id", "account_id", "user_id"))
            ):
                continue
            label = label_map.get(k_str) or COMMON_LABELS.get(k_lower, k_str)
            results.append({"label": label, "value": val})
                
        return results

    @property
    def is_refund_pending(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        return (
            (meta.get("refund_status") == "pending" or meta.get("refund_requested") is True)
            and meta.get("refund_status") not in ("approved", "rejected")
            and self.status not in (self.Status.REFUNDED, self.Status.CANCELLED)
        )

    @property
    def is_refund_approved(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        return (
            meta.get("refund_status") == "approved"
            or meta.get("shamcash_refunded") is True
            or meta.get("paymera_refunded") is True
            or self.status == self.Status.REFUNDED
        )

    @property
    def refund_reason_text(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        return meta.get("refund_reason") or meta.get("shamcash_refund_reason") or meta.get("reason") or ""

    @property
    def refund_details(self):
        """Returns structured human-friendly refund details."""
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        if not (meta.get("refund_requested") or meta.get("refund_status") or self.status == self.Status.REFUNDED or meta.get("shamcash_refunded") or meta.get("paymera_refunded")):
            return None
        
        status_val = meta.get("refund_status") or ("approved" if (self.status == self.Status.REFUNDED or meta.get("shamcash_refunded")) else "pending")
        status_display_map = {
            "pending": "بانتظار قرار الإدارة",
            "approved": "تمت الموافقة واسترداد المبلغ للعميل",
            "rejected": "مرفوض من الإدارة",
        }
        return {
            "status": status_val,
            "status_display": status_display_map.get(status_val, status_val),
            "reason": meta.get("refund_reason") or meta.get("shamcash_refund_reason") or "طلب استرداد من العميل",
            "requested_at": meta.get("refund_requested_at"),
            "approved_at": meta.get("refund_approved_at"),
            "approved_by": meta.get("refund_approved_by") or meta.get("shamcash_refund_actor"),
            "rejection_reason": meta.get("refund_rejection_reason"),
            "gateway_tran_id": meta.get("shamcash_refund_tran_id") or meta.get("paymera_refund_tran_id"),
            "is_gateway_refunded": bool(meta.get("shamcash_refunded") or meta.get("paymera_refunded")),
        }

    @property
    def payment_currency_summary(self):
        """Returns clean, formatted payment currency & conversion details."""
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        
        amt = meta.get("syp_amount") or meta.get("gateway_charge_amount")
        curr = (meta.get("selected_currency") or meta.get("gateway_charge_currency") or ("SYP" if meta.get("syp_amount") else None) or "").upper()
        
        rate_val = meta.get("exchange_rate")
        try:
            rate_float = float(rate_val) if rate_val else None
        except (ValueError, TypeError):
            rate_float = None

        base_usd = meta.get("base_usd_amount") or self.total_amount
        try:
            usd_float = float(base_usd) if base_usd else None
        except (ValueError, TypeError):
            usd_float = None

        syp_val = meta.get("syp_amount") or (amt if curr == "SYP" else None)
        try:
            syp_float = float(syp_val) if syp_val else None
        except (ValueError, TypeError):
            syp_float = None

        if not syp_float and usd_float and rate_float:
            syp_float = usd_float * rate_float

        if not usd_float and syp_float and rate_float and rate_float > 0:
            usd_float = syp_float / rate_float

        is_syp = (curr == "SYP") or (meta.get("syp_amount") is not None) or ("sham" in str(self.payment_method_display).lower())

        return {
            "is_syp": is_syp,
            "currency": "SYP" if is_syp else (curr or "USD"),
            "syp_amount": f"{syp_float:,.0f}" if syp_float else None,
            "usd_amount": f"{usd_float:.2f}" if usd_float else f"{self.total_amount}",
            "exchange_rate": f"{rate_float:,.0f}" if rate_float else (str(rate_val) if rate_val else None),
            "raw_amount": amt or self.total_amount,
        }

    @property
    def gateway_reference_id(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        return (
            meta.get("gateway_payment_id")
            or meta.get("shamcash_bill_no")
            or meta.get("paymera_payment_id")
            or meta.get("bill_no")
            or meta.get("tran_id")
            or meta.get("payment_id")
            or meta.get("transaction_id")
            or meta.get("checkout_session_id")
            or meta.get("external_id")
            or meta.get("provider_order_id")
            or self.api_order_id
            or None
        )

    @property
    def payment_method_display(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        gw = (
            meta.get("payment_gateway")
            or meta.get("payment_provider")
            or meta.get("gateway")
            or meta.get("provider")
            or meta.get("payment_method")
        )
        gw_str = str(gw or "").strip().lower()
        if "paymera" in gw_str or meta.get("paymera_url") or meta.get("paymera_payment_id"):
            return "بيميرا (Paymera)"
        elif "sham" in gw_str or meta.get("shamcash_url") or meta.get("shamcash_bill_no"):
            return "شام كاش (Sham Cash)"
        elif "fmp" in gw_str:
            return "بوابة FMP"
        elif gw and str(gw).strip() and "بوابة" not in str(gw):
            return str(gw).strip()
            
        if getattr(self, "payment_method", None):
            try:
                if getattr(self.payment_method, "gateway", None):
                    gw_prov = getattr(self.payment_method.gateway, "provider", "")
                    if "sham" in gw_prov.lower():
                        return "شام كاش (Sham Cash)"
                    elif "paymera" in gw_prov.lower():
                        return "بيميرا (Paymera)"
                    if self.payment_method.gateway.name:
                        return self.payment_method.gateway.name
                pm_name = self.payment_method.name
                if pm_name and "بوابة" not in pm_name:
                    return pm_name
            except Exception:
                pass

        if meta.get("is_direct_gateway_purchase") or meta.get("direct_gateway_purchase"):
            try:
                from apps.payments.models import ShamCashBillRecord
                if ShamCashBillRecord.objects.filter(order=self).exists():
                    return "شام كاش (Sham Cash)"
            except Exception:
                pass
            return "بيميرا (Paymera)"

        return "محفظة رقميات"

    @property
    def gateway_invoice_url(self):
        """
        Returns direct invoice/payment link at provider (ShamCash or Paymera).
        """
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        url = (
            meta.get("shamcash_url")
            or meta.get("paymera_url")
            or meta.get("payment_url")
            or meta.get("invoice_url")
        )
        if url:
            return url
        try:
            from apps.payments.models import ShamCashBillRecord
            rec = ShamCashBillRecord.objects.filter(order=self).order_by("-created_at").first()
            if rec and rec.payment_url:
                return rec.payment_url
        except Exception:
            pass
        return None

    @property
    def gateway_info_summary(self):
        """
        Returns structured dictionary of gateway provider details.
        """
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        prov = meta.get("payment_provider") or meta.get("payment_gateway")
        gw_id = meta.get("gateway_payment_id") or meta.get("shamcash_bill_no") or meta.get("paymera_payment_id")
        tran_id = meta.get("tran_id") or meta.get("transaction_id") or meta.get("rrn") or meta.get("gateway_rrn")
        amt = meta.get("gateway_charge_amount") or meta.get("syp_amount")
        curr = meta.get("gateway_charge_currency") or ("SYP" if meta.get("syp_amount") else "USD")
        status_name = meta.get("gateway_payment_status") or meta.get("payment_status")

        invoice_url = self.gateway_invoice_url

        try:
            from apps.payments.models import ShamCashBillRecord
            rec = ShamCashBillRecord.objects.filter(order=self).order_by("-created_at").first()
            if rec:
                if not gw_id:
                    gw_id = rec.bill_no
                if not tran_id and rec.tran_id:
                    tran_id = rec.tran_id
                if not amt:
                    amt = rec.amount
                if not curr:
                    curr = rec.currency_code
                if not status_name:
                    status_name = rec.status_name
                if not invoice_url and rec.payment_url:
                    invoice_url = rec.payment_url
                if not prov:
                    prov = "sham_cash"
        except Exception:
            pass

        if not gw_id and not invoice_url and not prov and not meta.get("is_direct_gateway_purchase"):
            return None

        display_status = status_name
        if str(status_name).lower() in ("a", "accepted", "paid", "4"):
            display_status = "مدفوع بنجاح (Paid)"
        elif str(status_name).lower() in ("pending", "1"):
            display_status = "بانتظار السداد (Pending)"
        elif str(status_name).lower() in ("refund", "refunded", "2"):
            display_status = "مسترد (Refunded)"
        elif str(status_name).lower() in ("expired", "3", "5", "failed"):
            display_status = "منتهي / ملغي"

        return {
            "provider": prov or "gateway",
            "provider_name": self.payment_method_display,
            "invoice_url": invoice_url,
            "payment_id": gw_id,
            "tran_id": tran_id,
            "amount": amt,
            "currency": curr,
            "status": display_status or ("مدفوع" if meta.get("is_paid") else "بانتظار التأكيد"),
            "is_paid": bool(meta.get("is_paid") or meta.get("gateway_payment_confirmed")),
        }

    @property
    def payment_gateway_charge_info(self):
        meta = self.metadata if isinstance(self.metadata, dict) else {}
        amt = meta.get("gateway_charge_amount") or meta.get("syp_amount")
        curr = meta.get("gateway_charge_currency") or ("SYP" if meta.get("syp_amount") else None)
        if amt:
            return {
                "amount": str(amt),
                "currency": curr or "SYP",
                "gateway": self.payment_method_display,
                "is_direct": True,
            }
        elif meta.get("is_direct_gateway_purchase") or meta.get("payment_gateway"):
            return {
                "amount": str(self.total_amount),
                "currency": "USD",
                "gateway": self.payment_method_display,
                "is_direct": True,
            }
        return None

    def get_server_responses(self):
        """
        Returns a list of structured server response dictionaries:
        [
            {
                "text": "...",
                "avatar": "https://...",
                "account_name": "...",
                "status_msg": "...",
                "package_info": "...",
                "reason": "...",
            },
            ...
        ]
        Extracts from fulfillment_data, metadata, OrderLogs, and ProviderOrders.
        """
        from apps.orders.provider_status import parse_server_response_details, extract_clean_text
        import re

        raw_candidates = []
        seen_texts = set()

        ff = self.fulfillment_data or {}
        meta = self.metadata or {}
        
        # 1. Direct lists or fields in fulfillment_data
        for key in ("all_server_responses", "server_responses", "ردود السيرفر"):
            val = ff.get(key)
            if isinstance(val, list):
                for item in val:
                    if item:
                        raw_candidates.append(item)
            elif isinstance(val, str) and val.strip():
                raw_candidates.append(val.strip())

        for key in (
            "رد السيرفر", "سبب الإلغاء من السيرفر", "كود التفعيل / البطاقة",
            "replay", "replay_api", "notes", "note", "msg", "message",
            "details", "server_response", "reason"
        ):
            val = ff.get(key)
            if val and not isinstance(val, (dict, list)):
                raw_candidates.append(val)

        # 2. Check metadata
        for key in (
            "server_response", "replay", "replay_api",
            "msg", "message", "notes", "note", "reason"
        ):
            val = meta.get(key)
            if val and not isinstance(val, (dict, list)):
                raw_candidates.append(val)

        # 3. Extract from OrderLogs (captures historical provider updates)
        try:
            for log in self.logs.all():
                note = log.note or ""
                matches = re.findall(r'\((?:رد السيرفر|سبب الإلغاء من السيرفر):\s*([^)]+)\)', note)
                for m in matches:
                    if m.strip():
                        raw_candidates.append(m.strip())
        except Exception:
            pass

        # 4. Check ProviderOrder status history if available
        try:
            for po in self.provider_orders.all():
                for sh in po.status_history.all():
                    if sh.raw_response:
                        raw_candidates.append(sh.raw_response)
        except Exception:
            pass

        # 5. Admin note if any
        if getattr(self, 'admin_note', None):
            raw_candidates.append(self.admin_note)

        # 6. Process each candidate and deduplicate
        structured_responses = []
        avatar_global = ff.get("صورة الحساب / الأفاتار") or ff.get("image_url") or meta.get("avatar") or meta.get("image_url")

        for cand in raw_candidates:
            if not cand:
                continue
            cand_img = None
            if isinstance(cand, dict):
                cand_img = cand.get("image_url") or cand.get("avatar")
                c_text = cand.get("clean_text") or cand.get("text") or cand.get("raw") or extract_clean_text(cand)
            else:
                c_text = extract_clean_text(cand)

            if not c_text or not str(c_text).strip():
                continue

            parsed = parse_server_response_details(str(c_text).strip())
            display_text = parsed.get("clean_text") or parsed.get("raw_clean") or str(c_text).strip()
            from apps.orders.error_codes import sanitize_text_for_customer
            display_text = sanitize_text_for_customer(display_text)

            if not display_text or display_text in seen_texts:
                continue

            # Skip technical internal status words alone
            if display_text.lower() in ("completed", "processing", "pending", "success", "failed", "cancelled", "none", "null", "ok"):
                continue

            # Skip if this text is an exact substring of an already recorded response
            if any(display_text in st for st in seen_texts):
                continue

            seen_texts.add(display_text)
            avatar = parsed.get("image_url") or cand_img or avatar_global
            clean_reason = sanitize_text_for_customer(parsed.get("reason")) if parsed.get("reason") else None

            structured_responses.append({
                "text": display_text,
                "avatar": avatar,
                "account_name": parsed.get("account_name"),
                "status_msg": parsed.get("status_msg"),
                "package_info": parsed.get("package_info"),
                "reason": clean_reason,
            })

        return structured_responses

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
        ]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE, verbose_name="الطلب")
    variant = models.ForeignKey(ProductVariant, related_name="order_items", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الباقة")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="سعر الوحدة")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0.00000000"), verbose_name="تكلفة الوحدة")
    total_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="السعر الإجمالي")

    class Meta:
        verbose_name = "بند طلب"
        verbose_name_plural = "بنود الطلبات"

    def __str__(self):
        return f"{self.order.number} - {self.variant}"


class OrderLog(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="logs", on_delete=models.CASCADE, verbose_name="الطلب")
    status = models.CharField(max_length=20, choices=Order.Status.choices, verbose_name="الحالة")
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="من قبل")

    class Meta:
        verbose_name = "سجل طلب"
        verbose_name_plural = "سجلات الطلبات"
        ordering = ["created_at"]


class Invoice(TimeStampedModel):
    order = models.OneToOneField(Order, related_name="invoice", on_delete=models.CASCADE, verbose_name="الطلب")
    invoice_number = models.CharField(max_length=40, unique=True, verbose_name="رقم الفاتورة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ الإجمالي")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإصدار")

    class Meta:
        verbose_name = "فاتورة"
        verbose_name_plural = "الفواتير"
