"""
Alkasr VIP API Integration — rebuilt from scratch per official documentation.

Base URL : https://api.alkasr-vip.com/
Auth     : Header  api-token: <YOUR_API_TOKEN>

Key concepts from the docs
===========================
product_type == "package"  → qty_values: null  → qty MUST be 1 (fixed package)
product_type == "package"  → qty_values: [...]  → only listed quantities allowed
product_type == "amount"   → qty_values: {min, max} → customer picks qty in range
                             PRICE = base_price × qty  (per-unit pricing!)

parent_id == 0  → top-level product/category item
parent_id != 0  → belongs to the category whose id == parent_id

Content API
-----------
GET /client/api/content/0              → home page products & categories (parent_id=0)
GET /client/api/content/<category.id>  → products & sub-categories for a category

Products API
------------
GET /client/api/products               → ALL products (flat list)
GET /client/api/products?products_id=1,2,3 → specific products
GET /client/api/products?base=1        → IDs + names only

Order
-----
GET /client/api/newOrder/<product.id>/params?qty=…&order_uuid=…&<params…>

Check
-----
GET /client/api/check?orders=[ID1,ID2,…]
GET /client/api/check?orders=[uuid]&uuid=1
"""

import logging
import re
import json
import uuid as _uuid
import requests
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mask_token(value: str) -> str:
    return value[:4] + "***" if value and len(value) > 4 else "***"


def _requests_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "api-token": token,
        "Accept": "application/json",
        "User-Agent": "AlkasrStore/2.0",
    })
    return s


# ==============================================================================
# 1. INTEGRATION RESOLUTION
# ==============================================================================

def get_alkasr_integration(store=None):
    """
    Returns the active APIIntegration record for Alkasr VIP.
    Falls back to a platform-wide integration if no store-specific one exists.
    Auto-creates from settings if the table is empty.
    """
    from apps.catalog.models import APIIntegration
    from django.core.cache import cache

    # Auto-create from settings if nothing exists yet
    if not cache.get("has_api_integrations"):
        if not APIIntegration.objects.exists():
            base_url = getattr(settings, "ALKASR_BASE_URL", "https://api.alkasr-vip.com/")
            api_token = getattr(settings, "ALKASR_API_TOKEN", "")
            if base_url and api_token:
                APIIntegration.objects.get_or_create(
                    provider="alkasr",
                    store=None,
                    defaults={
                        "name": "Alkasr VIP (Auto)",
                        "base_url": base_url,
                        "api_token": api_token,
                        "is_active": True,
                        "allow_sub_stores": True,
                    },
                )
        cache.set("has_api_integrations", True, 3600)

    # 1. Store-specific integration
    if store:
        itg = APIIntegration.objects.filter(store=store, provider="alkasr", is_active=True).first()
        if itg:
            return itg

    # 2. Platform-wide integration (store=None)
    return APIIntegration.objects.filter(provider="alkasr", is_active=True, store=None).first() \
        or APIIntegration.objects.filter(provider="alkasr", is_active=True).first()


# ==============================================================================
# 2. API TRANSACTION LOGGING
# ==============================================================================

def _log(integration, action, url, params, response_status, response_body,
         is_success, error_code=None, error_message=None,
         product_id=None, order_uuid=None):
    """Persist an API call record (masks tokens, truncates huge bodies)."""
    try:
        from apps.catalog.models import APITransaction

        # Mask token in params
        safe_params = {}
        if isinstance(params, dict):
            for k, v in params.items():
                if k.lower() in ("api_token", "api-token", "token", "key", "api_key", "apikey"):
                    safe_params[k] = "***"
                else:
                    safe_params[k] = v
        else:
            safe_params = params

        # Mask token in URL
        safe_url = re.sub(r'(api[-_]token)=([^&]+)', r'\1=***', url)

        # Truncate body
        body = (response_body or "")
        if len(body) > 40000:
            body = body[:40000] + "\n...[TRUNCATED]"

        APITransaction.objects.create(
            integration=integration,
            store=integration.store if integration else None,
            provider=integration.provider if integration else "alkasr",
            action=action,
            product_id=str(product_id) if product_id is not None else None,
            order_uuid=str(order_uuid) if order_uuid is not None else None,
            request_url=safe_url,
            request_params=json.dumps(safe_params, ensure_ascii=False) if safe_params else None,
            response_status=response_status,
            response_body=body,
            is_success=is_success,
            error_code=str(error_code) if error_code is not None else None,
            error_message=error_message,
        )
    except Exception as exc:
        logger.warning("Failed to log API transaction: %s", exc)


# ==============================================================================
# 3. CORE API CALLS
# ==============================================================================

def get_alkasr_profile(store=None, force_refresh=False, integration=None):
    """
    GET /client/api/profile
    Returns: {"balance": "8788.683", "email": "user@email.com"}
    """
    from django.core.cache import cache

    integration = integration or get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    cache_key = f"alkasr_profile_{integration.id}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    base = integration.base_url.rstrip("/")
    url = f"{base}/client/api/profile"
    session = _requests_session(integration.api_token.strip())

    try:
        resp = session.get(url, timeout=8, verify=False)
        resp.raise_for_status()
        data = resp.json()
        _log(integration, "profile", url, None, resp.status_code, resp.text, True)
        cache.set(cache_key, data, 1800)
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(integration, "profile", url, None,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, error_message=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(cache_key, result, 60)
        return result


def get_alkasr_products(store=None, force_refresh=False, integration=None,
                        product_ids=None, base_only=False):
    """
    GET /client/api/products
    GET /client/api/products?products_id=id1,id2,id3
    GET /client/api/products?base=1

    Returns a flat list of product dicts exactly as the API sends them.
    Each item has:
        id, name, price, params, category_name, available,
        qty_values, product_type, parent_id, base_price, category_img
    """
    from django.core.cache import cache

    integration = integration or get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    suffix = ""
    if product_ids:
        suffix = f"_ids_{'_'.join(str(i) for i in product_ids)}"
    elif base_only:
        suffix = "_base"
    cache_key = f"alkasr_products_{integration.id}{suffix}"

    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    base = integration.base_url.rstrip("/")
    url = f"{base}/client/api/products"
    params = {}
    if product_ids:
        params["products_id"] = ",".join(str(i) for i in product_ids)
    if base_only:
        params["base"] = 1

    session = _requests_session(integration.api_token.strip())
    try:
        resp = session.get(url, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise ValueError(f"Expected list, got: {type(data).__name__}")

        _log(integration, "products", resp.url, params, resp.status_code, resp.text, True)
        cache.set(cache_key, data, 14400)   # 4 hours
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(integration, "products", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, error_message=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(cache_key, result, 60)
        return result


def get_alkasr_content(category_id=0, store=None, force_refresh=False, integration=None):
    """
    GET /client/api/content/<category_id>
    Returns products and categories for the given parent category.
    Use category_id=0 for the home page (root).

    Typical response shape (from docs):
        { "products": [...], "categories": [...] }   OR   a flat list.
    We normalise to always return a dict with "products" and "categories" keys.
    """
    from django.core.cache import cache

    integration = integration or get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    cache_key = f"alkasr_content_{integration.id}_{category_id}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    base = integration.base_url.rstrip("/")
    url = f"{base}/client/api/content/{category_id}"
    session = _requests_session(integration.api_token.strip())

    try:
        resp = session.get(url, timeout=12, verify=False)
        resp.raise_for_status()
        raw = resp.json()

        # Normalise response shape
        if isinstance(raw, dict):
            result = {
                "products": raw.get("products") or [],
                "categories": raw.get("categories") or [],
            }
        elif isinstance(raw, list):
            # Some providers return a flat product list
            result = {"products": raw, "categories": []}
        else:
            result = {"products": [], "categories": []}

        _log(integration, f"content/{category_id}", url, None,
             resp.status_code, resp.text, True)
        cache.set(cache_key, result, 14400)
        return result
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(integration, f"content/{category_id}", url, None,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, error_message=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(cache_key, result, 60)
        return result


# ==============================================================================
# 4. ORDER PLACEMENT
# ==============================================================================

#: Human-readable Arabic messages for every documented error code
ALKASR_ERROR_MESSAGES = {
    120: "مفتاح API مطلوب — يرجى مراجعة إعدادات الربط (ERR-120)",
    121: "مفتاح API غير صحيح (ERR-121)",
    122: "غير مسموح بالوصول لـ API لهذا الحساب (ERR-122)",
    123: "عنوان IP غير مصرح له (ERR-123)",
    130: "المزوّد في وضع الصيانة مؤقتاً (ERR-130)",
    100: "رصيد الحساب لدى المزوّد غير كافٍ (ERR-100)",
    105: "الكمية غير متوفرة حالياً لدى المزوّد (ERR-105)",
    106: "الكمية غير مسموح بها لهذا المنتج (ERR-106)",
    107: "معرّف اللاعب (Player ID) محظور لدى المزوّد (ERR-107)",
    108: "يرجى إدخال رمز التحقق بخطوتين 2FA للمزوّد (ERR-108)",
    109: "المنتج محذوف أو غير موجود لدى المزوّد (ERR-109)",
    110: "المنتج غير متاح حالياً لدى المزوّد (ERR-110)",
    111: "يرجى المحاولة مجدداً بعد دقيقة واحدة (ERR-111)",
    112: "الكمية أقل من الحد الأدنى المسموح (ERR-112)",
    113: "الكمية أكبر من الحد الأقصى المسموح (ERR-113)",
    114: "خطأ غير معروف من المزوّد (ERR-114)",
    500: "خطأ داخلي في سيرفر المزوّد (ERR-500)",
}


def place_alkasr_order(api_product_id, qty, order_uuid, metadata, store=None, integration=None):
    """
    GET /client/api/newOrder/<product_id>/params?qty=<qty>&order_uuid=<uuid>&<params…>
    Header: api-token: <token>

    * order_uuid  — UUIDv4, idempotency key (same UUID → same order returned)
    * metadata    — dict of user-supplied param values (e.g. {"playerId": "12345"})
    * qty         — passed as-is to the API (validated by the caller)

    Returns the raw API JSON on success, or {"status": "error", "message": "..."}.
    """
    from apps.catalog.models import ProductVariant

    integration = integration or get_alkasr_integration(store)
    if not integration or not (integration.api_token or "").strip():
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    token = integration.api_token.strip()
    base = integration.base_url.rstrip("/")
    url = f"{base}/client/api/newOrder/{api_product_id}/params"

    # --- Build query params ---
    params = {
        "qty": int(qty),
        "order_uuid": str(order_uuid),
    }

    # Resolve form-field values from metadata
    variant = (
        ProductVariant.objects
        .filter(api_product_id=api_product_id)
        .select_related("product")
        .first()
    )
    schema_fields = []
    if variant:
        schema = (
            (variant.form_schema if hasattr(variant, "form_schema") and variant.form_schema else None)
            or (variant.product.form_schema if variant.product else None)
            or {}
        )
        schema_fields = schema.get("fields", []) if isinstance(schema, dict) else []

    clean_meta = {
        str(k).strip(): str(v).strip()
        for k, v in (metadata or {}).items()
        if k and v is not None
    }

    if schema_fields:
        # Map each form field by its exact API name
        for field in schema_fields:
            api_name = field.get("name")
            if not api_name:
                continue
            # Try exact match first, then case-insensitive, then single-value fallback
            val = (
                clean_meta.get(api_name)
                or clean_meta.get(f"custom_{api_name}")
                or next(
                    (v for k, v in clean_meta.items()
                     if k.lower() == api_name.lower() or k.lower() == f"custom_{api_name.lower()}"),
                    None
                )
                or (list(clean_meta.values())[0] if len(clean_meta) == 1 else None)
            )
            if val is not None:
                params[api_name] = val
    else:
        # No schema — pass all ASCII-safe keys through directly
        ascii_key = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        for k, v in clean_meta.items():
            if ascii_key.match(k):
                params[k] = v

    session = _requests_session(token)
    try:
        resp = session.get(url, params=params, timeout=15, verify=False)

        try:
            rjson = resp.json()
        except Exception:
            rjson = None

        # --- Handle provider-level errors ---
        if isinstance(rjson, dict) and rjson.get("status") == "ERROR":
            raw_code = rjson.get("code", 0)
            err_msg = rjson.get("msg") or rjson.get("message") or "خطأ غير معروف"
            try:
                code_int = int(raw_code)
            except (TypeError, ValueError):
                code_int = 0

            _log(integration, "newOrder", url, params,
                 resp.status_code, resp.text, False,
                 error_code=code_int, error_message=err_msg,
                 product_id=api_product_id, order_uuid=order_uuid)

            friendly = ALKASR_ERROR_MESSAGES.get(code_int, f"خطأ من المزوّد (ERR-{raw_code}): {err_msg}")
            logger.error("[Alkasr Order] API error code=%s msg=%s", raw_code, err_msg)

            try:
                from apps.notifications.services import notify_provider_error
                notify_provider_error(
                    error_code=code_int,
                    provider_name="Alkasr VIP",
                    product_id=api_product_id,
                    detail=err_msg,
                )
            except Exception as ne:
                logger.warning("notify_provider_error failed: %s", ne)

            return {"status": "error", "message": friendly}

        # --- Success path ---
        if isinstance(rjson, dict) and rjson.get("status") == "OK":
            _log(integration, "newOrder", url, params,
                 resp.status_code, resp.text, True,
                 product_id=api_product_id, order_uuid=order_uuid)
            return rjson

        # Unexpected response — raise for HTTP error codes
        resp.raise_for_status()
        _log(integration, "newOrder", url, params,
             resp.status_code, resp.text, False,
             error_message="Unexpected response",
             product_id=api_product_id, order_uuid=order_uuid)
        return {"status": "error", "message": "استجابة غير متوقعة من المزوّد."}

    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(integration, "newOrder", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, error_message=str(exc),
             product_id=api_product_id, order_uuid=order_uuid)
        logger.exception("[Alkasr Order] Exception for product_id=%s", api_product_id)
        return {"status": "error", "message": f"فشل الاتصال بالمزوّد: {exc}"}


# ==============================================================================
# 5. ORDER STATUS CHECK
# ==============================================================================

def check_alkasr_orders(order_identifiers, is_uuid=False, store=None, integration=None):
    """
    GET /client/api/check?orders=[ID1,ID2]
    GET /client/api/check?orders=[uuid]&uuid=1

    order_identifiers: str (single UUID) or list of order IDs
    is_uuid: True → pass &uuid=1 to the API
    """
    integration = integration or get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    base = integration.base_url.rstrip("/")
    url = f"{base}/client/api/check"

    if is_uuid:
        params = {"orders": f"[{order_identifiers}]", "uuid": 1}
    else:
        ids_str = (
            ",".join(str(i) for i in order_identifiers)
            if isinstance(order_identifiers, (list, tuple))
            else str(order_identifiers)
        )
        params = {"orders": f"[{ids_str}]"}

    session = _requests_session(integration.api_token.strip())
    try:
        resp = session.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        _log(integration, "check", url, params, resp.status_code, resp.text, True,
             order_uuid=order_identifiers if is_uuid else None)
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(integration, "check", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, error_message=str(exc),
             order_uuid=order_identifiers if is_uuid else None)
        return {"status": "error", "message": str(exc)}


# ==============================================================================
# 6. QTY_VALUES PARSER  (per official documentation)
# ==============================================================================

def parse_qty_values(qty_values_raw, product_type="package"):
    """
    Interprets the API's qty_values field exactly as documented:

    qty_values: null
        → product_type=="package": qty MUST be 1  (fixed package)
        → product_type=="amount" : treat as unlimited range (shouldn't happen per docs)

    qty_values: ["110", "150", "210"]
        → only these specific quantities are allowed  (qty_type = "list")

    qty_values: {"min": "500", "max": "500000"}
        → quantity must be within this range  (qty_type = "range")
        → for product_type=="amount" the PRICE is per-unit (price × qty)

    Returns a metadata dict stored on ProductVariant.metadata.
    """
    if qty_values_raw is None:
        # Fixed package — qty always 1
        return {
            "qty_type": "fixed",
            "qty_min": 1,
            "qty_max": 1,
            "qty_list": [],
            "allow_custom_quantity": False,
            "product_type": product_type,
        }

    if isinstance(qty_values_raw, list):
        cleaned = []
        for x in qty_values_raw:
            try:
                cleaned.append(str(int(x)))
            except (TypeError, ValueError):
                cleaned.append(str(x))
        return {
            "qty_type": "list",
            "qty_min": int(cleaned[0]) if cleaned else 1,
            "qty_max": int(cleaned[-1]) if cleaned else 1,
            "qty_list": cleaned,
            "allow_custom_quantity": False,
            "product_type": product_type,
        }

    if isinstance(qty_values_raw, dict):
        try:
            qty_min = int(qty_values_raw.get("min") or 1)
        except (TypeError, ValueError):
            qty_min = 1
        try:
            qty_max = int(qty_values_raw.get("max") or 999_999_999)
        except (TypeError, ValueError):
            qty_max = 999_999_999
        return {
            "qty_type": "range",
            "qty_min": qty_min,
            "qty_max": qty_max,
            "qty_list": [],
            "allow_custom_quantity": True,
            "product_type": product_type,
        }

    # Fallback — treat as fixed
    return {
        "qty_type": "fixed",
        "qty_min": 1,
        "qty_max": 1,
        "qty_list": [],
        "allow_custom_quantity": False,
        "product_type": product_type,
    }


def calculate_variant_price(base_price, qty_values_raw, product_type, qty, markup_percent=0.0):
    """
    Calculates the correct RETAIL price for a given quantity.

    product_type == "package":
        price = base_price × markup  (quantity is always 1 or from fixed list)

    product_type == "amount":
        price = base_price × qty × markup
        (per-unit pricing — e.g. 0.104 per UC × 100 UC = 10.4 USD)

    This function returns the per-ORDER price for the requested qty.
    """
    try:
        bp = Decimal(str(base_price))
    except InvalidOperation:
        bp = Decimal("0")

    markup = Decimal("1") + Decimal(str(markup_percent)) / Decimal("100")

    if product_type == "amount":
        # Per-unit pricing
        return (bp * Decimal(str(qty)) * markup).quantize(Decimal("0.0001"))
    else:
        # Fixed package price
        return (bp * markup).quantize(Decimal("0.0001"))


# ==============================================================================
# 7. CATALOG SYNC ENGINE
# ==============================================================================

def _build_form_schema(params_list):
    """
    Converts the API `params` array into a form_schema dict.
    The `name` field MUST match the exact API parameter name.
    """
    fields = []
    for param in (params_list or []):
        if not param or not isinstance(param, str):
            continue
        # Generate a user-friendly Arabic label
        lower = param.lower()
        if lower in ("playerid", "player_id", "player id"):
            label = "معرّف اللاعب (Player ID)"
        elif lower in ("username", "user_name", "user"):
            label = "اسم المستخدم"
        elif lower in ("phone", "mobile", "number"):
            label = "رقم الهاتف / الحساب"
        elif lower in ("email",):
            label = "البريد الإلكتروني"
        elif lower in ("zoneid", "zone_id", "zone"):
            label = "Zone ID"
        elif lower in ("serverid", "server_id", "server"):
            label = "Server ID"
        else:
            label = param

        fields.append({
            "name": param,       # CRITICAL: exact API parameter key
            "label": label,
            "type": "text",
            "required": True,
        })
    return {"version": 1, "fields": fields}


def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0, integration=None):
    """
    Synchronises the full Alkasr VIP product catalogue into the local database.

    Structure produced
    ------------------
    Category (main/parent)
      └─ Category (sub, named after category_name from product)
           └─ Product (one per unique category_name)
                └─ ProductVariant (one per API product entry)

    Pricing rules (from docs)
    -------------------------
    • product_type == "package" → variant.price = base_price × markup
      (the variant IS the package; qty is always 1 or from a fixed list)

    • product_type == "amount"  → variant stores base_price as cost/price-per-unit.
      The actual order total is calculated at checkout as:  price_per_unit × qty.
      We store the per-unit price in the variant and mark qty_type="range".

    Returns {"status": "success", "created": N, "updated": N} or error dict.
    """
    from apps.catalog.models import Category, Product, ProductVariant
    from apps.orders.models import OrderItem

    integration = integration or get_alkasr_integration(store)
    if not integration:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    # ── Fetch products ────────────────────────────────────────────────────────
    products_raw = get_alkasr_products(store=store, force_refresh=True, integration=integration)
    if isinstance(products_raw, dict) and products_raw.get("status") == "error":
        return products_raw
    if not isinstance(products_raw, list):
        return {"status": "error", "message": "استجابة غير صالحة من المزوّد."}

    # ── Fetch root content for category metadata (images etc.) ───────────────
    root_content = get_alkasr_content(0, store=store, force_refresh=True, integration=integration)
    api_categories_by_id = {}
    if isinstance(root_content, dict):
        for cat in root_content.get("categories", []):
            cid = cat.get("id")
            if cid is not None:
                api_categories_by_id[int(cid)] = cat

    created_count = 0
    updated_count = 0

    with transaction.atomic():

        # ── Delete obsolete API products (not referenced in active orders) ───
        for prod in list(Product.objects.filter(store=store, is_api_product=True)):
            if not OrderItem.objects.filter(variant__product=prod).exists():
                try:
                    prod.delete()
                except Exception:
                    prod.is_active = False
                    prod.save(update_fields=["is_active"])

        # ── Warm local caches ─────────────────────────────────────────────────
        local_categories: dict[str, "Category"] = {}
        for cat in Category.objects.filter(store=store).select_related("parent"):
            local_categories[cat.name] = cat
            if cat.parent:
                local_categories[f"{cat.parent.name}>{cat.name}"] = cat

        local_products: dict[str, "Product"] = {
            f"{p.category_id}:{p.name}": p
            for p in Product.objects.filter(store=store, is_api_product=True)
        }

        local_variants: dict[int, "ProductVariant"] = {
            v.api_product_id: v
            for v in ProductVariant.objects.filter(api_product_id__isnull=False)
                .select_related("product")
        }

        from apps.common.tenant_utils import bypass_tenant_filter
        with bypass_tenant_filter():
            existing_skus: set = set(ProductVariant.objects.values_list("sku", flat=True))

        # ── Process each API product ──────────────────────────────────────────
        for item in products_raw:
            api_id = item.get("id")
            if not api_id:
                continue

            raw_name = (item.get("name") or "").strip()
            if not raw_name or raw_name.lower() in ("null", "none", "nan"):
                continue

            cat_name = (item.get("category_name") or raw_name).strip()
            parent_id = int(item.get("parent_id") or 0)
            product_type = (item.get("product_type") or "package").lower()
            is_available = bool(item.get("available", True))
            qty_values_raw = item.get("qty_values")
            params_list = item.get("params") or []

            # Filter by selected categories if requested
            if selected_category_ids is not None:
                if parent_id not in selected_category_ids and str(parent_id) not in selected_category_ids:
                    continue

            # ── Pricing ───────────────────────────────────────────────────────
            # Use base_price for cost (wholesale), price for retail
            # For "amount" type: these are per-unit prices
            provider_price = item.get("price") or item.get("base_price") or 0
            provider_base = item.get("base_price") or item.get("price") or 0

            try:
                cost_per_unit = Decimal(str(provider_base))
            except InvalidOperation:
                cost_per_unit = Decimal("0")

            markup_factor = Decimal("1") + Decimal(str(markup_percent)) / Decimal("100")

            # For "amount" products: store the per-unit retail price
            # For "package" products: store the fixed package retail price
            try:
                api_unit_price = Decimal(str(provider_price))
            except InvalidOperation:
                api_unit_price = Decimal("0")

            retail_price_per_unit = (api_unit_price * markup_factor).quantize(Decimal("0.000001"))

            # ── Form schema ───────────────────────────────────────────────────
            form_schema = _build_form_schema(params_list)

            # ── Qty metadata ──────────────────────────────────────────────────
            qty_meta = parse_qty_values(qty_values_raw, product_type=product_type)

            # ── Resolve parent category name ───────────────────────────────
            if parent_id and parent_id in api_categories_by_id:
                main_cat_name = api_categories_by_id[parent_id].get("name") or "الخدمات الإلكترونية"
            elif parent_id:
                # Try fetching sub-content lazily
                sub_content = get_alkasr_content(parent_id, store=store, integration=integration)
                if isinstance(sub_content, dict) and not sub_content.get("status") == "error":
                    main_cat_name = f"تصنيف {parent_id}"
                else:
                    main_cat_name = "الخدمات الإلكترونية"
            else:
                main_cat_name = "الخدمات الإلكترونية"

            # ── Get or create main category ────────────────────────────────
            main_cat = local_categories.get(main_cat_name)
            if not main_cat:
                main_cat = Category.objects.create(
                    name=main_cat_name,
                    store=store,
                    is_active=True,
                    parent=None,
                )
                local_categories[main_cat_name] = main_cat

            # ── Get or create sub-category (named after category_name) ─────
            sub_key = f"{main_cat_name}>{cat_name}"
            sub_cat = local_categories.get(sub_key) or local_categories.get(cat_name)
            if not sub_cat:
                sub_cat = Category.objects.create(
                    name=cat_name,
                    store=store,
                    is_active=True,
                    parent=main_cat,
                )
                local_categories[sub_key] = sub_cat
                local_categories[cat_name] = sub_cat

            # ── Get or create Product (one per category_name under sub_cat) ─
            prod_key = f"{sub_cat.id}:{cat_name}"
            product = local_products.get(prod_key)
            if not product:
                product = Product.objects.create(
                    product_type="digital",
                    name=cat_name,
                    category=sub_cat,
                    store=store,
                    description="",
                    is_active=is_available,
                    is_api_product=True,
                    api_provider="alkasr",
                    form_schema=form_schema,
                )
                local_products[prod_key] = product
            else:
                changed = False
                if is_available and not product.is_active:
                    product.is_active = True
                    changed = True
                # Merge new form fields
                if form_schema.get("fields"):
                    existing_names = {
                        f.get("name")
                        for f in (product.form_schema or {}).get("fields", [])
                    }
                    new_fields = [
                        f for f in form_schema["fields"]
                        if f.get("name") not in existing_names
                    ]
                    if new_fields:
                        merged = list((product.form_schema or {}).get("fields", [])) + new_fields
                        product.form_schema = {"version": 1, "fields": merged}
                        changed = True
                if changed:
                    product.save()

            # ── Get or create Variant (one per API product entry) ─────────
            variant = local_variants.get(api_id)
            if variant:
                variant.product = product
                variant.name = raw_name
                variant.cost = cost_per_unit
                variant.price = retail_price_per_unit
                variant.is_active = is_available
                variant.metadata = qty_meta
                variant.save()
                updated_count += 1
            else:
                prefix = store.subdomain.upper() if (store and store.subdomain) else "GLB"
                sku = f"ALK-{prefix}-{api_id}"
                n = 1
                while sku in existing_skus:
                    sku = f"ALK-{prefix}-{api_id}-{n}"
                    n += 1
                existing_skus.add(sku)

                variant = ProductVariant.objects.create(
                    product=product,
                    name=raw_name,
                    sku=sku,
                    price=retail_price_per_unit,
                    cost=cost_per_unit,
                    api_product_id=api_id,
                    is_active=is_available,
                    delivery_type="manual",
                    metadata=qty_meta,
                )
                local_variants[api_id] = variant
                created_count += 1

    return {
        "status": "success",
        "created": created_count,
        "updated": updated_count,
    }
