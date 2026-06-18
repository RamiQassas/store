from django.db.models.signals import post_save, pre_delete
from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from apps.accounts.models import User, SecurityEvent
from apps.wallets.services import get_or_create_wallet
from apps.common.services import get_ip_info

@receiver(pre_delete, sender=User)
def clear_user_sessions_on_delete(sender, instance, **kwargs):
    """Ensure user session is deleted when the user account is deleted."""
    if instance.last_session_key:
        Session.objects.filter(session_key=instance.last_session_key).delete()



@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        get_or_create_wallet(instance)

@receiver(user_logged_in)
def update_user_ip_info(sender, request, user, **kwargs):
    """Updates user's last IP and location upon login and logs to history."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    user.last_ip = ip
    info = get_ip_info(ip)
    user.last_country = info.get("country", "Unknown")
    user.last_city = info.get("city", "Unknown")
    user.save(update_fields=["last_ip", "last_country", "last_city"])

    # Create detailed history entry
    SecurityEvent.objects.create(
        user=user,
        event_type=SecurityEvent.EventType.LOGIN,
        ip_address=ip,
        country=user.last_country,
        city=user.last_city,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        metadata={
            "isp": info.get("isp"),
            "org": info.get("org"),
            "as": info.get("as")
        }
    )
