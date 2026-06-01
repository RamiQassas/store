from django.db import models

from apps.common.models import TimeStampedModel


class Service(TimeStampedModel):
    class ServiceType(models.TextChoices):
        BILL_PAYMENT = "bill_payment", "دفع فواتير"
        APPOINTMENT = "appointment", "حجز موعد"
        GOVERNMENT = "government", "خدمات حكومية"
        TRANSFER = "transfer", "تحويل أموال"
        MOBILE_TOPUP = "mobile_topup", "شحن رصيد"
        CUSTOM = "custom", "مخصص"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    service_type = models.CharField(max_length=40, choices=ServiceType.choices, default=ServiceType.CUSTOM)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class ServiceField(TimeStampedModel):
    service = models.ForeignKey(Service, related_name="fields", on_delete=models.CASCADE)
    label = models.CharField(max_length=120)
    key = models.SlugField(max_length=80)
    field_type = models.CharField(max_length=20, default="text")
    required = models.BooleanField(default=True)
    options = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)
        unique_together = ("service", "key")
