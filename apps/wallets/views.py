from rest_framework import mixins, viewsets, decorators, response, status
from rest_framework.permissions import IsAuthenticated

from apps.wallets.models import Wallet
from apps.wallets.serializers import WalletSerializer
from apps.wallets.services import hold_funds, unhold_funds


class WalletViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Wallet.objects.select_related("user").order_by("-created_at")
        return Wallet.objects.filter(user=self.request.user).order_by("-created_at")

    @decorators.action(detail=True, methods=["post"])
    def hold(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        amount = request.data.get("amount")
        reason = request.data.get("reason", "Administrative hold")
        
        if not amount:
            return response.Response({"detail": "يرجى تحديد المبلغ."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            hold_funds(
                wallet_id=pk,
                amount=amount,
                description=reason,
                created_by=request.user
            )
            return response.Response({"status": "funds held successfully"})
        except Exception as e:
            return response.Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=["post"])
    def unhold(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        
        amount = request.data.get("amount")
        reason = request.data.get("reason", "Administrative release")
        
        if not amount:
            return response.Response({"detail": "يرجى تحديد المبلغ."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            unhold_funds(
                wallet_id=pk,
                amount=amount,
                description=reason,
                created_by=request.user
            )
            return response.Response({"status": "funds released successfully"})
        except Exception as e:
            return response.Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
