from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid

from apps.common.models import TimeStampedModel


from apps.common.tenant_utils import TenantManager


class ChatRoom(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "waiting", "في الانتظار"
        ASSIGNED = "assigned", "تم التعيين"
        IN_PROGRESS = "in_progress", "قيد المعالجة"
        CLOSED = "closed", "مغلق"
        REOPENED = "reopened", "تم إعادة الفتح"

    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        related_name="chat_rooms",
        null=True,
        blank=True,
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name="chat_rooms", 
        on_delete=models.CASCADE, 
        verbose_name="المستخدم"
    )
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="assigned_chats",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="الموظف المسؤول"
    )
    subject = models.CharField(max_length=180, blank=True, verbose_name="الموضوع")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING, verbose_name="الحالة")
    
    last_message_at = models.DateTimeField(default=timezone.now, verbose_name="آخر رسالة")
    unread_user_count = models.PositiveIntegerField(default=0, verbose_name="غير مقروء (للمستخدم)")
    unread_staff_count = models.PositiveIntegerField(default=0, verbose_name="غير مقروء (للموظف)")
    
    staff_notes = models.TextField(blank=True, verbose_name="ملاحظات داخلية للموظفين")

    class Meta:
        ordering = ["-last_message_at"]
        verbose_name = "غرفة محادثة"
        verbose_name_plural = "غرف المحادثة"

    def __str__(self):
        return f"Chat with {self.user.email} ({self.get_status_display()})"

    @property
    def is_guest_room(self):
        return " - زائر: " in self.subject or self.user.email == "guest@raqamiyat.com"

    @property
    def guest_name(self):
        if " - زائر: " in self.subject:
            return self.subject.split(" - زائر: ")[-1]
        return None

    @property
    def display_name(self):
        if self.is_guest_room and self.guest_name:
            return self.guest_name
        return self.user.get_full_name() or self.user.email


class ChatMessage(TimeStampedModel):
    room = models.ForeignKey(ChatRoom, related_name="messages", on_delete=models.CASCADE, verbose_name="الغرفة")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="chat_messages", on_delete=models.CASCADE, verbose_name="المرسل")
    text = models.TextField(blank=True, verbose_name="النص")
    
    # File support
    file = models.FileField(upload_to="chats/files/%Y/%m/", blank=True, null=True, verbose_name="ملف")
    is_image = models.BooleanField(default=False)
    
    is_staff_reply = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ القراءة")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "رسالة محادثة"
        verbose_name_plural = "رسائل المحادثة"

    def __str__(self):
        return f"Msg from {self.sender} in {self.room.id}"


class ChatCannedReply(TimeStampedModel):
    title = models.CharField(max_length=120, verbose_name="العنوان")
    body = models.TextField(verbose_name="نص الرد")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "رد جاهز (محادثة)"
        verbose_name_plural = "الردود الجاهزة (محادثة)"

    def __str__(self):
        return self.title


class SupportSettings(models.Model):
    welcome_message = models.TextField(
        default="مرحباً بك! كيف يمكننا مساعدتك اليوم؟", 
        verbose_name="رسالة الترحيب التلقائية",
        help_text="هذه الرسالة تظهر تلقائياً عند فتح محادثة جديدة"
    )

    class Meta:
        verbose_name = "إعدادات الدعم"
        verbose_name_plural = "إعدادات الدعم"

    def __str__(self):
        return "إعدادات الدعم الفني"
