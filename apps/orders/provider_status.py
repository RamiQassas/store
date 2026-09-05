from django.db import transaction

from apps.orders.models import Order, OrderLog
from apps.wallets.services import credit_wallet, get_or_create_wallet


TERMINAL_PROVIDER_STATUSES = {"accept", "reject"}


import json
import ast

def extract_clean_text(val):
    if not val:
        return ""
    if isinstance(val, str):
        val = val.strip()
        if (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
            try:
                parsed = json.loads(val)
                return extract_clean_text(parsed)
            except Exception:
                try:
                    parsed = ast.literal_eval(val)
                    return extract_clean_text(parsed)
                except Exception:
                    pass
        return val
    elif isinstance(val, dict):
        for priority_key in ("replay", "msg", "message", "note", "notes", "reason", "error", "text", "details"):
            if priority_key in val and val[priority_key]:
                return extract_clean_text(val[priority_key])
        parts = []
        for k, v in val.items():
            if k in ("status", "order_id", "id", "trans_id", "transaction_id", "code_status"):
                continue
            cleaned = extract_clean_text(v)
            if cleaned:
                parts.append(cleaned)
        return " | ".join(parts) if parts else ""
    elif isinstance(val, (list, tuple, set)):
        parts = [extract_clean_text(x) for x in val if x not in (None, "")]
        seen = set()
        deduped = []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                deduped.append(p)
        return " | ".join(deduped)
    return str(val).strip()


def cleanup_fulfillment_data(fulfillment, delivery_values=None):
    if not isinstance(fulfillment, dict):
        return {}

    # Remove internal technical keys
    fulfillment.pop("api_order_id", None)
    fulfillment.pop("ملاحظات وبيانات التنفيذ", None)

    # Clean and normalize cancellation reason
    cancel_reason = extract_clean_text(fulfillment.get("سبب الإلغاء من السيرفر"))
    if cancel_reason:
        fulfillment["سبب الإلغاء من السيرفر"] = cancel_reason
        if extract_clean_text(fulfillment.get("رد السيرفر")) == cancel_reason:
            fulfillment.pop("رد السيرفر", None)
    else:
        fulfillment.pop("سبب الإلغاء من السيرفر", None)

    # Clean and normalize delivery codes
    delivery_str = extract_clean_text(fulfillment.get("بيانات التسليم والأكواد"))
    if delivery_str:
        fulfillment["بيانات التسليم والأكواد"] = delivery_str
    else:
        fulfillment.pop("بيانات التسليم والأكواد", None)

    # Clean server response and eliminate duplicates
    if "رد السيرفر" in fulfillment:
        cleaned_msg = extract_clean_text(fulfillment["رد السيرفر"])
        deliv_list = delivery_values or []
        cur_delivery = fulfillment.get("بيانات التسليم والأكواد", "")
        if not cleaned_msg:
            fulfillment.pop("رد السيرفر", None)
        elif cleaned_msg in deliv_list or (cur_delivery and (cleaned_msg == cur_delivery or cleaned_msg in cur_delivery)):
            # Redundant with delivery codes/phone
            fulfillment.pop("رد السيرفر", None)
        elif cancel_reason and (cleaned_msg == cancel_reason or cleaned_msg in cancel_reason):
            # Redundant with cancellation reason
            fulfillment.pop("رد السيرفر", None)
        else:
            fulfillment["رد السيرفر"] = cleaned_msg

    # General deduplication of identical values across keys
    seen_values = set()
    priority = ["بيانات التسليم والأكواد", "كود التفعيل / البطاقة", "رقم الهاتف المستلم", "سبب الإلغاء من السيرفر", "رد السيرفر", "رقم العملية (Transaction ID)"]
    for p_key in priority:
        if p_key in fulfillment:
            val = fulfillment[p_key]
            if val in seen_values:
                fulfillment.pop(p_key, None)
            else:
                seen_values.add(val)

    for k in list(fulfillment.keys()):
        if k in ("api_provider", "api_status", "api_last_response", "api_refunded"):
            continue
        val = extract_clean_text(fulfillment[k])
        if not val or val in seen_values:
            fulfillment.pop(k, None)
        else:
            fulfillment[k] = val
            seen_values.add(val)

    return fulfillment


def extract_delivery_values(payload):
    values = []
    keys = ("card", "code", "serial", "pin", "key", "keys", "cards", "serial_number")

    def collect(obj, inside_key=False):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in keys or inside_key:
                    collect(value, inside_key=True)
                elif isinstance(value, (dict, list)):
                    collect(value, inside_key=False)
        elif isinstance(obj, list):
            for item in obj:
                collect(item, inside_key=inside_key)
        elif obj not in (None, ""):
            if inside_key:
                clean_val = extract_clean_text(obj)
                if clean_val:
                    values.append(clean_val)

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
            fulfillment["رقم الهاتف المستلم"] = extract_clean_text(phone)

        # Extract activation code / PIN / SMS
        code_val = (
            raw_response.get("code") or inner.get("code") or
            raw_response.get("pin") or inner.get("pin") or
            raw_response.get("sms") or inner.get("sms")
        )
        if code_val and isinstance(code_val, (str, int)):
            fulfillment["كود التفعيل / البطاقة"] = extract_clean_text(code_val)

        # Extract note / message / reply from provider
        provider_msg = (
            inner.get("replay_api") or raw_response.get("replay_api") or
            inner.get("replay") or raw_response.get("replay") or
            inner.get("msg") or raw_response.get("msg") or
            inner.get("message") or raw_response.get("message") or
            inner.get("note") or raw_response.get("note") or
            inner.get("notes") or raw_response.get("notes") or
            inner.get("reason") or raw_response.get("reason") or
            inner.get("error") or raw_response.get("error") or
            inner.get("details") or raw_response.get("details")
        )

        provider_msg_str = extract_clean_text(provider_msg)

        # For phone activation numbers or card pins, if replay contains the number/code:
        if provider_msg_str and (provider_status in status_completed_aliases or provider_status in status_processing_aliases):
            if any(c.isdigit() for c in provider_msg_str) and len(provider_msg_str) < 50:
                if provider_msg_str not in delivery_values:
                    delivery_values.append(provider_msg_str)

        # Extract remote order id
        remote_id = (
            raw_response.get("order_id") or inner.get("order_id") or
            raw_response.get("id") or inner.get("id")
        )
        if remote_id and not locked_order.api_order_id:
            locked_order.api_order_id = str(remote_id)

        if delivery_values:
            fulfillment["بيانات التسليم والأكواد"] = " | ".join(delivery_values)

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

        # Only store server reply if it provides new information not already in delivery codes or cancellation reason
        if provider_msg_str:
            cur_deliv = fulfillment.get("بيانات التسليم والأكواد", "")
            cur_cancel = fulfillment.get("سبب الإلغاء من السيرفر", "")
            if provider_msg_str not in delivery_values and provider_msg_str != cur_deliv and provider_msg_str != cur_cancel:
                fulfillment["رد السيرفر"] = provider_msg_str

        fulfillment["api_status"] = provider_status
        fulfillment["api_last_response"] = raw_response

        # Clean all duplicate / raw keys from fulfillment
        fulfillment = cleanup_fulfillment_data(fulfillment, delivery_values=delivery_values)

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
