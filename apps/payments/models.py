from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel
from apps.common.tenant_utils import TenantManager


class PaymentMethod(TimeStampedModel):
    # General Information
    name = models.CharField(max_length=120, verbose_name="اسم الوسيلة")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_methods",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    logo = models.ImageField(upload_to="payment-methods/logos/", blank=True, null=True, verbose_name="الشعار")
    method_type = models.CharField(max_length=100, verbose_name="نوع الوسيلة (مثلاً: بنك، محفظة)")
    description = models.TextField(blank=True, verbose_name="وصف الوسيلة")
    display_order = models.PositiveIntegerField(default=0, blank=True, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_maintenance_mode = models.BooleanField(default=False, verbose_name="وضع الصيانة")
    requires_kyc = models.BooleanField(default=False, verbose_name="يتطلب توثيق الهوية (KYC)", help_text="إذا تم تفعيله، لن تظهر هذه الوسيلة إلا للمستخدمين الموثقين.")
    
    # --- New Limit Fields ---
    is_unlimited = models.BooleanField(default=False, verbose_name="بلا حدود للوسيلة", help_text="عند التفعيل لا يوجد حد يومي أو شهري لوسيلة الدفع، مع التقيد بحدود حساب المستخدم.")
    daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد الإيداع اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD. 0 تعني غير محدود.")
    daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد السحب اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD. 0 تعني غير محدود.")
    monthly_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="حد الإيداع الشهري لهذه الوسيلة", help_text="القيمة بالدولار USD. 0 تعني غير محدود.")
    monthly_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="حد السحب الشهري لهذه الوسيلة", help_text="القيمة بالدولار USD. 0 تعني غير محدود.")
    
    # --- Daily & Monthly Usage Tracking ---
    daily_deposit_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    daily_withdrawal_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    monthly_deposit_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    monthly_withdrawal_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    last_limit_reset = models.DateTimeField(default=timezone.now)
    last_monthly_limit_reset = models.DateTimeField(default=timezone.now)

    # --- Global Cap ---
    global_deposit_cap = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الحد الإجمالي الأقصى للإيداعات", help_text="عند الوصول لهذا الحد، تتوقف الوسيلة تلقائياً. 0 تعني غير محدود.")
    global_deposit_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي الإيداعات الحالية (للمتابعة والحد الأقصى)")

    global_withdrawal_cap = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الحد الإجمالي الأقصى للسحوبات", help_text="عند الوصول لهذا الحد، تتوقف الوسيلة تلقائياً. 0 تعني غير محدود.")
    global_withdrawal_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي السحوبات الحالية")

    # --- Deposit Configuration ---
    deposit_info_schema = models.JSONField(default=dict, blank=True, verbose_name="بيانات الإيداع الثابتة (للعرض)", help_text='{"version": 1, "rows": [{"title": "IBAN", "value": "TR...", "copyable": true}]}')
    deposit_form_schema = models.JSONField(default=dict, blank=True, verbose_name="حقول الإيداع المطلوبة من العميل", help_text='{"version": 1, "fields": [{"label": "TXID", "type": "text", "required": true}]}')
    deposit_fee_settings = models.JSONField(default=dict, blank=True, verbose_name="إعدادات رسوم الإيداع", help_text='{"fixed": 0, "percent": 0, "min": 0, "max": 0, "enabled": true}')
    deposit_min_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10.00"), verbose_name="الحد الأدنى للإيداع", help_text="القيمة بالدولار USD وسيتم تحويلها تلقائياً")
    deposit_max_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="الحد الأقصى للإيداع", help_text="القيمة بالدولار USD وسيتم تحويلها تلقائياً")
    deposit_instructions = models.TextField(blank=True, verbose_name="تعليمات الإيداع")
    deposit_qr_image = models.ImageField(upload_to="payment-methods/qr/", blank=True, null=True, verbose_name="صورة QR للإيداع")

    # --- Withdrawal Configuration ---
    withdrawal_info_schema = models.JSONField(default=dict, blank=True, verbose_name="بيانات السحب الثابتة (للعرض)", help_text='{"version": 1, "rows": [{"title": "Processing Time", "value": "24h"}]}')
    withdrawal_form_schema = models.JSONField(default=dict, blank=True, verbose_name="حقول السحب المطلوبة من العميل", help_text='{"version": 1, "fields": [{"label": "Binance UID", "type": "text", "required": true}]}')
    withdrawal_fee_settings = models.JSONField(default=dict, blank=True, verbose_name="إعدادات رسوم السحب", help_text='{"fixed": 0, "percent": 0, "min": 0, "max": 0, "enabled": true}')
    withdrawal_min_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10.00"), verbose_name="الحد الأدنى للسحب", help_text="القيمة بالدولار USD وسيتم تحويلها تلقائياً")
    withdrawal_max_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="الحد الأقصى للسحب", help_text="القيمة بالدولار USD وسيتم تحويلها تلقائياً")
    withdrawal_instructions = models.TextField(blank=True, verbose_name="تعليمات السحب")
    
    # --- Advanced Financial ---
    capital_exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("1.000000"), verbose_name="سعر صرف رأس المال الداخلي (التكلفة)", help_text="سعر التكلفة الداخلي لهذه الوسيلة مقابل الدولار لحساب الأرباح الحقيقية.")
    
    deposit_exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True, verbose_name="سعر صرف الإيداع (التكلفة)", help_text="سعر صرف مخصص لعمليات الإيداع لهذه الوسيلة. إذا ترك فارغاً سيتم اعتماد السعر الافتراضي.")
    withdrawal_exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True, verbose_name="سعر صرف السحب (الربح)", help_text="سعر صرف مخصص لعمليات السحب لهذه الوسيلة. إذا ترك فارغاً سيتم اعتماد السعر الافتراضي.")

    supported_currencies = models.ManyToManyField("common.Currency", blank=True, verbose_name="العملات المدعومة")
    gateway = models.ForeignKey(
        "payments.PaymentGatewayIntegration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_methods",
        verbose_name="بوابة الدفع الإلكترونية المرتبطة",
        help_text="في حال تحديد بوابة دفع إلكترونية، سيتم توجيه العميل للدفع الإلكتروني التلقائي."
    )
    can_deposit = models.BooleanField(default=True, verbose_name="متاحة للإيداع")
    can_withdraw = models.BooleanField(default=False, verbose_name="متاحة للسحب")

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "وسيلة دفع"
        verbose_name_plural = "وسائل الدفع"

    def add_deposit_usage(self, amount_in_usd):
        self.reset_daily_limits_if_needed()
        amt = Decimal(str(amount_in_usd))
        self.daily_deposit_usage += amt
        self.monthly_deposit_usage += amt
        self.global_deposit_usage += amt
        
        # Task 5: Check Global Cap
        if self.global_deposit_cap > 0 and self.global_deposit_usage >= self.global_deposit_cap:
            self.is_maintenance_mode = True
            
            # Send Notification to Staff
            from apps.notifications.services import notify_staff
            notify_staff(
                title="تم الوصول للحد الإجمالي لوسيلة دفع",
                body=f"وصلت وسيلة الدفع {self.name} إلى الحد الإجمالي المسموح ({self.global_deposit_cap} USD). تم تفعيل وضع الصيانة تلقائياً.",
                action_url=f"/control/payment-methods/{self.id}/edit/"
            )
            
        self.save(update_fields=["daily_deposit_usage", "monthly_deposit_usage", "global_deposit_usage", "is_maintenance_mode"])

    def add_withdrawal_usage(self, amount_in_usd):
        self.reset_daily_limits_if_needed()
        amt = Decimal(str(amount_in_usd))
        self.daily_withdrawal_usage += amt
        self.monthly_withdrawal_usage += amt
        self.global_withdrawal_usage += amt
        
        # Check Global Cap
        if self.global_withdrawal_cap > 0 and self.global_withdrawal_usage >= self.global_withdrawal_cap:
            self.is_maintenance_mode = True
            from apps.notifications.services import notify_staff
            notify_staff(
                title="تم الوصول للحد الإجمالي لسحوبات وسيلة دفع",
                body=f"وصلت وسيلة الدفع {self.name} إلى الحد الإجمالي للسحوبات ({self.global_withdrawal_cap} USD). تم تفعيل وضع الصيانة تلقائياً.",
                action_url=f"/control/payment-methods/{self.id}/edit/"
            )
            
        self.save(update_fields=["daily_withdrawal_usage", "monthly_withdrawal_usage", "global_withdrawal_usage", "is_maintenance_mode"])

    def reset_daily_limits_if_needed(self):
        """Resets daily usage at 12:00 AM midnight and monthly usage at 12:00 AM on the 1st of each month (local time)."""
        from django.utils import timezone
        now = timezone.localtime(timezone.now())
        update_fields = []
        last_reset_local = timezone.localtime(self.last_limit_reset)
        if last_reset_local.date() < now.date():
            self.daily_deposit_usage = Decimal("0.00")
            self.daily_withdrawal_usage = Decimal("0.00")
            self.last_limit_reset = now
            update_fields.extend(["daily_deposit_usage", "daily_withdrawal_usage", "last_limit_reset"])

        last_monthly_local = timezone.localtime(self.last_monthly_limit_reset or self.last_limit_reset)
        if (last_monthly_local.year, last_monthly_local.month) < (now.year, now.month):
            self.monthly_deposit_usage = Decimal("0.00")
            self.monthly_withdrawal_usage = Decimal("0.00")
            self.last_monthly_limit_reset = now
            update_fields.extend(["monthly_deposit_usage", "monthly_withdrawal_usage", "last_monthly_limit_reset"])

        if update_fields:
            self.save(update_fields=update_fields)

    def get_effective_deposit_limits(self, user=None, currency=None):
        """
        Computes (min_amount, max_amount) in the given currency (or USD if None),
        respecting both the payment method's configured limits (or is_unlimited)
        and the user's account daily/custom limits.
        """
        self.reset_daily_limits_if_needed()

        # 1. Method limit in USD
        if self.is_unlimited:
            method_remaining = Decimal("999999999.99")
        else:
            candidates = []
            if self.deposit_max_amount and self.deposit_max_amount > 0:
                candidates.append(self.deposit_max_amount)
            if self.daily_deposit_limit and self.daily_deposit_limit > 0:
                candidates.append(max(Decimal("0.00"), self.daily_deposit_limit - self.daily_deposit_usage))
            if self.monthly_deposit_limit and self.monthly_deposit_limit > 0:
                candidates.append(max(Decimal("0.00"), self.monthly_deposit_limit - self.monthly_deposit_usage))
            if self.global_deposit_cap and self.global_deposit_cap > 0:
                candidates.append(max(Decimal("0.00"), self.global_deposit_cap - self.global_deposit_usage))
            method_remaining = min(candidates) if candidates else Decimal("999999999.99")

        # 2. User account limit in USD
        user_remaining = Decimal("999999999.99")
        if user and user.is_authenticated:
            user.reset_daily_limits_if_needed()
            user_remaining = max(Decimal("0.00"), user.daily_deposit_limit - user.daily_deposit_usage)

            if user.has_custom_limits and user.custom_payment_limits and isinstance(user.custom_payment_limits, dict):
                user_custom = (
                    user.custom_payment_limits.get(str(self.id))
                    or (user.custom_payment_limits.get(self.id.hex) if hasattr(self.id, "hex") else None)
                )
                if isinstance(user_custom, dict) and user_custom.get("deposit"):
                    try:
                        custom_limit = Decimal(str(user_custom["deposit"]))
                        method_remaining = custom_limit
                    except Exception:
                        pass

        effective_max_usd = min(method_remaining, user_remaining)
        min_usd = self.deposit_min_amount or Decimal("0.00")

        if currency:
            min_val = currency.from_base(min_usd, "deposit")
            max_val = currency.from_base(effective_max_usd, "deposit")
            # For MTN Cash Mobile in SYP, enforce gateway's 50,000 SYP daily purchase cap unless method is unlimited
            gw_provider = self.gateway.provider if getattr(self, "gateway", None) else ""
            if gw_provider == "mtn_pay" and str(currency.code).upper() == "SYP":
                min_val = max(min_val, Decimal("1.00"))
                if not self.is_unlimited:
                    max_val = min(max_val, Decimal("50000.00"))
        else:
            min_val = min_usd
            max_val = effective_max_usd

        if max_val < Decimal("0.00"):
            max_val = Decimal("0.00")
        return min_val, max_val

    def to_deposit_json(self, user=None):
        import json
        from django.core.serializers.json import DjangoJSONEncoder

        self.reset_daily_limits_if_needed()
        currencies_data = []
        effective_rate = self.get_effective_deposit_rate()
        for c in self.supported_currencies.all():
            min_val, max_val = self.get_effective_deposit_limits(user=user, currency=c)
            currencies_data.append({
                "id": str(c.id), 
                "code": c.code, 
                "symbol": c.symbol,
                "min_amount": float(min_val),
                "max_amount": float(max_val),
                "exchange_rate": float(effective_rate)
            })

        return json.dumps({
            "id": str(self.id),
            "name": self.name,
            "instructions": self.deposit_instructions,
            "qr": self.deposit_qr_image.url if self.deposit_qr_image else "",
            "static_info": self.deposit_info_schema if isinstance(self.deposit_info_schema, dict) and "rows" in self.deposit_info_schema else {"rows": []},
            "form_schema": self.deposit_form_schema if isinstance(self.deposit_form_schema, dict) and "fields" in self.deposit_form_schema else {"fields": []},
            "fees": {
                "fixed": float(self.deposit_fee_settings.get("fixed", 0)) if isinstance(self.deposit_fee_settings, dict) else 0,
                "percent": float(self.deposit_fee_settings.get("percent", 0)) if isinstance(self.deposit_fee_settings, dict) else 0,
                "min": float(self.deposit_fee_settings.get("min", 0)) if isinstance(self.deposit_fee_settings, dict) else 0,
                "max": float(self.deposit_fee_settings.get("max", 0)) if isinstance(self.deposit_fee_settings, dict) else 0,
                "enabled": self.deposit_fee_settings.get("enabled", True) if isinstance(self.deposit_fee_settings, dict) else True
            },
            "currencies": currencies_data
        }, cls=DjangoJSONEncoder)

    def to_withdrawal_json(self, user=None):
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        from apps.common.models import Currency
        from django.utils import timezone

        self.reset_daily_limits_if_needed()
        usd = Currency.objects.filter(code="USD").first()

        # 1. Global Method Remaining
        method_remaining = max(Decimal("0.00"), self.daily_withdrawal_limit - self.daily_withdrawal_usage)
        
        # 2. User Remaining
        user_remaining = Decimal("9999999.99")
        if user and user.is_authenticated:
            user.reset_daily_limits_if_needed()
            user_remaining = max(Decimal("0.00"), user.daily_withdrawal_limit - user.daily_withdrawal_usage)
            
            if user.has_custom_limits and user.custom_payment_limits and isinstance(user.custom_payment_limits, dict):
                user_custom = user.custom_payment_limits.get(str(self.id)) or user.custom_payment_limits.get(self.id.hex) if hasattr(self.id, 'hex') else user.custom_payment_limits.get(str(self.id))
                if isinstance(user_custom, dict) and user_custom.get('withdraw'):
                    try:
                        method_remaining = Decimal(str(user_custom['withdraw']))
                    except: pass
        
        effective_withdrawal_max = min(method_remaining, user_remaining)
        
        # 3. Cap by per-transaction max
        effective_withdrawal_max = min(effective_withdrawal_max, self.withdrawal_max_amount)

        currencies_data = []
        effective_rate = self.get_effective_withdrawal_rate()
        for c in self.supported_currencies.all():
            # Convert USD limits to this currency
            min_val = c.from_base(self.withdrawal_min_amount) if usd else self.withdrawal_min_amount
            max_val = c.from_base(effective_withdrawal_max) if usd else effective_withdrawal_max
            currencies_data.append({
                "id": str(c.id), 
                "code": c.code, 
                "symbol": c.symbol,
                "min_amount": float(min_val),
                "max_amount": float(max_val),
                "exchange_rate": float(effective_rate)
            })

        return json.dumps({
            "id": str(self.id),
            "name": self.name,
            "instructions": self.withdrawal_instructions,
            "static_info": self.withdrawal_info_schema if isinstance(self.withdrawal_info_schema, dict) and "rows" in self.withdrawal_info_schema else {"rows": []},
            "form_schema": self.withdrawal_form_schema if isinstance(self.withdrawal_form_schema, dict) and "fields" in self.withdrawal_form_schema else {"fields": []},
            "fees": {
                "fixed": float(self.withdrawal_fee_settings.get("fixed", 0)) if isinstance(self.withdrawal_fee_settings, dict) else 0,
                "percent": float(self.withdrawal_fee_settings.get("percent", 0)) if isinstance(self.withdrawal_fee_settings, dict) else 0,
                "min": float(self.withdrawal_fee_settings.get("min", 0)) if isinstance(self.withdrawal_fee_settings, dict) else 0,
                "max": float(self.withdrawal_fee_settings.get("max", 0)) if isinstance(self.withdrawal_fee_settings, dict) else 0,
                "enabled": self.withdrawal_fee_settings.get("enabled", True) if isinstance(self.withdrawal_fee_settings, dict) else True
            },
            "currencies": currencies_data
        }, cls=DjangoJSONEncoder)

    def calculate_fee(self, amount, mode="deposit"):
        """Calculates granular fee based on mode."""
        settings = self.deposit_fee_settings if mode == "deposit" else self.withdrawal_fee_settings
        if not settings or not settings.get("enabled", True):
            return Decimal("0.00")
            
        fixed = Decimal(str(settings.get("fixed", 0)))
        percent = Decimal(str(settings.get("percent", 0)))
        min_fee = Decimal(str(settings.get("min", 0)))
        max_fee = Decimal(str(settings.get("max", 0)))
        
        calculated = fixed + (Decimal(str(amount)) * percent / 100)
        
        if min_fee > 0:
            calculated = max(calculated, min_fee)
        if max_fee > 0:
            calculated = min(calculated, max_fee)
            
        return calculated

    def get_effective_deposit_rate(self):
        from apps.common.models import Currency
        if self.deposit_exchange_rate:
            return self.deposit_exchange_rate
        default_currency = Currency.objects.filter(is_default=True).first()
        if default_currency:
            return default_currency.buy_rate
        return Decimal("1.000000")

    @property
    def currency(self):
        first = self.supported_currencies.first()
        if first:
            return first
        from apps.common.models import Currency
        return Currency.all_objects.filter(is_default=True).first() or Currency.all_objects.filter(code="USD").first() or Currency.all_objects.first()

    def get_effective_withdrawal_rate(self):
        from apps.common.models import Currency
        if self.withdrawal_exchange_rate:
            return self.withdrawal_exchange_rate
        default_currency = Currency.objects.filter(is_default=True).first()
        if default_currency:
            return default_currency.sell_rate
        return Decimal("1.000000")

    @property
    def logo_url(self):
        if self.logo:
            try:
                if self.logo.name and "shamcash.svg" not in self.logo.name:
                    return self.logo.url
            except Exception:
                pass
        if self.gateway and self.gateway.logo:
            try:
                if self.gateway.logo.name and "shamcash.svg" not in self.gateway.logo.name:
                    return self.gateway.logo.url
            except Exception:
                pass
        if self.gateway:
            gw_url = getattr(self.gateway, "logo_url", None)
            if gw_url:
                return gw_url
        if self.logo:
            try:
                return self.logo.url
            except Exception:
                pass
        return ""


class PaymentMethodExchangeRateLog(TimeStampedModel):
    payment_method = models.ForeignKey(PaymentMethod, related_name="exchange_rate_logs", on_delete=models.CASCADE, verbose_name="وسيلة الدفع")
    old_rate = models.DecimalField(max_digits=14, decimal_places=6, verbose_name="السعر القديم")
    new_rate = models.DecimalField(max_digits=14, decimal_places=6, verbose_name="السعر الجديد")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="بواسطة")
    reason = models.TextField(blank=True, verbose_name="السبب")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تعديل سعر الصرف"
        verbose_name_plural = "سجلات تعديل أسعار الصرف"
        
    def __str__(self):
        return f"{self.payment_method.name}: {self.old_rate} -> {self.new_rate}"


class PaymentGatewayIntegration(TimeStampedModel):
    class Provider(models.TextChoices):
        PAYMERA = "paymera", "Paymera (بيميرا)"
        SHAM_CASH = "sham_cash", "شام كاش (ShamCash)"
        MTN_PAY = "mtn_pay", "Cash Mobile (MTN كاش موبايل)"
        BANIYAS_CRYPTO = "baniyas_crypto", "Baniyas Crypto"
        CUSTOM = "custom", "Custom API"

    class Mode(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        LIVE = "live", "Live"

    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_gateway_integrations",
        verbose_name="المتجر",
    )
    objects = TenantManager()
    all_objects = models.Manager()

    name = models.CharField(max_length=120, verbose_name="اسم بوابة الدفع")
    logo = models.ImageField(
        upload_to="payment-gateways/logos/",
        blank=True,
        null=True,
        verbose_name="شعار البوابة",
        help_text="الشعار الرسمي الذي يظهر للعملاء عند الدفع عبر هذه البوابة."
    )
    provider = models.CharField(max_length=40, choices=Provider.choices, default=Provider.BANIYAS_CRYPTO, verbose_name="المزود")
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.SANDBOX, verbose_name="وضع التشغيل")
    terminal_id = models.CharField(max_length=64, blank=True, verbose_name="رقم نقطة البيع (Terminal ID)", help_text="المعرف المخصص من بيميرا والمؤلف من 8 خانات")
    base_url = models.URLField(max_length=255, blank=True, verbose_name="رابط API الأساسي")
    api_key = models.CharField(max_length=255, blank=True, verbose_name="API Key")
    api_secret = models.CharField(max_length=255, blank=True, verbose_name="API Secret")
    webhook_secret = models.CharField(max_length=255, blank=True, verbose_name="Webhook Secret")
    is_active = models.BooleanField(default=False, verbose_name="نشطة")
    can_deposit = models.BooleanField(default=True, verbose_name="تدعم الإيداع")
    can_withdraw = models.BooleanField(default=False, verbose_name="تدعم السحب")
    supported_assets = models.JSONField(default=list, blank=True, verbose_name="الأصول المدعومة")
    settings = models.JSONField(default=dict, blank=True, verbose_name="إعدادات إضافية")
    last_health_check_at = models.DateTimeField(null=True, blank=True, verbose_name="آخر فحص اتصال")
    last_health_status = models.CharField(max_length=30, blank=True, verbose_name="نتيجة آخر فحص")

    @property
    def logo_url(self):
        if self.logo:
            try:
                if self.logo.name and "shamcash.svg" not in self.logo.name:
                    return self.logo.url
            except Exception:
                pass
        if isinstance(self.settings, dict) and self.settings.get("logo_url"):
            custom_url = str(self.settings.get("logo_url")).strip()
            if custom_url and "shamcash.svg" not in custom_url:
                return custom_url
        try:
            for pm in PaymentMethod.all_objects.filter(gateway=self):
                if pm.logo and pm.logo.name and "shamcash.svg" not in pm.logo.name:
                    return pm.logo.url
        except Exception:
            pass
        try:
            if self.provider:
                for other_gw in PaymentGatewayIntegration.all_objects.filter(provider=self.provider).exclude(pk=self.pk):
                    if other_gw.logo and other_gw.logo.name and "shamcash.svg" not in other_gw.logo.name:
                        return other_gw.logo.url
                q_kw = "شام" if self.provider == "sham_cash" else ("بيميرا" if self.provider == "paymera" else ("mtn" if self.provider == "mtn_pay" else self.provider))
                for pm in PaymentMethod.all_objects.filter(name__icontains=q_kw):
                    if pm.logo and pm.logo.name and "shamcash.svg" not in pm.logo.name:
                        return pm.logo.url
        except Exception:
            pass
        if self.logo:
            try:
                return self.logo.url
            except Exception:
                pass
        if self.provider == "paymera" or "paymera" in (self.name or "").lower() or "بيميرا" in (self.name or ""):
            return "/media/payment-methods/logos/paymera.png"
        if self.provider == "mtn_pay" or "mtn" in (self.name or "").lower() or "cash mobile" in (self.name or "").lower() or "كاش موبايل" in (self.name or ""):
            return "/static/site/img/brands/cash-mobile.jpg"
        return None

    class Meta:
        ordering = ["provider", "name"]
        verbose_name = "بوابة دفع API"
        verbose_name_plural = "بوابات دفع API"

    def __str__(self):
        return f"{self.name} - {self.get_provider_display()}"

    def sync_payment_method(self):
        """
        Ensures a corresponding PaymentMethod exists for this gateway integration,
        so it automatically appears in the payment methods list, deposit page, and checkout.
        """
        from apps.common.models import Currency

        if self.provider == self.Provider.SHAM_CASH or "sham" in (self.name or "").lower():
            target_name = "شام كاش (ShamCash)"
            method_type = "بوابة دفع إلكترونية"
            description = "إيداع ودفع فوري مباشر عبر شام كاش"
        elif self.provider == self.Provider.PAYMERA or "paymera" in (self.name or "").lower():
            target_name = "بيميرا (Paymera)"
            method_type = "بوابة دفع إلكترونية"
            description = "إيداع ودفع فوري عبر بوابة بيميرا الإلكترونية"
        elif self.provider == self.Provider.MTN_PAY or "mtn" in (self.name or "").lower() or "cash mobile" in (self.name or "").lower():
            target_name = "Cash Mobile (كاش موبايل)"
            method_type = "بوابة دفع إلكترونية"
            description = "دفع وشحن فوري مباشر عبر بوابة Cash Mobile (MTN)"
        elif self.provider == self.Provider.BANIYAS_CRYPTO:
            target_name = "Baniyas Crypto"
            method_type = "بوابة عملات رقمية"
            description = "دفع فوري بالعملات الرقمية عبر بنياس كريبتو"
        else:
            target_name = self.name or "بوابة دفع إلكترونية"
            method_type = "بوابة دفع إلكترونية"
            description = "دفع فوري عبر بوابة الدفع الإلكترونية"

        existing_methods = list(PaymentMethod.all_objects.filter(gateway=self))
        if len(existing_methods) > 1:
            # Prefer the method with existing deposits/activity
            existing_methods.sort(key=lambda m: (m.deposits.count(), m.created_at), reverse=True)
            for extra in existing_methods[1:]:
                if not extra.deposits.exists():
                    extra.delete()
                else:
                    extra.is_active = False
                    extra.save(update_fields=["is_active"])
            pm = existing_methods[0]
        elif existing_methods:
            pm = existing_methods[0]
        else:
            pm = PaymentMethod.all_objects.filter(store=self.store, name__icontains=target_name[:6]).first()

        if pm:
            pm.gateway = self
            pm.store = self.store
            pm.name = target_name
            pm.method_type = method_type
            if not pm.description:
                pm.description = description
            if self.logo:
                pm.logo = self.logo
            elif pm.logo and not self.logo:
                self.logo = pm.logo
                PaymentGatewayIntegration.all_objects.filter(pk=self.pk).update(logo=pm.logo.name)
            pm.is_active = self.is_active
            pm.can_deposit = self.can_deposit
            pm.can_withdraw = self.can_withdraw
            pm.save()
        else:
            pm = PaymentMethod.all_objects.create(
                gateway=self,
                store=self.store,
                name=target_name,
                method_type=method_type,
                description=description,
                logo=self.logo if self.logo else None,
                is_active=self.is_active,
                can_deposit=self.can_deposit,
                can_withdraw=self.can_withdraw,
                deposit_min_amount=Decimal("1.00"),
                deposit_max_amount=Decimal("10000.00"),
            )

        currencies = Currency.objects.filter(is_active=True)
        if self.provider == self.Provider.SHAM_CASH:
            syp = currencies.filter(code="SYP").first()
            usd = currencies.filter(code="USD").first()
            to_add = [c for c in (syp, usd) if c]
            if to_add:
                pm.supported_currencies.add(*to_add)
        else:
            usd = currencies.filter(code="USD").first()
            syp = currencies.filter(code="SYP").first()
            to_add = [c for c in (usd, syp) if c]
            if to_add:
                pm.supported_currencies.add(*to_add)

        if self.provider == self.Provider.MTN_PAY or "mtn" in (self.name or "").lower() or "cash mobile" in (self.name or "").lower():
            try:
                import os
                tid = (self.terminal_id or os.environ.get("MTN_PAY_TERMINAL_ID") or "9001000000064683").strip()
                b_url = (self.base_url or "https://cash.mtnsyr.com:9000").strip()
                if b_url.rstrip("/") == "https://cash.mtnsyr.com":
                    b_url = "https://cash.mtnsyr.com:9000"
                serial_val = ""
                if isinstance(self.settings, dict):
                    serial_val = str(self.settings.get("serial_number") or self.settings.get("Serial") or "").strip()
                if not serial_val or serial_val.startswith("SN-MTN-"):
                    serial_val = "RAQAMIYAT"

                term = MTNPayTerminalConfig.objects.filter(terminal_id=tid).first() or MTNPayTerminalConfig.objects.filter(store=self.store).first()
                default_settings = {
                    "Currency": {"Code": "760", "Brief": "SYP", "Fractional": 100},
                    "Limits": {"Minimum": 100, "Maximum": 5000000000000},
                    "Allowed": {"Payment": True},
                    "Description": {
                        "Business": "E payment section",
                        "Shop": "Raqmyat",
                        "Address": "Damascus",
                        "Phone": "963957222109",
                        "UniquePayCode": f"MTN-{tid[-6:]}",
                    },
                }
                if not term:
                    term = MTNPayTerminalConfig.objects.create(
                        store=self.store,
                        terminal_id=tid,
                        serial_number=serial_val,
                        base_url=b_url,
                        language="en",
                        is_activated=True,
                        is_locked=False,
                        activated_at=timezone.now(),
                        terminal_settings=default_settings,
                    )
                else:
                    term.terminal_id = tid
                    if b_url:
                        term.base_url = b_url
                    if not term.serial_number:
                        term.serial_number = serial_val
                    if not term.terminal_settings:
                        term.terminal_settings = default_settings
                    if self.is_active and not term.is_locked:
                        term.is_activated = True
                    term.save()
                from apps.payments.mtn_pay import MTNPaymentClient
                MTNPaymentClient(term).ensure_keypair()
            except Exception:
                pass

        return pm

    @classmethod
    def sync_all_active_gateways(cls):
        """Syncs all active payment gateways to ensure their PaymentMethod records exist and match."""
        for gw in cls.all_objects.filter(is_active=True):
            try:
                gw.sync_payment_method()
            except Exception:
                pass

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            self.sync_payment_method()
        except Exception:
            pass


class DepositRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        APPROVED = "approved", "تمت الموافقة"
        REJECTED = "rejected", "مرفوض"
        COMPLETED = "completed", "مكتمل"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="deposits", on_delete=models.PROTECT, verbose_name="المستخدم")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="deposit_requests",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    payment_method = models.ForeignKey(PaymentMethod, related_name="deposits", on_delete=models.PROTECT, verbose_name="وسيلة الدفع")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    wallet_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="المبلغ بعملة المحفظة")
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="مبلغ الرسوم")
    final_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ النهائي (الصافي)")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    transaction_id = models.CharField(max_length=160, blank=True, db_index=True, verbose_name="رقم العملية / المرجع")
    gateway_payment_id = models.CharField(max_length=128, blank=True, db_index=True, verbose_name="معرف دفعة البوابة")
    proof_image = models.ImageField(upload_to="deposit-proofs/", blank=True, null=True, verbose_name="وصل الدفع")
    customer_note = models.TextField(blank=True, verbose_name="ملاحظات العميل")
    admin_note = models.TextField(blank=True, verbose_name="ملاحظات المدير")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reviewed_deposits",
        on_delete=models.SET_NULL,
        verbose_name="تمت المراجعة من قبل"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    is_verified = models.BooleanField(default=False, verbose_name="تم التحقق")
    metadata = models.JSONField(default=dict, blank=True)

    @property
    def usd_amount(self):
        try:
            return self.currency.to_base(self.amount, "deposit")
        except:
            return Decimal("0.00")

    @property
    def formatted_metadata(self):
        """Returns a list of dicts with 'label', 'value', and 'type' for human-readable customer metadata."""
        if not self.metadata or not isinstance(self.metadata, dict):
            return []

        technical_keys = {
            "payment_provider", "base_usd_amount", "gateway_payment_id",
            "paymera_payment_id", "paymera_refunded", "paymera_refund_at", "paymera_refund_res",
            "shamcash_bill_no", "shamcash_tran_id", "shamcash_status", "shamcash_refund_actor",
            "shamcash_refund_timestamp", "shamcash_raw_res", "shamcash_payment_url",
            "mtn_invoice_number", "mtn_refund_invoice", "mtn_status_data", "mtn_terminal_id",
            "mtn_phone", "mtn_initiated_at", "mtn_confirmed_at", "mtn_raw_res",
            "refund_requested", "refund_status", "refund_reason", "refund_held",
            "refund_held_amount", "refund_requested_at", "refund_approved_at",
            "refund_approved_by", "refund_rejected_at", "refund_rejected_by",
            "refund_reject_reason", "refund_gateway_tx_id", "refund_raw_res",
            "auto_closed", "auto_closed_at", "auto_closed_reason",
        }

        results = []
        schema = getattr(self.payment_method, "deposit_form_schema", None) if self.payment_method else None
        fields = schema.get("fields", []) if isinstance(schema, dict) else []

        # Create a mapping of field key to (label, type)
        field_map = {}
        for f in fields:
            lbl = f.get("label", "")
            ftype = f.get("type", "text")
            fid = f.get("name") or f.get("id") or f.get("key") or lbl
            if fid:
                field_map[fid] = (lbl, ftype)

        for key, val in self.metadata.items():
            if key in technical_keys and key not in field_map:
                continue
            if isinstance(val, (dict, list)) and key not in field_map:
                continue
            if val is None or val == "":
                continue

            label, ftype = field_map.get(key, (key, "text"))

            # Heuristic: If value looks like an image path, force type to image
            if isinstance(val, str) and (val.startswith("/media/") or any(val.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])):
                ftype = "image"

            results.append({"label": label, "value": val, "type": ftype})

        return results

    def calculate_fees(self):
        amt = Decimal(str(self.amount)) if self.amount is not None else Decimal("0.00")
        self.fee_amount = self.payment_method.calculate_fee(amt, mode="deposit")
        fee = Decimal(str(self.fee_amount)) if self.fee_amount is not None else Decimal("0.00")
        self.final_amount = max(Decimal("0.00"), amt - fee)
        if self.currency:
            try:
                # Use wallet currency for wallet_amount calculation
                wallet = self.user.wallet
                # Compare by ID if possible, then by code
                if self.currency_id == wallet.currency_id or self.currency.code == wallet.currency.code:
                    self.wallet_amount = self.amount
                else:
                    # Convert via base currency (USD)
                    base_val = self.currency.to_base(self.amount, "deposit")
                    self.wallet_amount = wallet.currency.from_base(base_val, "withdraw")
            except Exception:
                # Fallback to base currency equivalent
                self.wallet_amount = self.currency.to_base(self.amount, "deposit")
        self._fees_calculated = True

    def get_metadata_value(self, keys):
        if not isinstance(self.metadata, dict):
            return ""
            
        # 1. Try to find the key in metadata by matching against form schema fields first
        if self.payment_method:
            schema = self.payment_method.deposit_form_schema
            fields = schema.get("fields", []) if isinstance(schema, dict) else []
            for key in keys:
                key_clean = key.strip().lower()
                for field in fields:
                    flabel = (field.get("label") or "").strip().lower()
                    fname = (field.get("name") or field.get("id") or field.get("key") or "").strip().lower()
                    
                    # Try exact match on label or name
                    if key_clean == flabel or key_clean == fname:
                        # Found matching field in schema, get its value from metadata using its actual name in metadata
                        actual_key = field.get("name") or field.get("id") or field.get("key") or field.get("label")
                        if actual_key in self.metadata:
                            return self.metadata[actual_key]
                            
            for key in keys:
                key_clean = key.strip().lower()
                for field in fields:
                    flabel = (field.get("label") or "").strip().lower()
                    fname = (field.get("name") or field.get("id") or field.get("key") or "").strip().lower()
                    
                    # Try substring match on label or name
                    if key_clean in flabel or flabel in key_clean or key_clean in fname or fname in key_clean:
                        actual_key = field.get("name") or field.get("id") or field.get("key") or field.get("label")
                        if actual_key in self.metadata:
                            return self.metadata[actual_key]

        # 2. Fallback to direct metadata search (for backward compatibility / if payment method not present)
        for key in keys:
            key_clean = key.strip().lower()
            # First try exact match
            for mk, mv in self.metadata.items():
                if mk.strip().lower() == key_clean:
                    return mv
            # Then try substring match
            for mk, mv in self.metadata.items():
                if key_clean in mk.strip().lower() or mk.strip().lower() in key_clean:
                    return mv
        return ""

    @property
    def metadata_account_name(self):
        val = self.get_metadata_value(["اسم حسابك", "اسم الحساب", "رقم الحساب", "حسابك", "الحساب", "العنوان", "عنوان", "الرقم", "المستلم", "رقم المحفظة", "محفظة", "account_name", "account_number", "account", "address", "wallet", "number"])
        return val if val else self.user.email

    @property
    def client_note(self):
        if self.customer_note:
            return self.customer_note
        val = self.get_metadata_value(["customer_note", "note", "notes", "ملاحظة", "ملاحظات", "ملاحظة العميل", "حقل ملاحظة", "ملاحظة الإيداع", "الرسالة", "message"])
        return val if val else ""

    def save(self, *args, **kwargs):
        if not getattr(self, "_fees_calculated", False) and self.amount and self.payment_method:
            self.calculate_fees()
        if not self.transaction_id or self.transaction_id.strip() in ("", "---"):
            import random
            import string
            rand_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            self.transaction_id = f"DEP-{rand_str}"
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["transaction_id"]),
        ]
        verbose_name = "طلب إيداع"
        verbose_name_plural = "طلبات الإيداع"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.amount} {self.currency} - {self.status}"


class WithdrawalRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد المعالجة"
        APPROVED = "approved", "تمت الموافقة"
        REJECTED = "rejected", "مرفوض"
        COMPLETED = "completed", "مكتمل"
        CANCELLED = "cancelled", "ملغي"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="withdrawals", on_delete=models.PROTECT, verbose_name="المستخدم")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="withdrawal_requests",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    payment_method = models.ForeignKey(PaymentMethod, related_name="withdrawals", on_delete=models.PROTECT, verbose_name="وسيلة السحب")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ المطلوب")
    wallet_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="المبلغ بعملة المحفظة")
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرسوم")
    final_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ الصافي للاستلام")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    
    # Payout Information
    payout_details = models.JSONField(default=dict, verbose_name="بيانات التحويل")
    
    admin_note = models.TextField(blank=True, verbose_name="ملاحظات المدير")
    proof_image = models.ImageField(upload_to="withdrawal-proofs/", blank=True, null=True, verbose_name="إثبات التحويل (صورة)")
    proof_file = models.FileField(upload_to="withdrawal-proofs/docs/", blank=True, null=True, verbose_name="إثبات التحويل (ملف/PDF)")
    
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reviewed_withdrawals",
        on_delete=models.SET_NULL,
        verbose_name="تمت المراجعة من قبل"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    is_verified = models.BooleanField(default=False, verbose_name="تم التحقق")
    metadata = models.JSONField(default=dict, blank=True)
    transaction_id = models.CharField(max_length=160, blank=True, null=True, db_index=True, verbose_name="رقم العملية / المرجع")

    @property
    def usd_amount(self):
        try:
            return self.currency.to_base(self.amount, "withdraw")
        except:
            return Decimal("0.00")

    @property
    def display_payout_value(self):
        """Safely returns a primary value for display in lists."""
        details = self.formatted_payout_details
        if details:
            # Show the first field's label and value
            item = details[0]
            return f"{item['label']}: {item['value']}"
        return ""

    @property
    def formatted_payout_details(self):
        """Returns a list of dicts with 'label', 'value', and 'type' for payout information."""
        if not self.payout_details:
            return []
            
        results = []
        
        # 1. Standard address field (fallback)
        addr = self.payout_details.get("address")
        if addr:
            results.append({"label": "رقم الحساب / العنوان", "value": addr, "type": "text"})
            
        # 2. Dynamic fields from schema
        dynamic = self.payout_details.get("dynamic")
        if isinstance(dynamic, dict) and dynamic:
            schema = self.payment_method.withdrawal_form_schema
            fields = schema.get("fields", []) if isinstance(schema, dict) else []
            
            # Create a mapping of field key to (label, type)
            field_map = {}
            for f in fields:
                lbl = f.get("label", "")
                ftype = f.get("type", "text")
                fid = f.get("name") or f.get("id") or f.get("key") or lbl
                if fid:
                    field_map[fid] = (lbl, ftype)
            
            for key, val in dynamic.items():
                label, ftype = field_map.get(key, (key, "text"))
                
                # Heuristic: If value looks like an image path, force type to image
                if isinstance(val, str) and (val.startswith("/media/") or any(val.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])):
                    ftype = "image"
                    
                results.append({"label": label, "value": val, "type": ftype})
                
        return results

    def calculate_fees(self):
        self.fee_amount = self.payment_method.calculate_fee(self.amount, mode="withdrawal")
        self.final_amount = self.amount - self.fee_amount
        if self.currency:
            if not self.wallet_amount or self.wallet_amount <= 0:
                try:
                    wallet = self.user.wallet
                    if self.currency_id == wallet.currency_id or self.currency.code == wallet.currency.code:
                        self.wallet_amount = self.amount
                    else:
                        base_val = self.currency.to_base(self.amount, "withdraw")
                        self.wallet_amount = wallet.currency.from_base(base_val, "deposit")
                except Exception:
                    self.wallet_amount = self.currency.to_base(self.amount, "withdraw")

    def save(self, *args, **kwargs):
        if not self.transaction_id or self.transaction_id.strip() in ("", "---"):
            import random
            import string
            rand_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            self.transaction_id = f"WTH-{rand_str}"
        if self.amount and self.payment_method:
            self.calculate_fees()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["transaction_id"]),
        ]
        verbose_name = "طلب سحب"
        verbose_name_plural = "طلبات السحب"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.amount} {self.currency} - {self.status}"


# ══════════════════════════════════════════════════════════════════════════════
# SHAMCASH 5-YEAR COMPLIANCE, AUDIT, BILLING & RECONCILIATION MODELS
# Required by ShamCash Terms & Conditions (Articles 3, 6, 8, 9, 11, 14, 15)
# ══════════════════════════════════════════════════════════════════════════════

class ShamCashComplianceProfile(TimeStampedModel):
    """
    Official KYC, Legal Registration & Regulatory Profile for ShamCash API.
    Mandated by Articles 3, 15, and 21 of ShamCash B2B Terms & Conditions.
    """
    company_name = models.CharField(max_length=255, default="شركة رقميات للحلول والتجارة الإلكترونية", verbose_name="اسم الشركة / المؤسسة")
    commercial_record_number = models.CharField(max_length=120, default="CR-1048291", verbose_name="رقم السجل التجاري")
    tax_number = models.CharField(max_length=120, default="TAX-300481920", verbose_name="الرقم الضريبي")
    establishment_contract_details = models.TextField(blank=True, default="شركة تجارية محدودة المسؤولية مرخصة أصولاً في الجمهورية العربية السورية لتقديم خدمات الدفع والتجارة الرقمية والحلول السحابية.", verbose_name="عقد التأسيس والترخيص")
    activity_description = models.TextField(blank=True, default="منصة إلكترونية لبيع البطاقات الرقمية، الأجهزة الذكية، وحلول المدفوعات والاشتراكات عبر الإنترنت.", verbose_name="وصف النشاط والخدمات")
    shamcash_account_number = models.CharField(max_length=120, default="0947991951", verbose_name="رقم الحساب التجاري الموثق لدى شام كاش")
    logo_url = models.URLField(max_length=500, blank=True, default="https://store.raqamiyat.sy/static/site/img/logo.png", verbose_name="رابط شعار المنصة المعتمد لدى شام كاش")
    
    general_manager_name = models.CharField(max_length=120, default="رامي قصاص", verbose_name="المدير العام / المسؤول الفعلي")
    authorized_signatory_name = models.CharField(max_length=120, default="رامي قصاص", verbose_name="المفوض بالتوقيع والتعامل")
    authorized_signatory_phone = models.CharField(max_length=50, default="+963947991951", verbose_name="هاتف المفوض")
    
    technical_lead_name = models.CharField(max_length=120, default="الفريق التقني - رقميات", verbose_name="المسؤول التقني")
    technical_lead_email = models.EmailField(default="tech@raqamiyat.sy", verbose_name="البريد الإلكتروني التقني")
    technical_lead_phone = models.CharField(max_length=50, default="+963947991951", verbose_name="هاتف المسؤول التقني")
    
    financial_officer_name = models.CharField(max_length=120, default="الإدارة المالية", verbose_name="المسؤول المالي")
    financial_officer_email = models.EmailField(default="finance@raqamiyat.sy", verbose_name="البريد الإلكتروني المالي")
    financial_officer_phone = models.CharField(max_length=50, default="+963947991951", verbose_name="هاتف المسؤول المالي")
    
    complaints_officer_name = models.CharField(max_length=120, default="قسم خدمة العملاء والشكاوى", verbose_name="المفوض بمتابعة الشكاوى")
    complaints_officer_email = models.EmailField(default="support@raqamiyat.sy", verbose_name="بريد متابعة الشكاوى")
    
    compliance_statement = models.TextField(
        blank=True,
        default="تلتزم المنصة بجميع الشروط والأحكام الخاصة بخدمة تحصيل الفواتير عبر API مع شام كاش، وتؤكد عدم فرض أي عمولة إضافية على المستخدمين نهائياً باسم شام كاش وفقاً للمادة 7، والاحتفاظ بالسجلات لمدة لا تقل عن خمس سنوات وفقاً للمادة 14، واستخدام واجهات الربط وفقاً للمتطلبات الأمنية وتشفير Direct JWE وحماية مفاتيح التشفير.",
        verbose_name="إقرار الامتثال والالتزام"
    )

    class Meta:
        verbose_name = "ملف الامتثال والتوثيق لشام كاش"
        verbose_name_plural = "ملفات الامتثال والتوثيق لشام كاش"

    def __str__(self):
        return f"{self.company_name} - سجل: {self.commercial_record_number}"


class ShamCashBillRecord(TimeStampedModel):
    """
    Immutable ledger of all bills generated via ShamCash API.
    Fulfills Article 6 (Invoices & Data Requirements) and Article 14 (5-Year Record Retention).
    """
    class BillType(models.TextChoices):
        ORDER = "order", "طلب منتج مباشر"
        DEPOSIT = "deposit", "إيداع محفظة مباشر"

    bill_no = models.CharField(max_length=120, unique=True, db_index=True, verbose_name="رقم الفاتورة الفريد (billNo)")
    bill_type = models.CharField(max_length=20, choices=BillType.choices, default=BillType.ORDER, verbose_name="نوع الفاتورة")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shamcash_bills", verbose_name="العميل")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="shamcash_bills", verbose_name="الطلب المرتبط")
    deposit = models.ForeignKey(DepositRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="shamcash_bills", verbose_name="طلب الإيداع المرتبط")
    
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="قيمة الفاتورة")
    currency_id = models.IntegerField(default=1, verbose_name="معرف العملة (1=USD, 2=SYP)")
    currency_code = models.CharField(max_length=10, default="USD", verbose_name="رمز العملة")
    
    status_id = models.IntegerField(default=1, db_index=True, verbose_name="رمز الحالة (1=pending, 2=refund, 3=expired, 4=paid, 5=partly refunded)")
    status_name = models.CharField(max_length=50, default="pending", verbose_name="اسم الحالة")
    tran_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="رقم عملية شام كاش (tranId)")
    
    payment_url = models.URLField(max_length=1000, blank=True, verbose_name="رابط الدفع المباشر")
    callback_url = models.URLField(max_length=500, blank=True, verbose_name="رابط الويب هوك")
    redirect_url = models.URLField(max_length=500, blank=True, verbose_name="رابط إعادة التوجيه")
    note = models.TextField(blank=True, verbose_name="ملاحظات / وصف الخدمة")
    
    total_refunded_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المبلغ المسترد")
    created_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الفاتورة (شام كاش)")
    created_time = models.TimeField(null=True, blank=True, verbose_name="وقت الفاتورة (شام كاش)")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت انتهاء الصلاحية (10 دقائق)")
    
    raw_create_response = models.JSONField(default=dict, blank=True, verbose_name="الاستجابة الأصلية لإنشاء الفاتورة")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل فاتورة شام كاش"
        verbose_name_plural = "سجلات فواتير شام كاش"
        indexes = [
            models.Index(fields=["bill_no"]),
            models.Index(fields=["tran_id"]),
            models.Index(fields=["status_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.bill_no} - {self.amount} {self.currency_code} ({self.status_name})"

    @property
    def is_paid(self):
        return self.status_id == 4

    @property
    def is_expired(self):
        return self.status_id == 3

    @property
    def is_refunded(self):
        return self.status_id in (2, 5)

    @property
    def remaining_refundable_amount(self):
        return max(Decimal("0.00"), self.amount - self.total_refunded_amount)


class ShamCashApiLog(TimeStampedModel):
    """
    Mandatory 5-Year Technical Audit Log for all ShamCash API Requests & Responses.
    Fulfills Article 11 (API Security) and Article 14 (5-Year Log Retention & Auditability).
    """
    endpoint = models.CharField(max_length=120, db_index=True, verbose_name="واجهة API")
    bill_no = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="رقم الفاتورة المرتبط")
    request_method = models.CharField(max_length=10, default="POST", verbose_name="نوع الطلب")
    request_payload_sanitized = models.JSONField(default=dict, blank=True, verbose_name="بيانات الطلب")
    response_status_code = models.IntegerField(default=200, verbose_name="رمز استجابة HTTP")
    response_result_code = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="رمز نتيجة شام كاش (result)")
    response_data = models.JSONField(null=True, blank=True, verbose_name="بيانات الاستجابة")
    is_success = models.BooleanField(default=False, db_index=True, verbose_name="نجاح العملية")
    duration_ms = models.IntegerField(default=0, verbose_name="زمن التنفيذ (ميلي ثانية)")
    error_message = models.TextField(blank=True, verbose_name="رسالة الخطأ إن وجدت")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تدقيق واجهات شام كاش (5 سنوات)"
        verbose_name_plural = "سجلات تدقيق واجهات شام كاش (5 سنوات)"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["endpoint"]),
            models.Index(fields=["bill_no"]),
            models.Index(fields=["response_result_code"]),
            models.Index(fields=["is_success"]),
        ]

    def __str__(self):
        return f"{self.endpoint} [{self.response_status_code} - result:{self.response_result_code}] at {self.created_at}"


class ShamCashWebhookLog(TimeStampedModel):
    """
    Mandatory 5-Year Inbound Webhook Event Audit Trail.
    Fulfills Article 14 (Notification Logs Retention).
    """
    bill_no = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="رقم الفاتورة")
    tran_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="رقم العملية tranId")
    status_id = models.IntegerField(null=True, blank=True, verbose_name="معرف الحالة")
    raw_enc_data = models.TextField(verbose_name="حزمة JWE المشفرة الخام")
    decrypted_payload = models.JSONField(null=True, blank=True, verbose_name="الحمولة المفكوكة التشفير")
    is_valid = models.BooleanField(default=False, verbose_name="صحة التشفير والصلاحية")
    processed_successfully = models.BooleanField(default=False, verbose_name="تمت المعالجة بنجاح")
    error_message = models.TextField(blank=True, verbose_name="تفاصيل الخطأ")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP المرسل")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل إشعارات الويب هوك لشام كاش"
        verbose_name_plural = "سجلات إشعارات الويب هوك لشام كاش"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["bill_no"]),
            models.Index(fields=["tran_id"]),
        ]

    def __str__(self):
        return f"Webhook bill:{self.bill_no} status:{self.status_id} at {self.created_at}"


class ShamCashRefundRecord(TimeStampedModel):
    """
    Refund Tracking and Idempotency Audit Ledger.
    Fulfills Article 9 & 14 (Refunds & Disputes Records).
    """
    bill = models.ForeignKey(ShamCashBillRecord, on_delete=models.CASCADE, related_name="refund_records", verbose_name="الفاتورة الأصلية")
    bill_no = models.CharField(max_length=120, db_index=True, verbose_name="رقم الفاتورة")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المسترد")
    idempotency_key = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="مفتاح عدم التكرار (idempotencyKey)")
    tran_id = models.BigIntegerField(null=True, blank=True, verbose_name="رقم حركة الاسترداد (tranId)")
    note = models.TextField(blank=True, verbose_name="سبب / ملاحظات الاسترداد")
    status = models.CharField(max_length=20, choices=[("success", "ناجح"), ("failed", "فاشل")], default="success", verbose_name="الحالة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المنفذ")
    raw_response = models.JSONField(default=dict, blank=True, verbose_name="استجابة شام كاش")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل استرداد شام كاش"
        verbose_name_plural = "سجلات استرداد شام كاش"

    def __str__(self):
        return f"Refund {self.amount} for bill {self.bill_no} (tranId: {self.tran_id})"


class ShamCashReconciliationBatch(TimeStampedModel):
    """
    EOD and Periodic Settlement Reconciliation Audit Report.
    Fulfills Article 8 (Settlement & Reconciliation) and Section 11 of the Integration Guide.
    """
    class BatchStatus(models.TextChoices):
        BALANCED = "balanced", "متطابق تماماً بدون أي فروقات"
        DISCREPANCY = "discrepancy", "يوجد فروقات تتطلب التدقيق"
        FAILED = "failed", "فشل أثناء جلب البيانات"

    from_date = models.DateField(verbose_name="من تاريخ")
    to_date = models.DateField(verbose_name="إلى تاريخ")
    status = models.CharField(max_length=30, choices=BatchStatus.choices, default=BatchStatus.BALANCED, verbose_name="حالة المطابقة")
    
    total_shamcash_count = models.IntegerField(default=0, verbose_name="عدد حركات شام كاش")
    total_shamcash_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي مبالغ شام كاش")
    
    total_local_count = models.IntegerField(default=0, verbose_name="عدد الحركات المحلية")
    total_local_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المبالغ المحلية")
    
    matched_count = models.IntegerField(default=0, verbose_name="عدد الحركات المتطابقة")
    discrepancies_count = models.IntegerField(default=0, verbose_name="عدد الفروقات")
    discrepancy_details = models.JSONField(default=list, blank=True, verbose_name="تفاصيل الفروقات")
    
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المنفذ")
    notes = models.TextField(blank=True, verbose_name="ملاحظات وتوصيات التسوية")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تقرير تسوية ومطابقة شام كاش"
        verbose_name_plural = "تقارير تسوية ومطابقة شام كاش"

    def __str__(self):
        return f"Reconciliation {self.from_date} to {self.to_date} - {self.get_status_display()}"



# ══════════════════════════════════════════════════════════════════════════════
# MTN PAYMENT API (MTNPay / pos_web) MODELS
# RSA-1024 + SHA-256 Signed POS Terminal, Invoice, Phone Payment & Refund Models
# ══════════════════════════════════════════════════════════════════════════════

class MTNPayTerminalConfig(TimeStampedModel):
    """
    Stores the activated MTN POS Terminal configuration and the Settings object
    received from `pos_web/pos/activate` (Currency, Limits, Allowed, Description).
    Private key and activation secret are never exposed to the UI.
    """
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mtn_pay_terminals",
        verbose_name="المتجر",
    )
    terminal_id = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="معرف الطرفية (Subject / Terminal ID)")
    serial_number = models.CharField(max_length=128, blank=True, verbose_name="الرقم التسلسلي للطرفية (Serial)")
    base_url = models.URLField(max_length=500, default="https://cash.mtnsyr.com:9000", verbose_name="رابط خادم MTN POS")
    language = models.CharField(max_length=16, default="en", verbose_name="لغة الطلبات (BCP 47)")

    public_key_b64 = models.TextField(blank=True, verbose_name="المفتاح العام للطرفية (Base64 RSA-1024)")
    server_public_key_b64 = models.TextField(blank=True, verbose_name="المفتاح العام لخادم MTN (Base64 RSA-1024)")

    is_activated = models.BooleanField(default=False, db_index=True, verbose_name="مفعلة")
    is_locked = models.BooleanField(default=False, verbose_name="موقوفة بسبب تجاوز محاولات التفعيل (3 مرات)")
    activation_attempts = models.IntegerField(default=0, verbose_name="عدد محاولات التفعيل الفاشلة")
    count_abuse = models.IntegerField(default=0, verbose_name="عداد المحاولات الفاشلة من الخادم (CountAbuse)")
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التفعيل")

    # Full Settings object returned by pos_web/pos/activate
    terminal_settings = models.JSONField(default=dict, blank=True, verbose_name="كائن الإعدادات (Settings)")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "إعداد طرفية MTN Payment"
        verbose_name_plural = "إعدادات طرفيات MTN Payment"

    def __str__(self):
        status_str = "مفعلة" if self.is_activated else ("مقفلة" if self.is_locked else "غير مفعلة")
        return f"MTN POS #{self.terminal_id} ({status_str})"

    @property
    def currency_info(self) -> dict:
        if isinstance(self.terminal_settings, dict):
            return self.terminal_settings.get("Currency") or {}
        return {}

    @property
    def limits_info(self) -> dict:
        if isinstance(self.terminal_settings, dict):
            return self.terminal_settings.get("Limits") or {}
        return {}

    @property
    def allowed_info(self) -> dict:
        if isinstance(self.terminal_settings, dict):
            return self.terminal_settings.get("Allowed") or {}
        return {}

    @property
    def description_info(self) -> dict:
        if isinstance(self.terminal_settings, dict):
            return self.terminal_settings.get("Description") or {}
        return {}

    @property
    def is_payment_allowed(self) -> bool:
        allowed = self.allowed_info
        return bool(allowed.get("Payment") is True)

    @property
    def otp_code_encoding(self) -> str:
        # Verified live on MTN Syria eMARA server: Code MUST be Base64(SHA-256(sms_code))
        return "sha256_b64"

    @property
    def fractional_factor(self) -> int:
        """
        Returns the multiplier to convert major currency units to minor units
        based on Settings.Currency.Fractional (e.g. 100 for SYP).
        """
        frac = self.currency_info.get("Fractional", 100)
        try:
            f_int = int(frac)
            if f_int <= 0:
                return 1
            if f_int in (1, 10, 100, 1000):
                return f_int
            if f_int <= 6:
                return 10 ** f_int
            return f_int
        except (TypeError, ValueError):
            return 100


class MTNPayInvoiceRecord(TimeStampedModel):
    """
    Represents a single MTN Payment API Invoice and its authorization lifecycle.
    Statuses: 0=Cancelled, 1=Active/Pending Auth, 5=Processing, 8=Failed, 9=Paid.
    """
    STATUS_CANCELLED = 0
    STATUS_ACTIVE = 1
    STATUS_PROCESSING = 5
    STATUS_FAILED = 8
    STATUS_PAID = 9

    STATUS_CHOICES = [
        (STATUS_CANCELLED, "ملغاة (0)"),
        (STATUS_ACTIVE, "نشطة بانتظار التفويض (1)"),
        (STATUS_PROCESSING, "قيد المعالجة (5)"),
        (STATUS_FAILED, "فاشلة (8)"),
        (STATUS_PAID, "مدفوعة بنجاح (9)"),
    ]

    terminal = models.ForeignKey(
        MTNPayTerminalConfig,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="الطرفية",
    )
    invoice_number = models.BigIntegerField(unique=True, db_index=True, verbose_name="رقم الفاتورة الفريد (Invoice)")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mtn_pay_invoices",
        verbose_name="العميل",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mtn_pay_invoices",
        verbose_name="الطلب المرتبط",
    )
    deposit = models.ForeignKey(
        DepositRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mtn_pay_invoices",
        verbose_name="طلب الإيداع المرتبط",
    )

    amount_major = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ بالوحدة الأساسية")
    amount_minor = models.BigIntegerField(verbose_name="المبلغ بأصغر وحدة نقدية (Amount)")
    currency_code = models.CharField(max_length=12, default="SYP", verbose_name="رمز العملة")

    session_id = models.CharField(max_length=128, blank=True, verbose_name="معرف الجلسة الاختياري (Session)")
    ttl_seconds = models.IntegerField(null=True, blank=True, verbose_name="مدة صلاحية الفاتورة (TTL)")

    status_code = models.IntegerField(choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True, verbose_name="حالة الفاتورة (Status)")
    transaction_id = models.CharField(max_length=128, blank=True, db_index=True, verbose_name="رقم المعاملة الداخلي (Transaction)")

    # Receipt details from pos_web/invoice/create & pos_web/invoice/get
    qr_code = models.TextField(blank=True, verbose_name="رمز QR للفاتورة")
    commission_minor = models.BigIntegerField(default=0, verbose_name="العمولة (Commission)")
    tax_minor = models.BigIntegerField(default=0, verbose_name="الضريبة (Tax)")
    created_remote = models.CharField(max_length=64, blank=True, verbose_name="تاريخ الإنشاء (Created)")
    expired_remote = models.CharField(max_length=64, blank=True, verbose_name="تاريخ الانتهاء (Expired)")
    processed_remote = models.CharField(max_length=64, blank=True, verbose_name="تاريخ المعالجة (Processed)")
    receipt_raw = models.JSONField(default=dict, blank=True, verbose_name="كائن الإيصال الكامل (Receipt)")

    # Phone payment fields (pos_web/payment_phone/initiate & confirm)
    customer_phone = models.CharField(max_length=32, blank=True, db_index=True, verbose_name="رقم هاتف العميل (Phone)")
    guid = models.CharField(max_length=128, blank=True, db_index=True, verbose_name="معرف الإشعار الفريد (Guid)")
    operation_number = models.CharField(max_length=128, blank=True, verbose_name="رقم عملية الإصدار (OperationNumber)")
    pay_system = models.CharField(max_length=64, default="MTNPay", verbose_name="نظام الدفع (PaySystem)")
    abuse_remaining = models.IntegerField(null=True, blank=True, verbose_name="المحاولات المتبقية لرمز التأكيد (Abuse)")

    is_refunded = models.BooleanField(default=False, verbose_name="تم الاسترداد")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "فاتورة MTN Payment"
        verbose_name_plural = "فواتير MTN Payment"

    def __str__(self):
        return f"MTN Invoice #{self.invoice_number} - {self.amount_major} {self.currency_code} (Status={self.status_code})"

    @property
    def is_paid(self) -> bool:
        return self.status_code == self.STATUS_PAID


class MTNPayRefundRecord(TimeStampedModel):
    """
    Tracks refund initiation (`pos_web/invoice/refund/initiate`),
    confirmation (`pos_web/invoice/refund/confirm`), and cancellation (`pos_web/invoice/refund/cancel`).
    """
    class RefundStatus(models.TextChoices):
        INITIATED = "initiated", "بدأ الاسترداد (بانتظار التأكيد)"
        CONFIRMED = "confirmed", "تم تأكيد الاسترداد بنجاح"
        CANCELLED = "cancelled", "تم إلغاء الاسترداد"
        FAILED = "failed", "فشل الاسترداد"

    invoice_record = models.ForeignKey(
        MTNPayInvoiceRecord,
        on_delete=models.CASCADE,
        related_name="refunds",
        verbose_name="الفاتورة الأصلية",
    )
    base_invoice = models.BigIntegerField(db_index=True, verbose_name="رقم الفاتورة الأصلية (BaseInvoice)")
    refund_invoice = models.BigIntegerField(unique=True, db_index=True, verbose_name="معرف فاتورة الاسترداد (RefundInvoice)")
    refund_invoice_date = models.CharField(max_length=64, blank=True, verbose_name="تاريخ فاتورة الاسترداد (RefundInvoiceDate)")

    refund_amount_minor = models.BigIntegerField(default=0, verbose_name="مبلغ الاسترداد (RefundAmount)")
    amount_minor = models.BigIntegerField(default=0, verbose_name="المبلغ النهائي المسترد (Amount)")
    commission_minor = models.BigIntegerField(default=0, verbose_name="العمولة المستردة (Commission)")
    tax_sender_minor = models.BigIntegerField(default=0, verbose_name="ضريبة المرسل (TaxSender)")
    is_same_day = models.BooleanField(default=True, verbose_name="نفس يوم عملية الدفع")
    parameters = models.JSONField(default=list, blank=True, verbose_name="معاملات إضافية (Parameters)")

    status = models.CharField(max_length=24, choices=RefundStatus.choices, default=RefundStatus.INITIATED, verbose_name="حالة الاسترداد")
    errno = models.IntegerField(default=0, verbose_name="رمز النتيجة (Errno)")
    raw_response = models.JSONField(default=dict, blank=True, verbose_name="استجابة الخادم")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل استرداد MTN Payment"
        verbose_name_plural = "سجلات استرداد MTN Payment"

    def __str__(self):
        return f"MTN Refund #{self.refund_invoice} for Base #{self.base_invoice} ({self.status})"


class MTNPayApiLog(TimeStampedModel):
    """
    Technical audit trail for all outgoing & incoming MTN Payment API calls.
    """
    request_name = models.CharField(max_length=120, db_index=True, verbose_name="اسم الطلب (Request-Name)")
    subject_terminal = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="معرف الطرفية (Subject)")
    invoice_number = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="رقم الفاتورة")
    request_payload_sanitized = models.JSONField(default=dict, blank=True, verbose_name="بيانات الطلب (محمية)")
    request_signature = models.TextField(blank=True, verbose_name="توقيع الطلب الصادر (X-Signature)")
    response_status_code = models.IntegerField(default=200, verbose_name="حالة HTTP")
    response_errno = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="رمز الخطأ (Errno)")
    response_payload = models.JSONField(default=dict, blank=True, verbose_name="بيانات الاستجابة")
    response_signature_valid = models.BooleanField(default=True, verbose_name="صحة توقيع الاستجابة")
    retried_on_timeout = models.BooleanField(default=False, verbose_name="تمت إعادة المحاولة بعد 408")
    recovered_via_get = models.BooleanField(default=False, verbose_name="تمت استعادة الحالة عبر invoice/get")
    is_success = models.BooleanField(default=False, db_index=True, verbose_name="نجاح العملية")
    error_message = models.TextField(blank=True, verbose_name="رسالة الخطأ")
    duration_ms = models.IntegerField(default=0, verbose_name="زمن التنفيذ (ms)")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تدقيق MTN Payment API"
        verbose_name_plural = "سجلات تدقيق MTN Payment API"
