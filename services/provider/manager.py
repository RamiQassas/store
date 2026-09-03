"""
Unified ProviderManager.
High-level entry point for all provider-related actions across the system.
Ensures Views, Models, Tasks, and Admin never call API Clients directly.
"""

import logging
from typing import Dict, Any, List, Optional
from services.provider.alkasr import AlkasrProviderService
from services.provider.alkasr.exceptions import AlkasrAPIException

logger = logging.getLogger("services.provider.manager")


class ProviderManager:
    """
    Unified Manager for multi-provider API integrations.
    """

    @classmethod
    def get_service(cls, profile):
        """
        Factory method to instantiate the appropriate provider service.
        """
        if not profile:
            raise ValueError("Provider profile is required.")

        p_name = (profile.provider_name or "").lower()
        base_url = (profile.base_url or "").lower()

        if "tafa3ol" in p_name or "تفاعل" in p_name or "tafa3ol" in base_url:
            from services.provider.tafa3olcard import Tafa3olCardProviderService
            return Tafa3olCardProviderService(
                api_token=profile.api_token,
                base_url=profile.base_url,
                profile_model=profile
            )
        elif "alkasr" in p_name or "الكسر" in p_name or "رقميات" in p_name or "alkasr" in base_url:
            return AlkasrProviderService(
                api_token=profile.api_token,
                base_url=profile.base_url,
                profile_model=profile
            )
        else:
            # Default to Alkasr
            return AlkasrProviderService(
                api_token=profile.api_token,
                base_url=profile.base_url,
                profile_model=profile
            )

    @classmethod
    def fetch_balance(cls, profile) -> dict:
        """Fetches provider current balance and updates profile."""
        svc = cls.get_service(profile)
        return svc.fetch_balance()

    @classmethod
    def fetch_products(cls, profile) -> list:
        """Fetches raw product list from provider."""
        svc = cls.get_service(profile)
        return svc.fetch_products()

    @classmethod
    def sync_catalog(cls, profile, selected_group_names=None) -> dict:
        """Executes full product catalog synchronization."""
        svc = cls.get_service(profile)
        return svc.sync_catalog(selected_group_names=selected_group_names)

    @classmethod
    def place_order(
        cls,
        profile,
        local_order,
        provider_product,
        quantity: int = 1,
        player_params: Dict[str, Any] = None,
        order_uuid: str = None
    ) -> dict:
        """
        Submits order to provider via unified service layer.
        """
        svc = cls.get_service(profile)
        return svc.place_order(
            local_order=local_order,
            provider_product=provider_product,
            quantity=quantity,
            player_params=player_params,
            order_uuid=order_uuid
        )

    @classmethod
    def check_orders(cls, profile, order_identifiers: List[str], is_uuid: bool = True) -> list:
        """Checks pending orders status."""
        svc = cls.get_service(profile)
        return svc.check_orders(order_identifiers, is_uuid=is_uuid)

    @classmethod
    def test_connection(cls, profile) -> dict:
        """Tests API token and connectivity with provider."""
        try:
            res = cls.fetch_balance(profile)
            return {"success": True, "balance": res.get("balance"), "currency": res.get("currency")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
