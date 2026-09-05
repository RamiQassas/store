import logging
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.tenant_utils import bypass_tenant_filter

logger = logging.getLogger(__name__)

from decimal import Decimal

def deduplicate_store_catalog(store=None):
    """
    Cleans up duplicate categories, products, and variants for a store
    (or global catalog if store=None).
    """
    with bypass_tenant_filter():
        cats_deleted = 0
        prods_deleted = 0
        vars_deleted = 0

        # 1. Deduplicate Categories
        if store:
            cats = list(Category.all_objects.filter(store=store).order_by("created_at"))
        else:
            cats = list(Category.all_objects.filter(store__isnull=True).order_by("created_at"))

        cat_groups = {}
        for c in cats:
            key = (c.name or "").strip().lower()
            if key:
                cat_groups.setdefault(key, []).append(c)

        for name_key, group in cat_groups.items():
            if len(group) <= 1:
                continue
            # Pick canonical: prefer one that has products, then earliest created
            def cat_score(cat):
                p_count = Product.all_objects.filter(category=cat).count()
                ts = cat.created_at.timestamp() if cat.created_at else 0
                return (p_count, -ts)

            group.sort(key=cat_score, reverse=True)
            canonical = group[0]
            duplicates = group[1:]

            for dup in duplicates:
                Product.all_objects.filter(category=dup).update(category=canonical)
                Category.all_objects.filter(parent=dup).update(parent=canonical)
                dup.delete()
                cats_deleted += 1

        # 2. Deduplicate Products
        if store:
            prods = list(Product.all_objects.filter(store=store).prefetch_related("variants").order_by("created_at"))
        else:
            prods = list(Product.all_objects.filter(store__isnull=True).prefetch_related("variants").order_by("created_at"))

        prod_groups = {}
        for p in prods:
            key = (p.name or "").strip().lower()
            if key:
                prod_groups.setdefault(key, []).append(p)

        from apps.orders.models import OrderItem
        for name_key, group in prod_groups.items():
            if len(group) <= 1:
                continue
            # Pick canonical: prefer one with most variants, then earliest created
            def prod_score(prod):
                v_count = prod.variants.count()
                ts = prod.created_at.timestamp() if prod.created_at else 0
                return (v_count, -ts)

            group.sort(key=prod_score, reverse=True)
            canonical = group[0]
            duplicates = group[1:]

            for dup in duplicates:
                for d_var in dup.variants.all():
                    c_var = canonical.variants.filter(name=d_var.name).first()
                    if c_var:
                        OrderItem.objects.filter(variant=d_var).update(variant=c_var)
                        d_var.delete()
                    else:
                        d_var.product = canonical
                        d_var.save(update_fields=["product"])
                dup.delete()
                prods_deleted += 1

        # 3. Deduplicate Variants within each product
        if store:
            curr_prods = Product.all_objects.filter(store=store).prefetch_related("variants")
        else:
            curr_prods = Product.all_objects.filter(store__isnull=True).prefetch_related("variants")

        for p in curr_prods:
            v_groups = {}
            for v in p.variants.all():
                key = (v.name or "").strip().lower()
                if key:
                    v_groups.setdefault(key, []).append(v)
            for v_key, v_list in v_groups.items():
                if len(v_list) <= 1:
                    continue
                v_list.sort(
                    key=lambda x: (x.price > 0, -x.created_at.timestamp() if x.created_at else 0),
                    reverse=True
                )
                canon_v = v_list[0]
                for dup_v in v_list[1:]:
                    OrderItem.objects.filter(variant=dup_v).update(variant=canon_v)
                    dup_v.delete()
                    vars_deleted += 1

        logger.info(f"Deduplication completed for store={store}: {cats_deleted} cats, {prods_deleted} prods, {vars_deleted} vars deleted")
        return {"cats_deleted": cats_deleted, "prods_deleted": prods_deleted, "vars_deleted": vars_deleted}


def deduplicate_all_stores():
    """
    Cleans up duplicate categories and products across all tenant stores
    and the global catalog.
    """
    from apps.stores.models import Store
    with bypass_tenant_filter():
        res_main = deduplicate_store_catalog(None)
        all_res = {"main": res_main, "stores": {}}
        for s in Store.objects.all():
            all_res["stores"][s.subdomain] = deduplicate_store_catalog(s)
        return all_res


def import_raqamiyat_products_for_store(store):
    """
    Imports and synchronizes all active global Raqamiyat categories, products,
    and variants into a specific tenant store with full tenant isolation.
    Guarantees no duplicate categories or products are created.
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
        # First clean any existing duplicates in this store
        deduplicate_store_catalog(store)

        # 1. Map and clone global categories to the store
        global_categories = Category.all_objects.filter(store__isnull=True, is_active=True).order_by("sort_order", "name")
        cat_mapping = {}  # global_cat_id -> store_cat

        for g_cat in global_categories:
            store_cat = Category.all_objects.filter(store=store, name=g_cat.name).first()
            if not store_cat:
                store_cat = Category.all_objects.create(
                    store=store,
                    name=g_cat.name,
                    image=g_cat.image,
                    is_active=g_cat.is_active,
                    is_featured=g_cat.is_featured,
                    sort_order=g_cat.sort_order,
                )
                stats["categories_created"] += 1
            else:
                store_cat.image = g_cat.image
                store_cat.is_active = g_cat.is_active
                store_cat.is_featured = g_cat.is_featured
                store_cat.sort_order = g_cat.sort_order
                store_cat.save(update_fields=["image", "is_active", "is_featured", "sort_order"])
                stats["categories_updated"] += 1

            cat_mapping[g_cat.id] = store_cat

        # Extract tier margins if configured by store owner
        tier_margins = getattr(store, "tier_margins", {}) or {}
        try:
            cust_m = Decimal(str(tier_margins.get("customer", 0) or 0))
        except Exception:
            cust_m = Decimal("0")
        try:
            deal_m = Decimal(str(tier_margins.get("dealer", 0) or 0))
        except Exception:
            deal_m = Decimal("0")
        try:
            vip_m = Decimal(str(tier_margins.get("vip", 0) or 0))
        except Exception:
            vip_m = Decimal("0")

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
                # Update category and active state
                store_prod.category = target_cat
                store_prod.is_active = g_prod.is_active
                store_prod.is_out_of_stock = g_prod.is_out_of_stock
                store_prod.save(update_fields=["category", "is_active", "is_out_of_stock"])
                stats["products_updated"] += 1

            # 3. Clone / sync variants
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

                store_var = store_prod.variants.filter(name=g_var.name).first()
                if not store_var:
                    store_var = ProductVariant.objects.create(
                        product=store_prod,
                        name=g_var.name,
                        sku=var_sku,
                        price=var_price,
                        cost=g_var.cost,
                        wholesale_price=var_wholesale,
                        vip_price=var_vip,
                        is_active=g_var.is_active,
                        is_temporarily_disabled=g_var.is_temporarily_disabled,
                        is_sale=g_var.is_sale,
                        discount_percent=g_var.discount_percent,
                        delivery_type=g_var.delivery_type,
                        is_recharge_card=g_var.is_recharge_card,
                        recharge_amount=g_var.recharge_amount,
                        recharge_currency=g_var.recharge_currency,
                        api_product_id=g_var.api_product_id,
                        sort_order=g_var.sort_order,
                        metadata=g_var.metadata,
                        estimated_delivery_minutes=g_var.estimated_delivery_minutes,
                    )
                    stats["variants_created"] += 1
                else:
                    store_var.cost = g_var.cost
                    store_var.is_active = g_var.is_active
                    store_var.is_temporarily_disabled = g_var.is_temporarily_disabled
                    store_var.api_product_id = g_var.api_product_id
                    if cust_m > 0 or deal_m > 0 or vip_m > 0:
                        store_var.price = var_price
                        store_var.wholesale_price = var_wholesale
                        store_var.vip_price = var_vip
                    store_var.save(update_fields=["cost", "is_active", "is_temporarily_disabled", "api_product_id", "price", "wholesale_price", "vip_price"])
                    stats["variants_updated"] += 1

    logger.info(f"Imported Raqamiyat products for store '{store.name}' ({store.subdomain}): {stats}")
    return stats
