from django.db import transaction

from apps.orders.models import Order, OrderLog
from apps.wallets.services import credit_wallet, get_or_create_wallet


TERMINAL_PROVIDER_STATUSES = {"accept", "reject"}


import json
import ast
import re

ERROR_KEYWORDS = [
    "blocked", "محظور", "error", "خطأ", "invalid", "غير صحيح", 
    "not found", "غير موجود", "unavailable", "غير متوفر", 
    "insufficient", "غير كاف", "maintenance", "صيانة", "deleted", "محذوف",
    "fail", "فشل", "فاشل", "refuse", "مرفوض", "cancel", "ملغي", "ملغى", "مسترد",
    "rejected", "unsuccessful"
]


def parse_server_response_details(val):
    """
    Parses complex server responses (like game topups, SoulStar, Alkasr)
    extracting image/avatar URLs, player names, package info, delivery codes,
    and returns a clean structured dict for user display and notification.
    """
    if not val:
        return {
            "clean_text": "",
            "image_url": None,
            "status_msg": None,
            "account_name": None,
            "package_info": None,
            "reason": None,
            "codes": [],
            "raw_clean": "",
        }

    raw_str = str(val).strip()

    # 1. Extract Image / Avatar URLs (e.g. https://.../Avatar/....gif or .png/.jpg/.jpeg/.webp)
    image_url = None
    img_pattern = r'(https?://[^\s\'"<>]+(?:Avatar[^\s\'"<>]*|\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s\'"<>]*)?))'
    img_match = re.search(img_pattern, raw_str, re.IGNORECASE)
    if img_match:
        image_url = img_match.group(1).rstrip('/;,')
        raw_str = raw_str.replace(img_match.group(0), "").strip()

    raw_str = re.sub(r'[\s/\|\-]+$', '', raw_str).strip()
    raw_str = re.sub(r'^[\s/\|\-]+', '', raw_str).strip()

    # 2. Split lines or segments by \n, /, or |
    raw_lines = [line.strip() for line in re.split(r'[\r\n]+', raw_str) if line.strip()]
    segments = []
    for line in raw_lines:
        parts = [p.strip() for p in re.split(r'\s+[/|]\s+', line) if p.strip()]
        segments.extend(parts)

    status_msg = None
    account_name = None
    package_info = None
    reason_parts = []
    codes = []
    cleaned_parts = []

    for seg in segments:
        seg_clean = re.sub(r'[\s/\|\-]+$', '', seg).strip()
        if not seg_clean:
            continue

        seg_lower = seg_clean.lower()

        # Ignore technical json tokens or IDs
        if seg_clean.startswith("{") or seg_clean.startswith("[") or "trans_id" in seg_lower or "order_id" in seg_lower:
            continue

        # Check for error/rejection
        if any(ek in seg_lower for ek in ERROR_KEYWORDS):
            reason_parts.append(seg_clean)
            continue

        # Check for success status phrases
        if any(s in seg_clean for s in ["عملية التحويل تمت بنجاح", "تم الشحن بنجاح", "تم التنفيذ", "تمت العملية بنجاح", "نجاح", "Success", "Completed", "Done"]):
            status_msg = seg_clean
        # Check for package info
        elif any(k in seg_clean for k in ["*", "سول ستار", "SoulStar", "مجوهرات", "شدات", "كوينز", "جوهرة", "ماسة", "Diamonds", "Coins", "UC"]):
            package_info = seg_clean
        # Check if code / pin / serial
        elif re.match(r'^[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+$', seg_clean):
            codes.append(seg_clean)
        else:
            if not account_name and len(seg_clean) < 60 and not seg_clean.isdigit():
                account_name = seg_clean
            else:
                cleaned_parts.append(seg_clean)

    formatted_lines = []
    if status_msg:
        formatted_lines.append(f"• العملية: {status_msg}")
    if account_name:
        formatted_lines.append(f"• المستلم / الحساب: {account_name}")
    if package_info:
        formatted_lines.append(f"• الباقة: {package_info}")
    if reason_parts:
        formatted_lines.append(f"• سبب الإلغاء: {' / '.join(reason_parts)}")
    for cp in cleaned_parts:
        formatted_lines.append(f"• {cp}")
    if codes:
        formatted_lines.append(f"• بيانات التسليم: {' | '.join(codes)}")

    clean_text = "\n".join(formatted_lines) if formatted_lines else raw_str

    return {
        "clean_text": clean_text,
        "image_url": image_url,
        "status_msg": status_msg,
        "account_name": account_name,
        "package_info": package_info,
        "reason": " / ".join(reason_parts) if reason_parts else None,
        "codes": codes,
        "raw_clean": raw_str
    }


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
    priority = [
        "بيانات التسليم والأكواد",
        "كود التفعيل / البطاقة",
        "رقم الهاتف المستلم",
        "سبب الإلغاء من السيرفر",
        "رد السيرفر",
        "صورة الحساب / الأفاتار",
        "رقم العملية (Transaction ID)",
    ]
    for p_key in priority:
        if p_key in fulfillment:
            val = fulfillment[p_key]
            if val in seen_values:
                fulfillment.pop(p_key, None)
            else:
                seen_values.add(val)

    for k in list(fulfillment.keys()):
        if k in ("api_provider", "api_status", "api_last_response", "api_refunded", "image_url"):
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
    provider_status = str(provider_status or "").strip().lower()
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

    status_completed_aliases = {
        "accept", "accepted", "completed", "complete", "success", "successful",
        "done", "approved", "1", 1, "تم الشحن", "مكتمل", "تم التنفيذ"
    }
    status_cancelled_aliases = {
        "reject", "rejected", "cancel", "cancelled", "canceled", "failed", "fail",
        "failure", "refused", "refuse", "declined", "decline", "refunded", "refund",
        "error", "err", "unsuccessful", "invalid", "مرفوض", "ملغي", "ملغى", "فشل",
        "فاشل", "تم الرفض", "تم الإلغاء", "مسترد", "2", 2, "3", 3, "-1", -1, "0", 0
    }
    status_processing_aliases = {
        "wait", "waiting", "pending", "processing", "in_progress", "قيد الانتظار", "قيد المعالجة"
    }

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
        if code_val and isinstance(code_val, (str, int)) and not isinstance(code_val, bool):
            # Only treat code as delivery code if not an HTTP/API error code
            code_int = None
            try:
                code_int = int(code_val)
            except Exception:
                pass
            if code_int is None or (code_int != 200 and code_int > 1000):
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

        # Parse complex provider replay (e.g. SoulStar, avatar URLs, player names)
        parsed_res = parse_server_response_details(provider_msg_str or "")
        extracted_avatar = parsed_res.get("image_url")
        if extracted_avatar:
            fulfillment["صورة الحساب / الأفاتار"] = extracted_avatar
            fulfillment["image_url"] = extracted_avatar

        if parsed_res.get("status_msg"):
            fulfillment["حالة العملية"] = parsed_res["status_msg"]
        if parsed_res.get("account_name"):
            fulfillment["اسم الحساب المستلم"] = parsed_res["account_name"]
        if parsed_res.get("package_info"):
            fulfillment["الباقة المنفذة"] = parsed_res["package_info"]

        # For phone activation numbers or card pins, if replay contains the number/code:
        if provider_msg_str and (provider_status in status_completed_aliases or provider_status in status_processing_aliases):
            if any(c.isdigit() for c in provider_msg_str) and len(provider_msg_str) < 50 and not extracted_avatar:
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

        # Detect error/cancellation conditions from status, codes, or messages
        has_provider_error = bool(
            raw_response.get("error") or
            inner.get("error") or
            (isinstance(raw_response.get("code"), int) and raw_response.get("code") not in (0, 200) and raw_response.get("code") < 600) or
            (isinstance(inner.get("code"), int) and inner.get("code") not in (0, 200) and inner.get("code") < 600)
        )
        
        is_cancelled = (
            provider_status in status_cancelled_aliases or
            has_provider_error or
            bool(parsed_res.get("reason"))
        )
        is_completed = (
            not is_cancelled and 
            (provider_status in status_completed_aliases or bool(parsed_res.get("status_msg") and "نجاح" in parsed_res.get("status_msg")))
        )

        clean_server_reply = parsed_res.get("clean_text") or parsed_res.get("raw_clean") or provider_msg_str

        if is_completed:
            locked_order.status = Order.Status.COMPLETED
            note = f"{note_prefix}: تم إكمال وتنفيذ الطلب بنجاح."
            if clean_server_reply:
                note += f" (رد السيرفر: {clean_server_reply})"
        elif is_cancelled:
            locked_order.status = Order.Status.CANCELLED
            note = f"{note_prefix}: تم إلغاء الطلب."
            cancel_reason_str = parsed_res.get("reason") or provider_msg_str or "تم رفض الطلب من قبل المزود"
            fulfillment["سبب الإلغاء من السيرفر"] = cancel_reason_str
            note += f" (سبب الإلغاء من السيرفر: {cancel_reason_str})"
        elif provider_status in status_processing_aliases:
            locked_order.status = Order.Status.PROCESSING
            note = f"{note_prefix}: الطلب قيد المعالجة والتنفيذ."
            if clean_server_reply:
                note += f" (رد السيرفر: {clean_server_reply})"
        else:
            note = f"{note_prefix}: حالة الطلب: {provider_status or '-'}."
            if clean_server_reply:
                note += f" (رد السيرفر: {clean_server_reply})"

        # Store server reply if useful
        if clean_server_reply:
            cur_deliv = fulfillment.get("بيانات التسليم والأكواد", "")
            cur_cancel = fulfillment.get("سبب الإلغاء من السيرفر", "")
            if clean_server_reply not in delivery_values and clean_server_reply != cur_deliv and clean_server_reply != cur_cancel:
                fulfillment["رد السيرفر"] = clean_server_reply

            # Maintain historical server responses list
            all_replies = list(fulfillment.get("all_server_responses") or [])
            if isinstance(all_replies, str):
                all_replies = [all_replies]
            if clean_server_reply not in all_replies:
                all_replies.append(clean_server_reply)
            fulfillment["all_server_responses"] = all_replies
            if len(all_replies) > 1:
                fulfillment["ردود السيرفر"] = all_replies

        fulfillment["api_status"] = "failed" if is_cancelled else (provider_status or "processing")
        fulfillment["api_last_response"] = raw_response

        # Clean all duplicate / raw keys from fulfillment
        fulfillment = cleanup_fulfillment_data(fulfillment, delivery_values=delivery_values)

        # Automatic Wallet Refund on Cancellation
        refunded = bool(fulfillment.get("api_refunded"))
        if is_cancelled and not refunded:
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
                reason=f"إلغاء الطلب آلياً ({fulfillment.get('سبب الإلغاء من السيرفر') or provider_status})",
                metadata={"provider_status": provider_status, "server_response": clean_server_reply},
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

            # Send Notification to Customer on Status Change or Cancellation
            if old_status != locked_order.status or (is_cancelled and not refunded):
                try:
                    from apps.notifications.services import notify_user
                    if locked_order.status == Order.Status.COMPLETED:
                        lines = [f"تم شحن وتنفيذ طلبك #{locked_order.number} بنجاح 🎉"]
                        if parsed_res.get("status_msg"):
                            lines.append(f"• العملية: {parsed_res['status_msg']}")
                        if parsed_res.get("account_name"):
                            lines.append(f"• اسم الحساب المستلم: {parsed_res['account_name']}")
                        if parsed_res.get("package_info"):
                            lines.append(f"• الباقة: {parsed_res['package_info']}")
                        elif clean_server_reply and clean_server_reply != parsed_res.get("status_msg"):
                            lines.append(f"• تفاصيل الرد: {clean_server_reply}")
                        if delivery_values:
                            lines.append(f"• بيانات التسليم: {' | '.join(delivery_values[:3])}")

                        body_txt = "\n".join(lines)
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم اكتمال طلبك #{locked_order.number} بنجاح 🎉",
                            body=body_txt,
                            action_url=f"/dashboard/orders/{locked_order.id}/",
                            image_url=extracted_avatar,
                            category="orders",
                            priority="high"
                        )
                    elif locked_order.status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
                        cancel_reason_clean = (
                            fulfillment.get("سبب الإلغاء من السيرفر") or
                            parsed_res.get("reason") or
                            clean_server_reply or
                            "تعذر تنفيذ الطلب لدى مزود الخدمة"
                        )
                        wallet = get_or_create_wallet(locked_order.customer)
                        curr_code = wallet.currency.code if (wallet.currency and wallet.currency.code) else "USD"
                        refund_val = locked_order.total_amount
                        if wallet.currency and wallet.currency.code != "USD":
                            refund_val = wallet.currency.from_base(locked_order.total_amount)

                        lines = [
                            f"تم إلغاء طلبك #{locked_order.number} ⚠️",
                            f"• سبب الإلغاء: {cancel_reason_clean}",
                            f"• تمت إعادة كامل المبلغ ({refund_val} {curr_code}) إلى محفظتك تلقائياً."
                        ]
                        body_txt = "\n".join(lines)
                        notify_user(
                            user=locked_order.customer,
                            title=f"تم إلغاء طلبك #{locked_order.number} وتمت استعادة الرصيد ⚠️",
                            body=body_txt,
                            action_url=f"/dashboard/orders/{locked_order.id}/",
                            category="orders",
                            priority="high"
                        )
                except Exception:
                    pass

        return locked_order

