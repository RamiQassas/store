from django.contrib import admin
from apps.stores.models import (
    SubscriptionPlan, Store, StoreEmployee, StorePage, StoreSetting,
    SaaSAdminRole, SaaSAuditLog, StoreTemplate, SaaSGlobalSetting, SubscriptionInvoice
)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_monthly", "price_yearly", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "custom_domain", "owner", "subscription_status", "is_featured", "display_order", "is_active", "created_at")
    list_editable = ("is_featured", "display_order", "is_active")
    list_filter = ("subscription_status", "is_featured", "is_active", "subscription_plan")
    search_fields = ("name", "subdomain", "custom_domain", "owner__email")

@admin.register(StoreEmployee)
class StoreEmployeeAdmin(admin.ModelAdmin):
    list_display = ("store", "user", "role")
    list_filter = ("role", "store")
    search_fields = ("user__email", "store__name")

@admin.register(StorePage)
class StorePageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "store", "is_active", "created_at")
    list_filter = ("is_active", "store")
    search_fields = ("title", "slug", "content")

@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ("store",)
    search_fields = ("store__name",)

@admin.register(SaaSAdminRole)
class SaaSAdminRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)

@admin.register(SaaSAuditLog)
class SaaSAuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__email", "action", "description")

@admin.register(StoreTemplate)
class StoreTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "category")

@admin.register(SaaSGlobalSetting)
class SaaSGlobalSettingAdmin(admin.ModelAdmin):
    list_display = ("platform_name", "support_email", "commission_rate")
    search_fields = ("platform_name", "support_email")

@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = ("store", "amount", "status", "invoice_number", "issued_at")
    list_filter = ("status", "store", "issued_at")
    search_fields = ("store__name", "invoice_number")
