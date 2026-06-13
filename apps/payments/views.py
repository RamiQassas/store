from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from rest_framework import decorators, response, status, viewsets, permissions

from apps.common.permissions import ReadOnlyOrAdmin
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.payments.serializers import DepositRequestSerializer, PaymentMethodSerializer, WithdrawalRequestSerializer
from apps.wallets.services import (
    credit_wallet, 
    freeze_funds, 
    release_funds, 
    finalize_withdrawal, 
    track_pending_deposit, 
    cancel_pending_deposit,
    get_or_create_wallet
)
from apps.notifications.services import notify_user


class PaymentMethodViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentMethodSerializer
    permission_classes = [ReadOnlyOrAdmin]

    def get_queryset(self):
        queryset = PaymentMethod.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class DepositRequestViewSet(viewsets.ModelViewSet):
    serializer_class = DepositRequestSerializer
    filterset_fields = ("status", "payment_method")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        queryset = DepositRequest.objects.select_related("user", "payment_method", "currency")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            # Check daily limit BEFORE creation
            user = self.request.user
            currency = serializer.validated_data.get('currency')
            amount = serializer.validated_data.get('amount')
            
            amount_in_usd = currency.to_base(amount, "deposit")
            if amount_in_usd > user.remaining_deposit_limit:
                raise permissions.exceptions.ValidationError(f"لقد تجاوزت حد الإيداع اليومي المتبقي ({user.remaining_deposit_limit:,.2f} USD).")

            deposit = serializer.save()
            wallet = get_or_create_wallet(deposit.user)
            track_pending_deposit(
                wallet_id=wallet.id,
                amount=deposit.wallet_amount,
                reference=f"deposit:{deposit.id}",
                description=f"إيداع معلق عبر {deposit.payment_method.name}",
                created_by=deposit.user
            )

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        with transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            
            if deposit.status == DepositRequest.Status.COMPLETED:
                return response.Response({"detail": "تم اعتماد هذا الطلب مسبقاً."}, status=status.HTTP_400_BAD_REQUEST)
            
            if deposit.status == DepositRequest.Status.REJECTED:
                return response.Response({"detail": "لا يمكن اعتماد طلب مرفوض."}, status=status.HTTP_400_BAD_REQUEST)

            # Check for admin override amount
            override_amount = request.data.get("amount")
            if override_amount:
                # Admin is overriding the GROSS amount
                deposit.amount = Decimal(str(override_amount))
                deposit.calculate_fees()
                
            final_amount = deposit.final_amount
            
            # Calculate final wallet amount (amount - fee) converted to wallet currency
            # We ALWAYS re-calculate here to ensure we use the correct rate and avoid stale/wrong stored values
            wallet = get_or_create_wallet(deposit.user)
            if deposit.currency.code == wallet.currency.code:
                wallet_final_amount = final_amount
            else:
                base_val = deposit.currency.to_base(final_amount, "deposit")
                wallet_final_amount = wallet.currency.from_base(base_val, "deposit")

            if wallet_final_amount <= 0:
                return response.Response({"detail": "خطأ في حساب المبلغ المودع: يجب أن يكون المبلغ أكبر من صفر."}, status=status.HTTP_400_BAD_REQUEST)

            # 1. Credit wallet FIRST
            credit_wallet(
                wallet_id=wallet.id,
                amount=wallet_final_amount,
                reference=f"deposit:{deposit.id}",
                description=f"إيداع عبر {deposit.payment_method.name}",
                created_by=request.user,
                metadata={
                    "from_pending": True,
                    "pending_amount": str(deposit.wallet_amount)
                }
            )

            # 2. Update deposit status ONLY IF credit succeeds
            deposit.final_amount = final_amount
            # Also update wallet_amount to reflect what was actually credited
            deposit.wallet_amount = wallet_final_amount
            deposit.status = DepositRequest.Status.COMPLETED
            deposit.reviewed_by = request.user
            deposit.reviewed_at = timezone.now()
            deposit.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at", "final_amount", "wallet_amount", "amount", "fee_amount"])
            
            # Increment daily usage for the user (in base currency/USD)
            try:
                amount_in_usd = deposit.currency.to_base(deposit.final_amount, "deposit")
                deposit.user.add_deposit_usage(amount_in_usd)
            except: pass

            notify_user(
                user=deposit.user,
                title="تم قبول طلب الإيداع",
                body=f"تمت إضافة {deposit.final_amount:,.2f} {deposit.currency.code} إلى محفظتك بنجاح.",
                action_url="/dashboard/wallet/",
                category='financial',
                priority="high"
            )

        return response.Response(self.get_serializer(deposit).data)

    @decorators.action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        with transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != DepositRequest.Status.COMPLETED:
                return response.Response({"detail": "يمكن تصحيح الطلبات المكتملة فقط."}, status=status.HTTP_400_BAD_REQUEST)

            new_amount = request.data.get("new_amount")
            if not new_amount:
                return response.Response({"detail": "المبلغ الجديد مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
                
            from decimal import Decimal
            new_amount = Decimal(str(new_amount))
            admin_note = request.data.get("admin_note", "")

            # 1. Calculate the difference
            old_amount = deposit.final_amount
            diff_amount = new_amount - old_amount
            
            if diff_amount == 0:
                return response.Response({"detail": "لم يتم تغيير المبلغ."}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Convert difference to wallet currency
            wallet = get_or_create_wallet(deposit.user)
            if deposit.currency.code == wallet.currency.code:
                wallet_diff = diff_amount
            else:
                base_diff = deposit.currency.to_base(diff_amount, "deposit")
                wallet_diff = wallet.currency.from_base(base_diff, "deposit")

            # 3. Apply adjustment to wallet
            from apps.wallets.services import debit_wallet
            if wallet_diff > 0:
                credit_wallet(
                    wallet_id=wallet.id,
                    amount=wallet_diff,
                    reference=f"deposit_adj:{deposit.id}",
                    description=f"تصحيح مبلغ الإيداع (زيادة): {admin_note}",
                    created_by=request.user,
                    source="admin_adjustment"
                )
            else:
                debit_wallet(
                    wallet_id=wallet.id,
                    amount=abs(wallet_diff),
                    reference=f"deposit_adj:{deposit.id}",
                    description=f"تصحيح مبلغ الإيداع (نقص): {admin_note}",
                    created_by=request.user,
                    source="admin_adjustment"
                )

            # 4. Update deposit record
            deposit.final_amount = new_amount
            # Update wallet_amount accordingly
            deposit.wallet_amount += wallet_diff
            if admin_note:
                current_notes = deposit.admin_note or ""
                deposit.admin_note = f"{current_notes}\n[تصحيح {timezone.now().strftime('%Y-%m-%d %H:%M')}]: {admin_note}"
            deposit.save(update_fields=["final_amount", "wallet_amount", "admin_note", "updated_at"])

        return response.Response(self.get_serializer(deposit).data)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        with transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status == DepositRequest.Status.COMPLETED:
                return response.Response({"detail": "لا يمكن رفض طلب مكتمل."}, status=status.HTTP_400_BAD_REQUEST)

            if deposit.status != DepositRequest.Status.REJECTED:
                wallet = get_or_create_wallet(deposit.user)
                cancel_pending_deposit(
                    wallet_id=wallet.id,
                    amount=deposit.wallet_amount,
                    reference=f"deposit_reject:{deposit.id}",
                    description=f"إلغاء إيداع معلق مرفوض عبر {deposit.payment_method.name}",
                    created_by=request.user
                )

            deposit.status = DepositRequest.Status.REJECTED
            deposit.admin_note = request.data.get("admin_note", deposit.admin_note)
            deposit.reviewed_by = request.user
            deposit.reviewed_at = timezone.now()
            deposit.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])
            
            notify_user(
                user=deposit.user,
                title="تم رفض طلب الإيداع",
                body=f"نعتذر، تم رفض طلب الإيداع رقم {deposit.id}. السبب: {deposit.admin_note}",
                action_url="/dashboard/",
                category='financial',
                priority="normal"
            )
        
        return response.Response(self.get_serializer(deposit).data)


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    serializer_class = WithdrawalRequestSerializer
    filterset_fields = ("status", "payment_method")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        queryset = WithdrawalRequest.objects.select_related("user", "payment_method", "currency")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            # Check daily limit BEFORE creation
            user = self.request.user
            currency = serializer.validated_data.get('currency')
            amount = serializer.validated_data.get('amount')
            
            amount_in_usd = currency.to_base(amount, "withdraw")
            if amount_in_usd > user.remaining_withdrawal_limit:
                raise permissions.exceptions.ValidationError(f"لقد تجاوزت حد السحب اليومي المتبقي ({user.remaining_withdrawal_limit:,.2f} USD).")

            withdrawal = serializer.save()
            wallet = get_or_create_wallet(withdrawal.user)
            # Freeze funds immediately upon request
            freeze_funds(
                wallet_id=wallet.id,
                amount=withdrawal.wallet_amount,
                reference=f"withdrawal:{withdrawal.id}",
                description=f"سحب عبر {withdrawal.payment_method.name}",
                created_by=withdrawal.user
            )
            # Increment usage on REQUEST to respect daily limits
            user.add_withdrawal_usage(amount_in_usd)

    @decorators.action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        withdrawal = self.get_object()
        if withdrawal.status != WithdrawalRequest.Status.PENDING:
            return response.Response({"detail": "يمكن معالجة الطلبات المعلقة فقط."}, status=status.HTTP_400_BAD_REQUEST)

        withdrawal.status = WithdrawalRequest.Status.PROCESSING
        withdrawal.reviewed_by = request.user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        
        return response.Response(self.get_serializer(withdrawal).data)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        withdrawal = self.get_object()
        if withdrawal.status not in [WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING]:
            return response.Response({"detail": "لا يمكن الموافقة على هذا الطلب في حالته الحالية."}, status=status.HTTP_400_BAD_REQUEST)

        withdrawal.status = WithdrawalRequest.Status.APPROVED
        withdrawal.admin_note = request.data.get("admin_note", withdrawal.admin_note)
        withdrawal.reviewed_by = request.user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])
        
        return response.Response(self.get_serializer(withdrawal).data)

    @decorators.action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            
            if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                return response.Response({"detail": "هذا الطلب مكتمل مسبقاً."}, status=status.HTTP_400_BAD_REQUEST)
            
            if withdrawal.status not in [WithdrawalRequest.Status.PROCESSING, WithdrawalRequest.Status.APPROVED]:
                return response.Response({"detail": "يجب معالجة أو الموافقة على الطلب قبل إكماله."}, status=status.HTTP_400_BAD_REQUEST)

            withdrawal.status = WithdrawalRequest.Status.COMPLETED
            withdrawal.admin_note = request.data.get("admin_note", withdrawal.admin_note)
            if "proof_image" in request.FILES:
                withdrawal.proof_image = request.FILES["proof_image"]
            withdrawal.reviewed_by = request.user
            withdrawal.reviewed_at = timezone.now()
            withdrawal.save()

            wallet = get_or_create_wallet(withdrawal.user)
            finalize_withdrawal(
                wallet_id=wallet.id,
                amount=withdrawal.wallet_amount,
                reference=f"withdrawal:{withdrawal.id}",
                description=f"سحب مكتمل عبر {withdrawal.payment_method.name}",
                created_by=request.user
            )
            
            notify_user(
                user=withdrawal.user,
                title="💰 تم اكتمال السحب",
                body=f"تم تحويل {withdrawal.amount} {withdrawal.currency.code} إلى حسابك بنجاح.",
                action_url="/dashboard/withdrawals/",
                category="financial",
                priority="high"
            )

        return response.Response(self.get_serializer(withdrawal).data)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            
            if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.CANCELLED, WithdrawalRequest.Status.REJECTED]:
                return response.Response({"detail": "لا يمكن رفض طلب منتهي."}, status=status.HTTP_400_BAD_REQUEST)

            withdrawal.status = WithdrawalRequest.Status.REJECTED
            withdrawal.admin_note = request.data.get("admin_note", withdrawal.admin_note)
            withdrawal.reviewed_by = request.user
            withdrawal.reviewed_at = timezone.now()
            withdrawal.save()

            # Release funds back to available balance
            wallet = get_or_create_wallet(withdrawal.user)
            release_funds(
                wallet_id=wallet.id,
                amount=withdrawal.wallet_amount,
                reference=f"withdrawal_reject:{withdrawal.id}",
                description=f"استرداد سحب مرفوض عبر {withdrawal.payment_method.name}",
                created_by=request.user
            )
            
            # Reverse daily usage on rejection
            try:
                amount_in_usd = withdrawal.currency.to_base(withdrawal.amount, "withdraw")
                withdrawal.user.add_withdrawal_usage(-amount_in_usd)
            except: pass
            
            notify_user(
                user=withdrawal.user,
                title="تم رفض طلب السحب",
                body=f"نعتذر، تم رفض طلب السحب رقم {withdrawal.id}. تم إعادة المبلغ لمحفظتك. السبب: {withdrawal.admin_note}",
                action_url="/dashboard/wallet/",
                category="financial",
                priority="normal"
            )
        
        return response.Response(self.get_serializer(withdrawal).data)

    @decorators.action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            
            if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                return response.Response({"detail": "يمكن عكس الطلبات المكتملة فقط."}, status=status.HTTP_400_BAD_REQUEST)

            withdrawal.status = WithdrawalRequest.Status.CANCELLED
            withdrawal.admin_note = request.data.get("admin_note", withdrawal.admin_note)
            withdrawal.reviewed_by = request.user
            withdrawal.reviewed_at = timezone.now()
            withdrawal.save()

            # Refund funds to available balance
            wallet = get_or_create_wallet(withdrawal.user)
            credit_wallet(
                wallet_id=wallet.id,
                amount=withdrawal.wallet_amount,
                reference=f"withdrawal_reverse:{withdrawal.id}",
                description=f"إلغاء وعكس سحب مكتمل عبر {withdrawal.payment_method.name}",
                created_by=request.user,
                reason="Withdrawal reversed by admin"
            )
            
            notify_user(
                user=withdrawal.user,
                title="تم إلغاء عملية السحب",
                body=f"تم إلغاء عملية السحب رقم {withdrawal.id} وإعادة المبلغ لمحفظتك.",
                action_url="/dashboard/wallet/",
                category="financial",
                priority="high"
            )
        
        return response.Response(self.get_serializer(withdrawal).data)

    @decorators.action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            
            if not request.user.is_staff and withdrawal.user != request.user:
                 return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)

            if withdrawal.status != WithdrawalRequest.Status.PENDING:
                return response.Response({"detail": "يمكن إلغاء الطلبات المعلقة فقط."}, status=status.HTTP_400_BAD_REQUEST)

            withdrawal.status = WithdrawalRequest.Status.CANCELLED
            withdrawal.save(update_fields=["status", "updated_at"])

            # Release funds back to available balance
            wallet = get_or_create_wallet(withdrawal.user)
            release_funds(
                wallet_id=wallet.id,
                amount=withdrawal.wallet_amount,
                reference=f"withdrawal_cancel:{withdrawal.id}",
                description=f"إلغاء طلب سحب عبر {withdrawal.payment_method.name}",
                created_by=request.user
            )

            # Reverse daily usage on cancellation
            try:
                amount_in_usd = withdrawal.currency.to_base(withdrawal.amount, "withdraw")
                withdrawal.user.add_withdrawal_usage(-amount_in_usd)
            except: pass
        
        return response.Response(self.get_serializer(withdrawal).data)
