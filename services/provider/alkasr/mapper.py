"""
Canonical Alkasr Product & Package Mapping Engine.
Strictly relies on provider_product_id and parent_id as the SINGLE SOURCE OF TRUTH.
Eliminates all fuzzy regexes, synthetic variants, and random package assignments.
"""

import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.db import transaction
from django.db.models import Exists, OuterRef

logger = logging.getLogger("provider.alkasr.mapper")


class AlkasrMapperService:
    """
    Canonical Mapper for Alkasr VIP Provider Catalog.
    
    Rules:
    1. Root Product: ProviderProduct with remote_parent_id in (None, '', '0', 0) OR product_type == 'amount'.
       Maps to apps.catalog.models.Product where api_product_id == pp.remote_id.
    2. Package (Child): ProviderProduct with remote_parent_id > 0 AND product_type != 'amount'.
       Maps strictly to apps.catalog.models.ProductVariant where:
       - variant.product.api_product_id == pp.remote_parent_id
       - variant.api_product_id == pp.remote_id
       - variant.provider_parent_id == pp.remote_parent_id
    3. ZERO heuristic matching, ZERO fake servers, ZERO synthetic bundling.
    """

    def __init__(self, profile):
        self.profile = profile
        self.store = getattr(profile, "store", None)

    @staticmethod
    def build_form_schema(raw_params: list) -> dict:
        """Constructs catalog form_schema from provider parameters list."""
        fields = []
        seen_names = set()

        if isinstance(raw_params, list):
            for idx, p in enumerate(raw_params):
                if isinstance(p, dict):
                    name = str(p.get("name") or p.get("key") or f"param_{idx}").strip()
                    label = str(p.get("label") or p.get("name") or name).strip()
                    p_type = str(p.get("type") or "text").strip()
                    required = bool(p.get("required", True))
                elif isinstance(p, str):
                    clean_str = p.strip()
                    name = "playerId" if idx == 0 else f"param_{idx}"
                    label = clean_str or "معرف الحساب"
                    p_type = "text"
                    required = True
                else:
                    continue

                if name and name not in seen_names:
                    seen_names.add(name)
                    fields.append({
                        "name": name,
                        "label": label,
                        "type": p_type,
                        "required": required
                    })

        return {"version": 1, "fields": fields}

    def _get_or_create_catalog_category(self, category_name: str):
        """Resolves or creates a Category in catalog.Category."""
        from apps.catalog.models import Category

        clean_name = (category_name or "عام").strip()
        cat = Category.objects.filter(store=self.store, name=clean_name).first()
        if not cat:
            cat = Category.objects.create(
                store=self.store,
                name=clean_name,
                is_active=True
            )
        return cat

    def map_all_to_catalog(self, selected_group_names=None) -> Dict[str, int]:
        """
        Executes full canonical mapping for this profile's ProviderProducts.
        """
        from apps.providers.models import ProviderProduct, ProviderMapping, ProviderPrice
        from apps.catalog.models import Product, ProductVariant

        provider_code = "alkasr"
        products_qs = ProviderProduct.objects.filter(profile=self.profile)

        stats = {
            "root_products_created": 0,
            "root_products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "variants_reassigned": 0,
            "disabled_count": 0,
        }

        # 1. Partition into Root Products and Packages
        root_pps = []
        child_pps = []

        for pp in products_qs:
            parent_id = str(pp.remote_parent_id or "").strip()
            is_root = parent_id in ("", "0", "None", "null") or pp.product_type == "amount"
            if is_root:
                root_pps.append(pp)
            else:
                child_pps.append(pp)

        # 2. Map ROOT Products
        mapped_root_products: Dict[int, Product] = {}

        for pp in root_pps:
            try:
                pid = int(pp.remote_id)
            except (ValueError, TypeError):
                logger.warning("Skipping ProviderProduct %s: invalid numeric remote_id", pp.remote_id)
                continue

            with transaction.atomic():
                cat_name = pp.provider_category_name or (pp.category.name if pp.category else "") or "عام"
                catalog_cat = self._get_or_create_catalog_category(cat_name)

                # Match Product strictly by (store, api_provider, api_product_id)
                local_product = Product.objects.filter(
                    store=self.store,
                    api_provider=provider_code,
                    api_product_id=pid
                ).first()

                # Fallback to existing ProviderMapping if api_product_id was missing previously
                if not local_product:
                    mapping = ProviderMapping.objects.filter(provider_product=pp).select_related("local_product").first()
                    if mapping and mapping.local_product:
                        local_product = mapping.local_product
                        local_product.api_product_id = pid
                        local_product.provider_parent_id = 0
                        local_product.api_provider = provider_code

                is_active = bool(pp.is_active and pp.local_is_active)
                schema = self.build_form_schema(pp.raw_params)
                prod_name = pp.local_name or pp.name

                meta = dict(local_product.metadata or {}) if local_product else {}
                if pp.provider_category_img:
                    meta["image_url"] = pp.provider_category_img
                meta["remote_id"] = str(pid)
                meta["product_type"] = pp.product_type

                if not local_product:
                    local_product = Product.objects.create(
                        store=self.store,
                        name=prod_name[:160],
                        category=catalog_cat,
                        is_active=is_active,
                        is_out_of_stock=not is_active,
                        track_inventory=False,
                        quantity=999999,
                        is_api_product=True,
                        api_provider=provider_code,
                        api_product_id=pid,
                        provider_parent_id=0,
                        description=pp.local_description or "",
                        form_schema=schema,
                        metadata=meta
                    )
                    stats["root_products_created"] += 1
                else:
                    local_product.category = catalog_cat
                    local_product.is_api_product = True
                    local_product.api_provider = provider_code
                    local_product.api_product_id = pid
                    local_product.provider_parent_id = 0
                    local_product.form_schema = schema
                    local_product.metadata = meta
                    local_product.save()
                    stats["root_products_updated"] += 1

                mapped_root_products[pid] = local_product

                # Update ProviderMapping
                ProviderMapping.objects.update_or_create(
                    provider_product=pp,
                    defaults={
                        "local_product": local_product
                    }
                )

                # If amount product, it is purchasable directly -> create primary ProductVariant
                if pp.product_type == "amount":
                    pricing = getattr(pp, "pricing", None)
                    cost = pp.cost_price
                    final_price = pricing.final_price if pricing else cost
                    wholesale_price = pricing.final_wholesale_price if pricing else cost
                    vip_price = pricing.final_vip_price if pricing else cost

                    sku_val = f"PRV-{self.profile.id}-{pid}"[:80]
                    v_meta = {
                        "qty_type": "range",
                        "qty_min": pp.qty_min or 1,
                        "qty_max": pp.qty_max or 999999,
                        "qty_list": pp.qty_list or [],
                        "product_type": "amount",
                        "remote_id": str(pid),
                        "params": pp.raw_params or []
                    }

                    var, v_created = ProductVariant.objects.update_or_create(
                        sku=sku_val,
                        defaults={
                            "product": local_product,
                            "name": (pp.local_name or pp.name)[:120],
                            "api_product_id": pid,
                            "provider_parent_id": 0,
                            "cost": cost,
                            "price": final_price,
                            "wholesale_price": wholesale_price,
                            "vip_price": vip_price,
                            "is_active": is_active,
                            "is_temporarily_disabled": not is_active,
                            "metadata": v_meta
                        }
                    )
                    if v_created:
                        stats["variants_created"] += 1
                    else:
                        stats["variants_updated"] += 1

                    mapping = ProviderMapping.objects.filter(provider_product=pp).first()
                    if mapping:
                        mapping.local_variant = var
                        mapping.save(update_fields=["local_variant", "updated_at"])

        # 3. Map PACKAGES (Child Variants) strictly to Product with api_product_id == parent_id
        for pp in child_pps:
            try:
                pkg_pid = int(pp.remote_id)
                parent_pid = int(pp.remote_parent_id)
            except (ValueError, TypeError):
                logger.warning("Skipping package %s: invalid remote_id or parent_id", pp.remote_id)
                continue

            with transaction.atomic():
                # Strictly find parent Product
                parent_product = mapped_root_products.get(parent_pid)
                if not parent_product:
                    parent_product = Product.objects.filter(
                        store=self.store,
                        api_provider=provider_code,
                        api_product_id=parent_pid
                    ).first()

                # If parent product does not exist, check if a ProviderProduct exists for it
                if not parent_product:
                    parent_pp = ProviderProduct.objects.filter(profile=self.profile, remote_id=str(parent_pid)).first()
                    cat_name = (parent_pp.provider_category_name if parent_pp else (pp.provider_category_name or (pp.category.name if pp.category else ""))) or "عام"
                    catalog_cat = self._get_or_create_catalog_category(cat_name)
                    parent_name = (parent_pp.name if parent_pp else None) or pp.provider_category_name or (pp.category.name if pp.category else None) or f"الخدمة #{parent_pid}"

                    parent_product = Product.objects.create(
                        store=self.store,
                        name=parent_name[:160],
                        category=catalog_cat,
                        is_active=True,
                        is_out_of_stock=False,
                        track_inventory=False,
                        quantity=999999,
                        is_api_product=True,
                        api_provider=provider_code,
                        api_product_id=parent_pid,
                        provider_parent_id=0,
                    )
                    mapped_root_products[parent_pid] = parent_product
                    stats["root_products_created"] += 1

                # Calculate Pricing
                pricing = getattr(pp, "pricing", None)
                cost = pp.cost_price
                final_price = pricing.final_price if pricing else cost
                wholesale_price = pricing.final_wholesale_price if pricing else cost
                vip_price = pricing.final_vip_price if pricing else cost

                # Determine quantity type
                if pp.product_type == "fixed_quantities" or (pp.qty_list and len(pp.qty_list) > 0):
                    qty_type = "list"
                elif pp.product_type == "amount" or (pp.qty_min and pp.qty_max and pp.qty_max > pp.qty_min and pp.qty_max > 1):
                    qty_type = "range"
                else:
                    qty_type = "fixed"

                sku_val = f"PRV-{self.profile.id}-{pkg_pid}"[:80]
                is_active = bool(pp.is_active and pp.local_is_active)
                v_name = (pp.local_name or pp.name)[:120]

                v_meta = {
                    "qty_type": qty_type,
                    "qty_min": pp.qty_min or 1,
                    "qty_max": pp.qty_max or 999999,
                    "qty_list": pp.qty_list or [],
                    "product_type": pp.product_type,
                    "remote_id": str(pkg_pid),
                    "parent_id": str(parent_pid),
                    "params": pp.raw_params or []
                }

                # Find existing variant by SKU or by (api_product_id, provider_parent_id)
                local_variant = ProductVariant.objects.filter(sku=sku_val).first()
                if not local_variant:
                    local_variant = ProductVariant.objects.filter(
                        api_product_id=pkg_pid,
                        provider_parent_id=parent_pid
                    ).first()

                if not local_variant:
                    local_variant = ProductVariant.objects.create(
                        product=parent_product,
                        name=v_name,
                        sku=sku_val,
                        price=final_price,
                        wholesale_price=wholesale_price,
                        vip_price=vip_price,
                        cost=cost,
                        is_active=is_active,
                        is_temporarily_disabled=not is_active,
                        api_product_id=pkg_pid,
                        provider_parent_id=parent_pid,
                        metadata=v_meta
                    )
                    stats["variants_created"] += 1
                else:
                    # Enforce that variant is linked to the true parent Product
                    if local_variant.product_id != parent_product.id:
                        local_variant.product = parent_product
                        stats["variants_reassigned"] += 1

                    local_variant.name = v_name
                    local_variant.price = final_price
                    local_variant.wholesale_price = wholesale_price
                    local_variant.vip_price = vip_price
                    local_variant.cost = cost
                    local_variant.is_active = is_active
                    local_variant.is_temporarily_disabled = not is_active
                    local_variant.api_product_id = pkg_pid
                    local_variant.provider_parent_id = parent_pid
                    local_variant.metadata = v_meta
                    local_variant.save()
                    stats["variants_updated"] += 1

                # Update ProviderMapping
                ProviderMapping.objects.update_or_create(
                    provider_product=pp,
                    defaults={
                        "local_product": parent_product,
                        "local_variant": local_variant
                    }
                )

        # 4. Soft-disable Stale Variants & Products
        with transaction.atomic():
            active_provider_pids = set()
            for p in products_qs.filter(is_active=True):
                try:
                    active_provider_pids.add(int(p.remote_id))
                except (ValueError, TypeError):
                    pass

            # Deactivate variants whose provider product is disabled or deleted
            stale_variants = ProductVariant.objects.filter(
                sku__startswith=f"PRV-{self.profile.id}-"
            ).exclude(api_product_id__in=active_provider_pids)

            disabled_cnt = stale_variants.filter(is_active=True).update(
                is_active=False,
                is_temporarily_disabled=True
            )
            stats["disabled_count"] += disabled_cnt

            # Re-evaluate Product is_active based on having at least one active variant
            active_vars = ProductVariant.objects.filter(
                product=OuterRef("pk"),
                is_active=True,
                is_temporarily_disabled=False
            )

            # Products with active variants -> active
            Product.objects.filter(
                store=self.store,
                api_provider=provider_code
            ).annotate(has_active=Exists(active_vars)).filter(has_active=True).update(
                is_active=True,
                is_out_of_stock=False
            )

            # Products with NO active variants -> inactive & out of stock
            Product.objects.filter(
                store=self.store,
                api_provider=provider_code
            ).annotate(has_active=Exists(active_vars)).filter(has_active=False).update(
                is_active=False,
                is_out_of_stock=True
            )

        return stats

    @classmethod
    def cleanup_corrupted_mappings(cls, profile=None) -> Dict[str, int]:
        """
        Database cleanup routine (PHASE 6).
        Identifies and repairs misassigned packages across the catalog:
        1. Fixes variants where variant.product.api_product_id != variant.provider_parent_id.
        2. Deactivates synthetic / fake variants.
        """
        from apps.catalog.models import Product, ProductVariant

        reassigned_count = 0
        deactivated_count = 0

        qs = ProductVariant.objects.filter(
            provider_parent_id__isnull=False,
            provider_parent_id__gt=0
        ).select_related("product")

        if profile:
            qs = qs.filter(sku__startswith=f"PRV-{profile.id}-")

        with transaction.atomic():
            for v in qs:
                # If variant parent does not match Product.api_product_id
                if not v.product or v.product.api_product_id != v.provider_parent_id:
                    correct_parent = Product.objects.filter(
                        api_provider="alkasr",
                        api_product_id=v.provider_parent_id
                    ).first()

                    if correct_parent:
                        v.product = correct_parent
                        v.save(update_fields=["product", "updated_at"])
                        reassigned_count += 1
                    else:
                        v.is_active = False
                        v.is_temporarily_disabled = True
                        v.save(update_fields=["is_active", "is_temporarily_disabled", "updated_at"])
                        deactivated_count += 1

        logger.info(
            "Cleanup completed: %d variants reassigned to correct parent, %d orphaned variants deactivated.",
            reassigned_count, deactivated_count
        )
        return {
            "reassigned_count": reassigned_count,
            "deactivated_count": deactivated_count
        }
