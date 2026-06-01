from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class PaymentProvider(TimeStampedModel):
    class ProviderType(models.TextChoices):
        SHAM_CASH = "sham_cash", "شام كاش"
        MANUAL = "manual", "تحقق يدوي"
        BANK = "bank", "بنك"

    name = models.CharField(max_length=120)
    provider_type = models.CharField(max_length=40, choices=ProviderType.choices)
    is_active = models.BooleanField(default=True)
    webhook_secret = models.CharField(max_length=255, blank=True)
    config = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class DepositRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PAID = "paid", "مدفوع"
        FAILED = "failed", "فشل"
        REFUNDED = "refunded", "مسترد"
        REJECTED = "rejected", "مرفوض"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="deposits", on_delete=models.PROTECT)
    provider = models.ForeignKey(PaymentProvider, related_name="deposits", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="SYP")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    external_reference = models.CharField(max_length=160, blank=True, db_index=True)
    proof_image = models.ImageField(upload_to="deposit-proofs/", blank=True, null=True)
    customer_note = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="reviewed_deposits", on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["external_reference"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.amount} {self.currency} - {self.status}"
