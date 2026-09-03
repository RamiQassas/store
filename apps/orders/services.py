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

import re
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

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

    Provider list quantities are selectable denominations/options, not a
    multiplier. Range quantities are the only API quantity type priced per unit.
    """
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        qty = 1
    qty = max(qty, 1)

    meta = variant.metadata if isinstance(variant.metadata, dict) else {}
    qty_type = meta.get("qty_type", "fixed")
    is_per_mille = meta.get("is_per_mille", False)
    unit_price = variant.get_price_for_user(user)

    return unit_price * Decimal(qty)


# ---------------------------------------------------------------------------
# Coupon validation
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


# ---------------------------------------------------------------------------
# Main order creation
# ---------------------------------------------------------------------------

@transaction.atomic
def create_order(customer, variant_id, quantity=1, fulfillment_data=None,
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
    variant = (
        ProductVariant.objects
        .select_related("product")
        .select_for_update()
        .get(id=variant_id, is_active=True, product__is_active=True)
    )

    # ── Read qty metadata stored during sync ─────────────────────────────────
    meta             = variant.metadata if isinstance(variant.metadata, dict) else {}
    qty_type         = meta.get("qty_type", "fixed")
    qty_list         = meta.get("qty_list", [])
    qty_min          = _safe_int(meta.get("qty_min"), 1)
    qty_max          = _safe_int(meta.get("qty_max"), 999_999_999)
    api_product_type = meta.get("product_type", "package")   # "amount" or "package"

    # ── Quantity validation (mirrors API rules) ───────────────────────────────
    if qty_type == "fixed":
        # null qty_values in API → must send qty=1
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
            raise ValueError("جميع حقول الشحن مطلوبة للمنتجات المادية.")

    # ── Auto-delivery keys (digital codes stored locally) ─────────────────────
    locked_keys = []
    if variant.delivery_type == "keys":
        key_ids = list(
            ProductKey.objects
            .filter(variant=variant, is_used=False)
            .values_list("id", flat=True)[:quantity]
        )
        if len(key_ids) < quantity:
            raise ValueError("المخزون غير كافٍ لتلبية الكمية المطلوبة.")
        locked_keys = list(
            ProductKey.objects.filter(id__in=key_ids).select_for_update()
        )
        if len(locked_keys) < quantity:
            raise ValueError("المخزون غير كافٍ لتلبية الكمية المطلوبة.")

    # ── Price calculation ─────────────────────────────────────────────────────
    price    = variant.get_price_for_user(customer)
    subtotal = calculate_variant_subtotal(variant, customer, quantity)

    # ── Coupon discount ───────────────────────────────────────────────────────
    discount = Decimal("0.00")
    if coupon:
        discount = validate_coupon(coupon, customer, variant, subtotal=subtotal)
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    total = max(subtotal - discount, Decimal("0.00"))

    order_status = Order.Status.COMPLETED if variant.delivery_type == "keys" else Order.Status.PROCESSING
    final_fulfillment = dict(fulfillment_data or {})
    api_order_uuid = uuid.uuid4() if (variant.product.is_api_product or variant.api_product_id or getattr(variant.product, 'api_product_id', None)) else None
    api_order_id = None
    if locked_keys:
        final_fulfillment["keys"] = [k.key_code for k in locked_keys]

    order = Order.objects.create(
        customer=customer,
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

    # ── Debit wallet ──────────────────────────────────────────────────────────
    wallet = get_or_create_wallet(customer)
    debit_amount = total
    if wallet.currency.code != "USD":
        debit_amount = wallet.currency.from_base(total)
    debit_wallet(
        wallet.id,
        debit_amount,
        reference=f"order:{order.id}",
        description=f"Order {order.number}",
        created_by=customer,
    )

    if variant.product.is_api_product or variant.api_product_id or getattr(variant.product, 'api_product_id', None):
        provider = variant.product.api_provider or "alkasr"
        api_order_id = None
        try:
            from services.provider.manager import ProviderManager
            from apps.providers.models import ProviderMapping, ProviderProduct
            
            provider_product = None
            profile = None
            
            mapping = getattr(variant, "provider_mapping", None)
            if not mapping or not mapping.provider_product:
                mapping = ProviderMapping.objects.filter(local_variant=variant).select_related("provider_product__profile").first()
            
            if mapping and mapping.provider_product:
                provider_product = mapping.provider_product
                profile = provider_product.profile
            elif variant.metadata and isinstance(variant.metadata, dict) and variant.metadata.get("remote_id"):
                provider_product = ProviderProduct.objects.filter(remote_id=str(variant.metadata["remote_id"])).select_related("profile").first()
                if provider_product:
                    profile = provider_product.profile
            elif variant.sku and "PRV-" in variant.sku:
                rem_id = variant.sku.split("-")[-1]
                provider_product = ProviderProduct.objects.filter(remote_id=rem_id).select_related("profile").first()
                if provider_product:
                    profile = provider_product.profile
            elif variant.api_product_id:
                provider_product = ProviderProduct.objects.filter(remote_id=variant.api_product_id).select_related("profile").first()
                if provider_product:
                    profile = provider_product.profile
            elif getattr(variant.product, 'api_product_id', None):
                provider_product = ProviderProduct.objects.filter(remote_id=variant.product.api_product_id).select_related("profile").first()
                if provider_product:
                    profile = provider_product.profile
            
            if not provider_product or not profile:
                raise ValueError(f"المنتج غير مربوط بمزود خدمة فعال.")

            if not api_order_uuid:
                api_order_uuid = uuid.uuid4()
                order.api_order_uuid = api_order_uuid
                order.save(update_fields=["api_order_uuid"])

            api_resp = ProviderManager.place_order(
                profile=profile,
                local_order=order,
                provider_product=provider_product,
                quantity=quantity,
                player_params=metadata or {},
                order_uuid=api_order_uuid,
            )
            api_status = api_resp.get("status") or "wait"
            api_order_id = api_resp.get("remote_order_id")
            raw_response = api_resp.get("raw_response") or api_resp

            fulfillment = dict(order.fulfillment_data or {})
            fulfillment.update({
                "api_order_id": api_order_id,
                "api_status": api_status,
            })
            order_meta = dict(order.metadata or {})
            order_meta["api_provider"] = provider
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
            fulfillment = dict(order.fulfillment_data or {})
            fulfillment.update({
                "api_status": "error",
            })
            order_meta = dict(order.metadata or {})
            order_meta["api_provider"] = provider
            order_meta["api_error"] = str(exc)
            order.metadata = order_meta
            order.fulfillment_data = fulfillment
            order.save(update_fields=["fulfillment_data", "metadata", "updated_at"])
            OrderLog.objects.create(
                order=order,
                status=order.status,
                note=f"فشل إرسال الطلب إلى المزود: {exc}",
                created_by=customer,
            )
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
