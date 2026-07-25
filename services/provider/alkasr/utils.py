"""
Utility functions for Alkasr Provider integration.
Handles logging, data serialization, and metric recording.
"""

import logging
import time
from typing import Dict, Any

logger = logging.getLogger("provider.alkasr")


def log_request(profile, endpoint: str, method: str, payload: Any = None):
    """Logs provider outgoing requests cleanly."""
    logger.info(f"[Alkasr API Request] Profile={profile} Method={method} Endpoint={endpoint}")


def log_response(profile, status_code: int, duration_ms: float, response_data: Any = None):
    """Logs provider incoming responses cleanly."""
    logger.info(f"[Alkasr API Response] Profile={profile} Status={status_code} Duration={duration_ms:.2f}ms")


def record_transaction_log(profile, endpoint: str, method: str, payload: Any, response_data: Any, status_code: int, duration_ms: float, is_success: bool, error_code: str = None, error_message: str = None):
    """
    Records request/response in ProviderRequestLog and ProviderResponseLog database models if present.
    """
    try:
        from apps.providers.models import ProviderRequestLog, ProviderResponseLog, ProviderErrorLog
        import json

        str_payload = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        str_response = json.dumps(response_data, ensure_ascii=False) if isinstance(response_data, (dict, list)) else str(response_data or "")

        req_log = ProviderRequestLog.objects.create(
            profile=profile,
            endpoint=endpoint,
            method=method,
            payload=str_payload,
            execution_time_ms=int(duration_ms)
        )
        ProviderResponseLog.objects.create(
            request_log=req_log,
            status_code=status_code,
            body=str_response,
            is_success=is_success
        )
        if not is_success and (error_code or error_message):
            ProviderErrorLog.objects.create(
                profile=profile,
                error_code=str(error_code or ""),
                message=str(error_message or "API Error"),
                related_request=req_log
            )
    except Exception as exc:
        logger.warning(f"Failed to record provider transaction log: {exc}")
