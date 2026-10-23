from decimal import Decimal
from django.db.models import Count, Q
from apps.common.models import Currency, SocialMediaLink, MetaPixelConfiguration
from apps.common.security import sanitize_custom_css
from apps.payments.models import PaymentMethod


def _build_cart_context(request, pref_currency=None):
    """
    Builds server-validated cart items, count, and total from session['rq_cart'].
    Prices are always fetched live from the database (never trusted from session).
    """
    session = getattr(request, "session", None)
    if not session:
        return {"cart_items": [], "cart_items_count": 0, "cart_total": Decimal("0.00")}

    raw_cart = session.get("rq_cart")
    if not raw_cart or not isinstance(raw_cart, dict):
        return {"cart_items": [], "cart_items_count": 0, "cart_total": Decimal("0.00")}

    try:
        from apps.catalog.models import ProductVariant
        variant_ids = list(raw_cart.keys())
        variants_qs = ProductVariant.all_objects.filter(
            id__in=variant_ids,
            is_active=True,
            product__is_active=True,
            product__is_publicly_visible=True,
        ).select_related("product", "product__category")
        variants_map = {str(v.id): v for v in variants_qs}

        user = getattr(request, "user", None)
        cart_items = []
        cart_items_count = 0
        cart_total = Decimal("0.00")
        cleaned_cart = {}

        for v_id, item_data in raw_cart.items():
            variant = variants_map.get(str(v_id))
            if not variant or not variant.product:
                continue
            product = variant.product
            try:
                qty = int(item_data.get("quantity", 1))
            except (ValueError, TypeError):
                qty = 1
            if qty < 1:
                continue
            if product.track_inventory and product.quantity > 0:
                qty = min(qty, product.quantity)

            unit_price = (
                Decimal(str(variant.price))
                if (variant.price and variant.price > Decimal("0.00"))
                else variant.get_price_for_user(user)
            )
            line_total = (unit_price * Decimal(qty)).quantize(Decimal("0.01"))
            is_available = (
                not product.is_out_of_stock
                and not variant.is_temporarily_disabled
                and (not product.track_inventory or product.quantity >= qty)
            )

            cart_items.append({
                "key": str(variant.id),
                "variant_id": str(variant.id),
                "product_id": str(product.id),
                "name": product.name,
                "variant_name": variant.name if variant.name != product.name else "",
                "category_name": product.category.name if product.category else "",
                "product_type": product.product_type,
                "image": product.image_url or "",
                "quantity": qty,
                "max_quantity": product.quantity if product.track_inventory and product.quantity > 0 else 99,
                "unit_price": unit_price,
                "total_price": line_total,
                "is_available": is_available,
                "metadata": item_data.get("metadata", {}),
            })
            cart_items_count += qty
            cart_total += line_total
            cleaned_cart[str(variant.id)] = {
                "product_id": str(product.id),
                "variant_id": str(variant.id),
                "quantity": qty,
                "metadata": item_data.get("metadata", {}),
            }

        if len(cleaned_cart) != len(raw_cart):
            session["rq_cart"] = cleaned_cart
            session.modified = True

        return {
            "cart_items": cart_items,
            "cart_items_count": cart_items_count,
            "cart_total": cart_total,
        }
    except Exception:
        return {"cart_items": [], "cart_items_count": 0, "cart_total": Decimal("0.00")}


def _build_nav_categories(store=None):
    """
    Returns actual active categories from the database that exist in the store.
    """
    try:
        from apps.catalog.models import Category
        store_q = Q(store=store) if store else Q(store__isnull=True)
        cats = list(
            Category.all_objects.filter(store_q, is_active=True)
            .annotate(
                active_products_count=Count(
                    "products",
                    filter=Q(products__is_active=True, products__is_publicly_visible=True),
                )
            )
            .filter(active_products_count__gt=0)
            .order_by("sort_order", "name")[:14]
        )
        if not cats:
            cats = list(
                Category.all_objects.filter(store_q, is_active=True)
                .order_by("sort_order", "name")[:14]
            )
        return cats
    except Exception:
        return []


def preferred_currency(request):
    """
    Determines the preferred currency for the current user or guest session.
    Returns:
        Currency object, active currencies, payment methods, actual nav_categories, social_links, and live cart context.
    """
    store = getattr(request, "store", None)
    if store and not Currency.all_objects.filter(store=store).exists():
        global_currencies = Currency.all_objects.filter(store__isnull=True)
        for gc in global_currencies:
            Currency.all_objects.create(
                store=store,
                name=gc.name,
                code=gc.code,
                symbol=gc.symbol,
                buy_rate=gc.buy_rate,
                sell_rate=gc.sell_rate,
                capital_rate=gc.capital_rate,
                conversion_method=gc.conversion_method,
                decimal_places=gc.decimal_places,
                display_order=gc.display_order,
                is_active=gc.is_active,
                is_default=gc.is_default
            )

    if store:
        all_currencies = list(Currency.all_objects.filter(store=store, is_active=True).order_by("display_order", "code"))
    else:
        all_currencies = list(Currency.all_objects.filter(store__isnull=True, is_active=True).order_by("display_order", "code"))
    
    pref_currency = None
    user = getattr(request, "user", None)
    session = getattr(request, "session", None)
    
    # 1. Check logged in user preference
    if user and user.is_authenticated and getattr(user, "preferred_currency", None):
        user_pref = user.preferred_currency
        if user_pref in all_currencies:
            pref_currency = user_pref
        else:
            pref_currency = next((c for c in all_currencies if c.code == user_pref.code), None)
    
    # 2. Check session for guest/override
    if not pref_currency and session:
        session_currency_id = session.get("preferred_currency_id")
        if session_currency_id:
            pref_currency = next((c for c in all_currencies if str(c.id) == str(session_currency_id)), None)
    
    # 3. Fallback to default currency
    if not pref_currency:
        pref_currency = next((c for c in all_currencies if getattr(c, 'is_default', False)), None)
    
    # 4. Absolute fallback to first active currency
    if not pref_currency and all_currencies:
        pref_currency = all_currencies[0]

    system_currency = next((c for c in all_currencies if c.code == "USD"), None) or (all_currencies[0] if all_currencies else None)

    payment_methods = PaymentMethod.objects.filter(is_active=True).order_by('display_order')
    social_links = list(SocialMediaLink.objects.filter(is_active=True).order_by("display_order"))
    nav_categories = _build_nav_categories(store=store)
    cart_ctx = _build_cart_context(request, pref_currency)

    return {
        "CURRENCY": pref_currency,
        "current_currency": pref_currency,
        "available_currencies": all_currencies,
        "ALL_CURRENCIES": all_currencies,
        "SYSTEM_CURRENCY": system_currency,
        "WITHDRAWAL_RATE": pref_currency.sell_rate if pref_currency else 1.0,
        "SOCIAL_LINKS": social_links,
        "social_links": social_links,
        "NAV_CATEGORIES": nav_categories,
        "nav_categories": nav_categories,
        "PAYMENT_METHODS": payment_methods,
        "payment_methods": payment_methods,
        **cart_ctx,
    }


def tenant_context(request):
    """
    Multi-Tenant Context Processor.
    
    Provides store branding data to ALL templates automatically.
    """
    try:
        from django.conf import settings
        from django.contrib.sites.models import Site
        site_id = getattr(settings, "SITE_ID", 1)
        site = Site.objects.filter(id=site_id).first()
        if not site:
            existing = Site.objects.filter(domain="raqamiyatapp.com").first() or Site.objects.first()
            if existing:
                if existing.id != site_id:
                    Site.objects.filter(id=existing.id).update(id=site_id, domain="raqamiyatapp.com", name="Raqamiyat")
                elif existing.domain != "raqamiyatapp.com":
                    existing.domain = "raqamiyatapp.com"
                    existing.name = "Raqamiyat"
                    existing.save(update_fields=["domain", "name"])
            else:
                Site.objects.create(id=site_id, domain="raqamiyatapp.com", name="Raqamiyat")
    except Exception:
        pass
    platform_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
    store = getattr(request, 'store', None)
    
    if store:
        from urllib.parse import quote
        next_target = request.GET.get("next") or "/dashboard/"
        if not next_target.startswith("http://") and not next_target.startswith("https://"):
            next_target = request.build_absolute_uri(next_target)

        sso_callback = f"{platform_url}/auth/sso-callback/?store_id={store.pk}&subdomain={store.subdomain}&next={quote(next_target)}"
        sso_google_login_url = f"{platform_url}/accounts/google/login/?store_id={store.pk}&subdomain={store.subdomain}&next={quote(sso_callback)}"

        pixel_config = MetaPixelConfiguration.get_settings(store=store)
        pixel_id = pixel_config.pixel_id.strip() if (pixel_config and pixel_config.is_active and pixel_config.pixel_id) else None

        return {
            "PLATFORM_URL": platform_url,
            "SSO_GOOGLE_LOGIN_URL": sso_google_login_url,
            "store": store,
            "is_tenant": True,
            "STORE_NAME": store.name,
            "STORE_LOGO": store.logo if store.logo else None,
            "STORE_BANNER": store.banner if store.banner else None,
            "STORE_DESCRIPTION": store.description or store.name,
            "STORE_PRIMARY": store.primary_color or "#3b82f6",
            "STORE_SECONDARY": store.secondary_color or "#2563eb",
            "STORE_BUTTON_COLOR": store.button_color or store.primary_color or "#2563eb",
            "STORE_BG": store.background_color or "#070b14",
            "STORE_TEXT": store.text_color or "#f8fafc",
            "STORE_FONT": store.theme_font or "Cairo",
            "STORE_CARD_STYLE": store.card_style or "flat",
            "STORE_HEADER_STYLE": store.header_style or "classic",
            "STORE_FOOTER_STYLE": store.footer_style or "classic",
            "STORE_BUTTON_STYLE": store.button_style or "pill",
            "STORE_SHADOW_STYLE": store.shadow_style or "soft",
            "STORE_CUSTOM_CSS": sanitize_custom_css(store.custom_css or ""),
            "STORE_PHONE": store.phone or "",
            "STORE_EMAIL": store.email or "",
            "STORE_ADDRESS": store.address or "",
            "STORE_FACEBOOK": store.social_facebook or "",
            "STORE_INSTAGRAM": store.social_instagram or "",
            "STORE_TWITTER": store.social_twitter or "",
            "STORE_TIKTOK": store.social_tiktok or "",
            "STORE_PLAN": store.subscription_plan,
            "META_PIXEL_CONFIG": pixel_config,
            "META_PIXEL_ID": pixel_id,
        }
    else:
        pixel_config = MetaPixelConfiguration.get_settings(store=None)
        pixel_id = pixel_config.pixel_id.strip() if (pixel_config and pixel_config.is_active and pixel_config.pixel_id) else None

        return {
            "PLATFORM_URL": platform_url,
            "SSO_GOOGLE_LOGIN_URL": "/accounts/google/login/",
            "store": None,
            "is_tenant": False,
            "STORE_NAME": "رقميات",
            "STORE_LOGO": None,
            "STORE_BANNER": None,
            "STORE_DESCRIPTION": "رقميات | متجر الإلكترونيات والتقنية والخدمات الرقمية",
            "STORE_PRIMARY": "#3b82f6",
            "STORE_SECONDARY": "#2563eb",
            "STORE_BUTTON_COLOR": "#2563eb",
            "STORE_BG": "#070b14",
            "STORE_TEXT": "#f8fafc",
            "STORE_FONT": "Cairo",
            "STORE_CARD_STYLE": "flat",
            "STORE_HEADER_STYLE": "classic",
            "STORE_FOOTER_STYLE": "classic",
            "STORE_BUTTON_STYLE": "pill",
            "STORE_SHADOW_STYLE": "soft",
            "STORE_CUSTOM_CSS": "",
            "STORE_PHONE": "",
            "STORE_EMAIL": "",
            "STORE_ADDRESS": "",
            "STORE_FACEBOOK": "",
            "STORE_INSTAGRAM": "",
            "STORE_TWITTER": "",
            "STORE_TIKTOK": "",
            "STORE_PLAN": None,
            "META_PIXEL_CONFIG": pixel_config,
            "META_PIXEL_ID": pixel_id,
        }
