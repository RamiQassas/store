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

@user_passes_test(is_staff)
def api_deposit_approve(request, pk):
    deposit = get_object_or_404(DepositRequest, pk=pk)
    # Re-importing logic or calling viewset directly is complex. 
    # For now, placeholder to fix routing.
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_deposit_reject(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_deposit_correct(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_wallet_hold(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_wallet_unhold(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_withdrawal_process(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_withdrawal_approve(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_withdrawal_complete(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_withdrawal_reject(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_order_mark_read(request, pk):
    return HttpResponse("Not implemented", status=501)

@user_passes_test(is_staff)
def api_user_search(request):
    return HttpResponse("Not implemented", status=501)
