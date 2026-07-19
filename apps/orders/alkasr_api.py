import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def log_api_transaction(integration, action, url, params, response_status, response_body, is_success, error_code=None, error_message=None, product_id=None, order_uuid=None):
    try:
        from apps.catalog.models import APITransaction
        import json

        # Clean/mask tokens in params
        clean_params = {}
        if isinstance(params, dict):
            for k, v in params.items():
                if k.lower() in ("api_token", "api-token", "token", "key", "api_key", "apikey"):
                    clean_params[k] = "***MASKED***"
                else:
                    clean_params[k] = v
        else:
            clean_params = params

        # Mask token in URL if present
        clean_url = url
        if "api_token=" in clean_url or "api-token=" in clean_url:
            import re
            clean_url = re.sub(r'(api[-_]token)=([^&]+)', r'\1=***MASKED***', clean_url)

        # Truncate response body if it's too huge
        clean_response = response_body
        if clean_response and len(clean_response) > 50000:
            clean_response = clean_response[:50000] + "\n... [TRUNCATED]"

        APITransaction.objects.create(
            integration=integration,
            store=integration.store if integration else None,
            provider=integration.provider if integration else "alkasr",
            action=action,
            product_id=product_id,
            order_uuid=order_uuid,
            request_url=clean_url,
            request_params=json.dumps(clean_params, ensure_ascii=False) if clean_params else None,
            response_status=response_status,
            response_body=clean_response,
            is_success=is_success,
            error_code=str(error_code) if error_code is not None else None,
            error_message=error_message,
        )
    except Exception as e:
        logger.warning(f"Failed to log API transaction: {e}")

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
        # Look for an Alkasr-specific integration for this store
        integration = APIIntegration.objects.filter(store=store, provider="alkasr", is_active=True).first()
    if not integration:
        # Platform-level Alkasr integration (store=None means it applies globally)
        integration = APIIntegration.objects.filter(provider="alkasr", is_active=True).first()
    if integration:
        logger.debug(f"[Alkasr] Using integration id={integration.id} name='{integration.name}' token_len={len(integration.api_token or '')}")
    else:
        logger.warning(f"[Alkasr] No active Alkasr integration found (store={store})")
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
        log_api_transaction(
            integration=integration,
            action="profile",
            url=url,
            params=None,
            response_status=response.status_code,
            response_body=response.text,
            is_success=True
        )
        cache.set(cache_key, res, 1800) # 30 minutes cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr profile")
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        body = getattr(getattr(e, 'response', None), 'text', str(e))
        log_api_transaction(
            integration=integration,
            action="profile",
            url=url,
            params=None,
            response_status=status_code,
            response_body=body,
            is_success=False,
            error_message=str(e)
        )
        res = {"status": "error", "message": str(e)}
        cache.set(cache_key, res, 60) # cache failure for 60 seconds
        return res

def place_alkasr_order(api_product_id, qty, order_uuid, metadata, store=None):
    """
    Sends a request to create a new order in Alkasr.

    KEY DESIGN PRINCIPLE:
    - The Alkasr API uses the exact strings from its `params` field as query parameter names.
      These can be Arabic strings like "يرجى إدخال رقم الـجوال" or English like "playerId".
    - We store these exact strings as `name` in form_schema during catalog sync.
    - We ONLY send what form_schema defines. Adding any extra params (like playerId)
      that are not in the schema causes a 417 rejection from the Alkasr server.
    """
    from apps.catalog.models import Product, ProductVariant, APIIntegration

    # Fetch the integration — try multiple approaches for robustness
    integration = get_alkasr_integration(store)
    
    # If no integration found via store, try getting any active Alkasr integration on the platform
    if not integration or not integration.api_token:
        integration = APIIntegration.objects.filter(provider="alkasr", is_active=True).first()
    
    if not integration:
        logger.error(f"[Alkasr Order] No active Alkasr integration found for product_id={api_product_id}")
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    if not integration.api_token or not integration.api_token.strip():
        logger.error(f"[Alkasr Order] Integration '{integration.name}' (id={integration.id}) has EMPTY api_token!")
        return {"status": "error", "message": "مفتاح API الخاص بالمزود فارغ. يرجى مراجعة إعدادات بوابة الربط في لوحة التحكم."}



    url = f"{integration.base_url.rstrip('/')}/client/api/newOrder/{api_product_id}/params"
    
    # Base query parameters required by the API
    params = {
        "qty": qty,
        "order_uuid": str(order_uuid)
    }
    
    # Clean metadata: strip whitespace from keys and values, skip empty keys
    clean_metadata = {}
    for k, v in metadata.items():
        k_clean = str(k).strip() if k else ""
        if k_clean:
            clean_metadata[k_clean] = str(v).strip() if v is not None else ""

    # Load form_schema: try variant-level first, then product-level
    form_schema = None
    variant = ProductVariant.objects.filter(api_product_id=api_product_id).select_related('product').first()
    if variant:
        if hasattr(variant, 'form_schema') and variant.form_schema:
            form_schema = variant.form_schema
        elif variant.product and variant.product.form_schema:
            form_schema = variant.product.form_schema

    logger.info(f"[Alkasr Order] product_id={api_product_id}, metadata_keys={list(clean_metadata.keys())}, form_schema={form_schema}")

    if form_schema:
        schema_fields = form_schema.get("fields", [])
        
        for field in schema_fields:
            # `api_name` = EXACT parameter name Alkasr expects (may be Arabic or English)
            api_name = field.get("name")
            # `label` = what we showed in our UI (same as api_name for Alkasr; stored separately)
            label = field.get("label", api_name)
            
            if not api_name:
                continue
            
            val = None
            
            # Match 1: exact match on api_name (HTML form sends `custom_<api_name>`)
            for mk, mv in clean_metadata.items():
                if mk == api_name:
                    val = mv
                    break
            
            # Match 2: case-insensitive match on api_name
            if val is None:
                for mk, mv in clean_metadata.items():
                    if mk.lower() == api_name.lower():
                        val = mv
                        break
            
            # Match 3: match on label (fallback if label differs from name)
            if val is None and label and label != api_name:
                for mk, mv in clean_metadata.items():
                    if mk.lower() == label.lower():
                        val = mv
                        break
            
            # Match 4: only one metadata value available — use it
            if val is None and len(clean_metadata) == 1:
                val = list(clean_metadata.values())[0]
            
            if val is not None:
                # Send with the EXACT api_name Alkasr expects
                params[api_name] = val
                logger.info(f"[Alkasr Order] Mapped field '{api_name}' = '{val}'")
            else:
                logger.warning(f"[Alkasr Order] Could not map field '{api_name}' from metadata keys: {list(clean_metadata.keys())}")
    else:
        # No form_schema available: only pass through purely ASCII/alphanumeric keys
        # Never pass Arabic-named keys directly as URL params without schema guidance
        import re
        ascii_key = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        for k, v in clean_metadata.items():
            if ascii_key.match(k):
                params[k] = v
                logger.info(f"[Alkasr Order] No schema: passing ASCII key '{k}'")
            else:
                logger.warning(f"[Alkasr Order] No schema: skipping non-ASCII key '{k}' for product {api_product_id}")

    # Per Alkasr API docs: authentication is ONLY via the "api-token" header.
    # Use a Session to ensure the header persists through any server-side redirects.
    token = (integration.api_token or "").strip()
    if not token:
        logger.error(f"[Alkasr Order] integration id={integration.id} has EMPTY api_token!")
        return {"status": "error", "message": "مفتاح API الخاص بالمزود فارغ. يرجى مراجعة إعدادات بوابة الربط في لوحة التحكم."}

    session = requests.Session()
    session.headers.update({
        "api-token": token,
        "Accept": "application/json",
        "User-Agent": "RaqamiyatStore/1.0",
    })
    
    try:
        logger.info(f"[Alkasr Order] Sending: product_id={api_product_id} integration={integration.id} token_prefix={token[:8]}... params_keys={list(params.keys())}")
        response = session.get(url, params=params, timeout=10.0, verify=False)
        logger.info(f"[Alkasr Order] HTTP {response.status_code} - Body: {response.text[:400]}")
        
        # Alkasr returns HTTP 417 for ANY API-level error (missing token, bad params, etc.)
        # Always parse the JSON body first to get the real error
        try:
            response_json = response.json()
        except Exception:
            response_json = None
        
        if response_json and response_json.get("status") == "ERROR":
            err_code = response_json.get("code", 0)
            err_msg  = response_json.get("msg", "خطأ غير معروف من المزود")
            
            log_api_transaction(
                integration=integration,
                action="newOrder",
                url=url,
                params=params,
                response_status=response.status_code,
                response_body=response.text,
                is_success=False,
                error_code=err_code,
                error_message=err_msg,
                product_id=api_product_id,
                order_uuid=order_uuid
            )

            alkasr_errors = {
                120: "ERR-120: مفتاح API مطلوب — يرجى مراجعة إعدادات بوابة الربط",
                121: "ERR-121: مفتاح API خاطئ — يرجى التحقق من صحة الرمز في لوحة التحكم",
                122: "ERR-122: غير مسموح باستخدام API لهذا الحساب",
                123: "ERR-123: عنوان IP غير مسموح له بالوصول للمزود",
                130: "ERR-130: المزود في وضع الصيانة — يرجى المحاولة لاحقاً",
                100: "ERR-100: رصيد غير كافٍ لدى المزود",
                105: "ERR-105: الكمية المطلوبة غير متوفرة لدى المزود",
                106: "ERR-106: الكمية غير مسموح بها لهذا المنتج",
                107: "ERR-107: معرّف اللاعب محظور من قِبل المزود",
                108: "ERR-108: يتطلب التحقق بخطوتين من المزود",
                109: "ERR-109: المنتج محذوف أو غير موجود لدى المزود",
                110: "ERR-110: المنتج غير متاح حالياً — يرجى المحاولة لاحقاً",
                111: "ERR-111: يرجى المحاولة مجدداً بعد دقيقة واحدة",
                112: "ERR-112: الكمية أقل من الحد الأدنى المسموح",
                113: "ERR-113: الكمية أكبر من الحد الأقصى المسموح",
                114: "ERR-114: خطأ غير معروف من المزود",
                500: "ERR-500: خطأ داخلي في خادم المزود",
            }
            friendly = alkasr_errors.get(int(err_code) if err_code else 0, f"ERR-{err_code}: {err_msg}")
            logger.error(f"[Alkasr Order] API error code={err_code}: {err_msg}")
            # Notify admins immediately
            try:
                from apps.notifications.services import notify_provider_error
                notify_provider_error(
                    error_code=int(err_code) if err_code else 0,
                    provider_name="Alkasr VIP",
                    product_id=api_product_id,
                    detail=err_msg,
                )
            except Exception as e:
                logger.warning(f"Failed to send provider alert: {e}")
            return {"status": "error", "message": friendly}
        
        if response_json and response_json.get("status") == "OK":
            logger.info(f"[Alkasr Order] Success: {response_json}")
            log_api_transaction(
                integration=integration,
                action="newOrder",
                url=url,
                params=params,
                response_status=response.status_code,
                response_body=response.text,
                is_success=True,
                product_id=api_product_id,
                order_uuid=order_uuid
            )
            return response_json
        
        # Unexpected response
        response.raise_for_status()
        log_api_transaction(
            integration=integration,
            action="newOrder",
            url=url,
            params=params,
            response_status=response.status_code,
            response_body=response.text,
            is_success=True,
            product_id=api_product_id,
            order_uuid=order_uuid
        )
        return response_json or {"status": "error", "message": "استجابة غير متوقعة من المزود"}
        
    except requests.exceptions.HTTPError as e:
        try:
            err_body = e.response.json() if e.response else {}
            err_msg = err_body.get("msg", str(e))
        except Exception:
            err_msg = e.response.text if e.response else str(e)
        logger.error(f"[Alkasr Order] HTTP Error {getattr(e.response, 'status_code', '?')}: {err_msg}")
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        body = getattr(getattr(e, 'response', None), 'text', str(e))
        log_api_transaction(
            integration=integration,
            action="newOrder",
            url=url,
            params=params,
            response_status=status_code,
            response_body=body,
            is_success=False,
            error_message=str(e),
            product_id=api_product_id,
            order_uuid=order_uuid
        )
        return {"status": "error", "message": f"خطأ من المزود: {err_msg}"}
    except Exception as e:
        logger.exception(f"[Alkasr Order] Unexpected error: product_id={api_product_id}")
        log_api_transaction(
            integration=integration,
            action="newOrder",
            url=url,
            params=params,
            response_status=None,
            response_body=None,
            is_success=False,
            error_message=str(e),
            product_id=api_product_id,
            order_uuid=order_uuid
        )
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
        res = response.json()
        log_api_transaction(
            integration=integration,
            action="check",
            url=url,
            params=params,
            response_status=response.status_code,
            response_body=response.text,
            is_success=True,
            order_uuid=order_identifiers if is_uuid else None
        )
        return res
    except Exception as e:
        logger.exception("Failed to check Alkasr order status")
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        body = getattr(getattr(e, 'response', None), 'text', str(e))
        log_api_transaction(
            integration=integration,
            action="check",
            url=url,
            params=params,
            response_status=status_code,
            response_body=body,
            is_success=False,
            error_message=str(e),
            order_uuid=order_identifiers if is_uuid else None
        )
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
        log_api_transaction(
            integration=integration,
            action="products",
            url=url,
            params=None,
            response_status=response.status_code,
            response_body=response.text,
            is_success=True
        )
        cache.set(cache_key, res, 14400) # 4 hours cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr products")
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        body = getattr(getattr(e, 'response', None), 'text', str(e))
        log_api_transaction(
            integration=integration,
            action="products",
            url=url,
            params=None,
            response_status=status_code,
            response_body=body,
            is_success=False,
            error_message=str(e)
        )
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
        log_api_transaction(
            integration=integration,
            action="categories",
            url=url,
            params=None,
            response_status=response.status_code,
            response_body=response.text,
            is_success=True
        )
        cache.set(cache_key, res, 14400) # 4 hours cache
        return res
    except Exception as e:
        logger.exception("Failed to fetch Alkasr categories")
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        body = getattr(getattr(e, 'response', None), 'text', str(e))
        log_api_transaction(
            integration=integration,
            action="categories",
            url=url,
            params=None,
            response_status=status_code,
            response_body=body,
            is_success=False,
            error_message=str(e)
        )
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
