from apps.common.models import Currency, SocialMediaLink
from apps.payments.models import PaymentMethod

def preferred_currency(request):
    """
    Determines the preferred currency for the current user or guest session.
    Returns:
        Currency object and a list of all active currencies.
    """
    all_currencies = Currency.objects.filter(is_active=True).order_by("display_order", "code")
    
    pref_currency = None
    
    # 1. Check logged in user preference
    if request.user.is_authenticated and request.user.preferred_currency:
        pref_currency = request.user.preferred_currency
    
    # 2. Check session for guest/override
    if not pref_currency:
        session_currency_id = request.session.get("preferred_currency_id")
        if session_currency_id:
            pref_currency = Currency.objects.filter(id=session_currency_id, is_active=True).first()
    
    # 3. Fallback to default currency
    if not pref_currency:
        pref_currency = Currency.objects.filter(is_default=True, is_active=True).first()
    
    # 4. Absolute fallback to first active currency
    if not pref_currency:
        pref_currency = all_currencies.first()

    system_currency = Currency.objects.filter(code="USD").first() or all_currencies.first()

    return {
        "CURRENCY": pref_currency,
        "ALL_CURRENCIES": all_currencies,
        "SYSTEM_CURRENCY": system_currency,
        "SOCIAL_LINKS": SocialMediaLink.objects.filter(is_active=True).order_by("display_order"),
        "PAYMENT_METHODS": PaymentMethod.objects.filter(is_active=True).order_by('display_order')
    }
