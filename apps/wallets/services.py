from decimal import Decimal

from django.db import transaction

from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction


class WalletError(Exception):
    pass


def credit_wallet(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type="credit",
            reference=reference,
            metadata=metadata or {},
        )
        return wallet


def debit_wallet(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.available_balance < amount:
            raise WalletError("Insufficient wallet balance.")
        wallet.available_balance -= amount
        wallet.save(update_fields=["available_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type="debit",
            reference=reference,
            metadata=metadata or {},
        )
        return wallet
