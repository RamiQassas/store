import json
import logging
from pywebpush import webpush, WebPushException
from django.conf import settings
from apps.notifications.models import Notification, NotificationSetting, PushSubscription

logger = logging.getLogger(__name__)

def send_web_push(subscription, payload):
    """Internal helper to deliver a single push via pywebpush."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth
                }
            },
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={
                "sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"
            }
        )
        return True
    except WebPushException as e:
        logger.error(f"WebPush Error: {str(e)}")
        # If the subscription is no longer valid, we should delete it
        if e.response and e.response.status_code in [404, 410]:
            subscription.delete()
        return False
    except Exception as e:
        logger.error(f"Unexpected Push Error: {str(e)}")
        return False

def notify_user(user, title, body, action_url=None, image_url=None, channel=Notification.Channel.IN_APP, priority=Notification.Priority.NORMAL, metadata=None):
    """
    Centralized service to notify users via multiple channels.
    Includes Real Browser Web Push.
    """
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=user)
    
    # Save in-app notification first
    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        action_url=action_url,
        image_url=image_url,
        channel=channel,
        priority=priority,
        metadata=metadata or {}
    )
    
    # Trigger Web Push for all active subscriptions
    subscriptions = PushSubscription.objects.filter(user=user)
    if subscriptions.exists():
        payload = {
            "title": title,
            "body": body,
            "action_url": action_url or "/dashboard/",
            "image": image_url
        }
        for sub in subscriptions:
            # We could use Celery here for truly non-blocking push
            send_web_push(sub, payload)
    
    if channel == Notification.Channel.PUSH:
        # PUSH channel is handled above by iterating subscriptions
        pass
        
    return notification

def notify_bulk(users, title, body, **kwargs):
    """Sends notification to multiple users at once."""
    for user in users:
        notify_user(user, title, body, **kwargs)
