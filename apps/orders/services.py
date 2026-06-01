from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.orders.models import Invoice, Order, OrderItem, OrderLog
from apps.wallets.services import debit_wallet, get_or_create_wallet


def next_order_number():
    return timezone.now().strftime("ORD%Y%m%d%H%M%S%f")


@transaction.atomic
def create_order(customer, variant_id, quantity=1, fulfillment_data=None, coupon=None):
    if customer.status != "active" and customer.restriction_purchases:
        raise ValueError("حسابك مقيد من عمليات الشراء.")
    
    quantity = int(quantity)
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")
    variant = ProductVariant.objects.select_related("product").select_for_update().get(id=variant_id, is_active=True, product__is_active=True)
    subtotal = variant.price * Decimal(quantity)
    discount = Decimal("0.00")
    if coupon:
        discount = subtotal * (coupon.discount_percent / Decimal("100.00"))
    total = subtotal - discount
    order = Order.objects.create(
        customer=customer,
        number=next_order_number(),
        status=Order.Status.PROCESSING,
        total_amount=total,
        coupon=coupon,
        fulfillment_data=fulfillment_data or {},
    )
    OrderItem.objects.create(order=order, variant=variant, quantity=quantity, unit_price=variant.price, total_price=subtotal)
    
    wallet = get_or_create_wallet(customer)
    debit_wallet(wallet.id, total, reference=f"order:{order.id}", description=f"Order {order.number}", created_by=customer)
    
    OrderLog.objects.create(order=order, status=order.status, note="Order created and wallet debited.", created_by=customer)
    Invoice.objects.create(order=order, invoice_number=order.number.replace("ORD", "INV", 1), total_amount=total)
    return order
