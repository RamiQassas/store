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
    
    # Preferences
    support_replies = models.BooleanField(default=True, verbose_name="ردود الدعم")
    order_updates = models.BooleanField(default=True, verbose_name="تحديثات الطلبات")
    financial_updates = models.BooleanField(default=True, verbose_name="العمليات المالية")
    system_announcements = models.BooleanField(default=True, verbose_name="إعلانات النظام")
    
    push_token = models.TextField(blank=True, help_text="Browser push registration token")

    class Meta:
        verbose_name = "إعدادات التنبيهات"
        verbose_name_plural = "إعدادات التنبيهات"


class PushSubscription(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="push_subscriptions", on_delete=models.CASCADE)
    endpoint = models.TextField()
    auth = models.CharField(max_length=255)
    p256dh = models.CharField(max_length=255)
    browser = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ("user", "endpoint")
        verbose_name = "اشتراك دفع"
        verbose_name_plural = "اشتراكات الدفع"
