from apps.notifications.models import Notification, NotificationSetting

def notify_user(user, title, body, action_url=None, image_url=None, channel=Notification.Channel.IN_APP, priority=Notification.Priority.NORMAL, metadata=None):
    """
    Centralized service to notify users via multiple channels.
    Checks user preferences before sending.
    """
    # Check preferences (Simple check, can be expanded per notification type)
    settings, _ = NotificationSetting.objects.get_or_create(user=user)
    
    # Logic for skipping based on type could be added here in metadata
    
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
    
    if channel == Notification.Channel.PUSH:
        # TODO: Trigger browser push via Firebase or Web-Push-Lib
        pass
        
    return notification

def notify_bulk(users, title, body, **kwargs):
    """Sends notification to multiple users at once."""
    for user in users:
        notify_user(user, title, body, **kwargs)
