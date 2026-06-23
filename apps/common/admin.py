from django.contrib import admin
from apps.common.models import Currency, SystemAuditLog, SocialMediaLink, SiteAnnouncement, PlatformStatistic, Testimonial

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "symbol", "buy_rate", "sell_rate", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

@admin.register(SystemAuditLog)
class SystemAuditLogAdmin(admin.ModelAdmin):
    list_display = ("actor", "action_type", "ip_address", "created_at")
    list_filter = ("action_type", "created_at")
    search_fields = ("actor__email", "action_type", "description")

@admin.register(SocialMediaLink)
class SocialMediaLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "is_active", "display_order")
    list_filter = ("is_active",)

@admin.register(SiteAnnouncement)
class SiteAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("text", "store", "is_active", "created_at")
    list_filter = ("is_active", "store")
    search_fields = ("text",)

@admin.register(PlatformStatistic)
class PlatformStatisticAdmin(admin.ModelAdmin):
    list_display = ("label", "stat_type", "value_override", "is_active", "display_order")
    list_filter = ("stat_type", "is_active")

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("user", "rating", "is_approved", "display_name_publicly")
    list_filter = ("rating", "is_approved")
