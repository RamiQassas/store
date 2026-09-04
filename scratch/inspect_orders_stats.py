import os
import sys
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.orders.models import Order, OrderItem
from apps.providers.models import ProviderOrder

orders = Order.objects.filter(status__in=[Order.Status.COMPLETED, Order.Status.PROCESSING]).order_by("-created_at")
print(f"Total orders: {orders.count()}")
for o in orders:
    print(f"\nOrder #{o.number}, Status: {o.status}, Total Amount: {o.total_amount}, API Order ID: {o.api_order_id}")
    for it in o.items.all():
        print(f"  Item: {it.product_name_cached} | Qty: {it.quantity} | Unit Price: {it.unit_price} | Total: {it.total_price} | Unit Cost: {it.unit_cost} | Variant Cost: {it.variant.cost if it.variant else None}")
    for po in o.provider_orders.all():
        print(f"  ProviderOrder: {po.provider} | Remote ID: {po.remote_order_id} | Status: {po.status} | Cost: {po.cost_amount}")
