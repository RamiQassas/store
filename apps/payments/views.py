from django.utils import timezone
from rest_framework import decorators, response, status, viewsets

from apps.common.permissions import ReadOnlyOrAdmin
from apps.payments.models import DepositRequest, PaymentProvider
from apps.payments.serializers import DepositRequestSerializer, PaymentProviderSerializer
from apps.wallets.models import Wallet
from apps.wallets.services import credit_wallet


class PaymentProviderViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentProviderSerializer
    permission_classes = [ReadOnlyOrAdmin]

    def get_queryset(self):
        queryset = PaymentProvider.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class DepositRequestViewSet(viewsets.ModelViewSet):
    serializer_class = DepositRequestSerializer
    filterset_fields = ("status", "provider")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        queryset = DepositRequest.objects.select_related("user", "provider")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        deposit = self.get_object()
        if deposit.status != DepositRequest.Status.PENDING:
            return response.Response({"detail": "لا يمكن اعتماد طلب غير معلق."}, status=status.HTTP_400_BAD_REQUEST)
        deposit.status = DepositRequest.Status.PAID
        deposit.reviewed_by = request.user
        deposit.reviewed_at = timezone.now()
        deposit.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
        credit_wallet(wallet.id, deposit.amount, reference=f"deposit:{deposit.id}", description="Manual deposit approval", created_by=request.user)
        return response.Response(self.get_serializer(deposit).data)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        deposit = self.get_object()
        deposit.status = DepositRequest.Status.REJECTED
        deposit.admin_note = request.data.get("admin_note", deposit.admin_note)
        deposit.reviewed_by = request.user
        deposit.reviewed_at = timezone.now()
        deposit.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])
        return response.Response(self.get_serializer(deposit).data)
