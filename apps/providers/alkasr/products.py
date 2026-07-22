from .client import AlkasrClient

class AlkasrProductService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_products(self):
        resp = self.client.request("products")
        if resp.get("status") == "OK" or resp.get("status") == "success":
            return resp.get("data", {})
        return {}

    def fetch_content(self, category_id=0):
        resp = self.client.request("content", {"category": category_id})
        if resp.get("status") == "OK" or resp.get("status") == "success":
            return resp.get("data", {})
        return {}
