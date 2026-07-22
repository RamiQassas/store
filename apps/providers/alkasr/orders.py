import uuid
from decimal import Decimal
from .client import AlkasrClient
from apps.providers.models import ProviderOrder, ProviderOrderStatus

class AlkasrOrderService:
    def __init__(self, profile):
        self.profile = profile
        self.client = AlkasrClient(profile)

    def place_order(self, local_order, provider_product, quantity, parameters):
        """Places a new order with the provider via GET /client/api/newOrder/[product_id]/params."""
        
        provider_order_uuid = uuid.uuid4()
        
        provider_order = ProviderOrder.objects.create(
            profile=self.profile,
            local_order=local_order,
            product=provider_product,
            uuid=provider_order_uuid,
            quantity=quantity,
            parameters_sent=parameters
        )

        payload = {
            "product_id": provider_product.remote_id,
            "qty": quantity,
            "order_uuid": str(provider_order_uuid)
        }
        
        # Add dynamic parameters (e.g. playerId, etc.)
        payload.update(parameters)

        try:
            # According to docs: GET /client/api/newOrder/[product_id]/params?qty=...&order_uuid=...
            resp = self.client.request("newOrder", payload)
            
            data = resp.get("data", {}) if isinstance(resp, dict) else {}
            api_status = data.get("status") or resp.get("status", "accept")
            remote_order_id = data.get("order_id") or resp.get("order_id")

            provider_order.remote_order_id = remote_order_id
            provider_order.status = api_status
            provider_order.save(update_fields=["remote_order_id", "status"])

            ProviderOrderStatus.objects.create(
                provider_order=provider_order,
                status=api_status,
                raw_response=resp
            )

            return {
                "success": True,
                "status": api_status,
                "remote_order_id": remote_order_id,
                "raw_response": resp
            }
        except Exception as e:
            provider_order.status = "error"
            provider_order.save(update_fields=["status"])
            ProviderOrderStatus.objects.create(
                provider_order=provider_order,
                status="error",
                raw_response={"error": str(e)}
            )
            raise

    def check_orders(self, identifiers, is_uuid=False):
        """Check status of multiple orders via GET /client/api/check."""
        payload = {}
        if is_uuid:
            payload["orders"] = f"[{','.join(str(i) for i in identifiers)}]"
            payload["uuid"] = "1"
        else:
            payload["orders"] = f"[{','.join(str(i) for i in identifiers)}]"

        resp = self.client.request("check", payload)
        
        data_list = []
        if isinstance(resp, dict):
            if resp.get("status") == "OK" and isinstance(resp.get("data"), list):
                data_list = resp["data"]
            elif isinstance(resp.get("data"), list):
                data_list = resp["data"]
        elif isinstance(resp, list):
            data_list = resp

        for order_data in data_list:
            if not isinstance(order_data, dict):
                continue
            remote_id = order_data.get("order_id")
            api_status = order_data.get("status")
            
            # Update ProviderOrder status
            po = ProviderOrder.objects.filter(profile=self.profile, remote_order_id=remote_id).first()
            if po and po.status != api_status:
                po.status = api_status
                po.save(update_fields=["status"])
                ProviderOrderStatus.objects.create(
                    provider_order=po,
                    status=api_status,
                    raw_response=order_data
                )
        return data_list
