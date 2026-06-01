from django.contrib import admin

from apps.services.models import Service, ServiceField


class ServiceFieldInline(admin.TabularInline):
    model = ServiceField
    extra = 1


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "service_type", "is_active", "created_at")
    list_filter = ("service_type", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ServiceFieldInline]
