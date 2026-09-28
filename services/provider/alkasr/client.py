"""
Unified Alkasr VIP API Client.
Handles low-level HTTP communication, authentication, session reuse, retries, timeout, and logging.
"""

import time
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .constants import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    ENDPOINT_PROFILE,
    ENDPOINT_PRODUCTS,
    ENDPOINT_NEW_ORDER,
    ENDPOINT_CHECK_ORDER,
)
from .exceptions import (
    AlkasrAPIException,
    NetworkException,
    TimeoutException,
    RetryAfterOneMinuteException,
    raise_for_code,
)
from .utils import log_request, log_response, record_transaction_log

logger = logging.getLogger("provider.alkasr.client")


class AlkasrClient:
    """
    HTTP Client for Alkasr VIP API.
    Reuses TCP connection pool via requests.Session, implements automatic retries,
    times out cleanly, and maps provider status codes to Python exceptions.
    """

    def __init__(self, api_token=None, base_url: str = None, timeout: int = DEFAULT_TIMEOUT, profile=None):
        import os
        env_token = os.environ.get("ALKASR_API_TOKEN", "").strip()
        env_base = os.environ.get("ALKASR_BASE_URL", "").strip()

        if hasattr(api_token, 'api_token'):
            profile = api_token
            api_token = getattr(profile, "api_token", "") or env_token
            base_url = base_url or getattr(profile, "base_url", None) or env_base
        elif profile and not api_token:
            api_token = getattr(profile, "api_token", "") or env_token
            base_url = base_url or getattr(profile, "base_url", None) or env_base
        elif not api_token and env_token:
            api_token = env_token

        self.api_token = (api_token or "").strip()
        base = (base_url or env_base or DEFAULT_BASE_URL).strip()
        if not base:
            base = DEFAULT_BASE_URL
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        if not base.endswith("/"):
            base += "/"
        # Ensure base contains /client/api/
        if "client/api" not in base.lower():
            base = urljoin(base, "client/api/")
        self.base_url = base
        self.timeout = timeout
        self.profile = profile

        self.session = requests.Session()
        retries = Retry(
            total=1,
            backoff_factor=0.2,
            status_forcelist=[502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_headers(self) -> dict:
        return {
            "api-token": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AlkasrVIPClient/2.0",
        }

    def _build_url(self, endpoint: str) -> str:
        base = (self.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        while base.lower().endswith("/client/api/client/api"):
            base = base[:-11].rstrip("/")
        if not base.lower().endswith("/client/api"):
            if "client/api" not in base.lower():
                base = f"{base}/client/api"
        clean_endpoint = endpoint.strip().lstrip("/")
        if clean_endpoint.startswith("client/api/"):
            clean_endpoint = clean_endpoint[11:].lstrip("/")
        return f"{base}/{clean_endpoint}"

    def request(self, method: str, endpoint: str = None, params: dict = None, json_data: dict = None, retries_left: int = 2, endpoint_override: str = None) -> dict:
        """
        Generic request method with error code mapping and 111 Retry-After handling.
        Supports both HTTP-method signatures: request("GET", "/products")
        and legacy action signatures: request("products", payload={...})
        """
        # Handle legacy action-based calls
        KNOWN_ACTIONS = ("profile", "products", "content", "neworder", "new_order", "check", "order")
        if endpoint_override:
            endpoint = endpoint_override
            method = "GET"
        elif method.lower() in KNOWN_ACTIONS or method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
            action = method.lower()
            payload = endpoint if isinstance(endpoint, dict) else (params or {})
            method = "GET"
            if action == "profile":
                endpoint = ENDPOINT_PROFILE
                params = payload
            elif action == "products":
                endpoint = ENDPOINT_PRODUCTS
                params = payload
            elif action in ("neworder", "new_order", "order"):
                prod_id = payload.get("product_id") or payload.get("id")
                endpoint = f"{ENDPOINT_NEW_ORDER}/{prod_id}/params"
                params = {k: v for k, v in payload.items() if k not in ("product_id", "id")}
            elif action == "check":
                endpoint = ENDPOINT_CHECK_ORDER
                params = payload
            elif action == "content":
                cat_id = payload.get("category", 0)
                endpoint = f"content/{cat_id}"
            else:
                endpoint = f"/{action}"
                params = payload

        url = self._build_url(endpoint)
        headers = self._get_headers()
        log_request(self.profile or "Default", endpoint, method, json_data or params)

        start_time = time.time()
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=self.timeout
            )
            duration_ms = (time.time() - start_time) * 1000
            log_response(self.profile or "Default", response.status_code, duration_ms, response.text)

        except requests.exceptions.Timeout as exc:
            duration_ms = (time.time() - start_time) * 1000
            record_transaction_log(self.profile, endpoint, method, json_data or params, str(exc), 0, duration_ms, False, "TIMEOUT", str(exc))
            raise TimeoutException(f"Request timeout connecting to {url}: {exc}")
        except requests.exceptions.RequestException as exc:
            duration_ms = (time.time() - start_time) * 1000
            record_transaction_log(self.profile, endpoint, method, json_data or params, str(exc), 0, duration_ms, False, "NETWORK_ERROR", str(exc))
            raise NetworkException(f"Network error connecting to {url}: {exc}")

        # Parse JSON response
        try:
            data = response.json()
        except ValueError:
            record_transaction_log(self.profile, endpoint, method, json_data or params, response.text, response.status_code, duration_ms, False, "INVALID_JSON", "Invalid JSON from provider")
            raise AlkasrAPIException(f"Invalid JSON response from provider (HTTP {response.status_code}): {response.text[:200]}")

        # Extract provider code / status
        if isinstance(data, list):
            is_success = response.status_code in (200, 201)
            status_val = "success" if is_success else "error"
            code_val = response.status_code
            error_code = None
            error_message = None
        else:
            status_val = data.get("status")
            code_val = data.get("code")
            has_explicit_error = bool(data.get("error") or data.get("error_code"))

            # Check for provider error codes inside response JSON
            error_code = code_val if (isinstance(code_val, int) and code_val not in (0, 200, 201)) else (
                data.get("error_code") if isinstance(data.get("error_code"), int) else None
            )
            if error_code is None and isinstance(status_val, int) and status_val not in (0, 200, 201):
                error_code = status_val
            
            error_message = data.get("message") or data.get("error")

            is_success = (
                response.status_code in (200, 201)
                and not has_explicit_error
                and (error_code is None or error_code in (0, 200, 201))
                and (
                    str(status_val).lower() in ("success", "ok", "true", "1")
                    or code_val in (200, 201, 0, None)
                )
            )

        # Handle 111 Retry Code (Retry after 1 minute)
        if error_code == 111 and retries_left > 0:
            logger.warning(f"Received Error 111 (Retry after one minute) from provider for endpoint {endpoint}. Sleeping 3s before retry attempt...")
            time.sleep(3)
            return self.request(method, endpoint, params=params, json_data=json_data, retries_left=retries_left - 1)

        record_transaction_log(
            self.profile,
            endpoint,
            method,
            json_data or params,
            data,
            response.status_code,
            duration_ms,
            is_success,
            error_code=error_code,
            error_message=error_message
        )

        if not is_success and error_code:
            raise_for_code(error_code, message=data.get("message") or data.get("error"), raw_response=data)

        return data

    def get_profile(self) -> dict:
        """Fetches account details & balance from /profile endpoint."""
        return self.request("GET", ENDPOINT_PROFILE)

    def get_products(self, products_id=None) -> Any:
        """
        Fetches products catalog from /products endpoint.
        Optionally filters by ID(s): GET /client/api/products?products_id=id1,id2
        """
        params = {}
        if products_id is not None:
            if isinstance(products_id, (list, tuple, set)):
                clean_ids = [str(x).strip() for x in products_id if x not in (None, "")]
                if clean_ids:
                    params["products_id"] = ",".join(clean_ids)
            elif str(products_id).strip():
                params["products_id"] = str(products_id).strip()
        return self.request("GET", ENDPOINT_PRODUCTS, params=params if params else None)

    def get_content(self, category_id: str = "0") -> Any:
        """Fetches category tree content from /content/{category_id}."""
        clean_cid = str(category_id).strip() if category_id not in (None, "") else "0"
        return self.request("GET", f"content/{clean_cid}")

    def create_order(self, order_uuid: str, product_id: str, quantity: int = 1, player_params: dict = None) -> dict:
        """
        Submits a new order using UUID v4.
        Format: GET /client/api/newOrder/{product_id}/params?qty=1&playerId=test&order_uuid=uuid
        """
        endpoint = f"{ENDPOINT_NEW_ORDER}/{product_id}/params"
        params = {
            "order_uuid": str(order_uuid),
            "qty": int(quantity),
        }
        if player_params:
            EXCLUDED_PARAM_KEYS = {
                "paymera_url", "payment_gateway", "payment_provider", "gateway_payment_id",
                "gateway_charge_amount", "gateway_charge_currency", "is_direct_gateway_purchase",
                "direct_gateway_purchase", "gateway_order", "direct_gateway", "checkout_session_id",
                "stripe_session_id", "transaction_id", "payment_id", "payment_reference",
                "payment_method", "client_secret", "payment_status", "order_channel",
                "api_provider", "api_status", "api_last_response", "api_refunded",
                "raw_response", "response", "api_error", "alkasr", "tafa3ol",
                "notes", "admin_notes", "price_adjustment_reason", "fulfillment_data"
            }
            EXCLUDED_PARAM_PREFIXES = (
                "gateway_", "payment_", "paymera_", "sham_", "fmp_", "stripe_", "api_", "_", "internal_"
            )

            cleaned_params = {}
            for k, v in player_params.items():
                if not k or v is None or str(v).strip() == "" or isinstance(v, (dict, list)):
                    continue
                k_str = str(k).strip()
                k_lower = k_str.lower()
                if k_lower in EXCLUDED_PARAM_KEYS or k_lower.startswith(EXCLUDED_PARAM_PREFIXES):
                    continue
                cleaned_params[k_str] = str(v).strip()
            
            # If playerId is not explicitly present, find matching ID alias and populate playerId
            if "playerId" not in cleaned_params:
                for k, v in list(cleaned_params.items()):
                    k_lower = k.lower()
                    if any(term in k_lower for term in ["player", "user", "id", "ايدي", "آيدي", "معرف", "حساب", "phone", "هاتف", "جوال"]):
                        cleaned_params["playerId"] = v
                        break

            params.update(cleaned_params)
        return self.request("GET", endpoint, params=params)

    def get_product(self, product_id: str) -> dict:
        """
        Fetches a single product by ID.
        Queries /products and finds item with matching provider ID.
        """
        all_prods = self.get_products()
        raw_items = all_prods if isinstance(all_prods, list) else (
            all_prods.get("data") if isinstance(all_prods, dict) and isinstance(all_prods.get("data"), list)
            else (all_prods.get("products") if isinstance(all_prods, dict) and isinstance(all_prods.get("products"), list) else [])
        )
        for item in raw_items:
            if str(item.get("id")) == str(product_id):
                return item
        raise ProductDeletedException(f"Product #{product_id} not found in provider catalog", code=109)

    def check_orders(self, order_identifiers: Any, is_uuid: bool = True) -> Any:
        """
        Checks order statuses via /check endpoint.
        Format: GET /client/api/check?orders=[ID1,ID2]
        Or UUID: GET /client/api/check?orders=[UUID1,UUID2]&uuid=1
        """
        if not isinstance(order_identifiers, (list, tuple, set)):
            order_identifiers = [order_identifiers]
        clean_ids = [str(x).strip() for x in order_identifiers if x not in (None, "")]
        params = {
            "orders": f"[{','.join(clean_ids)}]"
        }
        if is_uuid:
            params["uuid"] = "1"
        return self.request("GET", ENDPOINT_CHECK_ORDER, params=params)


AlkasrAPIClient = AlkasrClient

