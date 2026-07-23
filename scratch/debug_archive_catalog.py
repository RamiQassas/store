import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.catalog.models import Product, ProductVariant, Category
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderMapping, ProviderOrder
from apps.stores.models import Store

print("=== ALL STORES ===")
for s in Store.objects.all():
    print(f"Store ID: {s.id}, Name: '{s.name}', Subdomain: '{s.subdomain}'")

print("\n=== ALL PROVIDER PROFILES ===")
for p in ProviderProfile.objects.all():
    print(f"Profile ID: {p.id}, Provider: '{p.provider_name}', Store: {p.store_id}, BaseURL: '{p.base_url}'")

print("\n=== ALL PROVIDER PRODUCTS ===")
for pp in ProviderProduct.objects.all():
    print(f"PP ID: {pp.id}, RemoteID: '{pp.remote_id}', Name: '{pp.name}', Active: {pp.is_active}, LocalActive: {pp.local_is_active}")

print("\n=== ALL CATALOG PRODUCTS ===")
for pr in Product.all_objects.all():
    print(f"Prod ID: {pr.id}, Name: '{pr.name}', Store: {pr.store_id}, IsActive: {pr.is_active}, IsAPIProduct: {pr.is_api_product}, Category: {pr.category}")

print("\n=== ALL PROVIDER ORDERS ===")
for po in ProviderOrder.objects.all():
    print(f"PO ID: {po.id}, Product: {po.product_id}, LocalOrder: {po.local_order_id}")
