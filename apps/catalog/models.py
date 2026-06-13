from decimal import Decimal

from django.db import models
from django.conf import settings

from apps.common.models import TimeStampedModel


from django.utils.text import slugify

class Category(TimeStampedModel):
    name = models.CharField(max_length=120, verbose_name="اسم التصنيف")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    name = models.CharField(max_length=160, verbose_name="اسم المنتج")
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT, verbose_name="التصنيف")
    
    # Media
    image = models.ImageField(upload_to="products/main/", blank=True, null=True, verbose_name="الصورة الأساسية")
    cover_image = models.ImageField(upload_to="products/covers/", blank=True, null=True, verbose_name="صورة الغلاف")
    thumbnail = models.ImageField(upload_to="products/thumbs/", blank=True, null=True, verbose_name="مصغرة")

    description = models.TextField(blank=True, verbose_name="الوصف")
    instructions = models.TextField(blank=True, verbose_name="تعليمات الاستخدام")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_featured = models.BooleanField(default=False, verbose_name="مميز (عرض في الرئيسية)")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    delivery_time_display = models.CharField(max_length=60, blank=True, verbose_name="وقت التسليم المعروض", help_text="مثال: 5-15 دقيقة أو 1-2 ساعة")
    
    # Dynamic Form Engine
    form_schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="نموذج البيانات المطلوبة من العميل",
        help_text='مثال: {"version": 1, "fields": [{"label": "اسم المستخدم", "type": "text", "required": true}]}'
    )
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"
        ordering = ("sort_order", "name")
        indexes = [
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
    
    # Default Prices
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="السعر الافتراضي (Retail)")
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="سعر الجملة")
    vip_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="سعر VIP")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="التكلفة")
    
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="خصم (%)")
    estimated_delivery_minutes = models.PositiveIntegerField(default=0, verbose_name="وقت التسليم المتوقع (دقيقة)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_temporarily_disabled = models.BooleanField(default=False, verbose_name="إيقاف مؤقت (يظهر كغير متوفر)")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "باقة منتج"
        verbose_name_plural = "باقات المنتجات"
        ordering = ("sort_order", "price")
        indexes = [models.Index(fields=["sku"]), models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    @property
    def margin(self):
        """Calculates the absolute margin based on the base price and cost."""
        return self.price - self.cost

    @property
    def margin_percent(self):
        """Calculates the margin percentage."""
        if self.price > 0:
            return (self.margin / self.price) * 100
        return 0

    def get_price_for_user(self, user):
        """
        Returns the appropriate price based on the user's tier.
        Checks for:
        1. User-specific override
        2. Tier-specific override
        3. Default tier prices
        4. Base price
        """
        # 1. Check for user-specific override
        user_override = self.user_prices.filter(user=user).first()
        if user_override:
            return user_override.price

        # 2. Check for specific tier override
        override = self.tier_prices.filter(tier=user.tier).first()
        if override:
            return override.price
            
        # 3 & 4. Fallback to default prices based on tier
        from apps.accounts.models import User
        if user.tier == User.Tier.VIP:
            return self.vip_price or self.price
        elif user.tier == User.Tier.DEALER:
            return self.wholesale_price or self.price
        return self.price


class ProductTierPrice(TimeStampedModel):
    """
    Explicit price override for a specific user tier.
    """
    variant = models.ForeignKey(ProductVariant, related_name="tier_prices", on_delete=models.CASCADE)
    tier = models.CharField(max_length=20, verbose_name="الفئة")
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="السعر")

    class Meta:
        unique_together = ("variant", "tier")
        verbose_name = "سعر فئة"
        verbose_name_plural = "أسعار الفئات"


class ProductUserPrice(TimeStampedModel):
    """
    Manual price override for a specific individual user.
    Highest priority in pricing logic.
    """
    variant = models.ForeignKey(ProductVariant, related_name="user_prices", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ("variant", "user")
        verbose_name = "سعر مخصص لمستخدم"
        verbose_name_plural = "أسعار مخصصة لمستخدمين"


# Legacy model removed (ProductFormField)

