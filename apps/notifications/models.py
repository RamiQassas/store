from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-App"
        EMAIL = "email", "Email"
        PUSH = "push", "Push"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE, verbose_name="المستخدم")
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP, verbose_name="القناة")
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL, verbose_name="الأهمية")
    
    title = models.CharField(max_length=160, verbose_name="العنوان")
    body = models.TextField(blank=True, verbose_name="النص")
    action_url = models.CharField(max_length=255, blank=True, null=True, verbose_name="رابط الإجراء")
    image_url = models.URLField(blank=True, null=True, verbose_name="رابط الصورة")
    
    is_read = models.BooleanField(default=False, verbose_name="مقروء")
    read_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]
        ordering = ["-created_at"]
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"

    def __str__(self):
        return f"{self.user.email} - {self.title}"


class NotificationSetting(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="notification_settings", on_delete=models.CASCADE)
    
    # Global Toggle
    is_enabled = models.BooleanField(default=True, verbose_name="تفعيل الإشعارات بشكل عام")

    # --- User Preferences ---
    # In-App Preferences
    in_app_orders = models.BooleanField(default=True, verbose_name="تحديثات الطلبات (داخل التطبيق)")
    in_app_financial = models.BooleanField(default=True, verbose_name="العمليات المالية (داخل التطبيق)")
    in_app_support = models.BooleanField(default=True, verbose_name="ردود الدعم (داخل التطبيق)")
    in_app_kyc = models.BooleanField(default=True, verbose_name="تحديثات التوثيق (داخل التطبيق)")
    in_app_promotions = models.BooleanField(default=True, verbose_name="العروض والترويج (داخل التطبيق)")
    
    # Push Preferences
    push_orders = models.BooleanField(default=True, verbose_name="تحديثات الطلبات (Push)")
    push_financial = models.BooleanField(default=True, verbose_name="العمليات المالية (Push)")
    push_support = models.BooleanField(default=True, verbose_name="ردود الدعم (Push)")
    push_kyc = models.BooleanField(default=True, verbose_name="تحديثات التوثيق (Push)")
    push_promotions = models.BooleanField(default=False, verbose_name="العروض والترويج (Push)")
    
    # Email Preferences
    email_orders = models.BooleanField(default=True, verbose_name="تحديثات الطلبات (البريد)")
    email_financial = models.BooleanField(default=True, verbose_name="العمليات المالية (البريد)")
    email_support = models.BooleanField(default=True, verbose_name="ردود الدعم (البريد)")
    email_kyc = models.BooleanField(default=True, verbose_name="تحديثات التوثيق (البريد)")
    email_promotions = models.BooleanField(default=True, verbose_name="العروض والترويج (البريد)")

    # --- Admin/Staff Preferences ---
    # Only relevant for users with staff/admin roles
    admin_new_deposit = models.BooleanField(default=True, verbose_name="طلبات إيداع جديدة")
    admin_new_withdrawal = models.BooleanField(default=True, verbose_name="طلبات سحب جديدة")
    admin_new_order = models.BooleanField(default=True, verbose_name="طلبات شراء جديدة")
    admin_new_support = models.BooleanField(default=True, verbose_name="تذاكر دعم جديدة")
    admin_new_kyc = models.BooleanField(default=True, verbose_name="طلبات توثيق جديدة")
    admin_provider_alert = models.BooleanField(default=True, verbose_name="تنبيهات مشاكل مزودي الخدمة")
    
    admin_email_notifications = models.BooleanField(default=True, verbose_name="استلام إشعارات الإدارة عبر البريد")

    class Meta:
        verbose_name = "إعدادات التنبيهات"
        verbose_name_plural = "إعدادات التنبيهات"


class PushSubscription(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="push_subscriptions", on_delete=models.CASCADE)
    endpoint = models.TextField()
    auth = models.TextField()
    p256dh = models.TextField()
    browser = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "endpoint")
        verbose_name = "اشتراك دفع"
        verbose_name_plural = "اشتراكات الدفع"


class AppBroadcastNotification(TimeStampedModel):
    class Category(models.TextChoices):
        UPDATE = "update", "تحديث التطبيق / النظام"
        PROMO = "promo", "عرض ترويجي"
        DISCOUNT = "discount", "تخفيضات وخصومات"
        CUSTOM = "custom", "رسالة مخصصة"

    category = models.CharField(max_length=20, choices=Category.choices, default=Category.PROMO, verbose_name="نوع الإشعار")
    title = models.CharField(max_length=160, verbose_name="عنوان الإشعار")
    body = models.TextField(verbose_name="نص الإشعار")
    action_url = models.CharField(max_length=255, blank=True, null=True, verbose_name="رابط الإجراء")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_app_broadcasts",
        verbose_name="المرسل"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "بث إشعار للتطبيق"
        verbose_name_plural = "بث إشعارات التطبيق"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"
