from rest_framework import serializers

from apps.catalog.models import Category, Product, ProductVariant, ProductTierPrice, ProductUserPrice


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "icon", "is_active", "sort_order")


class ProductTierPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTierPrice
        fields = ("id", "tier", "price")


class ProductVariantSerializer(serializers.ModelSerializer):
    tier_prices = ProductTierPriceSerializer(many=True, read_only=True)
    
    class Meta:
        model = ProductVariant
        fields = ("id", "name", "sku", "price", "wholesale_price", "vip_price", "discount_percent", "estimated_delivery_minutes", "is_active", "tier_prices")


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "category",
            "category_name",
            "image",
            "description",
            "instructions",
            "is_active",
            "is_featured",
            "sort_order",
            "form_schema",
            "metadata",
            "variants",
        )
