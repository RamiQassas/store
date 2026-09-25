import json
import logging
import hmac
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.notifications.services import notify_user
from apps.payments.models import DepositRequest, PaymentGatewayIntegration
from apps.payments.paymera import PaymeraClient, PaymeraError
from apps.wallets.services import credit_wallet, get_or_create_wallet

logger = logging.getLogger(__name__)


def _stored_payment_id(record) -> str:
    """Return the payment ID created by us, never an ID supplied by a caller."""
    if isinstance(record, DepositRequest):
        return str(record.gateway_payment_id or "").strip()
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    return str(metadata.get("gateway_payment_id") or "").strip()


def _payment_id_is_bound(stored_payment_id: str, reported_payment_id) -> bool:
    """Reject callbacks that try to substitute a different gateway payment."""
    if not stored_payment_id:
        return False
    if not reported_payment_id:
        return True
    return hmac.compare_digest(stored_payment_id, str(reported_payment_id).strip())


def _complete_successful_deposit(deposit: DepositRequest, status_data: dict) -> bool:
    """
    Atomically credits the wallet and marks the deposit as COMPLETED.
    Returns True if completed in this call, False if already completed.
    """
    with transaction.atomic():
        locked_deposit = DepositRequest.objects.select_for_update().get(pk=deposit.pk)

        if locked_deposit.status == DepositRequest.Status.COMPLETED:
            logger.info(f"Deposit {deposit.id} already completed, skipping credit.")
            return False

        rrn = status_data.get("rrn")
        if rrn:
            locked_deposit.transaction_id = str(rrn)

        if not isinstance(locked_deposit.metadata, dict):
            locked_deposit.metadata = {}
        locked_deposit.metadata["paymera_status_data"] = status_data
        locked_deposit.metadata["paymera_verified_at"] = timezone.now().isoformat()

        # Recalculate fees and final amount
        locked_deposit.calculate_fees()
        final_amount = locked_deposit.final_amount

        # Calculate final wallet amount
        wallet = get_or_create_wallet(locked_deposit.user)
        if locked_deposit.currency.code == wallet.currency.code:
            wallet_final_amount = final_amount
        else:
            base_val = locked_deposit.currency.to_base(final_amount, "deposit")
            wallet_final_amount = wallet.currency.from_base(base_val, "deposit")

        if wallet_final_amount <= 0:
            logger.error(f"Deposit {deposit.id} has invalid wallet_final_amount: {wallet_final_amount}")
            return False

        # 1. Credit wallet
        credit_wallet(
            wallet_id=wallet.id,
            amount=wallet_final_amount,
            reference=f"paymera:{locked_deposit.id}",
            description=f"إيداع عبر بوابة بيميرا (Paymera)",
            created_by=locked_deposit.user,
            source="deposit",
            metadata={
                "from_paymera": True,
                "rrn": rrn,
                "payment_id": locked_deposit.gateway_payment_id,
            }
        )

        # 2. Update deposit
        locked_deposit.final_amount = final_amount
        locked_deposit.wallet_amount = wallet_final_amount
        locked_deposit.status = DepositRequest.Status.COMPLETED
        locked_deposit.is_verified = True
        locked_deposit.reviewed_at = timezone.now()
        locked_deposit.save()

        # 3. Add deposit usage for user
        try:
            amount_in_usd = locked_deposit.currency.to_base(locked_deposit.final_amount, "deposit")
            locked_deposit.user.add_deposit_usage(amount_in_usd)
        except Exception as exc:
            logger.warning(f"Could not add deposit usage for user: {exc}")

        # 4. Notify user
        try:
            notify_user(
                user=locked_deposit.user,
                title="تم تأكيد الدفع عبر بيميرا",
                body=f"تم تأكيد عملية الدفع بنجاح وإضافة {wallet_final_amount:,.2f} {wallet.currency.code} إلى محفظتك.",
                action_url="/dashboard/wallet/",
                category="financial",
                priority="high"
            )
        except Exception as exc:
            logger.warning(f"Could not send user notification: {exc}")

        logger.info(f"Successfully completed Deposit {deposit.id} via Paymera.")
        return True


from django.urls import reverse
from apps.orders.models import Order, OrderLog
from apps.orders.services import finalize_paid_gateway_order


@csrf_exempt
def paymera_trigger_view(request):
    """
    Webhook / Server-to-server trigger invoked by Paymera upon transaction completion.
    Supports both wallet deposits (deposit_id) and direct order checkouts (order_id).
    Endpoint: /payments/paymera/trigger/
    """
    order_id = request.GET.get("order_id") or request.POST.get("order_id")
    deposit_id = request.GET.get("deposit_id") or request.POST.get("deposit_id")
    payment_id = request.GET.get("payment_id") or request.POST.get("payment_id")
    payload_status = (request.GET.get("status") or request.POST.get("status") or "").strip().lower()

    # If payload is in JSON body
    if not order_id and not deposit_id and request.body:
        try:
            body_data = json.loads(request.body.decode("utf-8"))
            if isinstance(body_data, dict):
                order_id = body_data.get("order_id")
                deposit_id = deposit_id or body_data.get("deposit_id")
                payment_id = payment_id or body_data.get("payment_id") or body_data.get("paymentId")
                if not payload_status and body_data.get("status"):
                    payload_status = str(body_data.get("status")).strip().lower()
        except Exception:
            pass

    logger.info(f"Paymera trigger received. order_id={order_id}, deposit_id={deposit_id}, payment_id={payment_id}, payload_status={payload_status}")

    from apps.common.tenant_utils import bypass_tenant_filter

    with bypass_tenant_filter():
        # Resolve integration globally
        integration = PaymentGatewayIntegration.all_objects.filter(
            provider=PaymentGatewayIntegration.Provider.PAYMERA,
            is_active=True
        ).first()

        # ── Handle Direct Order Payment ──────────────────────────────────────────
        order = None
        if order_id:
            order = Order.all_objects.filter(pk=order_id).first()
        if not order and not deposit_id and payment_id:
            order = Order.all_objects.filter(metadata__gateway_payment_id=payment_id).first()

        if order:
            if not integration:
                logger.error("Paymera trigger (Order): No active Paymera integration found.")
                return JsonResponse({"status": "error", "message": "Integration not configured"}, status=500)

            client = PaymeraClient.from_integration(integration)
            active_payment_id = _stored_payment_id(order)
            if not _payment_id_is_bound(active_payment_id, payment_id):
                logger.warning("Rejected Paymera order callback with an unbound payment ID.")
                return JsonResponse({"status": "error", "message": "Invalid payment reference"}, status=400)

            # Direct check if payload indicates cancellation/failure
            if payload_status in ("cancel", "c", "canceled", "cancelled", "failed", "f"):
                if order.status == Order.Status.PENDING:
                    order.status = Order.Status.CANCELLED
                    order.admin_note = f"Paymera webhook reported cancellation/failure: {payload_status}"
                    order.save(update_fields=["status", "admin_note", "updated_at"])
                    OrderLog.objects.create(
                        order=order,
                        status=Order.Status.CANCELLED,
                        note=f"تم استلام إشعار إلغاء/فشل الدفع من بوابة بيميرا ({payload_status}).",
                        created_by=None,
                    )
                return JsonResponse({"status": "ok", "message": f"Order payment marked as {payload_status}"})

            try:
                status_res = client.get_payment_status(active_payment_id)
                payment_status = status_res.get("status")
                logger.info(f"Paymera trigger status for order {order.id}: {payment_status}")

                if payment_status == PaymeraClient.STATUS_ACCEPTED:
                    finalize_paid_gateway_order(order, status_res)
                    return JsonResponse({"status": "ok", "message": "Order payment accepted and processed"})

                elif payment_status in (PaymeraClient.STATUS_FAILED, PaymeraClient.STATUS_CANCELED):
                    if order.status == Order.Status.PENDING:
                        order.status = Order.Status.CANCELLED
                        order.admin_note = f"Paymera status: {payment_status}"
                        order.save(update_fields=["status", "admin_note", "updated_at"])
                        OrderLog.objects.create(
                            order=order,
                            status=Order.Status.CANCELLED,
                            note=f"تم إلغاء الطلب بناءً على استعلام حالة بيميرا ({payment_status}).",
                            created_by=None,
                        )
                    return JsonResponse({"status": "ok", "message": f"Order payment {payment_status}"})

                return JsonResponse({"status": "ok", "message": f"Order payment pending ({payment_status})"})

            except PaymeraError as exc:
                logger.error(f"Paymera trigger API error for order: {exc}")
                return JsonResponse({"status": "error", "message": str(exc)}, status=400)

        # ── Handle Deposit Payment ───────────────────────────────────────────────
        deposit = None
        if deposit_id:
            deposit = DepositRequest.all_objects.filter(pk=deposit_id).first()
        if not deposit and payment_id:
            deposit = DepositRequest.all_objects.filter(gateway_payment_id=payment_id).first()

        if not deposit:
            logger.warning(f"Paymera trigger: Neither Order nor Deposit found (order_id={order_id}, deposit_id={deposit_id}, payment_id={payment_id})")
            return JsonResponse({"status": "error", "message": "Transaction record not found"}, status=404)

        # Resolve integration & client for deposit
        dep_integration = getattr(deposit.payment_method, "gateway", None)
        if not dep_integration or dep_integration.provider != PaymentGatewayIntegration.Provider.PAYMERA:
            dep_integration = integration

        if not dep_integration:
            logger.error("Paymera trigger: No active Paymera integration found.")
            return JsonResponse({"status": "error", "message": "Integration not configured"}, status=500)

        client = PaymeraClient.from_integration(dep_integration)
        active_payment_id = _stored_payment_id(deposit)
        if not _payment_id_is_bound(active_payment_id, payment_id):
            logger.warning("Rejected Paymera deposit callback with an unbound payment ID.")
            return JsonResponse({"status": "error", "message": "Invalid payment reference"}, status=400)

        if payload_status in ("cancel", "c", "canceled", "cancelled", "failed", "f"):
            if deposit.status == DepositRequest.Status.PENDING:
                deposit.status = DepositRequest.Status.REJECTED
                deposit.admin_note = f"Paymera transaction webhook reported: {payload_status}"
                deposit.save(update_fields=["status", "admin_note", "updated_at"])
            return JsonResponse({"status": "ok", "message": f"Payment {payload_status}"})

        try:
            status_res = client.get_payment_status(active_payment_id)
            payment_status = status_res.get("status")
            logger.info(f"Paymera trigger status for deposit {deposit.id}: {payment_status}")

            if payment_status == PaymeraClient.STATUS_ACCEPTED:
                _complete_successful_deposit(deposit, status_res)
                return JsonResponse({"status": "ok", "message": "Payment accepted and processed"})

            elif payment_status in (PaymeraClient.STATUS_FAILED, PaymeraClient.STATUS_CANCELED):
                if deposit.status == DepositRequest.Status.PENDING:
                    deposit.status = DepositRequest.Status.REJECTED
                    deposit.admin_note = f"Paymera transaction status: {payment_status}"
                    if not isinstance(deposit.metadata, dict):
                        deposit.metadata = {}
                    deposit.metadata["paymera_status_data"] = status_res
                    deposit.save(update_fields=["status", "admin_note", "metadata", "updated_at"])
                return JsonResponse({"status": "ok", "message": f"Payment {payment_status}"})

            return JsonResponse({"status": "ok", "message": f"Payment pending ({payment_status})"})

        except PaymeraError as exc:
            logger.error(f"Paymera trigger API error: {exc}")
            return JsonResponse({"status": "error", "message": str(exc)}, status=400)


def paymera_callback_view(request):
    """
    User Return URL called when user clicks Finish or Cancel in Paymera.
    Supports both direct order checkouts (order_id) and wallet deposits (deposit_id).
    Endpoint: /payments/paymera/callback/
    """
    from django.conf import settings
    from apps.common.tenant_utils import bypass_tenant_filter

    order_id = request.GET.get("order_id")
    deposit_id = request.GET.get("deposit_id")
    payment_id = request.GET.get("payment_id")

    # Detect cancellation from GET query parameters
    status_param = (request.GET.get("status") or "").strip().lower()
    action_param = (request.GET.get("action") or "").strip().lower()
    state_param = (request.GET.get("state") or "").strip().lower()
    result_param = (request.GET.get("result") or "").strip().lower()
    is_cancelled_url = (
        status_param in ("cancel", "c", "canceled", "cancelled", "failed", "f", "reject", "rejected")
        or action_param in ("cancel", "cancelled", "abort", "back")
        or state_param in ("cancel", "cancelled", "failed")
        or result_param in ("cancel", "cancelled", "failed")
        or request.GET.get("cancelled") in ("1", "true", "True")
        or request.GET.get("cancel") in ("1", "true", "True")
    )

    with bypass_tenant_filter():
        integration = PaymentGatewayIntegration.all_objects.filter(
            provider=PaymentGatewayIntegration.Provider.PAYMERA,
            is_active=True
        ).first()

        # ── 1. Check for Direct Order Payment ────────────────────────────────────
        order = None
        if order_id:
            order = Order.all_objects.filter(pk=order_id).first()
        if not order and not deposit_id and payment_id:
            order = Order.all_objects.filter(metadata__gateway_payment_id=payment_id).first()

        if order:
            active_payment_id = (
                order.metadata.get("gateway_payment_id")
                if isinstance(order.metadata, dict) else None
            ) or payment_id

            # Prepare return redirect destination
            detail_path = f"{reverse('dashboard_order_detail', kwargs={'pk': order.id})}?new=1"
            if order.store and getattr(request, "store", None) != order.store:
                domain = order.store.custom_domain or f"{order.store.subdomain}.{getattr(settings, 'MAIN_DOMAIN', 'raqamiyatapp.com')}"
                order_dest_url = f"{request.scheme}://{domain}{detail_path}"
                order_list_url = f"{request.scheme}://{domain}{reverse('dashboard_orders')}"
            else:
                order_dest_url = detail_path
                order_list_url = reverse("dashboard_orders")

            # Handle direct cancellation indicated in URL
            if is_cancelled_url:
                if order.status == Order.Status.PENDING:
                    order.status = Order.Status.CANCELLED
                    order.admin_note = f"Paymera payment cancelled by customer via URL (status={status_param or action_param or 'cancelled'})"
                    order.save(update_fields=["status", "admin_note", "updated_at"])
                    OrderLog.objects.create(
                        order=order,
                        status=Order.Status.CANCELLED,
                        note="تم إلغاء عملية الدفع من قبل العميل وإلغاء الطلب.",
                        created_by=request.user if request.user.is_authenticated else None,
                    )
                messages.warning(request, "تم إلغاء عملية الدفع وإلغاء طلبك بنجاح.")
                return redirect(order_list_url)

            if integration and active_payment_id:
                client = PaymeraClient.from_integration(integration)
                try:
                    status_res = client.get_payment_status(active_payment_id)
                    payment_status = status_res.get("status")

                    if payment_status == PaymeraClient.STATUS_ACCEPTED:
                        finalized = finalize_paid_gateway_order(order, status_res)
                        if finalized.status == Order.Status.CANCELLED:
                            messages.warning(request, "تم سداد المبلغ بنجاح، ولكن المنتج غير متوفر حالياً لدى المزود وقد تم استرداد كامل المبلغ في محفظتك فوراً.")
                        else:
                            messages.success(request, "تم سداد قيمة طلبك بنجاح وجاري تنفيذه فوراً!")
                        return redirect(order_dest_url)

                    elif payment_status in (PaymeraClient.STATUS_CANCELED, PaymeraClient.STATUS_FAILED):
                        if order.status == Order.Status.PENDING:
                            order.status = Order.Status.CANCELLED
                            order.admin_note = f"Paymera status: {payment_status}"
                            order.save(update_fields=["status", "admin_note", "updated_at"])
                            OrderLog.objects.create(
                                order=order,
                                status=Order.Status.CANCELLED,
                                note=f"تم إلغاء الطلب بناءً على رد بوابة الدفع بيميرا ({payment_status}).",
                                created_by=request.user if request.user.is_authenticated else None,
                            )
                        if payment_status == PaymeraClient.STATUS_CANCELED:
                            messages.warning(request, "تم إلغاء عملية الدفع من قبلك وإلغاء الطلب.")
                        else:
                            messages.error(request, "فشلت عملية الدفع عبر بيميرا. تم إلغاء الطلب.")
                        return redirect(order_list_url)

                    else:
                        # User returned without payment being completed (e.g. status "P" / uncompleted)
                        if order.status == Order.Status.PENDING:
                            order.status = Order.Status.CANCELLED
                            order.admin_note = f"Paymera payment not completed (status={payment_status}). Cancelled on return."
                            order.save(update_fields=["status", "admin_note", "updated_at"])
                            OrderLog.objects.create(
                                order=order,
                                status=Order.Status.CANCELLED,
                                note=f"تم إلغاء الطلب لعدم استكمال السداد عبر بيميرا ({payment_status or 'معلق'}).",
                                created_by=request.user if request.user.is_authenticated else None,
                            )
                        messages.warning(request, "لم يتم استكمال عملية الدفع عبر بيميرا، وتم إلغاء الطلب المعلق.")
                        return redirect(order_list_url)

                except Exception as exc:
                    logger.warning(f"Paymera callback status check for order failed: {exc}")

            if order.status in (Order.Status.COMPLETED, Order.Status.PROCESSING):
                messages.success(request, "تم تأكيد طلبك بنجاح.")
                return redirect(order_dest_url)

            # If order is still pending, cancel it on return
            if order.status == Order.Status.PENDING:
                order.status = Order.Status.CANCELLED
                order.admin_note = "Paymera payment not confirmed on callback return. Cancelled."
                order.save(update_fields=["status", "admin_note", "updated_at"])
                OrderLog.objects.create(
                    order=order,
                    status=Order.Status.CANCELLED,
                    note="تم إلغاء الطلب لعدم تأكيد عملية السداد عند العودة من بوابة بيميرا.",
                    created_by=request.user if request.user.is_authenticated else None,
                )
                messages.warning(request, "لم يتم استكمال عملية الدفع عبر بيميرا وتم إلغاء الطلب.")
                return redirect(order_list_url)

        # ── 2. Check for Wallet Deposit ──────────────────────────────────────────
        deposit = None
        if deposit_id:
            deposit = DepositRequest.all_objects.filter(pk=deposit_id).first()
        if not deposit and payment_id:
            deposit = DepositRequest.all_objects.filter(gateway_payment_id=payment_id).first()

        if not deposit:
            messages.error(request, "لم يتم العثور على العملية المرتبطة ببوابة الدفع.")
            return redirect("dashboard_deposits")

        # Handle direct cancellation indicated in URL for deposit
        if is_cancelled_url:
            if deposit.status == DepositRequest.Status.PENDING:
                deposit.status = DepositRequest.Status.REJECTED
                deposit.admin_note = f"Paymera deposit cancelled by user via URL (status={status_param or 'cancelled'})"
                deposit.save(update_fields=["status", "admin_note", "updated_at"])
            messages.warning(request, "تم إلغاء عملية الإيداع.")
            return redirect("dashboard_deposits")

        dep_integration = getattr(deposit.payment_method, "gateway", None) or integration

        if dep_integration:
            client = PaymeraClient.from_integration(dep_integration)
            active_payment_id = deposit.gateway_payment_id or payment_id

            try:
                status_res = client.get_payment_status(active_payment_id)
                payment_status = status_res.get("status")

                if payment_status == PaymeraClient.STATUS_ACCEPTED:
                    _complete_successful_deposit(deposit, status_res)
                    messages.success(request, "تمت عملية الدفع بنجاح عبر بيميرا وتمت إضافة الرصيد إلى محفظتك!")
                    return redirect("dashboard_wallet")

                elif payment_status in (PaymeraClient.STATUS_CANCELED, PaymeraClient.STATUS_FAILED):
                    if deposit.status == DepositRequest.Status.PENDING:
                        deposit.status = DepositRequest.Status.REJECTED
                        deposit.admin_note = f"Paymera transaction status: {payment_status}"
                        if not isinstance(deposit.metadata, dict):
                            deposit.metadata = {}
                        deposit.metadata["paymera_status_data"] = status_res
                        deposit.save(update_fields=["status", "admin_note", "metadata", "updated_at"])
                    if payment_status == PaymeraClient.STATUS_CANCELED:
                        messages.warning(request, "تم إلغاء عملية الدفع من قبلك.")
                    else:
                        messages.error(request, "فشلت عملية الدفع عبر بيميرا. يرجى التأكد من بيانات البطاقة أو المحاولة مجدداً.")
                    return redirect("dashboard_deposits")

                else:
                    messages.info(request, "عملية الدفع لم تكتمل بعد. سيتم تحديث رصيدك تلقائياً عند اكتمالها وسدادها.")
                    return redirect("dashboard_deposits")

            except Exception as exc:
                logger.warning(f"Paymera callback status check failed: {exc}")

        # Fallback status display
        if deposit.status == DepositRequest.Status.COMPLETED:
            messages.success(request, "تم تأكيد طلب الإيداع بنجاح.")
            return redirect("dashboard_wallet")

        messages.info(request, "تم استلام عودتك من بوابة الدفع. سيتم تحديث حالة طلبك قريباً.")
        return redirect("dashboard_deposits")
