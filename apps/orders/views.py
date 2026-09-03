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

    @decorators.action(detail=False, methods=["post", "get"], url_path="alkasr_webhook", permission_classes=[], authentication_classes=[])
    def alkasr_webhook(self, request):
        return self._process_alkasr_webhook(request)

    @decorators.action(detail=False, methods=["post", "get"], url_path="webhook", permission_classes=[], authentication_classes=[])
    def legacy_webhook(self, request):
        return self._process_alkasr_webhook(request)

    def _process_alkasr_webhook(self, request):
        import logging
        from apps.orders.provider_status import apply_provider_status
        
        logger = logging.getLogger(__name__)
        
        data = {}
        if request.data and isinstance(request.data, dict):
            data.update(request.data)
        if request.POST:
            data.update(request.POST.dict())
        if request.GET:
            data.update(request.GET.dict())
            
        logger.info(f"Alkasr webhook payload: {data}")
        
        # Try to find the order by api_order_uuid or api_order_id
        order_uuid = data.get("order_uuid") or data.get("uuid") or data.get("orders")
        order_id = data.get("order_id") or data.get("id")
        api_status = data.get("status")
        
        order = None
        if order_uuid:
            order = Order.objects.filter(api_order_uuid=order_uuid).first()
        if not order and order_id:
            order = Order.objects.filter(api_order_id=order_id).first()
            
        if not order:
            logger.warning(f"Alkasr Webhook: Order not found for uuid={order_uuid}, order_id={order_id}")
            return response.Response({"status": "error", "message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
            
        if not api_status:
            logger.warning("Alkasr Webhook: Status field is missing in payload")
            return response.Response({"status": "error", "message": "Missing status"}, status=status.HTTP_400_BAD_REQUEST)
            
        logger.info(f"Updating Order {order.number} status via Alkasr webhook. New status: {api_status}")
        
        apply_provider_status(order, api_status, raw_response=data, actor=None, note_prefix="Alkasr webhook")
                
        return response.Response({"status": "success", "message": "Order status updated"})

    @decorators.action(detail=True, methods=["post"])
    def sync_alkasr_status(self, request, pk=None):
        from apps.orders.provider_status import apply_provider_status
        from services.provider.manager import ProviderManager
        
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        order = self.get_object()
        if not order.api_order_uuid and not order.api_order_id:
            return response.Response({"detail": "هذا الطلب غير مربوط بـ API خارجي."}, status=status.HTTP_400_BAD_REQUEST)
            
        provider_order = order.provider_orders.select_related("profile").first()
        if not provider_order or not provider_order.profile:
            return response.Response({"detail": "لا يوجد سجل طلب مزود مرتبط بهذا الطلب."}, status=status.HTTP_400_BAD_REQUEST)

        identifiers = [str(order.api_order_uuid)] if order.api_order_uuid else ([str(order.api_order_id)] if order.api_order_id else [])
        data_list = ProviderManager.check_orders(
            provider_order.profile,
            identifiers,
            is_uuid=bool(order.api_order_uuid)
        )
        res = {"status": "OK", "data": data_list}
            
        if res.get("status") == "OK" and isinstance(res.get("data"), list) and len(res["data"]) > 0:
            order_data = res["data"][0]
            api_status = order_data.get("status")
            api_order_id = order_data.get("order_id")
            
            if api_order_id and not order.api_order_id:
                order.api_order_id = api_order_id
                order.save(update_fields=["api_order_id", "updated_at"])
            order = apply_provider_status(order, api_status, raw_response=order_data, actor=request.user, note_prefix="فحص يدوي")
            return response.Response({
                "status": "success",
                "message": f"تم فحص الحالة وتحديث الطلب بنجاح إلى: {order.get_status_display()}",
                "api_status": api_status
            })
        else:
            error_msg = res.get("message") or "لم يتم العثور على بيانات الطلب في الـ API."
            return response.Response({"detail": f"فشل فحص الحالة: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)


class CouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [ReadOnlyOrAdmin]
    search_fields = ("code",)
