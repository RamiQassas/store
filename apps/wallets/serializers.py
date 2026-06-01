from rest_framework import serializers

from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ("id", "entry_type", "amount", "balance_after", "reference", "description", "metadata", "created_at")
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ("id", "status", "amount", "transaction_type", "reference", "metadata", "created_at")
        read_only_fields = fields


class WalletSerializer(serializers.ModelSerializer):
    ledger_entries = LedgerEntrySerializer(many=True, read_only=True)
    transactions = WalletTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Wallet
        fields = (
            "id", 
            "currency", 
            "available_balance", 
            "frozen_balance", 
            "held_balance", 
            "pending_balance", 
            "total_balance",
            "ledger_entries", 
            "transactions", 
            "created_at", 
            "updated_at"
        )
        read_only_fields = fields
