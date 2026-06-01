from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.wallets.models import Wallet
from apps.wallets.serializers import WalletSerializer


class WalletViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Wallet.objects.select_related("user").prefetch_related("ledger_entries", "transactions").order_by("-created_at")
        return Wallet.objects.filter(user=self.request.user).prefetch_related("ledger_entries", "transactions").order_by("-created_at")
