"""
Alkasr Order Placement, Verification, and Status Management Engine.
Enforces UUID v4 uniqueness, response persistence, and background status checking.
"""

import uuid
import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from django.db import transaction

from .client import AlkasrClient
from .validators import validate_order_preconditions
from .constants import PROVIDER_STATUS_MAP

logger = logging.getLogger("provider.alkasr.order")


class AlkasrOrderService:
    """Service to handle order submission and status checking with Alkasr VIP."""

    def __init__(self, client: AlkasrClient, profile_model=None):
        self.client = client
        self.profile = profile_model or getattr(client, "profile", None)

    def submit_order(
        self,
        local_order,
        provider_product,
        quantity: int = 1,
        player_params: Dict[str, Any] = None,
        order_uuid: str = None
    ) -> dict:
        """
        Validates order, generates unique UUID v4, submits to /newOrder, and records ProviderOrder.
        """
        from apps.providers.models import ProviderOrder, ProviderOrderStatus

        params = player_params or {}

        # 1. Fetch current profile balance for validation if profile is available
        current_balance = getattr(self.profile, "balance", None)
        cost_price = getattr(provider_product, "cost_price", Decimal("0.00"))
        estimated_cost = cost_price * Decimal(str(quantity))

        # 2. Validate Preconditions
        validate_order_preconditions(
            provider_product=provider_product,
            quantity=quantity,
            parameters_sent=params,
            provider_balance=current_balance,
            order_cost=estimated_cost
        )

        # 3. Generate UUID v4
        final_uuid = str(order_uuid) if order_uuid else str(uuid.uuid4())

        # Enforce UUID uniqueness
        if ProviderOrder.objects.filter(uuid=final_uuid).exists():
            final_uuid = str(uuid.uuid4())

        # 4. Submit to API Client
        remote_product_id = str(provider_product.remote_id)
        api_response = self.client.create_order(
            order_uuid=final_uuid,
            product_id=remote_product_id,
            quantity=quantity,
            player_params=params
        )

        # 5. Extract Remote Order ID & Status
        res_data = api_response.get("data") if isinstance(api_response.get("data"), dict) else api_response
        remote_order_id = res_data.get("order_id") or res_data.get("id") or api_response.get("order_id")
        raw_status = str(res_data.get("status") or api_response.get("status") or "pending").lower()

        mapped_status = PROVIDER_STATUS_MAP.get(raw_status, "processing")

        # 6. Create ProviderOrder record
        provider_order, _ = ProviderOrder.objects.update_or_create(
            uuid=final_uuid,
            defaults={
                "profile": self.profile,
                "local_order": local_order,
                "product": provider_product,
                "remote_order_id": str(remote_order_id) if remote_order_id else None,
                "status": mapped_status,
                "cost": estimated_cost,
                "quantity": quantity,
                "parameters_sent": params,
            }
        )

        ProviderOrderStatus.objects.create(
            provider_order=provider_order,
            status=mapped_status,
            raw_response=api_response
        )

        return {
            "uuid": final_uuid,
            "remote_order_id": remote_order_id,
            "status": mapped_status,
            "raw_status": raw_status,
            "estimated_cost": estimated_cost,
            "raw_response": api_response,
        }

    def check_orders(self, order_identifiers: List[str], is_uuid: bool = True) -> List[Dict[str, Any]]:
        """
        Queries /check endpoint for order status updates.
        """
        if not order_identifiers:
            return []

        response_data = self.client.check_orders(order_identifiers, is_uuid=is_uuid)
        items = []

        if isinstance(response_data, list):
            items = response_data
        elif isinstance(response_data, dict):
            items = response_data.get("data") or response_data.get("orders") or [response_data]

        parsed_results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_uuid = item.get("order_uuid") or item.get("uuid")
            item_id = item.get("order_id") or item.get("id")
            raw_status = str(item.get("status") or "").lower()
            mapped_status = PROVIDER_STATUS_MAP.get(raw_status, "processing")

            parsed_results.append({
                "order_uuid": item_uuid,
                "order_id": item_id,
                "status": mapped_status,
                "raw_status": raw_status,
                "cost": item.get("cost") or item.get("price"),
                "raw_response": item,
            })

        return parsed_results
