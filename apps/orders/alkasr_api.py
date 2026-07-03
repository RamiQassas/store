import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def get_alkasr_profile():
    """
    Fetches Alkasr profile information (balance and email).
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/profile"
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to fetch Alkasr profile")
        return {"status": "error", "message": str(e)}

def place_alkasr_order(api_product_id, qty, order_uuid, metadata):
    """
    Sends a request to create a new order in Alkasr.
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/newOrder/{api_product_id}/params"
    
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
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    
    try:
        logger.info(f"Sending order to Alkasr: product_id={api_product_id}, qty={qty}, uuid={order_uuid}, params={params}")
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        logger.info(f"Alkasr order response: {response_json}")
        return response_json
    except Exception as e:
        logger.exception("Failed to place Alkasr order")
        return {"status": "error", "message": str(e)}

def check_alkasr_orders(order_identifiers, is_uuid=False):
    """
    Checks the status of one or multiple orders on Alkasr.
    order_identifiers can be a list of order IDs (e.g. ['ID_a37aaa06']) or a single UUID string.
    """
    if is_uuid:
        # Check by order UUID
        url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/check"
        params = {
            "orders": f"[{order_identifiers}]",
            "uuid": 1
        }
    else:
        # Check by order IDs
        url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/check"
        ids_str = ",".join(order_identifiers)
        params = {
            "orders": f"[{ids_str}]"
        }
        
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to check Alkasr order status")
        return {"status": "error", "message": str(e)}

def get_alkasr_products():
    """
    Fetches the entire products list from Alkasr API.
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/products"
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to fetch Alkasr products")
        return {"status": "error", "message": str(e)}

def get_alkasr_categories():
    """
    Fetches categories from Alkasr API.
    """
    url = f"{settings.ALKASR_BASE_URL.rstrip('/')}/client/api/categories"
    headers = {
        "api-token": settings.ALKASR_API_TOKEN,
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Failed to fetch Alkasr categories")
        return {"status": "error", "message": str(e)}

def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0):
    """
    Fetches the catalog from Alkasr and synchronizes it with the local catalog.
    Only syncs products belonging to categories in selected_category_ids (list of ints).
    Adds a percentage markup_percent to the retail price.
    """
    from decimal import Decimal
    from apps.catalog.models import Category, Product, ProductVariant
    
    # Fetch products
    products = get_alkasr_products()
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
            fields_list.append({
                "label": p_field,
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
            # Update product details
            product.name = prod_name
            product.is_active = is_available
            product.form_schema = form_schema
            product.save()
            
            # Update variant details
            variant.cost = cost_val
            variant.price = retail_price
            variant.is_active = is_available
            variant.save()
            
            updated_count += 1
        else:
            # Create category if it doesn't exist
            category, _ = Category.objects.get_or_create(
                name=cat_name,
                store=store,
                defaults={"is_active": True}
            )
            
            # Create product
            product = Product.objects.create(
                product_type="digital",
                name=prod_name,
                category=category,
                store=store,
                description=f"منتج مستورد تلقائياً من Alkasr API (ID: {api_prod_id})",
                is_active=is_available,
                is_api_product=True,
                form_schema=form_schema
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

