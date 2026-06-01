from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class Ticket(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "مفتوح"
        ANSWERED = "answered", "تم الرد"
        WAITING_USER = "waiting_user", "في انتظار العميل"
        CLOSED = "closed", "مغلق"

    class Priority(models.TextChoices):
        LOW = "low", "منخفضة"
        NORMAL = "normal", "عادية"
        HIGH = "high", "عالية"
        URGENT = "urgent", "عاجلة"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tickets", on_delete=models.CASCADE, verbose_name="المستخدم")
    subject = models.CharField(max_length=180, verbose_name="العنوان")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name="الحالة")
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL, verbose_name="الأولوية")
    
    last_reply_at = models.DateTimeField(default=timezone.now, verbose_name="آخر رد")
    is_read_by_user = models.BooleanField(default=True, verbose_name="قرأها المستخدم")
    is_read_by_staff = models.BooleanField(default=False, verbose_name="قرأها الموظف")

    class Meta:
        ordering = ["-last_reply_at"]
        verbose_name = "تذكرة دعم"
        verbose_name_plural = "تذاكر الدعم"

    def __str__(self):
        return f"#{self.id} - {self.subject}"


class TicketMessage(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="messages", on_delete=models.CASCADE, verbose_name="التذكرة")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ticket_messages", on_delete=models.CASCADE, verbose_name="المرسل")
    message = models.TextField(verbose_name="الرسالة")
    attachment = models.FileField(upload_to="tickets/attachments/", blank=True, null=True, verbose_name="مرفق")
    is_staff_reply = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "رسالة تذكرة"
        verbose_name_plural = "رسائل التذاكر"

    def __str__(self):
        return f"Msg from {self.sender} on {self.ticket.id}"


class CannedReply(TimeStampedModel):
    title = models.CharField(max_length=120, verbose_name="العنوان")
    body = models.TextField(verbose_name="نص الرد")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "رد جاهز"
        verbose_name_plural = "الردود الجاهزة"

    def __str__(self):
        return self.title
