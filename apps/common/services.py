import logging
from django.contrib.contenttypes.models import ContentType
from apps.common.models import SystemAuditLog

logger = logging.getLogger(__name__)

def log_system_action(actor, action_type, target=None, description="", before_state=None, after_state=None, ip_address=None, user_agent="", reason="", metadata=None):
    """
    Utility function to create a SystemAuditLog entry.
    """
    try:
        content_type = None
        object_id = None
        
        if target:
            content_type = ContentType.objects.get_for_model(target)
            object_id = str(target.pk)
            
        return SystemAuditLog.objects.create(
            actor=actor,
            action_type=action_type,
            content_type=content_type,
            object_id=object_id,
            description=description,
            before_state=before_state or {},
            after_state=after_state or {},
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason,
            metadata=metadata or {}
        )
    except Exception as e:
        logger.error(f"Failed to log system action: {str(e)}")
        return None
