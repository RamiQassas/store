from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from apps.wallets.models import Wallet
from apps.payments.models import DepositRequest, WithdrawalRequest
from apps.wallets.services import credit_wallet, hold_funds, unhold_funds, finalize_withdrawal
from apps.common.services import log_system_action


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_deposit_approve(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.PENDING)
    admin_note = request.data.get("admin_note", "")
    adjusted_amount_str = request.data.get("adjusted_amount")
    
    try:
        wallet = Wallet.objects.get(user=deposit.user)
        final_amount = deposit.amount
        original_wallet_amount = deposit.wallet_amount
        
        if adjusted_amount_str:
            final_amount = Decimal(str(adjusted_amount_str))
            if final_amount != deposit.amount:
                if not deposit.metadata: deposit.metadata = {}
                deposit.metadata["adjusted_from"] = str(deposit.amount)
                deposit.amount = final_amount # Update original record to reflect approved amount
                
                # Recalculate wallet amount based on adjusted amount
                base_amount = deposit.currency.to_base(final_amount, "deposit")
                deposit.wallet_amount = wallet.currency.from_base(base_amount, "deposit")

        # Use service to credit wallet (atomic + ledger)
        credit_wallet(
            wallet_id=wallet.id,
            amount=deposit.wallet_amount,
            reference=f"dep:{deposit.id}",
            description=f"Approved deposit via {deposit.payment_method.name}",
            created_by=request.user,
            source="admin_approval",
            reason=admin_note,
            metadata={"from_pending": True, "pending_amount": str(original_wallet_amount), "is_adjusted": final_amount != Decimal(str(deposit.metadata.get("adjusted_from", final_amount)))}
        )
        
        deposit.status = DepositRequest.Status.COMPLETED
        deposit.reviewed_by = request.user
        deposit.reviewed_at = timezone.now()
        deposit.admin_note = admin_note
        deposit.save()
        
        log_system_action(
            actor=request.user,
            action_type="DEPOSIT_APPROVE",
            target=deposit,
            description=f"Approved deposit of {final_amount} for {deposit.user.email} (Adjusted: {final_amount != deposit.amount})",
            ip_address=request.META.get('REMOTE_ADDR'),
            reason=admin_note
        )

        from apps.notifications.services import notify_user
        notify_user(
            user=deposit.user,
            title="✅ تم تأكيد الإيداع",
            body=f"تمت إضافة {final_amount} {deposit.currency.code} إلى محفظتك بنجاح.",
            action_url="/dashboard/wallet/",
            priority="high",
            metadata={"type": "deposit_update"}
        )
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_deposit_reject(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.PENDING)
    admin_note = request.data.get("admin_note", "")
    
    from apps.wallets.services import cancel_pending_deposit
    wallet = Wallet.objects.get(user=deposit.user)
    
    cancel_pending_deposit(
        wallet_id=wallet.id,
        amount=deposit.amount,
        reference=f"dep:{deposit.id}",
        description="Deposit rejected by admin",
        created_by=request.user
    )
    
    deposit.status = DepositRequest.Status.REJECTED
    deposit.reviewed_by = request.user
    deposit.reviewed_at = timezone.now()
    deposit.admin_note = admin_note
    deposit.save()
    
    log_system_action(
        actor=request.user,
        action_type="DEPOSIT_REJECT",
        target=deposit,
        description=f"Rejected deposit of {deposit.amount} for {deposit.user.email}",
        ip_address=request.META.get('REMOTE_ADDR'),
        reason=admin_note
    )

    from apps.notifications.services import notify_user
    notify_user(
        user=deposit.user,
        title="❌ تم رفض الإيداع",
        body=f"عذراً، تم رفض طلب الإيداع. السبب: {admin_note or 'بيانات غير مكتملة'}",
        action_url="/dashboard/deposits/",
        priority="high"
    )

    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_deposit_correct(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.COMPLETED)
    admin_note = request.data.get("admin_note", "")
    new_amount_str = request.data.get("new_amount")
    
    if not new_amount_str:
        return Response({"detail": "المبلغ الجديد مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        new_amount = Decimal(str(new_amount_str))
        if new_amount == deposit.amount:
            return Response({"detail": "المبلغ مطابق للمبلغ الحالي."}, status=status.HTTP_400_BAD_REQUEST)

        wallet = Wallet.objects.get(user=deposit.user)
        old_wallet_amount = deposit.wallet_amount
        
        # Calculate new wallet amount
        base_amount = deposit.currency.to_base(new_amount, "deposit")
        new_wallet_amount = wallet.currency.from_base(base_amount, "deposit")
        
        difference = new_wallet_amount - old_wallet_amount
        
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(id=wallet.id)
            if difference < 0 and wallet.available_balance < abs(difference):
                 return Response({"detail": "رصيد المستخدم غير كافٍ لاسترداد الفارق."}, status=status.HTTP_400_BAD_REQUEST)
                 
            wallet.available_balance += difference
            wallet.save(update_fields=["available_balance", "updated_at"])
            
            from apps.wallets.models import LedgerEntry as LE
            entry_type = LE.EntryType.CREDIT if difference > 0 else LE.EntryType.DEBIT
            
            LE.objects.create(
                wallet=wallet,
                entry_type=entry_type,
                amount=abs(difference),
                balance_after=wallet.available_balance,
                reference=f"dep_corr:{deposit.id}",
                description=f"Admin correction for deposit via {deposit.payment_method.name}",
                source="admin_correction",
                reason=admin_note,
                created_by=request.user,
                metadata={"old_amount": str(deposit.amount), "new_amount": str(new_amount)}
            )
            
            if not deposit.metadata: deposit.metadata = {}
            if "adjusted_from" not in deposit.metadata:
                deposit.metadata["adjusted_from"] = str(deposit.amount)
            deposit.amount = new_amount
            deposit.wallet_amount = new_wallet_amount
            deposit.admin_note = f"{deposit.admin_note}\nCorrection: {admin_note}" if deposit.admin_note else f"Correction: {admin_note}"
            deposit.save()
            
            log_system_action(
                actor=request.user,
                action_type="DEPOSIT_CORRECT",
                target=deposit,
                description=f"Corrected deposit from {deposit.metadata['adjusted_from']} to {new_amount} for {deposit.user.email}",
                ip_address=request.META.get('REMOTE_ADDR'),
                reason=admin_note
            )
            
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_wallet_hold(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk)
    amount = Decimal(request.data.get("amount", "0"))
    reason = request.data.get("reason", "")
    
    try:
        hold_funds(
            wallet_id=wallet.id,
            amount=amount,
            description=f"Administrative hold: {reason}",
            created_by=request.user,
            source="admin_hold",
            reason=reason
        )
        
        log_system_action(
            actor=request.user,
            action_type="WALLET_HOLD",
            target=wallet,
            description=f"Held {amount} in wallet for {wallet.user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
            reason=reason,
            before_state={"available": str(wallet.available_balance + amount)},
            after_state={"available": str(wallet.available_balance)}
        )
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_wallet_unhold(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk)
    amount = Decimal(request.data.get("amount", "0"))
    reason = request.data.get("reason", "")
    
    try:
        unhold_funds(
            wallet_id=wallet.id,
            amount=amount,
            description=f"Released administrative hold: {reason}",
            created_by=request.user,
            source="admin_unhold",
            reason=reason
        )
        
        log_system_action(
            actor=request.user,
            action_type="WALLET_UNHOLD",
            target=wallet,
            description=f"Released hold of {amount} in wallet for {wallet.user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
            reason=reason,
            before_state={"held": str(wallet.held_balance + amount)},
            after_state={"held": str(wallet.held_balance)}
        )
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_withdrawal_process(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, status=WithdrawalRequest.Status.PENDING)
    withdrawal.status = WithdrawalRequest.Status.PROCESSING
    withdrawal.reviewed_by = request.user
    withdrawal.save()
    return Response({"status": "success"})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_withdrawal_approve(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING])
    withdrawal.status = WithdrawalRequest.Status.APPROVED
    withdrawal.reviewed_by = request.user
    withdrawal.save()
    return Response({"status": "success"})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_withdrawal_complete(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, status__in=[WithdrawalRequest.Status.APPROVED, WithdrawalRequest.Status.PROCESSING, WithdrawalRequest.Status.PENDING])
    admin_note = request.data.get("admin_note", "")
    
    try:
        from apps.wallets.services import finalize_withdrawal
        wallet = Wallet.objects.get(user=withdrawal.user)
        # Finalize (deduct from frozen)
        finalize_withdrawal(
            wallet_id=wallet.id,
            amount=withdrawal.wallet_amount,
            reference=f"with:{withdrawal.id}",
            description=f"Completed withdrawal via {withdrawal.payment_method.name}",
            created_by=request.user,
            source="withdrawal",
            reason=admin_note
        )
        
        withdrawal.status = WithdrawalRequest.Status.COMPLETED
        withdrawal.reviewed_by = request.user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.admin_note = admin_note
        withdrawal.save()
        
        log_system_action(
            actor=request.user,
            action_type="WITHDRAWAL_COMPLETE",
            target=withdrawal,
            description=f"Completed withdrawal of {withdrawal.amount} for {withdrawal.user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
            reason=admin_note
        )

        from apps.notifications.services import notify_user
        notify_user(
            user=withdrawal.user,
            title="💰 تم اكتمال السحب",
            body=f"تم تحويل {withdrawal.amount} {withdrawal.currency.code} إلى حسابك بنجاح.",
            action_url="/dashboard/withdrawals/",
            priority="high"
        )
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def api_withdrawal_reject(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    admin_note = request.data.get("admin_note", "")
    
    from apps.wallets.services import release_funds
    wallet = Wallet.objects.get(user=withdrawal.user)
    
    try:
        # Service to release frozen funds back to available
        release_funds(
            wallet_id=wallet.id,
            amount=withdrawal.wallet_amount,
            reference=f"with:{withdrawal.id}",
            description="Withdrawal rejected - funds released",
            created_by=request.user,
            source="withdrawal_reject",
            reason=admin_note
        )
        
        withdrawal.status = WithdrawalRequest.Status.REJECTED
        withdrawal.reviewed_by = request.user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.admin_note = admin_note
        withdrawal.save()
        
        log_system_action(
            actor=request.user,
            action_type="WITHDRAWAL_REJECT",
            target=withdrawal,
            description=f"Rejected withdrawal of {withdrawal.amount} for {withdrawal.user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
            reason=admin_note
        )

        from apps.notifications.services import notify_user
        notify_user(
            user=withdrawal.user,
            title="❌ تم رفض السحب",
            body=f"تم رفض طلب السحب وإعادة {withdrawal.amount} {withdrawal.currency.code} إلى رصيدك المتاح.",
            action_url="/dashboard/withdrawals/",
            priority="high"
        )
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
