from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Ticket(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        PENDING = "pending", "قيد المراجعة"
        RESOLVED = "resolved", "تم الحل"
        CLOSED = "closed", "مغلقة"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tickets", on_delete=models.CASCADE)
    subject = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, default="normal")

    def __str__(self):
        return self.subject


class TicketMessage(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ticket_messages", on_delete=models.CASCADE)
    message = models.TextField()
    is_staff_reply = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.ticket.subject} - {self.sender}"


class CannedReply(TimeStampedModel):
    title = models.CharField(max_length=120)
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title
