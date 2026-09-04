import os
import sys
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory
from apps.catalog.models import ProductVariant, Product

print("ProviderProfiles:")
for p in ProviderProfile.objects.all():
    print(f"ID: {p.id}, Name: {p.provider_name}, Store: {p.store_id}")

print("\nProviderProducts:")
for pp in ProviderProduct.objects.all()[:10]:
    print(f"ID: {pp.id}, Profile: {pp.profile_id}, RemoteID: {pp.remote_id}, Name: {pp.name}, Active: {pp.is_active}")

print("\nProductVariants with API:")
for v in ProductVariant.objects.filter(api_product_id__isnull=False)[:10]:
    print(f"Variant: {v.name}, Product: {v.product.name}, API ID: {v.api_product_id}")

print("\nProduct with is_api_product=True:")
for p in Product.objects.filter(is_api_product=True)[:10]:
    print(f"Product: {p.name}, API Product ID: {p.api_product_id}, Provider: {p.api_provider}")
