from rest_framework import serializers

from apps.catalog.serializers import ProductVariantSerializer
from apps.orders.models import Coupon, Invoice, Order, OrderItem, OrderLog
from apps.orders.services import create_order


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = ("id", "code", "discount_percent", "max_uses", "used_count", "is_active", "expires_at")


class OrderItemSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "variant", "quantity", "unit_price", "total_price")


class OrderLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLog
        fields = ("id", "status", "note", "created_at")


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ("id", "invoice_number", "total_amount", "issued_at")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    logs = OrderLogSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ("id", "number", "status", "total_amount", "coupon", "fulfillment_data", "metadata", "admin_note", "items", "logs", "invoice", "created_at")


class OrderCreateSerializer(serializers.Serializer):
    variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    fulfillment_data = serializers.JSONField(default=dict)
    metadata = serializers.JSONField(default=dict)
    coupon_code = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        coupon = None
        coupon_code = validated_data.get("coupon_code")
        if coupon_code:
            coupon = Coupon.objects.filter(code__iexact=coupon_code, is_active=True).first()
            if not coupon:
                raise serializers.ValidationError({"coupon_code": "الكوبون غير صالح."})
        return create_order(
            customer=self.context["request"].user,
            variant_id=validated_data["variant_id"],
            quantity=validated_data["quantity"],
            fulfillment_data=validated_data.get("fulfillment_data", {}),
            metadata=validated_data.get("metadata", {}),
            coupon=coupon,
        )

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data
