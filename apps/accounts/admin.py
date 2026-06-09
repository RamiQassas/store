from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import SecurityEvent, User, UserSession


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("email", "phone", "role", "tier", "email_verified", "is_active", "is_staff")
    list_filter = ("role", "tier", "email_verified", "is_active", "is_staff")
    search_fields = ("email", "phone", "first_name", "last_name")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (
        ("Platform", {"fields": ("phone", "role", "tier", "email_verified", "two_factor_enabled")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "tier", "is_staff", "is_superuser"),
        }),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "is_active", "last_seen_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "ip_address", "refresh_jti")


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "ip_address", "created_at")
    list_filter = ("event_type",)
    search_fields = ("user__email", "ip_address")
    readonly_fields = ("created_at", "updated_at")
