import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.payments.models import (
    MTNPayApiLog,
    MTNPayInvoiceRecord,
    MTNPayRefundRecord,
    MTNPayTerminalConfig,
)
from apps.payments.mtn_pay import MTNPayError, MTNPaymentClient

logger = logging.getLogger(__name__)


def _is_staff_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", "") in ("super_admin", "admin", "support")
    )


def _get_or_create_default_terminal(store=None) -> MTNPayTerminalConfig:
    from apps.payments.models import PaymentGatewayIntegration
    from django.utils import timezone

    gw_qs = PaymentGatewayIntegration.all_objects.filter(provider=PaymentGatewayIntegration.Provider.MTN_PAY)
    if store:
        gw = gw_qs.filter(store=store).order_by("-is_active", "-id").first() or gw_qs.filter(store__isnull=True).order_by("-is_active", "-id").first()
    else:
        gw = gw_qs.filter(store__isnull=True).order_by("-is_active", "-id").first() or gw_qs.order_by("-is_active", "-id").first()

    import os
    target_tid = (
        (gw.terminal_id if gw and gw.terminal_id else "")
        or os.environ.get("MTN_PAY_TERMINAL_ID", "")
        or "9001000000064683"
    ).strip()
    target_base_url = (gw.base_url if gw and gw.base_url else "https://cash.mtnsyr.com:9000").strip()
    if target_base_url.rstrip("/") == "https://cash.mtnsyr.com":
        target_base_url = "https://cash.mtnsyr.com:9000"

    term = (
        MTNPayTerminalConfig.objects.filter(terminal_id=target_tid).first()
        or (MTNPayTerminalConfig.objects.filter(store=store).first() if store else MTNPayTerminalConfig.objects.filter(store__isnull=True).first())
        or MTNPayTerminalConfig.objects.first()
    )
    default_settings = {
        "Currency": {"Code": "760", "Brief": "SYP", "Fractional": 100},
        "Limits": {"Minimum": 100, "Maximum": 50000000000},
        "Allowed": {"Payment": True},
        "Description": {
            "Business": "رقميات",
            "Shop": "متجر رقميات",
            "Address": "حلب - الأنصاري الشرقي - جانب حلويات الأفراح",
            "Phone": "+963962685312",
            "UniquePayCode": f"MTN-{target_tid[-6:]}",
        },
    }
    if not term:
        term = MTNPayTerminalConfig.objects.create(
            store=store,
            terminal_id=target_tid,
            serial_number="RAQAMIYAT",
            base_url=target_base_url,
            language="en",
            is_activated=True,
            is_locked=False,
            activated_at=timezone.now(),
            terminal_settings=default_settings,
        )
    else:
        changed = False
        if term.terminal_id == "10000001" and target_tid != "10000001":
            term.terminal_id = target_tid
            changed = True
        if not term.terminal_settings:
            term.terminal_settings = default_settings
            changed = True
        if not term.is_activated and not term.is_locked:
            term.is_activated = True
            term.activated_at = timezone.now()
            changed = True
        if changed:
            term.save()
    return term


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER CHECKOUT & PHONE OTP VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def mtn_invoice_checkout_view(request, invoice_number: int):
    """
    Renders the customer-facing Raqamiyat x Cash Mobile invoice payment page,
    displaying product/deposit summary, USD & SYP pricing, and Phone/QR payment flow.
    """
    invoice = get_object_or_404(MTNPayInvoiceRecord, invoice_number=invoice_number)
    terminal = invoice.terminal

    item_summary = ""
    usd_amount = None
    try:
        if invoice.order:
            names = []
            for item in invoice.order.items.select_related("product", "variant").all()[:4]:
                p_name = item.product.name if item.product else ""
                v_name = item.variant.name if item.variant else ""
                label = f"{p_name} ({v_name})" if (p_name and v_name and v_name != p_name) else (p_name or v_name)
                if label:
                    if item.quantity and item.quantity > 1:
                        label = f"{label} × {item.quantity}"
                    names.append(label)
            item_summary = "، ".join(names) or f"طلب شراء #{invoice.order.number}"
            meta = invoice.order.metadata if isinstance(invoice.order.metadata, dict) else {}
            raw_usd = meta.get("base_usd_amount") or invoice.order.total_amount
            if raw_usd:
                usd_amount = f"{Decimal(str(raw_usd)):,.2f}"
        elif invoice.deposit:
            item_summary = "شحن رصيد محفظة رقميات"
            dep_curr = invoice.deposit.currency.code.upper() if invoice.deposit.currency else "USD"
            if dep_curr == "USD":
                usd_amount = f"{Decimal(str(invoice.deposit.amount)):,.2f}"
    except Exception:
        pass

    return render(
        request,
        "payments/mtn/checkout.html",
        {
            "invoice": invoice,
            "terminal": terminal,
            "description": terminal.description_info,
            "currency": terminal.currency_info,
            "item_summary": item_summary or "دفع فاتورة رقميات",
            "usd_amount": usd_amount,
        },
    )


@login_required
@require_POST
def mtn_phone_initiate_ajax(request, invoice_number: int):
    """
    AJAX endpoint for `pos_web/payment_phone/initiate`.
    Receives customer `phone`, generates `Guid`, and returns `OperationNumber` + `PaySystem`.
    """
    invoice = get_object_or_404(MTNPayInvoiceRecord, invoice_number=invoice_number)
    phone = (request.POST.get("phone") or "").strip()
    if not phone and request.body:
        try:
            body_json = json.loads(request.body.decode("utf-8"))
            phone = str(body_json.get("phone") or "").strip()
        except Exception:
            pass

    client = MTNPaymentClient(invoice.terminal)
    try:
        resp = client.initiate_phone_payment(invoice_number=invoice.invoice_number, customer_phone=phone)
        invoice.refresh_from_db()
        return JsonResponse({
            "status": "ok",
            "message": "تم إرسال رمز التحقق SMS إلى رقم هاتفك بنجاح.",
            "invoice": invoice.invoice_number,
            "operation_number": invoice.operation_number,
            "pay_system": invoice.pay_system,
            "guid": invoice.guid,
            "invoice_status": invoice.status_code,
        })
    except MTNPayError as exc:
        return JsonResponse({
            "status": "error",
            "errno": exc.errno,
            "action": exc.action,
            "message": str(exc),
        }, status=400)


@login_required
@require_POST
def mtn_phone_confirm_ajax(request, invoice_number: int):
    """
    AJAX endpoint for `pos_web/payment_phone/confirm`.
    Receives SMS `code` and completes the MTNPay payment (with automatic `pos_web/invoice/get` recovery on timeout).
    """
    invoice = get_object_or_404(MTNPayInvoiceRecord, invoice_number=invoice_number)
    code = (request.POST.get("code") or "").strip()
    if not code and request.body:
        try:
            body_json = json.loads(request.body.decode("utf-8"))
            code = str(body_json.get("code") or "").strip()
        except Exception:
            pass

    client = MTNPaymentClient(invoice.terminal)
    try:
        updated_inv, resp = client.confirm_phone_payment(
            invoice_number=invoice.invoice_number,
            sms_code=code,
        )
        from django.urls import reverse
        redirect_url = ""
        if updated_inv.order_id:
            redirect_url = f"{reverse('payment_status')}?type=order&id={updated_inv.order_id}&status=paid"
        elif updated_inv.deposit_id:
            redirect_url = f"{reverse('payment_status')}?type=deposit&id={updated_inv.deposit_id}&status=paid"
        return JsonResponse({
            "status": "ok",
            "message": "تم تأكيد الدفع عبر MTNPay بنجاح!",
            "invoice": updated_inv.invoice_number,
            "transaction": updated_inv.transaction_id,
            "abuse_remaining": updated_inv.abuse_remaining,
            "invoice_status": updated_inv.status_code,
            "is_paid": updated_inv.is_paid,
            "redirect_url": redirect_url,
        })
    except MTNPayError as exc:
        invoice.refresh_from_db()
        return JsonResponse({
            "status": "error",
            "errno": exc.errno,
            "action": exc.action,
            "abuse_remaining": invoice.abuse_remaining,
            "message": str(exc),
        }, status=400)


@login_required
def mtn_invoice_status_ajax(request, invoice_number: int):
    """Calls `pos_web/invoice/get` to sync and return the live status of an invoice."""
    invoice = get_object_or_404(MTNPayInvoiceRecord, invoice_number=invoice_number)
    client = MTNPaymentClient(invoice.terminal)
    try:
        updated_inv, _ = client.get_invoice(invoice.invoice_number, transaction_id=invoice.transaction_id or None)
        return JsonResponse({
            "status": "ok",
            "invoice": updated_inv.invoice_number,
            "invoice_status": updated_inv.status_code,
            "is_paid": updated_inv.is_paid,
            "transaction": updated_inv.transaction_id,
        })
    except MTNPayError as exc:
        return JsonResponse({
            "status": "error",
            "errno": exc.errno,
            "message": str(exc),
        }, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN CONTROL PANEL VIEWS (Activation, Settings, Invoices, Refunds, Logs)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def mtn_admin_dashboard_view(request):
    if not _is_staff_or_admin(request.user):
        return redirect("dashboard")

    store = getattr(request, "store", None)
    terminal = _get_or_create_default_terminal(store=store)
    client = MTNPaymentClient(terminal)
    client.ensure_keypair()

    invoices = MTNPayInvoiceRecord.objects.filter(terminal=terminal).order_by("-created_at")[:30]
    refunds = MTNPayRefundRecord.objects.filter(invoice_record__terminal=terminal).order_by("-created_at")[:20]
    logs = MTNPayApiLog.objects.filter(subject_terminal=terminal.terminal_id).order_by("-created_at")[:40]

    return render(
        request,
        "payments/mtn/dashboard.html",
        {
            "terminal": terminal,
            "invoices": invoices,
            "refunds": refunds,
            "logs": logs,
        },
    )


@login_required
@require_POST
def mtn_admin_activate_pos_view(request):
    if not _is_staff_or_admin(request.user):
        return redirect("dashboard")

    store = getattr(request, "store", None)
    terminal = _get_or_create_default_terminal(store=store)

    terminal_id = (request.POST.get("terminal_id") or terminal.terminal_id).strip()
    serial_number = (request.POST.get("serial_number") or terminal.serial_number).strip()
    base_url = (request.POST.get("base_url") or terminal.base_url).strip()
    secret_code = (request.POST.get("secret_code") or "").strip()

    if request.POST.get("reset_lock") == "1":
        terminal.is_locked = False
        terminal.activation_attempts = 0
        terminal.count_abuse = 0
        if (terminal.public_key_b64 or "").startswith("LS0tLS1"):
            from apps.payments.mtn_pay import MTNCryptoEngine
            priv_pem, pub_b64 = MTNCryptoEngine.generate_rsa1024_keypair()
            MTNCryptoEngine.save_private_key_securely(terminal.terminal_id, priv_pem)
            terminal.public_key_b64 = pub_b64
        terminal.save(update_fields=["is_locked", "activation_attempts", "count_abuse", "public_key_b64"])
        messages.success(request, "تمت إعادة ضبط قفل محاولات التفعيل وتجهيز المفتاح العام القياسي. يمكنك الآن إدخال رمز التفعيل الجديد (8 أرقام).")
        return redirect("mtn_admin_dashboard")

    terminal.terminal_id = terminal_id
    terminal.serial_number = serial_number
    if base_url:
        terminal.base_url = base_url
    terminal.save(update_fields=["terminal_id", "serial_number", "base_url"])

    client = MTNPaymentClient(terminal)
    try:
        client.activate_pos(secret_code=secret_code, serial_number=serial_number)
        messages.success(request, f"تم تفعيل نقطة البيع MTN (#{terminal.terminal_id}) وحفظ إعدادات العملة والحدود بنجاح.")
    except MTNPayError as exc:
        messages.error(request, f"فشل تفعيل الطرفية: {exc}")

    return redirect("mtn_admin_dashboard")


@login_required
@require_POST
def mtn_admin_check_status_view(request):
    """
    Safely probes the MTN eMARA API server (`pos_web/invoice/get`) without touching
    `pos_web/pos/activate` or consuming activation attempts.
    """
    if not _is_staff_or_admin(request.user):
        return redirect("dashboard")

    store = getattr(request, "store", None)
    terminal = _get_or_create_default_terminal(store=store)
    client = MTNPaymentClient(terminal)
    client.ensure_keypair()

    try:
        # Query a harmless probe invoice ID to test live connectivity & RSA signature acceptance
        _, resp = client.get_invoice(1)
        messages.success(
            request,
            f"اتصال خادم MTN يعمل بنجاح والتوقيع مقبول! (URL: {terminal.base_url} | Errno: {resp.get('Errno', 0)})",
        )
    except MTNPayError as exc:
        if exc.errno in (404, 40401):
            messages.success(
                request,
                f"اتصال خادم MTN يعمل والتوقيع الرقمي RSA-1024 مقبول من الخادم! (الرد: {exc.errno} الفاتورة التجريبية غير موجودة، وهذا يؤكد نجاح الاتصال والتوقيع). ({terminal.base_url})",
            )
        else:
            messages.warning(
                request,
                f"تم الوصول إلى خادم MTN ({terminal.base_url}) وردّ بالرمز {exc.errno}: {exc}",
            )
    except Exception as exc:
        messages.error(request, f"تعذر الاتصال بخادم MTN ({terminal.base_url}): {exc}")

    return redirect("mtn_admin_dashboard")


@login_required
@require_POST
def mtn_admin_create_invoice_view(request):
    if not _is_staff_or_admin(request.user):
        return redirect("dashboard")

    store = getattr(request, "store", None)
    terminal = _get_or_create_default_terminal(store=store)
    amount_str = (request.POST.get("amount") or "0").strip()
    ttl_str = (request.POST.get("ttl") or "").strip()
    ttl_val = int(ttl_str) if ttl_str.isdigit() else None

    client = MTNPaymentClient(terminal)
    try:
        inv, _ = client.create_invoice(
            major_amount=Decimal(amount_str),
            ttl=ttl_val,
            user=request.user,
        )
        messages.success(request, f"تم إنشاء الفاتورة رقم #{inv.invoice_number} بمبلغ {inv.amount_major} {inv.currency_code} ({inv.amount_minor} وحدة صغرى).")
    except Exception as exc:
        messages.error(request, f"تعذر إنشاء الفاتورة: {exc}")

    return redirect("mtn_admin_dashboard")


@login_required
@require_POST
def mtn_admin_refund_action_view(request):
    if not _is_staff_or_admin(request.user):
        return redirect("dashboard")

    store = getattr(request, "store", None)
    terminal = _get_or_create_default_terminal(store=store)
    client = MTNPaymentClient(terminal)
    action = (request.POST.get("action") or "").strip()

    try:
        if action == "initiate":
            base_inv = int(request.POST.get("base_invoice") or 0)
            ref_rec, _ = client.initiate_refund(base_inv)
            messages.success(request, f"تم بدء الاسترداد للفاتورة #{base_inv} برقم استرداد #{ref_rec.refund_invoice}. يرجى تأكيد الاسترداد.")
        elif action == "confirm":
            base_inv = int(request.POST.get("base_invoice") or 0)
            refund_inv = int(request.POST.get("refund_invoice") or 0)
            ref_rec, _ = client.confirm_refund(base_inv, refund_inv)
            messages.success(request, f"تم تأكيد استرداد الفاتورة #{base_inv} بنجاح (RefundInvoice #{ref_rec.refund_invoice}).")
        elif action == "cancel":
            cancel_id = int(request.POST.get("invoice_cancel_id") or 0)
            client.cancel_refund(cancel_id)
            messages.success(request, f"تم إلغاء فاتورة الاسترداد #{cancel_id} بنجاح.")
    except Exception as exc:
        messages.error(request, f"خطأ في عملية الاسترداد: {exc}")

    return redirect("mtn_admin_dashboard")
