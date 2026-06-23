from django.conf import settings

def webpush_settings(request):
    """
    Exposes VAPID public key to all templates for browser push subscription.
    """
    return {
        "VAPID_PUBLIC_KEY": getattr(settings, "VAPID_PUBLIC_KEY", "")
    }

def common_context(request):
    from apps.common.models import Currency, SiteAnnouncement
    from apps.accounts.models import KYCRequest
    from apps.notifications.models import Notification
    
    active_store = getattr(request, "store", None)
    
    context = {
        "ALL_CURRENCIES": Currency.objects.filter(is_active=True).order_by("display_order"),
        "PENDING_KYC_COUNT": KYCRequest.objects.filter(status=KYCRequest.Status.PENDING).count() if request.user.is_staff else 0,
        "active_announcement": SiteAnnouncement.all_objects.filter(store=active_store, is_active=True).first()
    }
    
    if request.user.is_authenticated:
        context["UNREAD_NOTIFICATIONS_COUNT"] = Notification.objects.filter(user=request.user, is_read=False).count()
        context["RECENT_NOTIFICATIONS"] = Notification.objects.filter(user=request.user).order_by("-created_at")[:10]
        
    return context
