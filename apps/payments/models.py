from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class PaymentMethod(TimeStampedModel):
    # General Information
    name = models.CharField(max_length=120, verbose_name="اسم الوسيلة")
    logo = models.ImageField(upload_to="payment-methods/logos/", blank=True, null=True, verbose_name="الشعار")
    method_type = models.CharField(max_length=100, verbose_name="نوع الوسيلة (مثلاً: بنك، محفظة)")
    description = models.TextField(blank=True, verbose_name="وصف الوسيلة")
    display_order = models.PositiveIntegerField(default=0, blank=True, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_maintenance_mode = models.BooleanField(default=False, verbose_name="وضع الصيانة")
    
    # --- New Limit Fields ---
    daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد الإيداع اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD")
    daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد السحب اليومي لهذه الوسيلة", help_text="القيمة بالدولار USD")

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
    
    supported_currencies = models.ManyToManyField("common.Currency", blank=True, verbose_name="العملات المدعومة")
    can_deposit = models.BooleanField(default=True, verbose_name="متاحة للإيداع")
    can_withdraw = models.BooleanField(default=False, verbose_name="متاحة للسحب")

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "وسيلة دفع"
        verbose_name_plural = "وسائل الدفع"

    def __str__(self):
        return self.name

    def to_deposit_json(self):
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        from apps.common.models import Currency
        usd = Currency.objects.filter(code="USD").first()
        
        currencies_data = []
        for c in self.supported_currencies.all():
            # Convert USD limits to this currency
            min_val = c.from_base(self.deposit_min_amount) if usd else self.deposit_min_amount
            max_val = c.from_base(self.deposit_max_amount) if usd else self.deposit_max_amount
            currencies_data.append({
                "id": str(c.id), 
                "code": c.code, 
                "symbol": c.symbol,
                "min_amount": float(min_val),
                "max_amount": float(max_val)
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

    def to_withdrawal_json(self):
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        from apps.common.models import Currency
        usd = Currency.objects.filter(code="USD").first()

        currencies_data = []
        for c in self.supported_currencies.all():
            # Convert USD limits to this currency
            min_val = c.from_base(self.withdrawal_min_amount) if usd else self.withdrawal_min_amount
            max_val = c.from_base(self.withdrawal_max_amount) if usd else self.withdrawal_max_amount
            currencies_data.append({
                "id": str(c.id), 
                "code": c.code, 
                "symbol": c.symbol,
                "min_amount": float(min_val),
                "max_amount": float(max_val)
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


class DepositRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        APPROVED = "approved", "تمت الموافقة"
        REJECTED = "rejected", "مرفوض"
        COMPLETED = "completed", "مكتمل"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="deposits", on_delete=models.PROTECT, verbose_name="المستخدم")
    payment_method = models.ForeignKey(PaymentMethod, related_name="deposits", on_delete=models.PROTECT, verbose_name="وسيلة الدفع")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    wallet_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="المبلغ بعملة المحفظة")
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="مبلغ الرسوم")
    final_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ النهائي (الصافي)")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    transaction_id = models.CharField(max_length=160, blank=True, db_index=True, verbose_name="رقم العملية / المرجع")
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
    metadata = models.JSONField(default=dict, blank=True)

    def calculate_fees(self):
        self.fee_amount = self.payment_method.calculate_fee(self.amount, mode="deposit")
        self.final_amount = self.amount - self.fee_amount

    def save(self, *args, **kwargs):
        if self.amount and self.payment_method:
            self.calculate_fees()
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
    proof_image = models.ImageField(upload_to="withdrawal-proofs/", blank=True, null=True, verbose_name="إثبات التحويل")
    
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reviewed_withdrawals",
        on_delete=models.SET_NULL,
        verbose_name="تمت المراجعة من قبل"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    metadata = models.JSONField(default=dict, blank=True)

    @property
    def display_payout_value(self):
        """Safely returns a primary value for display in lists."""
        if not self.payout_details:
            return ""
        
        # 1. Check direct address
        addr = self.payout_details.get("address")
        if addr:
            return str(addr)
            
        # 2. Check dynamic fields
        dynamic = self.payout_details.get("dynamic")
        if isinstance(dynamic, dict) and dynamic:
            # Safely get the first non-empty value
            for val in dynamic.values():
                if val:
                    return str(val)
        
        return ""

    def calculate_fees(self):
        self.fee_amount = self.payment_method.calculate_fee(self.amount, mode="withdrawal")
        self.final_amount = self.amount - self.fee_amount

    def save(self, *args, **kwargs):
        if self.amount and self.payment_method:
            self.calculate_fees()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "طلب سحب"
        verbose_name_plural = "طلبات السحب"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.amount} {self.currency} - {self.status}"
