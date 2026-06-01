from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, verbose_name="اسم التصنيف")
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    icon = models.CharField(max_length=80, blank=True, verbose_name="الأيقونة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class DeliveryType(models.TextChoices):
        AUTOMATIC = "automatic", "تسليم تلقائي"
        MANUAL = "manual", "تسليم يدوي"
        API = "api", "تسليم عبر API"
        CUSTOM_FORM = "custom_form", "نموذج مخصص"

    name = models.CharField(max_length=160, verbose_name="اسم المنتج")
    slug = models.SlugField(max_length=180, unique=True)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT, verbose_name="التصنيف")
    
    # Media
    image = models.ImageField(upload_to="products/main/", blank=True, null=True, verbose_name="الصورة الأساسية")
    cover_image = models.ImageField(upload_to="products/covers/", blank=True, null=True, verbose_name="صورة الغلاف")
    thumbnail = models.ImageField(upload_to="products/thumbs/", blank=True, null=True, verbose_name="مصغرة")
    icon = models.CharField(max_length=80, blank=True, verbose_name="أيقونة (FA)")

    description = models.TextField(blank=True, verbose_name="الوصف")
    instructions = models.TextField(blank=True, verbose_name="تعليمات الاستخدام")
    delivery_type = models.CharField(max_length=30, choices=DeliveryType.choices, default=DeliveryType.MANUAL, verbose_name="نوع التسليم")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_featured = models.BooleanField(default=False, verbose_name="مميز (عرض في الرئيسية)")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_featured"]),
        ]

    def __str__(self):
        return self.name


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="gallery", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)
        verbose_name = "صورة المنتج"
        verbose_name_plural = "معرض صور المنتج"


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE, verbose_name="المنتج")
    name = models.CharField(max_length=120, verbose_name="اسم الباقة")
    sku = models.CharField(max_length=80, unique=True, verbose_name="SKU")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="السعر")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="التكلفة")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="خصم (%)")
    estimated_delivery_minutes = models.PositiveIntegerField(default=0, verbose_name="وقت التسليم المتوقع (دقيقة)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "باقة منتج"
        verbose_name_plural = "باقات المنتجات"
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
