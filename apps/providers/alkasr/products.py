from .client import AlkasrClient
from .exceptions import APIError, AuthenticationError, NetworkError

class AlkasrProductService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_products(self):
        resp = None
        last_error = None

        # 1. Primary endpoint according to Alkasr VIP docs: /client/api/products
        try:
            resp = self.client.request("products")
        except (APIError, AuthenticationError, NetworkError) as err:
            last_error = err
            resp = None

        # 2. If primary failed or empty, try content endpoint: /client/api/content/0
        if not resp:
            try:
                content_resp = self.client.request(
                    "content",
                    payload={"category": 0},
                    endpoint_override="/client/api/content/0"
                )
                extracted = self._extract_response_data(content_resp)
                if extracted:
                    resp = extracted
            except Exception:
                pass

        # 3. If still empty and primary raised an API error, re-raise the API error!
        if not resp and last_error:
            raise last_error

        return self._extract_response_data(resp)

    def _extract_response_data(self, resp):
        if not resp:
            return []
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if resp.get("status") in ("ERROR", "error", "failed", False):
                err_msg = resp.get("message") or resp.get("msg") or resp.get("error")
                if err_msg:
                    raise APIError(str(err_msg))
                return []
            for key in ("data", "products", "services", "items", "result"):
                if key in resp and isinstance(resp[key], (list, dict)):
                    return resp[key]
            return resp
        return []

    def fetch_content(self, category_id=0):
        try:
            resp = self.client.request(
                "content",
                payload={"category": category_id},
                endpoint_override=f"/client/api/content/{category_id}"
            )
        except Exception:
            return {}

        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if resp.get("status") in ("ERROR", "error", "failed", False):
                return {}
            for key in ("data", "categories", "content", "items"):
                if key in resp and isinstance(resp[key], (dict, list)):
                    return resp[key]
            return resp
        return {}

