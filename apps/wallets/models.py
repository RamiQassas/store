from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Wallet(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="wallet", on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, default="SYP")
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    frozen_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [models.Index(fields=["currency"])]

    def __str__(self):
        return f"{self.user} - {self.available_balance} {self.currency}"


class LedgerEntry(TimeStampedModel):
    class EntryType(models.TextChoices):
        CREDIT = "credit", "إيداع"
        DEBIT = "debit", "خصم"
        FREEZE = "freeze", "تجميد"
        RELEASE = "release", "فك تجميد"
        REFUND = "refund", "استرداد"

    wallet = models.ForeignKey(Wallet, related_name="ledger_entries", on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
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
