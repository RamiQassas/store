import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger("provider.tafa3olcard.client")

DEFAULT_BASE_URL = "https://tafa3olcard.com/api/v1/client-api"
DEFAULT_TIMEOUT = 12


class Tafa3olCardAPIException(Exception):
    """Base exception for Tafa3ol Card API errors."""
    pass


class Tafa3olCardClient:
    """
    HTTP Client for Tafa3ol Card (تفاعل كارد) API.
    Docs: https://tafa3olcard.com/shop/api
    Base URL: https://tafa3olcard.com/api/v1/client-api
    Auth Header: Authorization: Bearer <API_KEY> (or X-API-Key: <API_KEY>)
    """

    def __init__(self, api_token: str, base_url: str = None, timeout: int = DEFAULT_TIMEOUT, profile=None):
        self.api_token = (api_token or "").strip()
        base = (base_url or "").strip() or DEFAULT_BASE_URL
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        # Ensure base URL points to /api/v1/client-api
        base = base.rstrip("/")
        if not base.endswith("/client-api") and "api/v1/client-api" not in base:
            if "client-api" not in base:
                base = f"{base}/api/v1/client-api"
        self.base_url = base
        self.timeout = timeout
        self.profile = profile
        self.session = requests.Session()

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "X-API-Key": self.api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Raqamiyat-Store/1.0"
        }

    def _request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        # Check if api_token contains non-ascii characters (e.g. Arabic words entered during testing)
        try:
            self.api_token.encode('ascii')
        except UnicodeEncodeError:
            raise Tafa3olCardAPIException("مفتاح الـ API غير صالح (يحتوي على حروف عربية أو محارف غير صالحة. يجب أن يتكون من حروف وأرقام إنجليزية فقط).")

        headers = self._get_headers()

        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=self.timeout
            )
        except UnicodeEncodeError:
            raise Tafa3olCardAPIException("مفتاح الـ API غير صالح (يحتوي على أحرف غير مدعومة).")
        except requests.exceptions.Timeout:
            raise Tafa3olCardAPIException("انتهت مهلة الاتصال بخادم تفاعل كارد (Timeout).")
        except requests.exceptions.RequestException as e:
            raise Tafa3olCardAPIException(f"فشل الاتصال بخادم تفاعل كارد: {str(e)}")

        if resp.status_code == 401 or resp.status_code == 403:
            raise Tafa3olCardAPIException("بيانات المصادقة غير صحيحة (مفتاح الـ API الخاص بتفاعل كارد غير صالح).")

        try:
            data = resp.json()
        except Exception:
            if not resp.ok:
                raise Tafa3olCardAPIException(f"خطأ من خادم تفاعل كارد ({resp.status_code}): {resp.text[:200]}")
            raise Tafa3olCardAPIException(f"استجابة غير صالحة من تفاعل كارد: {resp.text[:200]}")

        if isinstance(data, dict):
            if data.get("success") is False:
                msg = data.get("message") or "فشل تنفيذ الطلب في تفاعل كارد"
                raise Tafa3olCardAPIException(msg)

        if not resp.ok:
            msg = data.get("message") if isinstance(data, dict) else resp.text[:200]
            raise Tafa3olCardAPIException(f"خطأ ({resp.status_code}): {msg}")

        return data

    def get_balance(self) -> dict:
        """GET /balance -> {success: true, message: '...', data: {balance: 152.75, currency: 'USD'}}"""
        return self._request("GET", "balance")

    def get_currencies(self) -> dict:
        """GET /currencies"""
        return self._request("GET", "currencies")

    def get_services(self) -> dict:
        """GET /services"""
        return self._request("GET", "services")

    def get_categories(self) -> dict:
        """GET /categories"""
        return self._request("GET", "categories")

    def get_products(self, search: str = None, page: int = 1, limit: int = 50) -> dict:
        """GET /products?search=...&page=...&limit=..."""
        params = {"page": page, "limit": limit}
        if search:
            params["search"] = search
        return self._request("GET", "products", params=params)

    def get_product(self, product_id: str) -> dict:
        """GET /products/:id"""
        return self._request("GET", f"products/{product_id}")

    def create_order(self, product_id: str, quantity: int = 1, requirements: dict = None) -> dict:
        """POST /orders -> {productId, quantity, requirements}"""
        payload = {
            "productId": str(product_id),
            "quantity": int(quantity or 1),
            "requirements": requirements or {}
        }
        return self._request("POST", "orders", json_data=payload)

    def get_order(self, order_id: str) -> dict:
        """GET /orders/:id"""
        return self._request("GET", f"orders/{order_id}")

    def get_orders(self, page: int = 1, limit: int = 20) -> dict:
        """GET /orders"""
        return self._request("GET", "orders", params={"page": page, "limit": limit})
