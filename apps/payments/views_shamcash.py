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
- Strict Anti-Polling Compliance (Doc Section 10.3, Page 26):
  getBillInfo is NEVER polled in loops; only invoked once after >= 10 minutes if webhook did not arrive.
- Dual Currency support: USD (currencyId=1) and SYP (currencyId=2).
"""

import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
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

# Official ShamCash safety window before a single fallback getBillInfo is permitted (Doc Page 26)
SHAMCASH_FALLBACK_SAFETY_MINUTES = 10


def _safe_uuid(val: Any) -> Optional[uuid.UUID]:
    if not val:
        return None
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _get_active_shamcash_integration():
    """Retrieve the most recently updated active PaymentGatewayIntegration for ShamCash."""
    with bypass_tenant_filter():
        return (
            PaymentGatewayIntegration.all_objects.filter(
                provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
                is_active=True,
            )
            .exclude(api_key="")
            .exclude(api_secret="")
            .order_by("-updated_at")
            .first()
            or PaymentGatewayIntegration.all_objects.filter(
                provider=PaymentGatewayIntegration.Provider.SHAM_CASH,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )


def _get_active_shamcash_client() -> Optional[ShamCashClient]:
    """Retrieve active ShamCashClient from DB integration or settings fallback."""
    integration = _get_active_shamcash_integration()
    if integration:
        client = ShamCashClient.from_integration(integration)
        if client.agent_key and client.raw_secret_key:
            return client
    agent_key = getattr(settings, "SHAM_CASH_AGENT_KEY", "")
    secret_key = getattr(settings, "SHAM_CASH_SECRET_KEY", "")
    if agent_key and secret_key:
        return ShamCashClient(
            agent_key=agent_key,
            secret_key=secret_key,
            base_url=getattr(settings, "SHAM_CASH_BASE_URL", None),
            mode=getattr(settings, "SHAM_CASH_MODE", "live"),
            proxy_url=getattr(settings, "SHAM_CASH_PROXY_URL", None),
        )
    return None


def _can_invoke_fallback_get_bill_info(bill_no: str, created_at=None, force: bool = False) -> bool:
    """
    Enforces ShamCash Doc Section 10.3 (Page 26 - Avoid Polling):
    - Never call getBillInfo within the first 10 minutes of bill creation (unless manual admin force=True).
    - Only invoke once per bill after the 10-minute safety window if no webhook arrived.
    """
    if not bill_no:
        return False
    if force:
        return True
    if not created_at:
        return False
    if timezone.now() - created_at < timedelta(minutes=SHAMCASH_FALLBACK_SAFETY_MINUTES):
        return False
    cache_key = f"shamcash_fallback_once:{bill_no}"
    try:
        return bool(cache.add(cache_key, 1, timeout=86400))
    except Exception:
        return True


def _check_bill_paid_in_shamcash(
    client: Optional[ShamCashClient],
    bill_no: str,
    created_at=None,
    force: bool = False,
) -> Tuple[bool, Any, dict]:
    """
    Checks ShamCash bill status strictly adhering to Doc Page 26:
    1. First checks local ShamCashBillRecord (updated by official ShamCash Webhook) — 0 network calls!
    2. Only calls POST /getBillInfo once if force=True or >= 10 minutes elapsed without webhook.
    """
    if not bill_no:
        return False, None, {}

    with bypass_tenant_filter():
        bill_rec = ShamCashBillRecord.objects.filter(bill_no=bill_no).first()

    if bill_rec:
        if not created_at:
            created_at = bill_rec.created_at
        if bill_rec.status_id == ShamCashClient.STATUS_PAID:
            return True, bill_rec.tran_id, {
                "billNo": bill_no,
                "tranId": bill_rec.tran_id,
                "statusId": ShamCashClient.STATUS_PAID,
                "statusName": "paid",
                "amount": str(bill_rec.amount),
            }
        if bill_rec.status_id == ShamCashClient.STATUS_EXPIRED and not force:
            return False, None, {
                "billNo": bill_no,
                "statusId": ShamCashClient.STATUS_EXPIRED,
                "statusName": "expired",
            }

    if not client or not _can_invoke_fallback_get_bill_info(bill_no, created_at=created_at, force=force):
        return False, None, {}

    try:
        bill_info = client.get_bill_info(bill_no) or {}
        raw_st = bill_info.get("statusId")
        status_id = int(raw_st) if raw_st is not None and str(raw_st).isdigit() else raw_st
        tran_id = bill_info.get("tranId")

        if bill_rec and status_id is not None:
            bill_rec.status_id = int(status_id) if str(status_id).isdigit() else bill_rec.status_id
            bill_rec.status_name = ShamCashClient.STATUS_NAMES.get(bill_rec.status_id, str(status_id))
            if tran_id and str(tran_id).isdigit():
                bill_rec.tran_id = int(tran_id)
            bill_rec.save(update_fields=["status_id", "status_name", "tran_id", "updated_at"])

        is_paid = (
            status_id == ShamCashClient.STATUS_PAID
            or str(bill_info.get("statusName", "")).lower() == "paid"
        )
        if is_paid:
            return True, tran_id, bill_info
        return False, None, bill_info
    except Exception as err:
        logger.warning(f"Single fallback get_bill_info check failed for {bill_no}: {err}")
        return False, None, {}


def reconcile_shamcash_deposit_if_overdue(deposit: DepositRequest, force: bool = False) -> dict:
    """
    Reconciles a ShamCash deposit without violating ShamCash's anti-polling policy.
    Completes immediately if local ShamCashBillRecord is already Paid via Webhook,
    or performs the single post-10-minute getBillInfo fallback check when overdue.
    """
    if not deposit:
        return {}
    if deposit.status == DepositRequest.Status.COMPLETED:
        return {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}

    with bypass_tenant_filter():
        bill_rec = ShamCashBillRecord.objects.filter(deposit=deposit).order_by("-created_at").first()

    bill_no = (
        deposit.gateway_payment_id
        or (deposit.metadata.get("shamcash_bill_no") if isinstance(deposit.metadata, dict) else "")
        or (bill_rec.bill_no if bill_rec else "")
    )
    if not bill_no:
        return {}

    meta = deposit.metadata if isinstance(deposit.metadata, dict) else {}
    if meta.get("shamcash_fallback_checked") and not force:
        # Still honor local bill_rec if webhook arrived later
        if bill_rec and bill_rec.status_id == ShamCashClient.STATUS_PAID:
            if deposit.status == DepositRequest.Status.REJECTED:
                deposit.status = DepositRequest.Status.PENDING
                deposit.save(update_fields=["status", "updated_at"])
            _complete_successful_shamcash_deposit(deposit, bill_rec.tran_id, {"billNo": bill_no, "tranId": bill_rec.tran_id, "statusId": 4})
            return {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}
        return {}

    created_at = (bill_rec.created_at if bill_rec else None) or deposit.created_at
    client = _get_active_shamcash_client()
    is_paid, tran_id, bill_info = _check_bill_paid_in_shamcash(
        client, bill_no, created_at=created_at, force=force
    )

    if bill_info and not force:
        if not isinstance(deposit.metadata, dict):
            deposit.metadata = {}
        deposit.metadata["shamcash_fallback_checked"] = True
        deposit.save(update_fields=["metadata", "updated_at"])

    if is_paid:
        if deposit.status == DepositRequest.Status.REJECTED:
            deposit.status = DepositRequest.Status.PENDING
            deposit.save(update_fields=["status", "updated_at"])
        _complete_successful_shamcash_deposit(deposit, tran_id, bill_info)
        return bill_info or {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}

    status_id = bill_info.get("statusId") if isinstance(bill_info, dict) else None
    if deposit.status == DepositRequest.Status.PENDING and status_id in (ShamCashClient.STATUS_EXPIRED, 3, "3"):
        deposit.status = DepositRequest.Status.REJECTED
        deposit.admin_note = "انتهت مهلة صلاحية الفاتورة في شام كاش (10 دقائق) دون تسديد."
        deposit.save(update_fields=["status", "admin_note", "updated_at"])

    return bill_info or {"statusId": ShamCashClient.STATUS_PENDING, "statusName": "pending"}


def reconcile_shamcash_order_if_overdue(order: Order, force: bool = False) -> dict:
    """
    Reconciles a ShamCash order without violating ShamCash's anti-polling policy.
    Completes immediately if local ShamCashBillRecord is already Paid via Webhook,
    or performs the single post-10-minute getBillInfo fallback check when overdue.
    """
    if not order:
        return {}
    if order.status in (Order.Status.PROCESSING, Order.Status.COMPLETED):
        return {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}

    with bypass_tenant_filter():
        bill_rec = ShamCashBillRecord.objects.filter(order=order).order_by("-created_at").first()

    meta = order.metadata if isinstance(order.metadata, dict) else {}
    bill_no = (
        meta.get("shamcash_bill_no")
        or meta.get("gateway_payment_id")
        or (bill_rec.bill_no if bill_rec else "")
    )
    if not bill_no:
        return {}

    if meta.get("shamcash_fallback_checked") and not force:
        if bill_rec and bill_rec.status_id == ShamCashClient.STATUS_PAID:
            if order.status == Order.Status.CANCELLED:
                with bypass_tenant_filter():
                    order.status = Order.Status.PENDING
                    order.admin_note = "تم تأكيد السداد عبر شام كاش وتفعيل الطلب."
                    order.save(update_fields=["status", "admin_note", "updated_at"])
            finalize_paid_gateway_order(order, {
                "status": "A",
                "id": bill_no,
                "tran_id": bill_rec.tran_id,
                "bill_no": bill_no,
                "provider": "sham_cash",
                "payload": {"billNo": bill_no, "tranId": bill_rec.tran_id, "statusId": 4},
            })
            return {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}
        return {}

    created_at = (bill_rec.created_at if bill_rec else None) or order.created_at
    client = _get_active_shamcash_client()
    is_paid, tran_id, bill_info = _check_bill_paid_in_shamcash(
        client, bill_no, created_at=created_at, force=force
    )

    if bill_info and not force:
        with bypass_tenant_filter():
            if not isinstance(order.metadata, dict):
                order.metadata = {}
            order.metadata["shamcash_fallback_checked"] = True
            order.save(update_fields=["metadata", "updated_at"])

    if is_paid:
        bill_amount = bill_info.get("amount") if isinstance(bill_info, dict) else None
        expected_charge = meta.get("gateway_charge_amount")
        if bill_amount and expected_charge:
            try:
                if Decimal(str(bill_amount)) < (Decimal(str(expected_charge)) * Decimal("0.95")):
                    logger.error(f"SECURITY: Order {order.id} underpaid in ShamCash! Expected {expected_charge}, got {bill_amount}")
                    return bill_info
            except Exception:
                pass

        if order.status == Order.Status.CANCELLED:
            with bypass_tenant_filter():
                order.status = Order.Status.PENDING
                order.admin_note = "تم تأكيد السداد من شام كاش وتفعيل الطلب."
                order.save(update_fields=["status", "admin_note", "updated_at"])

        finalize_paid_gateway_order(order, {
            "status": "A",
            "id": bill_no,
            "tran_id": tran_id,
            "bill_no": bill_no,
            "provider": "sham_cash",
            "payload": bill_info,
        })
        return bill_info or {"statusId": ShamCashClient.STATUS_PAID, "statusName": "paid"}

    status_id = bill_info.get("statusId") if isinstance(bill_info, dict) else None
    if order.status == Order.Status.PENDING and status_id in (ShamCashClient.STATUS_EXPIRED, 3, "3"):
        with bypass_tenant_filter():
            order.status = Order.Status.CANCELLED
            order.admin_note = "انتهت صلاحية فاتورة شام كاش دون تسديد (10 دقائق)."
            order.save(update_fields=["status", "admin_note", "updated_at"])

    return bill_info or {"statusId": ShamCashClient.STATUS_PENDING, "statusName": "pending"}


def _complete_successful_shamcash_deposit(deposit: DepositRequest, tran_id: Any, status_data: dict) -> bool:
    """
    Atomically credits the user's wallet and marks DepositRequest as COMPLETED.
    Guarantees strict idempotency via select_for_update().
    Enforces Article 7: ZERO extra surcharge on the customer.
    """
    with transaction.atomic():
        with bypass_tenant_filter():
            locked_deposit = DepositRequest.all_objects.select_for_update().get(pk=deposit.pk)

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
                description=f"إيداع عبر شام كاش - رقم العملية: {tran_id or locked_deposit.gateway_payment_id}",
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
            locked_deposit.admin_note = f"إيداع عبر شام كاش - رقم العملية: {tran_id or locked_deposit.gateway_payment_id}"
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
    Documentation: ShamCash E-Payment Integration Guide v1.0.0 (Section 9, Pages 23-24).
    Receives {"encData": "..."} containing Direct JWE encrypted status updates:
      {billNo, tranId, statusId (4=Paid, 3=Expired), iat, exp}
    Returns HTTP 200 within 10 seconds.
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

    client = _get_active_shamcash_client()
    if not client or not client.raw_secret_key:
        logger.error("ShamCash webhook: No active ShamCash credentials configured.")
        webhook_log.error_message = "No active ShamCash secret key configured"
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": 1702, "message": "Integration not active"}, status=500)

    try:
        # Decrypt Direct JWE payload and verify expiration claim (Doc Section 5 & 9)
        payload = client.decrypt_payload(enc_data, verify_exp=True)
    except ShamCashError as err:
        logger.error(f"ShamCash webhook decryption failed: {err}")
        webhook_log.error_message = f"Decryption/validation failed: {err}"
        webhook_log.save(update_fields=["error_message"])
        return JsonResponse({"result": err.error_code or 1705, "message": "Decryption failed"}, status=400)

    bill_no = str(payload.get("billNo") or "").strip()
    tran_id = payload.get("tranId")
    raw_status_id = payload.get("statusId")
    status_id = int(raw_status_id) if raw_status_id is not None and str(raw_status_id).isdigit() else raw_status_id

    webhook_log.bill_no = bill_no
    webhook_log.tran_id = int(tran_id) if tran_id and str(tran_id).isdigit() else None
    webhook_log.status_id = status_id if isinstance(status_id, int) else None
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

    with bypass_tenant_filter():
        bill_record = ShamCashBillRecord.objects.select_related("deposit", "order").filter(bill_no=bill_no).first()
        if bill_record:
            if isinstance(status_id, int):
                bill_record.status_id = status_id
                bill_record.status_name = ShamCashClient.STATUS_NAMES.get(status_id, str(status_id))
            if tran_id and str(tran_id).isdigit():
                bill_record.tran_id = int(tran_id)
            bill_record.save(update_fields=["status_id", "status_name", "tran_id", "updated_at"])

    # ── Determine Target (Deposit vs Order) via BillRecord first, then prefix/query ──
    query_deposit_uuid = _safe_uuid(request.GET.get("id") or request.GET.get("deposit_id"))
    query_order_uuid = _safe_uuid(request.GET.get("id") or request.GET.get("order_id"))

    is_deposit = (
        (bill_record and bill_record.deposit_id is not None)
        or bill_no.startswith("DEP-")
        or request.GET.get("type") == "deposit"
    )

    if is_deposit:
        with bypass_tenant_filter():
            deposit = bill_record.deposit if (bill_record and bill_record.deposit) else None
            if not deposit and query_deposit_uuid:
                deposit = DepositRequest.all_objects.filter(pk=query_deposit_uuid).first()
            if not deposit:
                deposit = DepositRequest.all_objects.filter(gateway_payment_id=bill_no).first()
            if not deposit:
                deposit = DepositRequest.all_objects.filter(metadata__shamcash_bill_no=bill_no).first()

            if not deposit:
                logger.error(f"ShamCash webhook: Deposit not found for billNo={bill_no}")
                webhook_log.error_message = f"Deposit record not found for {bill_no}"
                webhook_log.save(update_fields=["error_message"])
                return JsonResponse({"result": 1703, "message": "Deposit record not found"}, status=404)

            # Status 4 = Paid (Success)
            if status_id == ShamCashClient.STATUS_PAID or str(payload.get("statusName", "")).lower() == "paid":
                if deposit.status == DepositRequest.Status.REJECTED:
                    deposit.status = DepositRequest.Status.PENDING
                    deposit.save(update_fields=["status", "updated_at"])
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
    is_order = (
        (bill_record and bill_record.order_id is not None)
        or bill_no.startswith("ORD-")
        or request.GET.get("type") == "order"
        or bool(query_order_uuid)
    )

    if is_order:
        with bypass_tenant_filter():
            order = bill_record.order if (bill_record and bill_record.order) else None
            if not order and query_order_uuid:
                order = Order.all_objects.filter(pk=query_order_uuid).first()
            if not order:
                order = Order.all_objects.filter(metadata__shamcash_bill_no=bill_no).first()
            if not order:
                order = Order.all_objects.filter(metadata__gateway_payment_id=bill_no).first()
            if not order and "-" in bill_no:
                parts = bill_no.split("-")
                if len(parts) >= 2:
                    possible_num = parts[1]
                    order = (
                        Order.all_objects.filter(number=possible_num).first()
                        or Order.all_objects.filter(number=f"ORD-{possible_num}").first()
                    )

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

            if status_id == ShamCashClient.STATUS_PAID or str(payload.get("statusName", "")).lower() == "paid":
                webhook_amount = payload.get("amount")
                expected_charge = order.metadata.get("gateway_charge_amount") if isinstance(order.metadata, dict) else None
                if webhook_amount and expected_charge:
                    try:
                        wh_amt = Decimal(str(webhook_amount))
                        exp_amt = Decimal(str(expected_charge))
                        if wh_amt < (exp_amt * Decimal("0.95")):
                            logger.error(f"SECURITY: Order {order.id} underpaid in ShamCash! Expected {exp_amt}, received {wh_amt}")
                            webhook_log.error_message = f"Underpaid: expected {exp_amt}, received {wh_amt}"
                            webhook_log.save(update_fields=["error_message"])
                            return JsonResponse({"result": 1700, "message": "Amount underpaid"}, status=400)
                    except Exception as exc:
                        logger.warning(f"Error parsing amount for validation: {exc}")

                if order.status == Order.Status.CANCELLED:
                    order.status = Order.Status.PENDING
                    order.admin_note = "تم تأكيد سداد الفاتورة عبر إشعار شام كاش الرسمي."
                    order.save(update_fields=["status", "admin_note", "updated_at"])

                gateway_data = {
                    "status": "A",
                    "id": bill_no,
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

    webhook_log.processed_successfully = True
    webhook_log.save(update_fields=["processed_successfully"])
    return JsonResponse({"result": 2500, "message": "Notification received successfully"})


def shamcash_redirect_view(request, bill_no: str = ""):
    """
    Browser return endpoint when customer completes payment or returns from ShamCash.
    Endpoints:
      - /payments/shamcash/redirect/<bill_no>/
      - /payments/shamcash/redirect/
    Strictly adheres to Doc Section 7 & 10.3: relies on encrypted backend Webhook
    (and single post-10-minute fallback if overdue), never spamming getBillInfo.
    """
    raw_bill_no = (bill_no or request.GET.get("bill_no") or request.GET.get("billNo") or "").strip()
    if "?" in raw_bill_no:
        raw_bill_no = raw_bill_no.split("?", 1)[0].strip()

    req_type = (request.GET.get("type") or "").strip().lower()
    obj_uuid = _safe_uuid(request.GET.get("id"))
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

    logger.info(
        f"ShamCash redirect return: type={req_type}, id={obj_uuid}, bill_no={raw_bill_no}, raw_status={raw_status}, is_cancelled={is_cancelled}"
    )

    with bypass_tenant_filter():
        bill_rec = (
            ShamCashBillRecord.objects.select_related("deposit", "order")
            .filter(bill_no=raw_bill_no)
            .first()
            if raw_bill_no
            else None
        )

    # ── Handle Wallet Deposit Return ──────────────────────────────────────────
    if (bill_rec and bill_rec.deposit_id) or req_type == "deposit" or raw_bill_no.startswith("DEP-"):
        with bypass_tenant_filter():
            deposit = bill_rec.deposit if (bill_rec and bill_rec.deposit) else None
            if not deposit and obj_uuid:
                deposit = DepositRequest.all_objects.filter(pk=obj_uuid).first()
            if not deposit and raw_bill_no:
                deposit = (
                    DepositRequest.all_objects.filter(gateway_payment_id=raw_bill_no).first()
                    or DepositRequest.all_objects.filter(metadata__shamcash_bill_no=raw_bill_no).first()
                )

            if deposit:
                if is_cancelled:
                    if deposit.status == DepositRequest.Status.PENDING:
                        deposit.status = DepositRequest.Status.REJECTED
                        deposit.admin_note = "تم إلغاء عملية الدفع من قبل المستخدم."
                        deposit.save(update_fields=["status", "admin_note", "updated_at"])
                    return redirect(f"{reverse('payment_status')}?type=deposit&id={deposit.id}&status=cancelled")

                reconcile_shamcash_deposit_if_overdue(deposit, force=False)
                deposit.refresh_from_db()

                active_bill_no = raw_bill_no or deposit.gateway_payment_id or ""
                if deposit.status == DepositRequest.Status.COMPLETED:
                    st = "success"
                elif deposit.status == DepositRequest.Status.REJECTED:
                    st = "cancelled" if ("المستخدم" in (deposit.admin_note or "")) else "failed"
                else:
                    st = "pending"
                return redirect(f"{reverse('payment_status')}?type=deposit&id={deposit.id}&status={st}&bill_no={active_bill_no}")

        return redirect("dashboard_deposits")

    # ── Handle Direct Order Return ───────────────────────────────────────────
    if (bill_rec and bill_rec.order_id) or req_type == "order" or raw_bill_no.startswith("ORD-"):
        with bypass_tenant_filter():
            order = bill_rec.order if (bill_rec and bill_rec.order) else None
            if not order and obj_uuid:
                order = Order.all_objects.filter(pk=obj_uuid).first()
            if not order and raw_bill_no:
                order = (
                    Order.all_objects.filter(metadata__shamcash_bill_no=raw_bill_no).first()
                    or Order.all_objects.filter(metadata__gateway_payment_id=raw_bill_no).first()
                )
            if not order and raw_bill_no.startswith("ORD-"):
                parts = raw_bill_no.split("-")
                if len(parts) >= 2:
                    order = (
                        Order.all_objects.filter(number=parts[1]).first()
                        or Order.all_objects.filter(number=f"ORD-{parts[1]}").first()
                    )

            if order:
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

                reconcile_shamcash_order_if_overdue(order, force=False)
                order.refresh_from_db()

                active_bill_no = (
                    raw_bill_no
                    or (order.metadata.get("shamcash_bill_no") if isinstance(order.metadata, dict) else "")
                    or (order.metadata.get("gateway_payment_id") if isinstance(order.metadata, dict) else "")
                )
                if order.status in (Order.Status.PROCESSING, Order.Status.COMPLETED):
                    st = "success"
                elif order.status == Order.Status.CANCELLED:
                    st = "cancelled" if ("المستخدم" in (order.admin_note or "")) else "failed"
                else:
                    st = "pending"
                return redirect(f"{reverse('payment_status')}?type=order&id={order.id}&status={st}&bill_no={active_bill_no}")

    messages.info(request, "شكراً لاستخدامك خدمة شام كاش.")
    return redirect("dashboard")
