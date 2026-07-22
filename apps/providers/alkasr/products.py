from .client import AlkasrClient

class AlkasrProductService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_products(self):
        resp = self.client.request("products")
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if resp.get("status") in ("ERROR", "error"):
                return []
            if "data" in resp and isinstance(resp["data"], (list, dict)):
                return resp["data"]
            return resp
        return []

    def fetch_content(self, category_id=0):
        resp = self.client.request("content", payload={"category": category_id}, endpoint_override=f"/client/api/content/{category_id}")
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if resp.get("status") in ("ERROR", "error"):
                return {}
            if "data" in resp and isinstance(resp["data"], (dict, list)):
                return resp["data"]
            return resp
        return {}
