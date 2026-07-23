from .client import AlkasrClient

class AlkasrProductService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_products(self):
        resp = None
        try:
            resp = self.client.request("products")
        except Exception:
            try:
                resp = self.client.request("services", endpoint_override="/api/v2")
            except Exception:
                resp = []

        return self._extract_response_data(resp)

    def _extract_response_data(self, resp):
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if resp.get("status") in ("ERROR", "error", "failed", False):
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

