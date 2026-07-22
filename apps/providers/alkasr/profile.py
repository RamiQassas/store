from decimal import Decimal
from .client import AlkasrClient

class AlkasrProfileService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_balance(self):
        resp = self.client.request("profile")
        if resp.get("status") == "success" or resp.get("status") == "OK":
            data = resp.get("data", {})
            balance = data.get("balance", "0")
            currency = data.get("currency", "USD")
            
            self.profile.balance = Decimal(str(balance))
            self.profile.currency = currency
            self.profile.save(update_fields=["balance", "currency"])
            
            return {
                "balance": self.profile.balance,
                "currency": self.profile.currency,
                "email": data.get("email", "")
            }
        return None
