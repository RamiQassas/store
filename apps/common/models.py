import uuid
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class Currency(TimeStampedModel):
    class ConversionMethod(models.TextChoices):
        MULTIPLY = "multiply", _("ضرب (×)")
        DIVIDE = "divide", _("قسمة (÷)")

    name = models.CharField(max_length=50, verbose_name=_("اسم العملة"))
    code = models.CharField(max_length=3, unique=True, verbose_name=_("رمز العملة (ISO)"))
    symbol = models.CharField(max_length=10, verbose_name=_("رمز العملة"))
    buy_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, verbose_name=_("سعر الشراء (للإيداع)"), help_text=_("كم تساوي 1 وحدة من العملة الأساسية (مثال: 1 دولار = 10500 ليرة)"))
    sell_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1.0, verbose_name=_("سعر المبيع (للسحب)"), help_text=_("كم تساوي 1 وحدة من العملة الأساسية (مثال: 1 دولار = 10000 ليرة)"))
    conversion_method = models.CharField(
        max_length=10, 
        choices=ConversionMethod.choices, 
        default=ConversionMethod.MULTIPLY,
        verbose_name=_("طريقة التحويل")
    )
    decimal_places = models.PositiveIntegerField(default=2, verbose_name=_("عدد الخانات العشرية"))
    display_order = models.PositiveIntegerField(default=0, verbose_name=_("ترتيب العرض"))
    is_active = models.BooleanField(default=True, verbose_name=_("نشط"))
    is_default = models.BooleanField(default=False, verbose_name=_("العملة الافتراضية"))

    class Meta:
        ordering = ["display_order", "code"]
        verbose_name = _("عملة")
        verbose_name_plural = _("العملات")

    def __str__(self):
        return f"{self.code} ({self.symbol})"

    def to_base(self, amount, operation="deposit"):
        """Convert an amount in this currency to the base currency (e.g., USD)."""
        rate = self.buy_rate if operation == "deposit" else self.sell_rate
        if rate <= 0: return Decimal("0.00")
        
        if self.conversion_method == self.ConversionMethod.DIVIDE:
            return Decimal(str(amount)) * Decimal(str(rate))
        return Decimal(str(amount)) / Decimal(str(rate))

    def from_base(self, base_amount, operation="deposit"):
        """Convert a base currency amount to this currency."""
        rate = self.buy_rate if operation == "deposit" else self.sell_rate
        
        if self.conversion_method == self.ConversionMethod.DIVIDE:
            if rate <= 0: return Decimal("0.00")
            return Decimal(str(base_amount)) / Decimal(str(rate))
        return Decimal(str(base_amount)) * Decimal(str(rate))

    def save(self, *args, **kwargs):
        if self.is_default:
            Currency.objects.filter(is_default=True).update(is_default=False)
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
        verbose_name=_("المنفذ")
    )
    action_type = models.CharField(max_length=100, verbose_name=_("نوع الإجراء"))
    
    # Generic relation to target object
    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    
    description = models.TextField(blank=True, verbose_name=_("الوصف"))
    
    # State tracking
    before_state = models.JSONField(default=dict, blank=True, verbose_name=_("الحالة قبل"))
    after_state = models.JSONField(default=dict, blank=True, verbose_name=_("الحالة بعد"))
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name=_("IP عنوان"))
    user_agent = models.TextField(blank=True, verbose_name=_("متصفح المستخدم"))
    reason = models.TextField(blank=True, verbose_name=_("السبب"))
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("سجل تدقيق النظام")
        verbose_name_plural = _("سجلات تدقيق النظام")
        indexes = [
            models.Index(fields=["action_type"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.actor} - {self.action_type} - {self.created_at}"

class SocialMediaLink(TimeStampedModel):
    name = models.CharField(max_length=50, verbose_name=_("اسم المنصة"))
    url = models.URLField(verbose_name=_("رابط الحساب"))
    icon_image = models.ImageField(upload_to="social_icons/", blank=True, null=True, verbose_name=_("أيقونة/شعار"))
    icon_class = models.CharField(max_length=50, blank=True, help_text=_("FontAwesome class (e.g. fab fa-facebook)"), verbose_name=_("كود الأيقونة"))
    is_active = models.BooleanField(default=True, verbose_name=_("نشط"))
    display_order = models.PositiveIntegerField(default=0, verbose_name=_("ترتيب العرض"))

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = _("رابط تواصل اجتماعي")
        verbose_name_plural = _("روابط التواصل الاجتماعي")

    def __str__(self):
        return self.name
