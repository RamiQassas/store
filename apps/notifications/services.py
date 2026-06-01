from apps.notifications.models import Notification

def notify_user(user, title, body, action_url=None, channel=Notification.Channel.IN_APP, priority=Notification.Priority.NORMAL, metadata=None):
    """
    Centralized service to notify users via multiple channels.
    Currently supports IN_APP, extensible to EMAIL and PUSH.
    """
    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        action_url=action_url,
        channel=channel,
        priority=priority,
        metadata=metadata or {}
    )
    
    if channel == Notification.Channel.EMAIL:
        # TODO: Implement Email delivery (Phase 9 architecture stub)
        pass
    
    if channel == Notification.Channel.PUSH:
        # TODO: Implement Push delivery
        pass
        
    return notification
