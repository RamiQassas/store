"""
ShamCash Admin Management & Auditor Compliance Portal Views
Fulfills:
- Full administrative management of ShamCash gateway.
- Dedicated auditor portal for ShamCash team inspection (Articles 3, 6, 8, 9, 11, 14, 15).
- 5-Year Log Retention & Compliance Trail.
- End-of-Day / Periodic Reconciliation (Section 11).
- Creation and management of ShamCash Auditor credentials.
"""

import json
import logging
from decimal import Decimal
from typing import Any, Dict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import ActivityLog
from apps.common.tenant_utils import bypass_tenant_filter
from apps.orders.models import Order
from apps.payments.gateways import PaymentGatewayError, ShamCashGateway
from apps.payments.models import (
    DepositRequest,
    PaymentGatewayIntegration,
    PaymentMethod,
    ShamCashApiLog,
    ShamCashBillRecord,
    ShamCashComplianceProfile,
    ShamCashReconciliationBatch,
    ShamCashRefundRecord,
    ShamCashWebhookLog,
)
from apps.payments.shamcash import ShamCashClient, ShamCashError

User = get_user_model()
logger = logging.getLogger(__name__)


def _is_admin_or_staff(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", None) in ("super_admin", "admin", "finance")
    )


def _is_shamcash_auditor_or_admin(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or getattr(user, "is_shamcash_auditor", False)
        or getattr(user, "role", None) in ("super_admin", "admin", "finance", "shamcash_auditor")
    )


def _get_or_create_compliance_profile():
    profile = ShamCashComplianceProfile.objects.first()
    if not profile:
        profile = ShamCashComplianceProfile.objects.create()
    return profile


# ══════════════════════════════════════════════════════════════════════════════
# 1. SHAMCASH GATEWAY DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_dashboard_view(request):
    """Admin dashboard overview for ShamCash E-Payment gateway."""
    if not _is_admin_or_staff(request.user):
        messages.error(request, "غير مصرح لك بالوصول إلى هذه اللوحة.")
        return redirect("dashboard")

    integration = PaymentGatewayIntegration.all_objects.filter(
        provider=PaymentGatewayIntegration.Provider.SHAM_CASH
    ).first()

    # Aggregate metrics
    bills_qs = ShamCashBillRecord.objects.all()
    total_bills = bills_qs.count()
    paid_bills_count = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID).count()
    expired_bills_count = bills_qs.filter(status_id=ShamCashClient.STATUS_EXPIRED).count()
    refunded_bills_count = bills_qs.filter(status_id__in=(ShamCashClient.STATUS_REFUNDED, ShamCashClient.STATUS_PARTLY_REFUNDED)).count()

    total_usd_volume = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID, currency_id=ShamCashClient.CURRENCY_USD).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total_syp_volume = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID, currency_id=ShamCashClient.CURRENCY_SYP).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total_refunded_amount = bills_qs.aggregate(s=Sum("total_refunded_amount"))["s"] or Decimal("0.00")

    success_rate = (paid_bills_count / total_bills * 100) if total_bills > 0 else 0.0

    recent_bills = bills_qs.order_by("-created_at")[:10]
    recent_webhooks = ShamCashWebhookLog.objects.order_by("-created_at")[:10]
    recent_api_logs = ShamCashApiLog.objects.order_by("-created_at")[:8]
    compliance_profile = _get_or_create_compliance_profile()

    # Check auditor accounts
    auditor_users = User.objects.filter(Q(role="shamcash_auditor") | Q(email__icontains="shamcash"))

    context = {
        "integration": integration,
        "total_bills": total_bills,
        "paid_bills_count": paid_bills_count,
        "expired_bills_count": expired_bills_count,
        "refunded_bills_count": refunded_bills_count,
        "total_usd_volume": total_usd_volume,
        "total_syp_volume": total_syp_volume,
        "total_refunded_amount": total_refunded_amount,
        "success_rate": round(success_rate, 1),
        "recent_bills": recent_bills,
        "recent_webhooks": recent_webhooks,
        "recent_api_logs": recent_api_logs,
        "compliance_profile": compliance_profile,
        "auditor_users": auditor_users,
        "title": "إدارة بوابة شام كاش الإلكترونية (ShamCash)",
    }
    return render(request, "payments/shamcash/dashboard.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# 2. BILLS & INVOICES MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_bills_list_view(request):
    """List, search and filter all ShamCash bills and invoices."""
    if not _is_admin_or_staff(request.user):
        messages.error(request, "غير مصرح لك.")
        return redirect("dashboard")

    bills = ShamCashBillRecord.objects.all().order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        bills = bills.filter(
            Q(bill_no__icontains=q)
            | Q(tran_id__icontains=q)
            | Q(user__email__icontains=q)
            | Q(note__icontains=q)
        )

    status_filter = request.GET.get("status")
    if status_filter and status_filter.isdigit():
        bills = bills.filter(status_id=int(status_filter))

    type_filter = request.GET.get("type")
    if type_filter:
        bills = bills.filter(bill_type=type_filter)

    currency_filter = request.GET.get("currency")
    if currency_filter and currency_filter.isdigit():
        bills = bills.filter(currency_id=int(currency_filter))

    paginator = Paginator(bills, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "total_count": bills.count(),
        "query": q,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "currency_filter": currency_filter,
        "title": "فواتير وعمليات شام كاش",
    }
    return render(request, "payments/shamcash/bills.html", context)


@login_required
def shamcash_bill_detail_view(request, bill_no):
    """
    Detailed Invoice view compliant with Article 6 of ShamCash Terms:
    - Unique Bill Number (billNo).
    - Company Name (اسم الشركة).
    - Service / Goods Description (وصف الخدمة أو السلعة).
    - Amount (قيمة الفاتورة).
    - Currency (العملة).
    - Creation Date & Time (تاريخ ووقت الإنشاء).
    - Expiration Time (تاريخ انتهاء الصلاحية - 10 دقائق).
    - Reference Number (رقم العملية الناشئ عن الربط الإلكتروني tranId).
    """
    if not (_is_admin_or_staff(request.user) or _is_shamcash_auditor_or_admin(request.user)):
        messages.error(request, "غير مصرح لك.")
        return redirect("dashboard")

    bill = get_object_or_404(ShamCashBillRecord, bill_no=bill_no)
    compliance_profile = _get_or_create_compliance_profile()

    refund_records = bill.refund_records.all().order_by("-created_at")
    webhooks = ShamCashWebhookLog.objects.filter(bill_no=bill.bill_no).order_by("-created_at")
    api_logs = ShamCashApiLog.objects.filter(bill_no=bill.bill_no).order_by("-created_at")

    context = {
        "bill": bill,
        "compliance_profile": compliance_profile,
        "refund_records": refund_records,
        "webhooks": webhooks,
        "api_logs": api_logs,
        "title": f"فاتورة شام كاش: {bill.bill_no}",
    }
    return render(request, "payments/shamcash/bill_detail.html", context)


@login_required
@require_POST
def shamcash_check_bill_status_view(request, bill_no):
    """
    Query ShamCash getBillInfo API live fallback to synchronize bill status.
    Doc Section 6.2.
    """
    if not _is_admin_or_staff(request.user):
        return JsonResponse({"ok": False, "message": "Unauthorized"}, status=403)

    bill = get_object_or_404(ShamCashBillRecord, bill_no=bill_no)
    gw = ShamCashGateway()
    client = gw.get_client()

    try:
        data = client.get_bill_info(bill_no)
        status_id = data.get("statusId")
        tran_id = data.get("tranId")

        if status_id is not None:
            bill.status_id = int(status_id)
            bill.status_name = ShamCashClient.STATUS_NAMES.get(int(status_id), str(status_id))
        if tran_id:
            bill.tran_id = int(tran_id) if str(tran_id).isdigit() else None
        bill.save(update_fields=["status_id", "status_name", "tran_id", "updated_at"])

        # If it was pending and is now paid, complete the associated deposit or order!
        if status_id == ShamCashClient.STATUS_PAID:
            if bill.deposit and bill.deposit.status == DepositRequest.Status.PENDING:
                from apps.payments.views_shamcash import _complete_successful_shamcash_deposit
                _complete_successful_shamcash_deposit(bill.deposit, tran_id, data)
            elif bill.order and bill.order.status == Order.Status.PENDING:
                from apps.orders.services import finalize_paid_gateway_order
                gateway_data = {
                    "status": "A",
                    "id": str(tran_id or bill_no),
                    "tran_id": tran_id,
                    "bill_no": bill_no,
                    "provider": "sham_cash",
                    "payload": data,
                }
                finalize_paid_gateway_order(bill.order, gateway_data)

        msg = f"تم تحديث حالة الفاتورة بنجاح: {bill.status_name} (رقم الحركة: {bill.tran_id or 'لا يوجد'})."
        messages.success(request, msg)
        return JsonResponse({"ok": True, "message": msg, "data": data})

    except ShamCashError as err:
        msg = f"فشل استعلام الحالة من شام كاش: {err}"
        messages.error(request, msg)
        return JsonResponse({"ok": False, "message": msg}, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# 3. REFUND OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def shamcash_refund_bill_view(request):
    """
    Execute full or partial refund for a paid ShamCash bill.
    Complies with Article 9 (Refund Rules) and Doc Section 6.3.
    """
    if not _is_admin_or_staff(request.user):
        return JsonResponse({"ok": False, "message": "غير مصرح لك بتنفيذ الاسترداد."}, status=403)

    bill_no = request.POST.get("bill_no", "").strip()
    amount_str = request.POST.get("amount", "").strip()
    note = request.POST.get("note", "").strip() or "استرداد مالي عبر لوحة التحكم"

    bill = get_object_or_404(ShamCashBillRecord, bill_no=bill_no)

    if bill.status_id != ShamCashClient.STATUS_PAID and bill.status_id != ShamCashClient.STATUS_PARTLY_REFUNDED:
        return JsonResponse({"ok": False, "message": "لا يمكن استرداد فاتورة غير مدفوعة."}, status=400)

    try:
        amt = Decimal(amount_str).quantize(Decimal("0.01"))
        if amt <= Decimal("0.00"):
            raise ValueError()
    except Exception:
        return JsonResponse({"ok": False, "message": "المبلغ المراد استرداده غير صحيح."}, status=400)

    if amt > bill.remaining_refundable_amount:
        return JsonResponse({
            "ok": False,
            "message": f"المبلغ المطلوب ({amt}) يتجاوز الرصيد المتبقي القابل للاسترداد ({bill.remaining_refundable_amount}).",
        }, status=400)

    gw = ShamCashGateway()
    try:
        if bill.bill_type == ShamCashBillRecord.BillType.ORDER and bill.order:
            res = gw.refund_order_payment(bill.order, reason=note, amount=amt, actor=request.user)
        elif bill.bill_type == ShamCashBillRecord.BillType.DEPOSIT and bill.deposit:
            res = gw.refund_deposit_payment(bill.deposit, reason=note, amount=amt, actor=request.user)
        else:
            # Standalone refund
            client = gw.get_client()
            import uuid
            idempotency_key = f"REF-{uuid.uuid4().hex[:14]}"
            res = client.refund_bill(bill_no=bill_no, amount=amt, note=note, idempotency_key=idempotency_key)
            tran_id = res.get("tranId")

            bill.total_refunded_amount += amt
            if bill.total_refunded_amount >= bill.amount:
                bill.status_id = ShamCashClient.STATUS_REFUNDED
                bill.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_REFUNDED]
            else:
                bill.status_id = ShamCashClient.STATUS_PARTLY_REFUNDED
                bill.status_name = ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PARTLY_REFUNDED]
            bill.save(update_fields=["total_refunded_amount", "status_id", "status_name", "updated_at"])

            ShamCashRefundRecord.objects.create(
                bill=bill,
                bill_no=bill_no,
                amount=amt,
                idempotency_key=idempotency_key,
                tran_id=tran_id,
                note=note,
                status="success",
                created_by=request.user,
                raw_response=res,
            )

        tran_id = res.get("tranId")
        msg = f"تم تنفيذ الاسترداد بنجاح بقيمة {amt} {bill.currency_code}. رقم عملية الاسترداد: {tran_id or 'N/A'}"
        messages.success(request, msg)
        return JsonResponse({"ok": True, "message": msg, "tranId": tran_id})

    except Exception as err:
        msg = f"فشل تنفيذ الاسترداد: {err}"
        messages.error(request, msg)
        return JsonResponse({"ok": False, "message": msg}, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# 4. RECONCILIATION & SETTLEMENT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_reconciliation_view(request):
    """
    Run and inspect End-of-Day (EOD) or periodic reconciliations.
    Complies with Section 11 of the Integration Guide and Article 8 of Terms.
    """
    if not (_is_admin_or_staff(request.user) or _is_shamcash_auditor_or_admin(request.user)):
        messages.error(request, "غير مصرح لك.")
        return redirect("dashboard")

    batches = ShamCashReconciliationBatch.objects.all().order_by("-created_at")
    recent_batch = None

    if request.method == "POST":
        from_date = request.POST.get("from_date", "").strip()
        to_date = request.POST.get("to_date", "").strip()

        if not from_date or not to_date:
            messages.error(request, "يرجى تحديد تاريخ البداية وتاريخ النهاية للمطابقة.")
            return redirect("shamcash_reconciliation")

        gw = ShamCashGateway()
        client = gw.get_client()

        try:
            # 1. Fetch all records from ShamCash using cursor loop
            shamcash_txs = client.fetch_all_reconciliation_transactions(
                from_date=from_date,
                to_date=to_date,
                limit=1000,
            )

            # 2. Query local paid/refunded bills in that range
            local_bills = ShamCashBillRecord.objects.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
                status_id__in=(ShamCashClient.STATUS_PAID, ShamCashClient.STATUS_REFUNDED, ShamCashClient.STATUS_PARTLY_REFUNDED),
            )

            total_sham_count = len(shamcash_txs)
            total_sham_amount = Decimal("0.00")
            for tx in shamcash_txs:
                total_sham_amount += Decimal(str(tx.get("amount", 0)))

            total_local_count = local_bills.count()
            total_local_amount = local_bills.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

            # 3. Match by billNo and tranId
            sham_map = {str(tx.get("billNo")): tx for tx in shamcash_txs if tx.get("billNo")}
            matched_count = 0
            discrepancies = []

            for b in local_bills:
                if b.bill_no in sham_map:
                    matched_count += 1
                else:
                    discrepancies.append({
                        "type": "missing_in_shamcash",
                        "bill_no": b.bill_no,
                        "amount": str(b.amount),
                        "tran_id": b.tran_id,
                        "description": "الفاتورة مسجلة محلياً كمدفوعة ولكنها غير موجودة في سجل شام كاش المسترجع للفترة.",
                    })

            for bill_no, tx in sham_map.items():
                if not local_bills.filter(bill_no=bill_no).exists():
                    discrepancies.append({
                        "type": "missing_in_local_db",
                        "bill_no": bill_no,
                        "amount": str(tx.get("amount")),
                        "tran_id": tx.get("tranId"),
                        "description": "الحركة منفذة في شام كاش ولكنها غير مقيدة محلياً كفاتورة مدفوعة.",
                    })

            batch_status = (
                ShamCashReconciliationBatch.BatchStatus.BALANCED
                if len(discrepancies) == 0 and total_sham_amount == total_local_amount
                else ShamCashReconciliationBatch.BatchStatus.DISCREPANCY
            )

            recent_batch = ShamCashReconciliationBatch.objects.create(
                from_date=from_date,
                to_date=to_date,
                status=batch_status,
                total_shamcash_count=total_sham_count,
                total_shamcash_amount=total_sham_amount,
                total_local_count=total_local_count,
                total_local_amount=total_local_amount,
                matched_count=matched_count,
                discrepancies_count=len(discrepancies),
                discrepancy_details=discrepancies,
                executed_by=request.user,
                notes=f"تم تنفيذ المطابقة بنجاح. النتيجة: {batch_status}",
            )
            messages.success(request, f"تمت عملية المطابقة والتسوية بنجاح: {recent_batch.get_status_display()}")

        except Exception as err:
            logger.error(f"Reconciliation error: {err}")
            messages.error(request, f"فشلت عملية المطابقة مع شام كاش: {err}")

    context = {
        "batches": batches,
        "recent_batch": recent_batch,
        "today_str": timezone.now().strftime("%Y-%m-%d"),
        "title": "المطابقة والتسوية المالية مع شام كاش",
    }
    return render(request, "payments/shamcash/reconciliation.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# 5. 5-YEAR COMPLIANCE AUDIT LOGS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_logs_view(request):
    """
    Search and view 5-Year Technical Audit Logs.
    Complies with Article 11 (Security) and Article 14 (5-Year Logs Retention).
    """
    if not (_is_admin_or_staff(request.user) or _is_shamcash_auditor_or_admin(request.user)):
        messages.error(request, "غير مصرح لك.")
        return redirect("dashboard")

    log_type = request.GET.get("type", "api")  # "api" or "webhook"
    q = request.GET.get("q", "").strip()

    if log_type == "webhook":
        logs = ShamCashWebhookLog.objects.all().order_by("-created_at")
        if q:
            logs = logs.filter(Q(bill_no__icontains=q) | Q(tran_id__icontains=q) | Q(error_message__icontains=q))
    else:
        logs = ShamCashApiLog.objects.all().order_by("-created_at")
        if q:
            logs = logs.filter(Q(bill_no__icontains=q) | Q(endpoint__icontains=q) | Q(error_message__icontains=q))

    paginator = Paginator(logs, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "log_type": log_type,
        "query": q,
        "title": "سجلات التدقيق التقنية (تخزين 5 سنوات - شام كاش)",
    }
    return render(request, "payments/shamcash/logs.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# 6. KYC & COMPLIANCE DOSSIER
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_compliance_dossier_view(request):
    """
    View and edit the official KYC & Regulatory Dossier.
    Complies with Articles 3, 15 & 21 of ShamCash Terms.
    """
    if not _is_admin_or_staff(request.user):
        messages.error(request, "غير مصرح لك.")
        return redirect("dashboard")

    profile = _get_or_create_compliance_profile()

    if request.method == "POST":
        profile.company_name = request.POST.get("company_name", profile.company_name).strip()
        profile.commercial_record_number = request.POST.get("commercial_record_number", profile.commercial_record_number).strip()
        profile.tax_number = request.POST.get("tax_number", profile.tax_number).strip()
        profile.establishment_contract_details = request.POST.get("establishment_contract_details", profile.establishment_contract_details).strip()
        profile.activity_description = request.POST.get("activity_description", profile.activity_description).strip()
        profile.shamcash_account_number = request.POST.get("shamcash_account_number", profile.shamcash_account_number).strip()
        profile.logo_url = request.POST.get("logo_url", profile.logo_url).strip()

        profile.general_manager_name = request.POST.get("general_manager_name", profile.general_manager_name).strip()
        profile.authorized_signatory_name = request.POST.get("authorized_signatory_name", profile.authorized_signatory_name).strip()
        profile.authorized_signatory_phone = request.POST.get("authorized_signatory_phone", profile.authorized_signatory_phone).strip()

        profile.technical_lead_name = request.POST.get("technical_lead_name", profile.technical_lead_name).strip()
        profile.technical_lead_email = request.POST.get("technical_lead_email", profile.technical_lead_email).strip()
        profile.technical_lead_phone = request.POST.get("technical_lead_phone", profile.technical_lead_phone).strip()

        profile.financial_officer_name = request.POST.get("financial_officer_name", profile.financial_officer_name).strip()
        profile.financial_officer_email = request.POST.get("financial_officer_email", profile.financial_officer_email).strip()
        profile.financial_officer_phone = request.POST.get("financial_officer_phone", profile.financial_officer_phone).strip()

        profile.complaints_officer_name = request.POST.get("complaints_officer_name", profile.complaints_officer_name).strip()
        profile.complaints_officer_email = request.POST.get("complaints_officer_email", profile.complaints_officer_email).strip()

        profile.compliance_statement = request.POST.get("compliance_statement", profile.compliance_statement).strip()
        profile.save()

        messages.success(request, "تم حفظ وتحديث ملف الامتثال والتوثيق بنجاح.")
        return redirect("shamcash_compliance_dossier")

    context = {
        "profile": profile,
        "title": "ملف التعرف والامتثال القانوني (KYC) لشام كاش",
    }
    return render(request, "payments/shamcash/compliance_dossier.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# 7. CREATE SHAMCASH AUDITOR ACCOUNT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def shamcash_create_auditor_view(request):
    """
    Creates or re-sets a dedicated Auditor account for the ShamCash audit/compliance team.
    User instruction: "وامكانية انشاء حساب بوابة الى طرف شام كاش ليتطلعو على معلومات مطلوبة"
    """
    if not _is_admin_or_staff(request.user):
        return JsonResponse({"ok": False, "message": "غير مصرح لك."}, status=403)

    email = request.POST.get("email", "").strip() or "auditor.shamcash@shamcash.sy"
    password = request.POST.get("password", "").strip() or "ShamCash@Audit2026!"
    name = request.POST.get("name", "").strip() or "فريق تدقيق شام كاش (ShamCash Auditor)"

    username = email.split("@")[0]

    with transaction.atomic():
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            # Check if username is taken
            if User.objects.filter(username=username).exists():
                username = f"{username}_{int(time.time())}"
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name="ShamCash",
                last_name="Auditor",
            )
        else:
            user.set_password(password)

        user.role = "shamcash_auditor"
        user.is_active = True
        user.save()

    msg = f"تم إنشاء وتجهيز حساب مدقق شام كاش بنجاح. البريد: {email} | كلمة المرور: {password}"
    messages.success(request, msg)
    return JsonResponse({
        "ok": True,
        "message": msg,
        "email": email,
        "password": password,
        "portal_url": request.build_absolute_uri(reverse("shamcash_auditor_portal")),
    })


# ══════════════════════════════════════════════════════════════════════════════
# 8. DEDICATED AUDITOR PORTAL FOR SHAMCASH INSPECTORS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def shamcash_auditor_portal_view(request):
    """
    Dedicated compliance and audit portal specifically for the ShamCash auditing team.
    Allows ShamCash to inspect:
    - Official KYC, Commercial Register & Legal profile (Article 3 & 15).
    - Invoices and financial records with exact tracking IDs (Article 6).
    - Proof of zero user surcharge (Article 7).
    - 5-Year technical API logs and Webhook event trails (Article 11 & 14).
    - Live Reconciliation tool (Article 8 & Section 11).
    - Real-time status lookup.
    """
    if not _is_shamcash_auditor_or_admin(request.user):
        messages.error(request, "هذه البوابة مخصصة حصرياً لفريق تدقيق وامتثال شام كاش وإدارة النظام.")
        return redirect("dashboard")

    compliance_profile = _get_or_create_compliance_profile()
    integration = PaymentGatewayIntegration.all_objects.filter(
        provider=PaymentGatewayIntegration.Provider.SHAM_CASH
    ).first()

    bills_qs = ShamCashBillRecord.objects.all()
    total_bills = bills_qs.count()
    paid_bills = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID).count()
    total_paid_usd = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID, currency_id=ShamCashClient.CURRENCY_USD).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total_paid_syp = bills_qs.filter(status_id=ShamCashClient.STATUS_PAID, currency_id=ShamCashClient.CURRENCY_SYP).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total_refunded = bills_qs.aggregate(s=Sum("total_refunded_amount"))["s"] or Decimal("0.00")

    recent_bills = bills_qs.order_by("-created_at")[:15]
    recent_webhooks = ShamCashWebhookLog.objects.order_by("-created_at")[:15]
    recent_api_logs = ShamCashApiLog.objects.order_by("-created_at")[:15]
    reconciliation_batches = ShamCashReconciliationBatch.objects.order_by("-created_at")[:5]

    context = {
        "compliance_profile": compliance_profile,
        "integration": integration,
        "total_bills": total_bills,
        "paid_bills": paid_bills,
        "total_paid_usd": total_paid_usd,
        "total_paid_syp": total_paid_syp,
        "total_refunded": total_refunded,
        "recent_bills": recent_bills,
        "recent_webhooks": recent_webhooks,
        "recent_api_logs": recent_api_logs,
        "reconciliation_batches": reconciliation_batches,
        "title": "بوابة تدقيق وامتثال شام كاش الرسمية (ShamCash Audit & Compliance Portal)",
    }
    return render(request, "payments/shamcash/auditor_portal.html", context)


# ══════════════════════════════════════════════════════════════════════════════
# 9. ACTIVE TEST CONNECTION & HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def shamcash_test_connection_view(request):
    """Execute live health check against ShamCash API and return status."""
    if not _is_admin_or_staff(request.user):
        return JsonResponse({"ok": False, "message": "Unauthorized"}, status=403)

    gw = ShamCashGateway()
    res = gw.check_health()
    return JsonResponse(res)
