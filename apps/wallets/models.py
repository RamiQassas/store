from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Wallet(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="wallet", on_delete=models.CASCADE)
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    
    # Balance breakdown
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المتاح")
    frozen_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المجمد (سحوبات/طلبات)")
    held_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المحجوز (إداري/نزاعات)")
    pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المعلق (إيداعات قيد الانتظار)")
    reserved_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المحجوز (طلبات قيد التنفيذ)")
    debt_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الرصيد المستحق (ديون)")
    debt_is_withdrawable = models.BooleanField(default=False, verbose_name="الدين قابل للسحب")

    class Meta:
        indexes = [models.Index(fields=["currency"])]
        verbose_name = "محفظة"
        verbose_name_plural = "المحافظ"
        constraints = [
            models.CheckConstraint(
                check=models.Q(available_balance__gte=0),
                name="available_balance_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(frozen_balance__gte=0),
                name="frozen_balance_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(held_balance__gte=0),
                name="held_balance_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(pending_balance__gte=0),
                name="pending_balance_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(reserved_balance__gte=0),
                name="reserved_balance_non_negative"
            ),
            models.CheckConstraint(
                check=models.Q(debt_balance__gte=0),
                name="debt_balance_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.available_balance} {self.currency}"
    
    @property
    def total_balance(self):
        return self.available_balance + self.frozen_balance + self.held_balance
    
    @property
    def withdrawable_balance(self):
        if self.debt_is_withdrawable:
            return self.available_balance
        return max(Decimal("0.00"), self.available_balance - self.debt_balance)


class LedgerEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        CREDIT = "credit", "إيداع"
        DEBIT = "debit", "خصم"
        FREEZE = "freeze", "تجميد"
        RELEASE = "release", "فك تجميد"
        HOLD = "hold", "حجز إداري"
        UNHOLD = "unhold", "فك حجز"
        RESERVE = "reserve", "حجز طلب"
        UNRESERVE = "unreserve", "فك حجز طلب"
        REFUND = "refund", "استرداد"
        PENDING_DEPOSIT = "pending_deposit", "إيداع معلق"
        PENDING_CANCEL = "pending_cancel", "إلغاء إيداع معلق"
        DEBT_ADD = "debt_add", "إضافة دين"
        DEBT_PAYMENT = "debt_payment", "سداد دين"

    wallet = models.ForeignKey(Wallet, related_name="ledger_entries", on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, help_text="Available balance after this operation")
    reference = models.CharField(max_length=120, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    
    # Enhanced tracking
    source = models.CharField(max_length=100, blank=True, help_text="Source of the transaction (e.g. order, deposit, admin)")
    reason = models.CharField(max_length=255, blank=True, help_text="Reason for the transaction")
    
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["entry_type"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["source"]),
        ]
        verbose_name = "سجل حركة"
        verbose_name_plural = "سجلات الحركة"
        ordering = ["-created_at"]


class WalletTransaction(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        COMPLETED = "completed", "مكتمل"
        FAILED = "failed", "فشل"
        REFUNDED = "refunded", "مسترد"

    wallet = models.ForeignKey(Wallet, related_name="transactions", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_type = models.CharField(max_length=40)
    reference = models.CharField(max_length=120, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["reference"]),
        ]
        verbose_name = "عملية مالية"
        verbose_name_plural = "العمليات المالية"
        ordering = ["-created_at"]


class BalanceTransfer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        COMPLETED = "completed", "مكتمل"
        FAILED = "failed", "فشل"
        REJECTED = "rejected", "مرفوض"
        SUSPENDED = "suspended", "معلقة"

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="sent_transfers", on_delete=models.PROTECT, verbose_name="المرسل")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="received_transfers", on_delete=models.PROTECT, verbose_name="المستلم")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ المحول")
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="رسوم التحويل")
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ الصافي للمستلم")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    reference = models.CharField(max_length=120, blank=True, unique=True, verbose_name="الرقم المرجعي")
    note = models.CharField(max_length=255, blank=True, verbose_name="ملاحظة")

    class Meta:
        indexes = [
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["recipient", "created_at"]),
            models.Index(fields=["reference"]),
        ]
        verbose_name = "تحويل رصيد"
        verbose_name_plural = "تحويلات الرصيد"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender} -> {self.recipient} ({self.amount} {self.currency.code})"


class RechargeCard(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        REDEEMED = "redeemed", "تم استخدامه"
        CANCELLED = "cancelled", "ملغي"

    code = models.CharField(max_length=50, unique=True, verbose_name="رمز الشحن")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="قيمة الشحن")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="الحالة")
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name="created_recharge_cards",
        verbose_name="أنشئ بواسطة"
    )
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name="redeemed_recharge_cards",
        verbose_name="شحن بواسطة"
    )
    redeemed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الشحن")
    
    order = models.ForeignKey(
        "orders.Order", 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name="recharge_cards",
        verbose_name="الطلب المرتبط"
    )

    class Meta:
        verbose_name = "بطاقة شحن"
        verbose_name_plural = "بطاقات الشحن"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.amount} {self.currency.code})"
