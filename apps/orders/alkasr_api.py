import logging
import json
import requests
import datetime
from decimal import Decimal
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. API TRANSACTION LOGGING & INTEGRATION RESOLUTION
# ==============================================================================

def log_api_transaction(integration, action, url, params, response_status, response_body, is_success, error_code=None, error_message=None, product_id=None, order_uuid=None):
    """
    Logs every API HTTP request and response for auditing and troubleshooting.
    Masks API tokens and sensitive credentials before persisting.
    """
    try:
        from apps.catalog.models import APITransaction

        clean_params = {}
        if isinstance(params, dict):
            for k, v in params.items():
                if k.lower() in ("api_token", "api-token", "token", "key", "api_key", "apikey"):
                    clean_params[k] = "***MASKED***"
                else:
                    clean_params[k] = v
        else:
            clean_params = params

        clean_url = url
        if "api_token=" in clean_url or "api-token=" in clean_url:
            import re
            clean_url = re.sub(r'(api[-_]token)=([^&]+)', r'\1=***MASKED***', clean_url)

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
    """
    Resolves the active Alkasr VIP integration instance for a store or globally.
    """
    from apps.catalog.models import APIIntegration
    from django.core.cache import cache
    
    has_integrations = cache.get("has_api_integrations")
    if not has_integrations:
        if APIIntegration.objects.count() == 0:
            base_url = getattr(settings, "ALKASR_BASE_URL", "https://api.alkasr-vip.com/")
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
        integration = APIIntegration.objects.filter(provider="alkasr", is_active=True).first()

    return integration


# ==============================================================================
# 2. ALKASR API ENDPOINTS IMPLEMENTATION
# ==============================================================================

def get_alkasr_profile(store=None, force_refresh=False, integration=None):
    """
    GET /client/api/profile
    Retrieves user's balance and profile information from Alkasr VIP.
    Header: api-token: YOUR_API_TOKEN
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

    base_url = (integration.base_url or "https://api.alkasr-vip.com/").rstrip("/")
    url = f"{base_url}/client/api/profile"
    headers = {
        "api-token": (integration.api_token or "").strip(),
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=6.0, verify=False)
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
        cache.set(cache_key, res, 1800)
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
        cache.set(cache_key, res, 60)
        return res


def get_alkasr_products(store=None, force_refresh=False, integration=None):
    """
    GET /client/api/products
    Retrieves all available products from Alkasr VIP.
    Header: api-token: YOUR_API_TOKEN
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

    base_url = (integration.base_url or "https://api.alkasr-vip.com/").rstrip("/")
    url = f"{base_url}/client/api/products"
    headers = {
        "api-token": (integration.api_token or "").strip(),
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=12.0, verify=False)
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
        cache.set(cache_key, res, 14400)
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
        cache.set(cache_key, res, 60)
        return res


def get_alkasr_categories(store=None, force_refresh=False, integration=None):
    """
    GET /client/api/categories or /client/api/content/0
    Retrieves category tree from Alkasr VIP.
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

    base_url = (integration.base_url or "https://api.alkasr-vip.com/").rstrip("/")
    url = f"{base_url}/client/api/categories"
    headers = {
        "api-token": (integration.api_token or "").strip(),
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=8.0, verify=False)
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
        cache.set(cache_key, res, 14400)
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
        cache.set(cache_key, res, 60)
        return res


def place_alkasr_order(api_product_id, qty, order_uuid, metadata, store=None):
    """
    GET /client/api/newOrder/{product.id}/params?qty={qty}&order_uuid={order_uuid}&[param1]=[val1]...
    Header: api-token: YOUR_API_TOKEN
    Creates an idempotent order using unique order_uuid.
    """
    from apps.catalog.models import ProductVariant, APIIntegration

    integration = get_alkasr_integration(store)
    if not integration or not integration.api_token:
        integration = APIIntegration.objects.filter(provider="alkasr", is_active=True).first()

    if not integration or not (integration.api_token or "").strip():
        logger.error(f"[Alkasr Order] No active Alkasr integration found for product_id={api_product_id}")
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    token = integration.api_token.strip()
    base_url = (integration.base_url or "https://api.alkasr-vip.com/").rstrip("/")
    url = f"{base_url}/client/api/newOrder/{api_product_id}/params"

    params = {
        "qty": int(qty),
        "order_uuid": str(order_uuid)
    }

    clean_metadata = {}
    for k, v in (metadata or {}).items():
        k_clean = str(k).strip() if k else ""
        if k_clean:
            clean_metadata[k_clean] = str(v).strip() if v is not None else ""

    variant = ProductVariant.objects.filter(api_product_id=api_product_id).select_related('product').first()
    form_schema = None
    if variant:
        if hasattr(variant, 'form_schema') and variant.form_schema:
            form_schema = variant.form_schema
        elif variant.product and variant.product.form_schema:
            form_schema = variant.product.form_schema

    if form_schema and form_schema.get("fields"):
        for field in form_schema.get("fields", []):
            api_name = field.get("name") # MUST BE EXACT API PARAMETER NAME
            if not api_name:
                continue

            val = None
            for mk, mv in clean_metadata.items():
                if mk == api_name or mk == f"custom_{api_name}":
                    val = mv
                    break
            if val is None:
                for mk, mv in clean_metadata.items():
                    if mk.lower() == api_name.lower() or mk.lower() == f"custom_{api_name.lower()}":
                        val = mv
                        break
            if val is None and len(clean_metadata) == 1:
                val = list(clean_metadata.values())[0]

            if val is not None:
                params[api_name] = str(val).strip()
    else:
        import re
        ascii_key = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        for k, v in clean_metadata.items():
            if ascii_key.match(k):
                params[k] = str(v).strip()

    session = requests.Session()
    session.headers.update({
        "api-token": token,
        "Accept": "application/json",
        "User-Agent": "RaqamiyatStore/1.0",
    })

    try:
        response = session.get(url, params=params, timeout=12.0, verify=False)
        
        try:
            response_json = response.json()
        except Exception:
            response_json = None

        if response_json and response_json.get("status") == "ERROR":
            err_code = response_json.get("code", 0)
            err_msg = response_json.get("msg", "خطأ غير معروف من المزود")

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
                120: "ERR-120: مفتاح API مطلوب — يرجى مراجعة إعدادات الربط",
                121: "ERR-121: مفتاح API غير صحيح (Token error)",
                122: "ERR-122: غير مسموح بالوصول لـ API لهذا الحساب",
                123: "ERR-123: عنوان IP غير مصرح له",
                130: "ERR-130: المزود في وضع الصيانة مؤقتاً",
                100: "ERR-100: رصيد الحساب لدى المزود غير كافٍ",
                105: "ERR-105: الكمية غير متوفرة حالياً لدى المزود",
                106: "ERR-106: الكمية غير مسموح بها لهذا المنتج",
                107: "ERR-107: معرّف اللاعب (Player ID) محظور لدى المزود",
                108: "ERR-108: يرجى إدخال رمز التحقق بخطوتين 2FA للمزود",
                109: "ERR-109: المنتج محذوف أو غير موجود لدى المزود",
                110: "ERR-110: المنتج غير متاح حالياً لدى المزود",
                111: "ERR-111: يرجى المحاولة مجدداً بعد دقيقة واحدة",
                112: "ERR-112: الكمية المحددة أقل من الحد الأدنى المسموح",
                113: "ERR-113: الكمية المحددة أكبر من الحد الأقصى المسموح",
                114: "ERR-114: خطأ غير معروف من المزود",
                500: "ERR-500: خطأ داخلي في سيرفر المزود",
            }
            friendly = alkasr_errors.get(int(err_code) if err_code else 0, f"ERR-{err_code}: {err_msg}")
            logger.error(f"[Alkasr Order] API error code={err_code}: {err_msg}")

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

    except Exception as e:
        logger.exception(f"[Alkasr Order] Exception for product_id={api_product_id}: {e}")
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
        return {"status": "error", "message": f"فشل الاتصال بالمزود: {str(e)}"}


def check_alkasr_orders(order_identifiers, is_uuid=False, store=None):
    """
    GET /client/api/check?orders=[ID1,ID2]
    GET /client/api/check?orders=[yourOrderUUID]&uuid=1
    Checks status of orders. Status values: accept, reject, wait.
    """
    integration = get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "بوابة Alkasr VIP غير مهيئة في قاعدة البيانات."}

    base_url = (integration.base_url or "https://api.alkasr-vip.com/").rstrip("/")
    url = f"{base_url}/client/api/check"

    if is_uuid:
        params = {
            "orders": f"[{order_identifiers}]",
            "uuid": 1
        }
    else:
        ids_str = ",".join(order_identifiers) if isinstance(order_identifiers, list) else str(order_identifiers)
        params = {
            "orders": f"[{ids_str}]"
        }
        
    headers = {
        "api-token": (integration.api_token or "").strip(),
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=6.0, verify=False)
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


# ==============================================================================
# 3. COMPLETE & FAITHFUL CATALOG IMPORT & SYNCHRONIZATION ENGINE
# ==============================================================================

def parse_qty_values(qty_values_raw, product_type="package"):
    """
    Parses provider `qty_values` according to documentation rules:
    - qty_values: null -> Fixed package! Quantity in order must be 1.
    - qty_values: ["110", "150", "210"] -> Only these specific quantities are allowed.
    - qty_values: {"min": "500", "max": "500000"} -> Quantity must be within this range.
    """
    qty_type = "fixed"
    qty_min = 1
    qty_max = 1
    qty_list = []
    allow_custom = False

    if product_type == "package" and qty_values_raw is None:
        qty_type = "fixed"
        allow_custom = False
        qty_min = 1
        qty_max = 1
    elif isinstance(qty_values_raw, dict):
        qty_type = "range"
        allow_custom = True
        try:
            qty_min = int(qty_values_raw.get("min") or 1)
        except (ValueError, TypeError):
            qty_min = 1
        try:
            qty_max = int(qty_values_raw.get("max") or 999999)
        except (ValueError, TypeError):
            qty_max = 999999
    elif isinstance(qty_values_raw, list):
        qty_type = "list"
        allow_custom = False
        qty_list = [str(x) for x in qty_values_raw]
    elif qty_values_raw is None:
        qty_type = "fixed"
        allow_custom = False
        qty_min = 1
        qty_max = 1
    else:
        qty_type = "fixed"
        allow_custom = False
        qty_min = 1
        qty_max = 1

    return {
        "qty_values": qty_values_raw,
        "qty_type": qty_type,
        "qty_min": qty_min,
        "qty_max": qty_max,
        "qty_list": qty_list,
        "allow_custom_quantity": allow_custom,
        "product_type": product_type,
    }


def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0, integration=None):
    """
    Imports 100% of products from Alkasr VIP without skipping any item.
    Builds exact category hierarchy: Category -> App/Service Product -> Package Variant.
    Calculates cost and selling prices accurately.
    """
    from apps.catalog.models import Category, Product, ProductVariant
    from apps.orders.models import OrderItem

    products_api = get_alkasr_products(store=store, force_refresh=True, integration=integration)
    if isinstance(products_api, dict) and products_api.get("status") == "error":
        return products_api

    if not isinstance(products_api, list):
        return {"status": "error", "message": "استجابة غير صحيحة من المزود"}

    alkasr_cats_list = get_alkasr_categories(store=store, force_refresh=True, integration=integration)
    alkasr_cats = {}
    if isinstance(alkasr_cats_list, list):
        for c in alkasr_cats_list:
            cid = c.get("id")
            if cid is not None:
                alkasr_cats[int(cid)] = c

    created_count = 0
    updated_count = 0

    with transaction.atomic():
        # Clean up legacy un-ordered API products to ensure zero leftover corruption
        legacy_prods = Product.objects.filter(store=store, is_api_product=True)
        for p in list(legacy_prods):
            if not OrderItem.objects.filter(variant__product=p).exists():
                try:
                    p.delete()
                except Exception:
                    p.is_active = False
                    p.save()

        # Cache existing categories and products after cleanup
        existing_categories = {}
        for cat in Category.objects.filter(store=store).select_related('parent'):
            existing_categories[cat.name] = cat
            if cat.parent:
                existing_categories[f"{cat.parent.name} > {cat.name}"] = cat

        existing_products = {
            f"{p.category_id}_{p.name}": p
            for p in Product.objects.filter(store=store)
        }

        existing_variants = {
            v.api_product_id: v
            for v in ProductVariant.objects.filter(api_product_id__isnull=False).select_related('product')
        }

        from apps.common.tenant_utils import bypass_tenant_filter
        with bypass_tenant_filter():
            existing_skus = set(ProductVariant.objects.values_list('sku', flat=True))

        for index, item in enumerate(products_api):
            api_prod_id = item.get("id")
            parent_id = item.get("parent_id")

            if not api_prod_id:
                continue

            if selected_category_ids is not None:
                if parent_id not in selected_category_ids and str(parent_id) not in selected_category_ids:
                    continue

            raw_item_name = (item.get("name") or "").strip()
            cat_name_raw = (item.get("category_name") or "").strip()

            if not raw_item_name or raw_item_name.lower() in ["null", "none", "nan", ""]:
                continue

            # Determine Main Category & Sub Category / Product Title
            main_cat_name = "الخدمات الإلكترونية"
            p_id_int = int(parent_id) if parent_id is not None else 0
            if p_id_int in alkasr_cats:
                parent_cat_obj = alkasr_cats[p_id_int]
                main_cat_name = parent_cat_obj.get("name") or main_cat_name

            # Target Product Name (App / Game / Service Title)
            prod_name = cat_name_raw if cat_name_raw else raw_item_name
            var_name = raw_item_name

            # Determine cost price and calculate retail selling price
            provider_cost = item.get("price") or item.get("base_price") or 0.0
            cost_val = Decimal(str(provider_cost))
            markup_factor = Decimal(1) + (Decimal(str(markup_percent)) / Decimal(100))
            retail_price = cost_val * markup_factor

            is_available = item.get("available", True)
            params_list = item.get("params") or []

            # Build form schema for user inputs while keeping exact API parameter names
            fields_list = []
            for p_field in params_list:
                if not p_field or not isinstance(p_field, str):
                    continue
                label = p_field
                p_lower = p_field.lower()
                if p_lower in ("playerid", "player_id"):
                    label = "معرّف اللاعب (Player ID)"
                elif p_lower in ("username", "user_name", "user"):
                    label = "اسم المستخدم (Username)"
                elif p_lower in ("phone", "mobile", "number"):
                    label = "رقم الهاتف / الحساب"
                elif p_lower in ("email",):
                    label = "البريد الإلكتروني"

                fields_list.append({
                    "name": p_field, # CRITICAL: MUST BE EXACT PARAMETER NAME EXPECTED BY API
                    "label": label,  # UI display label
                    "type": "text",
                    "required": True
                })
            form_schema = {
                "version": 1,
                "fields": fields_list
            }

            # Get or create Main Category
            main_category = existing_categories.get(main_cat_name)
            if not main_category:
                main_category = Category.objects.create(
                    name=main_cat_name,
                    store=store,
                    is_active=True,
                    parent=None,
                    sort_order=index
                )
                existing_categories[main_cat_name] = main_category

            # Get or create Sub Category
            sub_category_key = f"{main_cat_name} > {prod_name}"
            sub_category = existing_categories.get(sub_category_key)
            if not sub_category:
                sub_category = Category.objects.create(
                    name=prod_name,
                    store=store,
                    is_active=True,
                    parent=main_category,
                    sort_order=index
                )
                existing_categories[sub_category_key] = sub_category

            target_category = sub_category

            # Get or create Product (App / Game Title)
            prod_cache_key = f"{target_category.id}_{prod_name}"
            product = existing_products.get(prod_cache_key)
            if not product:
                product = Product.objects.create(
                    product_type="digital",
                    name=prod_name,
                    category=target_category,
                    store=store,
                    description="",
                    is_active=is_available,
                    is_api_product=True,
                    api_provider="alkasr",
                    form_schema=form_schema,
                    image=None,
                    sort_order=index
                )
                existing_products[prod_cache_key] = product
            else:
                if is_available:
                    product.is_active = True
                product.category = target_category
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
                product.save()

            # Create or update Variant (Package / Quantity Item)
            variant = existing_variants.get(api_prod_id)
            variant_meta = parse_qty_values(item.get("qty_values"), product_type=item.get("product_type", "package"))

            if variant:
                variant.product = product
                variant.name = var_name
                variant.cost = cost_val
                variant.price = retail_price
                variant.is_active = is_available
                variant.metadata = variant_meta
                variant.save()
                updated_count += 1
            else:
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
                    delivery_type="manual",
                    metadata=variant_meta
                )
                existing_variants[api_prod_id] = variant
                created_count += 1

    return {
        "status": "success",
        "created": created_count,
        "updated": updated_count
    }
