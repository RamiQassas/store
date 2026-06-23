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

    # Task 9: KYC handling is now managed in templates/views with a message instead of hiding
    payment_methods = PaymentMethod.objects.filter(is_active=True).order_by('display_order')

    return {
        "CURRENCY": pref_currency,
        "ALL_CURRENCIES": all_currencies,
        "SYSTEM_CURRENCY": system_currency,
        "WITHDRAWAL_RATE": pref_currency.sell_rate if pref_currency else 1.0,
        "SOCIAL_LINKS": SocialMediaLink.objects.filter(is_active=True).order_by("display_order"),
        "PAYMENT_METHODS": payment_methods,
        "payment_methods": payment_methods
    }


def tenant_context(request):
    """
    Multi-Tenant Context Processor.
    
    Provides store branding data to ALL templates automatically.
    When request.store is set (by TenantMiddleware), this processor injects:
    - The active store object
    - Store colors as CSS variables
    - Store logo, name, font, contact info
    
    When request.store is None (main Raqamiyat site), it provides
    the default Raqamiyat branding values.
    
    This is the core of the Shared Template architecture: one template,
    multiple tenants, data isolation via store context.
    """
    from django.conf import settings
    from django.contrib.sites.models import Site
    if not Site.objects.filter(id=settings.SITE_ID).exists():
        Site.objects.create(
            id=settings.SITE_ID,
            domain="raqamiyatapp.com",
            name="Raqamiyat"
        )
    platform_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
    store = getattr(request, 'store', None)
    
    if store:
        return {
            "PLATFORM_URL": platform_url,
            # Core store object (available as {{ store }} in all templates)
            "store": store,
            "is_tenant": True,

            # Store identity
            "STORE_NAME": store.name,
            "STORE_LOGO": store.logo if store.logo else None,
            "STORE_BANNER": store.banner if store.banner else None,
            "STORE_DESCRIPTION": store.description or store.name,

            # Store theme colors (used as CSS variables in base.html)
            "STORE_PRIMARY": store.primary_color or "#06b6d4",
            "STORE_SECONDARY": store.secondary_color or "#0891b2",
            "STORE_BUTTON_COLOR": store.button_color or store.primary_color or "#06b6d4",
            "STORE_BG": store.background_color or "#0f172a",
            "STORE_TEXT": store.text_color or "#f8fafc",
            "STORE_FONT": store.theme_font or "Cairo",
            "STORE_CARD_STYLE": store.card_style or "flat",
            "STORE_HEADER_STYLE": store.header_style or "classic",
            "STORE_FOOTER_STYLE": store.footer_style or "classic",
            "STORE_BUTTON_STYLE": store.button_style or "pill",
            "STORE_SHADOW_STYLE": store.shadow_style or "soft",
            "STORE_CUSTOM_CSS": store.custom_css or "",

            # Store contact details
            "STORE_PHONE": store.phone or "",
            "STORE_EMAIL": store.email or "",
            "STORE_ADDRESS": store.address or "",

            # Store social links
            "STORE_FACEBOOK": store.social_facebook or "",
            "STORE_INSTAGRAM": store.social_instagram or "",
            "STORE_TWITTER": store.social_twitter or "",
            "STORE_TIKTOK": store.social_tiktok or "",

            # Store subscription info (for feature gating in templates)
            "STORE_PLAN": store.subscription_plan,
        }
    else:
        # Main Raqamiyat platform — no store, use platform defaults
        return {
            "PLATFORM_URL": platform_url,
            "store": None,
            "is_tenant": False,

            # Default platform branding
            "STORE_NAME": "رقميات",
            "STORE_LOGO": None,
            "STORE_BANNER": None,
            "STORE_DESCRIPTION": "رقميات | منصة الخدمات الرقمية",

            # Default platform theme (matches Raqamiyat design)
            "STORE_PRIMARY": "#06b6d4",
            "STORE_SECONDARY": "#0891b2",
            "STORE_BUTTON_COLOR": "#06b6d4",
            "STORE_BG": "#0f172a",
            "STORE_TEXT": "#f8fafc",
            "STORE_FONT": "Cairo",
            "STORE_CARD_STYLE": "glass",
            "STORE_HEADER_STYLE": "classic",
            "STORE_FOOTER_STYLE": "classic",
            "STORE_BUTTON_STYLE": "pill",
            "STORE_SHADOW_STYLE": "soft",
            "STORE_CUSTOM_CSS": "",

            # No contact details on main site (handled separately)
            "STORE_PHONE": "",
            "STORE_EMAIL": "",
            "STORE_ADDRESS": "",
            "STORE_FACEBOOK": "",
            "STORE_INSTAGRAM": "",
            "STORE_TWITTER": "",
            "STORE_TIKTOK": "",

            "STORE_PLAN": None,
        }

