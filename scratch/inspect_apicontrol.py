import os
import sys
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory
from apps.catalog.models import APIIntegration, Product, ProductVariant
from apps.orders.models import Order

print("=== PROFILES ===")
for p in ProviderProfile.objects.all():
    print(f"Profile ID: {p.id}, Name: {p.provider_name}, Store: {p.store_id}, Products: {p.products.count()}")

print("\n=== INTEGRATIONS ===")
for i in APIIntegration.objects.all():
    print(f"Integration ID: {i.id}, Name: {i.name}, Provider: {i.provider}, Store: {i.store_id}, Active: {i.is_active}")

print(f"\nTotal ProviderProduct count: {ProviderProduct.objects.count()}")
print(f"Active ProviderProduct count: {ProviderProduct.objects.filter(is_active=True).count()}")
print(f"Local Linked Variants count: {ProductVariant.objects.filter(api_product_id__isnull=False).count()}")

print("\n=== ORDERS WITH API ===")
for o in Order.objects.filter(status__in=[Order.Status.COMPLETED, Order.Status.PROCESSING])[:10]:
    print(f"Order #{o.number}, Status: {o.status}, Amount: {o.total_amount}, API Order ID: {o.api_order_id}")
