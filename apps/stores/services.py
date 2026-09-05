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
                store_var, v_created = ProductVariant.objects.get_or_create(
                    product=store_prod,
                    name=g_var.name,
                    defaults={
                        "sku": var_sku,
                        "price": g_var.price,
                        "cost": g_var.cost,
                        "wholesale_price": g_var.wholesale_price,
                        "vip_price": g_var.vip_price,
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
                    stats["variants_updated"] += 1

    logger.info(f"Imported Raqamiyat products for store '{store.name}' ({store.subdomain}): {stats}")
    return stats
