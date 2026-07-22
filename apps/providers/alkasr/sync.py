import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.providers.models import (
    ProviderCategory, ProviderProduct, ProviderProductParameter, 
    ProviderPrice, ProviderPriceHistory, ProviderSyncLog
)
from .products import AlkasrProductService

logger = logging.getLogger(__name__)

class AlkasrSyncService:
    def __init__(self, profile):
        self.profile = profile
        self.product_svc = AlkasrProductService(profile)

    def sync_catalog(self):
        """Main entrypoint for syncing categories and products."""
        sync_log = ProviderSyncLog.objects.create(profile=self.profile, status="running")
        
        try:
            # 1. Fetch data
            raw_products = self.product_svc.fetch_products()
            root_content = self.product_svc.fetch_content(0)
            
            stats = {
                "created": 0,
                "updated": 0,
                "disabled": 0
            }

            # 2. Build Category Tree
            # The API returns nested categories via fetch_content recursively or we can parse it from `categories` key in root_content
            # To simplify, we extract what we can from products and root_content
            categories_dict = {}
            if "categories" in root_content:
                self._process_categories(root_content["categories"], parent_remote_id=None, categories_dict=categories_dict)
                
            # 3. Flatten and Extract ALL Products Recursively
            active_remote_ids = set()
            raw_products_list = []
            
            def extract_products_recursive(obj):
                if isinstance(obj, list):
                    for item in obj:
                        extract_products_recursive(item)
                elif isinstance(obj, dict):
                    # If this dict has product characteristics
                    if "id" in obj and ("name" in obj or "price" in obj or "product_type" in obj):
                        raw_products_list.append(obj)
                    # Check nested containers
                    if "products" in obj and isinstance(obj["products"], (list, dict)):
                        extract_products_recursive(obj["products"])
                    if "categories" in obj and isinstance(obj["categories"], (list, dict)):
                        extract_products_recursive(obj["categories"])
                    if "subcategories" in obj and isinstance(obj["subcategories"], (list, dict)):
                        extract_products_recursive(obj["subcategories"])
                    if "data" in obj and isinstance(obj["data"], (list, dict)):
                        extract_products_recursive(obj["data"])

            extract_products_recursive(raw_products)
            extract_products_recursive(root_content)

            # Deduplicate by product ID
            seen_ids = set()
            unique_products = []
            for item in raw_products_list:
                item_id = str(item.get("id", item.get("service", "")))
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    unique_products.append((item_id, item))

            for pid, pdata in unique_products:
                try:
                    active_remote_ids.add(str(pid))
                    remote_id = str(pid)
                    name = str(pdata.get("name") or f"Product {pid}")
                    desc = str(pdata.get("desc") or "")
                    
                    cat_name = str(pdata.get("category_name") or pdata.get("category") or "")
                    raw_parent = pdata.get("parent_id")
                    if raw_parent is not None and str(raw_parent) != "":
                        cat_id = str(raw_parent)
                    elif cat_name:
                        cat_id = cat_name
                    else:
                        cat_id = "0"

                    try:
                        cost = Decimal(str(pdata.get("price", "0.00")))
                    except Exception:
                        cost = Decimal("0.00")

                    is_available = pdata.get("available", True)
                    
                    category_obj = categories_dict.get(cat_id)
                    if not category_obj and (cat_name or cat_id):
                        c_name = cat_name if cat_name else f"Category {cat_id}"
                        category_obj, _ = ProviderCategory.objects.get_or_create(
                            profile=self.profile, 
                            remote_id=cat_id,
                            defaults={"name": c_name}
                        )
                        if category_obj.name != c_name and cat_name:
                            category_obj.name = cat_name
                            category_obj.save(update_fields=["name"])
                        categories_dict[cat_id] = category_obj

                    p_type_from_api = pdata.get("product_type")
                    qty_values = pdata.get("qty_values")

                    if p_type_from_api in ("amount", "package", "fixed_quantities"):
                        product_type = p_type_from_api
                    elif qty_values is None:
                        product_type = "package"
                    elif isinstance(qty_values, dict):
                        product_type = "amount"
                    elif isinstance(qty_values, list):
                        product_type = "fixed_quantities"
                    else:
                        product_type = "package"

                    def _clean_int(val):
                        if val is None or val == "":
                            return None
                        try:
                            v = int(float(str(val)))
                            return max(-2147483648, min(v, 9223372036854775807))
                        except (ValueError, TypeError):
                            return None

                    if isinstance(qty_values, dict):
                        qty_min = _clean_int(qty_values.get("min"))
                        qty_max = _clean_int(qty_values.get("max"))
                        qty_list = []
                    elif isinstance(qty_values, list):
                        qty_list = qty_values
                        qty_min, qty_max = None, None
                    else:
                        qty_min, qty_max, qty_list = None, None, []

                    product_obj = ProviderProduct.objects.filter(profile=self.profile, remote_id=remote_id).first()
                    is_new = product_obj is None
                    
                    if is_new:
                        product_obj = ProviderProduct.objects.create(
                            profile=self.profile,
                            remote_id=remote_id,
                            name=name,
                            category=category_obj,
                            product_type=product_type,
                            cost_price=cost,
                            qty_min=qty_min,
                            qty_max=qty_max,
                            qty_list=qty_list,
                            is_active=bool(is_available)
                        )
                        
                        ProviderPrice.objects.create(
                            product=product_obj,
                            margin_type="percentage",
                            margin_value=Decimal('0.00')
                        )
                        stats["created"] += 1
                    else:
                        old_cost = product_obj.cost_price
                        product_obj.name = name
                        product_obj.category = category_obj
                        product_obj.product_type = product_type
                        product_obj.cost_price = cost
                        product_obj.qty_min = qty_min
                        product_obj.qty_max = qty_max
                        product_obj.qty_list = qty_list
                        product_obj.is_active = True
                        product_obj.save()
                        
                        pricing_obj = getattr(product_obj, "pricing", None)
                        if not pricing_obj:
                            pricing_obj = ProviderPrice.objects.create(
                                product=product_obj,
                                margin_type="percentage",
                                margin_value=Decimal('0.00')
                            )
                        
                        if old_cost != cost:
                            ProviderPriceHistory.objects.create(
                                product=product_obj,
                                old_cost=old_cost,
                                new_cost=cost,
                                old_final_price=pricing_obj.final_price,
                                new_final_price=pricing_obj.final_price,
                                reason="API Sync Cost Update"
                            )
                        stats["updated"] += 1

                    params = pdata.get("params", [])
                    if params:
                        ProviderProductParameter.objects.filter(product=product_obj).delete()
                        for p in params:
                            if isinstance(p, dict):
                                ProviderProductParameter.objects.create(
                                    product=product_obj,
                                    name=p.get("name", "param"),
                                    label=p.get("label", "Param"),
                                    required=True,
                                    parameter_type=p.get("type", "text")
                                )
                            elif isinstance(p, str):
                                ProviderProductParameter.objects.create(
                                    product=product_obj,
                                    name=p,
                                    label=p.replace("_", " ").title(),
                                    required=True,
                                    parameter_type="text"
                                )
                except Exception as item_err:
                    logger.warning(f"Skipping product item {pid} due to error: {item_err}")
                    continue

                # Disable products not in API
                disabled_count = ProviderProduct.objects.filter(profile=self.profile, is_active=True).exclude(remote_id__in=active_remote_ids).update(is_active=False)
                stats["disabled"] = disabled_count

            sync_log.status = "success"
            sync_log.products_created = stats["created"]
            sync_log.products_updated = stats["updated"]
            sync_log.products_disabled = stats["disabled"]
            sync_log.save()
            
            self.profile.last_sync_at = timezone.now()
            self.profile.save(update_fields=["last_sync_at"])
            
            return stats

        except Exception as e:
            logger.exception("Alkasr Sync Failed")
            sync_log.status = "failed"
            sync_log.error_message = str(e)
            sync_log.save()
            raise

    def _process_categories(self, categories_list, parent_remote_id, categories_dict):
        """Recursively build category tree from content."""
        if not isinstance(categories_list, list):
            return
            
        for cat in categories_list:
            cat_id = str(cat.get("id", ""))
            name = cat.get("name", "")
            
            if not cat_id:
                continue
                
            parent_obj = None
            if parent_remote_id:
                parent_obj = categories_dict.get(str(parent_remote_id))
                
            cat_obj, created = ProviderCategory.objects.update_or_create(
                profile=self.profile,
                remote_id=cat_id,
                defaults={
                    "name": name,
                    "parent_remote_id": parent_remote_id,
                    "parent": parent_obj
                }
            )
            categories_dict[cat_id] = cat_obj
            
            # Fetch subcategories if needed (this might require making more API calls depending on provider structure)
            # For Alkasr, sometimes it returns subcategories directly or requires fetching content for cat_id
            # To avoid N+1 requests, we assume we fetch it lazily or it's flat in products.
