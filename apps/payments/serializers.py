from rest_framework import serializers

from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.wallets.services import get_or_create_wallet


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class DepositRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositRequest
        fields = (
            "id",
            "payment_method",
            "amount",
            "fee_amount",
            "final_amount",
            "currency",
            "status",
            "transaction_id",
            "proof_image",
            "customer_note",
            "admin_note",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = ("id", "status", "fee_amount", "final_amount", "admin_note", "reviewed_at", "created_at")

    def validate(self, data):
        payment_method = data["payment_method"]
        amount = data["amount"]

        if not payment_method.can_deposit:
            raise serializers.ValidationError({"payment_method": "وسيلة الدفع هذه غير متاحة للإيداع."})

        if not payment_method.is_active:
            raise serializers.ValidationError({"payment_method": "وسيلة الدفع هذه غير نشطة حالياً."})
        
        if payment_method.is_maintenance_mode:
            raise serializers.ValidationError({"payment_method": "وسيلة الدفع هذه في وضع الصيانة حالياً."})

        if amount < payment_method.deposit_min_amount:
            raise serializers.ValidationError({"amount": f"المبلغ أقل من الحد الأدنى المسموح به ({payment_method.deposit_min_amount})."})

        if amount > payment_method.deposit_max_amount:
            raise serializers.ValidationError({"amount": f"المبلغ أكبر من الحد الأقصى المسموح به ({payment_method.deposit_max_amount})."})

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = (
            "id",
            "payment_method",
            "amount",
            "fee_amount",
            "final_amount",
            "currency",
            "status",
            "payout_details",
            "admin_note",
            "proof_image",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = ("id", "status", "fee_amount", "final_amount", "admin_note", "proof_image", "reviewed_at", "created_at")

    def validate(self, data):
        payment_method = data["payment_method"]
        amount = data["amount"]
        user = self.context["request"].user

        if not payment_method.can_withdraw:
            raise serializers.ValidationError({"payment_method": "وسيلة الدفع هذه غير متاحة للسحب."})

        if not payment_method.is_active:
            raise serializers.ValidationError({"payment_method": "وسيلة السحب هذه غير نشطة حالياً."})
        
        if payment_method.is_maintenance_mode:
            raise serializers.ValidationError({"payment_method": "وسيلة السحب هذه في وضع الصيانة حالياً."})

        if amount < payment_method.withdrawal_min_amount:
            raise serializers.ValidationError({"amount": f"المبلغ أقل من الحد الأدنى المسموح به ({payment_method.withdrawal_min_amount})."})

        if amount > payment_method.withdrawal_max_amount:
            raise serializers.ValidationError({"amount": f"المبلغ أكبر من الحد الأقصى المسموح به ({payment_method.withdrawal_max_amount})."})

        # Check balance
        wallet = get_or_create_wallet(user)
        if wallet.available_balance < amount:
            raise serializers.ValidationError({"amount": "الرصيد غير كافٍ لإجراء عملية السحب."})

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
