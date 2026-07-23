import logging
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant

logger = logging.getLogger(__name__)

class AlkasrMapperService:
    def __init__(self, profile):
        self.profile = profile

    def _get_group_name(self, pp):
        cat = pp.category
        if cat and cat.parent and cat.parent.name:
            parent_name = str(cat.parent.name).strip()
            if parent_name.lower() not in ("null", "none"):
                return parent_name

        raw_cat = (cat.name if cat else "").strip()
        if raw_cat and raw_cat.lower() not in ("null", "none"):
            return raw_cat
            
        prod_name = pp.name.strip()
        if not prod_name or prod_name.lower() in ("null", "none"):
            return "منتجات بدون تصنيف"
            
        return prod_name

    @transaction.atomic
    def map_all_to_catalog(self, products_qs=None, selected_group_names=None):
        """
        Batch map provider products into main store catalog.
        - Groups packages belonging to the same service under 1 Product with multiple ProductVariants (باقات).
        - Does NOT auto-create categories (user categorizes manually).
        - Ensures store=self.profile.store is set so products appear on /catalog/.
        """
        if products_qs is None:
            products_qs = ProviderProduct.objects.filter(profile=self.profile)
            
        products_list = list(products_qs.select_related('category', 'category__parent', 'pricing').prefetch_related('parameters'))
        store = self.profile.store

        # Group provider products by main service name (e.g. PUBG Mobile, Syriatel)
        grouped_products = {}
        for pp in products_list:
            group_name = self._get_group_name(pp)
            if selected_group_names is not None and group_name not in selected_group_names:
                continue
            grouped_products.setdefault(group_name, []).append(pp)

        for group_name, p_items in grouped_products.items():
            try:
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
                        category=None,  # No auto-category creation (user categorizes manually)
                        is_active=True,  # Active by default (not draft)
                        is_out_of_stock=False, # Available by default
                        track_inventory=False, # Disable inventory tracking for API products
                        quantity=999999, # Unlimited stock
                        is_api_product=True,
                        api_provider="alkasr",
                        description=p_items[0].local_description or "",
                        form_schema=schema
                    )
                else:
                    if store and local_product.store != store:
                        local_product.store = store
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

                    meta = {
                        "qty_type": "fixed",
                        "qty_min": pp.qty_min,
                        "qty_max": pp.qty_max,
                        "product_type": pp.product_type
                    }
                    if pp.qty_list:
                        meta["qty_list"] = pp.qty_list
                    
                    if pp.product_type == "amount" and getattr(pp, 'qty_min', 0) >= 10:
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
                            is_active=pp.is_active,  # Match provider active state
                            is_temporarily_disabled=False, # Available by default
                            metadata=meta,
                            api_product_id=pp.remote_id
                        )
                    else:
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

            except Exception as e:
                logger.exception("Error mapping group '%s' to catalog: %s", group_name, e)
                continue

    @transaction.atomic
    def map_to_catalog(self, provider_product: ProviderProduct):
        """Creates or updates a Product/Variant in the main store catalog."""
        return self.map_all_to_catalog(ProviderProduct.objects.filter(id=provider_product.id))
