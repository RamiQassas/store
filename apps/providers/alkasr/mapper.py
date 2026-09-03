import logging
from decimal import Decimal
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant, Category

logger = logging.getLogger(__name__)

class AlkasrMapperService:
    def __init__(self, profile):
        self.profile = profile

    def _get_group_name(self, pp):
        """
        Determines the parent Product name (e.g. PUBG Mobile, Free Fire, Syriatel, MTN).
        """
        cat = pp.category
        raw_cat = (cat.name if cat else "").strip()
        
        generic_names = {
            "null", "none", "games", "live application", "data and communication", 
            "gift cards", "tv services", "money transfers", "social media", 
            "numbers and accounts", "program activation numbers", "ألعاب", "عام"
        }
        
        # 1. If category itself is a specific service/game (not a top-level category)
        if raw_cat and raw_cat.lower() not in generic_names:
            return raw_cat
            
        # 2. If category has a parent that is a specific service/game
        if cat and cat.parent and cat.parent.name:
            p_name = str(cat.parent.name).strip()
            if p_name.lower() not in generic_names:
                return p_name
                
        # 3. Derive from product name prefix
        prod_name = pp.name.strip()
        for prefix in ("PUBG Mobile", "PUBG TR", "Pubg Mobile", "FREE FIRE", "Free fire", "LORDS MOBILE", 
                       "ROBLOX", "Syriatell", "Syriatel", "MTN", "Tik tok", "NETFLIX", "+Disney", "+Osn"):
            if prod_name.lower().startswith(prefix.lower()):
                return prefix

        return raw_cat or prod_name or "خدمة عامة"

    def _get_store_category(self, pp, store):
        """
        Maps Alkasr root categories into user-friendly Arabic store categories:
        - ألعاب (Games)
        - اتصالات ورصيد (Data and Communication / Telecom)
        - تطبيقات وبرامج (Live Application / Apps)
        - بطاقات رقمية (Gift Cards)
        - خدمات التلفزيون والبث (Tv Services)
        - تحويلات مالية (Money Transfers)
        - سوشيال ميديا (Social Media)
        """
        curr = pp.category
        root_name = ""
        while curr:
            if curr.name and curr.name.strip().lower() not in ("null", "none"):
                root_name = curr.name.strip()
            curr = curr.parent

        category_map = {
            "games": "ألعاب",
            "live application": "تطبيقات وبرامج",
            "data and communication": "اتصالات ورصيد",
            "gift cards": "بطاقات رقمية",
            "tv services": "خدمات التلفزيون والبث",
            "money transfers": "تحويلات مالية",
            "social media": "سوشيال ميديا",
            "numbers and accounts": "أرقام وحسابات",
            "program activation numbers": "تفعيل برامج واشتراكات",
        }
        
        ar_name = category_map.get(root_name.lower(), root_name or "خدمات رقمية")
        cat_obj, _ = Category.objects.get_or_create(
            store=store,
            name=ar_name,
            defaults={"is_active": True, "sort_order": 0}
        )
        return cat_obj

    @transaction.atomic
    def map_all_to_catalog(self, products_qs=None, selected_group_names=None):
        """
        Batch map provider products into main store catalog.
        - Groups packages belonging to the same service under 1 Product with multiple ProductVariants (باقات).
        - Automatically organizes products under top-level Categories (ألعاب، اتصالات ورصيد، تطبيقات وبرامج...).
        - Sets accurate qty_type, min, max, params, and per-mille pricing calculation rules.
        """
        if products_qs is None:
            products_qs = ProviderProduct.objects.filter(profile=self.profile)
            
        products_list = list(products_qs.select_related('category', 'category__parent', 'pricing').prefetch_related('parameters'))
        store = self.profile.store

        # Group provider products by main service name (e.g. PUBG Mobile, Free Fire, Syriatel, MTN)
        grouped_products = {}
        for pp in products_list:
            group_name = self._get_group_name(pp)
            if selected_group_names is not None and group_name not in selected_group_names:
                continue
            grouped_products.setdefault(group_name, []).append(pp)

        for group_name, p_items in grouped_products.items():
            try:
                # Find or create store category for this group
                store_category = self._get_store_category(p_items[0], store)

                # Find existing Product or create a new one
                local_product = Product.objects.filter(
                    store=store,
                    name=group_name,
                    is_api_product=True,
                    api_provider="alkasr"
                ).first()

                # Build combined parameters form_schema for this product
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

                if not local_product:
                    local_product = Product.objects.create(
                        store=store,
                        name=group_name,
                        category=store_category,
                        is_active=True,
                        is_out_of_stock=False,
                        track_inventory=False,
                        quantity=999999,
                        is_api_product=True,
                        api_provider="alkasr",
                        description=p_items[0].local_description or "",
                        form_schema=schema
                    )
                else:
                    if store and local_product.store != store:
                        local_product.store = store
                    if not local_product.category or local_product.category != store_category:
                        local_product.category = store_category
                    local_product.is_active = True
                    local_product.is_out_of_stock = False
                    local_product.track_inventory = False
                    local_product.quantity = 999999
                    local_product.is_api_product = True
                    local_product.api_provider = "alkasr"
                    if schema_fields:
                        local_product.form_schema = schema
                    local_product.save()

                # Map each ProviderProduct as a ProductVariant (باقة) inside this single Product
                for pp in p_items:
                    mapping = ProviderMapping.objects.filter(provider_product=pp).first()
                    if not mapping:
                        mapping = ProviderMapping(provider_product=pp)

                    mapping.local_product = local_product

                    pricing = getattr(pp, 'pricing', None)
                    final_price = pricing.final_price if pricing else pp.cost_price
                    wholesale_price = pricing.final_wholesale_price if pricing else pp.cost_price
                    vip_price = pricing.final_vip_price if pricing else pp.cost_price

                    # Determine quantity type, min, max, list, and per-mille flag
                    qty_min = getattr(pp, 'qty_min', None)
                    try:
                        qty_min = int(qty_min) if qty_min is not None else None
                    except (ValueError, TypeError):
                        qty_min = None

                    qty_max = getattr(pp, 'qty_max', None)
                    try:
                        qty_max = int(qty_max) if qty_max is not None else None
                    except (ValueError, TypeError):
                        qty_max = None

                    qty_list = getattr(pp, 'qty_list', None) or []

                    if qty_list and len(qty_list) > 0:
                        qty_type = "list"
                    elif qty_max is not None and qty_min is not None and (qty_max > qty_min or (qty_min > 1 and qty_max > 1)):
                        qty_type = "range"
                    elif pp.product_type == "amount":
                        qty_type = "range"
                    elif pp.product_type in ("fixed_quantities", "specificPackage"):
                        qty_type = "list"
                    else:
                        qty_type = "fixed"

                    is_per_mille = False
                    if qty_min is not None and qty_min >= 100:
                        is_per_mille = True
                    elif pp.product_type == "amount" and (qty_min is None or qty_min >= 10):
                        is_per_mille = True

                    meta = {
                        "qty_type": qty_type,
                        "qty_min": qty_min or 1,
                        "qty_max": qty_max or 999999,
                        "qty_list": qty_list,
                        "is_per_mille": is_per_mille,
                        "product_type": pp.product_type,
                        "params": [
                            {
                                "name": param.name,
                                "label": param.label,
                                "type": param.parameter_type,
                                "required": param.required
                            }
                            for param in pp.parameters.all()
                        ]
                    }

                    variant_name = (pp.local_name or pp.name).strip()
                    if not variant_name:
                        variant_name = f"الباقة {pp.remote_id}"

                    sku_val = f"PRV-{self.profile.id}-{pp.remote_id}"

                    local_variant = ProductVariant.objects.filter(sku=sku_val).first()
                    if not local_variant:
                        local_variant = ProductVariant.objects.filter(api_product_id=pp.remote_id, product=local_product).first()

                    if not local_variant:
                        local_variant = ProductVariant.objects.create(
                            product=local_product,
                            name=variant_name,
                            sku=sku_val,
                            price=final_price,
                            wholesale_price=wholesale_price,
                            vip_price=vip_price,
                            cost=pp.cost_price,
                            is_active=True,
                            is_temporarily_disabled=False,
                            metadata=meta,
                            api_product_id=pp.remote_id
                        )
                    else:
                        local_variant.name = variant_name
                        local_variant.price = final_price
                        local_variant.wholesale_price = wholesale_price
                        local_variant.vip_price = vip_price
                        local_variant.cost = pp.cost_price
                        local_variant.is_active = True
                        local_variant.is_temporarily_disabled = False
                        local_variant.metadata = meta
                        local_variant.api_product_id = pp.remote_id
                        local_variant.save()

                    mapping.local_variant = local_variant
                    mapping.save()

            except Exception as e:
                logger.exception("Error mapping group '%s' to catalog: %s", group_name, e)
                continue

    @transaction.atomic
    def map_to_catalog(self, provider_product: ProviderProduct):
        """Creates or updates a Product/Variant in the main store catalog."""
        return self.map_all_to_catalog(ProviderProduct.objects.filter(id=provider_product.id))
