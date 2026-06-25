import json
import uuid
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction, BalanceTransfer
from apps.common.models import Currency
from apps.notifications.models import Notification
from apps.accounts.models import KYCSettings

class WalletError(Exception):
    pass

def execute_p2p_transfer(sender, recipient, amount, currency, note=""):
    """
    Executes a P2P transfer between two users safely.
    Validates limits, KYC, and balances.
    """
    if sender == recipient:
        raise ValidationError("لا يمكنك تحويل رصيد لنفسك.")
    
    if amount <= Decimal("0.00"):
        raise ValidationError("يجب أن يكون المبلغ أكبر من صفر.")

    settings = KYCSettings.get_settings()
    
    if not settings.p2p_transfer_enabled:
        raise ValidationError("ميزة التحويل بين المستخدمين معطلة حالياً.")
        
    if settings.require_kyc_for_transfer and (not sender.is_kyc_verified or not recipient.is_kyc_verified):
        raise ValidationError("يجب أن يكون كلا الحسابين موثقين لإتمام التحويل.")

    # Calculate daily cumulative limit in USD
    limit_usd = sender.custom_p2p_transfer_limit if sender.has_custom_limits and sender.custom_p2p_transfer_limit else (settings.verified_transfer_limit if sender.is_kyc_verified else settings.unverified_transfer_limit)
    
    # Convert current amount to USD
    amount_usd = currency.to_base(amount, "withdraw")

    # Get transfers by this user today (Damascus midnight onwards)
    from django.utils import timezone
    from django.db.models import Sum
    today_start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_transfers_today = BalanceTransfer.objects.filter(
        sender=sender,
        status=BalanceTransfer.Status.COMPLETED,
        created_at__gte=today_start
    )
    
    daily_usage_usd = Decimal("0.00")
    for tr in sent_transfers_today:
        daily_usage_usd += tr.currency.to_base(tr.amount, "withdraw")

    if daily_usage_usd + amount_usd > limit_usd:
        remaining_usd = max(Decimal("0.00"), limit_usd - daily_usage_usd)
        remaining_in_currency = currency.from_base(remaining_usd, "withdraw")
        remaining_in_currency = remaining_in_currency.quantize(Decimal(f"0.{'0'*currency.decimal_places}"))
        raise ValidationError(
            f"لقد تجاوزت حد التحويل اليومي المسموح به. المتبقي لليوم: {remaining_in_currency} {currency.code} (يعادل {remaining_usd:.2f} USD) من أصل {limit_usd} USD."
        )

    fee_amount = (amount * settings.transfer_fee_percent) / Decimal("100.00")
    net_amount = amount - fee_amount

    # Mask emails for ledger descriptions
    email_parts_sender = sender.email.split('@')
    masked_sender_email = f"{email_parts_sender[0][:3]}***@{email_parts_sender[1]}" if len(email_parts_sender) == 2 and len(email_parts_sender[0]) > 3 else sender.email
    
    email_parts_recipient = recipient.email.split('@')
    masked_recipient_email = f"{email_parts_recipient[0][:3]}***@{email_parts_recipient[1]}" if len(email_parts_recipient) == 2 and len(email_parts_recipient[0]) > 3 else recipient.email

    with transaction.atomic():
        sender_wallet = Wallet.objects.select_for_update().get(user=sender, currency=currency)
        recipient_wallet = Wallet.objects.select_for_update().get(user=recipient, currency=currency)

        # Ensure that the debt balance is never transferable via P2P
        transferable_balance = sender_wallet.available_balance - sender_wallet.debt_balance
        if transferable_balance < amount:
            needed_extra = amount - transferable_balance
            raise ValidationError(
                f"رصيدك القابل للتحويل غير كافٍ لإتمام هذه العملية. "
                f"الرصيد المتاح للتحويل حالياً: {transferable_balance:.2f} {currency.code} (لا يمكن تحويل مبالغ الديون). "
                f"أنت بحاجة إلى إضافة {needed_extra:.2f} {currency.code} لتتمكن من تحويل مبلغ {amount:.2f} {currency.code}."
            )

        # Create Transfer Record
        transfer = BalanceTransfer.objects.create(
            sender=sender,
            recipient=recipient,
            currency=currency,
            amount=amount,
            fee_amount=fee_amount,
            net_amount=net_amount,
            status=BalanceTransfer.Status.COMPLETED,
            reference=f"P2P-{uuid.uuid4().hex[:8].upper()}",
            note=note
        )

        # Debit Sender
        debit_wallet(
            wallet_id=sender_wallet.id,
            amount=amount,
            source="P2P Transfer Out",
            reason=f"Transfer to {recipient.get_full_name() or recipient.display_name} ({masked_recipient_email}) [UID: {recipient.uid}] - Ref: {transfer.reference}",
            reference=transfer.reference,
            created_by=sender
        )

        # Credit Recipient
        credit_wallet(
            wallet_id=recipient_wallet.id,
            amount=net_amount,
            source="P2P Transfer In",
            reason=f"Transfer from {sender.get_full_name() or sender.display_name} ({masked_sender_email}) [UID: {sender.uid}] - Ref: {transfer.reference}",
            reference=transfer.reference,
            created_by=sender
        )

    # Send notifications (after commit)
    try:
        from apps.notifications.services import notify_user
        # Notify Sender
        notify_user(
            user=sender,
            title="تم تسليم التحويل المالي",
            body=f"تم توصيل حوالتك بقيمة {transfer.amount} {transfer.currency.code} بنجاح إلى {recipient.get_full_name() or recipient.display_name} (UID: {recipient.uid}).",
            category="financial",
            action_url="/dashboard/wallet/"
        )
        # Notify Recipient
        notify_user(
            user=recipient,
            title="استلام تحويل مالي جديد",
            body=f"لقد تلقيت حوالة مالية بقيمة {transfer.net_amount} {transfer.currency.code} من {sender.get_full_name() or sender.display_name} (UID: {sender.uid}).",
            category="financial",
            action_url="/dashboard/wallet/"
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send transfer notifications: {str(e)}")

    return transfer

def reverse_p2p_transfer(transfer, admin_user=None):
    """
    Reverses a completed or suspended P2P transfer.
    Deducts the net amount from the recipient, refunds the full amount to the sender.
    """
    if transfer.status not in [BalanceTransfer.Status.COMPLETED, BalanceTransfer.Status.SUSPENDED]:
        raise WalletError("لا يمكن إلغاء تحويل غير مكتمل أو معلق.")

    with transaction.atomic():
        sender_wallet = Wallet.objects.select_for_update().get(user=transfer.sender, currency=transfer.currency)
        recipient_wallet = Wallet.objects.select_for_update().get(user=transfer.recipient, currency=transfer.currency)

        is_suspended = (transfer.status == BalanceTransfer.Status.SUSPENDED)
        
        if is_suspended:
            if recipient_wallet.held_balance < transfer.net_amount:
                raise WalletError("رصيد المستلم المحجوز غير كافٍ لاسترداد مبلغ التحويل.")
            # Unhold funds manually in this transaction so we can debit them from available balance
            recipient_wallet.held_balance -= transfer.net_amount
            recipient_wallet.available_balance += transfer.net_amount
            recipient_wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
            
            # Create Ledger Entry for unholding
            LedgerEntry.objects.create(
                wallet=recipient_wallet,
                entry_type=LedgerEntry.EntryType.UNHOLD,
                amount=transfer.net_amount,
                balance_after=recipient_wallet.available_balance,
                reference=transfer.reference,
                description=f"فك حجز لإلغاء التحويل المرجعي: {transfer.reference}",
                source="P2P Reversal Unhold",
                reason="فك حجز تلقائي لإتمام عملية الإلغاء والاسترداد",
                created_by=admin_user,
            )

        if recipient_wallet.available_balance < transfer.net_amount:
            raise WalletError("رصيد المستلم غير كافٍ لاسترداد مبلغ التحويل.")

        # Update transfer status
        transfer.status = BalanceTransfer.Status.REJECTED
        transfer.note = f"{transfer.note} [تم إلغاء واسترداد التحويل]"
        transfer.save(update_fields=['status', 'note', 'updated_at'])

        # Debit Recipient (Reversal)
        debit_wallet(
            wallet_id=recipient_wallet.id,
            amount=transfer.net_amount,
            source="P2P Reversal Out",
            reason=f"Reversal of transfer from {transfer.sender.uid} - Ref: {transfer.reference}",
            reference=f"REV-{transfer.reference}",
            created_by=admin_user
        )

        # Credit Sender (Refund)
        credit_wallet(
            wallet_id=sender_wallet.id,
            amount=transfer.amount,
            source="P2P Reversal In",
            reason=f"Refund of transfer to {transfer.recipient.uid} - Ref: {transfer.reference}",
            reference=f"REV-{transfer.reference}",
            created_by=admin_user
        )

def suspend_p2p_transfer(transfer, admin_user=None):
    """
    Suspends a completed P2P transfer.
    Moves the net amount from the recipient's available balance to held balance.
    """
    if transfer.status != BalanceTransfer.Status.COMPLETED:
        raise WalletError("يمكن تعليق الحوالات المكتملة فقط.")

    recipient_wallet = Wallet.objects.get(user=transfer.recipient, currency=transfer.currency)
    
    with transaction.atomic():
        # Hold the net amount from the recipient's wallet
        hold_funds(
            wallet_id=recipient_wallet.id,
            amount=transfer.net_amount,
            reference=transfer.reference,
            description=f"تعليق الحوالة المرجعية: {transfer.reference}",
            created_by=admin_user,
            source="P2P Suspend",
            reason=f"تعليق الحوالة رقم {transfer.reference} بواسطة الإدارة"
        )
        
        # Update transfer status
        transfer.status = BalanceTransfer.Status.SUSPENDED
        transfer.note = f"{transfer.note} [تم تعليق الحوالة]"
        transfer.save(update_fields=['status', 'note', 'updated_at'])

def unsuspend_p2p_transfer(transfer, admin_user=None):
    """
    Unsuspends (resumes) a suspended P2P transfer.
    Releases the net amount from the recipient's held balance back to available balance.
    """
    if transfer.status != BalanceTransfer.Status.SUSPENDED:
        raise WalletError("لا يمكن إلغاء تعليق حوالة غير معلقة.")

    recipient_wallet = Wallet.objects.get(user=transfer.recipient, currency=transfer.currency)
    
    with transaction.atomic():
        # Release the net amount from the recipient's wallet
        unhold_funds(
            wallet_id=recipient_wallet.id,
            amount=transfer.net_amount,
            reference=transfer.reference,
            description=f"إلغاء تعليق الحوالة المرجعية: {transfer.reference}",
            created_by=admin_user,
            source="P2P Unsuspend",
            reason="إلغاء تعليق الحوالة من قبل الإدارة"
        )
        
        # Update transfer status
        transfer.status = BalanceTransfer.Status.COMPLETED
        transfer.note = f"{transfer.note} [تم إلغاء تعليق الحوالة]"
        transfer.save(update_fields=['status', 'note', 'updated_at'])

def edit_p2p_transfer_amount(transfer, new_amount, admin_user=None):
    """
    Edits the amount of a completed P2P transfer.
    Adjusts the sender's and recipient's balances accordingly.
    """
    if transfer.status != BalanceTransfer.Status.COMPLETED:
        raise WalletError("يمكن تعديل مبلغ الحوالات المكتملة فقط.")

    new_amount = Decimal(new_amount)
    if new_amount <= Decimal("0.00"):
        raise WalletError("يجب أن يكون المبلغ الجديد أكبر من صفر.")

    if new_amount == transfer.amount:
        return transfer

    from apps.accounts.models import KYCSettings
    settings = KYCSettings.get_settings()
    
    new_fee_amount = (new_amount * settings.transfer_fee_percent) / Decimal("100.00")
    new_net_amount = new_amount - new_fee_amount

    old_amount = transfer.amount
    old_net_amount = transfer.net_amount
    old_fee_amount = transfer.fee_amount

    amount_diff = new_amount - old_amount
    net_amount_diff = new_net_amount - old_net_amount

    with transaction.atomic():
        sender_wallet = Wallet.objects.select_for_update().get(user=transfer.sender, currency=transfer.currency)
        recipient_wallet = Wallet.objects.select_for_update().get(user=transfer.recipient, currency=transfer.currency)

        # Validate balances before making changes
        if amount_diff > 0:
            if sender_wallet.withdrawable_balance < amount_diff:
                raise WalletError("رصيد المرسل غير كافٍ لتعديل قيمة التحويل.")
        
        if net_amount_diff < 0:
            if recipient_wallet.available_balance < abs(net_amount_diff):
                raise WalletError("رصيد المستلم غير كافٍ لتعديل قيمة التحويل.")

        # Update Sender's wallet
        if amount_diff > 0:
            debit_wallet(
                wallet_id=sender_wallet.id,
                amount=amount_diff,
                source="P2P Adjustment Out",
                reason=f"تعديل مبلغ الحوالة {transfer.reference} (زيادة المبلغ من {old_amount} إلى {new_amount})",
                reference=transfer.reference,
                created_by=admin_user
            )
        elif amount_diff < 0:
            credit_wallet(
                wallet_id=sender_wallet.id,
                amount=abs(amount_diff),
                source="P2P Adjustment In",
                reason=f"تعديل مبلغ الحوالة {transfer.reference} (تخفيض المبلغ من {old_amount} إلى {new_amount})",
                reference=transfer.reference,
                created_by=admin_user
            )

        # Update Recipient's wallet
        if net_amount_diff > 0:
            credit_wallet(
                wallet_id=recipient_wallet.id,
                amount=net_amount_diff,
                source="P2P Adjustment In",
                reason=f"تعديل صافي الحوالة {transfer.reference} (زيادة من {old_net_amount} إلى {new_net_amount})",
                reference=transfer.reference,
                created_by=admin_user
            )
        elif net_amount_diff < 0:
            debit_wallet(
                wallet_id=recipient_wallet.id,
                amount=abs(net_amount_diff),
                source="P2P Adjustment Out",
                reason=f"تعديل صافي الحوالة {transfer.reference} (تخفيض من {old_net_amount} إلى {new_net_amount})",
                reference=transfer.reference,
                created_by=admin_user
            )

        # Save transfer changes
        transfer.amount = new_amount
        transfer.fee_amount = new_fee_amount
        transfer.net_amount = new_net_amount
        transfer.note = f"{transfer.note} [تم تعديل المبلغ من {old_amount} إلى {new_amount} بواسطة الإدارة]"
        transfer.save(update_fields=['amount', 'fee_amount', 'net_amount', 'note', 'updated_at'])

    # Send notifications (after commit)
    try:
        from apps.notifications.services import notify_user
        notify_user(
            user=transfer.sender,
            title="تعديل قيمة حوالة مالية",
            body=f"تم تعديل قيمة حوالتك ذات الرقم المرجعي {transfer.reference} لتصبح {transfer.amount} {transfer.currency.code} بدلاً من {old_amount} {transfer.currency.code}.",
            category="financial",
            action_url="/dashboard/wallet/"
        )
        notify_user(
            user=transfer.recipient,
            title="تعديل قيمة حوالة مالية",
            body=f"تم تعديل قيمة حوالتك الواردة ذات الرقم المرجعي {transfer.reference} لتصبح {transfer.net_amount} {transfer.currency.code} بدلاً من {old_net_amount} {transfer.currency.code}.",
            category="financial",
            action_url="/dashboard/wallet/"
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send transfer adjustment notifications: {str(e)}")

    return transfer

def json_serialize_safe(data):
    if not data: return {}
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal): return str(obj)
            if hasattr(obj, 'hex'): return str(obj) # UUID
            return super().default(obj)
    return json.loads(json.dumps(data, cls=CustomEncoder))

def credit_wallet(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="system", reason=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    
    # Extract source currency info if provided in metadata
    metadata = metadata or {}
    source_amount = metadata.get("source_amount")
    source_currency_code = metadata.get("source_currency")

    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        
        # If we were tracking this as pending, reduce pending balance
        if metadata and metadata.get("from_pending"):
            pending_amount = Decimal(metadata.get("pending_amount", amount)).quantize(Decimal("0.01"))
            wallet.pending_balance = max(Decimal("0.00"), wallet.pending_balance - pending_amount)

        # Auto-deduct debt if it's a deposit
        debt_paid = Decimal("0.00")
        if source in ["admin_approval", "deposit", "admin_adjustment", "admin_cash", "recharge_card"] and wallet.debt_balance > 0:
            debt_paid = min(amount, wallet.debt_balance)
            wallet.debt_balance -= debt_paid
            amount -= debt_paid
            
            if debt_paid > 0:
                LedgerEntry.objects.create(
                    wallet=wallet,
                    entry_type=LedgerEntry.EntryType.DEBT_PAYMENT,
                    amount=debt_paid,
                    balance_after=wallet.available_balance,
                    reference=reference,
                    description=f"Auto-deduction for debt from deposit. {description}",
                    source=source,
                    reason="Auto debt deduction",
                    created_by=created_by,
                    metadata=json_serialize_safe({
                        "original_credit_amount": str(amount + debt_paid), 
                        "debt_paid": str(debt_paid),
                        "source_amount": str(source_amount) if source_amount else None,
                        "source_currency": source_currency_code
                    })
                )

        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "pending_balance", "debt_balance", "updated_at"])
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount + debt_paid, # Track total amount in transaction
            transaction_type="credit",
            reference=reference,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def add_debt(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="admin", reason=""):
    """Assigns debt to a user and adds it to their available balance as credit."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        wallet.debt_balance += amount
        wallet.available_balance += amount # Add to available balance so they can spend it
        wallet.save(update_fields=["debt_balance", "available_balance", "updated_at"])
        
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.DEBT_ADD,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user, notify_staff
        notify_user(
            user=wallet.user,
            title="إضافة دين جديد",
            body=f"تم إضافة دين بقيمة {amount:,.2f} {wallet.currency.code} إلى حسابك. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )
        
        notify_staff(
            title="إضافة دين لمستخدم",
            body=f"تم إضافة دين بقيمة {amount:,.2f} {wallet.currency.code} للمستخدم {wallet.user.email}. السبب: {reason}",
            priority=Notification.Priority.HIGH
        )

        return wallet


def pay_debt(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="admin", reason="", deduct_from_balance=True):
    """Manually pays off debt. If deduct_from_balance is True, reduces available_balance."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.debt_balance < amount:
            raise WalletError("Payment exceeds outstanding debt.")
            
        if deduct_from_balance:
            if wallet.available_balance < amount:
                raise WalletError("Insufficient available balance to pay debt.")
            wallet.available_balance -= amount
            
        wallet.debt_balance -= amount
        wallet.save(update_fields=["available_balance", "debt_balance", "updated_at"])
        
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.DEBT_PAYMENT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user, notify_staff
        notify_user(
            user=wallet.user,
            title="تسديد دين",
            body=f"تم تسجيل سداد دين بقيمة {amount:,.2f} {wallet.currency.code}. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )

        notify_staff(
            title="سداد دين من مستخدم",
            body=f"تم تسجيل سداد دين بقيمة {amount:,.2f} {wallet.currency.code} للمستخدم {wallet.user.email}. السبب: {reason}"
        )

        return wallet


def debit_wallet(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="system", reason=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.available_balance < amount:
            raise WalletError("Insufficient wallet balance.")
        wallet.available_balance -= amount
        wallet.save(update_fields=["available_balance", "updated_at"])
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type="debit",
            reference=reference,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def freeze_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="system", reason=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.withdrawable_balance < amount:
            raise WalletError("رصيد غير كافٍ للسحب (رصيد الدين غير قابل للسحب).")
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user
        notify_user(
            user=wallet.user,
            title="تجميد مبلغ",
            body=f"تم تجميد مبلغ {amount:,.2f} {wallet.currency.code} من رصيدك لعملية سحب أو معالجة. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )

        return wallet


def release_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="system", reason=""):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.frozen_balance < amount:
            # Safely handle the case where frozen balance is missing or insufficient
            deficit = amount - wallet.frozen_balance
            wallet.frozen_balance = Decimal("0.00")
            description += f" (Warning: Released {amount} but only had {amount - deficit} frozen. Adjusted.)"
            wallet.available_balance += (amount - deficit) # Only release what was actually frozen back to available
        else:
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user
        notify_user(
            user=wallet.user,
            title="فك تجميد مبلغ",
            body=f"تم فك تجميد مبلغ {amount} {wallet.currency.code} وإعادته إلى رصيدك. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )

        return wallet


def finalize_withdrawal(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="withdrawal", reason=""):
    """Finalizes a withdrawal by deducting from frozen balance and logging a debit transaction."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.frozen_balance < amount:
            # Safely handle the case where frozen balance is missing or insufficient
            # Deduct whatever is left in frozen, and the rest from available (if possible)
            # or just log it and zero out frozen. The best approach is to deduct from frozen
            # and if not enough, deduct the remainder from available if possible, or just 
            # force frozen to zero and deduct from available.
            # To be safest, we just deduct what we can from frozen.
            deficit = amount - wallet.frozen_balance
            wallet.frozen_balance = Decimal("0.00")
            if wallet.available_balance >= deficit:
                wallet.available_balance -= deficit
                description += " (Warning: Insufficient frozen balance, deducted remainder from available.)"
            else:
                wallet.available_balance = Decimal("0.00")
                description += " (Critical Warning: Insufficient frozen AND available balance. Balances set to zero.)"
        else:
            wallet.frozen_balance -= amount
            
        wallet.save(update_fields=["frozen_balance", "available_balance", "updated_at"])
        
        # Note: Available balance doesn't change here because it was already deducted when frozen.
        # But we still create a LedgerEntry for audit trail.
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description,
            source=source,
            reason=reason or "Finalized withdrawal",
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type="withdrawal",
            reference=reference,
            metadata=json_serialize_safe(metadata),
            status=WalletTransaction.Status.COMPLETED,
        )
        return wallet


def hold_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="admin", reason=""):
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user, notify_staff
        notify_user(
            user=wallet.user,
            title="حجز أموال",
            body=f"تم حجز مبلغ {amount} {wallet.currency.code} مؤقتاً من رصيدك. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )
        
        notify_staff(
            title="حجز رصيد مستخدم",
            body=f"تم حجز مبلغ {amount} {wallet.currency.code} من رصيد {wallet.user.email}. السبب: {reason}"
        )

        # SystemAuditLog should be handled by the caller (view/admin) to include IP/UserAgent
        
        return wallet


def unhold_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="admin", reason=""):
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )

        from apps.notifications.services import notify_user, notify_staff
        notify_user(
            user=wallet.user,
            title="فك حجز الأموال",
            body=f"تم إلغاء حجز مبلغ {amount} {wallet.currency.code} وإعادته إلى رصيدك المتاح. {reason}",
            category='financial',
            metadata={'amount': str(amount), 'currency': wallet.currency.code, 'reference': reference}
        )

        notify_staff(
            title="فك حجز رصيد مستخدم",
            body=f"تم إلغاء حجز مبلغ {amount} {wallet.currency.code} للمستخدم {wallet.user.email}. السبب: {reason}"
        )

        return wallet


def reserve_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="order", reason=""):
    """Reserves funds for pending orders. Deducts from available, adds to reserved."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.available_balance < amount:
            raise WalletError("Insufficient wallet balance to reserve.")
        wallet.available_balance -= amount
        wallet.reserved_balance += amount
        wallet.save(update_fields=["available_balance", "reserved_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.RESERVE,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description or "Reserve funds",
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def release_reserved_funds(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="order", reason=""):
    """Releases reserved funds back to available balance."""
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("Amount must be positive.")
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        if wallet.reserved_balance < amount:
            raise WalletError("Insufficient reserved balance to release.")
        wallet.reserved_balance -= amount
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance", "reserved_balance", "updated_at"])
        LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=LedgerEntry.EntryType.UNRESERVE,
            amount=amount,
            balance_after=wallet.available_balance,
            reference=reference,
            description=description or "Release reserved funds",
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def track_pending_deposit(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="deposit", reason=""):
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def cancel_pending_deposit(wallet_id, amount, reference="", description="", created_by=None, metadata=None, source="deposit", reason=""):
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
            source=source,
            reason=reason,
            created_by=created_by,
            metadata=json_serialize_safe(metadata),
        )
        return wallet


def auto_seed_currencies():
    """Emergency seeding of initial currencies if table is empty."""
    from apps.common.models import Currency
    from apps.common.tenant_utils import get_current_store, bypass_tenant_filter
    
    current_store = get_current_store()
    
    if not Currency.objects.exists():
        with bypass_tenant_filter():
            global_currencies = list(Currency.objects.filter(store__isnull=True))
            
        if current_store is not None:
            if global_currencies:
                for gc in global_currencies:
                    Currency.objects.create(
                        store=current_store,
                        name=gc.name,
                        code=gc.code,
                        symbol=gc.symbol,
                        buy_rate=gc.buy_rate,
                        sell_rate=gc.sell_rate,
                        capital_rate=gc.capital_rate,
                        conversion_method=gc.conversion_method,
                        decimal_places=gc.decimal_places,
                        display_order=gc.display_order,
                        is_active=gc.is_active,
                        is_default=gc.is_default
                    )
            else:
                Currency.objects.create(
                    store=current_store,
                    code="USD",
                    name="US Dollar",
                    symbol="$",
                    buy_rate=1.0,
                    sell_rate=1.0,
                    is_default=True,
                    is_active=True
                )
                Currency.objects.create(
                    store=current_store,
                    code="TRY",
                    name="Turkish Lira",
                    symbol="₺",
                    buy_rate=Decimal("32.50"),
                    sell_rate=Decimal("32.00"),
                    is_active=True
                )
                Currency.objects.create(
                    store=current_store,
                    code="SYP",
                    name="Syrian Pound",
                    symbol="£S",
                    buy_rate=Decimal("15000.0"),
                    sell_rate=Decimal("14500.0"),
                    is_active=True
                )
        else:
            Currency.objects.create(
                code="USD",
                name="US Dollar",
                symbol="$",
                buy_rate=1.0,
                sell_rate=1.0,
                is_default=True,
                is_active=True
            )
            Currency.objects.create(
                code="TRY",
                name="Turkish Lira",
                symbol="₺",
                buy_rate=Decimal("32.50"),
                sell_rate=Decimal("32.00"),
                is_active=True
            )
            Currency.objects.create(
                code="SYP",
                name="Syrian Pound",
                symbol="£S",
                buy_rate=Decimal("15000.0"),
                sell_rate=Decimal("14500.0"),
                is_active=True
            )


def get_or_create_wallet(user):
    """
    Safely gets or creates a wallet for a user with the default currency in the current store context.
    Ensures currencies exist before creation.
    """
    from apps.common.tenant_utils import get_current_store, bypass_tenant_filter
    
    active_store = get_current_store()
    
    with transaction.atomic():
        wallet = Wallet.all_objects.filter(user=user, store=active_store).select_related("currency").first()
        if not wallet:
            # Emergency seed if table is empty
            auto_seed_currencies()
            
            default_currency = Currency.objects.filter(is_default=True).first()
            if not default_currency:
                # Fallback to USD or first available
                default_currency = Currency.objects.filter(code="USD").first() or Currency.objects.first()
            
            if not default_currency:
                with bypass_tenant_filter():
                    default_currency = Currency.objects.filter(is_default=True).first() or Currency.objects.first()
            
            if not default_currency:
                raise WalletError("Critical Error: No currencies found in system even after emergency seeding.")
                
            wallet = Wallet.all_objects.create(
                user=user,
                store=active_store,
                currency=default_currency,
                available_balance=Decimal("0.00")
            )
        return wallet
