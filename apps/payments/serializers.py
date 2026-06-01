from rest_framework import serializers

from apps.payments.gateways import gateway_for
from apps.payments.models import DepositRequest, PaymentProvider


class PaymentProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentProvider
        fields = ("id", "name", "provider_type", "is_active", "config")
        read_only_fields = ("id",)


class DepositRequestSerializer(serializers.ModelSerializer):
    gateway_payload = serializers.SerializerMethodField()

    class Meta:
        model = DepositRequest
        fields = (
            "id",
            "provider",
            "amount",
            "currency",
            "status",
            "external_reference",
            "proof_image",
            "customer_note",
            "admin_note",
            "reviewed_at",
            "gateway_payload",
            "created_at",
        )
        read_only_fields = ("id", "status", "external_reference", "admin_note", "reviewed_at", "gateway_payload", "created_at")

    def create(self, validated_data):
        request = self.context["request"]
        deposit = DepositRequest.objects.create(user=request.user, **validated_data)
        payload = gateway_for(deposit.provider).create_payment(deposit)
        deposit.metadata["gateway_payload"] = payload
        deposit.save(update_fields=["metadata", "updated_at"])
        return deposit

    def get_gateway_payload(self, obj):
        return obj.metadata.get("gateway_payload", {})
