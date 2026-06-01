from django.contrib import admin

from apps.orders.models import Coupon, Invoice, Order, OrderItem, OrderLog


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("variant", "quantity", "unit_price", "total_price")


class OrderLogInline(admin.TabularInline):
    model = OrderLog
    extra = 0
    readonly_fields = ("status", "note", "created_by", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("number", "customer__email")
    inlines = [OrderItemInline, OrderLogInline]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_percent", "is_active", "used_count", "max_uses", "expires_at")
    list_filter = ("is_active",)
    search_fields = ("code",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "order", "total_amount", "issued_at")
    search_fields = ("invoice_number", "order__number", "order__customer__email")
