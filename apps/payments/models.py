from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class PaymentMethod(TimeStampedModel):
    class MethodType(models.TextChoices):
        BANK = "bank", "بنك"
        WALLET = "wallet", "محفظة إلكترونية"
        CRYPTO = "crypto", "عملات رقمية"
        CASH = "cash", "نقدي"
        MOBILE_PAYMENT = "mobile_payment", "دفع عبر الهاتف"

    # General Information
    name = models.CharField(max_length=120, verbose_name="اسم الوسيلة")
    logo = models.ImageField(upload_to="payment-methods/logos/", blank=True, null=True, verbose_name="الشعار")
    icon = models.CharField(max_length=50, blank=True, verbose_name="الأيقونة (FontAwesome)")
    method_type = models.CharField(max_length=40, choices=MethodType.choices, verbose_name="نوع الوسيلة")
    provider_name = models.CharField(max_length=120, blank=True, verbose_name="اسم المزود أو البنك")
    description = models.TextField(blank=True, verbose_name="وصف الوسيلة")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_maintenance_mode = models.BooleanField(default=False, verbose_name="وضع الصيانة")

    # Payment Details (For Deposits)
    account_number = models.CharField(max_length=120, blank=True, verbose_name="رقم الحساب")
    account_name = models.CharField(max_length=120, blank=True, verbose_name="اسم صاحب الحساب")
    iban = models.CharField(max_length=120, blank=True, verbose_name="IBAN")
    wallet_address = models.CharField(max_length=255, blank=True, verbose_name="عنوان المحفظة / معرف")
    qr_image = models.ImageField(upload_to="payment-methods/qr/", blank=True, null=True, verbose_name="صورة QR")
    instructions = models.TextField(blank=True, verbose_name="تعليمات الدفع")
    custom_notes = models.TextField(blank=True, verbose_name="ملاحظات إضافية")

    # Limits and Fees
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الحد الأدنى")
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000000.00"), verbose_name="الحد الأقصى")
    fixed_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="رسوم ثابتة")
    percentage_fee = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="رسوم مئوية (%)")
    supported_currencies = models.ManyToManyField("common.Currency", blank=True, verbose_name="العملات المدعومة")

    # Capabilities
    can_deposit = models.BooleanField(default=True, verbose_name="متاحة للإيداع")
    can_withdraw = models.BooleanField(default=False, verbose_name="متاحة للسحب")

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "وسيلة دفع"
        verbose_name_plural = "وسائل الدفع"

    def __str__(self):
        return self.name


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
        fixed_fee = self.payment_method.fixed_fee
        percentage_fee = (self.amount * self.payment_method.percentage_fee) / 100
        self.fee_amount = fixed_fee + percentage_fee
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

    def calculate_fees(self):
        fixed_fee = self.payment_method.fixed_fee
        percentage_fee = (self.amount * self.payment_method.percentage_fee) / 100
        self.fee_amount = fixed_fee + percentage_fee
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
