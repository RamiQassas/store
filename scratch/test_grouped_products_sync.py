import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from unittest.mock import MagicMock
from django.contrib.auth import get_user_model
from apps.providers.models import ProviderProfile, ProviderProduct
from apps.providers.alkasr import AlkasrSyncService, AlkasrMapperService
from apps.catalog.models import Product, ProductVariant, Category
from apps.stores.models import Store

User = get_user_model()
print("=== Testing Product Grouping (Packages) & Store Catalog Alignment ===")

test_user, _ = User.objects.get_or_create(email="testowner@example.com", defaults={"username": "testowner"})
test_store, _ = Store.objects.get_or_create(
    subdomain="testgroupstore",
    defaults={"name": "Test Group Store", "owner": test_user, "is_active": True}
)

profile, _ = ProviderProfile.objects.get_or_create(
    provider_name="GroupTestProvider",
    store=test_store,
    defaults={
        "base_url": "https://api.alkasr-vip.com/",
        "api_token": "test-token-group",
        "is_active": True
    }
)

sync_svc = AlkasrSyncService(profile)

# Multiple packages belonging to same service/category
mock_products = [
    {
        "id": 18,
        "name": "60 UC",
        "price": 0.877,
        "params": ["playerId"],
        "category_name": "PUBG Mobile UC",
        "available": True,
        "qty_values": None,
        "product_type": "package"
    },
    {
        "id": 19,
        "name": "325 UC",
        "price": 4.50,
        "params": ["playerId"],
        "category_name": "PUBG Mobile UC",
        "available": True,
        "qty_values": None,
        "product_type": "package"
    },
    {
        "id": 20,
        "name": "660 UC",
        "price": 9.00,
        "params": ["playerId"],
        "category_name": "PUBG Mobile UC",
        "available": True,
        "qty_values": None,
        "product_type": "package"
    }
]

sync_svc.product_svc.fetch_products = MagicMock(return_value=mock_products)
sync_svc._fetch_content_tree = MagicMock(return_value={})

# Run sync catalog
sync_svc.sync_catalog()

# 1. Verify NO auto categories created
new_cats = Category.objects.filter(store=test_store, name="PUBG Mobile UC")
print("\nAuto-created categories count (Should be 0):", new_cats.count())
assert new_cats.count() == 0

# 2. Verify Catalog Product via all_objects
cat_prods = Product.all_objects.filter(store=test_store, is_active=True)
print("\nStore Catalog Products Count (Should be 1):", cat_prods.count())
for p in Product.all_objects.all():
    print(f"  - Product in DB: ID={p.id}, Name='{p.name}', Store={p.store}, Active={p.is_active}")

assert cat_prods.count() == 1

main_prod = cat_prods.first()
print(f"\nProduct Name: '{main_prod.name}', Category: {main_prod.category}, Store: {main_prod.store}")
assert main_prod.name == "PUBG Mobile UC"
assert main_prod.category is None

variants = main_prod.variants.all()
print(f"\nVariants (باقات) Count: {variants.count()}")
for v in variants:
    print(f"  - Package Variant: '{v.name}', Price: {v.price}, SKU: {v.sku}, API Product ID: {v.api_product_id}")

assert variants.count() == 3

# Clean up test records
test_store.delete()
test_user.delete()
print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
