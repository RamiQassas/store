from rest_framework import decorators, response, status, viewsets

from apps.common.permissions import ReadOnlyOrAdmin
from apps.orders.models import Coupon, Order, OrderLog
from apps.orders.serializers import CouponSerializer, OrderCreateSerializer, OrderSerializer


class OrderViewSet(viewsets.ModelViewSet):
    filterset_fields = ("status",)
    search_fields = ("number",)
    ordering_fields = ("created_at", "total_amount")

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        queryset = Order.objects.select_related("customer", "coupon", "invoice").prefetch_related("items__variant__product", "logs")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(customer=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        order = self.get_object()
        new_status = request.data.get("status")
        if new_status not in Order.Status.values:
            return response.Response({"status": "حالة غير صحيحة."}, status=status.HTTP_400_BAD_REQUEST)
        order.status = new_status
        order.admin_note = request.data.get("admin_note", order.admin_note)
        order.save(update_fields=["status", "admin_note", "updated_at"])
        OrderLog.objects.create(order=order, status=new_status, note=order.admin_note, created_by=request.user)
        return response.Response(OrderSerializer(order, context={"request": request}).data)


class CouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [ReadOnlyOrAdmin]
    search_fields = ("code",)
