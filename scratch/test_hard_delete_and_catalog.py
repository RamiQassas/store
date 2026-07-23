import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from unittest.mock import MagicMock
from django.contrib.auth import get_user_model
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderOrder
from apps.providers.alkasr import AlkasrSyncService
from apps.catalog.models import Product, ProductVariant
from apps.orders.models import Order, OrderItem
from apps.stores.models import Store

User = get_user_model()
print("=== Testing Hard Delete of Products with Executed Orders & Catalog Display ===")

# 1. Setup Test User and Store
test_user, _ = User.objects.get_or_create(email="harddeluser@example.com", defaults={"username": "harddeluser"})
test_store, _ = Store.objects.get_or_create(
    subdomain="harddelstore",
    defaults={"name": "Hard Delete Store", "owner": test_user, "is_active": True}
)

profile, _ = ProviderProfile.objects.get_or_create(
    provider_name="HardDelProvider",
    store=test_store,
    defaults={
        "base_url": "https://api.alkasr-vip.com/",
        "api_token": "test-token-harddel",
        "is_active": True
    }
)

sync_svc = AlkasrSyncService(profile)

# Mock provider product API response
mock_products = [
    {
        "id": 101,
        "name": "100 Diamonds",
        "price": 1.50,
        "params": ["playerId"],
        "category_name": "Free Fire Diamonds",
        "available": True,
        "qty_values": None,
        "product_type": "package"
    },
    {
        "id": 102,
        "name": "500 Diamonds",
        "price": 7.00,
        "params": ["playerId"],
        "category_name": "Free Fire Diamonds",
        "available": True,
        "qty_values": None,
        "product_type": "package"
    }
]

sync_svc.product_svc.fetch_products = MagicMock(return_value=mock_products)
sync_svc._fetch_content_tree = MagicMock(return_value={})

# Step A: Perform Sync
sync_svc.sync_catalog()

# Verify products created and visible on catalog
cat_prods_before = Product.all_objects.filter(store=test_store, is_active=True)
print(f"Products in Catalog after initial sync: {cat_prods_before.count()}")
assert cat_prods_before.count() >= 1

main_prod = cat_prods_before.first()
variant = main_prod.variants.first()
prov_prod = ProviderProduct.objects.filter(profile=profile, remote_id="101").first()

# Step B: Create Executed Orders referencing Product, Variant, and ProviderProduct
local_order = Order.objects.create(
    number="ORD-TEST-HARDDEL-01",
    customer=test_user,
    store=test_store,
    status=Order.Status.COMPLETED
)

order_item = OrderItem.objects.create(
    order=local_order,
    variant=variant,
    quantity=1,
    unit_price=variant.price,
    total_price=variant.price
)

prov_order = ProviderOrder.objects.create(
    profile=profile,
    local_order=local_order,
    product=prov_prod,
    uuid="12345678-1234-5678-1234-567812345678",
    remote_order_id="EXT-1001",
    status="completed"
)

print(f"Created Test Order '{local_order.number}' with ProviderOrder '{prov_order.remote_order_id}'")

# Step C: HARD DELETE via clear_catalog logic
print("\n--- Performing HARD DELETE of All Provider Products & Catalog Products ---")
cat_qs = Product.all_objects.filter(store=test_store, is_api_product=True)
del_cat_count, _ = cat_qs.delete()
del_prov_count, _ = ProviderProduct.objects.filter(profile=profile).delete()

print(f"Deleted {del_cat_count} Catalog items, {del_prov_count} ProviderProduct items.")

# Verify DB state after HARD DELETE
prods_after_del = Product.all_objects.filter(store=test_store)
prov_prods_after_del = ProviderProduct.objects.filter(profile=profile)
print(f"Products in Catalog DB after delete (Should be 0): {prods_after_del.count()}")
print(f"ProviderProducts in DB after delete (Should be 0): {prov_prods_after_del.count()}")
assert prods_after_del.count() == 0
assert prov_prods_after_del.count() == 0

# Verify Executed Order is STILL intact (SET_NULL on FK)
order_after = Order.objects.filter(id=local_order.id).first()
prov_order_after = ProviderOrder.objects.filter(id=prov_order.id).first()
order_item_after = OrderItem.objects.filter(id=order_item.id).first()

print(f"\nExecuted Order intact: {order_after is not None}")
print(f"ProviderOrder intact: {prov_order_after is not None}, Product FK: {prov_order_after.product_id}")
print(f"OrderItem intact: {order_item_after is not None}, Variant FK: {order_item_after.variant_id}")

assert order_after is not None
assert prov_order_after is not None
assert prov_order_after.product_id is None
assert order_item_after.variant_id is None

# Step D: Perform Fresh Sync again after Hard Delete
print("\n--- Performing Fresh Sync after Hard Delete ---")
sync_svc.sync_catalog()

fresh_prods = Product.all_objects.filter(store=test_store, is_active=True)
print(f"Products in Catalog after Fresh Sync (Should be active products): {fresh_prods.count()}")
assert fresh_prods.count() >= 1

fresh_main = fresh_prods.first()
print(f"Product Name: '{fresh_main.name}', IsActive: {fresh_main.is_active}, Variants (bakat): {fresh_main.variants.count()}")
assert fresh_main.is_active is True

# Cleanup
test_store.delete()
test_user.delete()
print("\nALL HARD DELETE AND CATALOG VISIBILITY TESTS PASSED 100% CLEANLY!")
