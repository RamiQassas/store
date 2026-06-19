import uuid
from django.db import models
from django.conf import settings
from apps.common.models import TimeStampedModel

class SubscriptionPlan(TimeStampedModel):
    name = models.CharField(max_length=100, verbose_name="اسم الباقة")
    description = models.TextField(blank=True, verbose_name="وصف الباقة")
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="السعر الشهري (USD)")
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="السعر السنوي (USD)")
    
    # Limits
    max_products = models.PositiveIntegerField(default=10, verbose_name="أقصى عدد منتجات")
    max_employees = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد موظفين")
    max_monthly_orders = models.PositiveIntegerField(default=100, verbose_name="أقصى عدد طلبات شهرياً")
    max_storage_mb = models.PositiveIntegerField(default=100, verbose_name="مساحة التخزين القصوى (ميغابايت)")
    max_images = models.PositiveIntegerField(default=100, verbose_name="أقصى عدد صور")
    max_branches = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد فروع")
    max_coupons = models.PositiveIntegerField(default=5, verbose_name="أقصى عدد كوبونات")
    max_domains = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد دومينات مخصصة")
    
    # Features
    custom_domain_enabled = models.BooleanField(default=False, verbose_name="دعم دومين مخصص")
    remove_branding_enabled = models.BooleanField(default=False, verbose_name="إزالة شعار رقميات")
    api_access_enabled = models.BooleanField(default=False, verbose_name="صلاحية الوصول للـ API")
    advanced_reports_enabled = models.BooleanField(default=False, verbose_name="التقارير المتقدمة")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "خطة اشتراك"
        verbose_name_plural = "خطط الاشتراكات"

    def __str__(self):
        return self.name


class Store(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        TRIALING = "trialing", "فترة تجريبية"
        UNPAID = "unpaid", "غير مدفوع"
        CANCELLED = "cancelled", "ملغى"
        SUSPENDED = "suspended", "موقوف"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_stores",
        verbose_name="المالك"
    )
    name = models.CharField(max_length=120, verbose_name="اسم المتجر")
    description = models.TextField(blank=True, verbose_name="وصف المتجر")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="رابط المتجر الفرعي (Subdomain slug)")
    custom_domain = models.CharField(max_length=255, unique=True, null=True, blank=True, verbose_name="النطاق المخصص")
    
    # Branding
    logo = models.ImageField(upload_to="stores/logos/", blank=True, null=True, verbose_name="شعار المتجر")
    banner = models.ImageField(upload_to="stores/banners/", blank=True, null=True, verbose_name="بانر المتجر")
    
    # Subscription status
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stores",
        verbose_name="خطة الاشتراك"
    )
    subscription_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TRIALING,
        verbose_name="حالة الاشتراك"
    )
    subscription_start = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ بدء الاشتراك")
    subscription_end = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ انتهاء الاشتراك")
    
    # Styling and Theme Colors
    primary_color = models.CharField(max_length=7, default="#06b6d4", verbose_name="اللون الأساسي")
    secondary_color = models.CharField(max_length=7, default="#0891b2", verbose_name="اللون الثانوي")
    background_color = models.CharField(max_length=7, default="#ffffff", verbose_name="لون الخلفية")
    text_color = models.CharField(max_length=7, default="#0f172a", verbose_name="لون النص")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    # Contact details
    phone = models.CharField(max_length=32, blank=True, verbose_name="الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    address = models.TextField(blank=True, verbose_name="العنوان")
    
    # Social links
    social_facebook = models.CharField(max_length=255, blank=True, verbose_name="فيسبوك")
    social_instagram = models.CharField(max_length=255, blank=True, verbose_name="إنستغرام")
    social_twitter = models.CharField(max_length=255, blank=True, verbose_name="تويتر/إكس")
    social_tiktok = models.CharField(max_length=255, blank=True, verbose_name="تيك توك")

    class Meta:
        verbose_name = "متجر"
        verbose_name_plural = "المتاجر"

    def __str__(self):
        return self.name


class StoreEmployee(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "مالك المتجر"
        MANAGER = "manager", "مدير"
        SALES = "sales", "موظف مبيعات"
        SUPPORT = "support", "موظف دعم"
        MODERATOR = "moderator", "مشرف منتجات"
        ACCOUNTANT = "accountant", "محاسب"
        CUSTOM = "custom", "صلاحيات مخصصة"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="employees", verbose_name="المتجر")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store_employments",
        verbose_name="المستخدم"
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.SALES, verbose_name="الوظيفة")
    permissions = models.JSONField(default=list, blank=True, verbose_name="الصلاحيات المخصصة")

    class Meta:
        unique_together = ("store", "user")
        verbose_name = "موظف متجر"
        verbose_name_plural = "موظفو المتاجر"

    def __str__(self):
        return f"{self.user.email} - {self.store.name} ({self.get_role_display()})"


class StorePage(TimeStampedModel):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="pages", verbose_name="المتجر")
    title = models.CharField(max_length=120, verbose_name="عنوان الصفحة")
    slug = models.SlugField(max_length=100, verbose_name="رابط الصفحة")
    content = models.TextField(verbose_name="محتوى الصفحة")
    is_active = models.BooleanField(default=True, verbose_name="نشطة")

    class Meta:
        unique_together = ("store", "slug")
        verbose_name = "صفحة متجر"
        verbose_name_plural = "صفحات المتاجر"

    def __str__(self):
        return f"{self.title} - {self.store.name}"


class StoreSetting(models.Model):
    store = models.OneToOneField(Store, on_delete=models.CASCADE, related_name="settings", verbose_name="المتجر")
    extra_json = models.JSONField(default=dict, blank=True, verbose_name="إعدادات إضافية")

    class Meta:
        verbose_name = "إعداد متجر"
        verbose_name_plural = "إعدادات المتاجر"

    def __str__(self):
        return f"إعدادات {self.store.name}"
