from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.catalog.models import ProductVariant
from apps.common.models import TimeStampedModel


class Coupon(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name="الكود")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="خصم (%)")
    max_uses = models.PositiveIntegerField(default=0, verbose_name="أقصى عدد استخدام")
    used_count = models.PositiveIntegerField(default=0, verbose_name="تم استخدامه")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الانتهاء")

    class Meta:
        verbose_name = "كوبون"
        verbose_name_plural = "الكوبونات"

    def __str__(self):
        return self.code


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing", "قيد المعالجة"
        COMPLETED = "completed", "مكتمل"
        REFUNDED = "refunded", "مسترد"
        CANCELLED = "cancelled", "ملغى"
        DISPUTED = "disputed", "متنازع عليه"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT, verbose_name="العميل")
    number = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="رقم الطلب")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING, verbose_name="الحالة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المبلغ")
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="الكوبون")
    fulfillment_data = models.JSONField(default=dict, blank=True, verbose_name="بيانات التنفيذ")
    admin_note = models.TextField(blank=True, verbose_name="ملاحظات المدير")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
        ]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE, verbose_name="الطلب")
    variant = models.ForeignKey(ProductVariant, related_name="order_items", on_delete=models.PROTECT, verbose_name="الباقة")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="سعر الوحدة")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="تكلفة الوحدة")
    total_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="السعر الإجمالي")

    class Meta:
        verbose_name = "بند طلب"
        verbose_name_plural = "بنود الطلبات"

    def __str__(self):
        return f"{self.order.number} - {self.variant}"


class OrderLog(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="logs", on_delete=models.CASCADE, verbose_name="الطلب")
    status = models.CharField(max_length=20, choices=Order.Status.choices, verbose_name="الحالة")
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="من قبل")

    class Meta:
        verbose_name = "سجل طلب"
        verbose_name_plural = "سجلات الطلبات"
        ordering = ["created_at"]


class Invoice(TimeStampedModel):
    order = models.OneToOneField(Order, related_name="invoice", on_delete=models.CASCADE, verbose_name="الطلب")
    invoice_number = models.CharField(max_length=40, unique=True, verbose_name="رقم الفاتورة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ الإجمالي")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإصدار")

    class Meta:
        verbose_name = "فاتورة"
        verbose_name_plural = "الفواتير"
