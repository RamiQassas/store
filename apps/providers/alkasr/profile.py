from decimal import Decimal
from .client import AlkasrClient

class AlkasrProfileService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def fetch_balance(self):
        try:
            resp = self.client.request("profile")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Balance check failed: {e}")
            return None

        if not resp:
            return None

        balance_val = None
        currency_val = "USD"
        email_val = ""

        if isinstance(resp, dict):
            # Format: {"balance": "8788.683", "email": "user@email.com"}
            balance_val = resp.get("balance") or resp.get("amount")
            email_val = resp.get("email", "")
            currency_val = resp.get("currency", "USD")

            if balance_val is None and "data" in resp and isinstance(resp["data"], dict):
                d = resp["data"]
                balance_val = d.get("balance") or d.get("amount")
                currency_val = d.get("currency", "USD")
                email_val = d.get("email", "")

        if balance_val is not None:
            try:
                self.profile.balance = Decimal(str(balance_val))
                self.profile.currency = str(currency_val)
                self.profile.save(update_fields=["balance", "currency"])
                return {
                    "balance": self.profile.balance,
                    "currency": self.profile.currency,
                    "email": email_val
                }
            except Exception:
                pass
                
        return None
