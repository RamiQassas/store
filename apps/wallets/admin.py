from django.contrib import admin

from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "available_balance", "frozen_balance", "currency", "updated_at")
    search_fields = ("user__email",)
    list_filter = ("currency",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("wallet", "entry_type", "amount", "balance_after", "reference", "created_at")
    list_filter = ("entry_type",)
    search_fields = ("wallet__user__email", "reference")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "transaction_type", "status", "amount", "reference", "created_at")
    list_filter = ("status", "transaction_type")
    search_fields = ("wallet__user__email", "reference")
