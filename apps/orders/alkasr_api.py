import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def get_alkasr_profile():
    """
    Fetches Alkasr profile information (balance and email).
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/profile"
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to fetch Alkasr profile")
        return {"status": "error", "message": str(e)}

def place_alkasr_order(api_product_id, qty, order_uuid, metadata):
    """
    Sends a request to create a new order in Alkasr.
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/newOrder/{api_product_id}/params"
    
    # Base query parameters required by the API
    params = {
        "qty": qty,
        "order_uuid": str(order_uuid)
    }
    
    # Map metadata custom fields directly
    for k, v in metadata.items():
        params[k] = v
        
    # Check if we have playerId in parameters, if not try to map common aliases
    if 'playerId' not in params:
        for k, v in metadata.items():
            if any(x in k.lower() for x in ['player', 'id', 'user', 'account', 'ايدي', 'لاعب', 'حساب']):
                params['playerId'] = v
                break
                
    # Fallback to the first value if playerId is still not found but metadata is not empty
    if 'playerId' not in params and metadata:
        params['playerId'] = list(metadata.values())[0]
        
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    
    try:
        logger.info(f"Sending order to Alkasr: product_id={api_product_id}, qty={qty}, uuid={order_uuid}, params={params}")
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        logger.info(f"Alkasr order response: {response_json}")
        return response_json
    except Exception as e:
        logger.exception("Failed to place Alkasr order")
        return {"status": "error", "message": str(e)}

def check_alkasr_orders(order_identifiers, is_uuid=False):
    """
    Checks the status of one or multiple orders on Alkasr.
    order_identifiers can be a list of order IDs (e.g. ['ID_a37aaa06']) or a single UUID string.
    """
    if is_uuid:
        # Check by order UUID
        url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/check"
        params = {
            "orders": f"[{order_identifiers}]",
            "uuid": 1
        }
    else:
        # Check by order IDs
        url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/check"
        ids_str = ",".join(order_identifiers)
        params = {
            "orders": f"[{ids_str}]"
        }
        
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to check Alkasr order status")
        return {"status": "error", "message": str(e)}
