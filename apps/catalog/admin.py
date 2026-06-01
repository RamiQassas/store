from django.contrib import admin

from apps.catalog.models import Category, Product, ProductFormField, ProductVariant


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class ProductFormFieldInline(admin.TabularInline):
    model = ProductFormField
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "delivery_type", "is_active", "is_featured", "sort_order")
    list_filter = ("delivery_type", "is_active", "is_featured", "category")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline, ProductFormFieldInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "sku", "price", "cost", "is_active")
    list_filter = ("is_active", "product")
    search_fields = ("product__name", "name", "sku")
