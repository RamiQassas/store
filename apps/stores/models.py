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
    max_categories = models.PositiveIntegerField(default=10, verbose_name="أقصى عدد تصنيفات")
    max_monthly_orders = models.PositiveIntegerField(default=100, verbose_name="أقصى عدد طلبات شهرياً")
    max_customers = models.PositiveIntegerField(default=100, verbose_name="أقصى عدد عملاء")
    max_employees = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد موظفين")
    max_branches = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد فروع")
    max_coupons = models.PositiveIntegerField(default=5, verbose_name="أقصى عدد كوبونات")
    max_images = models.PositiveIntegerField(default=100, verbose_name="أقصى عدد صور")
    max_storage_mb = models.PositiveIntegerField(default=100, verbose_name="مساحة التخزين القصوى (ميغابايت)")
    max_bandwidth_gb = models.PositiveIntegerField(default=100, verbose_name="أقصى استهلاك للباندويث (جيغابايت)")
    max_domains = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد دومينات مخصصة")
    max_api_keys = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد مفاتيح API")
    max_pages = models.PositiveIntegerField(default=5, verbose_name="أقصى عدد صفحات مخصصة")
    trial_days = models.PositiveIntegerField(default=14, verbose_name="فترة تجريبية (أيام)")
    
    # Features
    custom_domain_enabled = models.BooleanField(default=False, verbose_name="ربط دومين مخصص")
    remove_branding_enabled = models.BooleanField(default=False, verbose_name="إزالة شعار رقميات")
    multi_employee_enabled = models.BooleanField(default=False, verbose_name="دعم تعدد الموظفين")
    multi_branch_enabled = models.BooleanField(default=False, verbose_name="دعم تعدد الفروع")
    coupons_enabled = models.BooleanField(default=True, verbose_name="إنشاء أكواد خصم")
    recharge_cards_enabled = models.BooleanField(default=True, verbose_name="إنشاء بطاقات شحن")
    wallets_enabled = models.BooleanField(default=True, verbose_name="إنشاء محافظ إلكترونية")
    advanced_reports_enabled = models.BooleanField(default=False, verbose_name="تقارير متقدمة")
    live_stats_enabled = models.BooleanField(default=False, verbose_name="إحصائيات مباشرة")
    export_excel_enabled = models.BooleanField(default=False, verbose_name="تصدير Excel")
    export_pdf_enabled = models.BooleanField(default=False, verbose_name="تصدير PDF")
    api_access_enabled = models.BooleanField(default=False, verbose_name="REST API")
    webhooks_enabled = models.BooleanField(default=False, verbose_name="Webhooks")
    mobile_app_enabled = models.BooleanField(default=False, verbose_name="تطبيق جوال")
    sms_notifications_enabled = models.BooleanField(default=False, verbose_name="إشعارات SMS")
    whatsapp_notifications_enabled = models.BooleanField(default=False, verbose_name="إشعارات WhatsApp")
    email_marketing_enabled = models.BooleanField(default=False, verbose_name="البريد الإلكتروني التسويقي")
    import_products_enabled = models.BooleanField(default=False, verbose_name="استيراد المنتجات")
    export_products_enabled = models.BooleanField(default=False, verbose_name="تصدير المنتجات")
    backup_enabled = models.BooleanField(default=False, verbose_name="النسخ الاحتياطي")
    restore_enabled = models.BooleanField(default=False, verbose_name="استعادة النسخ الاحتياطية")
    professional_templates_enabled = models.BooleanField(default=False, verbose_name="القوالب الاحترافية")
    custom_css_js_enabled = models.BooleanField(default=False, verbose_name="تخصيص CSS و JavaScript")
    multi_language_enabled = models.BooleanField(default=False, verbose_name="دعم اللغات المتعددة")
    multi_currency_enabled = models.BooleanField(default=False, verbose_name="دعم العملات المتعددة")
    
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
    subdomain = models.SlugField(max_length=100, unique=True, verbose_name="رابط المتجر الفرعي (Subdomain)")
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
    limit_overrides = models.JSONField(default=dict, blank=True, verbose_name="تجاوز الحدود يدوياً")
    
    # Styling and Theme Colors (Extended)
    primary_color = models.CharField(max_length=7, default="#06b6d4", verbose_name="اللون الأساسي")
    secondary_color = models.CharField(max_length=7, default="#0891b2", verbose_name="اللون الثانوي")
    button_color = models.CharField(max_length=7, default="#06b6d4", verbose_name="لون الأزرار")
    background_color = models.CharField(max_length=7, default="#ffffff", verbose_name="لون الخلفية")
    text_color = models.CharField(max_length=7, default="#0f172a", verbose_name="لون النص")
    theme_font = models.CharField(max_length=50, default="Cairo", verbose_name="الخط")
    card_style = models.CharField(max_length=20, default="flat", verbose_name="شكل البطاقات")
    header_style = models.CharField(max_length=20, default="classic", verbose_name="شكل الهيدر")
    footer_style = models.CharField(max_length=20, default="classic", verbose_name="شكل الفوتر")
    
    # Managers
    objects = models.Manager()
    unfiltered = models.Manager()
    all_objects = models.Manager()
    
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

    @property
    def slug(self):
        return self.subdomain

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


class SaaSAdminRole(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم الدور")
    description = models.TextField(blank=True, verbose_name="الوصف")
    permissions = models.JSONField(default=list, blank=True, verbose_name="الصلاحيات")

    class Meta:
        verbose_name = "دور إداري SaaS"
        verbose_name_plural = "الأدوار الإدارية SaaS"

    def __str__(self):
        return self.name


class SaaSAuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المستخدم")
    action = models.CharField(max_length=255, verbose_name="العملية")
    description = models.TextField(verbose_name="التفاصيل")
    ip_address = models.CharField(max_length=45, blank=True, null=True, verbose_name="عنوان IP")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ العملية")

    class Meta:
        verbose_name = "سجل تدقيق SaaS"
        verbose_name_plural = "سجلات تدقيق SaaS"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.action} ({self.created_at})"


class StoreTemplate(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم القالب")
    image = models.ImageField(upload_to="stores/templates/", blank=True, null=True, verbose_name="صورة القالب")
    category = models.CharField(max_length=100, verbose_name="فئة القالب")
    mobile_responsive = models.BooleanField(default=True, verbose_name="متوافق مع الجوال")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    # Template design defaults
    primary_color = models.CharField(max_length=7, default="#06b6d4", verbose_name="اللون الأساسي")
    secondary_color = models.CharField(max_length=7, default="#0891b2", verbose_name="اللون الثانوي")
    button_color = models.CharField(max_length=7, default="#06b6d4", verbose_name="لون الأزرار")
    background_color = models.CharField(max_length=7, default="#ffffff", verbose_name="لون الخلفية")
    text_color = models.CharField(max_length=7, default="#0f172a", verbose_name="لون النص")
    theme_font = models.CharField(max_length=50, default="Cairo", verbose_name="الخط")
    card_style = models.CharField(max_length=20, default="flat", verbose_name="شكل البطاقات")
    header_style = models.CharField(max_length=20, default="classic", verbose_name="شكل الهيدر")
    footer_style = models.CharField(max_length=20, default="classic", verbose_name="شكل الفوتر")

    class Meta:
        verbose_name = "قالب متجر"
        verbose_name_plural = "قوالب المتاجر"

    def __str__(self):
        return self.name


class SaaSGlobalSetting(models.Model):
    platform_name = models.CharField(max_length=100, default="رقميات", verbose_name="اسم المنصة")
    logo = models.ImageField(upload_to="saas/logo/", blank=True, null=True, verbose_name="شعار المنصة")
    support_email = models.EmailField(default="support@raqamiyatapp.com", verbose_name="البريد الإلكتروني للدعم")
    allowed_languages = models.JSONField(default=list, blank=True, verbose_name="اللغات المدعومة")
    allowed_currencies = models.JSONField(default=list, blank=True, verbose_name="العملات المدعومة")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="نسبة عمولة المنصة (%)")
    backup_settings = models.JSONField(default=dict, blank=True, verbose_name="إعدادات النسخ الاحتياطي")

    class Meta:
        verbose_name = "إعداد عام SaaS"
        verbose_name_plural = "إعدادات عامة SaaS"

    def __str__(self):
        return self.platform_name


class SubscriptionInvoice(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription_invoices", verbose_name="المستخدم")
    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription_invoices", verbose_name="المتجر")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, verbose_name="باقة الاشتراك")
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الفاتورة")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ المدفوع")
    currency = models.ForeignKey("common.Currency", on_delete=models.PROTECT, verbose_name="العملة")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإصدار")
    status = models.CharField(
        max_length=20,
        choices=[("paid", "مدفوعة"), ("unpaid", "غير مدفوعة"), ("refunded", "مستردة")],
        default="paid",
        verbose_name="حالة الفاتورة"
    )

    class Meta:
        verbose_name = "فاتورة اشتراك"
        verbose_name_plural = "فواتير الاشتراكات"
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.invoice_number} - {self.store.name if self.store else self.user.email}"
