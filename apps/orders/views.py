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
        import json
        from apps.orders.provider_status import apply_provider_status
        from apps.providers.models import ProviderOrder, ProviderOrderStatus
        
        logger = logging.getLogger(__name__)
        
        data = {}
        if request.data:
            if isinstance(request.data, dict):
                data.update(request.data)
            elif isinstance(request.data, list) and len(request.data) > 0 and isinstance(request.data[0], dict):
                data.update(request.data[0])
        if request.POST:
            data.update(request.POST.dict())
        if request.GET:
            data.update(request.GET.dict())
        if not data and request.body:
            try:
                body_json = json.loads(request.body.decode('utf-8'))
                if isinstance(body_json, dict):
                    data.update(body_json)
                elif isinstance(body_json, list) and len(body_json) > 0 and isinstance(body_json[0], dict):
                    data.update(body_json[0])
            except Exception:
                pass
            
        logger.info(f"Alkasr webhook payload received: {data}")
        
        # Unpack nested item if wrapped
        item = data
        if isinstance(data.get("data"), dict):
            item = data["data"]
        elif isinstance(data.get("data"), list) and len(data["data"]) > 0 and isinstance(data["data"][0], dict):
            item = data["data"][0]
        elif isinstance(data.get("orders"), list) and len(data["orders"]) > 0 and isinstance(data["orders"][0], dict):
            item = data["orders"][0]

        order_uuid = item.get("order_uuid") or item.get("uuid") or (data.get("order_uuid") if not isinstance(data.get("order_uuid"), list) else None) or (data.get("uuid") if not isinstance(data.get("uuid"), list) else None)
        order_id = item.get("order_id") or item.get("id") or data.get("order_id") or data.get("id")
        api_status = item.get("status") or data.get("status")
        
        order = None
        if order_uuid:
            try:
                order = Order.all_objects.filter(api_order_uuid=order_uuid).first()
            except Exception:
                pass
        if not order and order_id:
            order = Order.all_objects.filter(api_order_id=str(order_id)).first()
        if not order and order_id:
            try:
                po = ProviderOrder.objects.filter(remote_order_id=str(order_id)).select_related("local_order").first()
                if po and po.local_order:
                    order = po.local_order
            except Exception:
                pass
        if not order and order_uuid:
            try:
                po = ProviderOrder.objects.filter(uuid=order_uuid).select_related("local_order").first()
                if po and po.local_order:
                    order = po.local_order
            except Exception:
                pass
            
        if not order:
            logger.warning(f"Alkasr Webhook: Order not found for uuid={order_uuid}, order_id={order_id}")
            return response.Response({"status": "error", "message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
            
        if not api_status:
            logger.warning("Alkasr Webhook: Status field is missing in payload")
            return response.Response({"status": "error", "message": "Missing status"}, status=status.HTTP_400_BAD_REQUEST)
            
        logger.info(f"Updating Order {order.number} status via Alkasr webhook. New status: {api_status}")
        
        updated_order = apply_provider_status(order, api_status, raw_response=item, actor=None, note_prefix="Alkasr Webhook")
        
        # Sync ProviderOrder record if present
        try:
            po = None
            if order_id:
                po = ProviderOrder.objects.filter(remote_order_id=str(order_id)).first()
            if not po and order_uuid:
                po = ProviderOrder.objects.filter(uuid=order_uuid).first()
            if not po and updated_order:
                po = updated_order.provider_orders.first()
            if po:
                po.status = str(api_status).lower()
                if order_id and not po.remote_order_id:
                    po.remote_order_id = str(order_id)
                po.save(update_fields=["status", "remote_order_id", "updated_at"])
                ProviderOrderStatus.objects.create(
                    provider_order=po,
                    status=str(api_status).lower(),
                    raw_response=item
                )
        except Exception as e:
            logger.warning(f"Error updating ProviderOrder in webhook: {e}")
                
        return response.Response({"status": "success", "message": "Order status updated", "order": updated_order.number, "status": updated_order.status})

    @decorators.action(detail=True, methods=["post"])
    def sync_alkasr_status(self, request, pk=None):
        from apps.orders.provider_status import apply_provider_status
        from services.provider.manager import ProviderManager
        from apps.providers.models import ProviderProfile
        
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        order = self.get_object()
        if not order.api_order_uuid and not order.api_order_id:
            return response.Response({"detail": "هذا الطلب غير مربوط بـ API خارجي."}, status=status.HTTP_400_BAD_REQUEST)
            
        provider_order = order.provider_orders.select_related("profile").first()
        profile = provider_order.profile if (provider_order and provider_order.profile) else None
        if not profile:
            profile = ProviderProfile.objects.filter(is_active=True).first()
            
        if not profile:
            return response.Response({"detail": "لا يوجد مزود خدمة فعال مرتبط."}, status=status.HTTP_400_BAD_REQUEST)

        if order.api_order_id:
            identifiers = [str(order.api_order_id)]
            is_uuid = False
        elif order.api_order_uuid:
            identifiers = [str(order.api_order_uuid)]
            is_uuid = True
        else:
            identifiers = []
            is_uuid = False

        data_list = ProviderManager.check_orders(
            profile,
            identifiers,
            is_uuid=is_uuid
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
