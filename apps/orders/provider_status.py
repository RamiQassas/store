from django.db import transaction

from apps.orders.models import Order, OrderLog
from apps.wallets.services import credit_wallet, get_or_create_wallet


TERMINAL_PROVIDER_STATUSES = {"accept", "reject"}


def extract_delivery_values(payload):
    values = []
    keys = ("card", "code", "serial", "pin", "key", "keys", "cards", "serial_number")

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
            values.append(str(obj).strip())

    collect(payload or {})
    return [v for v in values if v]


def apply_provider_status(order, provider_status, raw_response=None, actor=None, note_prefix="API"):
    provider_status = (provider_status or "").strip().lower()
    raw_response = raw_response or {}

    # Unpack nested dictionary if provider data is wrapped under "raw_response" or "data"
    inner = raw_response
    if isinstance(raw_response, dict):
        if isinstance(raw_response.get("raw_response"), dict):
            inner = raw_response["raw_response"]
        elif isinstance(raw_response.get("data"), dict):
            inner = raw_response["data"]
        elif isinstance(raw_response.get("data"), list) and len(raw_response["data"]) > 0 and isinstance(raw_response["data"][0], dict):
            inner = raw_response["data"][0]

    delivery_values = extract_delivery_values(inner) or extract_delivery_values(raw_response)

    status_completed_aliases = {"accept", "accepted", "completed", "complete", "success", "successful", "done", "approved"}
    status_cancelled_aliases = {"reject", "rejected", "cancel", "cancelled", "canceled", "failed", "error"}
    status_processing_aliases = {"wait", "waiting", "pending", "processing", "in_progress"}

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        old_status = locked_order.status
        fulfillment = dict(locked_order.fulfillment_data or {})

        # Extract transaction ID
        trans_id = (
            raw_response.get("trans_id") or inner.get("trans_id") or
            raw_response.get("transaction_id") or inner.get("transaction_id") or
            raw_response.get("transId") or inner.get("transId") or
            raw_response.get("reference") or inner.get("reference")
        )
        if trans_id:
            fulfillment["رقم العملية (Transaction ID)"] = str(trans_id)

        # Extract phone number (e.g. for WhatsApp activation numbers)
        phone = (
            raw_response.get("phone") or inner.get("phone") or
            raw_response.get("number") or inner.get("number") or
            raw_response.get("phone_number") or inner.get("phone_number")
        )
        if phone:
            fulfillment["رقم الهاتف المستلم"] = str(phone)

        # Extract activation code / PIN / SMS
        code_val = (
            raw_response.get("code") or inner.get("code") or
            raw_response.get("pin") or inner.get("pin") or
            raw_response.get("sms") or inner.get("sms")
        )
        if code_val and isinstance(code_val, (str, int)):
            fulfillment["كود التفعيل / البطاقة"] = str(code_val)

        # Extract note / message / reply from provider
        provider_msg = (
            inner.get("replay_api") or raw_response.get("replay_api") or
            inner.get("msg") or raw_response.get("msg") or
            inner.get("message") or raw_response.get("message") or
            inner.get("note") or raw_response.get("note") or
            inner.get("notes") or raw_response.get("notes") or
            inner.get("reason") or raw_response.get("reason") or
            inner.get("error") or raw_response.get("error") or
            inner.get("details") or raw_response.get("details")
        )

        provider_msg_str = ""
        if provider_msg:
            if isinstance(provider_msg, list):
                provider_msg_str = " | ".join(str(x) for x in provider_msg if x)
                # If completed and items look like codes/cards, also add to delivery values
                if provider_status in status_completed_aliases:
                    for x in provider_msg:
                        s = str(x).strip()
                        if s and s not in delivery_values:
                            delivery_values.append(s)
            elif isinstance(provider_msg, dict):
                import json
                provider_msg_str = json.dumps(provider_msg, ensure_ascii=False)
            else:
                provider_msg_str = str(provider_msg).strip()

        if provider_msg_str:
            fulfillment["رد السيرفر"] = provider_msg_str
            fulfillment["ملاحظات وبيانات التنفيذ"] = provider_msg_str

        # Extract remote order id
        remote_id = (
            raw_response.get("order_id") or inner.get("order_id") or
            raw_response.get("id") or inner.get("id")
        )
        if remote_id and not locked_order.api_order_id:
            locked_order.api_order_id = str(remote_id)

        if provider_status in status_completed_aliases:
            locked_order.status = Order.Status.COMPLETED
            note = f"{note_prefix}: تم إكمال وتنفيذ الطلب بنجاح."
            if provider_msg_str:
                note += f" (رد السيرفر: {provider_msg_str})"
        elif provider_status in status_cancelled_aliases:
            locked_order.status = Order.Status.CANCELLED
            note = f"{note_prefix}: تم إلغاء الطلب."
            if provider_msg_str:
                fulfillment["سبب الإلغاء من السيرفر"] = provider_msg_str
                note += f" (سبب الإلغاء من السيرفر: {provider_msg_str})"
        elif provider_status in status_processing_aliases:
            locked_order.status = Order.Status.PROCESSING
            note = f"{note_prefix}: الطلب قيد المعالجة والتنفيذ."
            if provider_msg_str:
                note += f" (رد السيرفر: {provider_msg_str})"
        else:
            note = f"{note_prefix}: حالة الطلب: {provider_status or '-'}."
            if provider_msg_str:
                note += f" (رد السيرفر: {provider_msg_str})"

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
                reason=f"إلغاء الطلب آلياً ({provider_msg_str or provider_status})",
                metadata={"provider_status": provider_status, "server_response": provider_msg_str},
            )
            fulfillment["api_refunded"] = True
            note += " وتم استرداد المبلغ إلى محفظة العميل تلقائياً."

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
                        body_txt = f"تم شحن وتنفيذ طلبك #{locked_order.number} بنجاح."
                        if provider_msg_str:
                            body_txt += f"\nرد السيرفر: {provider_msg_str}"
                        if delivery_values:
                            body_txt += f"\nبيانات التسليم: {' | '.join(delivery_values[:3])}"
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم اكتمال طلبك #{locked_order.number} بنجاح 🎉",
                            body=body_txt,
                            action_url=f"/dashboard/orders/{locked_order.id}/",
                            category="orders"
                        )
                    elif locked_order.status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
                        reason_txt = f"\nسبب الإلغاء من السيرفر: {provider_msg_str}" if provider_msg_str else ""
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم إلغاء طلبك #{locked_order.number} وتمت استعادة الرصيد ⚠️",
                            body=f"تم إلغاء الطلب #{locked_order.number}.{reason_txt}\nتمت إعادة كامل المبلغ إلى محفظتك تلقائياً.",
                            action_url=f"/dashboard/orders/{locked_order.id}/",
                            category="orders"
                        )
                except Exception:
                    pass

        return locked_order
