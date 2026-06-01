from django.contrib import admin

from apps.support.models import CannedReply, Ticket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "status", "priority", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("subject", "user__email")
    inlines = [TicketMessageInline]


@admin.register(CannedReply)
class CannedReplyAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "body")
