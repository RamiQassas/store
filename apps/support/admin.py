from django.contrib import admin
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply, Ticket, TicketMessage, SupportSettings


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("sender", "is_staff_reply", "read_at")


@admin.register(SupportSettings)
class SupportSettingsAdmin(admin.ModelAdmin):
    list_display = ("welcome_message",)
    
    def has_add_permission(self, request):
        return not SupportSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "assigned_agent", "status", "last_message_at", "unread_staff_count")
    list_filter = ("status", "assigned_agent")
    search_fields = ("user__email", "subject")
    inlines = [ChatMessageInline]


@admin.register(ChatCannedReply)
class ChatCannedReplyAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "body")


# Legacy
class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "user", "status", "priority", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("subject", "user__email")
    inlines = [TicketMessageInline]
