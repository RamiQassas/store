import uuid

from django.db import models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class Currency(TimeStampedModel):
    name = models.CharField(max_length=50, verbose_name="اسم العملة")
    code = models.CharField(max_length=3, unique=True, verbose_name="رمز العملة (ISO)")
    symbol = models.CharField(max_length=10, verbose_name="رمز العملة")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, help_text="نسبة الصرف مقابل العملة الأساسية (USD)")
    decimal_places = models.PositiveIntegerField(default=2, verbose_name="عدد الخانات العشرية")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_default = models.BooleanField(default=False, verbose_name="العملة الافتراضية")

    class Meta:
        ordering = ["display_order", "code"]
        verbose_name = "عملة"
        verbose_name_plural = "العملات"

    def __str__(self):
        return f"{self.code} ({self.symbol})"

    def save(self, *args, **kwargs):
        if self.is_default:
            Currency.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
