from decimal import Decimal

from django.db import models
from django.conf import settings

from apps.common.models import TimeStampedModel
from apps.common.tenant_utils import TenantManager


from django.utils.text import slugify

class Category(TimeStampedModel):
    name = models.CharField(max_length=120, verbose_name="اسم التصنيف")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="categories/", blank=True, null=True, verbose_name="صورة التصنيف")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_featured = models.BooleanField(default=False, verbose_name="تصنيف مميز (يظهر في الرئيسية)")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="categories",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    product_type = models.CharField(
        max_length=20,
        choices=(
            ("digital", "منتج رقمي"),
            ("physical", "منتج مادي"),
        ),
        default="digital",
        verbose_name="نوع المنتج"
    )
    name = models.CharField(max_length=160, verbose_name="اسم المنتج")
    category = models.ForeignKey(Category, related_name="products", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="التصنيف")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    
    # Media
    image = models.ImageField(upload_to="products/main/", blank=True, null=True, verbose_name="الصورة الأساسية")
    cover_image = models.ImageField(upload_to="products/covers/", blank=True, null=True, verbose_name="صورة الغلاف")
    thumbnail = models.ImageField(upload_to="products/thumbs/", blank=True, null=True, verbose_name="مصغرة")

    description = models.TextField(blank=True, verbose_name="الوصف")
    instructions = models.TextField(blank=True, verbose_name="تعليمات الاستخدام")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_featured = models.BooleanField(default=False, verbose_name="مميز (عرض في الرئيسية)")
    is_out_of_stock = models.BooleanField(default=False, verbose_name="غير متوفر (سيظل معروضاً)")
    is_sale = models.BooleanField(default=False, verbose_name="عليه عرض/تخفيض")
    is_api_product = models.BooleanField(default=False, verbose_name="منتج من الـ API")
    api_provider = models.CharField(
        max_length=50,
        choices=(
            ("alkasr", "الكاسر VIP"),
            ("tafa3olcard", "تفاعل كارد (Tafa3ol Card)"),
            ("generic", "مزوّد عام (Generic API)"),
            ("smm", "مزوّد خدمات (SMM)"),
            ("other", "مزوّد آخر"),
        ),
        default="generic",
        verbose_name="مزوّد الخدمة (API)",
        blank=True,
        null=True
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    delivery_time_display = models.CharField(max_length=60, blank=True, verbose_name="وقت التسليم المعروض", help_text="مثال: 5-15 دقيقة أو 1-2 ساعة")

    @property
    def api_provider_display_name(self):
        if self.api_provider == "alkasr":
            return "الكاسر VIP"
        elif self.api_provider == "tafa3olcard":
            return "تفاعل كارد"
        elif self.api_provider == "smm":
            return "مزوّد خدمات (SMM)"
        elif self.api_provider and self.api_provider not in ("generic", ""):
            return self.get_api_provider_display()

        # Fallback by checking provider mapping
        try:
            m = self.provider_mappings.first()
            if m and m.provider_product and m.provider_product.profile:
                p_name = m.provider_product.profile.provider_name
                if p_name and p_name not in ("رقميات", "Generic"):
                    return p_name
        except Exception:
            pass

        return "الكاسر VIP"
    
    # Inventory Tracking
    track_inventory = models.BooleanField(default=False, verbose_name="تتبع المخزون والكمية")
    quantity = models.IntegerField(default=0, verbose_name="الكمية المتوفرة")
    low_stock_threshold = models.IntegerField(default=5, verbose_name="حد التذكير بنفاد الكمية")
    
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

    def save(self, *args, **kwargs):
        if self.track_inventory and self.quantity > 0 and self.is_out_of_stock:
            self.is_out_of_stock = False
        super().save(*args, **kwargs)


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="gallery", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True, verbose_name="الصورة")
    video = models.FileField(upload_to="products/videos/", blank=True, null=True, verbose_name="الفيديو")
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    @property
    def is_video(self):
        return bool(self.video)

    @property
    def url(self):
        if self.video:
            return self.video.url
        if self.image:
            return self.image.url
        return ""

    class Meta:
        ordering = ("sort_order",)
        verbose_name = "صورة المنتج"
        verbose_name_plural = "معرض صور المنتج"


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE, verbose_name="المنتج")
    name = models.CharField(max_length=120, verbose_name="اسم الباقة")
    sku = models.CharField(max_length=80, unique=True, verbose_name="SKU")
    
    # Default Prices
    price = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0.00000000"), verbose_name="السعر الأساسي")
    wholesale_price = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0.00000000"), verbose_name="سعر الجملة")
    vip_price = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0.00000000"), verbose_name="سعر VIP")
    cost = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0.00000000"), verbose_name="التكلفة")
    
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="خصم (%)")
    is_sale = models.BooleanField(default=False, verbose_name="عليه عرض خاص")
    estimated_delivery_minutes = models.PositiveIntegerField(default=0, verbose_name="وقت التسليم المتوقع (دقيقة)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_temporarily_disabled = models.BooleanField(default=False, verbose_name="إيقاف مؤقت (يظهر كغير متوفر)")
    is_recharge_card = models.BooleanField(default=False, verbose_name="بطاقة شحن تلقائية", help_text="إذا تم التفعيل، سيتم توليد كود شحن تلقائياً عند اكتمال الطلب.")
    delivery_type = models.CharField(
        max_length=20,
        choices=(
            ("manual", "تسليم يدوي"),
            ("keys", "تسليم تلقائي (أكواد)"),
        ),
        default="manual",
        verbose_name="طريقة التسليم"
    )
    api_product_id = models.IntegerField(null=True, blank=True, verbose_name="رقم المنتج في الـ API")
    recharge_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة كود الشحن التلقائي")
    recharge_currency = models.ForeignKey("common.Currency", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="عملة كود الشحن التلقائي")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")

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
        if not user or not getattr(user, 'is_authenticated', False):
            return self.price

        # 1. Check for user-specific override
        user_override = self.user_prices.filter(user=user).first()
        if user_override:
            return user_override.price

        # 2. Check for specific tier override
        user_tier = getattr(user, 'tier', None)
        if user_tier:
            override = self.tier_prices.filter(tier=user_tier).first()
            if override:
                return override.price
            
        # 3 & 4. Fallback to default prices based on tier
        from apps.accounts.models import User
        if user_tier == User.Tier.COST:
            return self.cost if (self.cost and self.cost > 0) else self.price
        elif user_tier == User.Tier.VIP:
            return self.vip_price or self.price
        elif user_tier == User.Tier.DEALER:
            return self.wholesale_price or self.price
        return self.price


class ProductTierPrice(TimeStampedModel):
    """
    Explicit price override for a specific user tier.
    """
    variant = models.ForeignKey(ProductVariant, related_name="tier_prices", on_delete=models.CASCADE)
    tier = models.CharField(max_length=20, verbose_name="الفئة")
    price = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="السعر")

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
    price = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta:
        unique_together = ("variant", "user")
        verbose_name = "سعر مخصص لمستخدم"
        verbose_name_plural = "أسعار مخصصة لمستخدمين"


class ProductSuggestion(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "تمت الموافقة"
        REJECTED = "rejected", "مرفوض"
        IMPLEMENTED = "implemented", "تم التوفير"

    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="product_suggestions",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="suggestions", on_delete=models.CASCADE, verbose_name="المستخدم")
    product_name = models.CharField(max_length=160, verbose_name="اسم المنتج/الخدمة المقترح")
    category_name = models.CharField(max_length=120, blank=True, verbose_name="التصنيف (اختياري)")
    description = models.TextField(verbose_name="وصف الخدمة أو رابط لها")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    admin_notes = models.TextField(blank=True, verbose_name="ملاحظات الإدارة")

    class Meta:
        verbose_name = "مقترح منتج"
        verbose_name_plural = "مقترحات المنتجات"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.product_name} - {self.user.email}"


class ProductKey(TimeStampedModel):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="keys", verbose_name="الباقة")
    key_code = models.CharField(max_length=255, verbose_name="الكود")
    is_used = models.BooleanField(default=False, verbose_name="مستخدم")
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_keys",
        verbose_name="المشتري"
    )
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاستخدام")
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="keys",
        verbose_name="الطلب"
    )

    class Meta:
        verbose_name = "مفتاح منتج"
        verbose_name_plural = "مفاتيح المنتجات"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.variant.name} - {self.key_code[:20]}"


class APIIntegration(TimeStampedModel):
    """
    Model for managing multiple API Provider configurations.
    Enables storing credentials, active status, and sharing global APIs with tenant stores.
    """
    PROVIDER_CHOICES = (
        ("alkasr", "رقميات"),
        ("tafa3olcard", "تفاعل كارد (Tafa3ol Card)"),
        ("generic", "مزوّد عام (Generic API)"),
        ("smm", "مزوّد خدمات (SMM)"),
        ("other", "مزوّد آخر"),
    )
    
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="api_integrations",
        verbose_name="المتجر"
    )
    objects = models.Manager()
    all_objects = models.Manager()
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default="generic",
        verbose_name="نوع المزود"
    )
    name = models.CharField(
        max_length=100,
        verbose_name="اسم بوابة الربط"
    )
    base_url = models.URLField(
        max_length=255,
        verbose_name="رابط المزود (Base URL)"
    )
    api_token = models.CharField(
        max_length=255,
        verbose_name="مفتاح الوصول (API Token)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="تفعيل الاتصال"
    )
    allow_sub_stores = models.BooleanField(
        default=True,
        verbose_name="السماح للمتاجر الفرعية بالاستخدام"
    )

    class Meta:
        verbose_name = "إعداد ربط API"
        verbose_name_plural = "إعدادات ربط API"
        ordering = ("provider", "name")

    def __str__(self):
        store_label = f" ({self.store.name})" if self.store else " (عام/منصة)"
        return f"{self.name} - {self.get_provider_display()}{store_label}"



# Legacy model removed (ProductFormField)


class APITransaction(TimeStampedModel):
    integration = models.ForeignKey(
        "catalog.APIIntegration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="بوابة الربط"
    )
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="api_transactions",
        verbose_name="المتجر"
    )
    provider = models.CharField(max_length=50, verbose_name="المزود")
    action = models.CharField(max_length=100, verbose_name="العملية") # e.g. "newOrder", "check", "profile", "products"
    product_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم المنتج في المزود")
    order_uuid = models.CharField(max_length=100, blank=True, null=True, verbose_name="المعرف الفريد للطلب")
    request_url = models.TextField(verbose_name="رابط الطلب")
    request_params = models.TextField(blank=True, null=True, verbose_name="معاملات الطلب")
    response_status = models.IntegerField(null=True, blank=True, verbose_name="رمز استجابة HTTP")
    response_body = models.TextField(blank=True, null=True, verbose_name="محتوى الاستجابة")
    is_success = models.BooleanField(default=False, verbose_name="هل نجحت العملية؟")
    error_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="رمز الخطأ")
    error_message = models.TextField(blank=True, null=True, verbose_name="رسالة الخطأ")

    class Meta:
        verbose_name = "سجل حركة API"
        verbose_name_plural = "سجلات حركات API"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.provider} - {self.action} ({self.created_at})"
