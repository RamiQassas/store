from rest_framework import serializers

from apps.catalog.models import Category, Product, ProductVariant, ProductTierPrice, ProductUserPrice


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "parent", "is_active", "sort_order", "image")


class ProductTierPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTierPrice
        fields = ("id", "tier", "price")


class ProductVariantSerializer(serializers.ModelSerializer):
    tier_prices = ProductTierPriceSerializer(many=True, read_only=True)
    # Expose qty metadata so the frontend knows how to render the quantity selector
    qty_type = serializers.SerializerMethodField()
    qty_min = serializers.SerializerMethodField()
    qty_max = serializers.SerializerMethodField()
    qty_list = serializers.SerializerMethodField()
    allow_custom_quantity = serializers.SerializerMethodField()
    api_product_type = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "name",
            "sku",
            "price",
            "wholesale_price",
            "vip_price",
            "cost",
            "discount_percent",
            "estimated_delivery_minutes",
            "is_active",
            "api_product_id",
            "delivery_type",
            "tier_prices",
            # Qty helpers derived from metadata
            "qty_type",
            "qty_min",
            "qty_max",
            "qty_list",
            "allow_custom_quantity",
            "api_product_type",
        )

    def _meta(self, obj):
        return obj.metadata if isinstance(obj.metadata, dict) else {}

    def get_qty_type(self, obj):
        return self._meta(obj).get("qty_type", "fixed")

    def get_qty_min(self, obj):
        return self._meta(obj).get("qty_min", 1)

    def get_qty_max(self, obj):
        return self._meta(obj).get("qty_max", 1)

    def get_qty_list(self, obj):
        return self._meta(obj).get("qty_list", [])

    def get_allow_custom_quantity(self, obj):
        return self._meta(obj).get("allow_custom_quantity", False)

    def get_api_product_type(self, obj):
        """Returns 'amount' or 'package' so the frontend can show the right UI."""
        return self._meta(obj).get("product_type", "package")


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    parent_category_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "category",
            "category_name",
            "parent_category_name",
            "image",
            "description",
            "instructions",
            "is_active",
            "is_featured",
            "sort_order",
            "form_schema",
            "is_api_product",
            "api_provider",
            "variants",
        )

    def get_parent_category_name(self, obj):
        """Returns the grandparent category name for breadcrumb / grouping."""
        if obj.category and obj.category.parent:
            return obj.category.parent.name
        return None
