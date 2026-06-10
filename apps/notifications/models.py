from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", _("In-App")
        EMAIL = "email", _("Email")
        PUSH = "push", _("Push")

    class Priority(models.TextChoices):
        LOW = "low", _("Low")
        NORMAL = "normal", _("Normal")
        HIGH = "high", _("High")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE, verbose_name=_("المستخدم"))
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP, verbose_name=_("القناة"))
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL, verbose_name=_("الأهمية"))
    
    title = models.CharField(max_length=160, verbose_name=_("العنوان"))
    body = models.TextField(blank=True, verbose_name=_("النص"))
    action_url = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("رابط الإجراء"))
    image_url = models.URLField(blank=True, null=True, verbose_name=_("رابط الصورة"))
    
    is_read = models.BooleanField(default=False, verbose_name=_("مقروء"))
    read_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]
        ordering = ["-created_at"]
        verbose_name = _("إشعار")
        verbose_name_plural = _("الإشعارات")

    def __str__(self):
        return f"{self.user.email} - {self.title}"


class NotificationSetting(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="notification_settings", on_delete=models.CASCADE)
    
    # In-App Preferences
    in_app_orders = models.BooleanField(default=True, verbose_name=_("تحديثات الطلبات (داخل التطبيق)"))
    in_app_financial = models.BooleanField(default=True, verbose_name=_("العمليات المالية (داخل التطبيق)"))
    in_app_support = models.BooleanField(default=True, verbose_name=_("ردود الدعم (داخل التطبيق)"))
    in_app_promotions = models.BooleanField(default=True, verbose_name=_("العروض والترويج (داخل التطبيق)"))
    
    # Push Preferences
    push_orders = models.BooleanField(default=True, verbose_name=_("تحديثات الطلبات (Push)"))
    push_financial = models.BooleanField(default=True, verbose_name=_("العمليات المالية (Push)"))
    push_support = models.BooleanField(default=True, verbose_name=_("ردود الدعم (Push)"))
    push_promotions = models.BooleanField(default=False, verbose_name=_("العروض والترويج (Push)"))

    class Meta:
        verbose_name = _("إعدادات التنبيهات")
        verbose_name_plural = _("إعدادات التنبيهات")


class PushSubscription(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="push_subscriptions", on_delete=models.CASCADE)
    endpoint = models.TextField()
    auth = models.TextField()
    p256dh = models.TextField()
    browser = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "endpoint")
        verbose_name = _("اشتراك دفع")
        verbose_name_plural = _("اشتراكات الدفع")
