from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html
from .models import (
    ProviderProfile, ProviderCategory, ProviderProduct, ProviderPrice,
    ProviderProductParameter, ProviderPriceHistory, ProviderOrder,
    ProviderOrderStatus, ProviderSyncLog, ProviderRequestLog,
    ProviderResponseLog, ProviderErrorLog, ProviderMapping
)

@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ('provider_name', 'store', 'is_active', 'balance', 'currency', 'last_sync_at', 'sync_button')
    list_filter = ('is_active', 'store')
    search_fields = ('provider_name', 'store__name')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:profile_id>/sync/', self.admin_site.admin_view(self.sync_provider), name='provider_sync'),
            path('<int:profile_id>/balance/', self.admin_site.admin_view(self.fetch_balance), name='provider_balance'),
        ]
        return custom_urls + urls

    def sync_button(self, obj):
        return format_html(
            '<a class="button" href="{}">مزامنة المنتجات</a> &nbsp; '
            '<a class="button" href="{}">تحديث الرصيد</a>',
            f"{obj.id}/sync/",
            f"{obj.id}/balance/"
        )
    sync_button.short_description = "إجراءات"
    sync_button.allow_tags = True

    def sync_provider(self, request, profile_id):
        profile = self.get_object(request, profile_id)
        if profile:
            from services.provider.manager import ProviderManager
            try:
                stats = ProviderManager.sync_catalog(profile)
                messages.success(request, f"تمت المزامنة بنجاح: {stats}")
            except Exception as e:
                messages.error(request, f"فشلت المزامنة: {e}")
        return redirect('admin:providers_providerprofile_changelist')

    def fetch_balance(self, request, profile_id):
        profile = self.get_object(request, profile_id)
        if profile:
            from services.provider.manager import ProviderManager
            try:
                data = ProviderManager.fetch_balance(profile)
                messages.success(request, f"الرصيد الحالي: {data['balance']} {data['currency']}")
            except Exception as e:
                messages.error(request, f"فشل تحديث الرصيد: {e}")
        return redirect('admin:providers_providerprofile_changelist')


@admin.register(ProviderCategory)
class ProviderCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'remote_id', 'parent')
    list_filter = ('profile',)
    search_fields = ('name', 'remote_id')


@admin.register(ProviderProduct)
class ProviderProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'category', 'product_type', 'is_active', 'cost_price', 'local_is_active')
    list_filter = ('profile', 'is_active', 'local_is_active', 'product_type')
    search_fields = ('name', 'remote_id', 'local_name')
    readonly_fields = ('remote_id', 'cost_price')
    actions = ['map_to_store']
    
    def map_to_store(self, request, queryset):
        mapped = 0
        errors = 0
        from services.provider.manager import ProviderManager
        for p in queryset:
            try:
                ProviderManager.sync_catalog(p.profile)
                mapped += 1
            except Exception:
                errors += 1
        
        if mapped > 0:
            messages.success(request, f"تم تعيين/مزامنة المنتجات بنجاح.")
        if errors > 0:
            messages.error(request, f"فشل تعيين {errors} منتج.")
    map_to_store.short_description = "تعيين المنتجات المحددة في المتجر"


@admin.register(ProviderPrice)
class ProviderPriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'margin_type', 'margin_value', 'manual_price', 'final_price')
    list_filter = ('margin_type',)
    search_fields = ('product__name',)


@admin.register(ProviderOrder)
class ProviderOrderAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'profile', 'local_order', 'product', 'status', 'remote_order_id', 'created_at')
    list_filter = ('profile', 'status')
    search_fields = ('uuid', 'remote_order_id', 'local_order__number')
    readonly_fields = ('uuid', 'remote_order_id', 'status', 'parameters_sent')


@admin.register(ProviderRequestLog)
class ProviderRequestLogAdmin(admin.ModelAdmin):
    list_display = ('profile', 'endpoint', 'method', 'execution_time_ms', 'created_at')
    list_filter = ('profile', 'method')
    search_fields = ('endpoint', 'payload')
    readonly_fields = ('profile', 'endpoint', 'method', 'payload', 'execution_time_ms')


@admin.register(ProviderResponseLog)
class ProviderResponseLogAdmin(admin.ModelAdmin):
    list_display = ('request_log', 'status_code', 'is_success', 'created_at')
    list_filter = ('is_success', 'status_code')
    search_fields = ('body',)
    readonly_fields = ('request_log', 'status_code', 'body', 'is_success')


@admin.register(ProviderErrorLog)
class ProviderErrorLogAdmin(admin.ModelAdmin):
    list_display = ('profile', 'error_code', 'message', 'created_at')
    list_filter = ('profile', 'error_code')
    search_fields = ('message', 'traceback')
    readonly_fields = ('profile', 'error_code', 'message', 'traceback', 'related_request')


@admin.register(ProviderSyncLog)
class ProviderSyncLogAdmin(admin.ModelAdmin):
    list_display = ('profile', 'status', 'products_created', 'products_updated', 'created_at')
    list_filter = ('profile', 'status')
    readonly_fields = ('profile', 'status', 'products_created', 'products_updated', 'products_disabled', 'errors_count', 'error_message')

admin.site.register(ProviderProductParameter)
admin.site.register(ProviderPriceHistory)
admin.site.register(ProviderOrderStatus)
admin.site.register(ProviderMapping)
