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
    daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد الإيداع اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD")
    daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد السحب اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD")
    
    # --- Daily Usage Tracking ---
    daily_deposit_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    daily_withdrawal_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    last_limit_reset = models.DateTimeField(default=timezone.now)

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
            
        self.save(update_fields=["daily_deposit_usage", "global_deposit_usage", "is_maintenance_mode"])

    def add_withdrawal_usage(self, amount_in_usd):
        self.reset_daily_limits_if_needed()
        amt = Decimal(str(amount_in_usd))
        self.daily_withdrawal_usage += amt
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
            
        self.save(update_fields=["daily_withdrawal_usage", "global_withdrawal_usage", "is_maintenance_mode"])

    def reset_daily_limits_if_needed(self):
        """Resets daily usage if the date has changed in Damascus time."""
        from django.utils import timezone
        now = timezone.localtime(timezone.now())
        last_reset_local = timezone.localtime(self.last_limit_reset)
        if last_reset_local.date() < now.date():
            self.daily_deposit_usage = Decimal("0.00")
            self.daily_withdrawal_usage = Decimal("0.00")
            self.last_limit_reset = now
            self.save(update_fields=["daily_deposit_usage", "daily_withdrawal_usage", "last_limit_reset"])

    def to_deposit_json(self, user=None):
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        from apps.common.models import Currency
        from django.utils import timezone
        
        self.reset_daily_limits_if_needed()
        usd = Currency.objects.filter(code="USD").first()
        
        # 1. Start with Global Method Daily Limit
        method_remaining = max(Decimal("0.00"), self.daily_deposit_limit - self.daily_deposit_usage)
        
        # 2. Compare with User's Daily Limit (Total across all methods)
        user_remaining = Decimal("9999999.99")
        if user and user.is_authenticated:
            user.reset_daily_limits_if_needed()
            user_remaining = max(Decimal("0.00"), user.daily_deposit_limit - user.daily_deposit_usage)
            
            # 3. Check for User-Specific Method Custom Limit
            if user.has_custom_limits and user.custom_payment_limits and isinstance(user.custom_payment_limits, dict):
                user_custom = user.custom_payment_limits.get(str(self.id)) or user.custom_payment_limits.get(self.id.hex) if hasattr(self.id, 'hex') else user.custom_payment_limits.get(str(self.id))
                if isinstance(user_custom, dict) and user_custom.get('deposit'):
                    try:
                        custom_limit = Decimal(str(user_custom['deposit']))
                        # User custom limit overrides the global method limit for THIS user
                        method_remaining = custom_limit
                    except: pass
        
        # Effective max is the MINIMUM of what's allowed by the user and the method
        effective_deposit_max = min(method_remaining, user_remaining)
        
        # 4. Cap by per-transaction max
        effective_deposit_max = min(effective_deposit_max, self.deposit_max_amount)
        
        # 5. Check Global Cap (Task 5)
        if self.global_deposit_cap > 0:
            cap_remaining = max(Decimal("0.00"), self.global_deposit_cap - self.global_deposit_usage)
            effective_deposit_max = min(effective_deposit_max, cap_remaining)

        currencies_data = []
        effective_rate = self.get_effective_deposit_rate()
        for c in self.supported_currencies.all():
            # Convert USD limits to this currency
            min_val = c.from_base(self.deposit_min_amount) if usd else self.deposit_min_amount
            max_val = c.from_base(effective_deposit_max) if usd else effective_deposit_max
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
                return self.logo.url
            except Exception:
                pass
        if self.provider == "paymera" or "paymera" in (self.name or "").lower() or "بيميرا" in (self.name or ""):
            return "/media/payment-methods/logos/paymera.png"
        if self.provider == "sham_cash" or "sham" in (self.name or "").lower() or "شام" in (self.name or ""):
            return "/static/site/img/brands/shamcash.svg"
        return None

    class Meta:
        ordering = ["provider", "name"]
        verbose_name = "بوابة دفع API"
        verbose_name_plural = "بوابات دفع API"

    def __str__(self):
        return f"{self.name} - {self.get_provider_display()}"


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
        """Returns a list of dicts with 'label', 'value', and 'type' for metadata."""
        if not self.metadata:
            return []
            
        results = []
        schema = self.payment_method.deposit_form_schema
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
            label, ftype = field_map.get(key, (key, "text"))
            
            # Heuristic: If value looks like an image path, force type to image
            if isinstance(val, str) and (val.startswith("/media/") or any(val.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])):
                ftype = "image"
                
            results.append({"label": label, "value": val, "type": ftype})
                
        return results

    def calculate_fees(self):
        self.fee_amount = self.payment_method.calculate_fee(self.amount, mode="deposit")
        self.final_amount = self.amount - self.fee_amount
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
