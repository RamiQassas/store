from django.contrib import admin
from django.utils import timezone

from apps.payments.models import DepositRequest, PaymentProvider
from apps.wallets.models import Wallet
from apps.wallets.services import credit_wallet


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "provider_type", "is_active", "created_at")
    list_filter = ("provider_type", "is_active")
    search_fields = ("name",)


@admin.action(description="Approve selected deposits and credit wallets")
def approve_deposits(modeladmin, request, queryset):
    for deposit in queryset.filter(status=DepositRequest.Status.PENDING).select_related("user__wallet"):
        deposit.status = DepositRequest.Status.PAID
        deposit.reviewed_by = request.user
        deposit.reviewed_at = timezone.now()
        deposit.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
        credit_wallet(
            wallet.id,
            deposit.amount,
            reference=f"deposit:{deposit.id}",
            description="Manual deposit approval",
            created_by=request.user,
        )


@admin.action(description="Reject selected deposits")
def reject_deposits(modeladmin, request, queryset):
    queryset.filter(status=DepositRequest.Status.PENDING).update(
        status=DepositRequest.Status.REJECTED,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
    )


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "amount", "currency", "status", "created_at", "reviewed_by")
    list_filter = ("status", "provider", "currency")
    search_fields = ("user__email", "external_reference")
    actions = [approve_deposits, reject_deposits]
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
