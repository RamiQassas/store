import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant, ProductKey
from apps.orders.models import Invoice, Order, OrderItem, OrderLog, Coupon
from apps.wallets.services import debit_wallet, get_or_create_wallet
from apps.orders.alkasr_api import place_alkasr_order


def next_order_number():
    return timezone.now().strftime("ORD%Y%m%d%H%M%S%f")


def validate_coupon(coupon, user, variant, subtotal=None):
    if not coupon.is_active:
        raise ValueError("هذا الكوبون غير نشط.")
    
    now = timezone.now()
    if coupon.expires_at and coupon.expires_at < now:
        raise ValueError("انتهت صلاحية هذا الكوبون.")
        
    if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
        raise ValueError("تم استخدام هذا الكوبون لأقصى عدد مسموح به.")
        
    # Check max uses per user
    user_uses = Order.objects.filter(customer=user, coupon=coupon).count()
    if user_uses >= coupon.max_uses_per_user:
        raise ValueError("لقد استخدمت هذا الكوبون مسبقاً.")

    # Check minimum order amount (Always required if set)
    if subtotal and subtotal < coupon.min_order_amount:
        raise ValueError(f"الحد الأدنى للطلب لاستخدام هذا الكوبون هو {coupon.min_order_amount} USD")

    # --- Match Logic (Task 3) ---
    checks = [] # List of (condition_name, is_satisfied)
    
    # 1. KYC Check
    if coupon.is_verified_only:
        checks.append(("kyc", user.is_kyc_verified))
        
    # 2. User Restriction
    if coupon.limit_to_users.exists():
        checks.append(("user", coupon.limit_to_users.filter(id=user.id).exists()))
        
    # 3. Tier Restriction
    if coupon.limit_to_tiers:
        checks.append(("tier", user.tier in coupon.limit_to_tiers))

    # 3b. Registration Date Restriction
    if coupon.valid_for_users_before:
        checks.append(("registration_date_before", user.date_joined <= coupon.valid_for_users_before))
    
    if coupon.valid_for_users_after:
        checks.append(("registration_date_after", user.date_joined >= coupon.valid_for_users_after))
        
    # 4. Area Restrictions (KYC-based)
    if coupon.limit_to_area or coupon.limit_to_place_of_birth:
        kyc = getattr(user, 'kyc_request', None)
        area_satisfied = False
        if kyc:
            if coupon.limit_to_area:
                match_res = coupon.limit_to_area.lower() in kyc.current_residence.lower()
                if coupon.allow_area_type == Coupon.AreaType.RESIDENCE and match_res:
                    area_satisfied = True
                elif coupon.allow_area_type == Coupon.AreaType.BOTH and match_res:
                    area_satisfied = True
            
            if coupon.limit_to_place_of_birth:
                match_birth = coupon.limit_to_place_of_birth.lower() in kyc.place_of_birth.lower()
                if coupon.allow_area_type == Coupon.AreaType.BIRTH and match_birth:
                    area_satisfied = True
                elif coupon.allow_area_type == Coupon.AreaType.BOTH and match_birth:
                    area_satisfied = True
        checks.append(("area", area_satisfied))

    # 5. IP-based Geographic matching (Task 2)
    if coupon.limit_to_ip_countries or coupon.limit_to_ip_cities:
        ip_satisfied = False
        user_country = getattr(user, 'last_country', '').upper()
        user_city = getattr(user, 'last_city', '').lower()
        
        if coupon.limit_to_ip_countries and user_country in [c.upper() for c in coupon.limit_to_ip_countries]:
            ip_satisfied = True
        
        if coupon.limit_to_ip_cities and any(city.lower() in user_city for city in coupon.limit_to_ip_cities):
            ip_satisfied = True
            
        checks.append(("ip_geo", ip_satisfied))

    # 6. Product Limit
    if not coupon.apply_to_all_products:
        product_match = False
        if coupon.limit_to_products.exists():
            if coupon.limit_to_products.filter(id=variant.product.id).exists():
                product_match = True
        else:
            # If no products specified but apply_to_all is False, it shouldn't match anything?
            # Or should it be treated as "no limit"? Usually it means "specific products only".
            product_match = False
        checks.append(("product", product_match))

    # Evaluate checks based on match_mode
    if not checks:
        # No specific restrictions (beyond global ones like expiry/verified_only handled above)
        pass 
    else:
        satisfied_count = sum(1 for name, satisfied in checks if satisfied)
        
        if coupon.match_mode == Coupon.MatchMode.ALL:
            # ALL conditions must be met
            if satisfied_count < len(checks):
                # Find first failed condition for better error message
                failed = [name for name, satisfied in checks if not satisfied][0]
                error_msgs = {
                    "kyc": "هذا الكوبون مخصص للحسابات الموثقة فقط.",
                    "user": "هذا الكوبون غير مخصص لحسابك.",
                    "tier": "هذا الكوبون غير متاح لفئتك.",
                    "registration_date_before": "هذا الكوبون متاح فقط للحسابات القديمة (قبل تاريخ محدد).",
                    "registration_date_after": "هذا الكوبون متاح فقط للحسابات الجديدة (بعد تاريخ محدد).",
                    "area": "هذا الكوبون غير متاح لمنطقتك الجغرافية (KYC).",
                    "ip_geo": "هذا الكوبون غير متاح لموقعك الحالي.",
                    "product": f"هذا الكوبون صالح فقط لمنتج: {coupon.limit_to_product.name if coupon.limit_to_product else 'منتج آخر'}"
                }
                raise ValueError(error_msgs.get(failed, "لا تتوفر شروط استخدام الكوبون."))
        else:
            # ANY condition is enough
            if satisfied_count == 0:
                raise ValueError("عذراً، هذا الكوبون غير متاح لك (لا تنطبق عليك أي من شروط الاستخدام).")

    # Calculate discount
    discount = Decimal("0.00")
    if subtotal:
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount = (subtotal * (coupon.discount_percent / Decimal("100.00"))).quantize(Decimal("0.01"))
        elif coupon.discount_type == Coupon.DiscountType.FIXED_AMOUNT:
            discount = min(coupon.discount_amount, subtotal)
            
    return discount


@transaction.atomic
def create_order(customer, variant_id, quantity=1, fulfillment_data=None, coupon=None, metadata=None,
                 shipping_name=None, shipping_phone=None, shipping_address=None):
    if customer.restriction_purchases:
        raise ValueError("حسابك مقيد من عمليات الشراء.")

    quantity = int(quantity)
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")
    variant = ProductVariant.objects.select_related("product").select_for_update().get(id=variant_id, is_active=True, product__is_active=True)

    # Provider qty_values validation according to API specifications
    if variant.metadata and isinstance(variant.metadata, dict):
        qty_type = variant.metadata.get("qty_type") or "fixed"
        allow_custom = variant.metadata.get("allow_custom_quantity", False)
        qty_list = variant.metadata.get("qty_list") or []

        if qty_type == "fixed" or not allow_custom:
            if qty_list:
                if str(quantity) not in [str(x) for x in qty_list]:
                    raise ValueError(f"الكمية المسموح بها لهذه الباقة هي إحدى القيم التالية فقط: {', '.join(qty_list)}")
            else:
                quantity = 1
        elif qty_type == "range":
            qty_min = int(variant.metadata.get("qty_min") or 1)
            qty_max = int(variant.metadata.get("qty_max") or 999999)
            if quantity < qty_min:
                raise ValueError(f"الحد الأدنى المسموح به للكمية هو {qty_min}")
            if quantity > qty_max:
                raise ValueError(f"الحد الأقصى المسموح به للكمية هو {qty_max}")

    # Inventory checking and decrementing
    from apps.catalog.models import Product
    product = Product.objects.select_for_update().get(id=variant.product_id)
    if product.track_inventory:
        if product.quantity < quantity:
            raise ValueError(f"الكمية المطلوبة ({quantity}) غير متوفرة في المخزون للمنتج {product.name}. الكمية المتوفرة حالياً هي: {product.quantity}")
        
        product.quantity -= quantity
        if product.quantity <= 0:
            product.quantity = 0
            product.is_out_of_stock = True
            product.save(update_fields=["quantity", "is_out_of_stock"])
            
            # Notify staff that product is out of stock
            from apps.notifications.services import notify_staff
            notify_staff(
                title=f"نفاد مخزون المنتج: {product.name}",
                body=f"نود إفادتكم بأن كمية المنتج '{product.name}' قد نفدت بالكامل وتم تعديل حالته إلى 'غير متوفر'.",
                category="admin_new_order"
            )
        else:
            product.save(update_fields=["quantity"])
            # Check low stock threshold
            if product.quantity <= product.low_stock_threshold:
                from apps.notifications.services import notify_staff
                notify_staff(
                    title=f"تنبيه: مخزون منخفض للمنتج: {product.name}",
                    body=f"نود إفادتكم بأن كمية المنتج '{product.name}' قد وصلت للحد المنخفض المتبقي: {product.quantity} (حد التنبيه: {product.low_stock_threshold}).",
                    category="admin_new_order"
                )

    # Validate shipping info if physical product
    if variant.product.product_type == 'physical' and not variant.product.form_schema.get("fields"):
        if not (shipping_name and shipping_phone and shipping_address):
            raise ValueError("جميع حقول الشحن والتوصيل مطلوبة للمنتجات المادية.")

    # Get price based on user tier
    price = variant.get_price_for_user(customer)

    subtotal = price * Decimal(quantity)
    discount = Decimal("0.00")
    if coupon:
        discount = validate_coupon(coupon, customer, variant, subtotal=subtotal)
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    total = subtotal - discount
    if total < 0: total = Decimal("0.00")

    # Auto-delivery keys check
    locked_keys = []
    if variant.delivery_type == 'keys':
        key_ids = list(ProductKey.objects.filter(
            variant=variant,
            is_used=False
        ).values_list('id', flat=True)[:quantity])

        if len(key_ids) < quantity:
            raise ValueError("المخزون غير كافي لتلبية الكمية المطلوبة من هذا المنتج.")

        locked_keys = list(ProductKey.objects.filter(id__in=key_ids).select_for_update())
        if len(locked_keys) < quantity:
            raise ValueError("المخزون غير كافي لتلبية الكمية المطلوبة من هذا المنتج.")

    status = Order.Status.PROCESSING
    final_fulfillment_data = fulfillment_data or {}
    api_order_id = None
    api_order_uuid = None

    if variant.product.is_api_product and variant.api_product_id:
        api_order_uuid = uuid.uuid4()
        provider = variant.product.api_provider or "alkasr"
        
        if provider == "alkasr":
            res = place_alkasr_order(variant.api_product_id, quantity, api_order_uuid, metadata or {}, store=variant.product.store)
        else:
            # Alternate API provider placeholder routing
            res = {
                "status": "OK",
                "data": {
                    "status": "wait",
                    "order_id": f"{provider.upper()}-{uuid.uuid4().hex[:8]}"
                }
            }
            
        if res.get("status") == "OK":
            data = res.get("data", {})
            api_status = data.get("status")
            api_order_id = data.get("order_id")
            
            final_fulfillment_data["api_order_id"] = api_order_id
            final_fulfillment_data["api_status"] = api_status
            final_fulfillment_data["api_response"] = res
            final_fulfillment_data["api_provider"] = provider
            
            if api_status == "accept":
                status = Order.Status.COMPLETED
            elif api_status == "reject":
                error_msg = res.get("message") or "الطلب مرفوض من المزود."
                raise ValueError(f"فشل إرسال الطلب للمزود: {error_msg}")
            else: # wait
                status = Order.Status.PROCESSING
        else:
            raw_error = res.get("message") or res.get("error") or "خطأ غير معروف من المزود."
            error_code_match = None
            # Extract numeric error code from message if present (e.g. "ERR-100")
            import re
            m = re.search(r'ERR-(\d+)', raw_error)
            if m:
                error_code_match = int(m.group(1))
            
            # Notify admin with full details
            try:
                from apps.notifications.services import notify_provider_error
                provider_name = variant.product.api_provider or "alkasr"
                notify_provider_error(
                    error_code=error_code_match or 0,
                    provider_name=provider_name,
                    product_id=variant.api_product_id,
                    detail=raw_error,
                    store=str(variant.product.store) if variant.product.store else None,
                )
            except Exception as notify_err:
                import logging
                logging.getLogger(__name__).warning(f"Failed to send provider error notification: {notify_err}")
            
            # Show customer a safe, brief message with error code only
            if error_code_match:
                customer_msg = f"لم يتم معالجة طلبك بسبب خطأ مؤقت (رمز: ERR-{error_code_match}). يرجى التواصل مع فريق الدعم لحل المشكلة."
            else:
                customer_msg = "لم يتم معالجة طلبك بسبب خطأ مؤقت. يرجى التواصل مع فريق الدعم."
            raise ValueError(customer_msg)
    elif variant.delivery_type == 'keys':
        status = Order.Status.COMPLETED
        final_fulfillment_data['keys'] = [k.key_code for k in locked_keys]

    order = Order.objects.create(
        customer=customer,
        number=next_order_number(),
        status=status,
        total_amount=total,
        original_total=subtotal,
        coupon=coupon,
        fulfillment_data=final_fulfillment_data,
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
        total_price=subtotal
    )

    if variant.delivery_type == 'keys':
        for key in locked_keys:
            key.is_used = True
            key.used_by = customer
            key.used_at = timezone.now()
            key.order = order
            key.save(update_fields=['is_used', 'used_by', 'used_at', 'order'])
    
    wallet = get_or_create_wallet(customer)
    
    # Convert total (USD) to wallet currency for debiting
    debit_amount = total
    if wallet.currency.code != "USD":
        debit_amount = wallet.currency.from_base(total)
        
    debit_wallet(wallet.id, debit_amount, reference=f"order:{order.id}", description=f"Order {order.number}", created_by=customer)
    
    log_note = "Order created and wallet debited."
    if variant.product.is_api_product and variant.api_product_id:
        log_note = f"تم إنشاء الطلب وربطه بالـ API (رقم الطلب الخارجي: {api_order_id})."
    elif variant.delivery_type == 'keys':
        log_note = "تم إنشاء الطلب وتسليم الأكواد تلقائياً بنجاح."
    OrderLog.objects.create(order=order, status=order.status, note=log_note, created_by=customer)
    Invoice.objects.create(order=order, invoice_number=order.number.replace("ORD", "INV", 1), total_amount=total)

    from apps.notifications.services import notify_staff
    notify_staff(
        title="طلب جديد",
        body=f"تم إنشاء طلب جديد برقم {order.number} بقيمة {total} من قبل {customer.email}",
        action_url=f"/control/orders/{order.id}/",
        category='admin_new_order'
    )

    return order
