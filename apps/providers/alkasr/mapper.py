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
            return cat.parent.name.strip()

        raw_cat = (cat.name if cat else "").strip()
        prod_name = pp.name.strip()
        combined = f"{raw_cat} {prod_name}".upper()

        if "PUBG" in combined or "UC" in combined or raw_cat.upper().startswith("UC"):
            return "PUBG Mobile"

        if "سيرتيل" in raw_cat or "سيريتل" in raw_cat or "SYRIATEL" in combined:
            return "رصيد سيرتيل (Syriatel)"

        if "MTN" in combined or "ام تي ان" in raw_cat or "إم تي إن" in raw_cat:
            return "رصيد MTN"

        if "FREE FIRE" in combined or "فري فاير" in raw_cat or "فراي فاير" in raw_cat:
            return "فري فاير (Free Fire)"

        if "TIKTOK" in combined or "تيك توك" in raw_cat:
            return "تيك توك (TikTok)"

        if "YALLA" in combined or "يلا لودو" in raw_cat:
            return "يلا لودو (Yalla Ludo)"

        if raw_cat and not raw_cat.upper().startswith("UC"):
            return raw_cat

        return prod_name or f"Product {pp.remote_id}"

    @transaction.atomic
    def map_all_to_catalog(self, products_qs=None):
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
                        "qty_list": pp.qty_list,
                        "product_type": pp.product_type
                    }
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
                            is_active=True,  # Active by default
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
