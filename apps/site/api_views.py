from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.wallets.models import Wallet
from apps.common.models import Currency
from apps.payments.models import PaymentMethod, DepositRequest, WithdrawalRequest
from django.contrib.auth.decorators import user_passes_test

def is_staff(user):
    return user.is_staff

@login_required
def get_max_withdrawable(request):
    """API to calculate max withdrawable amount in a chosen currency."""
    currency_id = request.GET.get('currency_id')
    method_id = request.GET.get('method_id')
    
    if not currency_id or not method_id:
        return JsonResponse({"error": "Missing parameters"}, status=400)
        
    wallet = get_object_or_404(Wallet, user=request.user)
    currency = get_object_or_404(Currency, id=currency_id)
    method = get_object_or_404(PaymentMethod, id=method_id)
    
    available_usd = wallet.available_balance
    fee = method.calculate_fee(available_usd, mode="withdrawal")
    
    net_available_usd = max(Decimal("0.00"), available_usd - fee)
    
    max_amount = currency.from_base(net_available_usd, operation="withdraw")
    
    return JsonResponse({
        "max_amount": float(max_amount.quantize(Decimal("0.01"))),
        "currency_symbol": currency.symbol,
        "fee_estimate": float(fee.quantize(Decimal("0.01")))
    })

@login_required
def get_conversion_preview(request):
    """API to get conversion preview for deposit/withdrawal."""
    amount = Decimal(request.GET.get('amount', 0))
    currency_id = request.GET.get('currency_id')
    operation = request.GET.get('operation', 'deposit') # deposit or withdraw
    
    if not currency_id:
        return JsonResponse({"error": "Missing currency"}, status=400)
        
    currency = get_object_or_404(Currency, id=currency_id)
    
    # If deposit: convert from local to USD (base)
    # If withdraw: convert from local to USD (base) using sell_rate
    # This logic seems to depend on `to_base` vs `from_base`.
    # Based on models.py:
    # to_base: amount in currency -> USD
    # from_base: USD -> amount in currency
    
    if operation == "deposit":
        # User is depositing in local, what is it in USD?
        usd_value = currency.to_base(amount, operation="deposit")
    else:
        # User is withdrawing in local, what is it in USD?
        # Actually user wants to know what their USD balance is in local
        usd_value = currency.to_base(amount, operation="withdraw")
        
    return JsonResponse({
        "usd_value": float(usd_value.quantize(Decimal("0.01"))),
        "currency_symbol": currency.symbol
    })

from django.shortcuts import redirect
from rest_framework.test import APIRequestFactory
from apps.payments.views import DepositRequestViewSet, WithdrawalRequestViewSet

def _run_action(request, pk, action, viewset_class):
    factory = APIRequestFactory()
    # Mock a POST request for the action
    api_request = factory.post(f"/{action}/")
    api_request.user = request.user
    # Need to pass data if present
    api_request.data = request.POST
    
    view = viewset_class.as_view({'post': action})
    return view(api_request, pk=pk)

@user_passes_test(is_staff)
def api_deposit_approve(request, pk):
    return _run_action(request, pk, 'approve', DepositRequestViewSet)

@user_passes_test(is_staff)
def api_deposit_reject(request, pk):
    return _run_action(request, pk, 'reject', DepositRequestViewSet)

@user_passes_test(is_staff)
def api_deposit_correct(request, pk):
    # Deposit doesn't have 'correct' in viewset.
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_wallet_hold(request, pk):
    from apps.wallets.services import hold_funds
    import json
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get("amount", "0")))
        reason = data.get("reason", "Admin manual hold")
        hold_funds(pk, amount, reason=reason, created_by=request.user)
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@user_passes_test(is_staff)
def api_wallet_unhold(request, pk):
    from apps.wallets.services import unhold_funds
    import json
    try:
        data = json.loads(request.body)
        # Ensure amount is a clean string for Decimal conversion
        raw_amount = str(data.get("amount", "0")).replace(',', '').strip()
        amount = Decimal(raw_amount)
        reason = data.get("reason", "Admin manual unhold")
        unhold_funds(pk, amount, reason=reason, created_by=request.user)
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@user_passes_test(is_staff)
def api_withdrawal_process(request, pk):
    return _run_action(request, pk, 'process', WithdrawalRequestViewSet)

@user_passes_test(is_staff)
def api_withdrawal_approve(request, pk):
    return _run_action(request, pk, 'approve', WithdrawalRequestViewSet)

@user_passes_test(is_staff)
def api_withdrawal_complete(request, pk):
    return _run_action(request, pk, 'complete', WithdrawalRequestViewSet)

@user_passes_test(is_staff)
def api_withdrawal_reject(request, pk):
    return _run_action(request, pk, 'reject', WithdrawalRequestViewSet)

@user_passes_test(is_staff)
def api_order_mark_read(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_user_search(request):
    return HttpResponse("Not implemented", status=501)
