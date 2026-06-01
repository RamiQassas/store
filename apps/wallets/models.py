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

    class Meta:
        indexes = [models.Index(fields=["currency"])]
        verbose_name = "محفظة"
        verbose_name_plural = "المحافظ"

    def __str__(self):
        return f"{self.user} - {self.available_balance} {self.currency}"
    
    @property
    def total_balance(self):
        return self.available_balance + self.frozen_balance + self.held_balance


class LedgerEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        CREDIT = "credit", "إيداع"
        DEBIT = "debit", "خصم"
        FREEZE = "freeze", "تجميد"
        RELEASE = "release", "فك تجميد"
        HOLD = "hold", "حجز إداري"
        UNHOLD = "unhold", "فك حجز"
        REFUND = "refund", "استرداد"
        PENDING_DEPOSIT = "pending_deposit", "إيداع معلق"
        PENDING_CANCEL = "pending_cancel", "إلغاء إيداع معلق"

    wallet = models.ForeignKey(Wallet, related_name="ledger_entries", on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, help_text="Available balance after this operation")
    reference = models.CharField(max_length=120, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["entry_type"]),
            models.Index(fields=["reference"]),
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
