import logging
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.tenant_utils import bypass_tenant_filter

logger = logging.getLogger(__name__)

def import_raqamiyat_products_for_store(store):
    """
    Imports and synchronizes all active global Raqamiyat categories, products,
    and variants into a specific tenant store with full tenant isolation.
    """
    if not store:
        return {"categories_created": 0, "products_created": 0, "variants_created": 0}

    stats = {
        "categories_created": 0,
        "categories_updated": 0,
        "products_created": 0,
        "products_updated": 0,
        "variants_created": 0,
        "variants_updated": 0,
    }

    with bypass_tenant_filter():
        # 1. Map and clone global categories to the store
        global_categories = Category.all_objects.filter(store__isnull=True, is_active=True).order_by("sort_order", "name")
        cat_mapping = {}  # global_cat_id -> store_cat

        for g_cat in global_categories:
            store_cat, created = Category.all_objects.get_or_create(
                store=store,
                name=g_cat.name,
                defaults={
                    "image": g_cat.image,
                    "is_active": g_cat.is_active,
                    "is_featured": g_cat.is_featured,
                    "sort_order": g_cat.sort_order,
                }
            )
            if created:
                stats["categories_created"] += 1
            else:
                stats["categories_updated"] += 1
            cat_mapping[g_cat.id] = store_cat

        # Extract tier margins if configured by store owner
        from decimal import Decimal
        tier_margins = getattr(store, "tier_margins", {}) or {}
        try:
            cust_m = Decimal(str(tier_margins.get("customer", 0) or 0))
        except: cust_m = Decimal("0")
        try:
            deal_m = Decimal(str(tier_margins.get("dealer", 0) or 0))
        except: deal_m = Decimal("0")
        try:
            vip_m = Decimal(str(tier_margins.get("vip", 0) or 0))
        except: vip_m = Decimal("0")

        # 2. Map and clone global products to the store
        global_products = Product.all_objects.filter(
            store__isnull=True, 
            is_active=True
        ).prefetch_related("variants").order_by("sort_order", "id")

        for g_prod in global_products:
            target_cat = cat_mapping.get(g_prod.category_id) if g_prod.category_id else None
            
            # Check if this product already exists in the store by name
            store_prod = Product.all_objects.filter(store=store, name=g_prod.name).first()
            if not store_prod:
                store_prod = Product.all_objects.create(
                    store=store,
                    name=g_prod.name,
                    category=target_cat,
                    product_type=g_prod.product_type,
                    image=g_prod.image,
                    cover_image=g_prod.cover_image,
                    thumbnail=g_prod.thumbnail,
                    description=g_prod.description,
                    instructions=g_prod.instructions,
                    is_active=g_prod.is_active,
                    is_featured=g_prod.is_featured,
                    is_out_of_stock=g_prod.is_out_of_stock,
                    is_sale=g_prod.is_sale,
                    is_api_product=g_prod.is_api_product,
                    api_provider=g_prod.api_provider,
                    sort_order=g_prod.sort_order,
                    delivery_time_display=g_prod.delivery_time_display,
                    track_inventory=g_prod.track_inventory,
                    quantity=g_prod.quantity,
                    low_stock_threshold=g_prod.low_stock_threshold,
                    form_schema=g_prod.form_schema,
                )
                stats["products_created"] += 1
            else:
                # Update category if needed
                if target_cat and store_prod.category != target_cat:
                    store_prod.category = target_cat
                    store_prod.save(update_fields=["category"])
                stats["products_updated"] += 1

            # 3. Clone variants
            store_id_short = str(store.id)[:6] if hasattr(store, 'id') and store.id else "sub"
            for g_var in g_prod.variants.all():
                var_sku = f"{g_var.sku or 'SKU'}-{store_id_short}"
                base_cost = g_var.cost or Decimal("0")
                
                # Calculate prices using store tier profit margins
                if cust_m > 0 and base_cost > 0:
                    var_price = (base_cost * (Decimal("1") + cust_m / Decimal("100"))).quantize(Decimal("0.01"))
                else:
                    var_price = g_var.price

                if deal_m > 0 and base_cost > 0:
                    var_wholesale = (base_cost * (Decimal("1") + deal_m / Decimal("100"))).quantize(Decimal("0.01"))
                else:
                    var_wholesale = g_var.wholesale_price or g_var.price

                if vip_m > 0 and base_cost > 0:
                    var_vip = (base_cost * (Decimal("1") + vip_m / Decimal("100"))).quantize(Decimal("0.01"))
                else:
                    var_vip = g_var.vip_price or g_var.price

                store_var, v_created = ProductVariant.objects.get_or_create(
                    product=store_prod,
                    name=g_var.name,
                    defaults={
                        "sku": var_sku,
                        "price": var_price,
                        "cost": g_var.cost,
                        "wholesale_price": var_wholesale,
                        "vip_price": var_vip,
                        "is_active": g_var.is_active,
                        "is_temporarily_disabled": g_var.is_temporarily_disabled,
                        "is_sale": g_var.is_sale,
                        "discount_percent": g_var.discount_percent,
                        "delivery_type": g_var.delivery_type,
                        "is_recharge_card": g_var.is_recharge_card,
                        "recharge_amount": g_var.recharge_amount,
                        "recharge_currency": g_var.recharge_currency,
                        "api_product_id": g_var.api_product_id,
                        "sort_order": g_var.sort_order,
                        "metadata": g_var.metadata,
                        "estimated_delivery_minutes": g_var.estimated_delivery_minutes,
                    }
                )
                if v_created:
                    stats["variants_created"] += 1
                else:
                    # Update prices and cost upon re-sync
                    store_var.cost = g_var.cost
                    if cust_m > 0 or deal_m > 0 or vip_m > 0:
                        store_var.price = var_price
                        store_var.wholesale_price = var_wholesale
                        store_var.vip_price = var_vip
                    store_var.save(update_fields=["cost", "price", "wholesale_price", "vip_price"])
                    stats["variants_updated"] += 1

    logger.info(f"Imported Raqamiyat products for store '{store.name}' ({store.subdomain}): {stats}")
    return stats
