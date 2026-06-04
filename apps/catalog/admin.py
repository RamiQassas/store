from django.contrib import admin

from apps.catalog.models import Category, Product, ProductVariant, ProductTierPrice, ProductUserPrice


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class ProductTierPriceInline(admin.TabularInline):
    model = ProductTierPrice
    extra = 1


class ProductUserPriceInline(admin.TabularInline):
    model = ProductUserPrice
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "is_featured", "sort_order")
    list_filter = ("is_active", "is_featured", "category")
    search_fields = ("name",)
    inlines = [ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "sku", "price", "wholesale_price", "vip_price", "cost", "is_active")
    list_filter = ("is_active", "product")
    search_fields = ("product__name", "name", "sku")
    inlines = [ProductTierPriceInline, ProductUserPriceInline]
