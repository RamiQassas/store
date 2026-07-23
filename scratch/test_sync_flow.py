import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from unittest.mock import MagicMock
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory
from apps.providers.alkasr import AlkasrSyncService
from apps.catalog.models import Product, ProductVariant

print("Testing sync_catalog flow...")

# Create or get test ProviderProfile
profile, _ = ProviderProfile.objects.get_or_create(
    provider_name="TestProvider",
    defaults={
        "base_url": "https://api.test-provider.com",
        "api_token": "test-token-123",
        "is_active": True
    }
)

sync_svc = AlkasrSyncService(profile)

# Mock fetch_products & fetch_content
mock_products = [
    {
        "id": "1001",
        "name": "اختبار مجوهرات كلاش اوف كلانس 500",
        "price": "5.50",
        "available": True,
        "product_type": "package",
        "category_name": "العاب الموبايل",
        "params": [{"name": "player_id", "label": "معرف اللاعب", "type": "text"}]
    },
    {
        "service": "2002",
        "title": "متابعين انستغرام 1000",
        "rate": "1.20",
        "is_active": True,
        "category": "خدمات انستغرام"
    }
]

sync_svc.product_svc.fetch_products = MagicMock(return_value=mock_products)
sync_svc._fetch_content_tree = MagicMock(return_value={})

stats = sync_svc.sync_catalog()
print("Sync stats returned:", stats)

provider_prods = ProviderProduct.objects.filter(profile=profile)
print(f"ProviderProducts count for profile: {provider_prods.count()}")
for p in provider_prods:
    print(f"  - Remote ID: {p.remote_id}, Name: {p.name}, Cost: {p.cost_price}, Active: {p.is_active}")

catalog_prods = Product.objects.filter(is_api_product=True)
print(f"\nCatalog Products with is_api_product=True: {catalog_prods.count()}")
for cp in catalog_prods:
    print(f"  - ID: {cp.id}, Name: {cp.name}, Active: {cp.is_active}")
    for v in cp.variants.all():
        print(f"      Variant: {v.name}, SKU: {v.sku}, Price: {v.price}, Cost: {v.cost}")

print("\nSync test finished successfully!")
