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

    @decorators.action(detail=False, methods=["post"], permission_classes=[], authentication_classes=[])
    def alkasr_webhook(self, request):
        import logging
        from django.db import transaction
        from apps.wallets.services import get_or_create_wallet
        
        logger = logging.getLogger(__name__)
        logger.info(f"Alkasr webhook payload: {request.data}")
        
        data = request.data or {}
        
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
        
        old_status = order.status
        
        # Extract keys/codes from payload
        keys_delivered = []
        possible_key_fields = ["card", "code", "serial", "pin", "key", "keys", "cards", "serial_number"]
        for field in possible_key_fields:
            val = data.get(field)
            if val:
                if isinstance(val, list):
                    keys_delivered.extend([str(x) for x in val])
                else:
                    keys_delivered.append(str(val))
                    
        # Check nested "data" dict
        if isinstance(data.get("data"), dict):
            nested_data = data["data"]
            for field in possible_key_fields:
                val = nested_data.get(field)
                if val:
                    if isinstance(val, list):
                        keys_delivered.extend([str(x) for x in val])
                    else:
                        keys_delivered.append(str(val))

        if api_status == "accept":
            order.status = Order.Status.COMPLETED
            note = "تم تنفيذ الطلب بنجاح وتغيير حالته إلى مكتمل عبر الـ Webhook."
            if keys_delivered:
                note += f" | الأكواد المستلمة: {', '.join(keys_delivered)}"
        elif api_status == "reject":
            order.status = Order.Status.CANCELLED
            note = "تم رفض الطلب من المزود، تم إلغاء الطلب وإرجاع المبلغ للمحفظة عبر الـ Webhook."
        elif api_status == "wait":
            order.status = Order.Status.PROCESSING
            note = "حالة الطلب قيد الانتظار في الـ API."
        else:
            note = f"تحديث الحالة من المزود: {api_status}"
            
        if order.status != old_status or keys_delivered:
            with transaction.atomic():
                # If changing to cancelled, refund customer
                if order.status == Order.Status.CANCELLED and old_status != Order.Status.CANCELLED:
                    wallet = get_or_create_wallet(order.customer)
                    refund_amount = order.total_amount
                    if wallet.currency.code != "USD":
                        refund_amount = wallet.currency.from_base(order.total_amount)
                        
                    from apps.wallets.services import credit_wallet
                    credit_wallet(
                        wallet_id=wallet.id,
                        amount=refund_amount,
                        reference=f"refund:{order.id}",
                        description=f"Refund for cancelled order {order.number}",
                        created_by=None,
                        source="system",
                        reason="فشل تنفيذ الطلب من المزود تلقائياً"
                    )
                    
                if keys_delivered:
                    order.fulfillment_data["الرموز المسلمة (API)"] = ", ".join(keys_delivered)
                order.fulfillment_data["api_webhook_last_status"] = api_status
                order.fulfillment_data["api_webhook_response"] = data
                order.save(update_fields=["status", "fulfillment_data", "updated_at"])
                
                OrderLog.objects.create(
                    order=order,
                    status=order.status,
                    note=note,
                    created_by=None
                )
                
        return response.Response({"status": "success", "message": "Order status updated"})

    @decorators.action(detail=True, methods=["post"])
    def sync_alkasr_status(self, request, pk=None):
        from django.db import transaction
        from apps.wallets.services import get_or_create_wallet
        from apps.orders.alkasr_api import check_alkasr_orders
        
        if not request.user.is_staff:
            return response.Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
            
        order = self.get_object()
        if not order.api_order_uuid and not order.api_order_id:
            return response.Response({"detail": "هذا الطلب غير مربوط بـ API خارجي."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Determine provider
        provider = "alkasr"
        first_item = order.items.first()
        if first_item and first_item.variant and first_item.variant.product:
            provider = first_item.variant.product.api_provider or "alkasr"
            
        if provider == "alkasr":
            # Check by UUID if we have it, else by order ID
            if order.api_order_uuid:
                res = check_alkasr_orders(str(order.api_order_uuid), is_uuid=True, store=order.store)
            else:
                res = check_alkasr_orders([order.api_order_id], is_uuid=False, store=order.store)
        else:
            # Alternate API provider placeholder status check
            res = {
                "status": "OK",
                "data": [{
                    "status": "accept" if order.status == Order.Status.COMPLETED else "wait",
                    "order_id": order.api_order_id
                }]
            }
            
        if res.get("status") == "OK" and isinstance(res.get("data"), list) and len(res["data"]) > 0:
            order_data = res["data"][0]
            api_status = order_data.get("status")
            api_order_id = order_data.get("order_id")
            
            old_status = order.status
            updated = False
            note = f"تم فحص الحالة يدوياً من المزود. الحالة الخارجية: {api_status}"
            
            # Extract keys/codes from order_data
            keys_delivered = []
            possible_key_fields = ["card", "code", "serial", "pin", "key", "keys", "cards", "serial_number"]
            for field in possible_key_fields:
                val = order_data.get(field)
                if val:
                    if isinstance(val, list):
                        keys_delivered.extend([str(x) for x in val])
                    else:
                        keys_delivered.append(str(val))

            if api_status == "accept":
                order.status = Order.Status.COMPLETED
                updated = True
                if keys_delivered:
                    note += f" | الأكواد المستلمة: {', '.join(keys_delivered)}"
            elif api_status == "reject":
                order.status = Order.Status.CANCELLED
                updated = True
            elif api_status == "wait":
                order.status = Order.Status.PROCESSING
                updated = True
                
            if (updated and order.status != old_status) or keys_delivered:
                with transaction.atomic():
                    # Refund logic
                    if order.status == Order.Status.CANCELLED and old_status != Order.Status.CANCELLED:
                        wallet = get_or_create_wallet(order.customer)
                        refund_amount = order.total_amount
                        if wallet.currency.code != "USD":
                            refund_amount = wallet.currency.from_base(order.total_amount)
                            
                        from apps.wallets.services import credit_wallet
                        credit_wallet(
                            wallet_id=wallet.id,
                            amount=refund_amount,
                            reference=f"refund:{order.id}",
                            description=f"Refund for cancelled order {order.number}",
                            created_by=request.user,
                            source="system",
                            reason="تم إلغاء الطلب واسترداد الرصيد يدوياً بعد فحص حالة الـ API"
                        )
                        
                    if api_order_id and not order.api_order_id:
                        order.api_order_id = api_order_id
                        
                    if keys_delivered:
                        order.fulfillment_data["الرموز المسلمة (API)"] = ", ".join(keys_delivered)
                    order.fulfillment_data["api_status"] = api_status
                    order.fulfillment_data["api_last_checked_response"] = order_data
                    order.save(update_fields=["status", "api_order_id", "fulfillment_data", "updated_at"])
                    
                    OrderLog.objects.create(
                        order=order,
                        status=order.status,
                        note=note,
                        created_by=request.user
                    )
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
