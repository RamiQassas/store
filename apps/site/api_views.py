from decimal import Decimal
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.wallets.models import Wallet
from apps.common.models import Currency
from apps.payments.models import PaymentMethod

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
    
    # Calculate Max:
    # 1. Available balance in USD
    # 2. Subtract fee (if any, as % or fixed)
    # 3. Convert to target currency
    
    available_usd = wallet.available_balance
    
    # Simple fee calculation estimate (based on amount=available)
    fee = method.calculate_fee(available_usd, mode="withdrawal")
    
    net_available_usd = max(Decimal("0.00"), available_usd - fee)
    
    # Convert to target currency
    max_amount = currency.from_base(net_available_usd, operation="withdraw")
    
    return JsonResponse({
        "max_amount": float(max_amount.quantize(Decimal("0.01"))),
        "currency_symbol": currency.symbol,
        "fee_estimate": float(fee.quantize(Decimal("0.01")))
    })
