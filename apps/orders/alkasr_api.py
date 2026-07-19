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
        integration = APIIntegration.objects.filter(store=store, provider="alkasr", is_active=True).first()
    if not integration:
        integration = APIIntegration.objects.filter(store__isnull=True, provider="alkasr", is_active=True).first()
    return integration

def get_alkasr_profile(store=None, force_refresh=False):
    """
    Fetches Alkasr profile information (balance and email).
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    cache_key = f"alkasr_profile_{store.id if store else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    integration = get_alkasr_integration(store)
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
    integration = get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    url = f"{integration.base_url.rstrip('/')}/client/api/newOrder/{api_product_id}/params"
    
    # Base query parameters required by the API
    params = {
        "qty": qty,
        "order_uuid": str(order_uuid)
    }
    
    # Map metadata custom fields directly
    for k, v in metadata.items():
        params[k] = v
        
    # Check if we have playerId in parameters, if not try to map common aliases
    if 'playerId' not in params:
        for k, v in metadata.items():
            if any(x in k.lower() for x in ['player', 'id', 'user', 'account', 'ايدي', 'لاعب', 'حساب']):
                params['playerId'] = v
                break
                
    # Fallback to the first value if playerId is still not found but metadata is not empty
    if 'playerId' not in params and metadata:
        params['playerId'] = list(metadata.values())[0]
        
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

def get_alkasr_products(store=None, force_refresh=False):
    """
    Fetches the entire products list from Alkasr API.
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    cache_key = f"alkasr_products_{store.id if store else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    integration = get_alkasr_integration(store)
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

def get_alkasr_categories(store=None, force_refresh=False):
    """
    Fetches categories from Alkasr API.
    Caches the results to prevent site slowdown.
    """
    from django.core.cache import cache
    cache_key = f"alkasr_categories_{store.id if store else 'global'}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    integration = get_alkasr_integration(store)
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

def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0):
    """
    Fetches the catalog from Alkasr and synchronizes it with the local catalog.
    Only syncs products belonging to categories in selected_category_ids (list of ints).
    Adds a percentage markup_percent to the retail price.
    Also ensures images are completely cleared out as requested.
    """
    from decimal import Decimal
    from apps.catalog.models import Category, Product, ProductVariant
    
    # Fetch products (force refresh during sync)
    products = get_alkasr_products(store=store, force_refresh=True)
    if isinstance(products, dict) and products.get("status") == "error":
        return products
        
    if not isinstance(products, list):
        return {"status": "error", "message": "Invalid response from Alkasr API"}
        
    created_count = 0
    updated_count = 0
    
    # Pre-fetch existing variants with api_product_id to avoid N+1 queries
    existing_variants = {
        v.api_product_id: v 
        for v in ProductVariant.objects.filter(api_product_id__isnull=False).select_related('product')
    }
    
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
        "playerid": "معرّف اللاعب (Player ID)",
    }
    
    for item in products:
        api_prod_id = item.get("id")
        parent_id = item.get("parent_id")
        
        if not api_prod_id:
            continue
            
        # If category list is specified, filter by it
        if selected_category_ids is not None:
            if parent_id not in selected_category_ids and str(parent_id) not in selected_category_ids:
                continue
                
        cat_name = item.get("category_name") or "غير مصنف"
        prod_name = item.get("name")
        alkasr_price = item.get("price") or 0.0
        is_available = item.get("available", True)
        params_list = item.get("params") or []
        
        # Build form schema
        fields_list = []
        for p_field in params_list:
            norm_field = p_field.strip().lower()
            label = translation_map.get(norm_field, p_field)
            if p_field in translation_map:
                label = translation_map[p_field]
            elif p_field.lower() == "playerid":
                label = "معرّف اللاعب (Player ID)"
                
            fields_list.append({
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
        
        # Check if we already have a variant for this api_prod_id
        variant = existing_variants.get(api_prod_id)
        if variant:
            product = variant.product
            # Ensure the category is fetched/created and assigned to the product
            category, cat_created = Category.objects.get_or_create(
                name=cat_name,
                store=store,
                defaults={"is_active": True}
            )
            
            # Update product details
            product.name = prod_name
            product.category = category
            product.is_active = is_available
            product.form_schema = form_schema
            product.api_provider = "alkasr"
            # Do NOT overwrite product.image with None if it is already set (this prevents resetting user's custom images)
            if not product.image:
                product.image = None
            product.save()
            
            # Update variant details
            variant.cost = cost_val
            variant.price = retail_price
            variant.is_active = is_available
            variant.save()
            
            updated_count += 1
        else:
            # Create category if it doesn't exist
            category, cat_created = Category.objects.get_or_create(
                name=cat_name,
                store=store,
                defaults={"is_active": True}
            )
            
            # Create product with clean/empty description and empty image
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
                image=None
            )
            
            # Create default variant
            sku_code = f"ALK-{api_prod_id}"
            suffix = 1
            while ProductVariant.objects.filter(sku=sku_code).exists():
                sku_code = f"ALK-{api_prod_id}-{suffix}"
                suffix += 1
                
            ProductVariant.objects.create(
                product=product,
                name="الافتراضية",
                sku=sku_code,
                price=retail_price,
                cost=cost_val,
                api_product_id=api_prod_id,
                is_active=is_available,
                delivery_type="manual"
            )
            created_count += 1
            
    return {
        "status": "success",
        "created": created_count,
        "updated": updated_count
    }
