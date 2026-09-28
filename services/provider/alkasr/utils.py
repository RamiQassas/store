"""
Utility functions for Alkasr Provider integration.
Handles logging, data serialization, and metric recording.
"""

import logging
import time
from typing import Dict, Any

logger = logging.getLogger("provider.alkasr")


def mask_secrets(data: Any) -> Any:
    """Masks sensitive authentication tokens and passwords from payload before logging."""
    if not data:
        return data
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("token", "api-token", "secret", "password", "api_token")):
                masked[k] = "***MASKED***"
            elif isinstance(v, (dict, list)):
                masked[k] = mask_secrets(v)
            else:
                masked[k] = v
        return masked
    elif isinstance(data, (list, tuple)):
        return [mask_secrets(item) for item in data]
    return data


def log_request(profile, endpoint: str, method: str, payload: Any = None):
    """Logs provider outgoing requests cleanly with masked secrets."""
    clean_payload = mask_secrets(payload) if payload else None
    logger.info(f"[Alkasr API Request] Profile={profile} Method={method} Endpoint={endpoint} Payload={clean_payload}")


def log_response(profile, status_code: int, duration_ms: float, response_data: Any = None):
    """Logs provider incoming responses cleanly."""
    logger.info(f"[Alkasr API Response] Profile={profile} Status={status_code} Duration={duration_ms:.2f}ms")


def record_transaction_log(profile, endpoint: str, method: str, payload: Any, response_data: Any, status_code: int, duration_ms: float, is_success: bool, error_code: str = None, error_message: str = None):
    """
    Records request/response in ProviderRequestLog and ProviderResponseLog database models.
    Guarantees secrets and tokens are masked.
    """
    try:
        from apps.providers.models import ProviderRequestLog, ProviderResponseLog, ProviderErrorLog
        import json

        if not profile or not getattr(profile, "pk", None):
            return

        safe_payload = mask_secrets(payload)
        safe_response = mask_secrets(response_data) if isinstance(response_data, (dict, list)) else response_data

        str_payload = json.dumps(safe_payload, ensure_ascii=False) if isinstance(safe_payload, (dict, list)) else str(safe_payload or "")
        str_response = json.dumps(safe_response, ensure_ascii=False) if isinstance(safe_response, (dict, list)) else str(safe_response or "")

        # Extra safety check against leaking raw token
        if "api-token" in str_payload.lower() or "apitoken" in str_payload.lower():
            import re
            str_payload = re.sub(r'("?(?:api-?token)"?\s*:\s*)"[^"]+"', r'\1"***MASKED***"', str_payload, flags=re.I)

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

