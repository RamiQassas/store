"""
Order creation service — rebuilt from scratch.

Pricing rules for API products
═══════════════════════════════
  product_type == "package"
      → variant.price  = fixed price per package  (qty is always 1 or from a list)
      → customer pays:  variant.price  (independent of quantity field)

  product_type == "amount"
      → variant.price  = price PER UNIT  (e.g. 0.104 USD per UC)
      → customer pays:  variant.price × quantity_chosen
      → Example: 0.104 × 100 UC = 10.40 USD   ← NOT 100 USD

Quantity validation rules (mirrors API docs)
════════════════════════════════════════════
  qty_type == "fixed"  → force qty = 1
  qty_type == "list"   → qty must be one of qty_list
  qty_type == "range"  → qty_min ≤ qty ≤ qty_max
"""

import logging
import re
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from apps.catalog.models import ProductKey, ProductVariant
from apps.orders.models import Coupon, Invoice, Order, OrderItem, OrderLog
from apps.wallets.services import debit_wallet, get_or_create_wallet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def next_order_number():
    return timezone.now().strftime("ORD%Y%m%d%H%M%S%f")


def _safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def calculate_variant_subtotal(variant, user, quantity=1):
    """
    Return the payable subtotal for a variant and provider quantity.

    The API stores prices as per-unit values. For range/amount type products,
    the customer pays: unit_price * quantity. For fixed/list type, qty is 1 or
    a selected denomination — still multiply by qty (which will be 1 for fixed).
    """
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        qty = 1
    qty = max(qty, 1)

    unit_price = variant.get_price_for_user(user)
    return unit_price * Decimal(qty)


def resolve_variant_provider_and_product(variant):
    """
    Robust resolver for ProviderProduct and active ProviderProfile across
    all variant types (platform catalog, cloned sub-store variants, custom variants).
    Guarantees isolation bypass, extracts correct remote_id without suffix corruption,
    and synchronizes the active credentials from APIIntegration.
    """
    if not variant:
        return None, None

    import re
    from apps.common.tenant_utils import bypass_tenant_filter
    from apps.providers.models import ProviderMapping, ProviderProduct, ProviderProfile
    from apps.catalog.models import APIIntegration, ProductVariant
    from django.db.models import Q

    with bypass_tenant_filter():
        provider_product = None
        profile = None

        # 1. Direct mapping check on this variant
        mapping = getattr(variant, "provider_mapping", None)
        if not mapping or not mapping.provider_product:
            mapping = ProviderMapping.objects.filter(local_variant=variant).select_related("provider_product__profile").first()
        if mapping and mapping.provider_product:
            provider_product = mapping.provider_product
            profile = provider_product.profile

        # 2. Extract remote_id and candidate profile_id from SKU or metadata
        rem_id = None
        sku_profile_id = None
        if variant.sku:
            # Pattern: PRV-<uuid>-<remote_id>(-<suffix>)?
            m = re.match(r"^PRV-([a-f0-9\-]{36})-([0-9a-zA-Z_]+)(?:-[a-f0-9]+)?$", variant.sku, re.I)
            if m:
                sku_profile_id = m.group(1)
                rem_id = m.group(2)
            else:
                m2 = re.search(r"PRV-(?:.*?-)?(\d+)(?:-[a-f0-9]+)?$", variant.sku, re.I)
                if m2:
                    rem_id = m2.group(1)

        if not rem_id and variant.api_product_id:
            rem_id = str(variant.api_product_id)
        if not rem_id and variant.metadata and isinstance(variant.metadata, dict) and variant.metadata.get("remote_id"):
            rem_id = str(variant.metadata["remote_id"])
        if not rem_id and getattr(variant.product, "api_product_id", None):
            rem_id = str(variant.product.api_product_id)

        # 3. Sub-store variant template matching: match against platform catalog
        if not provider_product and variant.product.store:
            g_var = None
            if variant.sku:
                base_sku = variant.sku.rsplit("-", 1)[0]
                g_var = ProductVariant.all_objects.filter(product__store__isnull=True, sku=base_sku).first()
                if not g_var:
                    g_var = ProductVariant.all_objects.filter(product__store__isnull=True, sku=variant.sku).first()
            if not g_var and variant.api_product_id:
                g_var = ProductVariant.all_objects.filter(product__store__isnull=True, api_product_id=variant.api_product_id).first()
            if not g_var and rem_id:
                g_var = ProductVariant.all_objects.filter(product__store__isnull=True, sku__icontains=f"-{rem_id}").first()
            if not g_var:
                g_var = ProductVariant.all_objects.filter(
                    product__store__isnull=True,
                    name=variant.name,
                    product__name=variant.product.name
                ).first()

            if g_var:
                g_map = getattr(g_var, "provider_mapping", None) or ProviderMapping.objects.filter(local_variant=g_var).select_related("provider_product__profile").first()
                if g_map and g_map.provider_product:
                    provider_product = g_map.provider_product
                    profile = provider_product.profile
                elif g_var.api_product_id:
                    rem_id = str(g_var.api_product_id)

        # 4. Resolve ProviderProduct by rem_id if not yet set
        if not provider_product and rem_id:
            qs = ProviderProduct.objects.filter(remote_id=str(rem_id))
            if sku_profile_id:
                provider_product = qs.filter(profile_id=sku_profile_id).select_related("profile").first()
            if not provider_product:
                provider_product = qs.filter(profile__is_active=True).select_related("profile").first()
            if not provider_product:
                provider_product = qs.select_related("profile").first()
            if provider_product:
                profile = provider_product.profile

        # 5. Resolve active profile and synchronize credentials
        provider_code = (
            getattr(variant, "api_provider", None)
            or getattr(variant.product, "api_provider", None)
            or (getattr(profile, "provider_name", "") if profile else "")
            or "alkasr"
        )
        is_tafa3ol = "tafa3ol" in str(provider_code).lower()

        # Ensure profile is active
        if profile and not profile.is_active:
            profile = None

        if not profile:
            if is_tafa3ol:
                profile = ProviderProfile.all_objects.filter(store__isnull=True, is_active=True).filter(
                    Q(base_url__icontains="tafa3ol") | Q(provider_name__icontains="تفاعل")
                ).order_by("-updated_at").first()
            else:
                profile = ProviderProfile.all_objects.filter(store__isnull=True, is_active=True).filter(
                    Q(base_url__icontains="alkasr") | Q(provider_name__in=["رقميات", "الكاسر VIP", "Alkasr VIP"])
                ).order_by("-updated_at").first()

        # Synchronize token and base_url from active APIIntegration if available
        integ_filter = Q(provider="tafa3olcard") if is_tafa3ol else (Q(provider="alkasr") | Q(base_url__icontains="alkasr"))
        integ = APIIntegration.all_objects.filter(store__isnull=True, is_active=True).filter(integ_filter).order_by("-updated_at").first()
        if integ and integ.api_token and integ.api_token not in ("DEFAULT_TOKEN", ""):
            if not profile:
                profile = ProviderProfile.all_objects.create(
                    store=None,
                    provider_name="رقميات" if not is_tafa3ol else integ.name,
                    base_url=integ.base_url,
                    api_token=integ.api_token,
                    is_active=True,
                )
            elif profile.api_token != integ.api_token or profile.base_url != integ.base_url:
                profile.api_token = integ.api_token
                profile.base_url = integ.base_url
                profile.save(update_fields=["api_token", "base_url"])

        return provider_product, profile


def is_provider_unavailable_error(exc_or_data):
    """
    Returns True if an exception, error code, or raw response message
    indicates that the product or quantity is unavailable, out of stock, or deleted at the provider.
    """
    if not exc_or_data:
        return False

    code = getattr(exc_or_data, "code", None)
    if isinstance(exc_or_data, dict):
        code = code or exc_or_data.get("code") or exc_or_data.get("error_code")

    try:
        if code is not None and int(code) in (105, 106, 109, 110):
            return True
    except (ValueError, TypeError):
        pass

    try:
        from services.provider.alkasr.exceptions import (
            ProductUnavailableException,
            ProductDeletedException,
            QuantityNotAvailableException,
            QuantityNotAllowedException
        )
        if isinstance(exc_or_data, (ProductUnavailableException, ProductDeletedException, QuantityNotAvailableException, QuantityNotAllowedException)):
            return True
    except Exception:
        pass

    text = str(exc_or_data).lower()
    keywords = [
        "product unavailable", "quantity not available", "product deleted",
        "product not found", "out of stock", "غير متوفر", "غير متاح",
        "غير متوفرة", "الكمية غير متوفرة", "نفد المخزون", "محذوف",
        "disabled", "not available", "is not available", "item unavailable",
        "err-105", "err-106", "err-109", "err-110"
    ]
    return any(k in text for k in keywords)


def mark_variant_unavailable(variant, reason=None, error_code=None, provider_product=None):
    """
    Immediately deactivates a variant and its mapped ProviderProduct across the entire system.
    If no active variants remain for the parent Product, marks the parent Product as out of stock.
    Also propagates deactivation to cloned variants/products in tenant sub-stores.
    """
    if not variant:
        return

    logger.warning(
        f"Marking variant {variant.id} ({variant.name}) unavailable. Reason: {reason}, Code: {error_code}"
    )

    from apps.common.tenant_utils import bypass_tenant_filter
    from apps.providers.models import ProviderMapping, ProviderProduct
    from apps.catalog.models import Product, ProductVariant
    from django.db.models import Q
    from django.core.cache import cache

    # 1. Update this variant
    variant.is_active = False
    variant.is_temporarily_disabled = True
    variant.save(update_fields=["is_active", "is_temporarily_disabled", "updated_at"])

    # 2. Resolve mapped ProviderProduct
    if not provider_product:
        mapping = getattr(variant, "provider_mapping", None)
        if not mapping:
            mapping = ProviderMapping.objects.filter(local_variant=variant).first()
        if mapping and mapping.provider_product:
            provider_product = mapping.provider_product
        else:
            resolved_prod, _ = resolve_variant_provider_and_product(variant)
            if resolved_prod:
                provider_product = resolved_prod

    affected_product_ids = {variant.product_id}

    with bypass_tenant_filter():
        if provider_product:
            # Deactivate provider product
            provider_product.is_active = False
            provider_product.local_is_active = False
            provider_product.save(update_fields=["is_active", "local_is_active", "updated_at"])

            # Find all local variants mapped to this provider product
            mapped_var_ids = list(
                ProviderMapping.objects.filter(provider_product=provider_product)
                .values_list("local_variant_id", flat=True)
            )
            if mapped_var_ids:
                mapped_vars = ProductVariant.all_objects.filter(id__in=mapped_var_ids)
                affected_product_ids.update(mapped_vars.values_list("product_id", flat=True))
                mapped_vars.update(is_active=False, is_temporarily_disabled=True)

        # Also search for cloned variants in sub-stores matching SKU
        sku_clean = variant.sku
        if sku_clean:
            cloned_vars = ProductVariant.all_objects.filter(sku=sku_clean)
            affected_product_ids.update(cloned_vars.values_list("product_id", flat=True))
            cloned_vars.update(is_active=False, is_temporarily_disabled=True)

        if variant.api_product_id:
            api_vars = ProductVariant.all_objects.filter(api_product_id=variant.api_product_id)
            affected_product_ids.update(api_vars.values_list("product_id", flat=True))
            api_vars.update(is_active=False, is_temporarily_disabled=True)

        # 3. Check parent products and mark out of stock if no active variants remain
        for pid in affected_product_ids:
            if not pid:
                continue
            prod = Product.all_objects.filter(id=pid).first()
            if prod:
                has_active = prod.variants.filter(is_active=True, is_temporarily_disabled=False).exists()
                if not has_active:
                    prod.is_out_of_stock = True
                    prod.save(update_fields=["is_out_of_stock", "updated_at"])
                cache.delete(f"product_detail_{pid}")

    # Clear catalog caches
    try:
        store_id = getattr(variant.product, "store_id", None)
        cache.delete_many([
            "catalog_products_global",
            f"catalog_products_store_{store_id}" if store_id else "catalog_products_global",
            f"product_detail_{variant.product_id}",
        ])
    except Exception:
        pass

# ---------------------------------------------------------------------------

def validate_coupon(coupon, user, variant, subtotal=None):
    """
    Validates coupon eligibility and returns the discount amount (Decimal).
    Raises ValueError with a descriptive Arabic message on any failure.
    """
    now = timezone.now()

    if not coupon.is_active:
        raise ValueError("هذا الكوبون غير نشط.")
    if coupon.expires_at and coupon.expires_at < now:
        raise ValueError("انتهت صلاحية هذا الكوبون.")
    if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
        raise ValueError("تم استخدام هذا الكوبون لأقصى عدد مسموح به.")

    user_uses = Order.objects.filter(customer=user, coupon=coupon).count()
    if user_uses >= coupon.max_uses_per_user:
        raise ValueError("لقد استخدمت هذا الكوبون مسبقاً.")

    if subtotal and coupon.min_order_amount and subtotal < coupon.min_order_amount:
        raise ValueError(
            f"الحد الأدنى للطلب لاستخدام هذا الكوبون هو {coupon.min_order_amount} USD"
        )

    checks = []

    if coupon.is_verified_only:
        checks.append(("kyc", user.is_kyc_verified))

    if coupon.limit_to_users.exists():
        checks.append(("user", coupon.limit_to_users.filter(id=user.id).exists()))

    if coupon.limit_to_tiers:
        checks.append(("tier", user.tier in coupon.limit_to_tiers))

    if coupon.valid_for_users_before:
        checks.append(("reg_before", user.date_joined <= coupon.valid_for_users_before))

    if coupon.valid_for_users_after:
        checks.append(("reg_after", user.date_joined >= coupon.valid_for_users_after))

    if coupon.limit_to_area or coupon.limit_to_place_of_birth:
        kyc = getattr(user, "kyc_request", None)
        area_ok = False
        if kyc:
            if coupon.limit_to_area:
                if coupon.limit_to_area.lower() in kyc.current_residence.lower():
                    if coupon.allow_area_type in (Coupon.AreaType.RESIDENCE, Coupon.AreaType.BOTH):
                        area_ok = True
            if coupon.limit_to_place_of_birth:
                if coupon.limit_to_place_of_birth.lower() in kyc.place_of_birth.lower():
                    if coupon.allow_area_type in (Coupon.AreaType.BIRTH, Coupon.AreaType.BOTH):
                        area_ok = True
        checks.append(("area", area_ok))

    if coupon.limit_to_ip_countries or coupon.limit_to_ip_cities:
        ip_ok = False
        user_country = getattr(user, "last_country", "").upper()
        user_city    = getattr(user, "last_city",    "").lower()
        if coupon.limit_to_ip_countries and user_country in [c.upper() for c in coupon.limit_to_ip_countries]:
            ip_ok = True
        if coupon.limit_to_ip_cities and any(c.lower() in user_city for c in coupon.limit_to_ip_cities):
            ip_ok = True
        checks.append(("ip_geo", ip_ok))

    if not coupon.apply_to_all_products:
        prod_ok = (
            coupon.limit_to_products.filter(id=variant.product.id).exists()
            if coupon.limit_to_products.exists()
            else False
        )
        checks.append(("product", prod_ok))

    if checks:
        satisfied = sum(1 for _, ok in checks if ok)
        if coupon.match_mode == Coupon.MatchMode.ALL and satisfied < len(checks):
            failed = next(name for name, ok in checks if not ok)
            msgs = {
                "kyc":        "هذا الكوبون مخصص للحسابات الموثقة فقط.",
                "user":       "هذا الكوبون غير مخصص لحسابك.",
                "tier":       "هذا الكوبون غير متاح لفئتك.",
                "reg_before": "هذا الكوبون متاح فقط للحسابات القديمة.",
                "reg_after":  "هذا الكوبون متاح فقط للحسابات الجديدة.",
                "area":       "هذا الكوبون غير متاح لمنطقتك (KYC).",
                "ip_geo":     "هذا الكوبون غير متاح لموقعك الحالي.",
                "product":    "هذا الكوبون صالح لمنتج آخر فقط.",
            }
            raise ValueError(msgs.get(failed, "لا تتوفر شروط استخدام الكوبون."))
        elif coupon.match_mode == Coupon.MatchMode.ANY and satisfied == 0:
            raise ValueError("هذا الكوبون غير متاح لك (لا تنطبق عليك أي من شروط الاستخدام).")

    # Calculate discount amount
    discount = Decimal("0.00")
    if subtotal:
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount = (subtotal * (coupon.discount_percent / Decimal("100"))).quantize(Decimal("0.01"))
        elif coupon.discount_type == Coupon.DiscountType.FIXED_AMOUNT:
            discount = min(coupon.discount_amount, subtotal)
    return discount


class WholesaleInsufficientBalanceError(ValueError):
    def __init__(self, owner, variant_name, required_cost, curr_code, store_name=None, store_id=None):
        self.owner = owner
        self.variant_name = variant_name
        self.required_cost = required_cost
        self.curr_code = curr_code
        self.store_name = store_name
        self.store_id = store_id
        super().__init__("لم يتم إكمال الطلب، يرجى التواصل مع دعم المتجر.")


# ---------------------------------------------------------------------------
# Main order creation
# ---------------------------------------------------------------------------

@transaction.atomic
def _create_order_atomic(customer, variant_id, quantity=1, fulfillment_data=None,
                         coupon=None, metadata=None,
                         shipping_name=None, shipping_phone=None, shipping_address=None):
    """
    Creates a new order, debits the customer's wallet, and calls the API
    provider if needed.

    Returns the created Order instance.
    Raises ValueError (with an Arabic message) on any business logic failure.
    """
    # ── Guards ────────────────────────────────────────────────────────────────
    if customer.restriction_purchases:
        raise ValueError("حسابك مقيد من عمليات الشراء.")

    quantity = int(quantity)
    if quantity < 1:
        raise ValueError("الكمية يجب أن تكون 1 على الأقل.")

    # ── Fetch variant (locked for this transaction) ───────────────────────────
    try:
        variant = (
            ProductVariant.objects
            .select_related("product")
            .select_for_update()
            .get(id=variant_id, is_active=True, is_temporarily_disabled=False, product__is_active=True)
        )
    except ProductVariant.DoesNotExist:
        raise ValueError("هذه الباقة أو المنتج غير متوفر حالياً.")

    if variant.product.is_out_of_stock:
        raise ValueError("هذا المنتج غير متوفر حالياً (نفد المخزون).")

    # Check mapped provider product if API product
    prov_prod, _ = resolve_variant_provider_and_product(variant)
    if prov_prod and (not prov_prod.is_active or not prov_prod.local_is_active):
        mark_variant_unavailable(variant, reason="Provider product is inactive", provider_product=prov_prod)
        raise ValueError("هذه الباقة غير متوفرة حالياً لدى مزود الخدمة.")


    # ── Read qty metadata stored during sync ─────────────────────────────────
    meta             = variant.metadata if isinstance(variant.metadata, dict) else {}
    qty_type         = meta.get("qty_type")
    qty_list         = meta.get("qty_list", [])
    qty_min          = _safe_int(meta.get("qty_min"), 1)
    qty_max          = _safe_int(meta.get("qty_max"), 999_999_999)
    api_product_type = meta.get("product_type", "package")   # "amount" or "package"

    # ── Quantity validation (mirrors API rules) ───────────────────────────────
    if qty_type == "fixed":
        # null qty_values in API → must send qty=1
        quantity = 1

    elif qty_type == "list":
        clean_valid_quantities = [str(x).strip() for x in qty_list if x is not None and str(x).strip().lower() not in ('none', 'null', '')]
        if str(quantity) not in clean_valid_quantities:
            raise ValueError(
                f"الكمية المسموح بها لهذه الباقة هي إحدى القيم التالية فقط: {', '.join(clean_valid_quantities)}"
            )

    elif qty_type == "range":
        if quantity < qty_min:
            raise ValueError(f"الحد الأدنى المسموح به للكمية هو {qty_min:,}")
        if quantity > qty_max:
            raise ValueError(f"الحد الأقصى المسموح به للكمية هو {qty_max:,}")

    # ── Inventory check (for non-API products with inventory tracking) ────────
    from apps.catalog.models import Product
    product = Product.objects.select_for_update().get(id=variant.product_id)

    if product.track_inventory:
        if product.quantity < quantity:
            raise ValueError(
                f"الكمية المطلوبة ({quantity}) غير متوفرة. "
                f"الكمية المتوفرة حالياً: {product.quantity}"
            )
        product.quantity -= quantity
        if product.quantity <= 0:
            product.quantity      = 0
            product.is_out_of_stock = True
            product.save(update_fields=["quantity", "is_out_of_stock"])
            try:
                from apps.notifications.services import notify_staff
                notify_staff(
                    title=f"نفاد مخزون: {product.name}",
                    body=f"كمية المنتج '{product.name}' نفدت بالكامل.",
                    category="admin_new_order",
                )
            except Exception:
                pass
        else:
            product.save(update_fields=["quantity"])
            if product.quantity <= product.low_stock_threshold:
                try:
                    from apps.notifications.services import notify_staff
                    notify_staff(
                        title=f"مخزون منخفض: {product.name}",
                        body=f"تبقّى {product.quantity} وحدة من '{product.name}'.",
                        category="admin_new_order",
                    )
                except Exception:
                    pass

    # ── Shipping validation for physical products ─────────────────────────────
    if (
        variant.product.product_type == "physical"
        and not (variant.product.form_schema or {}).get("fields")
    ):
        if not (shipping_name and shipping_phone and shipping_address):
            raise ValueError("جميع حقول الشحن والتوصيل مطلوبة للطلب المادي.")

    # ── Auto-delivery keys (digital codes stored locally or via Raqamiyat) ────
    order_store = getattr(variant.product, "store", None)
    if not order_store:
        from apps.common.tenant_utils import get_current_store
        order_store = get_current_store()

    locked_keys = []
    if variant.delivery_type == "keys":
        key_ids = list(
            ProductKey.objects
            .filter(variant=variant, is_used=False)
            .values_list("id", flat=True)[:quantity]
        )
        if len(key_ids) < quantity and order_store:
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                global_var = ProductVariant.all_objects.filter(
                    product__store__isnull=True,
                    name=variant.name,
                    product__name=variant.product.name
                ).first()
                if global_var:
                    key_ids = list(
                        ProductKey.objects
                        .filter(variant=global_var, is_used=False)
                        .values_list("id", flat=True)[:quantity]
                    )

        if len(key_ids) < quantity:
            raise ValueError("المخزون غير كافٍ لتلبية الكمية المطلوبة.")

        from apps.common.tenant_utils import bypass_tenant_filter
        with bypass_tenant_filter():
            locked_keys = list(
                ProductKey.objects.filter(id__in=key_ids, is_used=False).select_for_update()
            )
        if len(locked_keys) < quantity:
            raise ValueError("المخزون غير كافٍ لتلبية الكمية المطلوبة.")

    # ── Price calculation ─────────────────────────────────────────────────────
    price    = variant.get_price_for_user(customer)
    subtotal = calculate_variant_subtotal(variant, customer, quantity)

    # ── Coupon discount ───────────────────────────────────────────────────────
    discount = Decimal("0.00")
    if coupon:
        from apps.orders.models import Coupon
        from django.db.models import F
        coupon = Coupon.objects.select_for_update().get(id=coupon.id)
        discount = validate_coupon(coupon, customer, variant, subtotal=subtotal)
        Coupon.objects.filter(id=coupon.id).update(used_count=F("used_count") + 1)
        coupon.refresh_from_db(fields=["used_count"])

    total = max(subtotal - discount, Decimal("0.00"))

    order_store = getattr(variant.product, "store", None)
    if not order_store:
        from apps.common.tenant_utils import get_current_store
        order_store = get_current_store()

    # ── 1. Check customer wallet balance ──────────────────────────────────────
    wallet = get_or_create_wallet(customer)
    debit_amount = total
    if wallet.currency.code != "USD":
        debit_amount = wallet.currency.from_base(total)
    if wallet.available_balance < debit_amount:
        raise ValueError(f"رصيدك غير كافٍ لإتمام هذا الطلب. الرصيد المطلوب: {debit_amount} {wallet.currency.code}")

    # ── 2. For tenant stores: Check store owner's Raqamiyat platform wallet balance ──
    owner_wallet = None
    owner_cost_amt = Decimal("0.00")
    if order_store and order_store.owner:
        base_cost = getattr(variant, "cost", Decimal("0")) or Decimal("0")
        if base_cost > Decimal("0"):
            total_wholesale_cost = (base_cost * quantity).quantize(Decimal("0.01"))
            if total_wholesale_cost > Decimal("0"):
                from apps.wallets.models import Wallet
                from apps.common.models import Currency
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    owner_wallet = Wallet.all_objects.filter(
                        user=order_store.owner,
                        store__isnull=True
                    ).select_related("currency").first()
                    if not owner_wallet:
                        default_curr = Currency.all_objects.filter(is_default=True).first() or Currency.all_objects.first()
                        owner_wallet = Wallet.all_objects.create(
                            user=order_store.owner,
                            store=None,
                            currency=default_curr,
                            available_balance=Decimal("0.00")
                        )
                if owner_wallet.currency.code != "USD":
                    owner_cost_amt = owner_wallet.currency.from_base(total_wholesale_cost)
                else:
                    owner_cost_amt = total_wholesale_cost
                owner_cost_amt = Decimal(owner_cost_amt).quantize(Decimal("0.01"))

                if owner_wallet.available_balance < owner_cost_amt:
                    raise WholesaleInsufficientBalanceError(
                        owner=order_store.owner,
                        variant_name=f"{variant.product.name} - {variant.name}",
                        required_cost=owner_cost_amt,
                        curr_code=owner_wallet.currency.code,
                        store_name=order_store.name,
                        store_id=order_store.id
                    )

    order_status = Order.Status.COMPLETED if variant.delivery_type == "keys" else Order.Status.PROCESSING
    final_fulfillment = dict(fulfillment_data or {})
    if not final_fulfillment and isinstance(metadata, dict):
        from services.provider.manager import ProviderManager
        final_fulfillment = ProviderManager.sanitize_player_params(metadata)

    api_order_uuid = uuid.uuid4() if (variant.product.is_api_product or variant.api_product_id or getattr(variant.product, 'api_product_id', None)) else None
    api_order_id = None
    if locked_keys:
        final_fulfillment["keys"] = [k.key_code for k in locked_keys]

    order = Order.objects.create(
        customer=customer,
        store=order_store,
        number=next_order_number(),
        status=order_status,
        total_amount=total,
        original_total=subtotal,
        coupon=coupon,
        fulfillment_data=final_fulfillment,
        metadata=metadata or {},
        shipping_name=shipping_name or "",
        shipping_phone=shipping_phone or "",
        shipping_address=shipping_address or "",
        api_order_id=api_order_id,
        api_order_uuid=api_order_uuid,
    )
    OrderItem.objects.create(
        order=order,
        variant=variant,
        quantity=quantity,
        unit_price=price,
        unit_cost=variant.cost,
        total_price=subtotal,
    )

    # ── Mark digital keys as used ─────────────────────────────────────────────
    if locked_keys:
        for key in locked_keys:
            key.is_used  = True
            key.used_by  = customer
            key.used_at  = timezone.now()
            key.order    = order
            key.save(update_fields=["is_used", "used_by", "used_at", "order"])

    # ── Debit customer wallet ─────────────────────────────────────────────────
    debit_wallet(
        wallet.id,
        debit_amount,
        reference=f"order:{order.id}",
        description=f"Order {order.number}",
        created_by=customer,
    )

    # ── Debit store owner's Raqamiyat platform wallet for wholesale cost ──────
    if owner_wallet and owner_cost_amt > Decimal("0"):
        debit_wallet(
            owner_wallet.id,
            owner_cost_amt,
            reference=f"substore_wholesale:{order.id}",
            description=f"تكلفة توريد طلب #{order.number} لمتجر {order_store.name}",
            created_by=order_store.owner,
            source="Raqmiyat Wholesale Fulfillment"
        )

    if locked_keys:
        return order

    is_api_candidate = bool(
        variant.product.is_api_product
        or variant.api_product_id
        or getattr(variant.product, 'api_product_id', None)
        or hasattr(variant, 'provider_mapping')
        or (variant.sku and "PRV-" in variant.sku)
        or (variant.metadata and isinstance(variant.metadata, dict) and variant.metadata.get("remote_id"))
        or (order_store and ProductVariant.all_objects.filter(product__store__isnull=True, name=variant.name, product__name=variant.product.name).exists())
    )
    if is_api_candidate:
        provider = variant.product.api_provider or "alkasr"
        api_order_id = None
        try:
            from services.provider.manager import ProviderManager

            provider_product, profile = resolve_variant_provider_and_product(variant)

            if not provider_product or not profile:
                if order_store:
                    order.status = Order.Status.PROCESSING
                    fulfillment = dict(order.fulfillment_data or {})
                    fulfillment["notes"] = "تم خصم تكلفة التوريد من رصيد المتجر في رقميات بنجاح، وبانتظار التنفيذ."
                    order.fulfillment_data = fulfillment
                    order.save(update_fields=["status", "fulfillment_data", "updated_at"])
                    return order
                else:
                    raise ValueError(f"المنتج غير مربوط بمزود خدمة فعال.")

            if not api_order_uuid:
                api_order_uuid = uuid.uuid4()
                order.api_order_uuid = api_order_uuid
                order.save(update_fields=["api_order_uuid"])

            # Merge customer inputs from fulfillment_data and metadata
            combined_params = dict(order.fulfillment_data or {})
            if isinstance(order.metadata, dict):
                for k, v in order.metadata.items():
                    if k not in combined_params or not combined_params[k]:
                        combined_params[k] = v

            sanitized_params = ProviderManager.sanitize_player_params(combined_params)

            api_resp = ProviderManager.place_order(
                profile=profile,
                local_order=order,
                provider_product=provider_product,
                quantity=quantity,
                player_params=sanitized_params,
                order_uuid=api_order_uuid,
            )
            api_status = api_resp.get("status") or "wait"
            api_order_id = api_resp.get("remote_order_id")
            raw_response = api_resp.get("raw_response") or api_resp

            fulfillment = dict(order.fulfillment_data or {})
            fulfillment.pop("api_order_id", None)
            fulfillment.pop("ملاحظات وبيانات التنفيذ", None)
            fulfillment.update({
                "api_status": api_status,
            })
            order_meta = dict(order.metadata or {})
            order_meta["api_provider"] = provider or getattr(profile, "provider_name", "alkasr")
            order.metadata = order_meta
            order.api_order_id = api_order_id
            order.fulfillment_data = fulfillment
            order.save(update_fields=["api_order_id", "fulfillment_data", "metadata", "updated_at"])

            from apps.orders.provider_status import apply_provider_status
            order = apply_provider_status(
                order,
                api_status,
                raw_response=raw_response,
                actor=customer,
                note_prefix="النظام الآلي",
            )
        except Exception as exc:
            if is_provider_unavailable_error(exc):
                mark_variant_unavailable(variant, reason=str(exc), error_code=getattr(exc, "code", None), provider_product=provider_product)
            from apps.orders.provider_status import apply_provider_status
            order = apply_provider_status(
                order,
                "failed",
                raw_response={
                    "error": str(exc),
                    "msg": str(exc),
                    "code": getattr(exc, "code", None)
                },
                actor=customer,
                note_prefix="النظام الآلي (فشل الإرسال للمزود)",
            )
            order_meta = dict(order.metadata or {})
            order_meta["api_provider"] = provider
            order_meta["api_error"] = str(exc)
            order.metadata = order_meta
            order.save(update_fields=["metadata", "updated_at"])
            try:
                from apps.notifications.services import notify_provider_error
                notify_provider_error(
                    error_code=0,
                    provider_name=provider,
                    product_id=variant.api_product_id,
                    detail=str(exc),
                    store=str(variant.product.store) if variant.product.store else None,
                )
            except Exception:
                pass

    # ── Logs + Invoice ────────────────────────────────────────────────────────
    if variant.product.is_api_product and variant.api_product_id:
        log_note = f"تم إنشاء الطلب وربطه بالـ API (رقم خارجي: {order.api_order_id or 'بانتظار المزود'})."
    elif locked_keys:
        log_note = "تم إنشاء الطلب وتسليم الأكواد تلقائياً."
    else:
        log_note = "تم إنشاء الطلب وخصم المبلغ من المحفظة."

    OrderLog.objects.create(order=order, status=order.status, note=log_note, created_by=customer)
    Invoice.objects.create(
        order=order,
        invoice_number=order.number.replace("ORD", "INV", 1),
        total_amount=total,
    )

    try:
        from apps.notifications.services import notify_staff
        notify_staff(
            title="طلب جديد",
            body=f"طلب جديد رقم {order.number} بقيمة {total} USD من {customer.email}",
            action_url=f"/control/orders/{order.id}/",
            category="admin_new_order",
        )
    except Exception:
        pass

    return order


def create_order(customer, variant_id, quantity=1, fulfillment_data=None,
                 coupon=None, metadata=None,
                 shipping_name=None, shipping_phone=None, shipping_address=None):
    """
    Public order creation entrypoint.
    Executes atomic order creation. If store owner has insufficient wholesale
    balance in Raqamiyat, notifies the store owner outside the rolled-back
    transaction and presents a friendly error message to the customer.
    """
    try:
        return _create_order_atomic(
            customer=customer,
            variant_id=variant_id,
            quantity=quantity,
            fulfillment_data=fulfillment_data,
            coupon=coupon,
            metadata=metadata,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_address=shipping_address,
        )
    except WholesaleInsufficientBalanceError as e:
        try:
            from apps.notifications.services import notify_user
            from apps.notifications.models import Notification
            notify_user(
                user=e.owner,
                title="⚠️ رصيد الجملة في رقميات غير كافٍ لإتمام طلب عميل",
                body=(
                    f"تعذر إكمال طلب للعميل على باقة '{e.variant_name}' "
                    f"لعدم توفر رصيد كافٍ في محفظتك بمنصة رقميات "
                    f"(المطلوب: {e.required_cost} {e.curr_code}). "
                    f"يرجى شحن محفظتك في رقميات لتتمكن من مواصلة تزويد وتوريد طلبات العملاء تلقائياً."
                ),
                action_url="/dashboard/wallet/",
                category="financial",
                priority=Notification.Priority.HIGH,
                metadata={
                    "store_id": str(e.store_id) if e.store_id else None,
                    "store_name": e.store_name,
                    "required_cost": str(e.required_cost),
                    "currency": e.curr_code,
                },
            )
        except Exception as notif_err:
            logger.warning("Failed to notify store owner about wholesale insufficient balance: %s", notif_err)
        raise ValueError("لم يتم إكمال الطلب، يرجى التواصل مع دعم المتجر.")


def create_pending_gateway_order(
    customer,
    variant_id,
    quantity=1,
    fulfillment_data=None,
    coupon=None,
    metadata=None,
    shipping_name=None,
    shipping_phone=None,
    shipping_address=None,
    gateway_code="paymera",
):
    """
    Creates an Order in PENDING status for direct payment through an electronic gateway.
    Does NOT debit the user's wallet.
    """
    if customer.restriction_purchases:
        raise ValueError("حسابك مقيد من عمليات الشراء.")

    quantity = int(quantity)
    if quantity < 1:
        raise ValueError("الكمية يجب أن تكون 1 على الأقل.")

    # Fetch variant
    try:
        variant = (
            ProductVariant.objects
            .select_related("product")
            .get(id=variant_id, is_active=True, is_temporarily_disabled=False, product__is_active=True)
        )
    except ProductVariant.DoesNotExist:
        raise ValueError("هذه الباقة أو المنتج غير متوفر حالياً.")

    product = variant.product
    if product.is_out_of_stock or not product.is_active:
        raise ValueError("هذا المنتج غير متوفر حالياً (نفد المخزون).")

    prov_prod, _ = resolve_variant_provider_and_product(variant)
    if prov_prod and (not prov_prod.is_active or not prov_prod.local_is_active):
        mark_variant_unavailable(variant, reason="Provider product is inactive", provider_product=prov_prod)
        raise ValueError("هذه الباقة غير متوفرة حالياً لدى مزود الخدمة.")


    # Read qty metadata
    meta = variant.metadata if isinstance(variant.metadata, dict) else {}
    qty_type = meta.get("qty_type")
    qty_list = meta.get("qty_list", [])
    qty_min = _safe_int(meta.get("qty_min"), 1)
    qty_max = _safe_int(meta.get("qty_max"), 999_999_999)

    if qty_type == "fixed":
        quantity = 1
    elif qty_type == "list":
        if str(quantity) not in [str(x) for x in qty_list]:
            raise ValueError(
                f"الكمية المسموح بها لهذه الباقة هي إحدى القيم التالية فقط: {', '.join(str(x) for x in qty_list)}"
            )
    elif qty_type == "range":
        if quantity < qty_min:
            raise ValueError(f"الحد الأدنى المسموح به للكمية هو {qty_min:,}")
        if quantity > qty_max:
            raise ValueError(f"الحد الأقصى المسموح به للكمية هو {qty_max:,}")

    # Inventory check
    product = variant.product
    if product.track_inventory:
        if product.quantity < quantity:
            raise ValueError(
                f"الكمية المطلوبة ({quantity}) غير متوفرة. "
                f"الكمية المتوفرة حالياً: {product.quantity}"
            )

    # Shipping validation for physical products
    if (
        product.product_type == "physical"
        and not (product.form_schema or {}).get("fields")
    ):
        if not (shipping_name and shipping_phone and shipping_address):
            raise ValueError("جميع حقول الشحن والتوصيل مطلوبة للطلب المادي.")

    # Digital Keys Availability check
    order_store = getattr(variant.product, "store", None)
    if not order_store:
        from apps.common.tenant_utils import get_current_store
        order_store = get_current_store()

    if variant.delivery_type == "keys":
        key_count = ProductKey.objects.filter(variant=variant, is_used=False).count()
        if key_count < quantity and order_store:
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                global_var = ProductVariant.all_objects.filter(
                    product__store__isnull=True,
                    name=variant.name,
                    product__name=variant.product.name
                ).first()
                if global_var:
                    key_count = ProductKey.objects.filter(variant=global_var, is_used=False).count()
        if key_count < quantity:
            raise ValueError("المخزون الرقمي غير كافٍ حالياً لتلبية هذا الطلب.")

    price = variant.get_price_for_user(customer)
    subtotal = calculate_variant_subtotal(variant, customer, quantity)

    discount = Decimal("0.00")
    if coupon:
        discount = validate_coupon(coupon, customer, variant, subtotal=subtotal)
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    total = max(subtotal - discount, Decimal("0.00"))

    order_meta = dict(metadata or {})
    order_meta["payment_gateway"] = gateway_code
    order_meta["is_direct_gateway_purchase"] = True

    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            store=order_store,
            number=next_order_number(),
            status=Order.Status.PENDING,
            total_amount=total,
            original_total=subtotal,
            coupon=coupon,
            fulfillment_data=dict(fulfillment_data or {}),
            metadata=order_meta,
            shipping_name=shipping_name or "",
            shipping_phone=shipping_phone or "",
            shipping_address=shipping_address or "",
        )
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=quantity,
            unit_price=price,
            unit_cost=variant.cost,
            total_price=subtotal,
        )
        OrderLog.objects.create(
            order=order,
            status=Order.Status.PENDING,
            note=f"تم إنشاء الطلب بانتظار إتمام الدفع عبر بوابة {gateway_code}.",
            created_by=customer,
        )

    return order


def finalize_paid_gateway_order(order, gateway_data=None):
    """
    Finalizes an Order after payment gateway confirmation.
    Idempotent: skips if status is already completed or processing.
    STRICT SECURITY: Refuses to fulfill or finalize any order without confirmed 'A' (ACCEPTED) gateway status.
    """
    gw_status = (gateway_data.get("status") if isinstance(gateway_data, dict) else None)
    if not gw_status or str(gw_status).strip().upper() != "A":
        logger.error(
            f"SECURITY: Refusing to finalize order {order.id} without confirmed ACCEPTED ('A') gateway status. "
            f"Received gateway_data: {gateway_data}"
        )
        return order

    with transaction.atomic():
        from apps.common.tenant_utils import bypass_tenant_filter
        with bypass_tenant_filter():
            locked_order = Order.all_objects.select_for_update().get(id=order.id)
        if locked_order.status not in (Order.Status.PENDING,):
            logger.info(f"Order {order.id} is already in status {locked_order.status}, skipping finalize.")
            return locked_order

        meta = dict(locked_order.metadata or {})
        meta["gateway_payment_confirmed"] = True
        meta["is_paid"] = True
        meta["gateway_charge_amount"] = str(locked_order.total_amount)
        if isinstance(gateway_data, dict):
            meta["gateway_payment_status"] = gateway_data.get("status")
            if gateway_data.get("id"):
                meta["gateway_payment_id"] = str(gateway_data.get("id"))
            if gateway_data.get("rrn"):
                meta["gateway_rrn"] = str(gateway_data.get("rrn"))
        locked_order.metadata = meta

        item = locked_order.items.select_related("variant", "variant__product").first()
        if not item or not item.variant:
            locked_order.status = Order.Status.PROCESSING
            locked_order.save(update_fields=["status", "metadata", "updated_at"])
            return locked_order

        variant = item.variant
        quantity = item.quantity
        order_store = locked_order.store
        customer = locked_order.customer

        # 1. Direct gateway order for tenant store:
        # The customer paid retail directly via gateway (Raqamiyat collected total_amount).
        # Calculate profit parameters (credited after fulfillment verification)
        owner_wallet = None
        profit_amt = Decimal("0.00")
        if order_store and order_store.owner:
            base_cost = getattr(variant, "cost", Decimal("0")) or Decimal("0")
            total_wholesale_cost = (base_cost * quantity).quantize(Decimal("0.01"))
            profit_usd = (locked_order.total_amount - total_wholesale_cost).quantize(Decimal("0.01"))

            from apps.wallets.models import Wallet
            from apps.common.models import Currency
            from apps.common.tenant_utils import bypass_tenant_filter

            with bypass_tenant_filter():
                owner_wallet = Wallet.all_objects.filter(
                    user=order_store.owner,
                    store__isnull=True
                ).select_related("currency").first()
                if not owner_wallet:
                    default_curr = Currency.all_objects.filter(is_default=True).first() or Currency.all_objects.first()
                    owner_wallet = Wallet.all_objects.create(
                        user=order_store.owner,
                        store=None,
                        currency=default_curr,
                        available_balance=Decimal("0.00")
                    )

            if profit_usd > Decimal("0.00"):
                if owner_wallet.currency.code != "USD":
                    profit_amt = owner_wallet.currency.from_base(profit_usd)
                else:
                    profit_amt = profit_usd
                profit_amt = Decimal(profit_amt).quantize(Decimal("0.01"))

        # 2. Fulfillment
        locked_keys = []
        if variant.delivery_type == "keys":
            key_ids = list(
                ProductKey.objects
                .filter(variant=variant, is_used=False)
                .values_list("id", flat=True)[:quantity]
            )
            if len(key_ids) < quantity and order_store:
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    global_var = ProductVariant.all_objects.filter(
                        product__store__isnull=True,
                        name=variant.name,
                        product__name=variant.product.name
                    ).first()
                    if global_var:
                        key_ids = list(
                            ProductKey.objects
                            .filter(variant=global_var, is_used=False)
                            .values_list("id", flat=True)[:quantity]
                        )
            if key_ids:
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    locked_keys = list(
                        ProductKey.objects.filter(id__in=key_ids, is_used=False).select_for_update()
                    )
            
            if len(locked_keys) >= quantity:
                for k in locked_keys:
                    k.is_used = True
                    k.used_by = customer
                    k.used_at = timezone.now()
                    k.order = locked_order
                    k.save(update_fields=["is_used", "used_by", "used_at", "order"])
                
                fulfillment = dict(locked_order.fulfillment_data or {})
                fulfillment["keys"] = [k.key_code for k in locked_keys]
                locked_order.fulfillment_data = fulfillment
                locked_order.status = Order.Status.COMPLETED
            else:
                from apps.orders.provider_status import apply_provider_status
                err_msg = "نفدت الأكواد من المخزون حالياً."
                fulfillment = dict(locked_order.fulfillment_data or {})
                fulfillment["سبب الإلغاء من السيرفر"] = err_msg
                locked_order.fulfillment_data = fulfillment
                locked_order = apply_provider_status(
                    locked_order,
                    "reject",
                    raw_response={"error": err_msg, "reason": err_msg},
                    actor=customer,
                    note_prefix="النظام الآلي (دفع مباشر - بيميرا)",
                )

        else:
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                provider = (
                    getattr(variant, "api_provider", None)
                    or getattr(variant.product, "api_provider", None)
                    or "alkasr"
                )
                try:
                    from services.provider.manager import ProviderManager

                    provider_product, profile = resolve_variant_provider_and_product(variant)

                    if provider_product and profile and provider_product.is_active and provider_product.local_is_active:
                        locked_order.status = Order.Status.PROCESSING
                        api_order_uuid = locked_order.api_order_uuid or uuid.uuid4()
                        locked_order.api_order_uuid = api_order_uuid

                        # Merge player parameters from both fulfillment_data and metadata
                        combined_params = dict(locked_order.fulfillment_data or {})
                        if isinstance(locked_order.metadata, dict):
                            for k, v in locked_order.metadata.items():
                                if k not in combined_params or not combined_params[k]:
                                    combined_params[k] = v

                        sanitized_params = ProviderManager.sanitize_player_params(combined_params)

                        api_resp = ProviderManager.place_order(
                            profile=profile,
                            local_order=locked_order,
                            provider_product=provider_product,
                            quantity=quantity,
                            player_params=sanitized_params,
                            order_uuid=api_order_uuid,
                        )
                        api_status = api_resp.get("status") or "wait"
                        api_order_id = api_resp.get("remote_order_id")
                        raw_response = api_resp.get("raw_response") or api_resp

                        fulfillment = dict(locked_order.fulfillment_data or {})
                        fulfillment.pop("api_order_id", None)
                        fulfillment.pop("ملاحظات وبيانات التنفيذ", None)
                        fulfillment["api_status"] = api_status
                        locked_order.api_order_id = api_order_id
                        locked_order.fulfillment_data = fulfillment

                        order_meta = dict(locked_order.metadata or {})
                        order_meta["api_provider"] = provider or getattr(profile, "provider_name", "alkasr")
                        locked_order.metadata = order_meta

                        locked_order.save(update_fields=["api_order_id", "fulfillment_data", "metadata", "api_order_uuid", "updated_at"])

                        from apps.orders.provider_status import apply_provider_status
                        locked_order = apply_provider_status(
                            locked_order,
                            api_status,
                            raw_response=raw_response,
                            actor=customer,
                            note_prefix="النظام الآلي (دفع مباشر - بيميرا)",
                        )
                    else:
                        err_msg = "المنتج غير متوفر حالياً لدى المزود الخارجي."
                        mark_variant_unavailable(variant, reason=err_msg, provider_product=None)
                        from apps.orders.provider_status import apply_provider_status
                        fulfillment = dict(locked_order.fulfillment_data or {})
                        fulfillment["سبب الإلغاء من السيرفر"] = err_msg
                        locked_order.fulfillment_data = fulfillment
                        order_meta = dict(locked_order.metadata or {})
                        order_meta["api_provider"] = provider
                        order_meta["api_error"] = err_msg
                        locked_order.metadata = order_meta
                        locked_order = apply_provider_status(
                            locked_order,
                            "reject",
                            raw_response={"error": err_msg, "reason": err_msg},
                            actor=customer,
                            note_prefix="النظام الآلي (دفع مباشر - بيميرا)",
                        )
                except Exception as api_exc:
                    logger.error(f"Error placing API order for paid order {locked_order.id}: {api_exc}", exc_info=True)
                    if is_provider_unavailable_error(api_exc):
                        mark_variant_unavailable(variant, reason=str(api_exc), error_code=getattr(api_exc, "code", None), provider_product=provider_product)
                    from apps.orders.provider_status import apply_provider_status
                    err_msg = f"تعذر تنفيذ الطلب لدى المزود: {str(api_exc)}"
                    fulfillment = dict(locked_order.fulfillment_data or {})
                    fulfillment["سبب الإلغاء من السيرفر"] = err_msg
                    locked_order.fulfillment_data = fulfillment
                    order_meta = dict(locked_order.metadata or {})
                    order_meta["api_provider"] = provider
                    order_meta["api_error"] = str(api_exc)
                    locked_order.metadata = order_meta
                    locked_order = apply_provider_status(
                        locked_order,
                        "reject",
                        raw_response={
                            "error": str(api_exc),
                            "reason": str(api_exc),
                            "code": getattr(api_exc, "code", None)
                        },
                        actor=customer,
                        note_prefix="النظام الآلي (دفع مباشر - بيميرا)",
                    )

        # 3. Credit merchant profit if fulfillment was NOT cancelled
        if locked_order.status != Order.Status.CANCELLED and owner_wallet and profit_amt > Decimal("0.00"):
            from apps.wallets.services import credit_wallet
            credit_wallet(
                owner_wallet.id,
                profit_amt,
                reference=f"substore_profit:{locked_order.id}",
                description=f"أرباح طلب #{locked_order.number} لمتجر {order_store.name} (دفع مباشر عبر بيميرا)",
                created_by=customer,
            )
            meta = dict(locked_order.metadata or {})
            meta["substore_profit_amount"] = str(profit_amt)
            meta["substore_owner_wallet_id"] = str(owner_wallet.id)
            locked_order.metadata = meta
            OrderLog.objects.create(
                order=locked_order,
                status=locked_order.status,
                note=f"تم إيداع أرباح المتجر بقيمة {profit_amt} {owner_wallet.currency.code} في محفظة صاحب المتجر ({order_store.owner.email}).",
                created_by=None,
            )

        # 4. Invoice
        Invoice.objects.get_or_create(
            order=locked_order,
            defaults={
                "invoice_number": locked_order.number.replace("ORD", "INV", 1),
                "total_amount": locked_order.total_amount,
            }
        )

        # 5. OrderLog
        gw_label = "بوابة الدفع الإلكتروني"
        if gateway_data and isinstance(gateway_data, dict):
            rrn = gateway_data.get("rrn")
            if rrn:
                gw_label += f" (RRN: {rrn})"
        OrderLog.objects.create(
            order=locked_order,
            status=locked_order.status,
            note=f"تم تأكيد السداد بنجاح عبر {gw_label}.",
            created_by=customer,
        )

        locked_order.save()

        # 6. Notifications
        try:
            from apps.notifications.services import notify_staff, notify_user
            notify_staff(
                title="طلب مدفوع إلكترونياً",
                body=f"تم سداد الطلب رقم {locked_order.number} بقيمة {locked_order.total_amount} USD إلكترونياً من {customer.email} (الحالة: {locked_order.status})",
                action_url=f"/control/orders/{locked_order.id}/",
                category="admin_new_order",
            )
            if locked_order.status == Order.Status.CANCELLED:
                notify_user(
                    user=customer,
                    title="تعذر توفر المنتج - تم استرداد المبلغ للمحفظة",
                    body=f"نعتذر منك، المنتج المطلوب في طلبك رقم {locked_order.number} غير متوفر حالياً. تم استرداد كامل المبلغ إلى محفظتك بنجاح.",
                    action_url=f"/dashboard/orders/{locked_order.id}/",
                    category="order_update",
                    priority="high"
                )
            else:
                notify_user(
                    user=customer,
                    title="تم تأكيد طلبك بنجاح",
                    body=f"تم استلام دفعتك للطلب رقم {locked_order.number} بنجاح وجاري تنفيذه.",
                    action_url=f"/dashboard/orders/{locked_order.id}/",
                    category="order_update",
                    priority="high"
                )
        except Exception:
            pass

        return locked_order


def process_order_refund_to_wallet(order, actor=None, old_status=None, source="admin", reason=None):
    """
    Safely refunds order amount to customer's wallet IF AND ONLY IF the order was actually paid
    and has not already been refunded.
    
    Returns (refunded: bool, message: str)
    """
    from apps.wallets.services import get_or_create_wallet, credit_wallet

    # 1. Check if already refunded
    ff = dict(order.fulfillment_data or {})
    meta = dict(order.metadata or {})
    if bool(ff.get("api_refunded") or meta.get("wallet_refunded")):
        return False, "تم استرداد مبلغ هذا الطلب مسبقاً، لن يتم تكرار الاسترداد."

    # 2. Check if direct gateway order and payment never completed
    is_direct_gw = bool(
        meta.get("is_direct_gateway_purchase")
        or meta.get("direct_gateway_purchase")
        or meta.get("payment_provider") == "paymera"
        or meta.get("gateway_payment_id")
        or meta.get("paymera_payment_id")
    )
    gw_confirmed = bool(meta.get("gateway_payment_confirmed") or meta.get("is_paid"))
    if is_direct_gw and not gw_confirmed:
        try:
            OrderLog.objects.create(
                order=order,
                status=order.status,
                note="تم إلغاء الطلب دون استرداد رصيد لعدم إتمام الدفع عبر بوابة الدفع (طلب غير مسدد).",
                created_by=actor,
            )
        except Exception:
            pass
        return False, "تم إلغاء الطلب (لم يتم تحويل رصيد للمحفظة لأن الطلب غير مسدد أصلاً عبر بوابة الدفع)."

    # 3. Direct gateway purchases must NOT be refunded to internal wallet unless explicitly requested as admin override
    if is_direct_gw and source != "explicit_wallet_choice":
        try:
            OrderLog.objects.create(
                order=order,
                status=order.status,
                note="لم يتم إيداع رصيد بمحفظة المنصة لأن الدفع تم مباشرة عبر البطاقة البنكية (بوابة الدفع).",
                created_by=actor,
            )
        except Exception:
            pass
        return False, "تم تحديث حالة الطلب دون إضافة رصيد للمحفظة نظراً لأن الدفع كان مباشراً عبر بوابة الدفع (البطاقة البنكية)."

    # 4. Check if order was cancelled from PENDING without confirmed gateway payment
    if old_status == Order.Status.PENDING and not gw_confirmed:
        try:
            OrderLog.objects.create(
                order=order,
                status=order.status,
                note="تم إلغاء الطلب دون استرداد رصيد لأن الطلب كان قيد الانتظار وغير مسدد.",
                created_by=actor,
            )
        except Exception:
            pass
        return False, "تم إلغاء الطلب (لم يتم تحويل رصيد للمحفظة لأن الطلب كان قيد الانتظار ولم يتم تحصيل قيمته)."

    # 5. Check total amount
    if order.total_amount <= Decimal("0.00"):
        return False, "مبلغ الطلب صفر، لا يوجد رصيد للاسترداد."

    # 6. Execute refund
    wallet = get_or_create_wallet(order.customer)
    refund_amount = order.total_amount
    if wallet.currency and wallet.currency.code != "USD":
        refund_amount = wallet.currency.from_base(order.total_amount)
    refund_amount = Decimal(refund_amount).quantize(Decimal("0.01"))

    credit_wallet(
        wallet_id=wallet.id,
        amount=refund_amount,
        reference=f"refund:{order.id}",
        description=f"استرداد مبلغ الطلب رقم #{order.number}",
        created_by=actor,
        source=source,
        reason=reason or f"استرداد رصيد لإلغاء/استرداد الطلب #{order.number}",
        metadata={"order_id": str(order.id), "order_number": order.number}
    )

    ff["api_refunded"] = True
    order.fulfillment_data = ff

    meta["wallet_refunded"] = True
    meta["wallet_refunded_amount"] = str(refund_amount)
    meta["wallet_refunded_at"] = timezone.now().isoformat()
    if actor and getattr(actor, "username", None):
        meta["wallet_refunded_by"] = actor.username
    order.metadata = meta

    order.save(update_fields=["fulfillment_data", "metadata", "updated_at"])

    OrderLog.objects.create(
        order=order,
        status=order.status,
        note=f"تم استرداد مبلغ {refund_amount} {wallet.currency.code} إلى محفظة العميل بنجاح.",
        created_by=actor,
    )
    return True, f"تم استرداد مبلغ {refund_amount} {wallet.currency.code} إلى محفظة العميل بنجاح."


def process_order_refund_to_paymera(order, actor=None, reason=None, otp: Optional[str] = None) -> tuple[bool, str]:
    """
    Cancels an order and executes a real-time Reversal (Refund) back to the customer's payment card
    via Paymera eGate v4.0 API (POST /api/cancel-payment).
    Supports optional OTP verification if required by Paymera.
    
    Returns (success: bool, message: str)
    """
    from datetime import timedelta
    from apps.notifications.services import notify_user, notify_staff
    from apps.payments.gateways import gateway_for
    from apps.payments.paymera import PaymeraError
    from apps.wallets.services import debit_wallet

    meta = dict(order.metadata or {})
    ff = dict(order.fulfillment_data or {})

    # 1. Validation: check if already refunded
    if meta.get("paymera_refunded"):
        return False, "تم استرداد هذا الطلب بالفعل إلى البطاقة البنكية مسبقاً عبر بيميرا."
    if meta.get("wallet_refunded") or ff.get("api_refunded"):
        return False, "تم استرداد هذا الطلب مسبقاً إلى المحفظة الداخلية، لا يمكن تكرار الاسترداد إلى البطاقة."

    # 2. Extract gateway payment ID
    payment_id = meta.get("gateway_payment_id") or meta.get("paymera_payment_id")
    if not payment_id:
        return False, "لا يوجد معرف دفعة بيميرا (Payment ID) مسجل لهذا الطلب."

    # 3. Call Paymera Cancel / Reversal API
    try:
        gw = gateway_for("paymera")
        client = gw.get_client()
        logger.info(f"Initiating Paymera reversal for order #{order.number}, payment_id={payment_id}, has_otp={bool(otp)}")
        reversal_res = client.cancel_payment(payment_id=payment_id, lang="ar", otp=otp)
    except PaymeraError as exc:
        err_msg = str(exc)
        logger.warning(f"Paymera reversal failed for order #{order.number}: {err_msg}")
        OrderLog.objects.create(
            order=order,
            status=order.status,
            note=f"فشل طلب استرداد الأموال إلى البطاقة عبر بيميرا: {err_msg}",
            created_by=actor,
        )
        return False, f"فشلت عملية استرداد الأموال عبر بيميرا: {err_msg}"
    except Exception as exc:
        logger.exception(f"Unexpected error during Paymera reversal for order #{order.number}: {exc}")
        return False, f"حدث خطأ غير متوقع أثناء الاتصال ببوابة بيميرا: {exc}"

    # 4. If reversal succeeded, update order and balance records atomically
    with transaction.atomic():
        old_status = order.status
        new_status = Order.Status.CANCELLED if old_status == Order.Status.PENDING else Order.Status.REFUNDED
        order.status = new_status
        order.admin_note = (order.admin_note or "") + f"\n[استرداد عبر بيميرا]: تم إلغاء/استرداد المبلغ للبطاقة في {timezone.now().strftime('%Y-%m-%d %H:%M')}. السبب: {reason or 'طلب استرداد'}"

        meta["paymera_refunded"] = True
        meta["paymera_refund_timestamp"] = timezone.now().isoformat()
        meta["paymera_refund_actor"] = getattr(actor, "email", str(actor)) if actor else "نظام"
        meta["paymera_refund_reason"] = reason or "استرداد للبطاقة البنكية عبر بيميرا"
        meta["paymera_refund_raw"] = reversal_res
        order.metadata = meta

        # 5. Reverse store owner profit if it was credited earlier
        profit_amt_str = meta.get("substore_profit_amount")
        owner_wallet_id = meta.get("substore_owner_wallet_id")
        if profit_amt_str and owner_wallet_id:
            try:
                profit_amt = Decimal(profit_amt_str)
                if profit_amt > 0:
                    debit_wallet(
                        wallet_id=owner_wallet_id,
                        amount=profit_amt,
                        reference=f"reversal_substore_profit:{order.id}",
                        description=f"خصم أرباح طلب مسترد #{order.number} (استرداد بيميرا للبطاقة)",
                        created_by=actor,
                        source="refund_reversal"
                    )
            except Exception as w_exc:
                logger.error(f"Failed to reverse substore owner profit for order #{order.number}: {w_exc}")

        order.save(update_fields=["status", "admin_note", "metadata", "updated_at"])

        OrderLog.objects.create(
            order=order,
            status=new_status,
            note=f"تم إلغاء/استرداد كامل قيمة الطلب ({order.total_amount} USD) بنجاح إلى البطاقة البنكية للعميل عبر بوابة بيميرا. السبب: {reason or 'طلب استرداد'}.",
            created_by=actor,
        )

    # 6. Notifications
    try:
        notify_user(
            user=order.customer,
            title="تم استرداد المبلغ إلى بطاقتك البنكية",
            body=f"تم استرداد كامل قيمة طلبك رقم #{order.number} إلى بطاقتك البنكية عبر بيميرا بنجاح. قد يستغرق ظهور الرصيد في حسابك البنكي بعض الوقت بحسب سياسة البنك المصدر للبطاقة.",
            action_url=f"/dashboard/orders/{order.id}/",
            category="financial",
            priority="high",
        )
        notify_staff(
            title="استرداد بنكي ناجح عبر بيميرا",
            body=f"تم استرداد الطلب رقم #{order.number} بنجاح إلى بطاقة العميل {getattr(order.customer, 'email', '')} عبر بوابة بيميرا.",
            action_url=f"/control/orders/{order.id}/",
            category="financial",
        )
    except Exception:
        pass

    return True, "تمت عملية إلغاء واسترداد المبلغ بنجاح إلى البطاقة البنكية للعميل عبر بوابة بيميرا."


def auto_cancel_expired_pending_orders(max_minutes: int = 5) -> dict:
    """
    Scans and automatically cancels pending orders that have remained uncompleted for more than max_minutes.
    Before cancellation, checks Paymera status if a gateway payment was initiated, ensuring
    no completed payments are incorrectly cancelled. Also terminates pending Paymera session.
    
    Returns a dict with statistics: {"checked": int, "cancelled": int, "finalized": int, "errors": int}
    """
    from datetime import timedelta
    from apps.payments.gateways import gateway_for
    from apps.payments.paymera import PaymeraClient, PaymeraError
    from apps.common.tenant_utils import bypass_tenant_filter

    cutoff_time = timezone.now() - timedelta(minutes=max_minutes)
    stats = {"checked": 0, "cancelled": 0, "finalized": 0, "errors": 0}

    with bypass_tenant_filter():
        expired_pending_orders = list(
            Order.all_objects.filter(
                status=Order.Status.PENDING,
                created_at__lte=cutoff_time
            ).order_by("created_at")[:100]
        )

    if not expired_pending_orders:
        return stats

    gw = None
    client = None

    for order in expired_pending_orders:
        stats["checked"] += 1
        meta = dict(order.metadata or {})
        payment_id = meta.get("gateway_payment_id") or meta.get("paymera_payment_id")

        try:
            # If the order is linked to a gateway payment, query Paymera first
            if payment_id:
                if not client:
                    try:
                        gw = gateway_for("paymera")
                        client = gw.get_client()
                    except Exception as gw_init_err:
                        logger.error(f"Cannot initialize Paymera client for pending check: {gw_init_err}")

                if client:
                    try:
                        status_res = client.get_payment_status(payment_id)
                        gw_status = status_res.get("status")
                        
                        # If payment was actually completed right before timeout, finalize it!
                        if gw_status == PaymeraClient.STATUS_ACCEPTED:
                            logger.info(f"Order #{order.number} was accepted on Paymera, finalizing instead of cancelling.")
                            finalize_paid_gateway_order(order, status_res)
                            stats["finalized"] += 1
                            continue
                    except PaymeraError as p_err:
                        logger.warning(f"Paymera status check error for order #{order.number} ({payment_id}): {p_err}")

            # Otherwise, cancel the expired pending order
            with transaction.atomic():
                with bypass_tenant_filter():
                    locked_order = Order.all_objects.select_for_update().get(pk=order.pk)
                    if locked_order.status != Order.Status.PENDING:
                        continue
                    locked_order.status = Order.Status.CANCELLED
                    locked_order.admin_note = (locked_order.admin_note or "") + f"\nتم إلغاء الطلب تلقائياً لتجاوز مهلة السداد المحددة ({max_minutes} دقائق دون إتمام الدفع)."
                    locked_order.save(update_fields=["status", "admin_note", "updated_at"])

                    OrderLog.objects.create(
                        order=locked_order,
                        status=Order.Status.CANCELLED,
                        note=f"تم إلغاء الطلب تلقائياً لانتهاء مهلة السداد ({max_minutes} دقائق دون إتمام عملية الدفع).",
                        created_by=None,
                    )
                    stats["cancelled"] += 1
                    logger.info(f"Auto-cancelled expired pending order #{locked_order.number} (age > {max_minutes}m).")

            # Try to cancel the gateway payment session on Paymera as well
            if client and payment_id:
                try:
                    client.cancel_payment(payment_id=payment_id, lang="ar")
                except Exception as cancel_exc:
                    logger.info(f"Auto-cancel gateway call note for order #{order.number}: {cancel_exc}")

        except Exception as exc:
            stats["errors"] += 1
            logger.error(f"Error auto-cancelling pending order #{order.number}: {exc}")

    return stats


