import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from urllib.parse import urljoin

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
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def request(self, action, payload=None, endpoint_override=None):
        from apps.catalog.models import APITransaction
        
        data = payload or {}
        headers = {
            "api-token": self.api_token,
            "User-Agent": "AlkasrClient/2.0"
        }

        base = self.base_url.rstrip("/")
        if "webhook" in base.lower() or "raqamiyatapp.com/api/orders" in base.lower():
            raise NetworkError(
                "رابط المزود غير صحيح: لقد قمت بإدخال رابط الـ Webhook الخاص بمتجرك بدلاً من رابط API المزود الخارجي (مثال: https://api.alkasr-vip.com). يرجى تعديل 'رابط المزود' من صفحة إعدادات البوابات."
            )

        # Automatically strip documentation paths if user entered docs page URL
        for doc_path in ["/api-docs", "/docs", "/documentation", "/swagger"]:
            if base.endswith(doc_path):
                base = base[:-len(doc_path)].rstrip("/")
            elif doc_path in base:
                base = base.replace(doc_path, "").rstrip("/")

        if not base.startswith("http"):
            base = "https://" + base

        # Determine relative endpoint according to Alkasr VIP docs
        if endpoint_override:
            rel_path = endpoint_override if endpoint_override.startswith("/") else "/" + endpoint_override
        elif action == "profile":
            rel_path = "/client/api/profile"
        elif action == "products":
            rel_path = "/client/api/products"
        elif action == "content":
            cat_id = data.get("category", 0)
            rel_path = f"/client/api/content/{cat_id}"
        elif action == "newOrder":
            prod_id = data.get("product_id")
            rel_path = f"/client/api/newOrder/{prod_id}/params"
        elif action == "check":
            rel_path = "/client/api/check"
        else:
            rel_path = f"/client/api/{action}"

        url = urljoin(base.rstrip("/") + "/", rel_path.lstrip("/"))

        method = "GET"

        req_log = ProviderRequestLog.objects.create(
            profile=self.profile,
            endpoint=url,
            method=method,
            payload=str({k: v for k, v in data.items() if k not in ("api_token", "key")})
        )

        start_time = time.time()

        try:
            response = self.session.get(
                url,
                params=dict(data),
                headers=headers,
                timeout=TIMEOUT
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            req_log.execution_time_ms = elapsed_ms
            req_log.save(update_fields=["execution_time_ms"])

            res_log = ProviderResponseLog.objects.create(
                request_log=req_log,
                status_code=response.status_code,
                body=response.text[:5000],
                is_success=False
            )

            try:
                json_resp = response.json()
            except ValueError:
                json_resp = {}

            is_success = response.status_code in (200, 201) and (
                isinstance(json_resp, list) or (
                    isinstance(json_resp, dict) and json_resp.get("status") not in ("ERROR", "error", "failed")
                    and json_resp.get("code") not in (120, 121, 122, 123)
                )
            )

            # Extract error message if any
            err_msg = ""
            err_code = None
            if isinstance(json_resp, dict):
                err_msg = json_resp.get("msg") or json_resp.get("message") or json_resp.get("error", "")
                err_code = json_resp.get("code")

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
                error_code=str(err_code) if err_code else None,
                error_message=err_msg if not is_success else ""
            )

            if not is_success and isinstance(json_resp, dict) and (json_resp.get("status") in ("ERROR", "error", "failed") or err_code):
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
        raw_msg = json_resp.get("message") or json_resp.get("msg") or json_resp.get("error") or ""
        
        # Try to extract ERR-XXX
        import re
        code = None
        m = re.search(r"ERR-(\d+)", raw_msg)
        if m:
            code = int(m.group(1))
        elif json_resp.get("code") is not None:
            try:
                code = int(json_resp.get("code"))
            except (TypeError, ValueError):
                code = None

        error_message = ERROR_MAPPING.get(code, raw_msg or "خطأ غير معروف من المزود.") if code else raw_msg

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
