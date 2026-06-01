from rest_framework import serializers

from apps.catalog.models import Category, Product, ProductFormField, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "icon", "is_active", "sort_order")


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "name", "sku", "price", "discount_percent", "estimated_delivery_minutes", "is_active")


class ProductFormFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFormField
        fields = ("id", "label", "key", "field_type", "required", "placeholder", "options", "sort_order")


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    form_fields = ProductFormFieldSerializer(many=True, read_only=True)
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
            "delivery_type",
            "is_active",
            "is_featured",
            "sort_order",
            "metadata",
            "variants",
            "form_fields",
        )
