from django.conf import settings

def webpush_settings(request):
    """
    Exposes VAPID public key to all templates for browser push subscription.
    """
    return {
        "VAPID_PUBLIC_KEY": getattr(settings, "VAPID_PUBLIC_KEY", "")
    }

def common_context(request):
    from apps.common.models import Currency, SiteAnnouncement, SiteFeatureFlag
    from apps.accounts.models import KYCRequest
    from apps.notifications.models import Notification
    
    active_store = getattr(request, "store", None)
    user = getattr(request, "user", None)
    is_staff = user.is_staff if (user and user.is_authenticated) else False
    
    if active_store:
        all_currencies = Currency.all_objects.filter(store=active_store, is_active=True).order_by("display_order", "code")
    else:
        all_currencies = Currency.all_objects.filter(store__isnull=True, is_active=True).order_by("display_order", "code")

    # Load feature flags for current store/platform
    features = SiteFeatureFlag.get_all_flags_dict(store=active_store)

    # Load active site payment gateways dynamically from DB with real names and logos
    site_gateways = []
    try:
        from apps.payments.models import PaymentGatewayIntegration, PaymentMethod
        from apps.common.tenant_utils import bypass_tenant_filter
        from django.db.models import Q
        with bypass_tenant_filter():
            if active_store:
                gw_qs = list(PaymentGatewayIntegration.all_objects.filter(
                    Q(store=active_store) | Q(store__isnull=True),
                    is_active=True
                ).order_by("store_id"))
            else:
                gw_qs = list(PaymentGatewayIntegration.all_objects.filter(
                    store__isnull=True,
                    is_active=True
                ))

            def _gw_order(g):
                if g.provider == "sham_cash": return 0
                if g.provider == "paymera": return 1
                return 2

            gw_qs.sort(key=_gw_order)
            seen_providers = set()
            for g in gw_qs:
                if g.provider in seen_providers:
                    continue
                seen_providers.add(g.provider)

                pm = PaymentMethod.all_objects.filter(gateway=g, is_active=True).first()
                name = (pm.name if pm and pm.name else "") or g.name or g.get_provider_display()
                logo_url = ""
                if pm and pm.logo:
                    try: logo_url = pm.logo.url
                    except Exception: pass
                if not logo_url and g.logo:
                    try: logo_url = g.logo.url
                    except Exception: pass
                if not logo_url and g.logo_url:
                    logo_url = g.logo_url
                if not logo_url:
                    if g.provider == "sham_cash":
                        logo_url = "/media/payment-methods/logos/shamcash.svg"
                    elif g.provider == "paymera":
                        logo_url = "/media/payment-methods/logos/paymera.png"

                site_gateways.append({
                    "provider": g.provider,
                    "name": name,
                    "logo_url": logo_url,
                })
    except Exception:
        pass

    context = {
        "ALL_CURRENCIES": all_currencies,
        "available_currencies": all_currencies,
        "SITE_GATEWAYS": site_gateways,
        "PENDING_KYC_COUNT": KYCRequest.objects.filter(status=KYCRequest.Status.PENDING).count() if is_staff else 0,
        "active_announcement": SiteAnnouncement.all_objects.filter(store=active_store, is_active=True).first(),
        "FEATURES": features,
        "features": features,
    }
    
    if user and user.is_authenticated:
        context["UNREAD_NOTIFICATIONS_COUNT"] = Notification.objects.filter(user=user, is_read=False).count()
        context["RECENT_NOTIFICATIONS"] = Notification.objects.filter(user=user).order_by("-created_at")[:10]
        
    return context
