"""
=============================================================================
Alkasr VIP — Complete API Integration Layer
=============================================================================

Base URL : https://api.alkasr-vip.com/
Auth     : HTTP header  →  api-token: <TOKEN>

Official qty_values rules (from docs):
  null                         → qty MUST be 1  (fixed package)
  ["110", "150", "210"]        → only these quantities are allowed
  {"min": "500","max":"500000"}→ qty must be within this range

product_type field:
  "package"  → price is FIXED per package, qty is always 1 (or from list)
  "amount"   → price is PER UNIT.  Total = unit_price × qty
               e.g. 0.104 $/UC × 100 UC = 10.40 $  (NOT 100 $)

parent_id:
  0          → top-level / root product (no parent category)
  non-zero   → belongs to the category whose id == parent_id
=============================================================================
"""

import json
import logging
import re
import uuid as _uuid_module
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(value, default=0):
    """Convert any value to int safely. Returns default on any failure."""
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "api-token": token.strip(),
        "Accept": "application/json",
        "User-Agent": "AlkasrStore/3.0",
    })
    return s


# ---------------------------------------------------------------------------
# 1.  INTEGRATION RESOLVER
# ---------------------------------------------------------------------------

def get_integration(store=None):
    """
    Returns the active APIIntegration record for Alkasr VIP.

    Priority:
      1. Store-specific integration
      2. Platform-wide integration  (store=None)
      3. Auto-create from settings if table is empty
    """
    from apps.catalog.models import APIIntegration
    from django.core.cache import cache

    if not cache.get("_alkasr_itg_exists"):
        if not APIIntegration.objects.filter(provider="alkasr").exists():
            base_url  = getattr(settings, "ALKASR_BASE_URL",  "https://api.alkasr-vip.com/")
            api_token = getattr(settings, "ALKASR_API_TOKEN", "")
            if base_url and api_token:
                APIIntegration.objects.create(
                    provider="alkasr",
                    store=None,
                    name="Alkasr VIP (auto)",
                    base_url=base_url,
                    api_token=api_token,
                    is_active=True,
                    allow_sub_stores=True,
                )
        cache.set("_alkasr_itg_exists", True, 3600)

    # 1. Store-specific
    if store:
        itg = APIIntegration.objects.filter(
            store=store, provider="alkasr", is_active=True
        ).first()
        if itg:
            return itg

    # 2. Platform-wide
    return (
        APIIntegration.objects.filter(provider="alkasr", is_active=True, store=None).first()
        or APIIntegration.objects.filter(provider="alkasr", is_active=True).first()
    )


# Keep the old name for backward compatibility
get_alkasr_integration = get_integration


# ---------------------------------------------------------------------------
# 2.  TRANSACTION LOGGING
# ---------------------------------------------------------------------------

def _log(itg, action, url, params, http_status, body, ok,
         err_code=None, err_msg=None, product_id=None, order_uuid=None):
    try:
        from apps.catalog.models import APITransaction

        safe_params = {}
        if isinstance(params, dict):
            for k, v in params.items():
                if k.lower() in ("api-token", "api_token", "token", "key", "apikey"):
                    safe_params[k] = "***"
                else:
                    safe_params[k] = v
        else:
            safe_params = params

        safe_url = re.sub(r"(api[-_]token)=([^&]+)", r"\1=***", url or "")
        safe_body = (body or "")[:40000]

        APITransaction.objects.create(
            integration=itg,
            store=itg.store if itg else None,
            provider=itg.provider if itg else "alkasr",
            action=action,
            product_id=str(product_id) if product_id is not None else None,
            order_uuid=str(order_uuid) if order_uuid is not None else None,
            request_url=safe_url,
            request_params=json.dumps(safe_params, ensure_ascii=False) if safe_params else None,
            response_status=http_status,
            response_body=safe_body,
            is_success=ok,
            error_code=str(err_code) if err_code is not None else None,
            error_message=err_msg,
        )
    except Exception as exc:
        log.warning("_log failed: %s", exc)


# ---------------------------------------------------------------------------
# 3.  PROFILE
# ---------------------------------------------------------------------------

def get_alkasr_profile(store=None, force_refresh=False, integration=None):
    """
    GET /client/api/profile
    Returns {"balance": "...", "email": "..."}
    """
    from django.core.cache import cache

    itg = integration or get_integration(store)
    if not itg:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    ck = f"alk_profile_{itg.id}"
    if not force_refresh:
        cached = cache.get(ck)
        if cached is not None:
            return cached

    url = itg.base_url.rstrip("/") + "/client/api/profile"
    try:
        resp = _session(itg.api_token).get(url, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        _log(itg, "profile", url, None, resp.status_code, resp.text, True)
        cache.set(ck, data, 1800)
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(itg, "profile", url, None,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, err_msg=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(ck, result, 60)
        return result


# ---------------------------------------------------------------------------
# 4.  PRODUCTS  (flat list, exactly as the API returns)
# ---------------------------------------------------------------------------

def get_alkasr_products(store=None, force_refresh=False, integration=None,
                        product_ids=None, base_only=False):
    """
    GET /client/api/products
    GET /client/api/products?products_id=id1,id2
    GET /client/api/products?base=1

    Always returns a plain Python list on success,
    or {"status":"error","message":"..."} on failure.
    """
    from django.core.cache import cache

    itg = integration or get_integration(store)
    if not itg:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    ck_suffix = ""
    if product_ids:
        ck_suffix = "_ids_" + "_".join(str(i) for i in product_ids)
    elif base_only:
        ck_suffix = "_base"
    ck = f"alk_products_{itg.id}{ck_suffix}"

    if not force_refresh:
        cached = cache.get(ck)
        if cached is not None:
            return cached

    url = itg.base_url.rstrip("/") + "/client/api/products"
    params = {}
    if product_ids:
        params["products_id"] = ",".join(str(i) for i in product_ids)
    if base_only:
        params["base"] = 1

    try:
        resp = _session(itg.api_token).get(url, params=params, timeout=20, verify=False)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"API returned {type(data).__name__}, expected list")
        _log(itg, "products", resp.url, params, resp.status_code, resp.text, True)
        cache.set(ck, data, 14400)   # 4 hours
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(itg, "products", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, err_msg=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(ck, result, 60)
        return result


# ---------------------------------------------------------------------------
# 5.  CONTENT  (categories + products per parent)
# ---------------------------------------------------------------------------

def get_alkasr_content(category_id=0, store=None, force_refresh=False, integration=None):
    """
    GET /client/api/content/<category_id>

    Use category_id=0 for root / home page.
    Always returns {"products": [...], "categories": [...]}
    """
    from django.core.cache import cache

    itg = integration or get_integration(store)
    if not itg:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    ck = f"alk_content_{itg.id}_{category_id}"
    if not force_refresh:
        cached = cache.get(ck)
        if cached is not None:
            return cached

    url = itg.base_url.rstrip("/") + f"/client/api/content/{category_id}"
    try:
        resp = _session(itg.api_token).get(url, timeout=15, verify=False)
        resp.raise_for_status()
        raw = resp.json()

        if isinstance(raw, dict):
            result = {
                "products":   raw.get("products")   or [],
                "categories": raw.get("categories") or [],
            }
        elif isinstance(raw, list):
            result = {"products": raw, "categories": []}
        else:
            result = {"products": [], "categories": []}

        _log(itg, f"content/{category_id}", url, None, resp.status_code, resp.text, True)
        cache.set(ck, result, 14400)
        return result
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(itg, f"content/{category_id}", url, None,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, err_msg=str(exc))
        result = {"status": "error", "message": str(exc)}
        cache.set(ck, result, 60)
        return result


# ---------------------------------------------------------------------------
# 6.  ORDER PLACEMENT
# ---------------------------------------------------------------------------

ALKASR_ERRORS = {
    120: "مفتاح API مطلوب (ERR-120)",
    121: "مفتاح API غير صحيح (ERR-121)",
    122: "غير مسموح بالوصول (ERR-122)",
    123: "عنوان IP غير مصرح (ERR-123)",
    130: "المزوّد في وضع الصيانة (ERR-130)",
    100: "رصيد المزوّد غير كافٍ (ERR-100)",
    105: "الكمية غير متوفرة (ERR-105)",
    106: "الكمية غير مسموح بها (ERR-106)",
    107: "معرّف اللاعب محظور (ERR-107)",
    108: "يرجى إدخال رمز 2FA (ERR-108)",
    109: "المنتج غير موجود (ERR-109)",
    110: "المنتج غير متاح الآن (ERR-110)",
    111: "حاول مجدداً بعد دقيقة (ERR-111)",
    112: "الكمية أقل من الحد الأدنى (ERR-112)",
    113: "الكمية أكبر من الحد الأقصى (ERR-113)",
    114: "خطأ غير معروف (ERR-114)",
    500: "خطأ داخلي في المزوّد (ERR-500)",
}


def place_alkasr_order(api_product_id, qty, order_uuid, metadata, store=None, integration=None):
    """
    GET /client/api/newOrder/<product_id>/params
        ?qty=<qty>
        &order_uuid=<uuid>
        &<param_name>=<param_value>...

    Returns the full API JSON on success {"status":"OK","data":{...}}
    or {"status":"error","message":"..."} on failure.
    """
    from apps.catalog.models import ProductVariant

    itg = integration or get_integration(store)
    if not itg or not (itg.api_token or "").strip():
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    url = itg.base_url.rstrip("/") + f"/client/api/newOrder/{api_product_id}/params"

    # Base parameters
    params = {
        "qty": int(qty),
        "order_uuid": str(order_uuid),
    }

    # Resolve user-supplied metadata → API parameter names
    clean = {
        str(k).strip(): str(v).strip()
        for k, v in (metadata or {}).items()
        if k and v is not None
    }

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

    if schema_fields:
        for field in schema_fields:
            api_name = field.get("name")
            if not api_name:
                continue
            val = (
                clean.get(api_name)
                or clean.get(f"custom_{api_name}")
                or next(
                    (v for k, v in clean.items()
                     if k.lower() == api_name.lower()),
                    None
                )
                or (list(clean.values())[0] if len(clean) == 1 else None)
            )
            if val is not None:
                params[api_name] = val
    else:
        # No schema → pass all ASCII-safe keys through
        for k, v in clean.items():
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                params[k] = v

    try:
        resp = _session(itg.api_token).get(url, params=params, timeout=20, verify=False)

        try:
            rj = resp.json()
        except Exception:
            rj = None

        # Provider-level error
        if isinstance(rj, dict) and str(rj.get("status", "")).upper() == "ERROR":
            raw_code = rj.get("code", 0)
            msg      = rj.get("msg") or rj.get("message") or "خطأ غير معروف"
            code_int = _safe_int(raw_code, 0)

            _log(itg, "newOrder", url, params, resp.status_code, resp.text, False,
                 err_code=code_int, err_msg=msg,
                 product_id=api_product_id, order_uuid=order_uuid)

            friendly = ALKASR_ERRORS.get(code_int, f"خطأ من المزوّد (ERR-{raw_code}): {msg}")
            log.error("[Alkasr] newOrder error code=%s msg=%s", raw_code, msg)

            try:
                from apps.notifications.services import notify_provider_error
                notify_provider_error(
                    error_code=code_int,
                    provider_name="Alkasr VIP",
                    product_id=api_product_id,
                    detail=msg,
                )
            except Exception as ne:
                log.warning("notify_provider_error: %s", ne)

            return {"status": "error", "message": friendly}

        # Success
        if isinstance(rj, dict) and str(rj.get("status", "")).upper() == "OK":
            _log(itg, "newOrder", url, params, resp.status_code, resp.text, True,
                 product_id=api_product_id, order_uuid=order_uuid)
            return rj

        resp.raise_for_status()
        _log(itg, "newOrder", url, params, resp.status_code, resp.text, False,
             err_msg="Unexpected response", product_id=api_product_id, order_uuid=order_uuid)
        return {"status": "error", "message": "استجابة غير متوقعة من المزوّد."}

    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(itg, "newOrder", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, err_msg=str(exc),
             product_id=api_product_id, order_uuid=order_uuid)
        log.exception("[Alkasr] newOrder exception product_id=%s", api_product_id)
        return {"status": "error", "message": f"فشل الاتصال بالمزوّد: {exc}"}


# ---------------------------------------------------------------------------
# 7.  ORDER STATUS CHECK
# ---------------------------------------------------------------------------

def check_alkasr_orders(order_identifiers, is_uuid=False, store=None, integration=None):
    """
    GET /client/api/check?orders=[ID1,ID2]
    GET /client/api/check?orders=[uuid]&uuid=1

    order_identifiers: single string (UUID mode) or list of order-ID strings.
    """
    itg = integration or get_integration(store)
    if not itg:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    url = itg.base_url.rstrip("/") + "/client/api/check"

    if is_uuid:
        params = {"orders": f"[{order_identifiers}]", "uuid": 1}
    else:
        ids_str = (
            ",".join(str(i) for i in order_identifiers)
            if isinstance(order_identifiers, (list, tuple))
            else str(order_identifiers)
        )
        params = {"orders": f"[{ids_str}]"}

    try:
        resp = _session(itg.api_token).get(url, params=params, timeout=12, verify=False)
        resp.raise_for_status()
        data = resp.json()
        _log(itg, "check", url, params, resp.status_code, resp.text, True,
             order_uuid=order_identifiers if is_uuid else None)
        return data
    except Exception as exc:
        r = getattr(exc, "response", None)
        _log(itg, "check", url, params,
             getattr(r, "status_code", None), getattr(r, "text", str(exc)),
             False, err_msg=str(exc),
             order_uuid=order_identifiers if is_uuid else None)
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# 8.  QTY_VALUES PARSER  — faithful to official documentation
# ---------------------------------------------------------------------------

def parse_qty_values(qty_values_raw, product_type="package"):
    """
    Converts the API's qty_values field to a metadata dict stored on
    ProductVariant.metadata.

    Rules (from official docs):
    ─────────────────────────────────────────────────────────────────
    qty_values: null
        → qty MUST be 1 (fixed package)

    qty_values: ["110", "150", "210"]
        → ONLY these quantities are allowed  (qty_type = "list")

    qty_values: {"min": "500", "max": "500000"}
        → qty must be within [min, max]  (qty_type = "range")
        → For product_type=="amount" this means PER-UNIT pricing
    ─────────────────────────────────────────────────────────────────

    IMPORTANT: min/max values from the API arrive as strings OR ints OR None.
    The implementation must handle all of these without crashing.
    """

    # ── null ──────────────────────────────────────────────────────────────────
    if qty_values_raw is None:
        return {
            "qty_type": "fixed",
            "qty_min": 1,
            "qty_max": 1,
            "qty_list": [],
            "allow_custom_quantity": False,
            "product_type": product_type,
        }

    # ── list of allowed values ────────────────────────────────────────────────
    if isinstance(qty_values_raw, list):
        valid = []
        for x in qty_values_raw:
            v = _safe_int(x, default=None)
            if v is not None and v > 0:
                valid.append(str(v))
        # If all items were invalid, treat as fixed
        if not valid:
            return {
                "qty_type": "fixed",
                "qty_min": 1,
                "qty_max": 1,
                "qty_list": [],
                "allow_custom_quantity": False,
                "product_type": product_type,
            }
        return {
            "qty_type": "list",
            "qty_min": int(valid[0]),
            "qty_max": int(valid[-1]),
            "qty_list": valid,
            "allow_custom_quantity": False,
            "product_type": product_type,
        }

    # ── range dict ────────────────────────────────────────────────────────────
    if isinstance(qty_values_raw, dict):
        qty_min = _safe_int(qty_values_raw.get("min"), default=1)
        qty_max = _safe_int(qty_values_raw.get("max"), default=999_999_999)
        if qty_min < 1:
            qty_min = 1
        if qty_max < qty_min:
            qty_max = qty_min
        return {
            "qty_type": "range",
            "qty_min": qty_min,
            "qty_max": qty_max,
            "qty_list": [],
            "allow_custom_quantity": True,
            "product_type": product_type,
        }

    # ── unknown / fallback ────────────────────────────────────────────────────
    return {
        "qty_type": "fixed",
        "qty_min": 1,
        "qty_max": 1,
        "qty_list": [],
        "allow_custom_quantity": False,
        "product_type": product_type,
    }


# ---------------------------------------------------------------------------
# 9.  FORM SCHEMA BUILDER
# ---------------------------------------------------------------------------

def _build_form_schema(params_list):
    """
    Converts the API `params` array (list of parameter name strings)
    into our internal form_schema dict.

    The `name` key MUST be the exact API parameter name — the server
    will reject the order if it doesn't match.
    """
    fields = []
    for param in (params_list or []):
        if not param or not isinstance(param, str):
            continue
        lower = param.lower().replace(" ", "").replace("_", "")
        if lower in ("playerid",):
            label = "معرّف اللاعب (Player ID)"
        elif lower in ("username", "user"):
            label = "اسم المستخدم"
        elif lower in ("phone", "mobile", "number"):
            label = "رقم الهاتف / الحساب"
        elif lower in ("email",):
            label = "البريد الإلكتروني"
        elif lower in ("zoneid",):
            label = "Zone ID"
        elif lower in ("serverid",):
            label = "Server ID"
        else:
            label = param   # Use the raw string as-is

        fields.append({
            "name": param,      # EXACT API parameter name
            "label": label,
            "type": "text",
            "required": True,
        })
    return {"version": 1, "fields": fields}


# ---------------------------------------------------------------------------
# 10.  CATALOG SYNC ENGINE
# ---------------------------------------------------------------------------

def sync_alkasr_catalog(store, selected_category_ids=None, markup_percent=0.0, integration=None):
    """
    Imports the full Alkasr VIP product catalogue into the local database.

    Database structure created
    ──────────────────────────
    Category  (main — derived from parent_id lookup or "الخدمات الإلكترونية")
      └─ Category  (sub — named from product.category_name)
           └─ Product  (one per unique category_name under that sub-category)
                └─ ProductVariant  (one per API product entry)

    Pricing logic
    ─────────────
    product_type == "package"
        → variant.price = api_price × markup_factor
        → qty always 1 (or from a fixed list)

    product_type == "amount"
        → variant.price = api_price × markup_factor   (STORED AS PER-UNIT PRICE)
        → At checkout: total = variant.price × quantity_chosen_by_customer
        → Example: 0.104 $/UC × 100 UC = 10.40 $  (NOT 100 $)
    """
    from apps.catalog.models import Category, Product, ProductVariant
    from apps.orders.models import OrderItem

    itg = integration or get_integration(store)
    if not itg:
        return {"status": "error", "message": "لا يوجد إعداد Alkasr VIP نشط."}

    # ── 1. Fetch ALL products from API ────────────────────────────────────────
    products_raw = get_alkasr_products(store=store, force_refresh=True, integration=itg)
    if isinstance(products_raw, dict) and products_raw.get("status") == "error":
        return products_raw
    if not isinstance(products_raw, list):
        return {"status": "error", "message": "استجابة غير صالحة من المزوّد."}

    # ── 2. Fetch root content to get category metadata (names, images) ────────
    root_content = get_alkasr_content(0, store=store, force_refresh=True, integration=itg)
    # Map category_id → category_dict  for fast lookup
    api_cats: dict[int, dict] = {}
    if isinstance(root_content, dict):
        for cat in root_content.get("categories", []):
            cid = _safe_int(cat.get("id"), default=None)
            if cid is not None:
                api_cats[cid] = cat

    # ── 3. Pre-compute markup factor ──────────────────────────────────────────
    try:
        markup_factor = Decimal("1") + Decimal(str(markup_percent)) / Decimal("100")
    except InvalidOperation:
        markup_factor = Decimal("1")

    created_count = 0
    updated_count = 0

    with transaction.atomic():

        # ── 4. Delete obsolete API products (safe — skip those with orders) ───
        for prod in list(Product.objects.filter(store=store, is_api_product=True)):
            if not OrderItem.objects.filter(variant__product=prod).exists():
                try:
                    prod.delete()
                except Exception:
                    prod.is_active = False
                    prod.save(update_fields=["is_active"])

        # ── 5. Warm in-memory caches ───────────────────────────────────────────
        local_cats: dict[str, Category] = {}
        for cat in Category.objects.filter(store=store).select_related("parent"):
            local_cats[cat.name] = cat
            if cat.parent:
                local_cats[f"{cat.parent.name}|||{cat.name}"] = cat

        local_prods: dict[str, Product] = {
            f"{p.category_id}||{p.name}": p
            for p in Product.objects.filter(store=store, is_api_product=True)
        }

        local_variants: dict[int, ProductVariant] = {
            v.api_product_id: v
            for v in ProductVariant.objects.filter(api_product_id__isnull=False)
                .select_related("product")
        }

        from apps.common.tenant_utils import bypass_tenant_filter
        with bypass_tenant_filter():
            existing_skus: set = set(
                ProductVariant.objects.values_list("sku", flat=True)
            )

        # ── 6. Process every API product ──────────────────────────────────────
        for item in products_raw:
            # ── 6a. Basic field extraction ────────────────────────────────────
            api_id = item.get("id")
            if not api_id:
                continue

            raw_name = (item.get("name") or "").strip()
            if not raw_name or raw_name.lower() in ("null", "none", "nan", ""):
                continue

            cat_name       = (item.get("category_name") or raw_name).strip()
            parent_id_raw  = item.get("parent_id")
            parent_id      = _safe_int(parent_id_raw, default=0)
            product_type   = (item.get("product_type") or "package").strip().lower()
            is_available   = bool(item.get("available", True))
            qty_values_raw = item.get("qty_values")
            params_list    = item.get("params") or []

            # ── 6b. Category filter (if operator chose specific categories) ───
            if selected_category_ids is not None:
                if parent_id not in selected_category_ids:
                    continue

            # ── 6c. Pricing ───────────────────────────────────────────────────
            # api price  = the price the store charges (includes provider margin)
            # base_price = provider cost
            try:
                api_price  = Decimal(str(item.get("price") or 0))
            except InvalidOperation:
                api_price  = Decimal("0")
            try:
                base_price = Decimal(str(item.get("base_price") or 0))
            except InvalidOperation:
                base_price = Decimal("0")

            # Retail price (stored in variant.price):
            #   For "amount" products → per-unit price × markup
            #   For "package" products → fixed package price × markup
            retail_price = (api_price * markup_factor).quantize(Decimal("0.000001"))
            cost_price   = base_price   # store provider cost as-is

            # ── 6d. Form schema & qty metadata ───────────────────────────────
            form_schema = _build_form_schema(params_list)
            qty_meta    = parse_qty_values(qty_values_raw, product_type=product_type)

            # ── 6e. Resolve main category name ────────────────────────────────
            if parent_id and parent_id in api_cats:
                main_cat_name = (api_cats[parent_id].get("name") or "").strip() or "الخدمات الإلكترونية"
            elif parent_id:
                main_cat_name = f"تصنيف {parent_id}"
            else:
                main_cat_name = "الخدمات الإلكترونية"

            # ── 6f. Get or create MAIN category ──────────────────────────────
            main_cat = local_cats.get(main_cat_name)
            if not main_cat:
                main_cat = Category.objects.create(
                    name=main_cat_name,
                    store=store,
                    is_active=True,
                    parent=None,
                )
                local_cats[main_cat_name] = main_cat

            # ── 6g. Get or create SUB category (= category_name) ─────────────
            sub_key = f"{main_cat_name}|||{cat_name}"
            sub_cat = local_cats.get(sub_key)
            if not sub_cat:
                # Check without parent prefix (might already exist)
                sub_cat = local_cats.get(cat_name)
                if not sub_cat:
                    sub_cat = Category.objects.create(
                        name=cat_name,
                        store=store,
                        is_active=True,
                        parent=main_cat,
                    )
                    local_cats[cat_name] = sub_cat
                local_cats[sub_key] = sub_cat

            # ── 6h. Get or create PRODUCT (one per category_name) ────────────
            prod_key = f"{sub_cat.id}||{cat_name}"
            product = local_prods.get(prod_key)
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
                local_prods[prod_key] = product
            else:
                changed = False
                if is_available and not product.is_active:
                    product.is_active = True
                    changed = True
                # Merge new form fields if needed
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

            # ── 6i. Get or create VARIANT (one per API product ID) ────────────
            variant = local_variants.get(api_id)
            if variant:
                variant.product  = product
                variant.name     = raw_name
                variant.cost     = cost_price
                variant.price    = retail_price
                variant.is_active = is_available
                variant.metadata = qty_meta
                variant.save()
                updated_count += 1
            else:
                prefix = store.subdomain.upper() if (store and getattr(store, "subdomain", None)) else "GLB"
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
                    price=retail_price,
                    cost=cost_price,
                    api_product_id=api_id,
                    is_active=is_available,
                    delivery_type="manual",
                    metadata=qty_meta,
                )
                local_variants[api_id] = variant
                created_count += 1

    log.info("[Alkasr sync] created=%d updated=%d", created_count, updated_count)
    return {
        "status": "success",
        "created": created_count,
        "updated": updated_count,
    }
