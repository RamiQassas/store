from django.db import transaction

from apps.orders.models import Order, OrderLog
from apps.wallets.services import credit_wallet, get_or_create_wallet


TERMINAL_PROVIDER_STATUSES = {"accept", "reject"}


def extract_delivery_values(payload):
    values = []
    keys = ("card", "code", "serial", "pin", "key", "keys", "cards", "serial_number", "replay_api")

    def collect(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in keys:
                    collect(value)
                elif isinstance(value, (dict, list)):
                    collect(value)
        elif isinstance(obj, list):
            for item in obj:
                collect(item)
        elif obj not in (None, ""):
            values.append(str(obj))

    collect(payload or {})
    return values


def apply_provider_status(order, provider_status, raw_response=None, actor=None, note_prefix="API"):
    provider_status = (provider_status or "").strip().lower()
    raw_response = raw_response or {}
    delivery_values = extract_delivery_values(raw_response)

    status_completed_aliases = {"accept", "accepted", "completed", "complete", "success", "successful", "done", "approved"}
    status_cancelled_aliases = {"reject", "rejected", "cancel", "cancelled", "canceled", "failed", "error"}
    status_processing_aliases = {"wait", "waiting", "pending", "processing", "in_progress"}

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        old_status = locked_order.status
        fulfillment = dict(locked_order.fulfillment_data or {})

        # Extract transaction ID
        trans_id = raw_response.get("trans_id") or raw_response.get("transaction_id") or raw_response.get("transId") or raw_response.get("reference")
        if trans_id:
            fulfillment["رقم العملية (Transaction ID)"] = str(trans_id)

        # Extract phone number (e.g. for WhatsApp activation numbers)
        phone = raw_response.get("phone") or raw_response.get("number") or raw_response.get("phone_number")
        if phone:
            fulfillment["رقم الهاتف المستلم"] = str(phone)

        # Extract activation code / PIN / SMS
        code_val = raw_response.get("code") or raw_response.get("pin") or raw_response.get("sms")
        if code_val and isinstance(code_val, (str, int)):
            fulfillment["كود التفعيل / البطاقة"] = str(code_val)

        # Extract note / message / reply
        provider_msg = raw_response.get("replay_api") or raw_response.get("msg") or raw_response.get("message") or raw_response.get("note") or raw_response.get("reason") or raw_response.get("details")
        if provider_msg:
            fulfillment["ملاحظات وبيانات التنفيذ"] = str(provider_msg)

        # Extract remote order id
        remote_id = raw_response.get("order_id") or raw_response.get("id")
        if remote_id and not locked_order.api_order_id:
            locked_order.api_order_id = str(remote_id)

        if provider_status in status_completed_aliases:
            locked_order.status = Order.Status.COMPLETED
            note = f"{note_prefix}: تم إكمال وتنفيذ الطلب بنجاح."
        elif provider_status in status_cancelled_aliases:
            locked_order.status = Order.Status.CANCELLED
            note = f"{note_prefix}: تم إلغاء الطلب."
            if provider_msg:
                note += f" (السبب: {provider_msg})"
        elif provider_status in status_processing_aliases:
            locked_order.status = Order.Status.PROCESSING
            note = f"{note_prefix}: الطلب قيد المعالجة والتنفيذ."
        else:
            note = f"{note_prefix}: حالة الطلب: {provider_status or '-'}."

        if delivery_values:
            fulfillment["بيانات التسليم والأكواد"] = " | ".join(delivery_values)

        fulfillment["api_status"] = provider_status
        fulfillment["api_last_response"] = raw_response

        refunded = bool(fulfillment.get("api_refunded"))
        if provider_status in status_cancelled_aliases and not refunded:
            wallet = get_or_create_wallet(locked_order.customer)
            refund_amount = locked_order.total_amount
            if wallet.currency and wallet.currency.code != "USD":
                refund_amount = wallet.currency.from_base(locked_order.total_amount)
            credit_wallet(
                wallet_id=wallet.id,
                amount=refund_amount,
                reference=f"refund:{locked_order.id}",
                description=f"Refund for cancelled order {locked_order.number}",
                created_by=actor,
                source="provider_api",
                reason="إلغاء الطلب آلياً",
                metadata={"provider_status": provider_status},
            )
            fulfillment["api_refunded"] = True
            note += " وتم استرداد المبلغ إلى محفظة العميل."

        changed = old_status != locked_order.status or delivery_values or fulfillment != (locked_order.fulfillment_data or {})
        if changed:
            locked_order.fulfillment_data = fulfillment
            locked_order.save(update_fields=["status", "fulfillment_data", "updated_at"])
            OrderLog.objects.create(
                order=locked_order,
                status=locked_order.status,
                note=note,
                created_by=actor,
            )

            # Send Notification to Customer on Status Change
            if old_status != locked_order.status:
                try:
                    from apps.notifications.services import notify_user
                    if locked_order.status == Order.Status.COMPLETED:
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم اكتمال طلبك #{locked_order.number} بنجاح 🎉",
                            body=f"تم شحن وتنفيذ طلبك #{locked_order.number} بنجاح. يمكنك مراجعة تفاصيل التنفيذ من صفحة الطلب.",
                            action_url=f"/orders/{locked_order.id}/",
                            category="orders"
                        )
                    elif locked_order.status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
                        reason_txt = f" (السبب: {provider_msg})" if provider_msg else ""
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم إلغاء طلبك #{locked_order.number} وتمت استعادة الرصيد ⚠️",
                            body=f"تم إلغاء الطلب #{locked_order.number}{reason_txt} وتمت إعادة كامل المبلغ إلى محفظتك.",
                            action_url=f"/orders/{locked_order.id}/",
                            category="orders"
                        )
                except Exception:
                    pass

        return locked_order
