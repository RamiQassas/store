from django.conf import settings

def webpush_settings(request):
    """
    Exposes VAPID public key to all templates for browser push subscription.
    """
    return {
        "VAPID_PUBLIC_KEY": getattr(settings, "VAPID_PUBLIC_KEY", "")
    }

def common_context(request):
    from apps.common.models import Currency
    from apps.accounts.models import KYCRequest
    return {
        "ALL_CURRENCIES": Currency.objects.filter(is_active=True).order_by("display_order"),
        "PENDING_KYC_COUNT": KYCRequest.objects.filter(status=KYCRequest.Status.PENDING).count() if request.user.is_staff else 0
    }
