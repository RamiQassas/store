from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant, Category

class AlkasrMapperService:
    def __init__(self, profile):
        self.profile = profile

    @transaction.atomic
    def map_to_catalog(self, provider_product: ProviderProduct):
        """Creates or updates a Product/Variant in the main store catalog."""
        store = self.profile.store
        mapping, created = ProviderMapping.objects.get_or_create(provider_product=provider_product)
        
        # 1. Map Category
        cat = None
        if provider_product.category:
            # Simple Category Mapping
            cat_name = provider_product.category.name
            cat, _ = Category.objects.get_or_create(
                name=cat_name, 
                store=store,
                defaults={"is_active": True}
            )

        # 2. Product
        is_active = provider_product.is_active and provider_product.local_is_active
        product_name = provider_product.local_name or provider_product.name
        description = provider_product.local_description or ""

        # Build schema from parameters
        schema = {"version": 1, "fields": []}
        for param in provider_product.parameters.all():
            schema["fields"].append({
                "name": param.name,
                "label": param.label,
                "type": param.parameter_type,
                "required": param.required
            })

        if not mapping.local_product:
            local_product = Product.objects.create(
                store=store,
                name=product_name,
                category=cat,
                is_active=is_active,
                is_api_product=True,
                description=description,
                form_schema=schema
            )
            mapping.local_product = local_product
        else:
            local_product = mapping.local_product
            local_product.name = product_name
            local_product.description = description
            local_product.is_active = is_active
            local_product.form_schema = schema
            if cat:
                local_product.category = cat
            local_product.save()

        # 3. Variant
        pricing = provider_product.pricing
        final_price = pricing.final_price
        
        # Build qty metadata
        meta = {
            "qty_type": "fixed",
            "qty_min": provider_product.qty_min,
            "qty_max": provider_product.qty_max,
            "qty_list": provider_product.qty_list,
            "product_type": provider_product.product_type
        }
        
        if provider_product.product_type == "amount":
            meta["qty_type"] = "range"
        elif provider_product.product_type == "fixed_quantities":
            meta["qty_type"] = "list"

        if not mapping.local_variant:
            local_variant = ProductVariant.objects.create(
                product=local_product,
                name="Default",
                sku=f"PRV-{provider_product.remote_id}",
                price=final_price,
                cost=provider_product.cost_price,
                is_active=is_active,
                metadata=meta,
                api_product_id=provider_product.remote_id
            )
            mapping.local_variant = local_variant
        else:
            local_variant = mapping.local_variant
            local_variant.price = final_price
            local_variant.cost = provider_product.cost_price
            local_variant.is_active = is_active
            local_variant.metadata = meta
            local_variant.save()

        mapping.save()
        return mapping
