from .client import AlkasrClient

class AlkasrProductService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_products(self):
        resp = self.client.request("products")
        if not isinstance(resp, dict):
            return {}
        if resp.get("status") == "error":
            return {}
        if "data" in resp and isinstance(resp["data"], (dict, list)):
            return resp["data"]
        return resp

    def fetch_content(self, category_id=0):
        resp = self.client.request("content", {"category": category_id})
        if not isinstance(resp, dict):
            return {}
        if resp.get("status") == "error":
            return {}
        if "data" in resp and isinstance(resp["data"], (dict, list)):
            return resp["data"]
        return resp
