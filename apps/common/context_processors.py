from django.conf import settings

def webpush_settings(request):
    """
    Exposes VAPID public key to all templates for browser push subscription.
    """
    return {
        "VAPID_PUBLIC_KEY": getattr(settings, "VAPID_PUBLIC_KEY", "")
    }
