import uuid
from decimal import Decimal

from django.db import models
from django.conf import settings
from apps.common.tenant_utils import TenantManager


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class Currency(TimeStampedModel):
    class ConversionMethod(models.TextChoices):
        MULTIPLY = "multiply", "ضرب (×)"
        DIVIDE = "divide", "قسمة (÷)"

    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="currencies",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()

    name = models.CharField(max_length=50, verbose_name="اسم العملة")
    code = models.CharField(max_length=3, verbose_name="رمز العملة (ISO)")
    symbol = models.CharField(max_length=10, verbose_name="رمز العملة")
    buy_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, verbose_name="سعر الشراء (للإيداع)", help_text="كم تساوي 1 وحدة من العملة الأساسية (مثال: 1 دولار = 10500 ليرة)")
    sell_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, verbose_name="سعر المبيع (للسحب)", help_text="كم تساوي 1 وحدة من العملة الأساسية (مثال: 1 دولار = 10000 ليرة)")
    capital_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, verbose_name="سعر صرف التكلفة", help_text="سعر التكلفة الحقيقي (الداخلي) مقابل الدولار لحساب الأرباح بدقة.")
    conversion_method = models.CharField(
        max_length=10, 
        choices=ConversionMethod.choices, 
        default=ConversionMethod.MULTIPLY,
        verbose_name="طريقة التحويل"
    )
    decimal_places = models.PositiveIntegerField(default=2, verbose_name="عدد الخانات العشرية")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_default = models.BooleanField(default=False, verbose_name="العملة الافتراضية")

    class Meta:
        ordering = ["display_order", "code"]
        verbose_name = "عملة"
        verbose_name_plural = "العملات"
        unique_together = ("code", "store")

    def __str__(self):
        return f"{self.code} ({self.symbol})"

    def to_base(self, amount, operation="deposit"):
        """Convert an amount in this currency to the base currency (e.g., USD)."""
        if amount is None: return Decimal("0.00")
        rate = self.buy_rate if operation == "deposit" else self.sell_rate
        if rate is None or rate <= 0: 
            return Decimal(str(amount)) # Fallback: assume 1:1 if rate is invalid
        
        if self.conversion_method == self.ConversionMethod.DIVIDE:
            return Decimal(str(amount)) * Decimal(str(rate))
        return Decimal(str(amount)) / Decimal(str(rate))

    def from_base(self, base_amount, operation="deposit"):
        """Convert a base currency amount to this currency."""
        if base_amount is None: return Decimal("0.00")
        rate = self.buy_rate if operation == "deposit" else self.sell_rate
        
        if rate is None or rate <= 0:
            return Decimal(str(base_amount)) # Fallback: assume 1:1 if rate is invalid

        if self.conversion_method == self.ConversionMethod.DIVIDE:
            return Decimal(str(base_amount)) / Decimal(str(rate))
        return Decimal(str(base_amount)) * Decimal(str(rate))

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        if self.buy_rate is not None and self.sell_rate is not None:
            if self.conversion_method == self.ConversionMethod.MULTIPLY:
                if self.sell_rate > self.buy_rate:
                    raise ValidationError({
                        "sell_rate": "سعر المبيع (للسحب) يجب ألا يتجاوز سعر الشراء (للإيداع) لتجنب ثغرات المراجحة المالية (Arbitrage)."
                    })
            elif self.conversion_method == self.ConversionMethod.DIVIDE:
                if self.buy_rate > self.sell_rate:
                    raise ValidationError({
                        "buy_rate": "سعر الشراء (للإيداع) يجب ألا يتجاوز سعر المبيع (للسحب) لطريقة التحويل بالقسمة."
                    })

    def save(self, *args, **kwargs):
        self.clean()
        if self.is_default:
            Currency.all_objects.filter(store=self.store, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)



class SystemAuditLog(TimeStampedModel):
    """
    Universal audit log for tracking administrative and sensitive actions.
    Records 'who', 'what', 'when', 'where', and 'why'.
    """
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="performed_audit_logs",
        verbose_name="المنفذ"
    )
    action_type = models.CharField(max_length=100, verbose_name="نوع الإجراء")
    
    # Generic relation to target object
    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    
    description = models.TextField(blank=True, verbose_name="الوصف")
    
    # State tracking
    before_state = models.JSONField(default=dict, blank=True, verbose_name="الحالة قبل")
    after_state = models.JSONField(default=dict, blank=True, verbose_name="الحالة بعد")
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP عنوان")
    user_agent = models.TextField(blank=True, verbose_name="متصفح المستخدم")
    reason = models.TextField(blank=True, verbose_name="السبب")
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تدقيق النظام"
        verbose_name_plural = "سجلات تدقيق النظام"
        indexes = [
            models.Index(fields=["action_type"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.actor} - {self.action_type} - {self.created_at}"

class SocialMediaLink(TimeStampedModel):
    name = models.CharField(max_length=50, verbose_name="اسم المنصة")
    url = models.URLField(verbose_name="رابط الحساب")
    icon_image = models.ImageField(upload_to="social_icons/", blank=True, null=True, verbose_name="أيقونة/شعار")
    icon_class = models.CharField(max_length=50, blank=True, help_text="FontAwesome class (e.g. fab fa-facebook)", verbose_name="كود الأيقونة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "رابط تواصل اجتماعي"
        verbose_name_plural = "روابط التواصل الاجتماعي"

    def __str__(self):
        return self.name

class SiteAnnouncement(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
        verbose_name="المتجر"
    )
    text = models.TextField(verbose_name="نص الملاحظة")
    link = models.URLField(blank=True, null=True, verbose_name="رابط (اختياري)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    background_color = models.CharField(max_length=20, default="#06b6d4", verbose_name="لون الخلفية")
    text_color = models.CharField(max_length=20, default="#ffffff", verbose_name="لون النص")

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "ملاحظة شريط الموقع"
        verbose_name_plural = "ملاحظات شريط الموقع"

    def __str__(self):
        return self.text[:50]

class PlatformStatistic(TimeStampedModel):
    class StatType(models.TextChoices):
        CUSTOM = "custom", "مخصص"
        USERS = "users", "المستخدمين"
        ORDERS = "orders", "الطلبات"
        DEPOSITS = "deposits", "الإيداعات"
        WITHDRAWALS = "withdrawals", "السحوبات"
        PRODUCTS = "products", "المنتجات"
        EXECUTION_TIME = "execution_time", "وقت التنفيذ"

    label = models.CharField(max_length=100, verbose_name="تسمية الإحصائية")
    value_override = models.IntegerField(default=0, help_text="القيمة الرقمية (يتم إضافتها للرقم الحقيقي)")
    value_suffix = models.CharField(max_length=20, blank=True, default="+", help_text="مثال: + أو %")
    string_value = models.CharField(max_length=50, blank=True, help_text="قيمة نصية مخصصة (تتجاوز الرقم، مثال: 24/7)")
    icon_class = models.CharField(max_length=50, blank=True, help_text="FontAwesome class (e.g. fas fa-users)")
    stat_type = models.CharField(max_length=20, choices=StatType.choices, default=StatType.CUSTOM, verbose_name="نوع الإحصائية")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "إحصائية المنصة"
        verbose_name_plural = "إحصائيات المنصة"
        ordering = ["display_order"]

    def __str__(self):
        return self.label

class Testimonial(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="testimonials", verbose_name="المستخدم")
    text = models.TextField(verbose_name="التعليق/الشهادة")
    rating = models.PositiveSmallIntegerField(default=5, verbose_name="التقييم (1-5)")
    admin_reply = models.TextField(blank=True, null=True, verbose_name="رد الإدارة")
    is_approved = models.BooleanField(default=False, verbose_name="تمت الموافقة")
    display_name_publicly = models.BooleanField(default=True, verbose_name="عرض الاسم للعامة")

    class Meta:
        verbose_name = "شهادة عميل"
        verbose_name_plural = "شهادات العملاء"

    def __str__(self):
        return f"{self.user.email} - {self.rating} stars"


class SiteMaintenanceMode(models.Model):
    """
    Singleton model to control site-wide operational switches.
    Admins can disable deposits, withdrawals, purchases, and transfers individually.
    """
    # Operational switches
    deposits_enabled = models.BooleanField(default=True, verbose_name="الإيداعات مفعّلة")
    withdrawals_enabled = models.BooleanField(default=True, verbose_name="السحوبات مفعّلة")
    purchases_enabled = models.BooleanField(default=True, verbose_name="الشراء مفعّل")
    transfers_enabled = models.BooleanField(default=True, verbose_name="التحويلات مفعّلة")
    registrations_enabled = models.BooleanField(default=True, verbose_name="التسجيل مفعّل")

    # Maintenance message shown to users
    maintenance_message = models.TextField(
        blank=True,
        default="الموقع في وضع الصيانة مؤقتاً. سيعود للعمل قريباً.",
        verbose_name="رسالة الصيانة"
    )

    # Timestamps
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_mode_changes",
        verbose_name="آخر تعديل بواسطة"
    )

    class Meta:
        verbose_name = "وضع الصيانة"
        verbose_name_plural = "وضع الصيانة"

    def __str__(self):
        return "إعدادات الصيانة والتشغيل"

    @classmethod
    def get_settings(cls):
        """Always returns the singleton instance, creating it if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_fully_operational(self):
        return all([
            self.deposits_enabled,
            self.withdrawals_enabled,
            self.purchases_enabled,
            self.transfers_enabled,
            self.registrations_enabled,
        ])

    @property
    def is_any_disabled(self):
        return not self.is_fully_operational


class MetaPixelConfiguration(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="meta_pixel_configurations",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()

    pixel_name = models.CharField(
        max_length=120,
        blank=True,
        default="بيكسل إعلانات ميتا",
        verbose_name="تسمية البيكسل الخاص بك"
    )
    pixel_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="معرّف البيكسل (Pixel ID)",
        help_text="معرف بيكسل ميتا المكون من 15-16 رقماً من مدير أحداث فيسبوك/ميتا"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="تفعيل البيكسل"
    )
    
    # Event tracking switches
    track_pageviews = models.BooleanField(
        default=True,
        verbose_name="تتبع مشاهدة الصفحات (PageView)"
    )
    track_view_content = models.BooleanField(
        default=True,
        verbose_name="تتبع تصفح المنتجات (ViewContent)"
    )
    track_initiate_checkout = models.BooleanField(
        default=True,
        verbose_name="تتبع بدء الشراء وإضافة السلة (AddToCart / InitiateCheckout)"
    )
    track_purchases = models.BooleanField(
        default=True,
        verbose_name="تتبع عمليات الشراء المكتملة (Purchase)"
    )
    track_registrations = models.BooleanField(
        default=True,
        verbose_name="تتبع تسجيل الحسابات الجديدة (CompleteRegistration)"
    )

    # Conversions API & testing (optional)
    conversions_api_token = models.TextField(
        blank=True,
        verbose_name="رمز وصول واجهة تحويلات ميتا (Conversions API Token)"
    )
    test_event_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="رمز اختبار الأحداث (Test Event Code)"
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meta_pixel_updates",
        verbose_name="آخر تعديل بواسطة"
    )

    class Meta:
        verbose_name = "إعدادات بيكسل ميتا (Meta Pixel)"
        verbose_name_plural = "إعدادات بيكسل ميتا (Meta Pixel)"

    def __str__(self):
        return f"{self.pixel_name} ({self.pixel_id or 'غير معين'})"

    @classmethod
    def get_settings(cls, store=None):
        """Returns the MetaPixelConfiguration instance for the given store or platform."""
        try:
            if store:
                obj = cls.all_objects.filter(store=store).first()
                if not obj:
                    obj = cls.all_objects.create(store=store, pixel_name=f"بيكسل {store.name}")
                return obj
            obj = cls.all_objects.filter(store__isnull=True).first()
            if not obj:
                obj = cls.all_objects.create(store=None, pixel_name="بيكسل منصة رقميات")
            return obj
        except Exception:
            return None

