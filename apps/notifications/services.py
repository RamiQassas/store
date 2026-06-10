import json
import logging
import hashlib
from pywebpush import webpush, WebPushException
from django.conf import settings
from django.utils import timezone
from django.db import models
from apps.notifications.models import Notification, NotificationSetting, PushSubscription

logger = logging.getLogger(__name__)

def generate_deduplication_hash(user_id, title, body, metadata):
    """Generates a unique hash for a notification to prevent spam within a short window."""
    raw_str = f"{user_id}:{title}:{body}:{json.dumps(metadata or {}, sort_keys=True)}"
    return hashlib.md5(raw_str.encode()).hexdigest()

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
        if e.response and e.response.status_code in [404, 410]:
            subscription.delete()
        return False
    except Exception as e:
        logger.error(f"Unexpected Push Error: {str(e)}")
        return False

def notify_user(user, title, body, action_url=None, image_url=None, category='system', priority=Notification.Priority.NORMAL, metadata=None, exclude_user=None):
    """
    Centralized service to notify users via multiple channels.
    category: 'orders', 'financial', 'support', 'promotions', 'system'
    """
    if not user.is_active or (exclude_user and user.id == exclude_user.id):
        return False

    # 1. Deduplication (Short window: 1 minute)
    # Check if a similar notification was sent recently to avoid spam
    dedup_hash = generate_deduplication_hash(user.id, title, body, metadata)
    one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
    if Notification.objects.filter(user=user, metadata__dedup_hash=dedup_hash, created_at__gte=one_minute_ago).exists():
        return False

    if metadata is None: metadata = {}
    metadata['dedup_hash'] = dedup_hash

    # 2. Check User Preferences
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=user)
    
    send_in_app = False
    send_push = False

    if category == 'orders':
        send_in_app = settings_obj.in_app_orders
        send_push = settings_obj.push_orders
    elif category == 'financial':
        send_in_app = settings_obj.in_app_financial
        send_push = settings_obj.push_financial
    elif category == 'support':
        send_in_app = settings_obj.in_app_support
        send_push = settings_obj.push_support
    elif category == 'promotions':
        send_in_app = settings_obj.in_app_promotions
        send_push = settings_obj.push_promotions
    else: # system
        send_in_app = True
        send_push = True

    # 3. Create In-App Notification
    if send_in_app:
        Notification.objects.create(
            user=user,
            title=title,
            body=body,
            action_url=action_url,
            image_url=image_url,
            channel=Notification.Channel.IN_APP,
            priority=priority,
            metadata=metadata
        )

    # 4. Trigger Web Push
    if send_push:
        subscriptions = PushSubscription.objects.filter(user=user)
        if subscriptions.exists():
            payload = {
                "title": title,
                "body": body,
                "action_url": action_url or "/dashboard/",
                "image": image_url,
                "tag": dedup_hash # For browser-side dedup
            }
            for sub in subscriptions:
                send_web_push(sub, payload)
    
    return True

def notify_bulk(users, title, body, **kwargs):
    """Sends notification to multiple users at once."""
    for user in users:
        notify_user(user, title, body, **kwargs)

def notify_staff(title, body, action_url=None, roles=None, priority=Notification.Priority.NORMAL, metadata=None, exclude_user=None):
    """
    Sends notification to staff members.
    If roles is provided, only notify users with those roles.
    Otherwise, notify all admin/staff users.
    """
    from apps.accounts.models import User
    
    staff_query = User.objects.filter(is_active=True)
    
    if roles:
        staff_query = staff_query.filter(role__in=roles)
    else:
        # Default staff roles that should receive notifications
        staff_roles = [
            User.Role.SUPER_ADMIN,
            User.Role.ADMIN,
            User.Role.MODERATOR,
            User.Role.FINANCE,
            User.Role.SUPPORT,
            User.Role.EMPLOYEE
        ]
        staff_query = staff_query.filter(models.Q(role__in=staff_roles) | models.Q(is_staff=True) | models.Q(is_superuser=True))
    
    staff_users = staff_query.distinct()
    return notify_bulk(staff_users, title, body, action_url=action_url, category='support', priority=priority, metadata=metadata, exclude_user=exclude_user)
