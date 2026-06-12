from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from apps.common.permissions import IsFinanceManager, IsKYCManager, IsSupportAgent

from apps.wallets.models import Wallet
from apps.payments.models import DepositRequest, WithdrawalRequest
from apps.wallets.services import credit_wallet, hold_funds, unhold_funds, finalize_withdrawal, release_funds, cancel_pending_deposit
from apps.common.services import log_system_action


@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_deposit_approve(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.PENDING)
    admin_note = request.data.get("admin_note", "")
    adjusted_amount_str = request.data.get("adjusted_amount")
    
    try:
        wallet = Wallet.objects.get(user=deposit.user)
        final_amount = deposit.amount
        
        if adjusted_amount_str:
            final_amount = Decimal(str(adjusted_amount_str))
            if final_amount <= 0:
                return Response({"detail": "المبلغ يجب أن يكون أكبر من الصفر."}, status=status.HTTP_400_BAD_REQUEST)
            
            if final_amount != deposit.amount:
                if not deposit.metadata: deposit.metadata = {}
                deposit.metadata["adjusted_from"] = str(deposit.amount)
                deposit.amount = final_amount
        
        # Recalculate wallet_amount based on final_amount if it's 0 or adjusted
        base_amount = deposit.currency.to_base(final_amount, "deposit")
        wallet_credit_amount = wallet.currency.from_base(base_amount, "deposit")
        
        if wallet_credit_amount <= Decimal("0"):
            return Response({"detail": "خطأ: القيمة المحولة للمحفظة يجب أن تكون أكبر من الصفر. تأكد من إدخال مبلغ صحيح وسعر صرف العملة."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Update deposit record first
            deposit.amount = final_amount
            deposit.wallet_amount = wallet_credit_amount
            deposit.status = DepositRequest.Status.COMPLETED
            deposit.reviewed_by = request.user
            deposit.reviewed_at = timezone.now()
            deposit.admin_note = admin_note
            deposit.save()

            credit_wallet(
                wallet_id=wallet.id,
                amount=wallet_credit_amount,
                reference=f"dep:{deposit.id}",
                description=f"Approved deposit via {deposit.payment_method.name}",
                created_by=request.user,
                source="admin_approval",
                reason=admin_note,
                metadata={"from_pending": True}
            )
        
        try:
            from apps.notifications.services import notify_user
            notify_user(
                user=deposit.user,
                title="✅ تم تأكيد الإيداع",
                body=f"تمت إضافة {deposit.wallet_amount:,.2f} {wallet.currency.code} إلى محفظتك بنجاح.",
                action_url="/dashboard/wallet/",
                category="financial",
                priority="high"
            )
        except:
            pass
        
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_deposit_reject(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.PENDING)
    admin_note = request.data.get("admin_note", "")
    
    try:
        wallet = Wallet.objects.get(user=deposit.user)
        
        # Ensure we have a valid amount to cancel
        cancel_amount = deposit.wallet_amount or Decimal("0.00")
        
        with transaction.atomic():
            if cancel_amount > 0:
                cancel_pending_deposit(
                    wallet_id=wallet.id,
                    amount=cancel_amount,
                    reference=f"dep:{deposit.id}",
                    description="Deposit rejected by admin",
                    created_by=request.user
                )
            
            deposit.status = DepositRequest.Status.REJECTED
            deposit.reviewed_by = request.user
            deposit.reviewed_at = timezone.now()
            deposit.admin_note = admin_note
            deposit.save()
        
        try:
            from apps.notifications.services import notify_user
            from apps.notifications.models import Notification
            notify_user(
                user=deposit.user,
                title="❌ تم رفض الإيداع",
                body=f"عذراً، تم رفض طلب الإيداع. السبب: {admin_note or 'بيانات غير مكتملة'}",
                action_url="/dashboard/deposits/",
                category="financial",
                priority=Notification.Priority.HIGH
            )
        except:
            pass

        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": f"خطأ أثناء الرفض: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_deposit_correct(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk, status=DepositRequest.Status.COMPLETED)
    admin_note = request.data.get("admin_note", "")
    new_amount_str = request.data.get("new_amount")
    
    if not new_amount_str:
        return Response({"detail": "المبلغ الجديد مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        new_amount = Decimal(str(new_amount_str))
        wallet = Wallet.objects.get(user=deposit.user)
        old_wallet_amount = deposit.wallet_amount
        
        base_amount = deposit.currency.to_base(new_amount, "deposit")
        new_wallet_amount = wallet.currency.from_base(base_amount, "deposit")
        difference = new_wallet_amount - old_wallet_amount
        
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(id=wallet.id)
            wallet.available_balance += difference
            wallet.save(update_fields=["available_balance", "updated_at"])
            
            deposit.amount = new_amount
            deposit.wallet_amount = new_wallet_amount
            deposit.save()
            
        return Response({"status": "success"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_wallet_hold(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk)
    amount = Decimal(request.data.get("amount", "0"))
    hold_funds(wallet.id, amount, description="Administrative hold", created_by=request.user)
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_wallet_unhold(request, pk):
    wallet = get_object_or_404(Wallet, pk=pk)
    amount = Decimal(request.data.get("amount", "0"))
    unhold_funds(wallet.id, amount, description="Hold released", created_by=request.user)
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_withdrawal_process(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    withdrawal.status = WithdrawalRequest.Status.PROCESSING
    withdrawal.save()
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_withdrawal_approve(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    withdrawal.status = WithdrawalRequest.Status.APPROVED
    withdrawal.save()
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_withdrawal_complete(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    admin_note = request.data.get("admin_note", "")
    wallet = Wallet.objects.get(user=withdrawal.user)
    
    finalize_withdrawal(
        wallet_id=wallet.id,
        amount=withdrawal.wallet_amount,
        reference=f"with:{withdrawal.id}",
        description="Withdrawal completed",
        created_by=request.user
    )
    
    withdrawal.status = WithdrawalRequest.Status.COMPLETED
    withdrawal.reviewed_at = timezone.now()
    withdrawal.admin_note = admin_note
    withdrawal.save()
    
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def api_order_mark_read(request, pk):
    from apps.orders.models import Order
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    order.is_delivery_read = True
    order.save(update_fields=["is_delivery_read"])
    return Response({"status": "success"})

@api_view(["POST"])
@permission_classes([IsFinanceManager])
def api_withdrawal_reject(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    admin_note = request.data.get("admin_note", "")
    wallet = Wallet.objects.get(user=withdrawal.user)
    
    release_funds(
        wallet_id=wallet.id,
        amount=withdrawal.wallet_amount,
        reference=f"with:{withdrawal.id}",
        description="Withdrawal rejected",
        created_by=request.user
    )
    
    withdrawal.reviewed_at = timezone.now()
    withdrawal.admin_note = admin_note
    withdrawal.save()
    
    return Response({"status": "success"})


@api_view(["GET"])
@permission_classes([IsSupportAgent])
def api_user_search(request):
    from django.db.models import Q
    from django.contrib.auth import get_user_model
    User = get_user_model()
    query = request.GET.get("q", "")
    if len(query) < 2:
        return Response([])
    
    users = User.objects.filter(
        Q(email__icontains=query) | 
        Q(username__icontains=query) | 
        Q(first_name__icontains=query) | 
        Q(last_name__icontains=query)
    ).only("email", "username", "first_name", "last_name", "public_uuid")[:10]
    
    results = [
        {
            "id": str(u.id),
            "email": u.email,
            "username": u.username,
            "full_name": u.get_full_name(),
            "public_uuid": str(u.public_uuid)
        } for u in users
    ]
    return Response(results)
