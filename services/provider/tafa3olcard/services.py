import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from .client import Tafa3olCardClient, Tafa3olCardAPIException

logger = logging.getLogger("provider.tafa3olcard.service")


class Tafa3olCardProviderService:
    """
    Main Service entry point for Tafa3ol Card (تفاعل كارد) Provider integration.
    Fully isolated and self-contained; guarantees other providers are never affected.
    """

    def __init__(self, api_token: str, base_url: str = None, profile_model=None):
        self.profile = profile_model
        if profile_model and not api_token:
            api_token = profile_model.api_token
            base_url = profile_model.base_url

        self.client = Tafa3olCardClient(
            api_token=api_token,
            base_url=base_url,
            profile=profile_model
        )

    def fetch_balance(self) -> dict:
        """
        Fetches current balance from Tafa3ol Card API.
        GET /balance
        Response format:
        { "success": true, "message": "Balance retrieved", "data": { "balance": 152.75, "openCredit": 0, "currency": "USD" } }
        """
        data = self.client.get_balance()
        inner = data.get("data") or {}

        raw_balance = inner.get("balance", 0)
        raw_currency = inner.get("currency") or "USD"

        balance_val = Decimal(str(raw_balance or "0.00"))
        currency_val = str(raw_currency or "USD")

        if self.profile:
            self.profile.balance = balance_val
            self.profile.currency = currency_val
            self.profile.save(update_fields=["balance", "currency", "updated_at"])

        return {
            "balance": balance_val,
            "currency": currency_val,
            "raw_response": data,
        }

    def fetch_products(self) -> list:
        """
        Fetches all available products from Tafa3ol Card with pagination.
        """
        all_products = []
        page = 1
        limit = 50

        while True:
            try:
                res = self.client.get_products(page=page, limit=limit)
                data = res.get("data") or []
                if not data:
                    break
                all_products.extend(data)
                meta = res.get("meta") or {}
                total = meta.get("total", 0)
                if len(all_products) >= total or len(data) < limit:
                    break
                page += 1
                if page > 50:  # safety bound
                    break
            except Exception as e:
                logger.error(f"Error fetching page {page} from Tafa3ol Card: {e}")
                break

        return all_products

    def sync_catalog(self, selected_group_names=None) -> dict:
        """
        Synchronizes Tafa3ol Card products and categories into ProviderProduct/ProviderCategory,
        and creates local catalog Product and ProductVariant records under profile store.
        """
        from apps.providers.models import ProviderCategory, ProviderProduct, ProviderPrice
        from apps.catalog.models import Category, Product, ProductVariant

        raw_products = self.fetch_products()
        created_count = 0
        updated_count = 0

        # Also fetch categories from provider
        cat_map = {}
        try:
            cats_res = self.client.get_categories()
            for c in cats_res.get("data") or []:
                c_id = str(c.get("_id") or "")
                c_name = c.get("name")
                if isinstance(c_name, dict):
                    c_name = c_name.get("ar") or c_name.get("en") or str(c_name)
                cat_map[c_id] = str(c_name or "عام")
        except Exception as e:
            logger.warning(f"Could not fetch Tafa3ol Card categories: {e}")

        store = self.profile.store if self.profile else None

        for item in raw_products:
            remote_id = str(item.get("_id") or "")
            if not remote_id:
                continue

            raw_name = item.get("name")
            if isinstance(raw_name, dict):
                p_name = raw_name.get("ar") or raw_name.get("en") or str(raw_name)
            else:
                p_name = str(raw_name or "منتج تفاعل كارد")

            cost_price = Decimal(str(item.get("costPrice") or "0.00"))
            cat_id = str(item.get("category") or "")
            cat_name = cat_map.get(cat_id, "عام")

            # Update or create ProviderCategory
            p_cat = None
            if self.profile:
                p_cat, _ = ProviderCategory.objects.get_or_create(
                    profile=self.profile,
                    remote_id=cat_id or "default",
                    defaults={"name": cat_name}
                )

                # Update or create ProviderProduct
                pp, created = ProviderProduct.objects.update_or_create(
                    profile=self.profile,
                    remote_id=remote_id,
                    defaults={
                        "name": p_name,
                        "category": p_cat,
                        "cost_price": cost_price,
                        "is_active": item.get("quantityAvailable", True),
                        "local_is_active": True,
                        "product_type": "package" if item.get("quantityMode") == "FIXED" else "recharge",
                        "min_quantity": item.get("minQuantity", 1),
                        "max_quantity": item.get("maxQuantity", 10),
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        if self.profile:
            self.profile.last_sync_at = timezone.now()
            self.profile.save(update_fields=["last_sync_at"])

        return {
            "status": "completed",
            "total": len(raw_products),
            "created": created_count,
            "updated": updated_count
        }

    def place_order(
        self,
        local_order,
        provider_product,
        quantity: int = 1,
        player_params: Dict[str, Any] = None,
        order_uuid: str = None
    ) -> dict:
        """
        Submits an order to Tafa3ol Card API.
        POST /orders
        Payload: { "productId": "...", "quantity": 1, "requirements": { ... } }
        """
        product_id = provider_product.remote_id
        reqs = player_params or {}

        res = self.client.create_order(
            product_id=product_id,
            quantity=quantity,
            requirements=reqs
        )

        data = res.get("data") or {}
        remote_order_id = str(data.get("_id") or data.get("orderNumber") or "")
        status = str(data.get("status") or "PROCESSING").upper()

        return {
            "status": status,
            "remote_order_id": remote_order_id,
            "raw_response": res
        }

    def check_orders(self, order_identifiers: List[str], is_uuid: bool = True) -> list:
        """
        Checks order statuses with Tafa3ol Card.
        GET /orders/:id
        """
        results = []
        for oid in order_identifiers:
            try:
                res = self.client.get_order(str(oid))
                data = res.get("data") or {}
                raw_status = str(data.get("status") or "").upper()

                # Map statuses
                if raw_status == "COMPLETED":
                    mapped = "completed"
                elif raw_status in ("PENDING_MANUAL", "PROCESSING"):
                    mapped = "pending"
                elif raw_status in ("FAILED", "CANCELLED"):
                    mapped = "failed"
                else:
                    mapped = "pending"

                results.append({
                    "remote_order_id": str(oid),
                    "status": mapped,
                    "raw_status": raw_status,
                    "data": data
                })
            except Exception as e:
                logger.error(f"Error checking order {oid} on Tafa3ol Card: {e}")
                results.append({
                    "remote_order_id": str(oid),
                    "status": "pending",
                    "error": str(e)
                })

        return results
