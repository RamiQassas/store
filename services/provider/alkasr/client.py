"""
Unified Alkasr VIP API Client.
Handles low-level HTTP communication, authentication, session reuse, retries, timeout, and logging.
"""

import time
import logging
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

    def __init__(self, api_token: str, base_url: str = None, timeout: int = DEFAULT_TIMEOUT, profile=None):
        self.api_token = (api_token or "").strip()
        base = (base_url or "").strip()
        if not base:
            base = DEFAULT_BASE_URL
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        if not base.endswith("/"):
            base += "/"
        self.base_url = base
        self.timeout = timeout
        self.profile = profile

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
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
        clean_endpoint = endpoint.lstrip("/")
        return urljoin(self.base_url, clean_endpoint)

    def request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None, retries_left: int = 2) -> dict:
        """
        Generic request method with error code mapping and 111 Retry-After handling.
        """
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
        status_val = data.get("status")
        code_val = data.get("code")

        is_success = response.status_code == 200 and (status_val in ["success", True, "1", 1] or code_val in [200, 0, None] and not data.get("error"))

        # Check for provider error codes inside response JSON
        error_code = code_val or (data.get("error_code") if isinstance(data.get("error_code"), int) else None)
        if error_code is None and isinstance(status_val, int):
            error_code = status_val

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
            error_message=data.get("message") or data.get("error")
        )

        if not is_success and error_code:
            raise_for_code(error_code, message=data.get("message") or data.get("error"), raw_response=data)

        return data

    def get_profile(self) -> dict:
        """Fetches account details & balance from /profile endpoint."""
        return self.request("POST", ENDPOINT_PROFILE)

    def get_products(self) -> dict:
        """Fetches full catalog from /products endpoint."""
        return self.request("POST", ENDPOINT_PRODUCTS)

    def create_order(self, order_uuid: str, product_id: str, quantity: int = 1, player_params: dict = None) -> dict:
        """
        Submits a new order to /newOrder endpoint using UUID v4.
        """
        payload = {
            "order_uuid": str(order_uuid),
            "product_id": str(product_id),
            "quantity": int(quantity),
        }
        if player_params:
            payload.update(player_params)
        return self.request("POST", ENDPOINT_NEW_ORDER, json_data=payload)

    def check_orders(self, order_identifiers: list, is_uuid: bool = True) -> dict:
        """
        Checks order statuses via /check endpoint.
        """
        param_name = "order_uuids" if is_uuid else "order_ids"
        params = {param_name: ",".join([str(x) for x in order_identifiers])}
        return self.request("POST", ENDPOINT_CHECK_ORDER, json_data=params)
