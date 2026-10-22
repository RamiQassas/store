"""
ShamCash E-Payment Webhook and Browser Redirect Views
Documentation: ShamCash E-Payment Integration Guide v1.0.0
Specification:
- Webhook receives Direct JWE encrypted payload in {"encData": "..."}
- Server verifies token expiration, decrypts using AES-256-GCM, and validates bill status.
- Idempotent processing of Wallet Deposits and Direct Order Checkouts.
- Returns HTTP 200 within 10 seconds.
- Seamless dual currency support: USD (currencyId=1) and SYP (currencyId=2).
"""

import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.common.tenant_utils import bypass_tenant_filter
from apps.notifications.services import notify_user
from apps.orders.models import Order, OrderLog
from apps.orders.services import finalize_paid_gateway_order
from apps.payments.models import DepositRequest, PaymentGatewayIntegration
from apps.accounts.models import ActivityLog
from apps.payments.shamcash import ShamCashClient, ShamCashError
from apps.wallets.services import credit_wallet, get_or_create_wallet

logger = logging.getLogger(__name__)


def _get_active_shamcash_integration():
    """Retrieve active PaymentGatewayIntegration for ShamCash."""
    with bypass_tenant_filter():
        return PaymentGatewayIntegration.all_objects.filter(
            provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
            is_active=True,
        ).first()


def _complete_successful_shamcash_deposit(deposit: DepositRequest, tran_id: Any, status_data: dict) -> bool:
    """
    Atomically credits the user's wallet and marks DepositRequest as COMPLETED.
    Guarantees idempotency via select_for_update().
    """
    with transaction.atomic():
        with bypass_tenant_filter():
            locked_deposit = DepositRequest.objects.select_for_update().get(pk=deposit.pk)

            if locked_deposit.status == DepositRequest.Status.COMPLETED:
                logger.info(f"Deposit {deposit.id} already completed, skipping credit.")
                return False

            if tran_id:
                locked_deposit.transaction_id = str(tran_id)

            if not isinstance(locked_deposit.metadata, dict):
                locked_deposit.metadata = {}
            locked_deposit.metadata["shamcash_status_data"] = status_data
            locked_deposit.metadata["shamcash_verified_at"] = timezone.now().isoformat()

            # Recalculate fees and final amount
            locked_deposit.calculate_fees()
            final_amount = locked_deposit.final_amount

            # Credit wallet in wallet currency (e.g. USD)
            wallet = get_or_create_wallet(locked_deposit.user)
            if locked_deposit.currency and locked_deposit.currency.code == wallet.currency.code:
                wallet_final_amount = final_amount
            else:
                base_val = locked_deposit.currency.to_base(final_amount, "deposit") if locked_deposit.currency else final_amount
                wallet_final_amount = wallet.currency.from_base(base_val, "deposit")

            if wallet_final_amount <= 0:
                logger.error(f"Deposit {deposit.id} calculated zero/negative final amount: {wallet_final_amount}")
                return False

            credit_wallet(
                wallet_id=wallet.id,
                amount=wallet_final_amount,
                reference=f"shamcash:{locked_deposit.id}",
                description=f"إيداع مؤكد عبر شام كاش (فاتورة: {locked_deposit.gateway_payment_id})",
                created_by=locked_deposit.user,
                source="deposit",
                metadata={
                    "from_shamcash": True,
                    "tranId": tran_id,
                    "billNo": locked_deposit.gateway_payment_id,
                },
            )

            locked_deposit.status = DepositRequest.Status.COMPLETED
            locked_deposit.is_verified = True
            locked_deposit.admin_note = (
                f"شام كاش - تم الدفع بنجاح. رقم العملية: {tran_id or 'N/A'}"
            )
            locked_deposit.save(
                update_fields=[
                    "status",
                    "is_verified",
                    "transaction_id",
                    "metadata",
                    "admin_note",
                    "updated_at",
                ]
            )

            ActivityLog.objects.create(
                user=locked_deposit.user,
                action="deposit_completed",
                description=f"إيداع مؤكد عبر شام كاش: {locked_deposit.amount} {locked_deposit.currency.code if locked_deposit.currency else 'USD'}",
                metadata={
                    "gateway": "sham_cash",
                    "deposit_id": str(locked_deposit.id),
                    "amount": str(locked_deposit.amount),
                    "currency": locked_deposit.currency.code if locked_deposit.currency else "USD",
                    "wallet_credited": str(wallet_final_amount),
                    "tranId": tran_id,
                },
            )

            notify_user(
                user=locked_deposit.user,
                title="تم تأكيد الإيداع عبر شام كاش",
                body=f"تم إيداع {locked_deposit.amount} {locked_deposit.currency.symbol if locked_deposit.currency else '$'} في محفظتك بنجاح.",
                category="financial",
            )
            logger.info(f"Successfully completed Deposit {deposit.id} via ShamCash.")
            return True


@csrf_exempt
def shamcash_callback_view(request):
    """
    Asynchronous Webhook endpoint invoked by ShamCash backend.
    Receives {"encData": "..."} containing encrypted status updates.
    Endpoint: /payments/shamcash/callback/
    """
    logger.info(f"ShamCash webhook received: method={request.method}")

    # Extract encData from JSON body or POST form data
    enc_data = None
    if request.body:
        try:
            body_json = json.loads(request.body.decode("utf-8"))
            if isinstance(body_json, dict):
                enc_data = body_json.get("encData")
        except Exception:
            pass

    if not enc_data:
        enc_data = request.POST.get("encData")

    if not enc_data:
        logger.warning("ShamCash webhook missing encData payload.")
        return JsonResponse({"result": 1702, "message": "Missing encData"}, status=400)

    integration = _get_active_shamcash_integration()
    if not integration:
        logger.error("ShamCash webhook: No active ShamCash integration configured.")
        return JsonResponse({"result": 1700, "message": "Integration inactive"}, status=500)

    client = ShamCashClient.from_integration(integration)

    try:
        # Decrypt Direct JWE payload and verify expiration
        payload = client.decrypt_payload(enc_data, verify_exp=True)
    except ShamCashError as err:
        logger.error(f"ShamCash webhook decryption failed: {err}")
        return JsonResponse({"result": 1702, "message": f"Decryption failed: {err}"}, status=400)

    bill_no = str(payload.get("billNo") or "").strip()
    tran_id = payload.get("tranId")
    status_id = payload.get("statusId")

    logger.info(
        f"ShamCash webhook verified: billNo={bill_no}, tranId={tran_id}, statusId={status_id}"
    )

    if not bill_no:
        return JsonResponse({"result": 1705, "message": "Missing billNo in payload"}, status=400)

    # ── Check if Deposit ─────────────────────────────────────────────────────────
    query_deposit_id = request.GET.get("id") or request.GET.get("deposit_id")
    is_deposit = bill_no.startswith("DEP-") or (request.GET.get("type") == "deposit") or bool(query_deposit_id)

    if is_deposit:
        with bypass_tenant_filter():
            deposit = None
            if query_deposit_id:
                deposit = DepositRequest.objects.filter(pk=query_deposit_id).first()
            if not deposit:
                deposit = DepositRequest.objects.filter(gateway_payment_id=bill_no).first()
            if not deposit and "-" in bill_no:
                # Attempt parsing DEP-{id}-{timestamp}
                parts = bill_no.split("-")
                if len(parts) >= 2:
                    possible_id = parts[1]
                    deposit = DepositRequest.objects.filter(pk=possible_id).first()

            if not deposit:
                logger.error(f"ShamCash webhook: Deposit not found for billNo={bill_no}")
                return JsonResponse({"result": 1705, "message": "Deposit record not found"}, status=404)

            # Status 4 = Paid (Success)
            if status_id == ShamCashClient.STATUS_PAID:
                _complete_successful_shamcash_deposit(deposit, tran_id, payload)
                return JsonResponse({"result": 2500, "message": "Deposit confirmed successfully"})

            # Status 3 = Expired
            elif status_id == ShamCashClient.STATUS_EXPIRED:
                if deposit.status == DepositRequest.Status.PENDING:
                    deposit.status = DepositRequest.Status.REJECTED
                    deposit.admin_note = "انتهت صلاحية الفاتورة في شام كاش دون تسديد."
                    deposit.save(update_fields=["status", "admin_note", "updated_at"])
                return JsonResponse({"result": 2500, "message": "Deposit marked expired"})

            return JsonResponse({"result": 2500, "message": f"Status {status_id} recorded"})

    # ── Check if Order ───────────────────────────────────────────────────────────
    query_order_id = request.GET.get("id") or request.GET.get("order_id")
    is_order = bill_no.startswith("ORD-") or (request.GET.get("type") == "order") or bool(query_order_id)

    if is_order:
        with bypass_tenant_filter():
            order = None
            if query_order_id:
                order = Order.all_objects.filter(pk=query_order_id).first()
            if not order:
                order = Order.all_objects.filter(metadata__gateway_payment_id=bill_no).first()
            if not order and "-" in bill_no:
                parts = bill_no.split("-")
                if len(parts) >= 2:
                    possible_num = parts[1]
                    order = Order.all_objects.filter(number=possible_num).first()

            if not order:
                logger.error(f"ShamCash webhook: Order not found for billNo={bill_no}")
                return JsonResponse({"result": 1705, "message": "Order record not found"}, status=404)

            if status_id == ShamCashClient.STATUS_PAID:
                gateway_data = {
                    "status": "A",
                    "id": str(tran_id or bill_no),
                    "tran_id": tran_id,
                    "bill_no": bill_no,
                    "provider": "sham_cash",
                    "payload": payload,
                }
                finalize_paid_gateway_order(order, gateway_data)
                return JsonResponse({"result": 2500, "message": "Order payment accepted and processed"})

            elif status_id == ShamCashClient.STATUS_EXPIRED:
                if order.status == Order.Status.PENDING:
                    order.status = Order.Status.CANCELLED
                    order.admin_note = "انتهت صلاحية فاتورة شام كاش دون دفع."
                    order.save(update_fields=["status", "admin_note", "updated_at"])
                    OrderLog.objects.create(
                        order=order,
                        status=Order.Status.CANCELLED,
                        note="تم إلغاء الطلب لانتهاء مهلة سداد فاتورة شام كاش.",
                    )
                return JsonResponse({"result": 2500, "message": "Order marked expired"})

            return JsonResponse({"result": 2500, "message": f"Status {status_id} recorded"})

    # Fallback response for unhandled bill formats
    return JsonResponse({"result": 2500, "message": "Notification received"})


def shamcash_redirect_view(request):
    """
    Browser return endpoint when customer completes payment or returns from ShamCash.
    Endpoint: /payments/shamcash/redirect/
    """
    bill_no = request.GET.get("bill_no") or request.GET.get("billNo") or ""
    req_type = request.GET.get("type") or ""
    obj_id = request.GET.get("id") or ""

    logger.info(f"ShamCash redirect return: type={req_type}, id={obj_id}, bill_no={bill_no}")

    integration = _get_active_shamcash_integration()
    client = ShamCashClient.from_integration(integration) if integration else None

    # ── Handle Wallet Deposit Return ──────────────────────────────────────────
    if req_type == "deposit" or bill_no.startswith("DEP-"):
        with bypass_tenant_filter():
            deposit = None
            if obj_id:
                deposit = DepositRequest.objects.filter(pk=obj_id).first()
            if not deposit and bill_no:
                deposit = DepositRequest.objects.filter(gateway_payment_id=bill_no).first()

            if deposit:
                # Active verification if still pending
                if deposit.status == DepositRequest.Status.PENDING and client and bill_no:
                    try:
                        bill_info = client.get_bill_info(bill_no)
                        status_id = bill_info.get("statusId")
                        if status_id == ShamCashClient.STATUS_PAID:
                            _complete_successful_shamcash_deposit(deposit, bill_info.get("tranId"), bill_info)
                        elif status_id == ShamCashClient.STATUS_EXPIRED:
                            deposit.status = DepositRequest.Status.REJECTED
                            deposit.admin_note = "انتهت صلاحية الفاتورة."
                            deposit.save(update_fields=["status", "admin_note", "updated_at"])
                    except Exception as err:
                        logger.warning(f"Could not actively verify ShamCash bill on return: {err}")

                deposit.refresh_from_db()
                if deposit.status == DepositRequest.Status.COMPLETED:
                    messages.success(request, "تم شحن رصيد محفظتك بنجاح عبر شام كاش!")
                elif deposit.status == DepositRequest.Status.REJECTED:
                    messages.warning(request, "تم إلغاء أو انتهاء صلاحية عملية الدفع عبر شام كاش.")
                else:
                    messages.info(request, "عملية الإيداع قيد المراجعة، وسيتم إضافة الرصيد فور وصول إشعار السداد.")

        return redirect("dashboard_deposits")

    # ── Handle Direct Order Return ───────────────────────────────────────────
    if req_type == "order" or bill_no.startswith("ORD-"):
        with bypass_tenant_filter():
            order = None
            if obj_id:
                order = Order.all_objects.filter(pk=obj_id).first()
            if not order and bill_no:
                order = Order.all_objects.filter(metadata__gateway_payment_id=bill_no).first()

            if order:
                # Active verification if still pending
                if order.status == Order.Status.PENDING and client and bill_no:
                    try:
                        bill_info = client.get_bill_info(bill_no)
                        status_id = bill_info.get("statusId")
                        if status_id == ShamCashClient.STATUS_PAID:
                            gateway_data = {
                                "status": "A",
                                "id": str(bill_info.get("tranId") or bill_no),
                                "tran_id": bill_info.get("tranId"),
                                "bill_no": bill_no,
                                "provider": "sham_cash",
                                "payload": bill_info,
                            }
                            finalize_paid_gateway_order(order, gateway_data)
                        elif status_id == ShamCashClient.STATUS_EXPIRED:
                            order.status = Order.Status.CANCELLED
                            order.save(update_fields=["status", "updated_at"])
                    except Exception as err:
                        logger.warning(f"Could not actively verify ShamCash order on return: {err}")

                order.refresh_from_db()
                if order.status in (Order.Status.PROCESSING, Order.Status.COMPLETED):
                    messages.success(request, "تم سداد قيمة الطلب بنجاح عبر شام كاش وجارٍ تنفيذه!")
                elif order.status == Order.Status.CANCELLED:
                    messages.warning(request, "تم إلغاء عملية الدفع عبر شام كاش.")
                else:
                    messages.info(request, "طلبك قيد المتابعة وسيتم تحديثه تلقائياً.")

                return redirect(f"{reverse('dashboard_order_detail', kwargs={'pk': order.id})}?new=1")

    # Default fallback
    messages.info(request, "شكراً لاستخدامك خدمة شام كاش.")
    return redirect("dashboard")
