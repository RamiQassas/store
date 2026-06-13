import logging
import json
from decimal import Decimal
from uuid import UUID
from django.contrib.contenttypes.models import ContentType
from apps.common.models import SystemAuditLog

import requests

logger = logging.getLogger(__name__)

def get_ip_info(ip):
    """
    Fetches geolocation information for a given IP address.
    Uses ip-api.com (free for non-commercial use, 45 requests/min).
    """
    if not ip or ip in ["127.0.0.1", "::1"]:
        return {"country": "Local", "city": "Development", "isp": "Localhost"}
        
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data
    except Exception as e:
        logger.warning(f"Failed to fetch IP info for {ip}: {str(e)}")
        
    return {"country": "Unknown", "city": "Unknown"}

class AuditJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)

def log_system_action(actor, action_type, target=None, description="", before_state=None, after_state=None, ip_address=None, user_agent="", reason="", metadata=None):
    """
    Utility function to create a SystemAuditLog entry.
    Ensures data is JSON serializable.
    """
    try:
        content_type = None
        object_id = None
        
        if target:
            content_type = ContentType.objects.get_for_model(target)
            object_id = str(target.pk)
            
        # Clean data for JSON storage
        def clean_data(data):
            if not data: return {}
            return json.loads(json.dumps(data, cls=AuditJSONEncoder))

        return SystemAuditLog.objects.create(
            actor=actor,
            action_type=action_type,
            content_type=content_type,
            object_id=object_id,
            description=description,
            before_state=clean_data(before_state),
            after_state=clean_data(after_state),
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason,
            metadata=clean_data(metadata)
        )
    except Exception as e:
        logger.error(f"Failed to log system action: {str(e)}")
        raise e # Re-raise to let the caller handle it or for debugging
