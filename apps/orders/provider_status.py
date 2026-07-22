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

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        old_status = locked_order.status
        fulfillment = dict(locked_order.fulfillment_data or {})

        if provider_status == "accept":
            locked_order.status = Order.Status.COMPLETED
            note = f"{note_prefix}: تم قبول الطلب من المزود وتحديثه إلى مكتمل."
        elif provider_status == "reject":
            locked_order.status = Order.Status.CANCELLED
            note = f"{note_prefix}: تم رفض الطلب من المزود وإلغاء الطلب."
        elif provider_status == "wait":
            locked_order.status = Order.Status.PROCESSING
            note = f"{note_prefix}: الطلب ما زال قيد الانتظار لدى المزود."
        else:
            note = f"{note_prefix}: حالة غير معروفة من المزود: {provider_status or '-'}."

        if delivery_values:
            fulfillment["الرموز المسلمة من المزود"] = " | ".join(delivery_values)

        fulfillment["api_status"] = provider_status
        fulfillment["api_last_response"] = raw_response

        refunded = bool(fulfillment.get("api_refunded"))
        if provider_status == "reject" and not refunded:
            wallet = get_or_create_wallet(locked_order.customer)
            refund_amount = locked_order.total_amount
            if wallet.currency and wallet.currency.code != "USD":
                refund_amount = wallet.currency.from_base(locked_order.total_amount)
            credit_wallet(
                wallet_id=wallet.id,
                amount=refund_amount,
                reference=f"refund:{locked_order.id}",
                description=f"Refund for rejected API order {locked_order.number}",
                created_by=actor,
                source="provider_api",
                reason="رفض المزود تنفيذ الطلب",
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

        return locked_order
