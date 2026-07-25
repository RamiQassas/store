"""
Alkasr Service Container & Main Service Layer.
Encapsulates all Alkasr sub-services into a unified service class.
"""

from .client import AlkasrClient
from .profile import AlkasrProfileService
from .products import AlkasrProductService
from .sync import AlkasrSyncService
from .order import AlkasrOrderService
from .pricing import PricingEngine


class AlkasrProviderService:
    """
    Main Service entry point for Alkasr VIP Provider integration.
    """

    def __init__(self, api_token: str, base_url: str = None, profile_model=None):
        self.profile = profile_model
        if profile_model and not api_token:
            api_token = profile_model.api_token
            base_url = profile_model.base_url

        self.client = AlkasrClient(api_token=api_token, base_url=base_url, profile=profile_model)
        self.profile_service = AlkasrProfileService(self.client, profile_model=profile_model)
        self.product_service = AlkasrProductService(self.client)
        self.sync_service = AlkasrSyncService(self.client, profile_model=profile_model)
        self.order_service = AlkasrOrderService(self.client, profile_model=profile_model)
        self.pricing_engine = PricingEngine()

    def fetch_balance(self) -> dict:
        return self.profile_service.fetch_profile()

    def fetch_products(self) -> list:
        return self.product_service.fetch_all_products()

    def sync_catalog(self) -> dict:
        return self.sync_service.sync_catalog()

    def place_order(self, local_order, provider_product, quantity: int = 1, player_params: dict = None, order_uuid: str = None) -> dict:
        return self.order_service.submit_order(
            local_order=local_order,
            provider_product=provider_product,
            quantity=quantity,
            player_params=player_params,
            order_uuid=order_uuid
        )

    def check_orders(self, order_identifiers: list, is_uuid: bool = True) -> list:
        return self.order_service.check_orders(order_identifiers, is_uuid=is_uuid)
