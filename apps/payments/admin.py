from django.contrib import admin
from apps.payments.models import DepositRequest, PaymentGatewayIntegration, PaymentMethod, WithdrawalRequest


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "method_type", "is_active", "is_maintenance_mode", "can_deposit", "can_withdraw", "display_order")
    list_filter = ("method_type", "is_active", "is_maintenance_mode", "can_deposit", "can_withdraw")
    search_fields = ("name", "provider_name")
    ordering = ("display_order", "name")


from django.utils.html import format_html


@admin.register(PaymentGatewayIntegration)
class PaymentGatewayIntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "logo_preview", "provider", "mode", "terminal_id", "store", "is_active", "can_deposit", "can_withdraw", "last_health_status")
    list_filter = ("provider", "mode", "is_active", "can_deposit", "can_withdraw")
    search_fields = ("name", "terminal_id", "base_url")

    def logo_preview(self, obj):
        url = obj.logo_url
        if url:
            return format_html('<img src="{}" style="height: 24px; width: 24px; object-fit: contain; border-radius: 4px;" />', url)
        return "-"
    logo_preview.short_description = "الشعار"


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "payment_method", "amount", "final_amount", "currency", "status", "created_at")
    list_filter = ("status", "payment_method", "currency")
    search_fields = ("user__email", "transaction_id", "customer_note")
    readonly_fields = ("fee_amount", "final_amount", "reviewed_at", "reviewed_by")
    date_hierarchy = "created_at"


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "payment_method", "amount", "final_amount", "currency", "status", "created_at")
    list_filter = ("status", "payment_method", "currency")
    search_fields = ("user__email", "admin_note")
    readonly_fields = ("fee_amount", "final_amount", "reviewed_at", "reviewed_by")
    date_hierarchy = "created_at"
