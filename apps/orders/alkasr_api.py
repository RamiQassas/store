import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def get_alkasr_integration(store=None):
    from apps.catalog.models import APIIntegration
    from django.core.cache import cache
    
    # Auto-seed default Alkasr VIP settings if the table is empty (cached check)
    has_integrations = cache.get("has_api_integrations")
    if not has_integrations:
        if APIIntegration.objects.count() == 0:
            base_url = getattr(settings, "ALKASR_BASE_URL", "")
            api_token = getattr(settings, "ALKASR_API_TOKEN", "")
            if base_url and api_token:
                APIIntegration.objects.get_or_create(
                    provider="alkasr",
                    defaults={
                        "name": "Alkasr VIP (Default Config)",
                        "base_url": base_url,
                        "api_token": api_token,
                        "is_active": True,
                        "allow_sub_stores": True
                    }
                )
        cache.set("has_api_integrations", True, 3600)
            
    integration = None
    if store:
        integration = APIIntegration.objects.filter(store=store, is_active=True).first()
    if not integration:
        integration = APIIntegration.objects.filter(store__isnull=True, is_active=True).first()
    return integration

def get_alkasr_profile(store=None, force_refresh=False, integration=None):
    """
    Fetches Alkasr profile information (balance and email).
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    if not integration:
        integration = get_alkasr_integration(store)
    cache_key = f"alkasr_profile_{integration.id if integration else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    if not integration:
        res = {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}
        cache.set(cache_key, res, 60)
        return res

    url = f"{integration.base_url.rstrip('/')}/client/api/profile"
    headers = {
        "api-token": integration.api_token,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=3.0, verify=False)
        response.raise_for_status()
        res = response.json()
        cache.set(cache_key, res, 1800) # 30 minutes cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr profile")
        res = {"status": "error", "message": str(e)}
        cache.set(cache_key, res, 60) # cache failure for 60 seconds
        return res

def place_alkasr_order(api_product_id, qty, order_uuid, metadata, store=None):
    """
    Sends a request to create a new order in Alkasr.
    """
    from apps.catalog.models import Product
    integration = get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    url = f"{integration.base_url.rstrip('/')}/client/api/newOrder/{api_product_id}/params"
    
    # Base query parameters required by the API
    params = {
        "qty": qty,
        "order_uuid": str(order_uuid)
    }
    
    # Clean metadata keys (remove any empty keys or keys that are spaces to avoid &= url errors)
    clean_metadata = {}
    for k, v in metadata.items():
        if k and str(k).strip():
            clean_metadata[str(k).strip()] = v

    # 1. Try to map fields using the product's form_schema to find the correct API parameter names
    product = Product.objects.filter(variants__api_product_id=api_product_id).first()
    if product and product.form_schema:
        fields = product.form_schema.get("fields", [])
        for f in fields:
            name = f.get("name") # e.g. "playerId"
            label = f.get("label") # e.g. "معرّف اللاعب (Player ID)"
            val = None
            
            # Match directly
            if name and name in clean_metadata:
                val = clean_metadata[name]
            elif label and label in clean_metadata:
                val = clean_metadata[label]
                
            # Case insensitive match
            if not val:
                for k, v in clean_metadata.items():
                    if name and k.lower() == name.lower():
                        val = v
                        break
                    if label and k.lower() == label.lower():
                        val = v
                        break
                        
            # Map name if found
            if val and name:
                params[name] = val

    # 2. Fallback direct mapping of any non-empty metadata keys has been removed
    # to prevent sending raw/Arabic parameter names (like "رابط الحساب") which Alkasr API rejects.

    # 3. Specific playerId resolution fallback (common for Alkasr)
    if 'playerId' not in params:
        # Try to find common playerId aliases in clean_metadata
        for k, v in clean_metadata.items():
            if any(x in k.lower() for x in ['player', 'id', 'user', 'account', 'ايدي', 'لاعب', 'حساب']):
                params['playerId'] = v
                break
                
    # 4. Final absolute fallback: if playerId is required but not in params, and metadata has one field, assign it!
    if 'playerId' not in params and clean_metadata:
        params['playerId'] = list(clean_metadata.values())[0]
        
    headers = {
        "api-token": integration.api_token,
        "Accept": "application/json"
    }
    
    try:
        logger.info(f"Sending order to Alkasr: product_id={api_product_id}, qty={qty}, uuid={order_uuid}, params={params}")
        response = requests.get(url, params=params, headers=headers, timeout=5.0, verify=False)
        response.raise_for_status()
        response_json = response.json()
        logger.info(f"Alkasr order response: {response_json}")
        return response_json
    except Exception as e:
        logger.exception("Failed to place Alkasr order")
        return {"status": "error", "message": str(e)}

def check_alkasr_orders(order_identifiers, is_uuid=False, store=None):
    """
    Checks the status of one or multiple orders on Alkasr.
    order_identifiers can be a list of order IDs (e.g. ['ID_a37aaa06']) or a single UUID string.
    """
    integration = get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    if is_uuid:
        # Check by order UUID
        url = f"{integration.base_url.rstrip('/')}/client/api/check"
        params = {
            "orders": f"[{order_identifiers}]",
            "uuid": 1
        }
    else:
        # Check by order IDs
        url = f"{integration.base_url.rstrip('/')}/client/api/check"
        ids_str = ",".join(order_identifiers)
        params = {
            "orders": f"[{ids_str}]"
        }
        
    headers = {
        "api-token": integration.api_token,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=4.0, verify=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to check Alkasr order status")
        return {"status": "error", "message": str(e)}

def get_alkasr_products(store=None, force_refresh=False, integration=None):
    """
    Fetches the entire products list from Alkasr API.
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    if not integration:
        integration = get_alkasr_integration(store)
    cache_key = f"alkasr_products_{integration.id if integration else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    if not integration:
        res = {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}
        cache.set(cache_key, res, 60)
        return res

    url = f"{integration.base_url.rstrip('/')}/client/api/products"
    headers = {
        "api-token": integration.api_token,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=6.0, verify=False)
        response.raise_for_status()
        res = response.json()
        cache.set(cache_key, res, 14400) # 4 hours cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr products")
        res = {"status": "error", "message": str(e)}
        cache.set(cache_key, res, 60) # cache failure for 60 seconds
        return res

def get_alkasr_categories(store=None, force_refresh=False, integration=None):
    """
    Fetches categories from Alkasr API.
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    if not integration:
        integration = get_alkasr_integration(store)
    cache_key = f"alkasr_categories_{integration.id if integration else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    if not integration:
        res = {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}
        cache.set(cache_key, res, 60)
        return res

    url = f"{integration.base_url.rstrip('/')}/client/api/categories"
    headers = {
        "api-token": integration.api_token,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=4.0, verify=False)
        response.raise_for_status()
        res = response.json()
        cache.set(cache_key, res, 14400) # 4 hours cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr categories")
        res = {"status": "error", "message": str(e)}
        cache.set(cache_key, res, 60) # cache failure for 60 seconds
        return res

def download_and_save_image(url, target_field):
    """
    Helper to download an image from a URL and save it to a FileField/ImageField.
    Disabled/Removed image download behavior as requested.
    """
    return

def parse_item_name(name, category_name=""):
    # Split by standard separators: " - ", " | ", " – ", " — "
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in name:
            parts = name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
            
    # Fallback separators (no spaces around hyphen)
    if " -" in name:
        parts = name.split(" -", 1)
        return parts[0].strip(), parts[1].strip()
    if "- " in name:
        parts = name.split("- ", 1)
        return parts[0].strip(), parts[1].strip()
        
    # If no separator found in the name:
    # Check if the name is just a package and category name is the game
    name_lower = name.lower()
    keywords = ["شدة", "جوهرة", "ماسة", "بلورة", "كارت", "بطاقة", "uc", "diamond", "gem", "coin", "point", "شحن"]
    clean_cat = category_name.strip()
    
    if any(x in name_lower for x in keywords) or any(char.isdigit() for char in name):
        # E.g. category_name="ببجي موبايل", name="60 شدة" -> prod_name="ببجي موبايل", var_name="60 شدة"
        if clean_cat and not any(clean_cat.lower() == kw.lower() for kw in ["ألعاب", "العاب", "games", "cards", "بطاقات", "غير مصنف"]):
            return clean_cat, name.strip()
            
    return name.strip(), "الافتراضية"


def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0, integration=None):
    """
    Fetches the catalog from Alkasr and synchronizes it with the local catalog.
    Only syncs products belonging to categories in selected_category_ids (list of ints).
    Adds a percentage markup_percent to the retail price.
    Also ensures images are completely cleared out as requested.
    Groups packages of the same game under a single Product as variants.
    """
    from decimal import Decimal
    from django.db import transaction
    from apps.catalog.models import Category, Product, ProductVariant
    
    # Fetch products (force refresh during sync)
    products = get_alkasr_products(store=store, force_refresh=True, integration=integration)
    if isinstance(products, dict) and products.get("status") == "error":
        return products
        
    if not isinstance(products, list):
        return {"status": "error", "message": "Invalid response from Alkasr API"}
        
    created_count = 0
    updated_count = 0
    
    # Pre-fetch existing categories for this store to avoid N+1 queries
    existing_categories = {
        cat.name: cat
        for cat in Category.objects.filter(store=store)
    }
    
    # Pre-fetch existing products for this store to avoid N+1 queries
    existing_products = {
        p.name: p
        for p in Product.objects.filter(store=store)
    }
    
    # Pre-fetch existing variants with api_product_id to avoid N+1 queries
    existing_variants = {
        v.api_product_id: v 
        for v in ProductVariant.objects.filter(api_product_id__isnull=False).select_related('product')
    }
    
    # Pre-fetch all SKUs in the database globally to optimize SKU uniqueness checks and bypass tenant filter
    from apps.common.tenant_utils import bypass_tenant_filter
    with bypass_tenant_filter():
        existing_skus = set(ProductVariant.objects.values_list('sku', flat=True))
    
    # Translation map for API parameter fields
    translation_map = {
        "playerid": "معرّف اللاعب (Player ID)",
        "player_id": "معرّف اللاعب (Player ID)",
        "id": "المعرّف (ID)",
        "username": "اسم المستخدم (Username)",
        "user_name": "اسم المستخدم (Username)",
        "user": "اسم المستخدم / الحساب",
        "phone": "رقم الهاتف",
        "number": "الرقم / المعرّف",
        "email": "البريد الإلكتروني",
        "password": "كلمة المرور",
        "pin": "الرمز السري (PIN)",
        "quantity": "الكمية",
        "qty": "الكمية",
        "amount": "المبلغ",
    }
    
    # Extract unique category order based on encounter sequence in API response
    category_order = []
    for item in products:
        cat_name = item.get("category_name") or "غير مصنف"
        if cat_name not in category_order:
            category_order.append(cat_name)

    # Wrap the entire catalog synchronization in a single transaction.atomic block
    # to execute bulk database operations extremely fast and avoid timeout/connection kills.
    with transaction.atomic():
        # First, clean description of any existing products that contain "Alkasr API" or are null/none
        Product.objects.filter(store=store, description__icontains="Alkasr API").update(description="")
        Product.objects.filter(store=store, description__in=["none", "null", "None", "Null"]).update(description="")
        
        for index, item in enumerate(products):
            api_prod_id = item.get("id")
            parent_id = item.get("parent_id")
            
            if not api_prod_id:
                continue
                
            # If category list is specified, filter by it
            if selected_category_ids is not None:
                if parent_id not in selected_category_ids and str(parent_id) not in selected_category_ids:
                    continue
                    
            cat_name = item.get("category_name") or "غير مصنف"
            raw_item_name = item.get("name") or ""
            
            # Parse grouped product name and variant/package name
            prod_name, var_name = parse_item_name(raw_item_name, cat_name)
            
            alkasr_price = item.get("price") or 0.0
            is_available = item.get("available", True)
            params_list = item.get("params") or []
            
            # Build form schema
            fields_list = []
            for p_field in params_list:
                if not p_field or not isinstance(p_field, str):
                    continue
                norm_field = p_field.strip().lower()
                label = translation_map.get(norm_field, p_field)
                if p_field in translation_map:
                    label = translation_map[p_field]
                elif p_field.lower() == "playerid":
                    label = "معرّف اللاعب (Player ID)"
                    
                fields_list.append({
                    "name": p_field,
                    "label": label,
                    "type": "text",
                    "required": True
                })
            form_schema = {
                "version": 1,
                "fields": fields_list
            }
            
            # Calculate price
            cost_val = Decimal(str(alkasr_price))
            markup_factor = Decimal(1) + (Decimal(str(markup_percent)) / Decimal(100))
            retail_price = cost_val * markup_factor
            
            # Get or create category from memory cache
            # Determine display category name: if product name is same as category name, use general category
            if prod_name.strip().lower() == cat_name.strip().lower() or cat_name.strip().lower() in [kw.lower() for kw in ["شدات ببجي", "جواهر فري فاير", "كوينز", "شحن شدات"]]:
                display_cat_name = "شحن ألعاب وبطاقات"
            else:
                display_cat_name = cat_name

            category = existing_categories.get(display_cat_name)
            if not category:
                category = Category.objects.create(
                    name=display_cat_name,
                    store=store,
                    is_active=True
                )
                existing_categories[display_cat_name] = category
            
            # Align category sort order with response encounter order
            cat_sort_order = category_order.index(cat_name)
            if category.sort_order != cat_sort_order:
                category.sort_order = cat_sort_order
                category.save(update_fields=['sort_order'])
            
            # Get or create product from memory cache (grouped by game name)
            product = existing_products.get(prod_name)
            if not product:
                product = Product.objects.create(
                    product_type="digital",
                    name=prod_name,
                    category=category,
                    store=store,
                    description="",
                    is_active=is_available,
                    is_api_product=True,
                    api_provider="alkasr",
                    form_schema=form_schema,
                    image=None,
                    sort_order=index
                )
                existing_products[prod_name] = product
            else:
                if is_available:
                    product.is_active = True
                product.category = category
                # Update schema: merge fields to make sure we don't lose any required fields of any variant
                if form_schema.get("fields"):
                    if not product.form_schema or not product.form_schema.get("fields"):
                        product.form_schema = form_schema
                    else:
                        existing_fields = list(product.form_schema.get("fields", []))
                        existing_names = {f.get("name") or f.get("label") for f in existing_fields}
                        for new_f in form_schema.get("fields", []):
                            new_name = new_f.get("name") or new_f.get("label")
                            if new_name not in existing_names:
                                existing_fields.append(new_f)
                        product.form_schema = {"version": 1, "fields": existing_fields}
                product.api_provider = "alkasr"
                
                # Clean description if it's none/null or old Alkasr API tag
                if not product.description or product.description.lower() in ["none", "null", "none.", "null."]:
                    product.description = ""
                elif "Alkasr API" in product.description:
                    product.description = ""
                    
                product.save()
            
            # Check if we already have a variant for this api_prod_id
            variant = existing_variants.get(api_prod_id)
            if variant:
                variant.product = product
                variant.name = var_name
                variant.cost = cost_val
                variant.price = retail_price
                variant.is_active = is_available
                variant.save()
                
                updated_count += 1
            else:
                # Create default variant
                store_prefix = f"-{store.subdomain.upper()}" if store and store.subdomain else ""
                sku_code = f"ALK{store_prefix}-{api_prod_id}"
                suffix = 1
                while sku_code in existing_skus:
                    sku_code = f"ALK{store_prefix}-{api_prod_id}-{suffix}"
                    suffix += 1
                existing_skus.add(sku_code)
                    
                variant = ProductVariant.objects.create(
                    product=product,
                    name=var_name,
                    sku=sku_code,
                    price=retail_price,
                    cost=cost_val,
                    api_product_id=api_prod_id,
                    is_active=is_available,
                    delivery_type="manual"
                )
                existing_variants[api_prod_id] = variant
                created_count += 1
                
    return {
        "status": "success",
        "created": created_count,
        "updated": updated_count
    }
