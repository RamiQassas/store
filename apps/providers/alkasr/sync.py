import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.providers.models import (
    ProviderCategory,
    ProviderPrice,
    ProviderPriceHistory,
    ProviderProduct,
    ProviderProductParameter,
    ProviderSyncLog,
)
from .products import AlkasrProductService

logger = logging.getLogger(__name__)


class AlkasrSyncService:
    def __init__(self, profile):
        self.profile = profile
        self.product_svc = AlkasrProductService(profile)

    def sync_catalog(self):
        sync_log = ProviderSyncLog.objects.create(profile=self.profile, status="running")

        try:
            raw_products = self.product_svc.fetch_products()
            content_by_id = self._fetch_content_tree()
            stats = {"created": 0, "updated": 0, "disabled": 0}

            with transaction.atomic():
                categories_by_remote = self._sync_categories(content_by_id)
                products = self._dedupe_products(
                    self._extract_products(raw_products)
                    + self._extract_products(list(content_by_id.values()))
                )
                active_remote_ids = set()

                for remote_id, pdata in products:
                    active_remote_ids.add(remote_id)
                    is_new = self._upsert_product(remote_id, pdata, categories_by_remote)
                    if is_new:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                if active_remote_ids:
                    stats["disabled"] = ProviderProduct.objects.filter(
                        profile=self.profile,
                        is_active=True,
                    ).exclude(remote_id__in=active_remote_ids).update(is_active=False)

                from .mapper import AlkasrMapperService
                AlkasrMapperService(self.profile).map_all_to_catalog()

                sync_log.status = "success"
                sync_log.products_created = stats["created"]
                sync_log.products_updated = stats["updated"]
                sync_log.products_disabled = stats["disabled"]
                sync_log.save()

                self.profile.last_sync_at = timezone.now()
                self.profile.save(update_fields=["last_sync_at"])

            return stats

        except Exception as exc:
            logger.exception("Alkasr sync failed")
            sync_log.status = "failed"
            sync_log.error_message = str(exc)
            sync_log.errors_count = 1
            sync_log.save()
            raise

    def _fetch_content_tree(self, max_nodes=80):
        content_by_id = {}
        queue = ["0"]
        seen = set()

        while queue and len(seen) < max_nodes:
            category_id = str(queue.pop(0))
            if category_id in seen:
                continue
            seen.add(category_id)

            try:
                content = self.product_svc.fetch_content(category_id)
            except Exception:
                logger.exception("Failed to fetch Alkasr content category %s", category_id)
                continue

            content_by_id[category_id] = content
            for cat in self._extract_categories(content):
                cat_id = self._clean_remote_id(cat.get("id"))
                if cat_id and cat_id not in seen:
                    queue.append(cat_id)

        return content_by_id

    def _sync_categories(self, content_by_id):
        categories_by_remote = {}
        pending = []

        for parent_remote_id, content in content_by_id.items():
            for cat in self._extract_categories(content):
                remote_id = self._clean_remote_id(cat.get("id"))
                if not remote_id:
                    continue
                inferred_parent = None if str(parent_remote_id) == "0" else str(parent_remote_id)
                pending.append((remote_id, str(cat.get("name") or f"Category {remote_id}"), inferred_parent))

        for remote_id, name, parent_remote_id in pending:
            parent = categories_by_remote.get(parent_remote_id)
            obj, _ = ProviderCategory.objects.update_or_create(
                profile=self.profile,
                remote_id=remote_id,
                defaults={
                    "name": name,
                    "parent_remote_id": parent_remote_id,
                    "parent": parent,
                },
            )
            categories_by_remote[remote_id] = obj

        return categories_by_remote

    def _upsert_product(self, remote_id, pdata, categories_by_remote):
        name = str(pdata.get("name") or pdata.get("title") or pdata.get("service") or f"Product {remote_id}")
        raw_cost = (
            pdata.get("price")
            or pdata.get("base_price")
            or pdata.get("cost")
            or pdata.get("rate")
            or pdata.get("price_usd")
            or "0.00"
        )
        cost = self._decimal(raw_cost)
        is_available = bool(pdata.get("available", pdata.get("is_active", True)))

        category_obj = self._category_for_product(pdata, categories_by_remote)
        product_type, qty_min, qty_max, qty_list = self._quantity_config(pdata)

        product_obj = ProviderProduct.objects.filter(
            profile=self.profile,
            remote_id=remote_id,
        ).first()
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
                is_active=is_available,
            )
            ProviderPrice.objects.create(
                product=product_obj,
                margin_type="percentage",
                margin_value=Decimal("0.00"),
            )
        else:
            old_cost = product_obj.cost_price
            product_obj.name = name
            product_obj.category = category_obj
            product_obj.product_type = product_type
            product_obj.cost_price = cost
            product_obj.qty_min = qty_min
            product_obj.qty_max = qty_max
            product_obj.qty_list = qty_list
            product_obj.is_active = is_available
            product_obj.save()

            pricing_obj = getattr(product_obj, "pricing", None)
            if not pricing_obj:
                pricing_obj = ProviderPrice.objects.create(
                    product=product_obj,
                    margin_type="percentage",
                    margin_value=Decimal("0.00"),
                )

            if old_cost != cost:
                ProviderPriceHistory.objects.create(
                    product=product_obj,
                    old_cost=old_cost,
                    new_cost=cost,
                    old_final_price=pricing_obj.final_price,
                    new_final_price=pricing_obj.final_price,
                    reason="Alkasr API sync cost update",
                )

        ProviderProductParameter.objects.filter(product=product_obj).delete()
        for param in pdata.get("params") or []:
            name_key, label, field_type = self._normalize_param(param)
            ProviderProductParameter.objects.create(
                product=product_obj,
                name=name_key,
                label=label,
                required=True,
                parameter_type=field_type,
            )

        return is_new

    def _category_for_product(self, pdata, categories_by_remote):
        parent_id = self._clean_remote_id(pdata.get("parent_id"))
        if parent_id and parent_id in categories_by_remote:
            return categories_by_remote[parent_id]

        category_name = str(pdata.get("category_name") or pdata.get("category") or "").strip()
        if not category_name:
            return None

        remote_id = parent_id or f"name:{category_name}"
        obj, _ = ProviderCategory.objects.update_or_create(
            profile=self.profile,
            remote_id=remote_id,
            defaults={"name": category_name, "parent_remote_id": parent_id or None},
        )
        categories_by_remote[remote_id] = obj
        return obj

    def _quantity_config(self, pdata):
        qty_values = pdata.get("qty_values")
        api_type = pdata.get("product_type")

        if api_type in ("amount", "package", "fixed_quantities"):
            product_type = api_type
        elif qty_values is None:
            product_type = "package"
        elif isinstance(qty_values, dict):
            product_type = "amount"
        elif isinstance(qty_values, list):
            product_type = "fixed_quantities"
        else:
            product_type = "package"

        if isinstance(qty_values, dict):
            return product_type, self._int_or_none(qty_values.get("min")), self._int_or_none(qty_values.get("max")), []
        if isinstance(qty_values, list):
            return product_type, None, None, [str(item) for item in qty_values]
        return product_type, None, None, []

    def _extract_products(self, obj):
        products = []
        if isinstance(obj, list):
            for item in obj:
                products.extend(self._extract_products(item))
        elif isinstance(obj, dict):
            if self._looks_like_product(obj):
                products.append(obj)
            for key in ("products", "services", "items", "data", "children", "categories", "subcategories"):
                value = obj.get(key)
                if isinstance(value, (list, dict)):
                    products.extend(self._extract_products(value))
        return products

    def _extract_categories(self, obj):
        categories = []
        if isinstance(obj, list):
            for item in obj:
                categories.extend(self._extract_categories(item))
        elif isinstance(obj, dict):
            if self._looks_like_category(obj):
                categories.append(obj)
            for key in ("categories", "subcategories", "children", "data"):
                value = obj.get(key)
                if isinstance(value, (list, dict)):
                    categories.extend(self._extract_categories(value))
        return categories

    def _looks_like_product(self, obj):
        if not isinstance(obj, dict):
            return False
        has_id = (
            obj.get("id") is not None
            or obj.get("service") is not None
            or obj.get("service_id") is not None
            or obj.get("product_id") is not None
        )
        has_price_or_meta = (
            "price" in obj
            or "base_price" in obj
            or "cost" in obj
            or "rate" in obj
            or "price_usd" in obj
            or "qty_values" in obj
            or "product_type" in obj
            or "params" in obj
            or "min" in obj
            or "max" in obj
        )
        return bool(has_id and has_price_or_meta)

    def _looks_like_category(self, obj):
        return bool(
            obj.get("id") is not None
            and obj.get("name")
            and not self._looks_like_product(obj)
        )

    def _dedupe_products(self, raw_products):
        deduped = {}
        for item in raw_products:
            remote_id = self._clean_remote_id(
                item.get("id") or item.get("service") or item.get("service_id") or item.get("product_id")
            )
            if remote_id:
                deduped[remote_id] = item
        return list(deduped.items())

    def _normalize_param(self, param):
        if isinstance(param, dict):
            raw_name = str(param.get("name") or param.get("key") or param.get("label") or "param").strip()
            label = str(param.get("label") or raw_name).strip()
            field_type = str(param.get("type") or "text").strip()
        else:
            label = str(param).strip()
            raw_name = "playerId" if "الايدي" in label or "id" in label.lower() else label
            field_type = "text"
        return raw_name or "param", label or raw_name or "Param", field_type or "text"

    def _clean_remote_id(self, value):
        if value is None or value == "":
            return ""
        return str(value).strip()

    def _int_or_none(self, value):
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

    def _decimal(self, value):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0.00")
