from decimal import Decimal

from django.db import transaction

from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction
from apps.common.models import Currency


class WalletError(Exception):
    pass


def credit_wallet(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        
        # If we were tracking this as pending, reduce pending balance
        if metadata and metadata.get("from_pending"):
            pending_amount = Decimal(metadata.get("pending_amount", amount))
            wallet.pending_balance = max(Decimal("0.00"), wallet.pending_balance - pending_amount)

        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "pending_balance", "updated_at"])
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


def freeze_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.available_balance < amount:
            raise WalletError("Insufficient wallet balance to freeze.")
        wallet.available_balance -= amount
        wallet.frozen_balance += amount
        wallet.save(update_fields=["available_balance", "frozen_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.FREEZE,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def release_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.frozen_balance < amount:
            raise WalletError("Insufficient frozen balance to release.")
        wallet.frozen_balance -= amount
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "frozen_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.RELEASE,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def finalize_withdrawal(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    """Finalizes a withdrawal by deducting from frozen balance and logging a debit transaction."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.frozen_balance < amount:
            raise WalletError("Insufficient frozen balance to finalize withdrawal.")
        wallet.frozen_balance -= amount
        wallet.save(update_fields=["frozen_balance", "updated_at"])
        
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type="withdrawal",
            reference=reference,
            metadata=metadata or {},
            status=WalletTransaction.Status.COMPLETED,
        )
        return wallet


def hold_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    """Holds funds for moderation or disputes. Deducts from available, adds to held."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.available_balance < amount:
            raise WalletError("Insufficient wallet balance to hold.")
        wallet.available_balance -= amount
        wallet.held_balance += amount
        wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.HOLD,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def unhold_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    """Releases held funds back to available balance."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.held_balance < amount:
            raise WalletError("Insufficient held balance to release.")
        wallet.held_balance -= amount
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.UNHOLD,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def track_pending_deposit(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    """Tracks a potential incoming deposit."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        wallet.pending_balance += amount
        wallet.save(update_fields=["pending_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.PENDING_DEPOSIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def cancel_pending_deposit(wallet_id, amount, reference="", description="", created_by=None, metadata=None):
    """Cancels a pending deposit tracking."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        wallet.pending_balance = max(Decimal("0.00"), wallet.pending_balance - amount)
        wallet.save(update_fields=["pending_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.PENDING_CANCEL,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            created_by=created_by,
            metadata=metadata or {},
        )
        return wallet


def auto_seed_currencies():
    """Emergency seeding of initial currencies if table is empty."""
    from apps.common.models import Currency
    if not Currency.objects.exists():
        Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            exchange_rate=1.0,
            is_default=True,
            is_active=True
        )
        Currency.objects.create(
            code="TRY",
            name="Turkish Lira",
            symbol="₺",
            exchange_rate=Decimal("32.50"),
            is_active=True
        )
        Currency.objects.create(
            code="SYP",
            name="Syrian Pound",
            symbol="£S",
            exchange_rate=Decimal("15000.0"),
            is_active=True
        )


def get_or_create_wallet(user):
    """
    Safely gets or creates a wallet for a user with the default currency.
    Ensures currencies exist before creation.
    """
    with transaction.atomic():
        wallet = Wallet.objects.filter(user=user).select_related("currency").first()
        if not wallet:
            # Emergency seed if table is empty
            auto_seed_currencies()
            
            default_currency = Currency.objects.filter(is_default=True).first()
            if not default_currency:
                # Fallback to USD or first available
                default_currency = Currency.objects.filter(code="USD").first() or Currency.objects.first()
            
            if not default_currency:
                raise WalletError("Critical Error: No currencies found in system even after emergency seeding.")
                
            wallet = Wallet.objects.create(
                user=user,
                currency=default_currency,
                available_balance=Decimal("0.00")
            )
        return wallet
