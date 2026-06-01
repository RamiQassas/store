from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    icon = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class DeliveryType(models.TextChoices):
        AUTOMATIC = "automatic", "تسليم تلقائي"
        MANUAL = "manual", "تسليم يدوي"
        API = "api", "تسليم عبر API"
        CUSTOM_FORM = "custom_form", "نموذج مخصص"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    delivery_type = models.CharField(max_length=30, choices=DeliveryType.choices, default=DeliveryType.MANUAL)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_featured"]),
        ]

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=80, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    estimated_delivery_minutes = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "price")
        indexes = [models.Index(fields=["sku"]), models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class ProductFormField(TimeStampedModel):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        EMAIL = "email", "Email"
        NUMBER = "number", "Number"
        SELECT = "select", "Select"
        PASSWORD = "password", "Password"

    product = models.ForeignKey(Product, related_name="form_fields", on_delete=models.CASCADE)
    label = models.CharField(max_length=120)
    key = models.SlugField(max_length=80)
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    required = models.BooleanField(default=True)
    placeholder = models.CharField(max_length=160, blank=True)
    options = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)
        unique_together = ("product", "key")

    def __str__(self):
        return f"{self.product.name} - {self.label}"
