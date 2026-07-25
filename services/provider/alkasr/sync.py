"""
Alkasr Product Catalog Synchronization Engine.
Handles automatic fetching, updating, adding, and disabling of provider products.
Never deletes products from database (Soft disable only).
"""

import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from .products import AlkasrProductService

logger = logging.getLogger("provider.alkasr.sync")


class AlkasrSyncService:
    """Synchronizes remote Alkasr VIP products into local ProviderProduct models."""

    def __init__(self, client, profile_model):
        self.client = client
        self.profile = profile_model
        self.product_service = AlkasrProductService(client)

    def sync_catalog(self, selected_group_names=None) -> dict:
        """
        Executes catalog synchronization.
        """
        from apps.providers.models import (
            ProviderCategory, ProviderProduct, ProviderProductParameter,
            ProviderPrice, ProviderSyncLog
        )

        log_entry = ProviderSyncLog.objects.create(
            profile=self.profile,
            status="running"
        )

        progress_key = f"sync_progress_{self.profile.id}"
        cache.set(progress_key, {
            "status": "running", "total": 0, "current": 0,
            "percent": 0, "created": 0, "updated": 0, "disabled": 0
        }, timeout=600)

        created_count = 0
        updated_count = 0
        disabled_count = 0
        error_message = ""

        try:
            remote_products = self.product_service.fetch_all_products()
            total_items = len(remote_products)
            seen_remote_ids = set()

            with transaction.atomic():
                for index, item in enumerate(remote_products, start=1):
                    remote_id = item["remote_id"]
                    seen_remote_ids.add(remote_id)

                    # Ensure Category exists
                    cat_name = item.get("category_name") or "عام"
                    cat_remote_id = item.get("category_id") or "1"

                    cat_obj, _ = ProviderCategory.objects.get_or_create(
                        profile=self.profile,
                        remote_id=cat_remote_id,
                        defaults={"name": cat_name}
                    )
                    if cat_obj.name != cat_name:
                        cat_obj.name = cat_name
                        cat_obj.save(update_fields=["name", "updated_at"])

                    # Get or create ProviderProduct
                    prod_obj, created = ProviderProduct.objects.get_or_create(
                        profile=self.profile,
                        remote_id=remote_id,
                        defaults={
                            "name": item["name"],
                            "category": cat_obj,
                            "product_type": item["product_type"],
                            "is_active": item["is_active"],
                            "cost_price": Decimal(str(item["cost_price"] or "0.00")),
                            "qty_min": item["qty_min"],
                            "qty_max": item["qty_max"],
                            "qty_list": item["qty_list"],
                        }
                    )

                    if created:
                        created_count += 1
                        # Create default price entry
                        ProviderPrice.objects.get_or_create(
                            product=prod_obj,
                            defaults={
                                "margin_type": getattr(self.profile, "default_margin_type", "percentage"),
                                "margin_value": getattr(self.profile, "default_retail_margin", Decimal("5.00")),
                                "retail_margin_value": getattr(self.profile, "default_retail_margin", Decimal("5.00")),
                                "dealer_margin_value": getattr(self.profile, "default_dealer_margin", Decimal("2.00")),
                                "vip_margin_value": getattr(self.profile, "default_vip_margin", Decimal("1.00")),
                            }
                        )
                    else:
                        updated_count += 1
                        prod_obj.name = item["name"]
                        prod_obj.category = cat_obj
                        prod_obj.product_type = item["product_type"]
                        prod_obj.is_active = item["is_active"]
                        prod_obj.cost_price = Decimal(str(item["cost_price"] or "0.00"))
                        prod_obj.qty_min = item["qty_min"]
                        prod_obj.qty_max = item["qty_max"]
                        prod_obj.qty_list = item["qty_list"]
                        prod_obj.save()

                    # Update parameters
                    if item.get("parameters"):
                        prod_obj.parameters.all().delete()
                        for p in item["parameters"]:
                            if isinstance(p, dict):
                                ProviderProductParameter.objects.create(
                                    product=prod_obj,
                                    name=p.get("name") or p.get("key") or "param",
                                    label=p.get("label") or p.get("name") or "Param",
                                    required=bool(p.get("required", True)),
                                    parameter_type=p.get("type") or "text"
                                )

                    # Update Cache Progress
                    pct = int((index / total_items) * 100) if total_items > 0 else 100
                    cache.set(progress_key, {
                        "status": "running", "total": total_items, "current": index,
                        "percent": pct, "created": created_count, "updated": updated_count,
                        "disabled": disabled_count, "product_name": item["name"]
                    }, timeout=600)

                # Soft disable products missing from provider payload
                disabled_qs = ProviderProduct.objects.filter(profile=self.profile, is_active=True).exclude(remote_id__in=seen_remote_ids)
                disabled_count = disabled_qs.count()
                disabled_qs.update(is_active=False)

                # Automatically map ProviderProducts to store catalog Product & ProductVariant
                try:
                    from .mapper import AlkasrMapperService
                    AlkasrMapperService(self.profile).map_all_to_catalog(selected_group_names=selected_group_names)
                except Exception as map_err:
                    logger.warning(f"Catalog mapping warning for profile {self.profile}: {map_err}")

            self.profile.last_sync_at = timezone.now()
            self.profile.save(update_fields=["last_sync_at", "updated_at"])

            log_entry.status = "success"
            log_entry.products_created = created_count
            log_entry.products_updated = updated_count
            log_entry.products_disabled = disabled_count
            log_entry.save()

            result_data = {
                "status": "completed",
                "total": total_items,
                "created": created_count,
                "updated": updated_count,
                "disabled": disabled_count,
                "percent": 100
            }
            cache.set(progress_key, result_data, timeout=600)
            return result_data

        except Exception as exc:
            error_message = str(exc)
            logger.error(f"Catalog sync failed for profile {self.profile}: {exc}", exc_info=True)
            log_entry.status = "failed"
            log_entry.error_message = error_message
            log_entry.save()
            err_data = {"status": "error", "error": error_message, "percent": 0}
            cache.set(progress_key, err_data, timeout=600)
            raise exc
