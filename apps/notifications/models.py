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
