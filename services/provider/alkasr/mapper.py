"""
Alkasr Catalog Mapper Engine.
Maps ProviderProduct records into main store catalog Product & ProductVariant models.
"""

import logging
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant

logger = logging.getLogger("provider.alkasr.mapper")


class AlkasrMapperService:
    """Service for mapping provider products into store catalog."""

    def __init__(self, profile):
        self.profile = profile

    def _get_group_name(self, pp: ProviderProduct) -> str:
        prod_name = pp.name.strip()
        if not prod_name or prod_name.lower() in ("null", "none"):
            return f"منتج {pp.remote_id}"
        return prod_name

    def map_all_to_catalog(self, products_qs=None, selected_group_names=None) -> int:
        """
        Batch maps provider products into main store catalog (catalog.Product & catalog.ProductVariant).
        """
        if products_qs is None:
            products_qs = ProviderProduct.objects.filter(profile=self.profile)

        products_list = list(
            products_qs.select_related("category", "category__parent", "pricing").prefetch_related("parameters")
        )
        store = getattr(self.profile, "store", None)

        grouped_products = {}
        for pp in products_list:
            group_name = self._get_group_name(pp)
            if selected_group_names and len(selected_group_names) > 0 and group_name not in selected_group_names:
                continue
            grouped_products.setdefault(group_name, []).append(pp)

        mapped_count = 0
        for group_name, p_items in grouped_products.items():
            with transaction.atomic():
                try:
                    local_product = Product.objects.filter(
                        store=store,
                        name=group_name,
                        is_api_product=True
                    ).first()

                    schema_fields = {}
                    for pp in p_items:
                        for param in pp.parameters.all():
                            if param.name not in schema_fields:
                                schema_fields[param.name] = {
                                    "name": param.name,
                                    "label": param.label,
                                    "type": param.parameter_type,
                                    "required": param.required
                                }
                    schema = {"version": 1, "fields": list(schema_fields.values())}

                    from apps.catalog.models import Category
                    cat_obj = None
                    if p_items[0].category and p_items[0].category.name:
                        cat_name = p_items[0].category.name.strip()
                        if cat_name and cat_name.lower() not in ("null", "none"):
                            cat_obj = Category.objects.filter(store=store, name=cat_name).first()
                            if not cat_obj:
                                cat_obj = Category.objects.create(store=store, name=cat_name, is_active=True)

                    if not local_product:
                        local_product = Product.objects.create(
                            store=store,
                            name=group_name,
                            category=cat_obj,
                            is_active=True,
                            is_out_of_stock=False,
                            track_inventory=False,
                            quantity=999999,
                            is_api_product=True,
                            api_provider=getattr(self.profile, "provider_name", "alkasr"),
                            description=p_items[0].local_description or "",
                            form_schema=schema
                        )
                    else:
                        if store and local_product.store != store:
                            local_product.store = store
                        if not local_product.category and cat_obj:
                            local_product.category = cat_obj
                        local_product.is_active = True
                        local_product.is_out_of_stock = False
                        local_product.track_inventory = False
                        local_product.quantity = 999999
                        local_product.is_api_product = True
                        local_product.api_provider = getattr(self.profile, "provider_name", "alkasr")
                        if schema_fields:
                            local_product.form_schema = schema
                        local_product.save()

                    for pp in p_items:
                        mapping = ProviderMapping.objects.filter(provider_product=pp).first()
                        if not mapping:
                            mapping = ProviderMapping(provider_product=pp)

                        mapping.local_product = local_product

                        pricing = getattr(pp, "pricing", None)
                        final_price = pricing.final_price if pricing else pp.cost_price
                        wholesale_price = pricing.final_wholesale_price if pricing else pp.cost_price
                        vip_price = pricing.final_vip_price if pricing else pp.cost_price

                        meta = {
                            "qty_type": "fixed",
                            "qty_min": pp.qty_min,
                            "qty_max": pp.qty_max,
                            "product_type": pp.product_type
                        }
                        if pp.qty_list:
                            meta["qty_list"] = pp.qty_list

                        if pp.product_type == "amount" and getattr(pp, "qty_min", 0) >= 10:
                            meta["is_per_mille"] = True

                        if pp.product_type == "amount":
                            meta["qty_type"] = "range"
                        elif pp.product_type == "fixed_quantities":
                            meta["qty_type"] = "list"

                        variant_name = (pp.local_name or pp.name).strip()
                        if not variant_name:
                            variant_name = f"الباقة {pp.remote_id}"

                        sku_val = f"PRV-{self.profile.id}-{pp.remote_id}"

                        local_variant = ProductVariant.objects.filter(sku=sku_val).first()
                        if not local_variant:
                            local_variant = ProductVariant.objects.filter(
                                api_product_id=pp.remote_id, product=local_product
                            ).first()

                        if not local_variant:
                            local_variant = ProductVariant.objects.create(
                                product=local_product,
                                name=variant_name,
                                sku=sku_val,
                                price=final_price,
                                wholesale_price=wholesale_price,
                                vip_price=vip_price,
                                cost=pp.cost_price,
                                is_active=pp.is_active,
                                is_temporarily_disabled=False,
                                metadata=meta,
                                api_product_id=pp.remote_id
                            )
                        else:
                            local_variant.product = local_product
                            local_variant.name = variant_name
                            local_variant.price = final_price
                            local_variant.wholesale_price = wholesale_price
                            local_variant.vip_price = vip_price
                            local_variant.cost = pp.cost_price
                            local_variant.is_active = pp.is_active
                            local_variant.is_temporarily_disabled = False
                            local_variant.metadata = meta
                            local_variant.api_product_id = pp.remote_id
                            local_variant.save()

                        mapping.local_variant = local_variant
                        mapping.save()
                        mapped_count += 1

                except Exception as e:
                    logger.exception(f"Error mapping group '{group_name}' to catalog: {e}")
                    continue

        return mapped_count
