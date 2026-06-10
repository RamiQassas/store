from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import ProductVariant
from apps.common.models import TimeStampedModel


class Coupon(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name=_("Code"))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Discount (%)"))
    max_uses = models.PositiveIntegerField(default=0, verbose_name=_("Max Uses"))
    used_count = models.PositiveIntegerField(default=0, verbose_name=_("Used Count"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Expires At"))

    class Meta:
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def __str__(self):
        return self.code


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")
        DISPUTED = "disputed", _("Disputed")

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT, verbose_name=_("Customer"))
    number = models.CharField(max_length=32, unique=True, db_index=True, verbose_name=_("Order Number"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING, verbose_name=_("Status"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Total Amount"))
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Coupon"))
    fulfillment_data = models.JSONField(default=dict, blank=True, verbose_name=_("Fulfillment Data"))
    admin_note = models.TextField(blank=True, verbose_name=_("Admin Note"))
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Metadata"))
    is_delivery_read = models.BooleanField(default=False, verbose_name=_("Is Delivery Read"))

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
        ]
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-created_at"]

    def formatted_metadata(self):
        """Returns a list of dicts with 'label' and 'value' for metadata."""
        if not self.metadata:
            return []
            
        results = []
        first_item = self.items.first()
        schema = {}
        if first_item and first_item.variant and first_item.variant.product:
            schema = first_item.variant.product.form_schema
            
        fields = schema.get("fields", []) if isinstance(schema, dict) else []
        
        # Create a mapping of field key to label
        label_map = {}
        for f in fields:
            lbl = f.get("label", "")
            fid = f.get("name") or f.get("id") or f.get("key") or lbl
            if fid:
                label_map[fid] = lbl
        
        for key, val in self.metadata.items():
            label = label_map.get(key, key)
            results.append({"label": label, "value": val})
                
        return results

    def __str__(self):
        return self.number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE, verbose_name=_("Order"))
    variant = models.ForeignKey(ProductVariant, related_name="order_items", on_delete=models.PROTECT, verbose_name=_("Package"))
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("Quantity"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Unit Price"))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Unit Cost"))
    total_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("Total Price"))

    class Meta:
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")

    def __str__(self):
        return f"{self.order.number} - {self.variant}"


class OrderLog(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="logs", on_delete=models.CASCADE, verbose_name=_("Order"))
    status = models.CharField(max_length=20, choices=Order.Status.choices, verbose_name=_("Status"))
    note = models.TextField(blank=True, verbose_name=_("Note"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Created By"))

    class Meta:
        verbose_name = _("Order Log")
        verbose_name_plural = _("Order Logs")
        ordering = ["created_at"]


class Invoice(TimeStampedModel):
    order = models.OneToOneField(Order, related_name="invoice", on_delete=models.CASCADE, verbose_name=_("Order"))
    invoice_number = models.CharField(max_length=40, unique=True, verbose_name=_("Invoice Number"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_("Total Amount"))
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Issued At"))

    class Meta:
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
