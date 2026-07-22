import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.utils import timezone
import logging

from apps.providers.models import ProviderRequestLog, ProviderResponseLog, ProviderErrorLog
from .constants import DEFAULT_BASE_URL, TIMEOUT, MAX_RETRIES, ERROR_MAPPING
from .exceptions import NetworkError, AuthenticationError, BalanceError, APIError

logger = logging.getLogger(__name__)

class AlkasrClient:
    def __init__(self, profile):
        self.profile = profile
        self.api_token = profile.api_token
        self.base_url = profile.base_url or DEFAULT_BASE_URL
        self.session = self._build_session()

    def _build_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def request(self, action, payload=None):
        from apps.catalog.models import APITransaction
        
        data = payload or {}
        data["api_token"] = self.api_token
        data["key"] = self.api_token
        data["action"] = action

        url = self.base_url.rstrip("/") + "/api/v2"
        if not url.startswith("http"):
            url = "https://" + url

        # Create Request Log
        req_log = ProviderRequestLog.objects.create(
            profile=self.profile,
            endpoint=url,
            method="POST",
            payload=str({k: v for k, v in data.items() if k not in ("api_token", "key")})
        )

        start_time = time.time()
        
        try:
            response = self.session.post(
                url, 
                data=data, 
                headers={"User-Agent": "AlkasrClient/2.0"},
                timeout=TIMEOUT
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            req_log.execution_time_ms = elapsed_ms
            req_log.save(update_fields=["execution_time_ms"])

            res_log = ProviderResponseLog.objects.create(
                request_log=req_log,
                status_code=response.status_code,
                body=response.text[:5000],  # Truncate if too long
                is_success=False
            )

            try:
                json_resp = response.json()
            except ValueError:
                json_resp = {}

            is_success = response.status_code == 200 and json_resp.get("status") not in ("error", "failed")

            # Create APITransaction for template rendering
            APITransaction.objects.create(
                store=self.profile.store,
                provider=self.profile.provider_name,
                action=action,
                product_id=str(data.get("product_id", "")),
                order_uuid=str(data.get("order_uuid", "")),
                request_url=url,
                request_params=str({k: v for k, v in data.items() if k not in ("api_token", "key")}),
                response_status=response.status_code,
                response_body=response.text[:5000],
                is_success=is_success,
                error_message=json_resp.get("message") or json_resp.get("error", "") if not is_success else ""
            )

            response.raise_for_status()
            
            if json_resp.get("status") == "error":
                res_log.is_success = False
                res_log.save(update_fields=["is_success"])
                self._handle_api_error(json_resp, req_log)

            res_log.is_success = True
            res_log.save(update_fields=["is_success"])
            return json_resp

        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            req_log.execution_time_ms = elapsed_ms
            req_log.save(update_fields=["execution_time_ms"])
            
            ProviderErrorLog.objects.create(
                profile=self.profile,
                message=f"Network Error: {str(e)}",
                related_request=req_log
            )
            raise NetworkError(f"فشل الاتصال بالمزود: {str(e)}") from e
        except ValueError as e:
            ProviderErrorLog.objects.create(
                profile=self.profile,
                message=f"Invalid JSON response: {str(e)}",
                related_request=req_log
            )
            raise NetworkError("استجابة غير صالحة من المزود.") from e

    def _handle_api_error(self, json_resp, req_log):
        raw_msg = json_resp.get("message") or json_resp.get("error") or ""
        
        # Try to extract ERR-XXX
        import re
        code = None
        m = re.search(r"ERR-(\d+)", raw_msg)
        if m:
            code = int(m.group(1))

        error_message = ERROR_MAPPING.get(code, "خطأ غير معروف من المزود.") if code else raw_msg

        ProviderErrorLog.objects.create(
            profile=self.profile,
            error_code=str(code) if code else None,
            message=error_message,
            traceback=raw_msg,
            related_request=req_log
        )

        if code == 100:
            raise BalanceError(error_message, code, json_resp)
        elif code in (120, 121):
            raise AuthenticationError(error_message, code, json_resp)
        
        raise APIError(error_message, code, json_resp)
