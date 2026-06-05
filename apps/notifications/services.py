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

def notify_user(user, title, body, action_url=None, image_url=None, channel=None, priority=Notification.Priority.NORMAL, metadata=None):
    """
    Centralized service to notify users via multiple channels.
    channel: can be 'in_app', 'push', 'email', or 'multi' (defaults based on type)
    """
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=user)
    
    # Smart Defaults: Support and Financial always get Push + In-App unless specified otherwise
    is_critical = False
    if metadata and metadata.get('type') in ['chat_reply', 'deposit_update', 'withdrawal_update', 'order_critical']:
        is_critical = True

    # If no channel specified, determine based on criticality
    target_channels = []
    if channel == 'multi':
        target_channels = ['in_app', 'push']
    elif channel:
        target_channels = [channel]
    elif is_critical:
        target_channels = ['in_app', 'push']
    else:
        target_channels = ['in_app']

    # 1. Create In-App Notification record if requested
    if 'in_app' in target_channels:
        Notification.objects.create(
            user=user,
            title=title,
            body=body,
            action_url=action_url,
            image_url=image_url,
            channel=Notification.Channel.IN_APP,
            priority=priority,
            metadata=metadata or {}
        )

    # 2. Trigger Web Push if requested and subscribed
    if 'push' in target_channels:
        subscriptions = PushSubscription.objects.filter(user=user)
        if subscriptions.exists():
            payload = {
                "title": title,
                "body": body,
                "action_url": action_url or "/dashboard/",
                "image": image_url
            }
            for sub in subscriptions:
                send_web_push(sub, payload)
    
    return True

def notify_bulk(users, title, body, **kwargs):
    """Sends notification to multiple users at once."""
    for user in users:
        notify_user(user, title, body, **kwargs)
