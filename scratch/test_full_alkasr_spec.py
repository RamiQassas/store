import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from unittest.mock import MagicMock
from django.core.cache import cache
from apps.providers.models import ProviderProfile, ProviderProduct
from apps.providers.alkasr import AlkasrSyncService
from apps.catalog.models import Product, ProductVariant

print("=== Testing Full Alkasr VIP Spec & Real-time Progress ===")

profile, _ = ProviderProfile.objects.get_or_create(
    provider_name="AlkasrVIPTest",
    defaults={
        "base_url": "https://api.alkasr-vip.com/",
        "api_token": "test-token-12345",
        "is_active": True
    }
)

sync_svc = AlkasrSyncService(profile)

# Mock API product responses matching exact user documentation example:
mock_products = [
    {
        "id": 365,
        "name": "UC 60 (Amount)",
        "price": 0.104,
        "params": ["ادخل الايدي الاعب"],
        "category_name": "UC 60",
        "available": True,
        "qty_values": {
            "min": 1,
            "max": "15000"
        },
        "product_type": "amount",
        "parent_id": 0,
        "base_price": 0.10,
        "category_img": ""
    },
    {
        "id": 18,
        "name": "UC 60 (Package)",
        "price": 1.094,
        "params": ["ادخل الايدي الاعب"],
        "category_name": "PUBG Global ID UC",
        "available": True,
        "qty_values": None,
        "product_type": "package",
        "parent_id": 7,
        "base_price": 0.877,
        "category_img": "images/category/1710948113.webp"
    },
    {
        "id": 99,
        "name": "Free Fire Fixed Pack",
        "price": 2.50,
        "params": ["playerId"],
        "category_name": "Free Fire",
        "available": True,
        "qty_values": ["110", "150", "210"],
        "product_type": "fixed_quantities",
        "parent_id": 0,
        "base_price": 2.10,
        "category_img": ""
    }
]

sync_svc.product_svc.fetch_products = MagicMock(return_value=mock_products)
sync_svc._fetch_content_tree = MagicMock(return_value={})

# Run sync catalog
stats = sync_svc.sync_catalog()
print("\nSync Stats:", stats)

# Verify progress cached
progress_cached = cache.get(f"sync_progress_{profile.id}")
print("\nCached Progress Status:", progress_cached)

# Verify ProviderProducts
prods = ProviderProduct.objects.filter(profile=profile)
print(f"\nProviderProduct Count: {prods.count()}")
for p in prods:
    print(f"  - Remote ID: {p.remote_id}, Name: {p.name}, Type: {p.product_type}, Min/Max: {p.qty_min}/{p.qty_max}, QtyList: {p.qty_list}, Params: {[param.name for param in p.parameters.all()]}")

# Verify Catalog Products
cat_prods = Product.objects.filter(is_api_product=True, api_provider="alkasr")
print(f"\nCatalog Products Count: {cat_prods.count()}")
for cp in cat_prods:
    print(f"  - Catalog Product: {cp.name}, Schema: {cp.form_schema}")
    for v in cp.variants.all():
        print(f"      Variant SKU: {v.sku}, Price: {v.price}, Cost: {v.cost}, Metadata: {v.metadata}")

# Clean up test records
profile.delete()
cat_prods.delete()
print("\nTest completed cleanly!")
