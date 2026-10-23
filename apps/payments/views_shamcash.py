"""
ShamCash E-Payment Webhook and Browser Redirect Views
Documentation: ShamCash E-Payment Integration Guide v1.0.0
Terms & Conditions: ShamCash B2B Collection Specification

Specification:
- Webhook receives Direct JWE encrypted payload in {"encData": "..."}.
- Server decrypts using AES-256-GCM, checks exp claim against replay attacks, and verifies payload.
- Full 5-Year Webhook & Audit logging per Article 14 of ShamCash Terms.
- Zero customer surcharge compliance per Article 7.
- Idempotent processing of Wallet Deposits and Direct Order Checkouts.
- Returns HTTP 200 with result code 2500 within the 10-second safety window.
- Dual Currency support: USD (currencyId=1) and SYP (currencyId=2).
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

from apps.accounts.models import ActivityLog
from apps.common.tenant_utils import bypass_tenant_filter
from apps.notifications.services import notify_user
from apps.orders.models import Order, OrderLog
from apps.orders.services import finalize_paid_gateway_order
from apps.payments.models import (
    DepositRequest,
    PaymentGatewayIntegration,
    ShamCashBillRecord,
    ShamCashWebhookLog,
)
from apps.payments.shamcash import ShamCashClient, ShamCashError
from apps.wallets.services import credit_wallet, get_or_create_wallet

logger = logging.getLogger(__name__)


def _get_active_shamcash_integration():
    """Retrieve active PaymentGatewayIntegration for ShamCash."""
    with bypass_tenant_filter():
        return (
            PaymentGatewayIntegration.all_objects.filter(
                provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
                is_active=True,
            )
            .exclude(api_key="")
            .first()
        )


def _complete_successful_shamcash_deposit(deposit: DepositRequest, tran_id: Any, status_data: dict) -> bool:
    """
    Atomically credits the user's wallet and marks DepositRequest as COMPLETED.
    Guarantees strict idempotency via select_for_update().
    Enforces Article 7: ZERO extra surcharge on the customer.
    """
    with transaction.atomic():
        with bypass_tenant_filter():
            locked_deposit = DepositRequest.objects.select_for_update().get(pk=deposit.pk)

            if locked_deposit.status == DepositRequest.Status.COMPLETED:
                logger.info(f"Deposit {deposit.id} already completed; skipping redundant credit.")
                return False

            if tran_id:
                locked_deposit.transaction_id = str(tran_id)

            if not isinstance(locked_deposit.metadata, dict):
                locked_deposit.metadata = {}
            locked_deposit.metadata["shamcash_status_data"] = status_data
            locked_deposit.metadata["shamcash_verified_at"] = timezone.now().isoformat()
            locked_deposit.metadata["shamcash_tran_id"] = tran_id

            # Zero surcharge policy: client gets 100% of their deposit amount
            deposit_amount = locked_deposit.amount
            locked_deposit.fee_amount = Decimal("0.00")
            locked_deposit.final_amount = deposit_amount

            # Credit wallet in wallet currency
            wallet = get_or_create_wallet(locked_deposit.user)
            if locked_deposit.currency and locked_deposit.currency.code == wallet.currency.code:
                wallet_final_amount = deposit_amount
            else:
                base_val = locked_deposit.currency.to_base(deposit_amount, "deposit") if locked_deposit.currency else deposit_amount
                wallet_final_amount = wallet.currency.from_base(base_val, "deposit")

            if wallet_final_amount <= 0:
                logger.error(f"Deposit {deposit.id} calculated zero/negative final amount: {wallet_final_amount}")
                return False

            credit_wallet(
                wallet_id=wallet.id,
                amount=wallet_final_amount,
                reference=f"shamcash:{locked_deposit.id}",
                description=f"إيداع مؤكد عبر شام كاش (رقم الفاتورة: {locked_deposit.gateway_payment_id} - رقم العملية: {tran_id or 'N/A'})",
                created_by=locked_deposit.user,
                source="deposit",
                metadata={
                    "from_shamcash": True,
                    "tranId": tran_id,
                    "billNo": locked_deposit.gateway_payment_id,
                    "provider": "sham_cash",
                },
            )

            locked_deposit.status = DepositRequest.Status.COMPLETED
            locked_deposit.is_verified = True
            locked_deposit.admin_note = (
                f"شام كاش - تم استلام وتأكيد الدفع بنجاح. رقم الحركة: {tran_id or 'N/A'}"
            )
            locked_deposit.save(
                update_fields=[
                    "status",
                    "is_verified",
                    "transaction_id",
                    "fee_amount",
                    "final_amount",
                    "metadata",
                    "admin_note",
                    "updated_at",
                ]
            )

            # Update ShamCashBillRecord if exists
            bill_no = locked_deposit.gateway_payment_id
            if bill_no:
                ShamCashBillRecord.objects.filter(bill_no=bill_no).update(
                    status_id=ShamCashClient.STATUS_PAID,
                    status_name=ShamCashClient.STATUS_NAMES[ShamCashClient.STATUS_PAID],
                    tran_id=int(tran_id) if tran_id and str(tran_id).isdigit() else None,
                    updated_at=timezone.now(),
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
                title="تم تأكيد الإيداع عبر شام كاش بنجاح",
                body=f"تم إيداع {locked_deposit.amount} {locked_deposit.currency.symbol if locked_deposit.currency else '$'} في محفظتك بنجاح.",
                category="financial",
            )
            logger.info(f"Successfully completed Deposit {deposit.id} via ShamCash [tranId={tran_id}].")
            return True


@csrf_exempt
def shamcash_callback_view(request):
    """
    Asynchronous Webhook endpoint invoked by ShamCash backend.
    Documentation: ShamCash E-Payment Integration Guide v1.0.0 (Section 9).
    Receives {"encData": "..."} containing encrypted status updates.
    Endpoint: /payments/shamcash/callback/
    """
    client_ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    logger.info(f"ShamCash webhook received from IP={client_ip}: method={request.method}")

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

    # Initial Webhook Log for 5-Year compliance audit
    webhook_log = ShamCashWebhookLog.objects.create(
        raw_enc_data=enc_data or (request.body.decode("utf-8", errors="ignore")[:2000] if request.body else ""),
        ip_address=client_ip,
        is_valid=False,
        processed_successfully=False,
    )

    if not enc_data:
        err_msg = "Missing encData payload in request"
        logger.warning(f"ShamCash webhook missing encData payload [log_id={webhook_log.id}].")
        webhook_log.error_message = err_msg
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": 1700, "message": err_msg}, status=400)

    integration = _get_active_shamcash_integration()
    if not integration:
        logger.error("ShamCash webhook: No active ShamCash integration configured.")
        webhook_log.error_message = "No active ShamCash integration found"
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": 1702, "message": "Integration not active"}, status=500)

    client = ShamCashClient.from_integration(integration)

    try:
        # Decrypt Direct JWE payload and verify expiration claim (Doc Section 5 & 9)
        payload = client.decrypt_payload(enc_data, verify_exp=True)
    except ShamCashError as err:
        logger.error(f"ShamCash webhook decryption failed: {err}")
        webhook_log.error_message = f"Decryption/validation failed: {err}"
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": 1705, "message": f"Decryption failed: {err}"}, status=400)

    bill_no = str(payload.get("billNo") or "").strip()
    tran_id = payload.get("tranId")
    status_id = payload.get("statusId")

    webhook_log.bill_no = bill_no
    webhook_log.tran_id = int(tran_id) if tran_id and str(tran_id).isdigit() else None
    webhook_log.status_id = int(status_id) if status_id is not None else None
    webhook_log.decrypted_payload = payload
    webhook_log.is_valid = True
    webhook_log.save(update_fields=["bill_no", "tran_id", "status_id", "decrypted_payload", "is_valid"])

    logger.info(
        f"ShamCash webhook verified: billNo={bill_no}, tranId={tran_id}, statusId={status_id}"
    )

    if not bill_no:
        webhook_log.error_message = "Missing billNo in decrypted payload"
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": 1700, "message": "Missing billNo in payload"}, status=400)

    # Update central ShamCashBillRecord status
    bill_record = ShamCashBillRecord.objects.filter(bill_no=bill_no).first()
    if bill_record:
        if status_id is not None:
            bill_record.status_id = int(status_id)
            bill_record.status_name = ShamCashClient.STATUS_NAMES.get(int(status_id), str(status_id))
        if tran_id:
            bill_record.tran_id = int(tran_id) if str(tran_id).isdigit() else None
        bill_record.save(update_fields=["status_id", "status_name", "tran_id", "updated_at"])

    # ── Handle Wallet Deposit ──────────────────────────────────────────────────
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
                parts = bill_no.split("-")
                if len(parts) >= 2:
                    possible_id = parts[1]
                    deposit = DepositRequest.objects.filter(pk=possible_id).first()

            if not deposit:
                logger.error(f"ShamCash webhook: Deposit not found for billNo={bill_no}")
                webhook_log.error_message = f"Deposit record not found for {bill_no}"
                webhook_log.save(update_fields=["error_message"])
                return JsonResponse({"result": 1703, "message": "Deposit record not found"}, status=404)

            # Status 4 = Paid (Success)
            if status_id == ShamCashClient.STATUS_PAID:
                _complete_successful_shamcash_deposit(deposit, tran_id, payload)
                webhook_log.processed_successfully = True
                webhook_log.save(update_fields=["processed_successfully"])
                return JsonResponse({"result": 2500, "message": "Deposit confirmed successfully"})

            # Status 3 = Expired
            elif status_id == ShamCashClient.STATUS_EXPIRED:
                if deposit.status == DepositRequest.Status.PENDING:
                    deposit.status = DepositRequest.Status.REJECTED
                    deposit.admin_note = "انتهت مهلة صلاحية الفاتورة في شام كاش (10 دقائق) دون تسديد."
                    deposit.save(update_fields=["status", "admin_note", "updated_at"])
                webhook_log.processed_successfully = True
                webhook_log.save(update_fields=["processed_successfully"])
                return JsonResponse({"result": 2500, "message": "Deposit marked expired"})

            webhook_log.processed_successfully = True
            webhook_log.save(update_fields=["processed_successfully"])
            return JsonResponse({"result": 2500, "message": f"Status {status_id} recorded"})

    # ── Handle Direct Order ────────────────────────────────────────────────────
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
                webhook_log.error_message = f"Order record not found for {bill_no}"
                webhook_log.save(update_fields=["error_message"])
                return JsonResponse({"result": 1703, "message": "Order record not found"}, status=404)

            # Idempotency check: if order is already processed, return 2500 safely
            if order.status in (Order.Status.PROCESSING, Order.Status.COMPLETED):
                logger.info(f"Order {order.id} already completed; skipping redundant webhook processing.")
                webhook_log.processed_successfully = True
                webhook_log.save(update_fields=["processed_successfully"])
                return JsonResponse({"result": 2500, "message": "Order already processed"})

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
                webhook_log.processed_successfully = True
                webhook_log.save(update_fields=["processed_successfully"])
                return JsonResponse({"result": 2500, "message": "Order payment accepted and processed"})

            elif status_id == ShamCashClient.STATUS_EXPIRED:
                if order.status == Order.Status.PENDING:
                    order.status = Order.Status.CANCELLED
                    order.admin_note = "انتهت صلاحية فاتورة شام كاش دون تسديد (10 دقائق)."
                    order.save(update_fields=["status", "admin_note", "updated_at"])
                    OrderLog.objects.create(
                        order=order,
                        status=Order.Status.CANCELLED,
                        note="تم إلغاء الطلب لانتهاء مهلة سداد فاتورة شام كاش.",
                    )
                webhook_log.processed_successfully = True
                webhook_log.save(update_fields=["processed_successfully"])
                return JsonResponse({"result": 2500, "message": "Order marked expired"})

            webhook_log.processed_successfully = True
            webhook_log.save(update_fields=["processed_successfully"])
            return JsonResponse({"result": 2500, "message": f"Status {status_id} recorded"})

    # Fallback response
    webhook_log.processed_successfully = True
    webhook_log.save(update_fields=["processed_successfully"])
    return JsonResponse({"result": 2500, "message": "Notification received successfully"})


def shamcash_redirect_view(request):
    """
    Browser return endpoint when customer completes payment or returns from ShamCash.
    Endpoint: /payments/shamcash/redirect/
    """
    bill_no = request.GET.get("bill_no") or request.GET.get("billNo") or ""
    req_type = request.GET.get("type") or ""
    obj_id = request.GET.get("id") or ""
    raw_status = (
        request.GET.get("status")
        or request.GET.get("st")
        or request.GET.get("state")
        or request.GET.get("result")
        or request.GET.get("action")
        or ""
    ).strip().lower()
    is_cancelled = (
        raw_status in ("cancel", "cancelled", "canceled", "user_cancel", "reject", "rejected")
        or request.GET.get("cancel") in ("1", "true", "yes")
        or request.GET.get("cancelled") in ("1", "true", "yes")
    )

    logger.info(f"ShamCash redirect return: type={req_type}, id={obj_id}, bill_no={bill_no}, raw_status={raw_status}, is_cancelled={is_cancelled}")

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
                # Handle explicit user cancellation
                if is_cancelled:
                    if deposit.status == DepositRequest.Status.PENDING:
                        deposit.status = DepositRequest.Status.REJECTED
                        deposit.admin_note = "تم إلغاء عملية الدفع من قبل المستخدم."
                        deposit.save(update_fields=["status", "admin_note", "updated_at"])
                    return redirect(f"{reverse('payment_status')}?type=deposit&id={deposit.id}&status=cancelled")

                # Active fallback verification if still pending
                active_bill_no = bill_no or getattr(deposit, "gateway_payment_id", "")
                if deposit.status == DepositRequest.Status.PENDING and client and active_bill_no:
                    try:
                        bill_info = client.get_bill_info(active_bill_no)
                        status_id = bill_info.get("statusId")
                        if status_id == ShamCashClient.STATUS_PAID:
                            _complete_successful_shamcash_deposit(deposit, bill_info.get("tranId"), bill_info)
                        elif status_id == ShamCashClient.STATUS_EXPIRED:
                            deposit.status = DepositRequest.Status.REJECTED
                            deposit.admin_note = "انتهت صلاحية الفاتورة دون دفع."
                            deposit.save(update_fields=["status", "admin_note", "updated_at"])
                    except Exception as err:
                        logger.warning(f"Could not actively verify ShamCash bill on return: {err}")

                deposit.refresh_from_db()
                if deposit.status == DepositRequest.Status.COMPLETED:
                    st = "success"
                elif deposit.status == DepositRequest.Status.REJECTED:
                    st = "cancelled" if ("المستخدم" in (deposit.admin_note or "")) else "failed"
                else:
                    st = "pending"
                return redirect(f"{reverse('payment_status')}?type=deposit&id={deposit.id}&status={st}")

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
                # Handle explicit user cancellation
                if is_cancelled:
                    if order.status == Order.Status.PENDING:
                        order.status = Order.Status.CANCELLED
                        order.admin_note = "تم إلغاء عملية الدفع من قبل المستخدم."
                        order.save(update_fields=["status", "admin_note", "updated_at"])
                        OrderLog.objects.create(
                            order=order,
                            status=Order.Status.CANCELLED,
                            note="تم إلغاء عملية الدفع من قبل المستخدم.",
                            created_by=request.user if (getattr(request, "user", None) and request.user.is_authenticated and request.user == order.customer) else None,
                        )
                    return redirect(f"{reverse('payment_status')}?type=order&id={order.id}&status=cancelled")

                # Active fallback verification if still pending
                active_bill_no = bill_no or (order.metadata.get("gateway_payment_id") if order.metadata else "") or getattr(order, "order_number", "")
                if order.status == Order.Status.PENDING and client and active_bill_no:
                    try:
                        bill_info = client.get_bill_info(active_bill_no)
                        status_id = bill_info.get("statusId")
                        if status_id == ShamCashClient.STATUS_PAID:
                            gateway_data = {
                                "status": "A",
                                "id": str(bill_info.get("tranId") or active_bill_no),
                                "tran_id": bill_info.get("tranId"),
                                "bill_no": active_bill_no,
                                "provider": "sham_cash",
                                "payload": bill_info,
                            }
                            finalize_paid_gateway_order(order, gateway_data)
                        elif status_id == ShamCashClient.STATUS_EXPIRED:
                            order.status = Order.Status.CANCELLED
                            order.admin_note = "انتهت مهلة الدفع في شام كاش."
                            order.save(update_fields=["status", "admin_note", "updated_at"])
                    except Exception as err:
                        logger.warning(f"Could not actively verify ShamCash order on return: {err}")

                order.refresh_from_db()
                if order.status in (Order.Status.PROCESSING, Order.Status.COMPLETED):
                    st = "success"
                elif order.status == Order.Status.CANCELLED:
                    st = "cancelled"
                else:
                    st = "pending"
                return redirect(f"{reverse('payment_status')}?type=order&id={order.id}&status={st}")

    # Default fallback
    messages.info(request, "شكراً لاستخدامك خدمة شام كاش.")
    return redirect("dashboard")
