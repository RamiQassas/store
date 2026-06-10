from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.orders.models import Invoice, Order, OrderItem, OrderLog
from apps.wallets.services import debit_wallet, get_or_create_wallet


def next_order_number():
    return timezone.now().strftime("ORD%Y%m%d%H%M%S%f")


def validate_coupon(coupon, user, variant, subtotal=None):
    if not coupon.is_active:
        raise ValueError("هذا الكوبون غير نشط.")
    
    now = timezone.now()
    if coupon.expires_at and coupon.expires_at < now:
        raise ValueError("انتهت صلاحية هذا الكوبون.")
        
    if coupon.is_verified_only and not user.is_kyc_verified:
        raise ValueError("هذا الكوبون مخصص للحسابات الموثقة فقط.")
        
    if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
        raise ValueError("تم استخدام هذا الكوبون لأقصى عدد مسموح به.")
        
    # Check max uses per user
    user_uses = Order.objects.filter(customer=user, coupon=coupon).count()
    if user_uses >= coupon.max_uses_per_user:
        raise ValueError("لقد استخدمت هذا الكوبون مسبقاً.")
        
    # Check product limit
    if not coupon.apply_to_all_products:
        if coupon.limit_to_product and variant.product != coupon.limit_to_product:
            raise ValueError(f"هذا الكوبون صالح فقط لمنتج: {coupon.limit_to_product.name}")
        elif not coupon.limit_to_product:
             raise ValueError("هذا الكوبون غير صالح لهذا المنتج.")
             
    # Calculate discount
    discount = Decimal("0.00")
    if subtotal:
        if coupon.discount_percent > 0:
            discount = subtotal * (coupon.discount_percent / Decimal("100.00"))
        elif coupon.discount_amount > 0:
            discount = coupon.discount_amount
            
    return discount


@transaction.atomic
def create_order(customer, variant_id, quantity=1, fulfillment_data=None, coupon=None, metadata=None):
    if customer.restriction_purchases:
        raise ValueError("حسابك مقيد من عمليات الشراء.")

    quantity = int(quantity)
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")
    variant = ProductVariant.objects.select_related("product").select_for_update().get(id=variant_id, is_active=True, product__is_active=True)

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
    order = Order.objects.create(
        customer=customer,
        number=next_order_number(),
        status=Order.Status.PROCESSING,
        total_amount=total,
        coupon=coupon,
        fulfillment_data=fulfillment_data or {},
        metadata=metadata or {},
    )
    OrderItem.objects.create(
        order=order, 
        variant=variant, 
        quantity=quantity, 
        unit_price=price, 
        unit_cost=variant.cost,
        total_price=subtotal
    )
    
    wallet = get_or_create_wallet(customer)
    
    # Convert total (USD) to wallet currency for debiting
    debit_amount = total
    if wallet.currency.code != "USD":
        debit_amount = wallet.currency.from_base(total)
        
    debit_wallet(wallet.id, debit_amount, reference=f"order:{order.id}", description=f"Order {order.number}", created_by=customer)
    
    OrderLog.objects.create(order=order, status=order.status, note="Order created and wallet debited.", created_by=customer)
    Invoice.objects.create(order=order, invoice_number=order.number.replace("ORD", "INV", 1), total_amount=total)

    from apps.notifications.services import notify_staff
    notify_staff(
        title="طلب جديد",
        body=f"تم إنشاء طلب جديد برقم {order.number} بقيمة {total} من قبل {customer.email}",
        action_url=f"/control/orders/{order.id}/"
    )

    return order
