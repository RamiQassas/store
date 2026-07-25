"""
Alkasr Profile Service.
Handles fetching account profile info, updating balance, and storing metadata.
"""

from decimal import Decimal
from django.utils import timezone
from .client import AlkasrClient


class AlkasrProfileService:
    """Service to query provider account balance & details."""

    def __init__(self, client: AlkasrClient, profile_model=None):
        self.client = client
        self.profile = profile_model or getattr(client, "profile", None)

    def fetch_profile(self) -> dict:
        data = self.client.get_profile()
        res_data = data.get("data") or data.get("profile") or data

        balance_val = Decimal(str(res_data.get("balance") or res_data.get("credit") or "0.00"))
        currency_val = str(res_data.get("currency") or "USD")

        if self.profile:
            self.profile.balance = balance_val
            self.profile.currency = currency_val
            self.profile.save(update_fields=["balance", "currency", "updated_at"])

        return {
            "balance": balance_val,
            "currency": currency_val,
            "raw_response": data,
        }
